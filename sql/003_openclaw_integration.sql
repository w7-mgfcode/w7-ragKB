-- ==============================================================================
-- Migration 003: OpenClaw Integration - Multi-Channel Gateway
-- ==============================================================================
-- Adds tables for multi-channel support, session management, webhooks, and
-- cron scheduling as part of the OpenClaw integration.
-- ==============================================================================

-- Channels table: stores configuration for each messaging platform
CREATE TABLE channels (
    channel_id TEXT PRIMARY KEY,  -- e.g., "slack-main", "telegram-bot1"
    channel_type TEXT NOT NULL,   -- slack, telegram, discord, whatsapp
    config JSONB NOT NULL,         -- API tokens, webhook URLs, rate limits
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_channels_type ON channels(channel_type);
CREATE INDEX idx_channels_enabled ON channels(enabled);

-- Sessions table: isolated conversation contexts
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,  -- Generated from channel + chat + thread
    channel_id TEXT NOT NULL REFERENCES channels(channel_id),
    user_id TEXT NOT NULL,        -- Platform-specific user ID
    chat_id TEXT NOT NULL,        -- DM, group, or thread identifier
    session_type TEXT NOT NULL,   -- main, group, webhook
    activation_mode TEXT DEFAULT 'mention',  -- mention, always, manual
    tool_allowlist JSONB DEFAULT '[]',
    message_count INT DEFAULT 0,
    token_usage JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ DEFAULT NOW(),
    archived_at TIMESTAMPTZ
);

CREATE INDEX idx_sessions_channel ON sessions(channel_id);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_chat ON sessions(chat_id);
CREATE INDEX idx_sessions_activity ON sessions(last_activity_at) WHERE archived_at IS NULL;
CREATE INDEX idx_sessions_type ON sessions(session_type);

-- Session messages: replaces the messages table with session isolation
CREATE TABLE session_messages (
    message_id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    role TEXT NOT NULL,           -- user, assistant, system
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',  -- Attachments, tool calls, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_session_messages_session ON session_messages(session_id);
CREATE INDEX idx_session_messages_created ON session_messages(created_at);
CREATE INDEX idx_session_messages_role ON session_messages(role);

-- Channel users: tracks users across channels with approval status
CREATE TABLE channel_users (
    channel_user_id TEXT PRIMARY KEY,  -- channel_id:user_id
    channel_id TEXT NOT NULL REFERENCES channels(channel_id),
    user_id TEXT NOT NULL,
    user_name TEXT,
    approved BOOLEAN DEFAULT FALSE,
    approval_code TEXT,
    approval_code_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel_id, user_id)
);

CREATE INDEX idx_channel_users_channel ON channel_users(channel_id);
CREATE INDEX idx_channel_users_approved ON channel_users(approved);
CREATE INDEX idx_channel_users_approval_code ON channel_users(approval_code) WHERE approval_code IS NOT NULL;

-- Webhooks: HTTP endpoints that trigger agent actions
CREATE TABLE webhooks (
    webhook_id TEXT PRIMARY KEY,
    webhook_url TEXT NOT NULL UNIQUE,
    target_session_id TEXT NOT NULL REFERENCES sessions(session_id),
    auth_token TEXT NOT NULL,
    payload_schema JSONB,
    transform_rules JSONB DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_triggered_at TIMESTAMPTZ
);

CREATE INDEX idx_webhooks_url ON webhooks(webhook_url);
CREATE INDEX idx_webhooks_target_session ON webhooks(target_session_id);
CREATE INDEX idx_webhooks_enabled ON webhooks(enabled);

-- Cron jobs: scheduled agent tasks
CREATE TABLE cron_jobs (
    cron_job_id TEXT PRIMARY KEY,
    schedule TEXT NOT NULL,       -- Cron expression
    target_session_id TEXT NOT NULL REFERENCES sessions(session_id),
    message_template TEXT NOT NULL,
    timezone TEXT DEFAULT 'UTC',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_executed_at TIMESTAMPTZ,
    next_execution_at TIMESTAMPTZ
);

CREATE INDEX idx_cron_jobs_next_execution ON cron_jobs(next_execution_at) WHERE enabled = TRUE;
CREATE INDEX idx_cron_jobs_target_session ON cron_jobs(target_session_id);
CREATE INDEX idx_cron_jobs_enabled ON cron_jobs(enabled);

-- ==============================================================================
-- FUNCTIONS
-- ==============================================================================

-- Auto-update updated_at on channels changes
CREATE OR REPLACE FUNCTION update_channels_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Auto-update last_activity_at on session_messages insert
CREATE OR REPLACE FUNCTION update_session_activity()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE sessions
    SET last_activity_at = NOW(),
        message_count = message_count + 1
    WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==============================================================================
-- TRIGGERS
-- ==============================================================================

CREATE TRIGGER update_channels_updated_at
    BEFORE UPDATE ON channels
    FOR EACH ROW
    EXECUTE FUNCTION update_channels_updated_at();

CREATE TRIGGER update_session_activity
    AFTER INSERT ON session_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_session_activity();

-- ==============================================================================
-- SETUP COMPLETE
-- ==============================================================================
-- Created:
--   Tables:  channels, sessions, session_messages, channel_users, webhooks, cron_jobs
--   Indexes: Performance indexes for routing, lookup, and filtering
--   Functions: Auto-update triggers for timestamps and activity tracking
--   Triggers: Automatic maintenance of updated_at and last_activity_at
-- ==============================================================================
