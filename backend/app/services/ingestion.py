# backend/app/services/ingestion.py
import io
import re
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pypdf
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document, Chunk
from app.models.audit import AuditLog
from app.services.embedder import get_embedding_service
from app.services.vector_store import get_vector_store, FAISSVectorStore
from app.metrics.prometheus import (
    INGESTION_COUNT, INGESTION_CHUNK_COUNT, INGESTION_LATENCY,
)

logger = get_logger(__name__)


# ── Section-aware chunker ─────────────────────────────────────────────────────

# Matches resume/document section headers in ALL-CAPS or Title Case:
# e.g. "PROJECTS", "EXPERIENCE", "SKILLS", "EDUCATION", "Projects:", "Work Experience"
# Anchored to line start to avoid matching mid-sentence uppercase words.
_SECTION_HEADER_RE = re.compile(
    r"^(?:"
    r"[A-Z][A-Z\s&/]{2,}|"           # ALL-CAPS header:  "PROJECTS", "WORK EXPERIENCE"
    r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)*" # Title Case header: "Projects", "Work Experience"
    r")(?:\s*:)?\s*$",
    re.MULTILINE,
)


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """
    Splits document text into (section_name, section_body) pairs.

    Strategy:
      - Scan for lines that match _SECTION_HEADER_RE.
      - Everything before the first header goes into a "Header" section
        (captures name/contact block in resumes).
      - Each subsequent header starts a new section.

    Returns:
        List of (section_name, body_text) tuples. Guaranteed non-empty.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    sections: list[tuple[str, str]] = []
    current_name = "Header"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and _SECTION_HEADER_RE.match(stripped):
            # Flush the current section if it has content
            body = "\n".join(current_lines).strip()
            if body:
                sections.append((current_name, body))
            current_name = stripped.rstrip(":")
            current_lines = []
        else:
            current_lines.append(line)

    # Flush final section
    body = "\n".join(current_lines).strip()
    if body:
        sections.append((current_name, body))

    # Fallback: if no headers were detected, treat whole doc as one section
    if not sections:
        sections = [("Document", text.strip())]

    return sections


def _chunk_section(
    section_name: str,
    body: str,
    chunk_size: int,
    overlap: int,
) -> list[tuple[str, str]]:
    """
    Splits a single section body into overlapping word-window chunks.

    Returns list of (section_name, chunk_text) tuples.

    Design decisions:
      - Normalize whitespace once at entry — no repeated .split() overhead.
      - Overlap is applied to EVERY split boundary (not just oversized paragraphs).
      - Minimum chunk size guard: drops chunks under 10 words (pure noise).
      - Prepends section name to each chunk so embedding captures topic context:
        "PROJECTS: Built an Agentic RAG pipeline using FastAPI..."
    """
    # Flatten all whitespace within the section into a single word list
    words = body.split()
    if not words:
        return []

    chunks: list[tuple[str, str]] = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        window = words[start:end]

        if len(window) >= 10:  # drop micro-fragments (noise)
            # Prepend section header for embedding context
            chunk_text = f"{section_name}: " + " ".join(window)
            chunks.append((section_name, chunk_text))

        # Advance by (chunk_size - overlap) so next chunk starts in the
        # overlap window — every boundary gets context from its predecessor
        advance = max(1, chunk_size - overlap)
        start += advance

    return chunks


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[tuple[str, str]]:
    """
    Section-aware chunker. Replaces the previous paragraph-split chunker.

    Returns list of (section_name, chunk_text) tuples.
    The section_name is stored in chunk metadata for observability.

    Algorithm:
      1. Split document into named sections via header detection
      2. Apply sliding-window chunking within each section with overlap
      3. Merge sub-threshold trailing words into the preceding chunk

    Args:
        text:        Raw document text (UTF-8, any line endings)
        chunk_size:  Max words per chunk. Defaults to CHUNK_SIZE from config.
        overlap:     Overlap words between consecutive chunks.
                     Defaults to CHUNK_OVERLAP from config.

    NOTE: Parameters resolve from config when None, never use `or` to coerce
    (avoids treating 0 as falsy — same fix pattern as BUG 1).
    """
    cfg = get_settings()
    resolved_size    = chunk_size if chunk_size is not None else cfg.CHUNK_SIZE
    resolved_overlap = overlap    if overlap    is not None else cfg.CHUNK_OVERLAP

    sections = _split_into_sections(text)

    all_chunks: list[tuple[str, str]] = []
    for section_name, body in sections:
        section_chunks = _chunk_section(section_name, body, resolved_size, resolved_overlap)
        all_chunks.extend(section_chunks)

    logger.debug(
        "chunking_sections",
        total_sections=len(sections),
        total_chunks=len(all_chunks),
        section_names=[s for s, _ in sections],
    )
    return all_chunks


# ── PDF / TXT extractors ──────────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> tuple[str, int]:
    """
    Extracts plain text from a PDF binary.
    Returns (full_text, page_count).

    Uses pypdf (pure Python, no system deps).
    Handles encrypted/malformed PDFs gracefully — returns ("", 0) with warning.
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        page_count = len(reader.pages)
        pages = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            pages.append(f"[PAGE {i + 1}]\n{page_text}")
        return "\n\n".join(pages), page_count
    except pypdf.errors.PdfReadError as e:
        logger.warning("pdf_parse_failed", error=str(e))
        return "", 0


