-- ==============================================================================
-- Document Sync Status Tracking
-- ==============================================================================
-- Tracks synchronization state between the filesystem (./rag-documents) and
-- the database (documents table). Enables the Document Browser to show which
-- documents are in sync, out of sync, processing, or in error state.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS document_sync_status (
    file_path       TEXT PRIMARY KEY,
    sync_status     TEXT NOT NULL DEFAULT 'pending_indexing'
                    CHECK (sync_status IN (
                        'in_sync', 'out_of_sync', 'processing',
                        'error', 'orphaned_chunks', 'pending_indexing'
                    )),
    filesystem_mtime TIMESTAMPTZ,
    database_mtime   TIMESTAMPTZ,
    chunk_count      INTEGER DEFAULT 0,
    error_message    TEXT,
    source           TEXT NOT NULL DEFAULT 'filesystem'
                     CHECK (source IN ('filesystem', 'browser')),
    last_checked     TIMESTAMPTZ DEFAULT NOW(),
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_doc_sync_status
    ON document_sync_status(sync_status);

CREATE INDEX IF NOT EXISTS idx_doc_sync_source
    ON document_sync_status(source);

CREATE INDEX IF NOT EXISTS idx_doc_sync_updated
    ON document_sync_status(updated_at);

-- Auto-update updated_at on row modification
CREATE OR REPLACE FUNCTION update_document_sync_status_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_document_sync_status_updated_at
    ON document_sync_status;

CREATE TRIGGER trg_document_sync_status_updated_at
    BEFORE UPDATE ON document_sync_status
    FOR EACH ROW
    EXECUTE FUNCTION update_document_sync_status_updated_at();

-- ==============================================================================
-- SETUP COMPLETE
-- ==============================================================================
-- Created:
--   Table:    document_sync_status (file_path PK, sync_status, mtimes, etc.)
--   Indexes:  sync_status, source, updated_at
--   Trigger:  auto-update updated_at on modification
-- ==============================================================================
