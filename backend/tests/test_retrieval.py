"""
Tests for retrieval service and retrieval API endpoints.

Unit tests mock the vector store to avoid needing a live Postgres + pgvector.
Integration tests use the FAISS backend with the mock embedder.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.retriever import RetrieverService
from app.services.vector_store import RetrievedChunk
from app.schemas.query import CitationSchema


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_chunk(
    similarity: float = 0.85,
    content: str = "Attention mechanisms use query, key and value vectors.",
    chunk_index: int = 0,
) -> RetrievedChunk:
    """Factory for RetrievedChunk test objects."""
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        content=content,
        similarity=similarity,
        chunk_index=chunk_index,
        metadata={"page_num": 1, "filename": "test.txt"},
    )


# ── Unit tests: RetrieverService ─────────────────────────────────────────────

class TestRetrieverServiceSnippet:
    """Tests for the snippet generation helper."""

    def setup_method(self):
        self.retriever = RetrieverService.__new__(RetrieverService)

    def test_short_content_returned_as_is(self):
        content = "Short text under 300 chars."
        result = self.retriever._make_snippet(content)
        assert result == content

    def test_long_content_truncated_at_word_boundary(self):
        # Build exactly 350 words so it must be truncated
        content = " ".join(["word"] * 350)
        result = self.retriever._make_snippet(content, max_chars=300)
        assert len(result) <= 301  # 300 + ellipsis char
        assert result.endswith("…")

    def test_newlines_stripped_from_snippet(self):
        content = "Line one.\nLine two.\nLine three."
        result = self.retriever._make_snippet(content)
        assert "\n" not in result

    def test_empty_content_returns_empty(self):
        result = self.retriever._make_snippet("", max_chars=300)
        assert result == ""


class TestRetrieverContextBlock:
    """Tests for context block formatting."""

    def setup_method(self):
        self.retriever = RetrieverService.__new__(RetrieverService)

    def test_context_block_uses_source_numbering(self):
        chunks = [make_chunk(similarity=0.9), make_chunk(similarity=0.8)]
        block = self.retriever.build_context_block(chunks)
        assert "[SOURCE 1]" in block
        assert "[SOURCE 2]" in block

    def test_context_block_includes_similarity_score(self):
        chunks = [make_chunk(similarity=0.87)]
        block = self.retriever.build_context_block(chunks)
        assert "0.87" in block

    def test_empty_chunks_returns_no_context_message(self):
        block = self.retriever.build_context_block([])
        assert "No relevant context" in block

    def test_context_block_preserves_chunk_order(self):
        c1 = make_chunk(content="First chunk content.", chunk_index=0)
        c2 = make_chunk(content="Second chunk content.", chunk_index=1)
        block = self.retriever.build_context_block([c1, c2])
        assert block.index("First chunk") < block.index("Second chunk")


class TestRetrieverRetrieve:
    """Integration-style tests for the retrieve() method."""

    @pytest.mark.asyncio
    async def test_retrieve_returns_citations_and_raw_chunks(
        self, db, mock_embedder
    ):
        """
        retrieve() should return both citations and raw chunks
        when the vector store returns results.
        """
        workspace_id = uuid.uuid4()
        query_log_id = uuid.uuid4()
        mock_chunk = make_chunk(similarity=0.88)
        mock_chunk.workspace_id = workspace_id

        # Mock vector store to return one chunk
        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[mock_chunk])

        with (
            patch(
                "app.services.retriever.get_embedding_service",
                return_value=mock_embedder,
            ),
            patch(
                "app.services.retriever.get_vector_store",
                return_value=mock_store,
            ),
        ):
            retriever = RetrieverService()
            citations, raw_chunks = await retriever.retrieve(
                db=db,
                query="What is attention mechanism?",
                workspace_id=workspace_id,
                query_log_id=query_log_id,
                top_k=5,
            )

        assert len(citations) == 1
        assert len(raw_chunks) == 1
        assert isinstance(citations[0], CitationSchema)
        assert citations[0].similarity == 0.88

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_on_no_chunks(self, db, mock_embedder):
        """
        retrieve() should return empty lists when no chunks are found.
        """
        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[])

        with (
            patch(
                "app.services.retriever.get_embedding_service",
                return_value=mock_embedder,
            ),
            patch(
                "app.services.retriever.get_vector_store",
                return_value=mock_store,
            ),
        ):
            retriever = RetrieverService()
            citations, raw_chunks = await retriever.retrieve(
                db=db,
                query="Unknown query with no matches",
                workspace_id=uuid.uuid4(),
                query_log_id=uuid.uuid4(),
                top_k=5,
            )

        assert citations == []
        assert raw_chunks == []

    @pytest.mark.asyncio
    async def test_retrieve_filters_by_min_similarity(self, db, mock_embedder):
        """
        Chunks below RETRIEVAL_MIN_SIMILARITY should not appear in results.
        This is enforced inside the vector store — we verify the parameter
        is passed through correctly.
        """
        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[])

        with (
            patch(
                "app.services.retriever.get_embedding_service",
                return_value=mock_embedder,
            ),
            patch(
                "app.services.retriever.get_vector_store",
                return_value=mock_store,
            ),
        ):
            retriever = RetrieverService()
            await retriever.retrieve(
                db=db,
                query="test query",
                workspace_id=uuid.uuid4(),
                query_log_id=uuid.uuid4(),
                top_k=5,
            )

        # Verify min_similarity was passed to the vector store
        call_kwargs = mock_store.search.call_args.kwargs
        assert "min_similarity" in call_kwargs
        assert call_kwargs["min_similarity"] > 0


# ── API endpoint tests ────────────────────────────────────────────────────────

class TestRetrievalAPI:
    """Tests for /api/retrieval/* endpoints."""

    @pytest.mark.asyncio
    async def test_semantic_search_requires_auth(self, client):
        """Unauthenticated requests must receive 403."""
        response = await client.post(
            "/api/retrieval/search",
            params={"workspace_id": str(uuid.uuid4()), "query": "test"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_query_history_empty_for_new_workspace(
        self, client, auth_headers, test_user
    ):
        """A new workspace should have an empty query history."""
        workspace_id = test_user["workspace"].id
        response = await client.get(
            "/api/retrieval/history",
            params={"workspace_id": str(workspace_id)},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_provenance_returns_404_for_unknown_id(
        self, client, auth_headers
    ):
        """Requesting provenance for a non-existent query log returns 404."""
        response = await client.get(
            f"/api/retrieval/history/{uuid.uuid4()}/provenance",
            headers=auth_headers,
        )
        assert response.status_code == 404
