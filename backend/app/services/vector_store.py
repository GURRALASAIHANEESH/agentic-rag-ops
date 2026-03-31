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


class PgVectorStore:
    """
    PostgreSQL + pgvector persistent vector search backend.

    Supports optional filters:
      - document_ids : restrict search to specific document UUIDs
      - section      : restrict search to a specific section name
                       (e.g. "Projects", "Experience", "ABSTRACT")

    These filters are pushed into the SQL WHERE clause so Postgres
    does the filtering — no wasted vector comparisons.
    """

    async def search(
        self,
        db: AsyncSession,
        query_embedding: list[float],
        workspace_id: UUID,
        top_k: int | None = None,
        min_similarity: float | None = None,
        document_ids: list[UUID] | None = None,   # scope to specific docs
        section: str | None = None,               # scope to specific section
        namespace: str | None = None,             # Phase 2C: scope to doc_namespace
    ) -> list[RetrievedChunk]:
        cfg = get_settings()
        resolved_top_k  = top_k         if top_k         is not None else cfg.RETRIEVAL_TOP_K
        resolved_min_sim = min_similarity if min_similarity is not None else cfg.RETRIEVAL_MIN_SIMILARITY

        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

        # ── Build dynamic WHERE clause ────────────────────────────────────
        # Base conditions always present
        where_clauses = [
            "workspace_id = :workspace_id",
            "embedding IS NOT NULL",
            "1 - (embedding <=> :embedding ::vector) >= :min_sim",
        ]
        params: dict = {
            "embedding":    embedding_str,
            "workspace_id": str(workspace_id),
            "min_sim":      resolved_min_sim,
            "top_k":        resolved_top_k,
        }

        # Optional: filter to specific document IDs
        # Converts list of UUIDs to a Postgres ANY(:doc_ids) expression
        if document_ids:
            where_clauses.append("document_id = ANY(:doc_ids)")
            params["doc_ids"] = [str(d) for d in document_ids]

        # Optional: filter to a specific section (case-insensitive)
        if section:
            where_clauses.append("LOWER(metadata->>'section') = LOWER(:section)")
            params["section"] = section

        # Optional: filter to a specific doc_namespace (Phase 2C)
        if namespace:
            where_clauses.append("metadata->>'doc_namespace' = :namespace")
            params["namespace"] = namespace

        where_sql = " AND ".join(where_clauses)

        sql = text(f"""
            SELECT
                id,
                document_id,
                workspace_id,
                content,
                chunk_index,
                metadata,
                1 - (embedding <=> :embedding ::vector) AS similarity
            FROM chunks
            WHERE {where_sql}
            ORDER BY embedding <=> :embedding ::vector
            LIMIT :top_k
        """)

        result = await db.execute(sql, params)
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
            document_filter=len(document_ids) if document_ids else None,
            section_filter=section,
            namespace_filter=namespace,
        )
        return chunks

    async def upsert_chunk(self, db: AsyncSession, chunk: Chunk) -> None:
        db.add(chunk)


class FAISSVectorStore:
    """
    In-memory FAISS fallback. Supports document_ids and section filters
    via post-search filtering (FAISS has no native predicate pushdown).
    """

    def __init__(self):
        import faiss
        self._faiss = faiss
        cfg = get_settings()
        self._dimension  = cfg.EMBEDDING_DIMENSION
        self._index_path = cfg.FAISS_INDEX_PATH
        self._index: Optional[object] = None
        self._metadata: list[dict] = []
        self._load_or_create()

    def _load_or_create(self):
        bin_path  = f"{self._index_path}.bin"
        meta_path = f"{self._index_path}.pkl"
        if os.path.exists(bin_path) and os.path.exists(meta_path):
            self._index = self._faiss.read_index(bin_path)
            with open(meta_path, "rb") as f:
                self._metadata = pickle.load(f)
            logger.info("faiss_index_loaded", vectors=self._index.ntotal)
        else:
            self._index = self._faiss.IndexFlatIP(self._dimension)
            self._metadata = []
            logger.info("faiss_index_created", dimension=self._dimension)

    def save(self):
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
        vec = np.array([embedding], dtype=np.float32)
        self._index.add(vec)
        self._metadata.append({
            "chunk_id":     chunk_id,
            "document_id":  document_id,
            "workspace_id": workspace_id,
            "content":      content,
            "chunk_index":  chunk_index,
            "metadata":     metadata,
        })

    async def search(
        self,
        db: AsyncSession,
        query_embedding: list[float],
        workspace_id: UUID,
        top_k: int | None = None,
        min_similarity: float | None = None,
        document_ids: list[UUID] | None = None,   # scope to specific docs
        section: str | None = None,               # scope to specific section
        namespace: str | None = None,             # Phase 2C: scope to doc_namespace
    ) -> list[RetrievedChunk]:
        if self._index.ntotal == 0:
            return []

        cfg = get_settings()
        resolved_top_k   = top_k         if top_k         is not None else cfg.RETRIEVAL_TOP_K
        resolved_min_sim = min_similarity if min_similarity is not None else cfg.RETRIEVAL_MIN_SIMILARITY

        # Build filter sets for post-search filtering
        doc_id_set = {str(d) for d in document_ids} if document_ids else None
        section_lower = section.lower() if section else None
        namespace_val = namespace if namespace else None

        vec = np.array([query_embedding], dtype=np.float32)
        k = min(resolved_top_k * 5, self._index.ntotal)  # over-fetch for filters
        similarities, indices = self._index.search(vec, k)

        results = []
        for sim, idx in zip(similarities[0], indices[0]):
            if idx == -1:
                continue
            meta = self._metadata[idx]

            # Workspace isolation
            if meta["workspace_id"] != workspace_id:
                continue
            # Document filter
            if doc_id_set and str(meta["document_id"]) not in doc_id_set:
                continue
            # Section filter
            if section_lower:
                chunk_section = (meta.get("metadata") or {}).get("section", "").lower()
                if chunk_section != section_lower:
                    continue
            # Namespace filter (Phase 2C)
            if namespace_val:
                chunk_ns = (meta.get("metadata") or {}).get("doc_namespace", "")
                if chunk_ns != namespace_val:
                    continue
            # Similarity threshold
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


def get_vector_store() -> PgVectorStore | FAISSVectorStore:
    backend = get_settings().VECTOR_STORE_BACKEND
    if backend == "pgvector":
        return PgVectorStore()
    elif backend == "faiss":
        return FAISSVectorStore()
    else:
        raise ValueError(f"Unknown VECTOR_STORE_BACKEND='{backend}'")