def extract_text_from_txt(file_bytes: bytes) -> tuple[str, int]:
    """Extracts text from a plain .txt file. Page count is always 1."""
    return file_bytes.decode("utf-8", errors="replace"), 1


# ── Ingestion pipeline ────────────────────────────────────────────────────────

class IngestionService:
    """
    Full pipeline: file bytes → parse → chunk → embed → store in DB.

    Steps:
      1.  Fetch Document record from DB
      2.  Parse PDF or TXT to raw text
      3.  Section-aware chunking → list of (section_name, chunk_text)
      4.  Batch embed all chunks in a single model call
      5.  Build Chunk ORM objects with section metadata
      6.  Persist all chunks in one DB transaction
      7.  If FAISS backend: add to in-memory index + save to disk
      8.  Mark Document.status = 'ready', set retention expiry
      9.  Write AuditLog entry
      10. Record Prometheus metrics
    """

    def __init__(self):
        self._embedder = get_embedding_service()
        self._vector_store = get_vector_store()

    def _sanitize_text(self, text: str) -> str:
        """Remove null bytes and characters illegal in PostgreSQL UTF-8."""
        return text.replace("\x00", "").replace("\u0000", "")

    def _extract_page_num(self, text: str, fallback: int) -> int:
        """Extracts page number from [PAGE N] marker inserted during PDF parse."""
        match = re.search(r"\[PAGE (\d+)\]", text)
        return int(match.group(1)) if match else fallback + 1

    async def ingest_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        file_bytes: bytes,
        mime_type: str,
        user_id: uuid.UUID,
    ) -> int:
        """
        Ingests a document end-to-end. Returns the number of chunks created.
        Updates document.status to 'processing' → 'ready' | 'failed'.
        """
        start_time = time.monotonic()
        cfg = get_settings()  # single config read for entire pipeline

        # ── 1. Fetch document record ──────────────────────────────────────
        doc = await db.get(Document, document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found.")

        doc.status = "processing"
        await db.commit()
        logger.info("ingestion_started", doc_id=str(document_id), filename=doc.filename)

        try:
            # ── 2. Parse file ─────────────────────────────────────────────
            if mime_type == "application/pdf":
                full_text, page_count = extract_text_from_pdf(file_bytes)
            else:
                full_text, page_count = extract_text_from_txt(file_bytes)

            if not full_text.strip():
                raise ValueError("Parsed document produced no text content.")

            doc.page_count = page_count

            # ── 3. Section-aware chunking ─────────────────────────────────
            # Returns list of (section_name, chunk_text)
            raw_chunks: list[tuple[str, str]] = chunk_text(full_text)

            if not raw_chunks:
                raise ValueError("Chunking produced zero chunks — document may be empty.")

            logger.info(
                "chunking_complete",
                doc_id=str(document_id),
                chunks=len(raw_chunks),
                sections=list({s for s, _ in raw_chunks}),
            )

            # ── 4. Batch embed all chunk texts ────────────────────────────
            chunk_texts_only = [text for _, text in raw_chunks]
            embeddings = await self._embedder.embed_batch(chunk_texts_only)

            # ── 5. Build Chunk ORM objects ────────────────────────────────
            chunk_objects: list[Chunk] = []

            for i, ((section_name, chunk_text_val), embedding) in enumerate(
                zip(raw_chunks, embeddings)
            ):
                page_num        = self._extract_page_num(chunk_text_val, i)
                sanitized_text  = self._sanitize_text(chunk_text_val)

                raw_metadata = {
                    "page_num":     page_num,
                    "filename":     doc.filename,
                    "chunk_total":  len(raw_chunks),
                    "section":      section_name,   # ← NEW: section provenance
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
                    token_count=len(sanitized_text.split()),
                    embedding=embedding,
                    metadata_=sanitized_metadata,
                )
                chunk_objects.append(chunk)

                # Sync to FAISS in-memory index if applicable
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

            # ── 7. Mark document ready + set retention expiry ─────────────
            doc.status = "ready"
            if cfg.DOCUMENT_RETENTION_DAYS > 0:
                doc.expires_at = datetime.now(timezone.utc) + timedelta(
                    days=cfg.DOCUMENT_RETENTION_DAYS
                )

            # ── 8. Write audit log ────────────────────────────────────────
            db.add(AuditLog(
                user_id=user_id,
                event_type="ingestion",
                payload={
                    "document_id":   str(document_id),
                    "filename":      doc.filename,
                    "chunks_created": len(chunk_objects),
                    "page_count":    page_count,
                    "mime_type":     mime_type,
                    "sections":      list({s for s, _ in raw_chunks}),
                },
            ))
            await db.commit()

            # ── 9. Persist FAISS index to disk ────────────────────────────
            if isinstance(self._vector_store, FAISSVectorStore):
                self._vector_store.save()

            # ── 10. Prometheus metrics ────────────────────────────────────
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
            await db.rollback()

            # Re-fetch after rollback — original `doc` reference is stale
            doc = await db.get(Document, document_id)
            if doc:
                doc.status = "failed"
                await db.commit()

            INGESTION_COUNT.labels(status="failed").inc()
            logger.error(
                "ingestion_failed",
                doc_id=str(document_id),
                error=str(e),
                traceback=traceback.format_exc(),
            )
            raise
