import uuid
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

settings = get_settings()
logger = get_logger(__name__)


class RetrieverService:
    """
    Handles semantic retrieval: embeds the query, searches the vector
    store, enriches results with document filenames, and returns
    CitationSchema objects ready for the response.

    Also writes a 'retrieval' AuditLog entry so every search is traceable.
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
        top_k: int = None,
    ) -> tuple[list[CitationSchema], list[RetrievedChunk]]:
        """
        Main retrieval method.

        Returns:
          - citations: list[CitationSchema] for the API response
          - raw_chunks: list[RetrievedChunk] for the orchestrator (to build prompt)

        Steps:
          1. Embed the query string
          2. Vector search (pgvector or FAISS)
          3. Enrich with document filenames
          4. Build CitationSchema objects with snippet (≤300 chars)
          5. Log retrieval to audit_logs
        """
        top_k = top_k or settings.RETRIEVAL_TOP_K

        # ── 1. Embed query ────────────────────────────────────────────────
        query_embedding = await self._embedder.embed_text(query)

        # ── 2. Vector search with metrics tracking ────────────────────────
        backend_name = settings.VECTOR_STORE_BACKEND
        with track_retrieval(backend=backend_name) as tracker:
            raw_chunks = await self._vector_store.search(
                db=db,
                query_embedding=query_embedding,
                workspace_id=workspace_id,
                top_k=top_k,
                min_similarity=settings.RETRIEVAL_MIN_SIMILARITY,
            )
            tracker.set_chunk_count(len(raw_chunks))

        if not raw_chunks:
            logger.warning(
                "no_chunks_retrieved",
                workspace=str(workspace_id),
                query=query[:80],
            )
            return [], []

        # ── 3. Enrich: fetch filenames for retrieved document IDs ─────────
        doc_ids = list({c.document_id for c in raw_chunks})
        docs_result = await db.execute(
            select(Document.id, Document.filename).where(Document.id.in_(doc_ids))
        )
        doc_map: dict[uuid.UUID, str] = {
            row.id: row.filename for row in docs_result.fetchall()
        }

        # ── 4. Build citation schemas ─────────────────────────────────────
        citations: list[CitationSchema] = []
        for chunk in raw_chunks:
            snippet = self._make_snippet(chunk.content)
            citations.append(CitationSchema(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=doc_map.get(chunk.document_id, "Unknown"),
                chunk_index=chunk.chunk_index,
                snippet=snippet,
                similarity=round(chunk.similarity, 4),
            ))

        # ── 5. Audit log ──────────────────────────────────────────────────
        audit = AuditLog(
            query_log_id=query_log_id,
            event_type="retrieval",
            payload={
                "query": query[:200],
                "top_k": top_k,
                "chunks_found": len(raw_chunks),
                "backend": backend_name,
                "similarities": [round(c.similarity, 4) for c in raw_chunks],
            },
        )
        db.add(audit)
        # Caller commits via get_db() dependency

        logger.info(
            "retrieval_complete",
            query_log_id=str(query_log_id),
            chunks=len(raw_chunks),
            top_similarity=raw_chunks[0].similarity if raw_chunks else 0,
        )
        return citations, raw_chunks

    def build_context_block(self, raw_chunks: list[RetrievedChunk]) -> str:
        """
        Formats retrieved chunks into a numbered context block
        for injection into the LLM prompt.

        Format:
            [SOURCE 1] (similarity: 0.87)
            <chunk text>

            [SOURCE 2] (similarity: 0.81)
            <chunk text>
        """
        if not raw_chunks:
            return "No relevant context found."

        lines = []
        for i, chunk in enumerate(raw_chunks, start=1):
            lines.append(
                f"[SOURCE {i}] (similarity: {chunk.similarity:.2f})\n{chunk.content}"
            )
        return "\n\n".join(lines)

    def _make_snippet(self, content: str, max_chars: int = 300) -> str:
        """
        Returns a clean ≤300 char excerpt, truncating at the last
        complete word boundary to avoid cutting mid-word.
        """
        content = content.replace("\n", " ").strip()
        if len(content) <= max_chars:
            return content
        truncated = content[:max_chars]
        last_space = truncated.rfind(" ")
        return truncated[:last_space] + "…" if last_space > 0 else truncated + "…"
