import re
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.audit import AuditLog
from app.schemas.query import CriticReport, ClaimVerification
from app.services.embedder import get_embedding_service
from app.services.vector_store import RetrievedChunk
from app.metrics.prometheus import CRITIC_SCORE, CRITIC_VERIFIED_CLAIMS

logger = get_logger(__name__)


# ── Critic system prompt ──────────────────────────────────────────────────────
CRITIC_SYSTEM_PROMPT = """You are a factual verification critic for a RAG system.
You will be given an AI-generated answer and the source chunks used to produce it.

Your job:
1. Split the answer into individual factual claims (one per sentence).
2. For each claim, determine if it is supported by the provided sources.
3. Assign a status: "verified", "partial", or "unverified".
4. Assign a confidence score between 0.0 and 1.0.
5. List the [SOURCE N] numbers that support each claim.

Respond ONLY with a JSON array. No extra text. Example:
[
  {
    "claim": "Transformers use self-attention mechanisms.",
    "status": "verified",
    "confidence": 0.95,
    "supporting_sources": [1, 2]
  },
  {
    "claim": "The model was trained on 100TB of data.",
    "status": "unverified",
    "confidence": 0.1,
    "supporting_sources": []
  }
]
"""

CONTRADICTION_SYSTEM_PROMPT = """You are a contradiction detector for a RAG system.
You will be given an AI-generated answer and the source chunks used to produce it.

Your job: Identify any claims in the answer that DIRECTLY CONTRADICT the sources.
A contradiction is when the answer states X but a source explicitly states NOT-X.
Absence of information is NOT a contradiction — only flag direct conflicts.

Respond ONLY with a JSON array. Empty array if no contradictions found. Example:
[
  {
    "claim": "The model was released in 2023.",
    "contradiction": "SOURCE 2 states the model was released in 2024.",
    "severity": "high"
  }
]
"""

def _token_overlap(text_a: str, text_b: str) -> float:
    """
    Computes Jaccard token overlap between two strings.
    Used for fuzzy matching contradiction claims to verified claims.
    Returns 0.0–1.0. Avoids importing heavy NLP libs.
    """
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


