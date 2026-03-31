# app/models/eval.py

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EvalResult(Base):
    """
    Stores RAGAS evaluation scores per document ingestion.

    One row per synthetic question generated during post-ingestion evaluation.
    A single document ingestion produces RAGAS_SAMPLE_SIZE rows.

    Scores are floats in [0.0, 1.0]:
        faithfulness       — does the answer contain only facts from context?
        answer_relevancy   — does the answer address the question?
        context_precision  — are the retrieved chunks actually relevant?
    """
    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    # The synthetic question used for this eval sample
    question: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM-generated answer from retrieved context
    generated_answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Ground-truth context chunks used (stored for auditability)
    context_chunks: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    # RAGAS metric scores — None means scoring failed for that metric
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Metadata
    llm_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    eval_model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Raw LLM responses stored for debugging score anomalies
    raw_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        # Fast lookup: "show all eval results for this document"
        Index("ix_eval_results_document_id", "document_id"),
        # Fast lookup: "show all eval results for this workspace"
        Index("ix_eval_results_workspace_id", "workspace_id"),
        # Time-series queries: "eval scores over the last 7 days"
        Index("ix_eval_results_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvalResult doc={self.document_id} "
            f"F={self.faithfulness:.2f} "
            f"AR={self.answer_relevancy:.2f} "
            f"CP={self.context_precision:.2f}>"
        )
