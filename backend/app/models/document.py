# backend/app/models/document.py
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, event
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.database import Base

# ── Embedding dimension constant ──────────────────────────────────────────────
# Defined here as a module-level constant instead of calling get_settings() at
# class definition time. get_settings() at import time causes ValidationError in
# tests and CI where DATABASE_URL / JWT_SECRET_KEY are not yet set.
# This value MUST match EMBEDDING_DIMENSION in config.py and the pgvector index
# dimension in 001_init.sql. If you change the model, update all three.
EMBEDDING_DIMENSION = 768


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="application/pdf"
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)

    # pending | processing | ready | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Auto-expiry for data retention policy (DOCUMENT_RETENTION_DAYS in config)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    workspace: Mapped["Workspace"] = relationship(
        "Workspace", back_populates="documents", lazy="noload"
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        back_populates="document",
        lazy="select",            # CHANGED: was "noload"
        cascade="all, delete-orphan",
        passive_deletes=False,    # Force ORM to load + delete chunks explicitly
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status}>"


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # ondelete="CASCADE" ensures PostgreSQL enforces cascade at the DB level
        # as a safety net — even if the ORM cascade fires correctly, the FK
        # constraint guarantees no orphans survive a direct SQL DELETE.
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # pgvector column — EMBEDDING_DIMENSION constant avoids get_settings() at
    # import time. JSON variant used for SQLite in tests (no pgvector extension).
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    # JSONB on Postgres (indexed, fast), JSON on SQLite (tests only)
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    document: Mapped["Document"] = relationship(
        "Document", back_populates="chunks", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} doc={self.document_id} index={self.chunk_index}>"
