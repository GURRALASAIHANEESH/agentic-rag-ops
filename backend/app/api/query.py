import uuid
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.core.security import get_current_user_payload, get_user_id_from_payload
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.query import QueryRequest, QueryResponse
from app.services.orchestrator import Orchestrator

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)


# ── POST /api/query ───────────────────────────────────────────────────────────

@router.post(
    "/",
    summary="Submit a query and receive a streamed RAG response",
    response_description="Server-Sent Events stream of tokens + citations + critic",
)
@limiter.limit(
    f"{settings.RATE_LIMIT_REQUESTS}/{settings.RATE_LIMIT_WINDOW_SECONDS}seconds"
)
async def query(
    request: Request,                   # required by slowapi rate limiter
    body: QueryRequest,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    """
    Main RAG query endpoint.

    Flow:
      1. Validates auth + workspace access
      2. Runs the full Orchestrator pipeline (Router → Retrieval → LLM → Critic)
      3. Returns a Server-Sent Events (SSE) stream if body.stream=True
      4. Returns a single JSON response if body.stream=False

    SSE event types (in order):
      - token     : partial LLM response token
      - clarify   : router decided query needs rephrasing (includes suggestion)
      - citations : list of source chunks with similarity scores
      - critic    : per-claim verification report
      - done      : stream complete, includes query_log_id
      - error     : pipeline error

    Example curl (streaming):
      curl -X POST http://localhost:8000/api/query \\
        -H "Authorization: Bearer <token>" \\
        -H "Content-Type: application/json" \\
        -d '{"query": "What is RAG?", "workspace_id": "<uuid>", "stream": true}'
    """
    user_id = get_user_id_from_payload(payload)

    logger.info(
        "query_received",
        user_id=str(user_id),
        workspace=str(body.workspace_id),
        query=body.query[:80],
        stream=body.stream,
    )

    orchestrator = Orchestrator(db=db)

    # ── Streaming response ────────────────────────────────────────────────
    if body.stream:
        return StreamingResponse(
            _event_stream(orchestrator, body, user_id),
            media_type="text/event-stream",
            headers={
                # Prevent proxies/nginx from buffering the stream
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # ── Non-streaming response ────────────────────────────────────────────
    response = await orchestrator.run_sync(request=body, user_id=user_id)
    return response


async def _event_stream(
    orchestrator: Orchestrator,
    body: QueryRequest,
    user_id: uuid.UUID,
) -> AsyncGenerator[bytes, None]:
    """
    Wraps orchestrator.run_streaming() to yield raw bytes for StreamingResponse.
    Each SSE event is encoded as UTF-8 bytes.

    Also sends a heartbeat comment every 15s to keep the connection alive
    through proxies that close idle connections.
    """
    import asyncio

    try:
        async for event in orchestrator.run_streaming(
            request=body, user_id=user_id
        ):
            yield event.encode("utf-8")
    except asyncio.CancelledError:
        # Client disconnected mid-stream — clean exit, not an error
        logger.info("stream_cancelled", user_id=str(user_id))
    except Exception as e:
        logger.error("stream_error", error=str(e), user_id=str(user_id))
        error_event = f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
        yield error_event.encode("utf-8")


# ── POST /api/query/sync ──────────────────────────────────────────────────────

@router.post(
    "/sync",
    response_model=QueryResponse,
    summary="Submit a query and receive a single JSON response (non-streaming)",
)
@limiter.limit(
    f"{settings.RATE_LIMIT_REQUESTS}/{settings.RATE_LIMIT_WINDOW_SECONDS}seconds"
)
async def query_sync(
    request: Request,
    body: QueryRequest,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    """
    Convenience endpoint for non-streaming clients (e.g., curl tests, CI).
    Runs the full pipeline and returns the complete QueryResponse in one shot.

    Example curl:
      curl -X POST http://localhost:8000/api/query/sync \\
        -H "Authorization: Bearer <token>" \\
        -H "Content-Type: application/json" \\
        -d '{"query": "What is attention?", "workspace_id": "<uuid>", "stream": false}'
    """
    user_id = get_user_id_from_payload(payload)
    orchestrator = Orchestrator(db=db)

    # Force stream=False so orchestrator uses run_sync()
    body.stream = False
    return await orchestrator.run_sync(request=body, user_id=user_id)