class CriticAgent:
    """
    Verifies the LLM-generated answer against the retrieved source chunks.

    Two-pass verification strategy:
      Pass 1 (LLM-based): Ask the LLM to verify claims against sources.
                          More accurate but slower.
      Pass 2 (embedding-based): For any claim the LLM marks as unverified,
                                compute cosine similarity between the claim
                                embedding and chunk embeddings as a fallback
                                numeric check.

    This hybrid approach catches hallucinations the LLM might miss
    while keeping latency reasonable on a local model.
    """

    def __init__(self, llm_client):
        self._llm = llm_client
        self._embedder = get_embedding_service()

    async def verify(
        self,
        db: AsyncSession,
        answer: str,
        raw_chunks: list[RetrievedChunk],
        query_log_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CriticReport:
        """
        Main verification entry point.
        Returns a CriticReport with per-claim verification status.
        """
        if not get_settings().CRITIC_ENABLED or not raw_chunks:
            return self._empty_report(answer)

        # ── Build numbered source block for the prompt ────────────────────
        source_block = self._build_source_block(raw_chunks)

        # ── Pass 1: LLM-based claim verification ──────────────────────────
        llm_claims = await self._llm_verify(answer, source_block)

        # ── Pass 2: Embedding fallback for unverified claims ──────────────
        chunk_embeddings = await self._get_chunk_embeddings(raw_chunks)
        verified_claims = await self._embedding_fallback(
            llm_claims, raw_chunks, chunk_embeddings
        )

        # ── Pass 3: Contradiction detection ───────────────────────────────
        # Runs only when critic is enabled and we have real source chunks.
        # Web results are included — contradicting a web source is still a bug.
        contradictions = await self._contradiction_check(answer, source_block)

        # Downgrade any verified claim that has a detected contradiction
        if contradictions:
            contradiction_claims = {c.get("claim", "").lower() for c in contradictions}
            for claim_dict in verified_claims:
                claim_lower = claim_dict.get("claim", "").lower()
                # Fuzzy match: if contradiction claim text overlaps significantly
                for contra in contradictions:
                    contra_claim = contra.get("claim", "").lower()
                    if (
                        claim_lower in contra_claim
                        or contra_claim in claim_lower
                        or _token_overlap(claim_lower, contra_claim) > 0.6
                    ):
                        claim_dict["status"] = "unverified"
                        claim_dict["confidence"] = min(
                            float(claim_dict.get("confidence", 0.0)) * 0.3, 0.3
                        )
                        logger.warning(
                            "critic_claim_contradicted",
                            claim=claim_dict["claim"][:80],
                            contradiction=contra.get("contradiction", "")[:80],
                        )
                        break

        # ── Map source indices back to real chunk UUIDs ───────────────────
        final_claims = self._map_sources_to_chunk_ids(verified_claims, raw_chunks)

        # ── Compute aggregate score ───────────────────────────────────────
        report = self._build_report(final_claims)

        # ── Record metrics ────────────────────────────────────────────────
        CRITIC_SCORE.observe(report.overall_score)
        CRITIC_VERIFIED_CLAIMS.labels(status="verified").inc(report.verified_count)
        CRITIC_VERIFIED_CLAIMS.labels(status="unverified").inc(report.unverified_count)
        CRITIC_VERIFIED_CLAIMS.labels(status="partial").inc(report.partial_count)

        # ── Audit log ─────────────────────────────────────────────────────
        audit = AuditLog(
            query_log_id=query_log_id,
            user_id=user_id,
            event_type="critic_result",
            payload={
                "overall_score": report.overall_score,
                "verified": report.verified_count,
                "unverified": report.unverified_count,
                "partial": report.partial_count,
                "contradictions_found": len(contradictions),
                "model": self._llm.model_name,
                "claims_count": len(final_claims),
            },
        )
        db.add(audit)

        logger.info(
            "critic_complete",
            score=report.overall_score,
            verified=report.verified_count,
            unverified=report.unverified_count,
            query_log_id=str(query_log_id),
        )
        return report

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _llm_verify(
        self, answer: str, source_block: str
    ) -> list[dict]:
        """
        Asks the LLM to split the answer into claims and verify each one.
        Returns a list of raw claim dicts from the LLM.
        Falls back to sentence-splitting if LLM response is malformed.
        """
        import json

        prompt = (
            f"SOURCES:\n{source_block}\n\n"
            f"ANSWER TO VERIFY:\n{answer}\n\n"
            "Verify each claim in the answer against the sources. "
            "Respond with JSON array only."
        )

        try:
            raw = await self._llm.generate(prompt=prompt, system=CRITIC_SYSTEM_PROMPT)
            cleaned = raw.strip().strip("```json").strip("```").strip()
            claims = json.loads(cleaned)
            if not isinstance(claims, list):
                raise ValueError("LLM critic did not return a list.")
            return claims
        except Exception as e:
            logger.warning("critic_llm_parse_failed", error=str(e))
            # Fallback: treat each sentence as an unverified claim
            return self._fallback_sentence_split(answer)

    async def _embedding_fallback(
        self,
        llm_claims: list[dict],
        raw_chunks: list[RetrievedChunk],
        chunk_embeddings: list[list[float]],
    ) -> list[dict]:
        """
        For claims the LLM marked as 'unverified' with confidence < threshold,
        compute cosine similarity between claim embedding and all chunk embeddings.
        If similarity > threshold, upgrade the claim to 'partial'.

        This catches cases where the LLM hallucinated a verdict but the
        semantic overlap is actually strong.
        """
        threshold = get_settings().CRITIC_CONFIDENCE_THRESHOLD
        enriched = []

        for claim_dict in llm_claims:
            status = claim_dict.get("status", "unverified")
            confidence = float(claim_dict.get("confidence", 0.0))

            # Only run embedding check for low-confidence claims
            if status == "unverified" and confidence < threshold:
                claim_text = claim_dict.get("claim", "")
                if claim_text:
                    claim_embedding = await self._embedder.embed_text(claim_text)
                    max_sim = max(
                        (
                            self._embedder.cosine_similarity(claim_embedding, ce)
                            for ce in chunk_embeddings
                        ),
                        default=0.0,
                    )
                    # If embedding similarity is strong, upgrade to partial
                    if max_sim >= threshold:
                        claim_dict["status"] = "partial"
                        claim_dict["confidence"] = round(max_sim * 0.8, 3)
                        logger.debug(
                            "critic_embedding_upgrade",
                            claim=claim_text[:60],
                            sim=max_sim,
                        )

            enriched.append(claim_dict)

        return enriched

    async def _contradiction_check(
        self,
        answer: str,
        source_block: str,
    ) -> list[dict]:
        """
        LLM pass that detects direct contradictions between the answer
        and source chunks.

        Unlike claim verification (which checks support), this specifically
        hunts for cases where the answer states the OPPOSITE of a source.
        Example: answer says "FastAPI uses Flask routing" but source says
        "FastAPI uses Starlette routing".

        Returns list of contradiction dicts. Empty list = no contradictions.
        Fails open — any LLM/parse error returns [] to never block the pipeline.
        """
        import json

        prompt = (
            f"SOURCES:\n{source_block}\n\n"
            f"ANSWER TO CHECK:\n{answer}\n\n"
            "List any claims in the answer that directly contradict the sources. "
            "Return empty array [] if no contradictions. JSON only."
        )

        try:
            raw = await self._llm.generate(
                prompt=prompt,
                system=CONTRADICTION_SYSTEM_PROMPT,
            )
            cleaned = raw.strip().strip("```json").strip("```").strip()
            contradictions = json.loads(cleaned)
            if not isinstance(contradictions, list):
                return []

            logger.info(
                "critic_contradiction_check",
                contradictions_found=len(contradictions),
            )
            return contradictions

        except Exception as e:
            logger.warning("critic_contradiction_check_failed", error=str(e))
            return []

    async def _get_chunk_embeddings(
        self,
        raw_chunks: list,
    ) -> list[list[float]]:
        """
        Returns embeddings for all retrieved chunks.

        Prefer stored embeddings from the chunk object (zero cost — already
        computed during ingestion). Fall back to re-embedding only for web
        results (WebResult has no stored embedding).

        This avoids a full embed_batch() call on every critic invocation,
        which was the main latency cost of the previous implementation.
        """
        embeddings = []
        texts_to_embed = []
        indices_to_embed = []

        for i, chunk in enumerate(raw_chunks):
            stored = getattr(chunk, "embedding", None)
            if stored is not None and len(stored) > 0:
                embeddings.append(stored)
            else:
                # Web result or chunk with no stored embedding — queue for batch embed
                embeddings.append(None)
                texts_to_embed.append(chunk.content)
                indices_to_embed.append(i)

        # Batch embed only the chunks that need it (typically web results only)
        if texts_to_embed:
            batch_embeddings = await self._embedder.embed_batch(texts_to_embed)
            for idx, emb in zip(indices_to_embed, batch_embeddings):
                embeddings[idx] = emb

        return embeddings

    def _map_sources_to_chunk_ids(
        self,
        claims: list[dict],
        raw_chunks: list[RetrievedChunk],
    ) -> list[ClaimVerification]:
        """
        Converts [SOURCE N] integer indices from LLM output to real chunk UUIDs.
        Source indices are 1-based in the prompt, 0-based in raw_chunks list.
        """
        result = []
        for c in claims:
            source_indices = c.get("supporting_sources", [])
            chunk_ids = []
            for idx in source_indices:
                # LLM uses 1-based indexing matching [SOURCE 1], [SOURCE 2]...
                real_idx = int(idx) - 1
                if 0 <= real_idx < len(raw_chunks):
                    chunk_ids.append(raw_chunks[real_idx].chunk_id)

            result.append(ClaimVerification(
                claim=c.get("claim", ""),
                status=c.get("status", "unverified"),
                confidence=min(max(float(c.get("confidence", 0.0)), 0.0), 1.0),
                supporting_chunk_ids=chunk_ids,
            ))
        return result

    def _build_source_block(self, raw_chunks: list[RetrievedChunk]) -> str:
        """Formats source chunks for the critic prompt."""
        lines = []
        for i, chunk in enumerate(raw_chunks, start=1):
            lines.append(f"[SOURCE {i}]\n{chunk.content[:600]}")
        return "\n\n".join(lines)

    def _build_report(self, claims: list[ClaimVerification]) -> CriticReport:
        """Aggregates per-claim results into a CriticReport."""
        if not claims:
            return CriticReport(
                overall_score=0.0,
                verified_count=0,
                unverified_count=0,
                partial_count=0,
                claims=[],
            )

        verified = sum(1 for c in claims if c.status == "verified")
        unverified = sum(1 for c in claims if c.status == "unverified")
        partial = sum(1 for c in claims if c.status == "partial")
        overall = sum(c.confidence for c in claims) / len(claims)

        return CriticReport(
            overall_score=round(overall, 4),
            verified_count=verified,
            unverified_count=unverified,
            partial_count=partial,
            claims=claims,
        )

    def _fallback_sentence_split(self, answer: str) -> list[dict]:
        """
        Splits answer into sentences and marks all as unverified.
        Used when LLM critic response is unparseable.
        """
        sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
        return [
            {
                "claim": s.strip(),
                "status": "unverified",
                "confidence": 0.0,
                "supporting_sources": [],
            }
            for s in sentences if s.strip()
        ]

    def _empty_report(self, answer: str) -> CriticReport:
        """Returns a pass-through report when critic is disabled."""
        sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
        claims = [
            ClaimVerification(
                claim=s.strip(),
                status="verified",
                confidence=1.0,
                supporting_chunk_ids=[],
            )
            for s in sentences if s.strip()
        ]
        return CriticReport(
            overall_score=1.0,
            verified_count=len(claims),
            unverified_count=0,
            partial_count=0,
            claims=claims,
        )
