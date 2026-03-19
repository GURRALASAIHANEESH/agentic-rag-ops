from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional


# ── Upload response ───────────────────────────────────────────────────────────

class DocumentUploadResponse(BaseModel):
    id: UUID
    filename: str
    file_size_bytes: int
    mime_type: str
    status: str                 # pending | processing | ready | failed
    created_at: datetime
    expires_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: UUID
    filename: str
    file_size_bytes: int
    status: str
    page_count: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    total: int


# ── Chunk schema (used in provenance viewer) ──────────────────────────────────

class ChunkSchema(BaseModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    token_count: Optional[int]
    # metadata_ aliased to "metadata" in JSON output
    metadata: dict = Field(alias="metadata_", default={})

    model_config = {"from_attributes": True, "populate_by_name": True}


# ── Ingestion status ──────────────────────────────────────────────────────────

class IngestionStatusResponse(BaseModel):
    document_id: UUID
    status: str
    chunks_created: Optional[int] = None
    error: Optional[str] = None
    message: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"pending", "processing", "ready", "failed"}
        if v not in allowed:
            raise ValueError(f"Status must be one of {allowed}")
        return v
