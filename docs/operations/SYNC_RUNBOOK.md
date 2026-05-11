# Document Sync Operations Runbook

## Sync Status Overview

| Status | Meaning | Action |
|--------|---------|--------|
| `in_sync` | Filesystem file matches database chunks | None — healthy state |
| `out_of_sync` | File modified after last indexing | Trigger re-index |
| `processing` | Currently being re-indexed | Wait for completion |
| `error` | Indexing failed | Check error_message, fix root cause, re-index |
| `orphaned_chunks` | Database chunks exist but file is missing | Clean up chunks or restore file |
| `pending_indexing` | File exists but no database chunks | Trigger re-index |

## Troubleshooting Common Issues

### Document stuck in `processing`

A document may remain in `processing` if a re-index task crashed mid-operation.

```sql
-- Check how long it's been stuck
SELECT file_path, updated_at, last_checked
FROM document_sync_status
WHERE sync_status = 'processing'
AND updated_at < NOW() - INTERVAL '10 minutes';

-- Force to error state for manual retry
UPDATE document_sync_status
SET sync_status = 'error', error_message = 'Manually reset from stuck processing state'
WHERE file_path = '<path>' AND sync_status = 'processing';
```

Then trigger a manual re-index (see below).

### Document stuck in `error`

```sql
-- View error details
SELECT file_path, error_message, updated_at
FROM document_sync_status
WHERE sync_status = 'error'
ORDER BY updated_at DESC;
```

Common causes:
- **Embedding API failure**: Check Vertex AI quotas and service status
- **File encoding issue**: Ensure file is valid UTF-8
- **Database connection pool exhaustion**: Check pool metrics
- **Timeout**: File too large or Vertex AI slow — check `SYNC_REINDEX_TIMEOUT`

Fix the root cause, then re-index:
```bash
curl -X POST http://localhost:8000/api/documents/reindex/<path> \
  -H "Authorization: Bearer <token>"
```

### Orphaned chunks (`orphaned_chunks`)

Database chunks exist but the source file was deleted from the filesystem.

```sql
-- List orphaned documents
SELECT file_path, chunk_count, updated_at
FROM document_sync_status
WHERE sync_status = 'orphaned_chunks';

-- Clean up orphaned chunks
DELETE FROM documents WHERE metadata->>'file_path' = '<path>';
DELETE FROM document_sync_status WHERE file_path = '<path>';
```

### Pending indexing (`pending_indexing`)

File exists on disk but has never been indexed.

```bash
# Re-index a single document
curl -X POST http://localhost:8000/api/documents/reindex/<path> \
  -H "Authorization: Bearer <token>"

# Re-index an entire directory
curl -X POST http://localhost:8000/api/documents/reindex-directory/<dir_path> \
  -H "Authorization: Bearer <token>"
```

## Manual Operations

### Check sync status

```bash
# All documents
curl http://localhost:8000/api/documents/sync-status \
  -H "Authorization: Bearer <token>"

# Single document
curl http://localhost:8000/api/documents/sync-status/<path> \
  -H "Authorization: Bearer <token>"
```

### Re-index operations

```bash
# Single document
curl -X POST http://localhost:8000/api/documents/reindex/<path> \
  -H "Authorization: Bearer <token>"

# Directory (recursive)
curl -X POST http://localhost:8000/api/documents/reindex-directory/<dir_path> \
  -H "Authorization: Bearer <token>"

# Full re-index (all documents)
curl -X POST http://localhost:8000/api/documents/reindex-all \
  -H "Authorization: Bearer <token>"
```

### Direct database queries

```sql
-- Sync status distribution
SELECT sync_status, COUNT(*), source
FROM document_sync_status
GROUP BY sync_status, source
ORDER BY COUNT(*) DESC;

-- Documents with errors
SELECT file_path, error_message, updated_at
FROM document_sync_status
WHERE sync_status = 'error'
ORDER BY updated_at DESC
LIMIT 20;

-- Chunk count per document
SELECT metadata->>'file_path' as path,
       COUNT(*) as chunks,
       array_agg(DISTINCT chunk_level) as levels
FROM documents
WHERE metadata->>'file_path' IS NOT NULL
GROUP BY metadata->>'file_path'
ORDER BY chunks DESC
LIMIT 20;
```

