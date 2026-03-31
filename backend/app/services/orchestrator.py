# backend/app/services/orchestrator.py
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.audit import AuditLog, QueryLog, Citation
from app.models.user import Workspace
from app.schemas.query import (
    QueryRequest, QueryResponse, StreamChunk, CitationSchema, CriticReport
)
from app.services.llm_client import LLMClient, get_llm_client
from app.services.retriever import RetrieverService
from app.services.router_agent import RouterAgent, ROUTE_CLARIFY, ROUTE_WEB
from app.services.critic_agent import CriticAgent
from app.services.web_search import WebSearchService
from app.metrics.prometheus import (
    track_llm_call, LLM_TOKEN_COUNT, ACTIVE_QUERIES
)

logger = get_logger(__name__)

WEB_SEARCH_SYSTEM_PROMPT = """You are a precise research assistant answering
questions from live web search results.

RULES:
1. Answer using ONLY the provided web search results — never fabricate facts.
2. Cite every fact inline using [SOURCE N] notation immediately after the claim.
3. Each source is a web page — treat the snippet as the available context.
4. Be concise and direct. No filler phrases.
5. If results are insufficient, say so clearly.
"""

# ── RAG system prompt ─────────────────────────────────────────────────────────
RAG_SYSTEM_PROMPT = """You are a precise, helpful research assistant answering
questions from a personal knowledge base of documents.

RULES:
1. Answer using ONLY the provided source context — never fabricate facts.
2. Cite every fact inline using [SOURCE N] notation immediately after the claim.
   Example: "Sai Haneesh studied at Malla Reddy Engineering College [SOURCE 1]."
3. Sources may be prefixed with a section label like "Education:", "PROJECTS:",
   "SKILLS:" — treat the content after the colon as the actual information.
4. Answer directly and confidently when the answer exists in ANY source,
   even if the source chunk is partial or the similarity score is low.
5. Only say "I could not find this information in the provided sources." when
   the answer is genuinely absent from ALL sources — not when it is present
   but phrased differently.
6. For simple factual questions (names, dates, places), give a one-sentence
   direct answer first, then cite. Do not over-qualify.
7. Be concise. No filler phrases like "Based on the context provided..."
"""


