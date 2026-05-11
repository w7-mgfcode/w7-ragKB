-- Tool access log table for security auditing
-- This table tracks all tool access attempts (both allowed and blocked)
-- for security monitoring and policy refinement

CREATE TABLE IF NOT EXISTS tool_access_log (
    log_id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    user_id TEXT,
    channel_id TEXT,
    access_granted BOOLEAN NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_tool_access_log_session ON tool_access_log(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_access_log_timestamp ON tool_access_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_tool_access_log_blocked ON tool_access_log(access_granted) WHERE access_granted = FALSE;
CREATE INDEX IF NOT EXISTS idx_tool_access_log_tool ON tool_access_log(tool_name);

-- Add tool_denylist column to sessions table if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sessions' AND column_name = 'tool_denylist'
    ) THEN
        ALTER TABLE sessions ADD COLUMN tool_denylist JSONB DEFAULT '[]';
    END IF;
END $$;

COMMENT ON TABLE tool_access_log IS 'Audit log for tool access attempts (both allowed and blocked)';
COMMENT ON COLUMN tool_access_log.session_id IS 'Session identifier';
COMMENT ON COLUMN tool_access_log.tool_name IS 'Name of the tool that was accessed or blocked';
COMMENT ON COLUMN tool_access_log.user_id IS 'Platform-specific user ID';
COMMENT ON COLUMN tool_access_log.channel_id IS 'Channel identifier';
COMMENT ON COLUMN tool_access_log.access_granted IS 'Whether the tool access was granted (true) or blocked (false)';
COMMENT ON COLUMN tool_access_log.timestamp IS 'When the access attempt occurred';
COMMENT ON COLUMN tool_access_log.metadata IS 'Additional metadata about the access attempt';
