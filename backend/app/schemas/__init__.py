# Re-export all schemas for clean imports elsewhere:
# from app.schemas import QueryRequest, QueryResponse, CitationSchema

from app.schemas.auth import (
    SignupRequest,
    SignupResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
    WorkspaceCreateRequest,
    WorkspaceResponse,
)

from app.schemas.document import (
    DocumentUploadResponse,
    DocumentListItem,
    DocumentListResponse,
    ChunkSchema,
    IngestionStatusResponse,
)

from app.schemas.query import (
    QueryRequest,
    QueryResponse,
    CitationSchema,
    CriticReport,
    ClaimVerification,
    StreamChunk,
)

__all__ = [
    # Auth
    "SignupRequest", "SignupResponse", "LoginRequest",
    "RefreshRequest", "TokenResponse", "UserResponse",
    "WorkspaceCreateRequest", "WorkspaceResponse",
    # Documents
    "DocumentUploadResponse", "DocumentListItem",
    "DocumentListResponse", "ChunkSchema", "IngestionStatusResponse",
    # Query
    "QueryRequest", "QueryResponse", "CitationSchema",
    "CriticReport", "ClaimVerification", "StreamChunk",
]
