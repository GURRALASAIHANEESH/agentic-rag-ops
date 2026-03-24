# backend/app/services/vector_store.py
import os
import pickle
from typing import Optional
from uuid import UUID

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.document import Chunk

logger = get_logger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

class RetrievedChunk:
    """Plain data object returned by both pgvector and FAISS backends."""

    def __init__(
        self,
        chunk_id: UUID,
        document_id: UUID,
        workspace_id: UUID,
        content: str,
        similarity: float,
        chunk_index: int,
        metadata: dict,
    ):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.workspace_id = workspace_id
        self.content = content
        self.similarity = similarity
        self.chunk_index = chunk_index
        self.metadata = metadata


# ── pgvector backend ──────────────────────────────────────────────────────────

class PgVectorStore:
    """
    Uses PostgreSQL + pgvector for persistent vector search.
    Recommended for production — vectors survive restarts.

    Cosine similarity search via the <=> operator.
    IVFFlat index (created in 001_init.sql) speeds up search
    on large datasets at the cost of slight recall reduction.
    """

    async def search(
        self,
        db: AsyncSession,
        query_embedding: list[float],
        workspace_id: UUID,
        top_k: int | None = None,
        min_similarity: float | None = None,
    ) -> list[RetrievedChunk]:
        """
        Finds the top_k most similar chunks within a workspace.
        Filters by workspace_id for tenant isolation.
        Discards results below min_similarity threshold.

        IMPORTANT: top_k and min_similarity default to None here intentionally.
        Actual values are always resolved from config at call time — never
        hardcoded — so .env changes take effect without restart.
        """
        cfg = get_settings()
        resolved_top_k = top_k if top_k is not None else cfg.RETRIEVAL_TOP_K
        resolved_min_sim = min_similarity if min_similarity is not None else cfg.RETRIEVAL_MIN_SIMILARITY

        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        # 1 - (embedding <=> query) converts cosine distance → similarity score
        sql = text("""
            SELECT
                id,
                document_id,
                workspace_id,
                content,
                chunk_index,
                metadata,
                1 - (embedding <=> :embedding ::vector) AS similarity
            FROM chunks
            WHERE workspace_id = :workspace_id
              AND embedding IS NOT NULL
              AND 1 - (embedding <=> :embedding ::vector) >= :min_sim
            ORDER BY embedding <=> :embedding ::vector
            LIMIT :top_k
        """)

        result = await db.execute(sql, {
            "embedding": embedding_str,
            "workspace_id": str(workspace_id),
            "min_sim": resolved_min_sim,
            "top_k": resolved_top_k,
        })
        rows = result.fetchall()

        chunks = [
            RetrievedChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                workspace_id=row.workspace_id,
                content=row.content,
                similarity=float(row.similarity),
                chunk_index=row.chunk_index,
                metadata=row.metadata or {},
            )
            for row in rows
        ]

        logger.info(
            "pgvector_search_complete",
            workspace=str(workspace_id),
            returned=len(chunks),
            top_k=resolved_top_k,
            min_similarity=resolved_min_sim,
        )
        return chunks

    async def upsert_chunk(self, db: AsyncSession, chunk: Chunk) -> None:
        """
        Inserts or updates a single chunk's embedding in Postgres.
        Called during ingestion after embedding is computed.
        Caller commits via get_db() dependency.
        """
        db.add(chunk)


# ── FAISS fallback backend ────────────────────────────────────────────────────

