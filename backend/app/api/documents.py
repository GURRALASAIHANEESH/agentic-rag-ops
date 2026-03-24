import uuid
import os
from pathlib import Path

from fastapi import (
    APIRouter, Depends, HTTPException,
    UploadFile, File, BackgroundTasks, status
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone

from app.core.database import get_db
from app.core.security import get_current_user_payload, get_user_id_from_payload
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document
from app.models.user import Workspace
from app.schemas.document import (
    DocumentUploadResponse, DocumentListResponse,
    DocumentListItem, IngestionStatusResponse,
)
from app.services.ingestion import IngestionService

router = APIRouter()
logger = get_logger(__name__)

# Allowed MIME types parsed from config string
ALLOWED_TYPES = set(get_settings().ALLOWED_MIME_TYPES.split(","))
MAX_BYTES = get_settings().MAX_UPLOAD_SIZE_MB * 1024 * 1024


# ── POST /api/documents/upload ────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF or TXT document for ingestion",
)
async def upload_document(
    workspace_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    user_id = get_user_id_from_payload(payload)

    # ── Validate workspace ownership (RBAC) ───────────────────────────────
    workspace = await db.get(Workspace, workspace_id)
    if not workspace or workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Workspace not found or access denied.")

    # ── Validate file type ────────────────────────────────────────────────
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{content_type}' not allowed. Accepted: {ALLOWED_TYPES}",
        )

    # ── Read and validate file size ───────────────────────────────────────
    file_bytes = await file.read()
    if len(file_bytes) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {get_settings().MAX_UPLOAD_SIZE_MB}MB limit.",
        )

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # ── Save file to storage ──────────────────────────────────────────────
    upload_dir = Path(get_settings().UPLOAD_DIR) / str(workspace_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = _sanitize_filename(file.filename or "upload.pdf")
    file_path = upload_dir / f"{uuid.uuid4()}_{safe_filename}"
    file_path.write_bytes(file_bytes)

    # ── Create Document record ────────────────────────────────────────────
    doc = Document(
        workspace_id=workspace_id,
        filename=safe_filename,
        file_size_bytes=len(file_bytes),
        mime_type=content_type,
        storage_path=str(file_path),
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(
            days=get_settings().DOCUMENT_RETENTION_DAYS
        ) if get_settings().DOCUMENT_RETENTION_DAYS > 0 else None,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # ── Kick off ingestion in background ─────────────────────────────────
    # BackgroundTasks runs after response is sent — user gets instant feedback
    background_tasks.add_task(
        _run_ingestion,
        document_id=doc.id,
        file_bytes=file_bytes,
        mime_type=content_type,
        user_id=user_id,
    )

    logger.info(
        "document_uploaded",
        doc_id=str(doc.id),
        filename=safe_filename,
        size_bytes=len(file_bytes),
    )
    return DocumentUploadResponse.model_validate(doc)


# ── GET /api/documents ────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List all documents in a workspace",
)
async def list_documents(
    workspace_id: uuid.UUID,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    user_id = get_user_id_from_payload(payload)

    workspace = await db.get(Workspace, workspace_id)
    if not workspace or workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    result = await db.execute(
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()

    return DocumentListResponse(
        documents=[DocumentListItem.model_validate(d) for d in docs],
        total=len(docs),
    )


# ── GET /api/documents/{document_id}/status ───────────────────────────────────

@router.get(
    "/{document_id}/status",
    response_model=IngestionStatusResponse,
    summary="Get ingestion status for a document",
)
async def get_document_status(
    document_id: uuid.UUID,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    user_id = get_user_id_from_payload(payload)
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Verify workspace ownership
    workspace = await db.get(Workspace, doc.workspace_id)
    if not workspace or workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    # Count chunks created
    from sqlalchemy import func
    from app.models.document import Chunk
    count_result = await db.execute(
        select(func.count()).where(Chunk.document_id == document_id)
    )
    chunk_count = count_result.scalar()

    return IngestionStatusResponse(
        document_id=doc.id,
        status=doc.status,
        chunks_created=chunk_count,
        message=_status_message(doc.status),
    )


# ── DELETE /api/documents/{document_id} ───────────────────────────────────────

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and all its chunks",
)
async def delete_document(
    document_id: uuid.UUID,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Deletes a document and ALL its chunks.

    Cascade strategy (defence in depth — two layers):
      Layer 1 — ORM: cascade="all, delete-orphan" on Document.chunks
                with lazy="select" loads and deletes chunks via SQLAlchemy.
      Layer 2 — DB:  ON DELETE CASCADE on chunks.document_id FK ensures
                no orphan survives even a direct SQL DELETE or bulk operation.
    """
    user_id = get_user_id_from_payload(payload)
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    workspace = await db.get(Workspace, doc.workspace_id)
    if not workspace or workspace.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    # ORM delete — triggers cascade="all, delete-orphan" on chunks relationship
    await db.delete(doc)
    await db.commit()

    logger.info(
        "document_deleted",
        document_id=str(document_id),
        user_id=str(user_id),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitize_filename(filename: str) -> str:
    """
    Strips path traversal characters and replaces spaces.
    Prevents directory traversal attacks in file storage.
    """
    import re
    name = Path(filename).name          # strip any directory prefix
    name = re.sub(r"[^\w.\-]", "_", name)  # allow only safe chars
    return name[:200]                   # cap filename length


async def _run_ingestion(
    document_id: uuid.UUID,
    file_bytes: bytes,
    mime_type: str,
    user_id: uuid.UUID,
) -> None:
    """
    Background task: runs the full ingestion pipeline.
    Creates its own DB session since BackgroundTasks runs outside
    the request lifecycle (original session is already closed).
    """
    from app.core.database import get_session_factory
    async with get_session_factory()() as db:
        try:
            service = IngestionService()
            await service.ingest_document(
                db=db,
                document_id=document_id,
                file_bytes=file_bytes,
                mime_type=mime_type,
                user_id=user_id,
            )
        except Exception as e:
            logger.error(
                "background_ingestion_failed",
                doc_id=str(document_id),
                error=str(e),
            )


def _status_message(status: str) -> str:
    messages = {
        "pending": "Document queued for processing.",
        "processing": "Document is being ingested. Please wait.",
        "ready": "Document ingested successfully and ready for queries.",
        "failed": "Ingestion failed. Please re-upload the document.",
    }
    return messages.get(status, "Unknown status.")

