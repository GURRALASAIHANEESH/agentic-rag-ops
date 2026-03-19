import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pypdf
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document, Chunk
from app.models.audit import AuditLog
from app.services.embedder import get_embedding_service
from app.services.vector_store import get_vector_store, FAISSVectorStore
from app.metrics.prometheus import (
    INGESTION_COUNT, INGESTION_CHUNK_COUNT, INGESTION_LATENCY
)
import time

settings = get_settings()
logger = get_logger(__name__)


# ── Text chunker ──────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = None,
    overlap: int = None,
) -> list[str]:
    """
    Splits text into overlapping word-based chunks.

    Why word-based instead of token-based?
    Token counting requires loading a tokenizer (slow startup).
    Word count is a good proxy: ~1.3 words per token on average.
    For a 512-token chunk: 512 / 1.3 ≈ 394 words.

    overlap ensures consecutive chunks share context so retrieval
    doesn't miss answers that span a chunk boundary.
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP

    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        # Move forward by (chunk_size - overlap) to create the sliding window
        start += chunk_size - overlap

    return chunks


# ── PDF parser ────────────────────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> tuple[str, int]:
    """
    Extracts plain text from a PDF binary.
    Returns (full_text, page_count).

    Uses pypdf (pure Python, no system deps).
    Handles encrypted PDFs gracefully — returns empty string with a warning.
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        page_count = len(reader.pages)
        pages = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            # Add page marker for metadata tracking
            pages.append(f"[PAGE {i + 1}]\n{page_text}")
        return "\n\n".join(pages), page_count
    except pypdf.errors.PdfReadError as e:
        logger.warning("pdf_parse_failed", error=str(e))
        return "", 0


def extract_text_from_txt(file_bytes: bytes) -> tuple[str, int]:
    """Extracts text from a plain .txt file. Page count is always 1."""
    text = file_bytes.decode("utf-8", errors="replace")
    return text, 1


# ── Main ingestion pipeline ───────────────────────────────────────────────────

class IngestionService:
    """
    Full pipeline: file bytes → parse → chunk → embed → store in DB.

    Steps:
      1. Parse PDF/TXT to plain text
      2. Split into overlapping chunks
      3. Batch embed all chunks (single model call)
      4. Persist Chunk rows to Postgres (with vectors)
      5. If FAISS backend, also add to in-memory index
      6. Update Document.status → 'ready'
      7. Write AuditLog entry
    """

    def __init__(self):
        self._embedder = get_embedding_service()
        self._vector_store = get_vector_store()

    def _sanitize_text(self, text: str) -> str:
        """Remove null bytes and other characters illegal in PostgreSQL UTF-8."""
        return text.replace("\x00", "").replace("\u0000", "")

    async def ingest_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        file_bytes: bytes,
        mime_type: str,
        user_id: uuid.UUID,
    ) -> int:
        """
        Ingests a document. Returns the number of chunks created.
        Updates document.status throughout the process.
        """
        start_time = time.monotonic()

        # ── 1. Fetch document record ──────────────────────────────────────
        doc = await db.get(Document, document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found.")

        doc.status = "processing"
        await db.commit()
        logger.info("ingestion_started", doc_id=str(document_id))

        try:
            # ── 2. Parse file ─────────────────────────────────────────────
            if mime_type == "application/pdf":
                full_text, page_count = extract_text_from_pdf(file_bytes)
            else:
                full_text, page_count = extract_text_from_txt(file_bytes)

            if not full_text.strip():
                raise ValueError("Parsed document produced no text content.")

            doc.page_count = page_count

            # ── 3. Chunk text ─────────────────────────────────────────────
            raw_chunks = chunk_text(full_text)
            logger.info(
                "chunking_complete",
                doc_id=str(document_id),
                chunks=len(raw_chunks),
            )

            # ── 4. Batch embed all chunks ─────────────────────────────────
            embeddings = await self._embedder.embed_batch(raw_chunks)

            # ── 5. Build Chunk ORM objects ────────────────────────────────
            chunk_objects = []
            for i, (text_chunk, embedding) in enumerate(zip(raw_chunks, embeddings)):
                # Extract page number from the [PAGE N] marker if present
                page_num = self._extract_page_num(text_chunk, i)
                sanitized_text = self._sanitize_text(text_chunk)

                raw_metadata = {
                    "page_num": page_num,
                    "filename": doc.filename,
                    "chunk_total": len(raw_chunks),
                }
                
                sanitized_metadata = {
                    k: self._sanitize_text(v) if isinstance(v, str) else v
                    for k, v in raw_metadata.items()
                }

                chunk = Chunk(
                    id=uuid.uuid4(),
                    document_id=document_id,
                    workspace_id=doc.workspace_id,
                    chunk_index=i,
                    content=sanitized_text,
                    token_count=len(text_chunk.split()),  # word count proxy
                    embedding=embedding,
                    metadata_=sanitized_metadata,
                )
                chunk_objects.append(chunk)

                # If FAISS, add to in-memory index too
                if isinstance(self._vector_store, FAISSVectorStore):
                    self._vector_store.add_chunk(
                        chunk_id=chunk.id,
                        document_id=document_id,
                        workspace_id=doc.workspace_id,
                        content=sanitized_text,
                        embedding=embedding,
                        chunk_index=i,
                        metadata=sanitized_metadata,
                    )

            # ── 6. Persist all chunks in one transaction ──────────────────
            db.add_all(chunk_objects)

            # ── 7. Mark document ready ────────────────────────────────────
            doc.status = "ready"

            # Set retention expiry
            if settings.DOCUMENT_RETENTION_DAYS > 0:
                doc.expires_at = datetime.now(timezone.utc) + timedelta(
                    days=settings.DOCUMENT_RETENTION_DAYS
                )

            # ── 8. Write audit log ────────────────────────────────────────
            audit = AuditLog(
                user_id=user_id,
                event_type="ingestion",
                payload={
                    "document_id": str(document_id),
                    "filename": doc.filename,
                    "chunks_created": len(chunk_objects),
                    "page_count": page_count,
                    "mime_type": mime_type,
                },
            )
            db.add(audit)
            await db.commit()

            # Save FAISS index to disk if applicable
            if isinstance(self._vector_store, FAISSVectorStore):
                self._vector_store.save()

            # ── 9. Record metrics ─────────────────────────────────────────
            elapsed = time.monotonic() - start_time
            INGESTION_COUNT.labels(status="success").inc()
            INGESTION_CHUNK_COUNT.inc(len(chunk_objects))
            INGESTION_LATENCY.observe(elapsed)

            logger.info(
                "ingestion_complete",
                doc_id=str(document_id),
                chunks=len(chunk_objects),
                latency_s=round(elapsed, 2),
            )
            return len(chunk_objects)

        except Exception as e:
            await db.rollback()  # Clear the failed transaction state first
            
            # Re-fetch the document to update its status
            doc = await db.get(Document, document_id)
            if doc:
                doc.status = "failed"
                await db.commit()
                
            INGESTION_COUNT.labels(status="failed").inc()
            import traceback
            logger.error("ingestion_failed", doc_id=str(document_id), error=str(e), traceback=traceback.format_exc())
            raise

    def _extract_page_num(self, text: str, fallback: int) -> int:
        """Extracts page number from [PAGE N] marker inserted during PDF parse."""
        import re
        match = re.search(r"\[PAGE (\d+)\]", text)
        return int(match.group(1)) if match else fallback + 1
