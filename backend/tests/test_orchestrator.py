"""
Integration tests for the Orchestrator pipeline.

The LLM, embedder, and vector store are all mocked.
Tests verify the full Router -> Retrieval -> LLM -> Critic flow
produces correct SSE events in the correct order.
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.orchestrator import Orchestrator
from app.schemas.query import QueryRequest
from app.models.user import Workspace


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_sse_events(events: list[str]) -> list[dict]:
    """
    Parses a list of SSE event strings into dicts.
    Filters out empty lines and non-data lines.
    """
    parsed = []
    for event in events:
        for line in event.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                try:
                    parsed.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass
    return parsed


async def collect_stream(orchestrator: Orchestrator, request: QueryRequest, user_id: uuid.UUID) -> list[dict]:
    """Collects all SSE events from the orchestrator into a list."""
    raw_events = []
    async for event in orchestrator.run_streaming(request=request, user_id=user_id):
        raw_events.append(event)
    return parse_sse_events(raw_events)


def make_request(workspace_id: uuid.UUID, query: str = "What is attention?") -> QueryRequest:
    return QueryRequest(
        query=query,
        workspace_id=workspace_id,
        top_k=3,
        stream=True,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestOrchestratorPipeline:

    @pytest.mark.asyncio
    async def test_full_pipeline_emits_token_citations_critic_done(
        self, db, mock_llm, mock_embedder, test_user
    ):
        """
        A successful query should emit events in the order:
        token(s) -> citations -> critic -> done
        """
        workspace = test_user["workspace"]
        user = test_user["user"]
        request = make_request(workspace.id)

        from app.services.vector_store import RetrievedChunk
        mock_chunk = RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            workspace_id=workspace.id,
            content="Attention mechanisms compute query key value vectors.",
            similarity=0.88,
            chunk_index=0,
            metadata={},
        )

        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[mock_chunk])

        mock_router_response = {"route": "local", "reason": "Query is specific."}
        mock_critic_report_response = json.dumps([
            {
                "claim": "Attention uses query key value.",
                "status": "verified",
                "confidence": 0.9,
                "supporting_sources": [1],
            }
        ])

        with (
            patch("app.services.orchestrator.get_llm_client", return_value=mock_llm),
            patch("app.services.retriever.get_embedding_service", return_value=mock_embedder),
            patch("app.services.retriever.get_vector_store", return_value=mock_store),
            patch("app.services.critic_agent.get_embedding_service", return_value=mock_embedder),
        ):
            mock_llm.generate = AsyncMock(side_effect=[
                json.dumps(mock_router_response),  # first call: router
                mock_critic_report_response,        # second call: critic
            ])

            orchestrator = Orchestrator(db=db)
            events = await collect_stream(orchestrator, request, user.id)

        event_types = [e["type"] for e in events]

        # Verify ordering: tokens come before citations, citations before critic, done is last
        assert "token" in event_types
        assert "citations" in event_types
        assert "critic" in event_types
        assert "done" in event_types
        assert event_types.index("citations") > event_types.index("token")
        assert event_types.index("critic") > event_types.index("citations")
        assert event_types[-1] == "done"

    @pytest.mark.asyncio
    async def test_pipeline_emits_clarify_when_router_decides_clarify(
        self, db, mock_llm, mock_embedder, test_user
    ):
        """
        When the router returns 'clarify', the pipeline should emit
        a 'clarify' event and stop — no retrieval or LLM call.
        """
        workspace = test_user["workspace"]
        user = test_user["user"]
        request = make_request(workspace.id, query="stuff")

        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[])

        clarify_response = json.dumps({
            "route": "clarify",
            "reason": "Query is too vague.",
            "suggestion": "Try asking: What is the attention mechanism in Transformers?",
        })

        with (
            patch("app.services.orchestrator.get_llm_client", return_value=mock_llm),
            patch("app.services.retriever.get_embedding_service", return_value=mock_embedder),
            patch("app.services.retriever.get_vector_store", return_value=mock_store),
            patch("app.services.critic_agent.get_embedding_service", return_value=mock_embedder),
        ):
            mock_llm.generate = AsyncMock(return_value=clarify_response)
            orchestrator = Orchestrator(db=db)
            events = await collect_stream(orchestrator, request, user.id)

        event_types = [e["type"] for e in events]
        assert "clarify" in event_types
        # Pipeline must stop after clarify — no token, citations, or critic
        assert "token" not in event_types
        assert "citations" not in event_types

    @pytest.mark.asyncio
    async def test_pipeline_handles_no_chunks_gracefully(
        self, db, mock_llm, mock_embedder, test_user
    ):
        """
        When retrieval returns no chunks, the pipeline should emit a
        token with a fallback message and done — no critic call needed.
        """
        workspace = test_user["workspace"]
        user = test_user["user"]
        request = make_request(workspace.id)

        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[])

        router_response = json.dumps({
            "route": "local",
            "reason": "Proceeding with local retrieval.",
        })

        with (
            patch("app.services.orchestrator.get_llm_client", return_value=mock_llm),
            patch("app.services.retriever.get_embedding_service", return_value=mock_embedder),
            patch("app.services.retriever.get_vector_store", return_value=mock_store),
            patch("app.services.critic_agent.get_embedding_service", return_value=mock_embedder),
        ):
            mock_llm.generate = AsyncMock(return_value=router_response)
            orchestrator = Orchestrator(db=db)
            events = await collect_stream(orchestrator, request, user.id)

        event_types = [e["type"] for e in events]
        assert "token" in event_types
        assert "done" in event_types

        # Verify the no-context message was returned
        token_events = [e for e in events if e["type"] == "token"]
        combined_text = "".join(e.get("data", "") for e in token_events)
        assert "relevant information" in combined_text.lower()

    @pytest.mark.asyncio
    async def test_pipeline_rejects_wrong_workspace(
        self, db, mock_llm, mock_embedder, test_user
    ):
        """
        If the workspace does not belong to the requesting user,
        the pipeline should emit an error event.
        """
        user = test_user["user"]
        # Use a workspace ID that does not belong to this user
        wrong_workspace_id = uuid.uuid4()
        request = make_request(wrong_workspace_id)

        with (
            patch("app.services.orchestrator.get_llm_client", return_value=mock_llm),
            patch("app.services.retriever.get_embedding_service", return_value=mock_embedder),
        ):
            orchestrator = Orchestrator(db=db)
            events = await collect_stream(orchestrator, request, user.id)

        event_types = [e["type"] for e in events]
        assert "error" in event_types

    @pytest.mark.asyncio
    async def test_run_sync_returns_query_response_object(
        self, db, mock_llm, mock_embedder, test_user
    ):
        """
        run_sync() should collect all SSE events and return
        a well-formed QueryResponse object.
        """
        from app.schemas.query import QueryResponse

        workspace = test_user["workspace"]
        user = test_user["user"]
        request = make_request(workspace.id)
        request.stream = False

        mock_chunk = MagicMock()
        mock_chunk.chunk_id = uuid.uuid4()
        mock_chunk.document_id = uuid.uuid4()
        mock_chunk.workspace_id = workspace.id
        mock_chunk.content = "Attention is all you need."
        mock_chunk.similarity = 0.9
        mock_chunk.chunk_index = 0
        mock_chunk.metadata = {}

        mock_store = MagicMock()
        mock_store.search = AsyncMock(return_value=[mock_chunk])

        router_json = json.dumps({"route": "local", "reason": "Specific query."})
        critic_json = json.dumps([
            {
                "claim": "Attention is all you need.",
                "status": "verified",
                "confidence": 0.92,
                "supporting_sources": [1],
            }
        ])

        with (
            patch("app.services.orchestrator.get_llm_client", return_value=mock_llm),
            patch("app.services.retriever.get_embedding_service", return_value=mock_embedder),
            patch("app.services.retriever.get_vector_store", return_value=mock_store),
            patch("app.services.critic_agent.get_embedding_service", return_value=mock_embedder),
        ):
            mock_llm.generate = AsyncMock(side_effect=[router_json, critic_json])
            orchestrator = Orchestrator(db=db)
            result = await orchestrator.run_sync(request=request, user_id=user.id)

        assert isinstance(result, QueryResponse)
        assert result.answer != ""
        assert isinstance(result.critic.overall_score, float)
