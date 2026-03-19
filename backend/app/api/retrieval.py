import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user_payload, get_user_id_from_payload
from app.core.logging import get_logger
from app.models.audit import QueryLog, Citation, AuditLog
from app.models.document import Chunk
from app.models.user import Workspace
from app.schemas.query import CitationSchema, QueryResponse
from app.schemas.document import ChunkSchema
from app.services.retriever import RetrieverService
from app.services.embedder import get_embedding_service

router = APIRouter()
logger = get_logger(__name__)


# ── POST /api/retrieval/search ────────────────────────────────────────────────

@router.post(
    "/search",
    response_model=list[CitationSchema],
    summary="Raw semantic search — returns top-K chunks without LLM",
)
async def semantic_search(
    workspace_id: uuid.UUID,
    query: str = Query(..., min_length=3, max_length=500),
    top_k: int = Query(default=5, ge=1, le=20),
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    """
    Performs semantic search directly against the vector store.
    Does NOT call the LLM — returns raw chunk citations only.
    Useful for debugging retrieval quality independently of generation.
    """
    user_id = get_user_id_from_payload(payload)

    # Workspace access check
    workspace = await db.get(Workspace, workspace_id)
    if not workspace or workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    retriever = RetrieverService()
    dummy_log_id = uuid.uuid4()  # no persistent QueryLog for raw search

    citations, _ = await retriever.retrieve(
        db=db,
        query=query,
        workspace_id=workspace_id,
        query_log_id=dummy_log_id,
        top_k=top_k,
    )
    return citations


# ── GET /api/retrieval/history ────────────────────────────────────────────────

@router.get(
    "/history",
    summary="Get query history for a workspace",
)
async def get_query_history(
    workspace_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns recent queries and their answers for a workspace.
    Used to populate the query history panel in the UI.
    """
    user_id = get_user_id_from_payload(payload)

    workspace = await db.get(Workspace, workspace_id)
    if not workspace or workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.workspace_id == workspace_id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    return [
        {
            "id": str(log.id),
            "query": log.query_text,
            "answer_preview": (log.answer_text or "")[:200],
            "critic_score": log.critic_score,
            "latency_ms": log.latency_ms,
            "model_used": log.model_used,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


# ── GET /api/retrieval/history/{query_log_id}/provenance ─────────────────────

@router.get(
    "/history/{query_log_id}/provenance",
    summary="Get full provenance for a past query",
)
async def get_provenance(
    query_log_id: uuid.UUID,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the full answer, citations, and audit trail for a past query.
    Used by the ProvenanceViewer component in the frontend.
    """
    user_id = get_user_id_from_payload(payload)

    # Fetch query log
    log = await db.get(QueryLog, query_log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Query log not found.")

    # Verify workspace ownership
    workspace = await db.get(Workspace, log.workspace_id)
    if not workspace or workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    # Fetch citations with chunk content
    citations_result = await db.execute(
        select(Citation).where(Citation.query_log_id == query_log_id)
    )
    citations = citations_result.scalars().all()

    # Fetch audit trail for this query
    audit_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.query_log_id == query_log_id)
        .order_by(AuditLog.created_at.asc())
    )
    audit_logs = audit_result.scalars().all()

    return {
        "query_log_id": str(log.id),
        "query": log.query_text,
        "answer": log.answer_text,
        "critic_score": log.critic_score,
        "latency_ms": log.latency_ms,
        "model_used": log.model_used,
        "created_at": log.created_at.isoformat(),
        "citations": [
            {
                "chunk_id": str(c.chunk_id),
                "similarity": c.similarity,
                "snippet": c.snippet,
            }
            for c in citations
        ],
        "audit_trail": [
            {
                "event_type": a.event_type,
                "payload": a.payload,
                "timestamp": a.created_at.isoformat(),
            }
            for a in audit_logs
        ],
    }


# ── GET /api/retrieval/chunks/{chunk_id} ──────────────────────────────────────

@router.get(
    "/chunks/{chunk_id}",
    response_model=ChunkSchema,
    summary="Fetch a single chunk by ID (for provenance deep-dive)",
)
async def get_chunk(
    chunk_id: uuid.UUID,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    user_id = get_user_id_from_payload(payload)
    chunk = await db.get(Chunk, chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found.")

    # Verify workspace ownership
    workspace = await db.get(Workspace, chunk.workspace_id)
    if not workspace or workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    return ChunkSchema.model_validate(chunk)
