"""
Tests for the ingestion pipeline.

Covers:
  - Text chunking (chunk_text)
  - PDF text extraction
  - Plain text extraction
  - Full ingestion pipeline with mocked embedder and vector store
  - Error handling (empty file, failed ingestion)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

from app.services.ingestion import chunk_text, extract_text_from_pdf, extract_text_from_txt
from app.models.document import Document


# ── Unit tests: chunk_text ────────────────────────────────────────────────────

class TestChunkText:

    def test_empty_text_returns_empty_list(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert chunk_text("   \n\t  ") == []

    def test_short_text_returns_single_chunk(self):
        text = "Short document with fewer words than chunk size."
        result = chunk_text(text, chunk_size=512, overlap=64)
        assert len(result) == 1
        assert result[0] == text.strip()

    def test_long_text_produces_multiple_chunks(self):
        # 1000 words should produce at least 2 chunks with chunk_size=512
        text = " ".join(["word"] * 1000)
        result = chunk_text(text, chunk_size=512, overlap=64)
        assert len(result) >= 2

    def test_overlap_creates_shared_content(self):
        """Adjacent chunks should share overlap words at their boundary."""
        words = [f"word{i}" for i in range(200)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        if len(chunks) >= 2:
            # Last 20 words of chunk 0 should appear at start of chunk 1
            end_of_first = chunks[0].split()[-20:]
            start_of_second = chunks[1].split()[:20]
            assert end_of_first == start_of_second

    def test_chunk_size_respected(self):
        text = " ".join(["word"] * 1000)
        result = chunk_text(text, chunk_size=100, overlap=10)
        for chunk in result:
            word_count = len(chunk.split())
            # Each chunk should be at most chunk_size words
            assert word_count <= 100

    def test_single_word_text(self):
        result = chunk_text("hello", chunk_size=512, overlap=64)
        assert len(result) == 1
        assert result[0] == "hello"


# ── Unit tests: file extraction ───────────────────────────────────────────────

class TestExtractTextFromTxt:

    def test_plain_utf8_text_extracted_correctly(self):
        content = "Hello world. This is a test document."
        text, pages = extract_text_from_txt(content.encode("utf-8"))
        assert text == content
        assert pages == 1

    def test_non_utf8_bytes_handled_gracefully(self):
        # Latin-1 encoded bytes should not raise, just replace
        bad_bytes = b"Caf\xe9 au lait"
        text, pages = extract_text_from_txt(bad_bytes)
        assert isinstance(text, str)
        assert pages == 1

    def test_empty_file_returns_empty_string(self):
        text, pages = extract_text_from_txt(b"")
        assert text == ""
        assert pages == 1


class TestExtractTextFromPdf:

    def test_invalid_pdf_bytes_returns_empty_string(self):
        text, pages = extract_text_from_pdf(b"this is not a pdf")
        assert text == ""
        assert pages == 0

    def test_empty_bytes_returns_empty(self):
        text, pages = extract_text_from_pdf(b"")
        assert text == ""
        assert pages == 0


# ── Integration tests: IngestionService ──────────────────────────────────────

class TestIngestionService:

    def _make_document(self, workspace_id: uuid.UUID) -> Document:
        return Document(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            filename="test_doc.txt",
            file_size_bytes=500,
            mime_type="text/plain",
            storage_path="/tmp/test_doc.txt",
            status="pending",
        )

    @pytest.mark.asyncio
    async def test_ingest_txt_creates_chunks(self, db, mock_embedder):
        """
        Ingesting a plain text file should create Chunk records
        in the database and update document status to 'ready'.
        """
        from app.services.ingestion import IngestionService

        workspace_id = uuid.uuid4()
        user_id = uuid.uuid4()
        doc = self._make_document(workspace_id)
        db.add(doc)
        await db.flush()

        content = " ".join([f"sentence {i} about transformers and attention." for i in range(100)])
        file_bytes = content.encode("utf-8")

        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[])

        with (
            patch(
                "app.services.ingestion.get_embedding_service",
                return_value=mock_embedder,
            ),
            patch(
                "app.services.ingestion.get_vector_store",
                return_value=mock_store,
            ),
        ):
            service = IngestionService()
            chunk_count = await service.ingest_document(
                db=db,
                document_id=doc.id,
                file_bytes=file_bytes,
                mime_type="text/plain",
                user_id=user_id,
            )

        assert chunk_count > 0
        # Reload document to check status was updated
        await db.refresh(doc)
        assert doc.status == "ready"
        assert doc.page_count == 1

    @pytest.mark.asyncio
    async def test_ingest_empty_file_marks_document_failed(self, db, mock_embedder):
        """
        Ingesting an empty file should mark the document as 'failed'
        and raise a ValueError.
        """
        from app.services.ingestion import IngestionService

        workspace_id = uuid.uuid4()
        user_id = uuid.uuid4()
        doc = self._make_document(workspace_id)
        db.add(doc)
        await db.flush()

        mock_store = MagicMock()

        with (
            patch(
                "app.services.ingestion.get_embedding_service",
                return_value=mock_embedder,
            ),
            patch(
                "app.services.ingestion.get_vector_store",
                return_value=mock_store,
            ),
        ):
            service = IngestionService()
            with pytest.raises(ValueError, match="no text content"):
                await service.ingest_document(
                    db=db,
                    document_id=doc.id,
                    file_bytes=b"",
                    mime_type="text/plain",
                    user_id=user_id,
                )

        await db.refresh(doc)
        assert doc.status == "failed"

    @pytest.mark.asyncio
    async def test_ingest_nonexistent_document_raises(self, db, mock_embedder):
        """
        Attempting to ingest a document ID that does not exist
        should raise a ValueError immediately.
        """
        from app.services.ingestion import IngestionService

        mock_store = MagicMock()

        with (
            patch(
                "app.services.ingestion.get_embedding_service",
                return_value=mock_embedder,
            ),
            patch(
                "app.services.ingestion.get_vector_store",
                return_value=mock_store,
            ),
        ):
            service = IngestionService()
            with pytest.raises(ValueError, match="not found"):
                await service.ingest_document(
                    db=db,
                    document_id=uuid.uuid4(),  # does not exist
                    file_bytes=b"some content",
                    mime_type="text/plain",
                    user_id=uuid.uuid4(),
                )

    @pytest.mark.asyncio
    async def test_ingest_sets_retention_expiry(self, db, mock_embedder):
        """
        When DOCUMENT_RETENTION_DAYS > 0, the document should have
        an expires_at value set after ingestion.
        """
        from app.services.ingestion import IngestionService

        workspace_id = uuid.uuid4()
        user_id = uuid.uuid4()
        doc = self._make_document(workspace_id)
        db.add(doc)
        await db.flush()

        content = " ".join([f"word{i}" for i in range(200)])
        mock_store = MagicMock()

        with (
            patch(
                "app.services.ingestion.get_embedding_service",
                return_value=mock_embedder,
            ),
            patch(
                "app.services.ingestion.get_vector_store",
                return_value=mock_store,
            ),
            patch(
                "app.services.ingestion.settings.DOCUMENT_RETENTION_DAYS",
                30,
            ),
        ):
            service = IngestionService()
            await service.ingest_document(
                db=db,
                document_id=doc.id,
                file_bytes=content.encode(),
                mime_type="text/plain",
                user_id=user_id,
            )

        await db.refresh(doc)
        assert doc.expires_at is not None
        # SQLite stores datetimes without timezone info (naive), so compare
        # against naive datetime.now() to avoid offset-naive/aware TypeError.
        assert doc.expires_at > datetime.now()