class FAISSVectorStore:
    """
    In-memory FAISS index as a fallback when pgvector is unavailable.
    WARNING: index is lost on restart unless saved to disk.
    Suitable for local development without Postgres.

    Index is saved to FAISS_INDEX_PATH as two files:
      - faiss_index.bin  : the FAISS index
      - faiss_meta.pkl   : chunk metadata (id, content, workspace_id, etc.)
    """

    def __init__(self):
        import faiss
        self._faiss = faiss
        cfg = get_settings()
        self._dimension = cfg.EMBEDDING_DIMENSION
        self._index_path = cfg.FAISS_INDEX_PATH
        self._index: Optional[object] = None
        self._metadata: list[dict] = []
        self._load_or_create()

    def _load_or_create(self):
        """Loads existing index from disk or creates a new one."""
        bin_path = f"{self._index_path}.bin"
        meta_path = f"{self._index_path}.pkl"

        if os.path.exists(bin_path) and os.path.exists(meta_path):
            self._index = self._faiss.read_index(bin_path)
            with open(meta_path, "rb") as f:
                self._metadata = pickle.load(f)
            logger.info("faiss_index_loaded", vectors=self._index.ntotal)
        else:
            # IndexFlatIP = inner product (cosine on normalized vectors)
            self._index = self._faiss.IndexFlatIP(self._dimension)
            self._metadata = []
            logger.info("faiss_index_created", dimension=self._dimension)

    def save(self):
        """Persists the FAISS index to disk."""
        os.makedirs(os.path.dirname(self._index_path) or ".", exist_ok=True)
        self._faiss.write_index(self._index, f"{self._index_path}.bin")
        with open(f"{self._index_path}.pkl", "wb") as f:
            pickle.dump(self._metadata, f)
        logger.info("faiss_index_saved", vectors=self._index.ntotal)

    def add_chunk(
        self,
        chunk_id: UUID,
        document_id: UUID,
        workspace_id: UUID,
        content: str,
        embedding: list[float],
        chunk_index: int,
        metadata: dict,
    ) -> None:
        """Adds a single chunk vector to the in-memory FAISS index."""
        vec = np.array([embedding], dtype=np.float32)
        self._index.add(vec)
        self._metadata.append({
            "chunk_id": chunk_id,
            "document_id": document_id,
            "workspace_id": workspace_id,
            "content": content,
            "chunk_index": chunk_index,
            "metadata": metadata,
        })

    async def search(
        self,
        db: AsyncSession,  # kept for interface compatibility with PgVectorStore
        query_embedding: list[float],
        workspace_id: UUID,
        top_k: int | None = None,
        min_similarity: float | None = None,
    ) -> list[RetrievedChunk]:
        """
        Searches FAISS index. Filters results by workspace_id post-search
        (FAISS doesn't support filtered search natively).
        """
        if self._index.ntotal == 0:
            return []

        cfg = get_settings()
        resolved_top_k = top_k if top_k is not None else cfg.RETRIEVAL_TOP_K
        resolved_min_sim = min_similarity if min_similarity is not None else cfg.RETRIEVAL_MIN_SIMILARITY

        vec = np.array([query_embedding], dtype=np.float32)
        # Over-fetch to account for workspace_id filtering
        k = min(resolved_top_k * 3, self._index.ntotal)
        similarities, indices = self._index.search(vec, k)

        results = []
        for sim, idx in zip(similarities[0], indices[0]):
            if idx == -1:
                continue
            meta = self._metadata[idx]
            if meta["workspace_id"] != workspace_id:
                continue
            if float(sim) < resolved_min_sim:
                continue
            results.append(RetrievedChunk(
                chunk_id=meta["chunk_id"],
                document_id=meta["document_id"],
                workspace_id=meta["workspace_id"],
                content=meta["content"],
                similarity=float(sim),
                chunk_index=meta["chunk_index"],
                metadata=meta["metadata"],
            ))
            if len(results) >= resolved_top_k:
                break

        logger.info(
            "faiss_search_complete",
            workspace=str(workspace_id),
            returned=len(results),
            min_similarity=resolved_min_sim,
        )
        return results


# ── Factory ───────────────────────────────────────────────────────────────────

def get_vector_store() -> PgVectorStore | FAISSVectorStore:
    """
    Returns the correct vector store backend based on VECTOR_STORE_BACKEND.

    Usage:
        store = get_vector_store()
        chunks = await store.search(db, query_embedding, workspace_id)
    """
    backend = get_settings().VECTOR_STORE_BACKEND
    if backend == "pgvector":
        return PgVectorStore()
    elif backend == "faiss":
        return FAISSVectorStore()
    else:
        raise ValueError(f"Unknown VECTOR_STORE_BACKEND='{backend}'")
