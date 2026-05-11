# Deployment Guide

## Environment Variables

### Core

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | — | Yes |
| `JWT_SECRET` | Secret key for JWT token signing | — | Yes |
| `VERTEX_AI_PROJECT` | GCP project ID for Vertex AI | `w7-cloudbase` | Yes |
| `VERTEX_AI_REGION` | GCP region for Vertex AI | `europe-west4` | Yes |

### RAG Document Browser

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `RAG_DOCUMENTS_DIR` | Filesystem path where RAG documents are stored | `/data/documents` | Yes |

### Document Sync & WebSocket

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SYNC_CHECK_INTERVAL` | Interval in seconds for background sync checks | `60` | No |
| `SYNC_REINDEX_CONCURRENCY` | Max concurrent re-indexing operations | `3` | No |
| `SYNC_REINDEX_TIMEOUT` | Timeout in seconds for a single re-index operation | `300` | No |
| `WS_PING_INTERVAL` | WebSocket ping interval in seconds | `30` | No |
| `WS_MAX_CONNECTIONS_PER_USER` | Max WebSocket connections per user | `5` | No |
| `WS_MESSAGE_QUEUE_SIZE` | Max queued messages for disconnected users | `100` | No |

**Note:** The document browser reads/writes markdown files to `RAG_DOCUMENTS_DIR`. Ensure the directory exists and the application user has read/write permissions. Migrations `003_hierarchical_rag.sql` and `005_document_sync_status.sql` must be applied for full functionality.

## Docker Compose

```bash
cd w7-vertex-master && docker compose up -d
```

Services: postgres (1GB), slack-bot (1.5GB), rag-pipeline (1GB), frontend (512MB). Total memory limit: 4GB.

## Database Migrations

Apply in order:

```bash
psql $DATABASE_URL -f sql/init.sql
psql $DATABASE_URL -f sql/002_web_users.sql
psql $DATABASE_URL -f sql/003_hierarchical_rag.sql
psql $DATABASE_URL -f sql/004_ivfflat_probes.sql
psql $DATABASE_URL -f sql/005_document_sync_status.sql
```
