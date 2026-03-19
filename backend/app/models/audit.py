import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class QueryLog(Base):
    """
    Records every user query and the final answer.
    Acts as the parent record for Citations and AuditLogs.
    """
    __tablename__ = "query_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Overall critic confidence score 0.0–1.0
    critic_score: Mapped[Optional[float]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # ── Relationships ─────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User", back_populates="query_logs", lazy="noload"
    )
    citations: Mapped[list["Citation"]] = relationship(
        "Citation", back_populates="query_log", lazy="noload", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="query_log", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<QueryLog id={self.id} critic={self.critic_score}>"


class Citation(Base):
    """
    Stores per-query provenance: which chunk backed which answer,
    with similarity score and the displayed snippet.
    """
    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("query_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    # Cosine similarity between query embedding and this chunk (0.0–1.0)
    similarity: Mapped[float] = mapped_column(nullable=False)
    # Short excerpt (≤300 chars) shown in the provenance viewer
    snippet: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # ── Relationships ─────────────────────────────────────────────────────
    query_log: Mapped["QueryLog"] = relationship(
        "QueryLog", back_populates="citations", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Citation query={self.query_log_id} chunk={self.chunk_id} sim={self.similarity:.2f}>"


class AuditLog(Base):
    """
    Immutable append-only log of every agent decision in the pipeline.
    event_type values:
      - router_decision : Router chose local vs web retrieval
      - retrieval       : Vector search completed, N chunks found
      - llm_call        : LLM called with prompt, tokens used
      - critic_result   : Critic scored the answer
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_log_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("query_logs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # One of: router_decision | retrieval | llm_call | critic_result
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Full decision payload — structured for easy querying
    # Example for critic_result:
    # {"score": 0.87, "verified_claims": 3, "unverified_claims": 1, "model": "llama-3.2-3b"}
    payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    query_log: Mapped[Optional["QueryLog"]] = relationship(
        "QueryLog", back_populates="audit_logs", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<AuditLog type={self.event_type} query={self.query_log_id}>"
