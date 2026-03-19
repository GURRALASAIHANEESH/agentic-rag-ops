// ─────────────────────────────────────────────────────────────
// All shared TypeScript interfaces for the RAG Ops frontend.
// Import from here — never define types inline in components.
// ─────────────────────────────────────────────────────────────

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface User {
    id: string;
    email: string;
    full_name: string;
    role: "admin" | "user";
    is_active: boolean;
    created_at: string;
}

export interface TokenResponse {
    access_token: string;
    refresh_token: string;
    token_type: string;
    expires_in: number;
}

export interface SignupResponse {
    user: User;
    tokens: TokenResponse;
}

// ── Workspace ─────────────────────────────────────────────────────────────────

export interface Workspace {
    id: string;
    owner_id: string;
    name: string;
    description: string | null;
    created_at: string;
}

export type WorkspaceRole = "owner" | "editor" | "viewer";

export interface WorkspaceWithRole extends Workspace {
    role: WorkspaceRole;
}

// ── Documents ─────────────────────────────────────────────────────────────────

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";
export type MimeType = "application/pdf" | "text/plain";

export interface Document {
    id: string;
    filename: string;
    file_size_bytes: number;
    mime_type: MimeType;
    status: DocumentStatus;
    page_count: number | null;
    created_at: string;
    expires_at: string | null;
}

export interface IngestionStatus {
    document_id: string;
    status: DocumentStatus;
    chunks_created: number | null;
    error: string | null;
    message: string;
}

// ── Query & Retrieval ─────────────────────────────────────────────────────────

export interface QueryRequest {
    query: string;
    workspace_id: string;
    top_k?: number;
    stream?: boolean;
}

export interface Citation {
    chunk_id: string;
    document_id: string;
    filename: string;
    chunk_index: number;
    snippet: string;
    similarity: number;
}

export type ClaimStatus = "verified" | "partial" | "unverified";

export interface ClaimVerification {
    claim: string;
    status: ClaimStatus;
    confidence: number;
    supporting_chunk_ids: string[];
}

export interface CriticReport {
    overall_score: number;
    verified_count: number;
    unverified_count: number;
    partial_count: number;
    claims: ClaimVerification[];
}

export interface QueryResponse {
    query_log_id: string;
    query: string;
    answer: string;
    model_used: string;
    latency_ms: number;
    citations: Citation[];
    critic: CriticReport;
    created_at: string;
}

// ── SSE stream events ─────────────────────────────────────────────────────────

export type StreamEventType =
    | "token"
    | "citations"
    | "critic"
    | "clarify"
    | "done"
    | "error";

export interface StreamEvent {
    type: StreamEventType;
    data?: string | Citation[] | CriticReport | null;
    query_log_id?: string;
}

// ── Query history ─────────────────────────────────────────────────────────────

export interface QueryHistoryItem {
    id: string;
    query: string;
    answer_preview: string;
    critic_score: number | null;
    latency_ms: number | null;
    model_used: string | null;
    created_at: string;
}

export interface ProvenanceRecord {
    query_log_id: string;
    query: string;
    answer: string | null;
    critic_score: number | null;
    latency_ms: number | null;
    model_used: string | null;
    created_at: string;
    citations: Array<{
        chunk_id: string;
        similarity: number;
        snippet: string;
    }>;
    audit_trail: Array<{
        event_type: string;
        payload: Record<string, unknown>;
        timestamp: string;
    }>;
}

// ── UI state ──────────────────────────────────────────────────────────────────

export type LLMProvider = "local" | "openai" | "groq";

export interface QuerySettings {
    provider: LLMProvider;
    top_k: number;
    run_critic: boolean;
    cite_sources: boolean;
    temperature: number;
}

export type PanelState = "open" | "collapsed";

export interface StreamingState {
    isStreaming: boolean;
    tokens: string;
    citations: Citation[];
    critic: CriticReport | null;
    clarification: string | null;
    error: string | null;
    queryLogId: string | null;
    latencyMs: number | null;
}

export const INITIAL_STREAMING_STATE: StreamingState = {
    isStreaming: false,
    tokens: "",
    citations: [],
    critic: null,
    clarification: null,
    error: null,
    queryLogId: null,
    latencyMs: null,
};

// ── API errors ────────────────────────────────────────────────────────────────

export interface ApiError {
    status: number;
    detail: string | Array<{ msg: string; loc: string[] }>;
}
