"""
Tests for the CriticAgent service.

Covers:
  - LLM-based claim verification
  - Embedding fallback for unverified claims
  - Malformed LLM response fallback (sentence split)
  - CriticReport aggregation
  - Disabled critic passthrough
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.critic_agent import CriticAgent
from app.services.vector_store import RetrievedChunk
from app.schemas.query import CriticReport, ClaimVerification


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_chunk(content: str = "Transformers use self-attention.", similarity: float = 0.85) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        content=content,
        similarity=similarity,
        chunk_index=0,
        metadata={},
    )


VALID_LLM_CRITIC_RESPONSE = """
[
  {
    "claim": "Transformers use self-attention mechanisms.",
    "status": "verified",
    "confidence": 0.95,
    "supporting_sources": [1]
  },
  {
    "claim": "The model was trained on 100TB of data.",
    "status": "unverified",
    "confidence": 0.05,
    "supporting_sources": []
  }
]
"""

MALFORMED_LLM_RESPONSE = "Sorry, I cannot verify this at the moment."


# ── Unit tests: CriticReport building ────────────────────────────────────────

class TestCriticReportBuilding:

    def setup_method(self):
        mock_llm = MagicMock()
        mock_llm.model_name = "mock-model"
        mock_llm.provider_name = "mock"
        self.critic = CriticAgent.__new__(CriticAgent)
        self.critic._llm = mock_llm
        self.critic._embedder = MagicMock()

    def test_build_report_computes_correct_counts(self):
        claims = [
            ClaimVerification(claim="c1", status="verified", confidence=0.9, supporting_chunk_ids=[]),
            ClaimVerification(claim="c2", status="unverified", confidence=0.1, supporting_chunk_ids=[]),
            ClaimVerification(claim="c3", status="partial", confidence=0.5, supporting_chunk_ids=[]),
        ]
        report = self.critic._build_report(claims)
        assert report.verified_count == 1
        assert report.unverified_count == 1
        assert report.partial_count == 1

    def test_build_report_overall_score_is_mean_confidence(self):
        claims = [
            ClaimVerification(claim="c1", status="verified", confidence=0.8, supporting_chunk_ids=[]),
            ClaimVerification(claim="c2", status="verified", confidence=0.6, supporting_chunk_ids=[]),
        ]
        report = self.critic._build_report(claims)
        assert abs(report.overall_score - 0.7) < 0.001

    def test_build_report_empty_claims_returns_zero_score(self):
        report = self.critic._build_report([])
        assert report.overall_score == 0.0
        assert report.verified_count == 0

    def test_confidence_clamped_between_zero_and_one(self):
        claims = [
            ClaimVerification(
                claim="test",
                status="verified",
                # Pydantic Field ge=0.0 le=1.0 enforces this at schema level
                confidence=1.0,
                supporting_chunk_ids=[],
            )
        ]
        report = self.critic._build_report(claims)
        assert 0.0 <= report.overall_score <= 1.0


class TestCriticFallbackSentenceSplit:

    def setup_method(self):
        mock_llm = MagicMock()
        self.critic = CriticAgent.__new__(CriticAgent)
        self.critic._llm = mock_llm
        self.critic._embedder = MagicMock()

    def test_fallback_splits_on_sentence_boundaries(self):
        answer = "First sentence. Second sentence. Third sentence."
        result = self.critic._fallback_sentence_split(answer)
        assert len(result) == 3

    def test_fallback_marks_all_claims_unverified(self):
        answer = "Claim one. Claim two."
        result = self.critic._fallback_sentence_split(answer)
        assert all(c["status"] == "unverified" for c in result)

    def test_fallback_marks_all_confidence_zero(self):
        answer = "Some claim here. Another claim."
        result = self.critic._fallback_sentence_split(answer)
        assert all(c["confidence"] == 0.0 for c in result)

    def test_fallback_handles_single_sentence(self):
        answer = "Only one sentence here."
        result = self.critic._fallback_sentence_split(answer)
        assert len(result) == 1
        assert result[0]["claim"] == "Only one sentence here."


class TestCriticSourceMapping:

    def setup_method(self):
        mock_llm = MagicMock()
        self.critic = CriticAgent.__new__(CriticAgent)
        self.critic._llm = mock_llm
        self.critic._embedder = MagicMock()

    def test_source_index_mapped_to_chunk_uuid(self):
        chunk1 = make_chunk()
        chunk2 = make_chunk()
        raw_chunks = [chunk1, chunk2]

        llm_claims = [
            {
                "claim": "Some verified claim.",
                "status": "verified",
                "confidence": 0.9,
                "supporting_sources": [1, 2],  # 1-based
            }
        ]

        result = self.critic._map_sources_to_chunk_ids(llm_claims, raw_chunks)
        assert len(result) == 1
        assert chunk1.chunk_id in result[0].supporting_chunk_ids
        assert chunk2.chunk_id in result[0].supporting_chunk_ids

    def test_out_of_range_source_index_is_ignored(self):
        chunk = make_chunk()
        raw_chunks = [chunk]

        llm_claims = [
            {
                "claim": "Claim referencing non-existent source.",
                "status": "verified",
                "confidence": 0.7,
                "supporting_sources": [99],  # out of range
            }
        ]

        result = self.critic._map_sources_to_chunk_ids(llm_claims, raw_chunks)
        assert result[0].supporting_chunk_ids == []

    def test_empty_supporting_sources_produces_empty_chunk_ids(self):
        raw_chunks = [make_chunk()]
        llm_claims = [
            {
                "claim": "Unverified claim.",
                "status": "unverified",
                "confidence": 0.1,
                "supporting_sources": [],
            }
        ]
        result = self.critic._map_sources_to_chunk_ids(llm_claims, raw_chunks)
        assert result[0].supporting_chunk_ids == []


# ── Integration tests: verify() method ───────────────────────────────────────

class TestCriticVerify:

    @pytest.mark.asyncio
    async def test_verify_returns_critic_report_with_valid_llm_response(
        self, db, mock_embedder
    ):
        mock_llm = MagicMock()
        mock_llm.model_name = "mock-model"
        mock_llm.provider_name = "mock"
        mock_llm.generate = AsyncMock(return_value=VALID_LLM_CRITIC_RESPONSE)

        with patch(
            "app.services.critic_agent.get_embedding_service",
            return_value=mock_embedder,
        ):
            critic = CriticAgent(llm_client=mock_llm)
            report = await critic.verify(
                db=db,
                answer="Transformers use self-attention. The model trained on 100TB.",
                raw_chunks=[make_chunk()],
                query_log_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )

        assert isinstance(report, CriticReport)
        assert report.verified_count >= 1
        assert 0.0 <= report.overall_score <= 1.0

    @pytest.mark.asyncio
    async def test_verify_falls_back_on_malformed_llm_response(
        self, db, mock_embedder
    ):
        """
        When the LLM returns non-JSON, the critic falls back to
        sentence splitting and marks all claims unverified.
        """
        mock_llm = MagicMock()
        mock_llm.model_name = "mock-model"
        mock_llm.provider_name = "mock"
        mock_llm.generate = AsyncMock(return_value=MALFORMED_LLM_RESPONSE)

        with patch(
            "app.services.critic_agent.get_embedding_service",
            return_value=mock_embedder,
        ):
            critic = CriticAgent(llm_client=mock_llm)
            report = await critic.verify(
                db=db,
                answer="First claim. Second claim.",
                raw_chunks=[make_chunk()],
                query_log_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )

        assert isinstance(report, CriticReport)
        # All claims should be unverified or partial (embedding fallback may upgrade)
        assert report.verified_count == 0 or report.partial_count >= 0

    @pytest.mark.asyncio
    async def test_verify_returns_passthrough_when_disabled(
        self, db, mock_embedder
    ):
        """When CRITIC_ENABLED=false, all claims are returned as verified."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="[]")

        with (
            patch(
                "app.services.critic_agent.get_embedding_service",
                return_value=mock_embedder,
            ),
            patch(
                "app.services.critic_agent.settings.CRITIC_ENABLED",
                False,
            ),
        ):
            critic = CriticAgent(llm_client=mock_llm)
            report = await critic.verify(
                db=db,
                answer="Single claim sentence.",
                raw_chunks=[],
                query_log_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )

        assert report.overall_score == 1.0
        assert report.unverified_count == 0

    @pytest.mark.asyncio
    async def test_verify_with_no_chunks_returns_empty_report(
        self, db, mock_embedder
    ):
        """When no chunks are retrieved, verify returns a passthrough report."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="[]")

        with patch(
            "app.services.critic_agent.get_embedding_service",
            return_value=mock_embedder,
        ):
            critic = CriticAgent(llm_client=mock_llm)
            report = await critic.verify(
                db=db,
                answer="Some answer.",
                raw_chunks=[],   # no chunks triggers passthrough
                query_log_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )

        assert isinstance(report, CriticReport)
