-- ==============================================================================
-- w7-ragKB AI Agent Database Schema — PostgreSQL 16 + pgvector
-- ==============================================================================
-- Self-hosted schema for the Vertex AI refactor.
-- All Supabase-specific constructs (RLS, auth.uid(), auth.users FK,
-- Supabase triggers) have been removed.
-- Vector dimension is 768 for Vertex AI gemini-embedding-001.
-- ==============================================================================

-- Enable the pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- ==============================================================================
-- TABLES
-- ==============================================================================

-- Slack user tracking (replaces Supabase-linked user_profiles)
CREATE TABLE slack_users (
    slack_id    TEXT PRIMARY KEY,
    display_name TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Conversations keyed by Slack channel/thread
CREATE TABLE conversations (
    session_id       TEXT PRIMARY KEY,
    slack_user_id    TEXT NOT NULL REFERENCES slack_users(slack_id),
    slack_channel_id TEXT NOT NULL,
    title            TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    last_message_at  TIMESTAMPTZ DEFAULT NOW(),
    is_archived      BOOLEAN DEFAULT FALSE
);

-- Messages (no computed_session_user_id — Supabase auth removed)
CREATE TABLE messages (
    id           SERIAL PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES conversations(session_id),
    message      JSONB NOT NULL,
    message_data TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Document metadata
CREATE TABLE document_metadata (
    id         TEXT PRIMARY KEY,
    title      TEXT,
    url        TEXT,
    schema     TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Document rows (tabular data)
CREATE TABLE document_rows (
    id         SERIAL PRIMARY KEY,
    dataset_id TEXT REFERENCES document_metadata(id),
    row_data   JSONB
);

-- Documents with vector embeddings (768d for Vertex AI gemini-embedding-001)
CREATE TABLE documents (
    id        BIGSERIAL PRIMARY KEY,
    content   TEXT,
    metadata  JSONB,
    embedding vector(768)
);

-- RAG pipeline state
CREATE TABLE rag_pipeline_state (
    pipeline_id    TEXT PRIMARY KEY,
    pipeline_type  TEXT NOT NULL,
    last_check_time TIMESTAMPTZ,
    known_files    JSONB,
    last_run       TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ==============================================================================
-- INDEXES
-- ==============================================================================

CREATE INDEX idx_conversations_slack_user ON conversations(slack_user_id);
CREATE INDEX idx_conversations_channel    ON conversations(slack_channel_id);
CREATE INDEX idx_messages_session         ON messages(session_id);
CREATE INDEX idx_rag_pipeline_state_type  ON rag_pipeline_state(pipeline_type);

-- IVFFlat index for fast vector similarity search (cosine distance)
CREATE INDEX idx_documents_embedding ON documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ==============================================================================
-- FUNCTIONS
-- ==============================================================================

-- Vector similarity search function (768d for Vertex AI gemini-embedding-001)
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(768),
    match_count     INT  DEFAULT 4,
    filter          JSONB DEFAULT '{}'
)
RETURNS TABLE (
    id         BIGINT,
    content    TEXT,
    metadata   JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Improve IVFFlat recall and avoid empty result sets on valid queries.
    PERFORM set_config('ivfflat.probes', '20', true);

    RETURN QUERY
    SELECT
        d.id,
        d.content,
        d.metadata,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM documents d
    WHERE d.metadata @> filter
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Auto-update updated_at on rag_pipeline_state changes
CREATE OR REPLACE FUNCTION update_rag_pipeline_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==============================================================================
-- TRIGGERS
-- ==============================================================================

CREATE TRIGGER update_rag_pipeline_state_updated_at
    BEFORE UPDATE ON rag_pipeline_state
    FOR EACH ROW
    EXECUTE FUNCTION update_rag_pipeline_state_updated_at();

-- ==============================================================================
-- SETUP COMPLETE
-- ==============================================================================
-- Created:
--   Tables:  slack_users, conversations, messages, document_metadata,
--            document_rows, documents, rag_pipeline_state
--   Indexes: conversation lookups, message session, pipeline type,
--            IVFFlat vector similarity (cosine, 100 lists)
--   Functions: match_documents (768d), update_rag_pipeline_state_updated_at
--   Triggers: auto-update updated_at on rag_pipeline_state
--
-- Removed from original schema:
--   - user_profiles table (replaced by slack_users)
--   - requests table (rate limiting is now in-memory)
--   - All RLS policies
--   - auth.uid() / auth.users references
--   - Supabase triggers (on_auth_user_created)
--   - handle_new_user(), is_admin(), execute_custom_sql() functions
--   - computed_session_user_id column from messages
-- ==============================================================================