## Conflict Resolution

When a conflict is detected (file modified on disk while being edited in browser):

```bash
# Check conflict details
curl http://localhost:8000/api/documents/sync-status/<path> \
  -H "Authorization: Bearer <token>"

# Resolve: keep filesystem version
curl -X POST http://localhost:8000/api/documents/resolve-conflict/<path> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"strategy": "keep_filesystem"}'

# Resolve: keep database version
curl -X POST http://localhost:8000/api/documents/resolve-conflict/<path> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"strategy": "keep_database"}'

# Resolve: manual merge
curl -X POST http://localhost:8000/api/documents/resolve-conflict/<path> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"strategy": "manual_merge", "merged_content": "# Merged content here..."}'
```

## Rollback Procedures

### Document rollback

The SyncManager creates backup files during operations:
- Update: `.md.bak` (renamed back on failure)
- Delete: `.md.deleted` (renamed back on failure)

If backups remain after a crash:
```bash
# Check for leftover backups
find /rag-documents -name "*.bak" -o -name "*.deleted"

# Restore a backup manually
mv /rag-documents/path/to/doc.md.bak /rag-documents/path/to/doc.md
```

### Database rollback

Chunks are regenerated from the filesystem on re-index. The filesystem is the source of truth.

```bash
# Re-index to regenerate database chunks from filesystem
curl -X POST http://localhost:8000/api/documents/reindex/<path> \
  -H "Authorization: Bearer <token>"
```

## Monitoring

### Key metrics (via System Monitor)

- `reindex_count` / `reindex_errors` — re-index success rate
- `reindex_avg_time_ms` — average re-index duration
- `ws_connections` — active WebSocket connections
- `ws_messages_sent` — total WebSocket messages broadcast
- `sync_status_updates` — total sync status transitions

### Alert thresholds (recommended)

| Metric | Warning | Critical |
|--------|---------|----------|
| Error documents | > 5 | > 10 |
| Orphaned chunks | > 3 | > 10 |
| Stuck processing (> 10 min) | > 1 | > 3 |
| Reindex queue depth | > 10 | > 20 |
| WebSocket disconnections/min | > 5 | > 15 |

### Health check query

```sql
SELECT
  COUNT(*) FILTER (WHERE sync_status = 'in_sync') as in_sync,
  COUNT(*) FILTER (WHERE sync_status = 'error') as errors,
  COUNT(*) FILTER (WHERE sync_status = 'processing' AND updated_at < NOW() - INTERVAL '10 minutes') as stuck,
  COUNT(*) FILTER (WHERE sync_status = 'orphaned_chunks') as orphaned,
  COUNT(*) FILTER (WHERE sync_status = 'pending_indexing') as pending
FROM document_sync_status;
```

## Environment Variables

See [Deployment Guide](DEPLOYMENT.md) for full list. Key sync-related variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_CHECK_INTERVAL` | `60` | Seconds between sync checks |
| `SYNC_REINDEX_CONCURRENCY` | `3` | Max concurrent re-index operations |
| `SYNC_REINDEX_TIMEOUT` | `300` | Seconds before re-index times out |
| `SYNC_EMBEDDING_BATCH_SIZE` | `10` | Texts per embedding API call |
| `WS_PING_INTERVAL` | `30` | WebSocket keepalive interval (seconds) |
| `WS_MAX_CONNECTIONS_PER_USER` | `5` | Max WebSocket connections per user |
| `WS_MESSAGE_QUEUE_SIZE` | `100` | Max missed messages queued per user |
| `WATCHER_MAX_CONCURRENT_FILES` | `3` | Max files processed concurrently by watcher |
