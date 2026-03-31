# app/workers/ingestion_worker.py

from __future__ import annotations

import asyncio
import uuid

import structlog
from celery import Celery
from celery.signals import worker_process_init
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Celery application
# ─────────────────────────────────────────────────────────────────────────────

def _make_celery_app() -> Celery:
    cfg = get_settings()
    app = Celery(
        "ragops",
        broker=cfg.REDIS_URL,
        backend=cfg.REDIS_URL,
    )
    app.conf.update(
        # Serialization
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],

        # Routing — all ingestion tasks go to the dedicated queue
        task_default_queue="ingestion",
        task_routes={
            "app.workers.ingestion_worker.run_ingestion_task": {
                "queue": "ingestion"
            }
        },

        # Reliability
        task_acks_late=True,              # ack only after task completes, not on receipt
        task_reject_on_worker_lost=True,  # re-queue if worker dies mid-task
        worker_prefetch_multiplier=1,     # one task at a time per worker slot

        # Result expiry — status available for 24h after completion
        result_expires=86400,

        # Timezone
        timezone="UTC",
        enable_utc=True,
    )
    return app


celery_app: Celery = _make_celery_app()


# ─────────────────────────────────────────────────────────────────────────────
# Worker lifecycle — create a fresh async DB session pool per worker process
# ─────────────────────────────────────────────────────────────────────────────

@worker_process_init.connect
def init_worker_db(**kwargs: object) -> None:
    """
    Called once when each Celery worker process starts.
    Ensures the async engine is initialised in the worker process,
    not inherited from the parent (fork-safety).
    """
    from app.core.database import init_db_engine
    init_db_engine()
    logger.info("celery_worker.db_engine_initialised")


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion task
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.workers.ingestion_worker.run_ingestion_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,      # seconds between retries
    soft_time_limit=300,         # 5 min soft limit — raises SoftTimeLimitExceeded
    time_hard_limit=360,         # 6 min hard kill
    acks_late=True,
)
def run_ingestion_task(
    self,                        # bound task — gives access to self.retry()
    document_id: str,
    file_bytes_hex: str,         # bytes serialised as hex — JSON-safe
    mime_type: str,
    user_id: str,
    doc_namespace: str | None = None,      # default None for backward compat with queued tasks
) -> dict[str, object]:
    """
    Celery task: runs the full IngestionService pipeline in a worker process.

    Args:
        document_id:    UUID string of the Document record
        file_bytes_hex: Raw file bytes encoded as hex string (JSON-serialisable)
        mime_type:      MIME type string ("application/pdf" or "text/plain")
        user_id:        UUID string of the uploading user

    Returns:
        dict with chunks_created and status — stored in Celery result backend.

    Retry policy:
        Retries up to 3 times on transient errors (DB timeout, embedding API).
        Permanent errors (bad file, document not found) are NOT retried.
    """
    log = logger.bind(
        document_id=document_id,
        mime_type=mime_type,
        task_id=self.request.id,
        doc_namespace=doc_namespace,           # traceable in Grafana/structlog
    )
    log.info("ingestion_task.received")

    # Deserialise file bytes from hex
    file_bytes: bytes = bytes.fromhex(file_bytes_hex)

    try:
        result = asyncio.run(
            _async_ingest(
                document_id=uuid.UUID(document_id),
                file_bytes=file_bytes,
                mime_type=mime_type,
                user_id=uuid.UUID(user_id),
                doc_namespace=doc_namespace,
            )
        )
        log.info("ingestion_task.success", chunks_created=result["chunks_created"])
        return result

    except ValueError as exc:
        # Permanent failure — bad file, document not found, zero chunks
        # Do NOT retry these — mark failed immediately
        log.error("ingestion_task.permanent_failure", error=str(exc))
        raise

    except Exception as exc:
        # Transient failure — DB timeout, network hiccup, embedding API down
        log.warning(
            "ingestion_task.transient_failure",
            error=str(exc),
            retry_count=self.request.retries,
        )
        raise self.retry(exc=exc)


async def _async_ingest(
    document_id: uuid.UUID,
    file_bytes: bytes,
    mime_type: str,
    user_id: uuid.UUID,
    doc_namespace: str | None = None,
) -> dict[str, object]:
    """
    Async wrapper that runs inside asyncio.run() from the sync Celery task.
    Sequence:
        1. IngestionService  — parse → chunk → embed → persist chunks
        2. EvaluatorService  — synthetic QA → score → persist eval_results
    Step 2 failure is fully swallowed — ingestion result is never affected.
    """
    from app.core.database import get_async_session
    from app.models.document import Document
    from app.services.evaluator import EvaluatorService
    from app.services.ingestion import IngestionService

    service   = IngestionService()
    evaluator = EvaluatorService()

    async with get_async_session() as db:

        # ── Step 1: Ingestion ─────────────────────────────────────────────
        chunks_created: int = await service.ingest_document(
            db=db,
            document_id=document_id,
            file_bytes=file_bytes,
            mime_type=mime_type,
            user_id=user_id,
            doc_namespace=doc_namespace,
        )

        # ── Step 2: RAGAS evaluation ──────────────────────────────────────
        # Reload doc inside the same session — workspace_id is needed by evaluator.
        # doc is guaranteed status='ready' here because ingest_document() committed it.
        doc = await db.get(Document, document_id)
        if doc is not None:
            logger.info(
                "evaluator.trigger",
                document_id=str(document_id),
                workspace_id=str(doc.workspace_id),
            )
            await evaluator.evaluate_document(
                db=db,
                document_id=document_id,
                workspace_id=doc.workspace_id,
            )
        else:
            logger.warning(
                "evaluator.skipped_doc_not_found",
                document_id=str(document_id),
            )

    return {
        "document_id":    str(document_id),
        "chunks_created": chunks_created,
        "status":         "ready",
    }
