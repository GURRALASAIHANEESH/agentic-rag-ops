# app/services/evaluator.py

from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.eval import EvalResult
from app.services.vector_store import RetrievedChunk, get_vector_store

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal DTOs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _EvalSample:
    """One synthetic QA triplet used for RAGAS scoring."""
    question: str
    generated_answer: str
    context_chunks: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# Evaluator Service
# ─────────────────────────────────────────────────────────────────────────────

class EvaluatorService:
    """
    Post-ingestion RAGAS evaluation pipeline.

    Flow per document:
        1. Sample RAGAS_SAMPLE_SIZE chunks from the freshly ingested document
        2. For each chunk: generate a synthetic question via LLM
        3. Retrieve context for that question via vector search
        4. Generate an answer from retrieved context via LLM
        5. Score: faithfulness, answer_relevancy, context_precision
        6. Persist EvalResult rows to eval_results table

    All LLM calls are sequential with asyncio.sleep(0.5) between them
    to respect Groq free tier limits (30 req/min).
    """

    def __init__(self) -> None:
        self._vector_store = get_vector_store()

    async def evaluate_document(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> list[EvalResult]:
        """
        Entry point. Runs the full evaluation pipeline for one document.
        Returns persisted EvalResult rows (empty list if RAGAS disabled or failed).
        """
        cfg = get_settings()

        if not cfg.RAGAS_ENABLED:
            logger.info("evaluator.disabled", document_id=str(document_id))
            return []

        log = logger.bind(
            document_id=str(document_id),
            workspace_id=str(workspace_id),
            sample_size=cfg.RAGAS_SAMPLE_SIZE,
        )
        log.info("evaluator.start")

        try:
            # Step 1 — Sample source chunks from this document
            source_chunks = await self._sample_chunks(
                db=db,
                document_id=document_id,
                workspace_id=workspace_id,
                n=cfg.RAGAS_SAMPLE_SIZE,
            )

            if not source_chunks:
                log.warning("evaluator.no_chunks_to_sample")
                return []

            # Steps 2–5 — Generate QA pairs and score them (sequential, Groq-safe)
            eval_rows: list[EvalResult] = []

            for i, chunk in enumerate(source_chunks):
                log.info("evaluator.processing_sample", sample_index=i + 1)

                row = await self._evaluate_single(
                    db=db,
                    source_chunk=chunk,
                    document_id=document_id,
                    workspace_id=workspace_id,
                )
                if row is not None:
                    eval_rows.append(row)

                # Groq free tier: 30 req/min — each sample makes 2 LLM calls
                # 500ms between samples keeps us well under the limit
                if i < len(source_chunks) - 1:
                    await asyncio.sleep(0.5)

            # Step 6 — Persist all rows
            if eval_rows:
                db.add_all(eval_rows)
                await db.commit()

            log.info(
                "evaluator.complete",
                rows_saved=len(eval_rows),
                avg_faithfulness=_safe_avg([r.faithfulness for r in eval_rows]),
                avg_relevancy=_safe_avg([r.answer_relevancy for r in eval_rows]),
                avg_precision=_safe_avg([r.context_precision for r in eval_rows]),
            )
            return eval_rows

        except Exception as exc:
            log.error(
                "evaluator.pipeline_failed",
                error=str(exc),
            )
            # Evaluation failure must NEVER affect ingestion status
            return []

    # ── Chunk sampling ────────────────────────────────────────────────────────

    async def _sample_chunks(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        workspace_id: uuid.UUID,
        n: int,
    ) -> list[RetrievedChunk]:
        """
        Fetches chunks for this document and randomly samples n of them.
        Filters out chunks that are too short to generate meaningful questions.
        """
        from sqlalchemy import select
        from app.models.document import Chunk

        cfg = get_settings()

        result = await db.execute(
            select(Chunk).where(
                Chunk.document_id == document_id,
                Chunk.workspace_id == workspace_id,
            )
        )
        all_chunks = result.scalars().all()

        # Filter: skip micro-chunks that can't anchor a real question
        eligible = [
            c for c in all_chunks
            if len(c.content.split()) >= cfg.RAGAS_MIN_CHUNK_WORDS
        ]

        if not eligible:
            return []

        sampled = random.sample(eligible, min(n, len(eligible)))

        # Convert ORM Chunk → RetrievedChunk for uniform downstream handling
        return [
            RetrievedChunk(
                chunk_id=str(c.id),
                document_id=str(c.document_id),
                workspace_id=str(c.workspace_id),
                content=c.content,
                chunk_index=c.chunk_index,
                similarity=1.0,       # source chunk — perfect relevance by definition
                metadata=c.metadata_ or {},
            )
            for c in sampled
        ]

    # ── Single sample evaluation ──────────────────────────────────────────────

    async def _evaluate_single(
        self,
        db: AsyncSession,
        source_chunk: RetrievedChunk,
        document_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> EvalResult | None:
        """
        Runs the full eval cycle for one source chunk:
            generate question → retrieve context → generate answer → score
        """
        cfg = get_settings()

        from app.services.llm_client import get_llm_client
        from app.services.embedder import get_embedding_service

        llm = get_llm_client()
        embedder = get_embedding_service()

        try:
            # ── Step 2: Generate synthetic question ───────────────────────
            question = await self._generate_question(
                llm=llm, chunk_content=source_chunk.content
            )
            if not question:
                return None

            # ── Step 3: Retrieve context for the question ─────────────────
            query_embedding = await embedder.embed_text(question)
            context_chunks = await self._vector_store.search(
                db=db,
                query_embedding=query_embedding,
                workspace_id=workspace_id,
                top_k=5,
                min_similarity=0.05,
            )

            if not context_chunks:
                return None

            context_texts: list[str] = [c.content for c in context_chunks]
            context_block = "\n\n".join(
                f"[SOURCE {i+1}] {text}"
                for i, text in enumerate(context_texts)
            )

            # ── Step 4: Generate answer from context ──────────────────────
            # 500ms sleep between question gen and answer gen (Groq rate limit)
            await asyncio.sleep(0.5)
            generated_answer = await self._generate_answer(
                llm=llm,
                question=question,
                context_block=context_block,
            )
            if not generated_answer:
                return None

            # ── Step 5: Score the triplet ─────────────────────────────────
            scores = self._score(
                question=question,
                answer=generated_answer,
                context_texts=context_texts,
                source_content=source_chunk.content,
            )

            return EvalResult(
                id=uuid.uuid4(),
                document_id=document_id,
                workspace_id=workspace_id,
                question=question,
                generated_answer=generated_answer,
                context_chunks=context_texts,
                faithfulness=scores["faithfulness"],
                answer_relevancy=scores["answer_relevancy"],
                context_precision=scores["context_precision"],
                llm_provider=cfg.LLM_PROVIDER,
                eval_model=cfg.GROQ_MODEL,
                raw_scores=scores,
            )

        except Exception as exc:
            logger.warning(
                "evaluator.sample_failed",
                document_id=str(document_id),
                error=str(exc),
            )
            return None

    # ── LLM prompts ───────────────────────────────────────────────────────────

    async def _generate_question(self, llm: object, chunk_content: str) -> str | None:
        """Generates one specific, answerable question from a chunk."""
        prompt = f"""You are evaluating a RAG system. Given the following text chunk, 
generate exactly one specific question that can be answered using ONLY the information in this chunk.
The question must be answerable from the chunk alone — no external knowledge required.
Respond with only the question. No explanation, no numbering, no quotes.

Chunk:
{chunk_content[:1000]}

Question:"""
        try:
            response: str = await llm.generate(prompt=prompt)
            cleaned = response.strip().strip('"').strip("'")
            return cleaned if len(cleaned) > 10 else None
        except Exception as exc:
            logger.warning("evaluator.question_gen_failed", error=str(exc))
            return None

    async def _generate_answer(
        self, llm: object, question: str, context_block: str
    ) -> str | None:
        """Generates an answer strictly grounded in the provided context."""
        prompt = f"""Answer the following question using ONLY the provided context.
If the context does not contain enough information, respond: "I could not find this in the provided context."
Be concise — 1–3 sentences maximum.

Context:
{context_block[:2000]}

Question: {question}

Answer:"""
        try:
            response: str = await llm.generate(prompt=prompt)
            return response.strip() if response.strip() else None
        except Exception as exc:
            logger.warning("evaluator.answer_gen_failed", error=str(exc))
            return None

    # ── RAGAS-style scoring ───────────────────────────────────────────────────

    def _score(
        self,
        question: str,
        answer: str,
        context_texts: list[str],
        source_content: str,
    ) -> dict[str, float]:
        """
        Lightweight RAGAS-style scoring without the heavy ragas library.
        Uses word-overlap heuristics — production-grade approximations that
        avoid additional LLM calls and run synchronously.

        Faithfulness:
            Fraction of answer sentences that overlap with any context chunk.
            Proxy: "does the answer stay within the source material?"

        Answer Relevancy:
            Jaccard similarity between question tokens and answer tokens.
            Proxy: "does the answer address what was asked?"

        Context Precision:
            Fraction of retrieved chunks that overlap with the source chunk.
            Proxy: "did we retrieve the right chunks?"
        """
        answer_lower = answer.lower()
        question_tokens = set(question.lower().split())
        answer_tokens = set(answer_lower.split())
        context_combined = " ".join(context_texts).lower()
        source_tokens = set(source_content.lower().split())

        # ── Faithfulness ──────────────────────────────────────────────────
        # Split answer into sentences, check each against context
        sentences = [s.strip() for s in answer_lower.replace("?", ".").split(".") if len(s.strip()) > 5]
        if sentences:
            grounded = sum(
                1 for s in sentences
                if any(word in context_combined for word in s.split() if len(word) > 4)
            )
            faithfulness = round(grounded / len(sentences), 4)
        else:
            faithfulness = 0.0

        # ── Answer Relevancy ──────────────────────────────────────────────
        # Jaccard similarity: question ∩ answer / question ∪ answer
        # Filter stopwords via length proxy (words > 3 chars carry meaning)
        q_meaningful = {t for t in question_tokens if len(t) > 3}
        a_meaningful = {t for t in answer_tokens if len(t) > 3}
        if q_meaningful | a_meaningful:
            answer_relevancy = round(
                len(q_meaningful & a_meaningful) / len(q_meaningful | a_meaningful), 4
            )
        else:
            answer_relevancy = 0.0

        # ── Context Precision ─────────────────────────────────────────────
        # What fraction of retrieved chunks overlap with the source chunk?
        if context_texts:
            precise = sum(
                1 for ctx in context_texts
                if len(source_tokens & set(ctx.lower().split())) > 5
            )
            context_precision = round(precise / len(context_texts), 4)
        else:
            context_precision = 0.0

        return {
            "faithfulness":        faithfulness,
            "answer_relevancy":    answer_relevancy,
            "context_precision":   context_precision,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_avg(values: list[float | None]) -> float | None:
    """Returns average of non-None values, or None if all are None."""
    valid = [v for v in values if v is not None]
    return round(sum(valid) / len(valid), 4) if valid else None
