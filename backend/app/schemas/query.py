from pydantic import ConfigDict, BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional


# â”€â”€ Citation / Provenance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class CitationSchema(BaseModel):
    """
    Single source chunk that backed the answer.
    Returned in every QueryResponse for provenance display.
    """
    chunk_id: UUID
    document_id: UUID
    filename: str                       # human-readable source label
    chunk_index: int
    snippet: str                        # â‰¤300 char excerpt shown in UI
    similarity: float = Field(..., ge=0.0, le=1.0)   # cosine similarity score

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# â”€â”€ Critic output â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ClaimVerification(BaseModel):
    """
    Per-claim verification produced by the Critic agent.
    The critic splits the answer into sentences/claims and
    checks each one against the retrieved chunks.
    """
    claim: str                          # the sentence/claim extracted from answer
    status: str                         # 'verified' | 'unverified' | 'partial'
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_chunk_ids: list[UUID]    # which chunks support this claim


class CriticReport(BaseModel):
    """
    Full critic output attached to every QueryResponse.
    overall_score = mean confidence across all claims.
    """
    overall_score: float = Field(..., ge=0.0, le=1.0)
    verified_count: int
    unverified_count: int
    partial_count: int
    claims: list[ClaimVerification]


# â”€â”€ Query request â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    workspace_id: UUID
    top_k: int = Field(default=5, ge=1, le=20)     # how many chunks to retrieve
    stream: bool = True                              # SSE streaming vs. single JSON

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """
        Basic prompt-injection mitigation:
        strip leading/trailing whitespace and reject
        strings that are purely special characters.
        """
        v = v.strip()
        if not any(c.isalnum() for c in v):
            raise ValueError("Query must contain at least one alphanumeric character.")
        return v


# â”€â”€ Query response â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class QueryResponse(BaseModel):
    """
    Full non-streaming response. For streaming, the final chunk
    of the SSE stream contains this as a JSON payload.
    """
    query_log_id: UUID
    query: str
    answer: str
    model_used: str
    latency_ms: int
    citations: list[CitationSchema]     # provenance sources
    critic: CriticReport                # verification map
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# â”€â”€ Streaming chunk â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class StreamChunk(BaseModel):
    """
    Individual SSE event payload during streaming.
    type values:
      - 'token'    : a partial LLM token (delta text)
      - 'citations': the provenance list (sent after all tokens)
      - 'critic'   : the critic report (sent last)
      - 'error'    : something went wrong mid-stream
      - 'done'     : stream complete, includes query_log_id
    """
    type: str
    data: str | dict | None = None
    query_log_id: Optional[UUID] = None