class Orchestrator:
    """
    Stateful agent workflow controller.

    Pipeline (in order):
      Step 1 — Router    : Decide if query is answerable or needs clarification
      Step 2 — Retrieval : Semantic search → top-K chunks
      Step 3 — Prompt    : Build context-injected prompt with [SOURCE N] labels
      Step 4 — LLM       : Stream tokens to client in real-time
      Step 5 — Critic    : Verify claims against sources, build confidence map
      Step 6 — Persist   : Save QueryLog + Citations + AuditLogs to DB

    Every step is logged to audit_logs so the full decision trail is queryable.
    """

    def __init__(self, db: AsyncSession):
        self._db = db
        self._llm: LLMClient = get_llm_client()
        self._retriever = RetrieverService()
        self._router = RouterAgent(self._llm)
        self._critic = CriticAgent(self._llm)
        self._web_search = WebSearchService()

    async def run_streaming(
        self,
        request: QueryRequest,
        user_id: uuid.UUID,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming RAG pipeline with Phase 3D parallel rerank.

        Timeline:
            t=0   retrieve top-20 chunks (vector search)
            t=0   fire reranker as background task  ← Phase 3D
            t=0   build prompt from raw chunks (stream starts immediately)
            t=?   LLM streams tokens to client
            t=?   reranker task completes in parallel (typically faster than LLM)
            t=end await reranker result, use rerank-ordered citations
            t=end yield citations (rerank-ordered) + critic + done
        """
        start_time = time.monotonic()
        ACTIVE_QUERIES.inc()

        # ── Validate workspace ownership ──────────────────────────────────
        workspace = await self._db.get(Workspace, request.workspace_id)
        if not workspace or workspace.owner_id != user_id:
            yield self._sse_event("error", "Workspace not found or access denied.")
            ACTIVE_QUERIES.dec()
            return

        # ── Create QueryLog early (needed for FK in audit logs) ───────────
        query_log = QueryLog(
            id=uuid.uuid4(),
            user_id=user_id,
            workspace_id=request.workspace_id,
            query_text=request.query,
            model_used=self._llm.model_name,
        )
        self._db.add(query_log)
        await self._db.flush()  # get ID without full commit

        try:
            # ── Step 1: Router ────────────────────────────────────────────
            route_result = await self._router.route(
                db=self._db,
                query=request.query,
                query_log_id=query_log.id,
                user_id=user_id,
            )

            if route_result["route"] == ROUTE_CLARIFY:
                suggestion = route_result.get("suggestion", "Please rephrase your query.")
                yield self._sse_event("clarify", suggestion)
                await self._db.commit()
                ACTIVE_QUERIES.dec()
                return

            # ── Step 2: Retrieve vector search candidates (top-20) ────────
            citations, raw_chunks = await self._retriever.retrieve(
                db=self._db,
                query=request.query,
                workspace_id=request.workspace_id,
                query_log_id=query_log.id,
                document_ids=request.document_ids,
                section=request.section,
                top_k=20,
            )

            # ── Step 2B: Web search fallback ──────────────────────────────
            # Triggered when: router explicitly chose "web" OR vector search
            # returned no results (implicit fallback for knowledge-gap queries).
            # Web results are normalized to WebResult which duck-types ChunkResult,
            # so every downstream step (reranker, citations, critic) is unchanged.
            use_web = (
                route_result["route"] == ROUTE_WEB
                or (not raw_chunks)
            )

            if use_web:
                logger.info(
                    "orchestrator.web_search_triggered",
                    reason="explicit_route" if route_result["route"] == ROUTE_WEB else "vector_empty",
                    query_log_id=str(query_log.id),
                )
                web_results = await self._web_search.search(query=request.query)

                if web_results:
                    # Normalize: WebResult duck-types ChunkResult — no conversion needed
                    raw_chunks = web_results          # type: ignore[assignment]
                    citations = self._build_citations_from_chunks(web_results)

                    # Audit: record web search was used
                    self._db.add(AuditLog(
                        query_log_id=query_log.id,
                        user_id=user_id,
                        event_type="web_search",
                        payload={
                            "query": request.query[:200],
                            "results_count": len(web_results),
                            "trigger": "explicit_route" if route_result["route"] == ROUTE_WEB else "vector_fallback",
                            "urls": [r.metadata.get("filename", "") for r in web_results],
                        },
                    ))
                else:
                    # Web search also failed — surface honest message
                    no_context_msg = (
                        "I could not find relevant information in your documents "
                        "or via web search for this query."
                    )
                    yield self._sse_event("token", no_context_msg)
                    yield self._sse_event("citations", [])
                    yield self._sse_event("done", None, query_log_id=str(query_log.id))
                    await self._db.commit()
                    ACTIVE_QUERIES.dec()
                    return

            # ── Step 3: Phase 3D — fire reranker as background task ───────
            # Reranker is CPU-bound (asyncio.to_thread inside rerank()).
            # It starts NOW and runs concurrently while LLM streams tokens.
            # We await it only after the stream completes.
            # Web results are already rank-ordered by DDG relevance score.
            # Reranker expects ChunkResult objects with embeddings — WebResult
            # has no embedding, so we skip reranking for web results entirely.
            if use_web:
                rerank_task = None
            else:
                rerank_task: asyncio.Task = asyncio.create_task(
                    self._retriever.rerank(
                        query=request.query,
                        chunks=raw_chunks,
                    ),
                    name=f"rerank-{query_log.id}",
                )
            logger.info(
                "streaming.rerank_task_started",
                candidates=len(raw_chunks),
                query_log_id=str(query_log.id),
            )

            # ── Step 4: Build prompt and stream LLM tokens ────────────────
            # Intentional: don't wait for reranker here.
            # top-5 raw (vector-order) chunks used for prompt — LLM starts immediately.
            context_block = self._retriever.build_context_block(raw_chunks[:5])
            prompt = self._build_rag_prompt(request.query, context_block)

            full_answer_parts: list[str] = []
            with track_llm_call(
                provider=self._llm.provider_name,
                model=self._llm.model_name,
            ):
                system_prompt = (
                    WEB_SEARCH_SYSTEM_PROMPT if use_web else RAG_SYSTEM_PROMPT
                )

                async for token in self._llm.stream(
                    prompt=prompt,
                    system=system_prompt,
                ):
                    full_answer_parts.append(token)
                    yield self._sse_event("token", token)

            full_answer = "".join(full_answer_parts)

            estimated_tokens = len(full_answer) // 4
            LLM_TOKEN_COUNT.labels(
                provider=self._llm.provider_name,
                model=self._llm.model_name,
                direction="completion",
            ).inc(estimated_tokens)

            # ── Step 5: Await reranker — should already be done by now ────
            # In the common case (LLM latency > reranker latency), this
            # await returns instantly — the task finished during streaming.
            if use_web or rerank_task is None:
                # Web results: already ordered by DDG relevance, no reranking needed
                final_citations = citations
                logger.info("streaming.rerank_skipped", reason="web_results")
            else:
                try:
                    reranked_chunks = await asyncio.wait_for(
                        rerank_task,
                        timeout=10.0,
                    )
                    logger.info(
                        "streaming.rerank_complete",
                        reranked_count=len(reranked_chunks),
                        top_score=(
                            reranked_chunks[0].metadata.get("rerank_score")
                            if reranked_chunks else None
                        ),
                    )
                    final_citations = self._build_citations_from_chunks(reranked_chunks)
    
                except asyncio.TimeoutError:
                    logger.warning("streaming.rerank_timeout", fallback="original_vector_order")
                    rerank_task.cancel()
                    final_citations = citations
    
                except Exception as exc:
                    logger.error("streaming.rerank_failed", error=str(exc), fallback="original_vector_order")
                    rerank_task.cancel()
                    final_citations = citations

            # ── Send citations (rerank-ordered) to client ─────────────────
            citations_payload = [c.model_dump(mode="json") for c in final_citations]
            yield self._sse_event("citations", citations_payload)

            # ── Step 6: Critic verification ───────────────────────────────
            critic_report = await self._critic.verify(
                db=self._db,
                answer=full_answer,
                raw_chunks=raw_chunks,
                query_log_id=query_log.id,
                user_id=user_id,
            )
            yield self._sse_event("critic", critic_report.model_dump(mode="json"))

            # ── Step 7: Persist final state ───────────────────────────────
            latency_ms = int((time.monotonic() - start_time) * 1000)
            query_log.answer_text  = full_answer
            query_log.latency_ms   = latency_ms
            query_log.critic_score = critic_report.overall_score

            for citation in final_citations:
                # Web citations have no DB chunk record — skip FK insert to avoid
                # IntegrityError. Web sources are recorded in the web_search audit
                # log entry instead. Only persist citations backed by real chunks.
                if citation.filename.startswith("http"):
                    continue
                self._db.add(Citation(
                    query_log_id=query_log.id,
                    chunk_id=citation.chunk_id,
                    similarity=citation.similarity,
                    snippet=citation.snippet,
                ))

            self._db.add(AuditLog(
                query_log_id=query_log.id,
                user_id=user_id,
                event_type="llm_call",
                payload={
                    "model":            self._llm.model_name,
                    "provider":         self._llm.provider_name,
                    "prompt_chars":     len(prompt),
                    "answer_chars":     len(full_answer),
                    "latency_ms":       latency_ms,
                    "estimated_tokens": estimated_tokens,
                },
            ))

            await self._db.commit()
            yield self._sse_event("done", None, query_log_id=str(query_log.id))

            logger.info(
                "orchestrator_complete",
                query_log_id=str(query_log.id),
                latency_ms=latency_ms,
                critic_score=critic_report.overall_score,
                chunks_used=len(raw_chunks),
            )

        except Exception as e:
            await self._db.rollback()
            logger.error(
                "orchestrator_error",
                error=str(e),
                query_log_id=str(query_log.id),
            )
            yield self._sse_event("error", f"Pipeline error: {str(e)}")
        finally:
            ACTIVE_QUERIES.dec()


    async def run_sync(
        self,
        request: QueryRequest,
        user_id: uuid.UUID,
    ) -> QueryResponse:
        """
        Non-streaming version — collects all SSE events and returns
        a single QueryResponse. Used for testing and non-streaming clients.
        """
        tokens = []
        citations = []
        critic = None
        query_log_id = None

        async for event in self.run_streaming(request, user_id):
            if not event.startswith("data:"):
                continue
            raw = event[5:].strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue

            etype = parsed.get("type")
            if etype == "token":
                tokens.append(parsed.get("data", ""))
            elif etype == "citations":
                citations = parsed.get("data", [])
            elif etype == "critic":
                critic = parsed.get("data")
            elif etype == "done":
                query_log_id = parsed.get("query_log_id")

        return QueryResponse(
            query_log_id=uuid.UUID(query_log_id) if query_log_id else uuid.uuid4(),
            query=request.query,
            answer="".join(tokens),
            model_used=self._llm.model_name,
            latency_ms=0,
            citations=[CitationSchema(**c) for c in citations],
            critic=CriticReport(**critic) if critic else CriticReport(
                overall_score=0.0,
                verified_count=0,
                unverified_count=0,
                partial_count=0,
                claims=[],
            ),
            created_at=datetime.now(timezone.utc),
        )

    # ── Private helpers ─────────────────────────────────────────────────────

    def _build_citations_from_chunks(self, chunks: list) -> list:
        """
        Rebuilds CitationSchema list from reranked chunks.
        Filename is already in chunk.metadata['filename'] — no extra DB call needed.
        Uses rerank_score from metadata if present, falls back to vector similarity.
        """
        from app.schemas.query import CitationSchema
        return [
            CitationSchema(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=chunk.metadata.get("filename", "Unknown"),
                chunk_index=chunk.chunk_index,
                snippet=chunk.content[:300],
                similarity=round(
                    chunk.metadata.get("rerank_score", chunk.similarity), 4
                ),
            )
            for chunk in chunks
        ]

    def _build_rag_prompt(self, query: str, context_block: str) -> str:
        """
        Builds the RAG prompt with context injection.

        Structure:
          - CONTEXT block with [SOURCE N] labels
          - USER QUESTION
          - Explicit instruction to answer directly from sources
        """
        return (
            f"CONTEXT FROM KNOWLEDGE BASE:\n"
            f"{context_block}\n\n"
            f"USER QUESTION: {query}\n\n"
            f"Instructions: Answer the question directly using the context above. "
            f"If the answer appears in any source (even partially), state it confidently "
            f"and cite with [SOURCE N]. For simple facts, answer in one sentence."
        )

    def _sse_event(
        self,
        event_type: str,
        data,
        query_log_id: str = None,
    ) -> str:
        """
        Formats a Server-Sent Event string.
        Double newline is required by the SSE spec.
        Format: "data: {json}\n\n"
        """
        payload = {"type": event_type, "data": data}
        if query_log_id:
            payload["query_log_id"] = query_log_id
        return f"data: {json.dumps(payload)}\n\n"
