-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────
-- USERS & AUTH
-- ─────────────────────────────────────────
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT NOT NULL UNIQUE,
    full_name   TEXT NOT NULL,
    hashed_password TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'user',   -- 'admin' | 'user'
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);

-- ─────────────────────────────────────────
-- WORKSPACES (per-user isolation)
-- ─────────────────────────────────────────
CREATE TABLE workspaces (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_workspaces_owner ON workspaces(owner_id);

-- ─────────────────────────────────────────
-- DOCUMENTS
-- ─────────────────────────────────────────
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    mime_type       TEXT NOT NULL DEFAULT 'application/pdf',
    storage_path    TEXT NOT NULL,              -- local path or S3 key
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | ready | failed
    page_count      INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days')  -- auto-retention policy
);

CREATE INDEX idx_documents_workspace ON documents(workspace_id);
CREATE INDEX idx_documents_status    ON documents(status);

-- ─────────────────────────────────────────
-- CHUNKS (pgvector embeddings live here)
-- ─────────────────────────────────────────
CREATE TABLE chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,           -- order within document
    content         TEXT NOT NULL,              -- raw text of this chunk
    token_count     INTEGER,
    -- 384-dim vector for all-MiniLM-L6-v2 (free, fast, runs on CPU)
    -- Change to 768 if switching to a larger embedding model
    embedding       vector(384),
    metadata        JSONB DEFAULT '{}',         -- page_num, section, etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chunks_document    ON chunks(document_id);
CREATE INDEX idx_chunks_workspace   ON chunks(workspace_id);

-- pgvector IVFFlat index for fast ANN search
-- NOTE: Run AFTER ingesting at least a few hundred chunks for best results.
-- lists=100 is a safe default for up to ~1M vectors.
CREATE INDEX idx_chunks_embedding ON chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ─────────────────────────────────────────
-- QUERY HISTORY
-- ─────────────────────────────────────────
CREATE TABLE query_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    query_text      TEXT NOT NULL,
    answer_text     TEXT,
    latency_ms      INTEGER,
    model_used      TEXT,
    critic_score    FLOAT,                      -- overall confidence 0.0–1.0
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_query_logs_user      ON query_logs(user_id);
CREATE INDEX idx_query_logs_workspace ON query_logs(workspace_id);

-- ─────────────────────────────────────────
-- CITATIONS (provenance per query)
-- ─────────────────────────────────────────
CREATE TABLE citations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_log_id    UUID NOT NULL REFERENCES query_logs(id) ON DELETE CASCADE,
    chunk_id        UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    similarity      FLOAT NOT NULL,             -- cosine similarity score
    snippet         TEXT NOT NULL,              -- excerpt shown to user
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_citations_query ON citations(query_log_id);

-- ─────────────────────────────────────────
-- AUDIT LOG (every agent decision)
-- ─────────────────────────────────────────
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_log_id    UUID REFERENCES query_logs(id) ON DELETE SET NULL,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,   -- 'router_decision' | 'retrieval' | 'llm_call' | 'critic_result'
    payload         JSONB NOT NULL DEFAULT '{}',  -- full decision details
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_query   ON audit_logs(query_log_id);
CREATE INDEX idx_audit_event   ON audit_logs(event_type);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
