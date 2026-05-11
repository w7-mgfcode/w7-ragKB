-- ==============================================================================
-- Migration 002: Web Users, Refresh Tokens, Password Reset Tokens
-- ==============================================================================
-- Adds self-hosted JWT authentication tables for the React frontend,
-- decoupled from Slack user tracking.
-- ==============================================================================

-- Web users (separate from slack_users)
CREATE TABLE web_users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT,  -- NULL for OAuth-only users
    full_name     TEXT,
    avatar_url    TEXT,
    is_admin      BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_web_users_email ON web_users(email);

-- Refresh tokens
CREATE TABLE refresh_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

-- Password reset tokens
CREATE TABLE password_reset_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used       BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add web_user_id to conversations for web frontend users
ALTER TABLE conversations
    ADD COLUMN web_user_id UUID REFERENCES web_users(id);

CREATE INDEX idx_conversations_web_user ON conversations(web_user_id);
