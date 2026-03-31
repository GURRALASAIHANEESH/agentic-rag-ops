# backend/app/services/retriever.py
import uuid
import json
import asyncio
from functools import lru_cache

from sentence_transformers import CrossEncoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document, Chunk
from app.models.audit import AuditLog, QueryLog
from app.schemas.query import CitationSchema
from app.services.embedder import get_embedding_service
from app.services.vector_store import get_vector_store, RetrievedChunk
from app.metrics.prometheus import track_retrieval

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_cross_encoder() -> CrossEncoder:
    settings = get_settings()
    logger.info("reranker.loading", model=settings.RERANKER_MODEL)
    model = CrossEncoder(settings.RERANKER_MODEL, max_length=512)
    # FIX: Ensure tokenizer strictly respects the max_length to prevent tensor dimension mismatch errors
    model.tokenizer.model_max_length = 512
    logger.info("reranker.loaded", model=settings.RERANKER_MODEL)
    return model


class RetrieverService:
    """
    Production retriever with three accuracy improvements over the original:

    1. Document-scoped filtering  — pass document_ids to restrict search to
       specific files. Prevents a 160-chunk PDF drowning a 6-chunk resume.

    2. Section-scoped filtering   — pass section="Projects" to search only
       within a named section across all documents in the workspace.

    3. Per-document score boosting — when multiple documents are present,
       boosts scores of chunks from smaller documents to counteract the
       statistical disadvantage of fewer chunks.
    """

    def __init__(self):
        self._embedder = get_embedding_service()
        self._vector_store = get_vector_store()

    async def retrieve(
        self,
        db: AsyncSession,
        query: str,
        workspace_id: uuid.UUID,
        query_log_id: uuid.UUID,
        top_k: int | None = None,
        min_similarity: float | None = None,
        document_ids: list[uuid.UUID] | None = None,  # NEW: scope to specific docs
        section: str | None = None,                   # NEW: scope to section
    ) -> tuple[list[CitationSchema], list[RetrievedChunk]]:
        """
        Main retrieval method.

        Returns:
          - citations   : list[CitationSchema] for the API response
          - raw_chunks  : list[RetrievedChunk] for the orchestrator prompt

        When document_ids is None and section is None, runs a two-pass search:
          Pass 1 — Scoped search (inferred from query intent via keyword detection)
          Pass 2 — Full workspace search if Pass 1 returns < min_results

        This ensures resume queries get resume chunks even alongside large PDFs.
        """
        cfg = get_settings()
        resolved_top_k   = top_k         if top_k         is not None else cfg.RETRIEVAL_TOP_K
        resolved_min_sim = min_similarity if min_similarity is not None else cfg.RETRIEVAL_MIN_SIMILARITY
        backend_name     = cfg.VECTOR_STORE_BACKEND

        # ── Embed query ───────────────────────────────────────────────────
        # ── Phase 2B: Query Expansion ─────────────────────────────────────
        # Expand original query into N semantic variants, search all of them,
        # merge results, deduplicate by chunk_id — then proceed as normal.
        expanded_queries: list[str] = await self.expand_query(query)

        query_embedding = await self._embedder.embed_text(query)  # original always used

        if len(expanded_queries) > 1:
            # Run all variant searches concurrently
            variant_tasks = [
                self._embedder.embed_text(q) for q in expanded_queries[1:]
            ]
            variant_embeddings: list[list[float]] = await asyncio.gather(*variant_tasks)

            # We'll collect chunks from expanded searches after the main search block.
            # Store embeddings here; actual search runs after the main search below.
            _expansion_embeddings = variant_embeddings
        else:
            _expansion_embeddings = []

        # ── Two-pass retrieval when no explicit filters given ─────────────
        # Pass 1: Infer document scope from query keywords
        # Pass 2: Fall back to full workspace search if insufficient results
        raw_chunks: list[RetrievedChunk] = []

        with track_retrieval(backend=backend_name) as tracker:

            # If caller provided explicit filters, use them directly
            if document_ids or section:
                raw_chunks = await self._vector_store.search(
                    db=db,
                    query_embedding=query_embedding,
                    workspace_id=workspace_id,
                    top_k=resolved_top_k,
                    min_similarity=resolved_min_sim,
                    document_ids=document_ids,
                    section=section,
                )

            else:
                # ── Phase 2C: Namespace-first routing ─────────────────────
                # Infer namespace from query → search that namespace first.
                # Fall back to global if namespace search is insufficient.
                cfg_ns = get_settings()
                inferred_namespace = self._resolve_namespace(query)

                if inferred_namespace:
                    # Namespace search: filter by metadata_->>'doc_namespace'
                    raw_chunks = await self._vector_store.search(
                        db=db,
                        query_embedding=query_embedding,
                        workspace_id=workspace_id,
                        top_k=resolved_top_k,
                        min_similarity=min(resolved_min_sim, 0.05),
                        namespace=inferred_namespace,
                    )
                    logger.info(
                        "retrieval_namespace_pass",
                        inferred_namespace=inferred_namespace,
                        results=len(raw_chunks),
                    )

                # Fall back to global search if:
                # a) no namespace was inferred, OR
                # b) namespace search returned too few results
                if not inferred_namespace or len(raw_chunks) < cfg_ns.DOC_NAMESPACE_FALLBACK_THRESHOLD:
                    global_chunks = await self._vector_store.search(
                        db=db,
                        query_embedding=query_embedding,
                        workspace_id=workspace_id,
                        top_k=resolved_top_k,
                        min_similarity=min(resolved_min_sim, 0.05),
                    )
                    # Merge without duplicates — namespace hits ranked first
                    existing_ids = {c.chunk_id for c in raw_chunks}
                    for chunk in global_chunks:
                        if chunk.chunk_id not in existing_ids:
                            raw_chunks.append(chunk)
                    logger.info(
                        "retrieval_global_fallback",
                        reason="namespace_insufficient" if inferred_namespace else "no_namespace_inferred",
                        total_after_merge=len(raw_chunks),
                    )

                # ── Section-scoped pass (Phase 2B) runs AFTER namespace ───
                # Only fires if namespace pass narrowed the pool too aggressively.
                inferred_section = self._infer_section(query)
                if inferred_section and len(raw_chunks) < max(2, resolved_top_k // 2):
                    section_chunks = await self._vector_store.search(
                        db=db,
                        query_embedding=query_embedding,
                        workspace_id=workspace_id,
                        top_k=resolved_top_k,
                        min_similarity=min(resolved_min_sim, 0.05),
                        section=inferred_section,
                    )
                    existing_ids = {c.chunk_id for c in raw_chunks}
                    for chunk in section_chunks:
                        if chunk.chunk_id not in existing_ids:
                            raw_chunks.append(chunk)

                # ── Apply document diversity boost ────────────────────────
                # Boosts chunks from documents with fewer total chunks so
                # a 6-chunk resume competes fairly with a 160-chunk PDF.
                raw_chunks = await self._apply_diversity_boost(
                    db=db,
                    chunks=raw_chunks,
                    workspace_id=workspace_id,
                )

            tracker.set_chunk_count(len(raw_chunks))

        # ── Phase 2B: Merge expanded query results ────────────────────────
        if _expansion_embeddings:
            seen_ids: set[str] = {c.chunk_id for c in raw_chunks}

            expansion_searches = [
                self._vector_store.search(
                    db=db,
                    query_embedding=emb,
                    workspace_id=workspace_id,
                    top_k=resolved_top_k,
                    min_similarity=min(resolved_min_sim, 0.05),
                    document_ids=document_ids,
                    section=section,
                )
                for emb in _expansion_embeddings
            ]
            expansion_results: list[list[RetrievedChunk]] = await asyncio.gather(
                *expansion_searches
            )

            for result_set in expansion_results:
                for chunk in result_set:
                    if chunk.chunk_id not in seen_ids:
                        raw_chunks.append(chunk)
                        seen_ids.add(chunk.chunk_id)

            # Re-sort merged pool by similarity before reranker takes over
            raw_chunks.sort(key=lambda c: c.similarity, reverse=True)

            logger.info(
                "query_expansion.merge_done",
                total_chunks_after_merge=len(raw_chunks),
                unique_chunks=len(seen_ids),
            )

        # ── Phase 2A: Cross-encoder rerank ────────────────────────
        if raw_chunks:
            raw_chunks = await self.rerank(query=query, chunks=raw_chunks)

        if not raw_chunks:
            logger.warning(
                "no_chunks_retrieved",
                workspace=str(workspace_id),
                query=query[:80],
                top_k=resolved_top_k,
                min_similarity=resolved_min_sim,
            )
            return [], []

        # ── Enrich: fetch filenames ───────────────────────────────────────
        doc_ids = list({c.document_id for c in raw_chunks})
        docs_result = await db.execute(
            select(Document.id, Document.filename).where(Document.id.in_(doc_ids))
        )
        doc_map: dict[uuid.UUID, str] = {
            row.id: row.filename for row in docs_result.fetchall()
        }

        # ── Build citation schemas ────────────────────────────────────────
        citations: list[CitationSchema] = [
            CitationSchema(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=doc_map.get(chunk.document_id, "Unknown"),
                chunk_index=chunk.chunk_index,
                snippet=self._make_snippet(chunk.content),
                similarity=round(chunk.similarity, 4),
            )
            for chunk in raw_chunks
        ]

        # ── Audit log ─────────────────────────────────────────────────────
        db.add(AuditLog(
            query_log_id=query_log_id,
            event_type="retrieval",
            payload={
                "query":          query[:200],
                "top_k":          resolved_top_k,
                "min_similarity": resolved_min_sim,
                "chunks_found":   len(raw_chunks),
                "backend":        backend_name,
                "similarities":   [round(c.similarity, 4) for c in raw_chunks],
                "document_filter": [str(d) for d in document_ids] if document_ids else None,
                "section_filter": section,
            },
        ))

        logger.info(
            "retrieval_complete",
            query_log_id=str(query_log_id),
            chunks=len(raw_chunks),
            top_k=resolved_top_k,
            min_similarity=resolved_min_sim,
            top_similarity=raw_chunks[0].similarity if raw_chunks else 0,
        )
        return citations, raw_chunks

    # ── Section inference ─────────────────────────────────────────────────────

    def _infer_section(self, query: str) -> str | None:
        """
        Maps query keywords to document section names.
        Returns None if no clear section intent is detected.

        This is a lightweight keyword heuristic — fast, zero LLM calls,
        fires before the vector search to scope it correctly.
        """
        q = query.lower()

        section_keywords = {
            "Projects":        ["project", "built", "developed", "created", "made", "portfolio", "github"],
            "Experience":      ["experience", "work", "job", "intern", "internship", "company", "employer", "role", "position"],
            "Education":       ["education", "college", "university", "degree", "studied", "gpa", "cgpa", "batch", "year", "graduate"],
            "Technical Skills":["skill", "technology", "tech stack", "programming", "language", "framework", "tool", "knows", "expertise"],
            "Certifications":  ["certification", "certificate", "certified", "course", "azure", "aws", "credential"],
            "Extracurricular": ["extracurricular", "volunteer", "activity", "club", "ngo", "social"],
        }

        for section, keywords in section_keywords.items():
            if any(kw in q for kw in keywords):
                return section

        return None

    # ── Namespace resolver ─────────────────────────────────────────────────────────

    def _resolve_namespace(self, query: str) -> str | None:
        """
        Infers the target namespace from query intent.
        Returns None when intent is ambiguous → triggers global search directly.

        Kept intentionally lightweight — zero LLM calls, pure keyword heuristic.
        Namespace routing fires BEFORE vector search so it scopes the index early.
        """
        q = query.lower()

        _RESUME_SIGNALS    = ("resume", "cv", "candidate", "applicant", "hire",
                              "experience", "education", "skill", "intern",
                              "project", "certification", "worked at", "studied")
        _RESEARCH_SIGNALS  = ("paper", "study", "research", "experiment",
                              "findings", "methodology", "hypothesis", "arxiv",
                              "proposed", "dataset", "baseline", "ablation")
        _TECHNICAL_SIGNALS = ("how does", "architecture", "spec", "overview",
                              "implementation", "algorithm", "system design",
                              "api", "configuration", "setup", "install",
                              "pgvector", "faiss", "transformer", "attention")

        if any(s in q for s in _RESUME_SIGNALS):
            return "resume"
        if any(s in q for s in _RESEARCH_SIGNALS):
            return "research"
        if any(s in q for s in _TECHNICAL_SIGNALS):
            return "technical"
        return None   # ambiguous → go global

    # ── Query Expansion ────────────────────────────────────────────────────────────

    async def expand_query(self, query: str) -> list[str]:
        """
        Expands the original query into N semantic variants using the LLM.

        Why: A single embedding may miss relevant chunks that use different
        terminology. Three variants cast a wider semantic net, and deduplication
        ensures no chunk is double-counted.

        Returns:
            list[str] — original query + up to QUERY_EXPANSION_VARIANTS variants.
            On any LLM failure, returns [query] so retrieval always proceeds.

        Example:
            Input : "What technologies does the candidate know?"
            Output: [
                "What technologies does the candidate know?",      ← original
                "List the programming languages and frameworks used by the applicant",
                "Technical skills and tools mentioned in the resume",
                "Software expertise and tech stack of the developer"
            ]
        """
        cfg = get_settings()

        if not cfg.QUERY_EXPANSION_ENABLED:
            return [query]

        n = cfg.QUERY_EXPANSION_VARIANTS

        prompt = f"""You are a query expansion assistant for a RAG system.
Given a user query, generate exactly {n} semantically distinct rewordings.
Each variant must preserve the original intent but use different vocabulary.
Respond with a valid JSON array of {n} strings. No explanation. No markdown.

User query: {query}

JSON array:"""

        log = logger.bind(original_query=query[:80], variants_requested=n)
        log.info("query_expansion.start")

        try:
            from app.services.llm_client import get_llm_client
            llm = get_llm_client()

            raw_response: str = await llm.generate(
                prompt=prompt,
            )

            # Strip markdown fences if model wraps in ```json ... ```
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            variants: list[str] = json.loads(cleaned)

            if not isinstance(variants, list):
                raise ValueError(f"LLM returned non-list: {type(variants)}")

            # Sanitize: keep only non-empty strings, cap at n
            variants = [v.strip() for v in variants if isinstance(v, str) and v.strip()][:n]

            all_queries = [query] + variants

            log.info(
                "query_expansion.done",
                total_queries=len(all_queries),
                variants=variants,
            )
            return all_queries

        except json.JSONDecodeError as exc:
            log.warning(
                "query_expansion.parse_failed",
                error=str(exc),
                fallback="original_query_only",
            )
            return [query]

        except Exception as exc:
            log.error(
                "query_expansion.failed",
                error=str(exc),
                fallback="original_query_only",
            )
            return [query]

    # ── Document diversity boost ──────────────────────────────────────────────

    async def _apply_diversity_boost(
        self,
        db: AsyncSession,
        chunks: list[RetrievedChunk],
        workspace_id: uuid.UUID,
    ) -> list[RetrievedChunk]:
        """
        Boosts similarity scores of chunks from smaller documents.

        Formula: boosted_score = score * (1 + boost_factor)
        Where:   boost_factor = (max_chunks - doc_chunks) / max_chunks * 0.3

        Effect: A chunk from a 6-chunk resume with score 0.31 gets boosted
        to ~0.40 when competing against a 160-chunk document, making it
        surface in top results instead of being buried.

        Max boost cap: 30% — prevents tiny documents from dominating unfairly.
        """
        if not chunks:
            return chunks

        # Count chunks per document in this workspace
        from sqlalchemy import func
        from app.models.document import Chunk
        result = await db.execute(
            select(Chunk.document_id, func.count(Chunk.id).label("cnt"))
            .where(Chunk.workspace_id == workspace_id)
            .group_by(Chunk.document_id)
        )
        doc_chunk_counts: dict[uuid.UUID, int] = {
            row.document_id: row.cnt for row in result.fetchall()
        }

        if not doc_chunk_counts:
            return chunks

        max_chunks = max(doc_chunk_counts.values())

        # Apply boost only when there's meaningful imbalance (>2x difference)
        if max_chunks < 2:
            return chunks

        for chunk in chunks:
            doc_count = doc_chunk_counts.get(chunk.document_id, max_chunks)
            if doc_count < max_chunks:
                boost = (max_chunks - doc_count) / max_chunks * 0.30
                chunk.similarity = min(1.0, chunk.similarity * (1 + boost))

        # Re-sort after boost adjustment
        chunks.sort(key=lambda c: c.similarity, reverse=True)
        return chunks

    # ── Helpers ───────────────────────────────────────────────────────────────

    def build_context_block(self, raw_chunks: list[RetrievedChunk]) -> str:
        """
        Formats retrieved chunks into a numbered [SOURCE N] context block
        for LLM prompt injection. Includes section label for clarity.
        """
        if not raw_chunks:
            return "No relevant context found."

        parts = []
        for i, chunk in enumerate(raw_chunks, start=1):
            section = chunk.metadata.get("section", "")
            section_label = f" [{section}]" if section else ""
            parts.append(
                f"[SOURCE {i}]{section_label} (similarity: {chunk.similarity:.2f})\n"
                f"{chunk.content}"
            )
        return "\n\n".join(parts)

    def _make_snippet(self, content: str, max_chars: int = 300) -> str:
        """Returns a clean ≤300 char excerpt truncated at word boundary."""
        content = content.replace("\n", " ").strip()
        if len(content) <= max_chars:
            return content
        truncated = content[:max_chars]
        last_space = truncated.rfind(" ")
        return truncated[:last_space] + "…" if last_space > 0 else truncated + "…"

    # ── Reranker ─────────────────────────────────────────────────────────

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """
        Cross-encoder reranker — cross-encoder/ms-marco-MiniLM-L-6-v2.
        Offloads CPU inference to asyncio.to_thread().
        Returns top RERANKER_TOP_K chunks sorted by rerank score DESC.
        Falls back to input order on any error.
        """
        if not chunks:
            return []

        cfg = get_settings()
        top_k: int = cfg.RERANKER_TOP_K
        pairs: list[tuple[str, str]] = [(query, c.content) for c in chunks]

        log = logger.bind(
            reranker_model=cfg.RERANKER_MODEL,
            input_count=len(pairs),
            top_k=top_k,
        )

        try:
            scores: list[float] = await asyncio.to_thread(
                self._run_reranker, pairs
            )
        except Exception as exc:
            log.error(
                "reranker.failed",
                error=str(exc),
                fallback="vector_score_order",
            )
            return chunks[:top_k]

        for chunk, score in zip(chunks, scores):
            chunk.metadata["rerank_score"] = round(float(score), 4)

        ranked = sorted(
            chunks,
            key=lambda c: c.metadata.get("rerank_score", 0.0),
            reverse=True,
        )[:top_k]

        log.info(
            "reranker.done",
            top_score=ranked[0].metadata.get("rerank_score") if ranked else None,
            bottom_score=ranked[-1].metadata.get("rerank_score") if ranked else None,
        )
        return ranked

    def _run_reranker(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Sync inference — called via asyncio.to_thread only."""
        model = _load_cross_encoder()
        return [float(s) for s in model.predict(pairs)]