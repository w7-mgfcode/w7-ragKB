# w7-ragKB — Agent API Service

Slack bot + AI agent + FastAPI auth/data/chat API, powered by Google Vertex AI Gemini. Runs as a single container serving both Slack Socket Mode (for the conversational agent) and a FastAPI HTTP server (for web frontend auth, data, chat, and admin endpoints) via `asyncio.gather` with graceful shutdown support.

## Agent Capabilities

- **Agentic RAG**: Query documents with context-aware retrieval (local files or Google Drive)
- **Long-term Memory**: Persistent memory across conversations via Mem0
- **Web Search**: Brave API or SearXNG
- **Image Analysis**: Gemini vision models
- **Code Execution**: Sandboxed Python execution
- **Conversation Management**: Full history stored in PostgreSQL

## Architecture

```
┌─────────────────────────────────────────────┐
│              slack-bot container             │
│                                             │
│  main.py ─── asyncio.gather ───┐            │
│       │                        │            │
│  Slack Socket Mode        FastAPI :8000     │
│  (slack_bot.py)           (http_server.py)  │
│       │                        │            │
│  Pydantic AI Agent        Auth / Data /     │
│  (agent.py + tools.py)    Chat / Admin /    │
│       │                   Monitor / Docs    │
│  Vertex AI Gemini         (auth_router.py,  │
│  (vertex_provider.py)      data_router.py,  │
│       │                    chat_router.py,  │
│  PostgreSQL 16 + pgvector  admin_router.py, │
│  (db.py, asyncpg)          monitor_router.py,│
│                            documents_router.py)│
│                                │            │
│                           JWT Auth          │
│                           (token_manager.py) │
│  Graceful shutdown via shared asyncio.Event │
└─────────────────────────────────────────────┘
```

## Project Structure

```
backend_agent_api/
├── main.py                 # Entry point — starts Slack + FastAPI concurrently
├── agent.py                # Pydantic AI agent definition and tools
├── slack_bot.py            # Slack Bolt async app with Socket Mode
├── http_server.py          # FastAPI app factory + uvicorn runner
├── vertex_provider.py      # Vertex AI Gemini model factory
├── vertex_embeddings.py    # Vertex AI embedding client
├── db.py                   # asyncpg connection pool management
├── db_conversations.py     # Conversation/message DB queries
├── db_documents.py         # Document/RAG DB queries
├── db_web_users.py         # Web user account DB queries
├── token_manager.py        # JWT access/refresh token creation and validation
├── rate_limiter.py         # Login rate limiting (in-memory)
├── auth_middleware.py      # FastAPI dependency for JWT-protected routes
├── auth_router.py          # Auth endpoints (register, login, refresh, OAuth)
├── chat_router.py          # POST /api/agent — frontend chat endpoint
├── data_router.py          # Conversation data endpoints for the frontend
├── admin_router.py         # Admin endpoints (status, user management, conversations)
├── documents_router.py     # Document CRUD, search, sync, reindex, conflict resolution, WebSocket (22 endpoints)
├── sync_manager.py         # Document sync between filesystem and DB (atomic CRUD, reindex, conflict resolution)
├── websocket_manager.py    # WebSocket connection tracking, broadcast, missed message queue
├── document_exceptions.py  # Document-specific exception hierarchy
├── monitor_router.py       # System monitor endpoints (health, metrics, logs, resources)
├── metrics_collector.py    # In-process API metrics + psutil system resource readings
├── log_buffer.py           # Circular log buffer (logging.Handler backed by deque)
├── tools.py                # Agent tool implementations (RAG, web search, etc.)
├── prompt.py               # System prompt template
├── Dockerfile
├── requirements.txt
└── tests/
    ├── conftest.py
    ├── test_agent.py
    ├── test_auth_router.py
    ├── test_auth_middleware.py
    ├── test_data_router.py
    ├── test_admin_router.py
    ├── test_monitor_router.py          # Unit tests for system monitor endpoints
    ├── test_db_*.py
    ├── test_token_manager.py
    ├── test_rate_limiter.py
    ├── test_slack_bot.py
    ├── test_tools.py
    ├── test_vertex_provider.py
    ├── test_vertex_embeddings.py
    ├── test_pbt_metrics_collector.py   # PBT: API metrics counting (P9), resource invariants (P7)
    ├── test_pbt_log_buffer.py          # PBT: buffer capacity/FIFO (P4), level filtering (P5)
    ├── test_pbt_monitor_router.py      # PBT: health (P1), DB status (P2), model config (P3),
    │                                   #   Slack tokens (P6), RAG counts (P8), auth (P11), secrets (P12)
    ├── test_pbt_health_status_colors.py # PBT: status-to-color mapping (P10)
    ├── test_pbt_sync_status.py        # PBT: sync status computation invariants (P3-P7)
    ├── test_sync_manager.py           # Unit tests for SyncManager (22 tests)
    ├── test_websocket_manager.py      # Unit tests for WebSocketManager (13 tests)
    └── test_pbt_*.py                   # Other property-based tests (hypothesis)
```

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account (bcrypt password) |
| POST | `/api/auth/login` | Login → access token + httpOnly refresh cookie |
| POST | `/api/auth/refresh` | Rotate access token via refresh cookie |
| POST | `/api/auth/logout` | Clear refresh cookie |
| POST | `/api/auth/reset-password` | Request password reset |
| POST | `/api/auth/reset-password/confirm` | Confirm password reset |
| GET | `/api/auth/google` | Start Google OAuth flow |
| GET | `/api/auth/google/callback` | Google OAuth callback |
| GET | `/api/auth/me` | Get current user profile |
| PATCH | `/api/auth/me` | Update current user profile |

### Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/conversations` | List user's conversations |
| GET | `/api/conversations/{session_id}/messages` | Get messages for a conversation |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/agent` | Send a message to the AI agent from the web frontend |

### Admin
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/status` | Get admin status for current user |
| GET | `/api/admin/users` | List all web users (admin only) |
| PATCH | `/api/admin/users/{user_id}` | Update user profile/admin flag (admin only) |
| GET | `/api/admin/conversations` | List all conversations with `?sort=asc\|desc` (admin only) |
| GET | `/api/admin/conversations/{session_id}/messages` | Get messages for any conversation (admin only) |

### Documents
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/documents/tree` | Hierarchical document tree |
| GET | `/api/documents/stats` | Aggregate document statistics |
| GET | `/api/documents/{path}` | Fetch a single document |
| POST | `/api/documents` | Create a new document |
| PUT | `/api/documents/{path}` | Update a document |
| DELETE | `/api/documents/{path}` | Delete a document |
| POST | `/api/documents/search` | Search by content or filename |
| POST | `/api/documents/directories` | Create a directory |
| DELETE | `/api/documents/directories/{path}` | Delete an empty directory |
| GET | `/api/documents/directories` | List all directories |
| POST | `/api/documents/bulk-delete` | Bulk delete documents |
| POST | `/api/documents/bulk-move` | Bulk move documents |
| GET | `/api/documents/categories` | Category tree with counts |
| GET | `/api/documents/category-stats` | Per-category statistics |
| POST | `/api/documents/route-query` | LLM-powered category routing |
| GET | `/api/documents/sync-status` | Sync status for all documents |
| GET | `/api/documents/sync-status/{path}` | Sync status for one document |
| POST | `/api/documents/reindex/{path}` | Re-index a single document |
| POST | `/api/documents/reindex-directory/{path}` | Re-index a directory |
| POST | `/api/documents/reindex-all` | Re-index all documents |
| POST | `/api/documents/resolve-conflict/{path}` | Resolve filesystem/DB conflict |
| WS | `/api/documents/ws` | Real-time document update notifications |

### System Monitor (admin only)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/monitor/health` | Service health for Slack bot, DB, HTTP, RAG |
| GET | `/api/admin/monitor/models` | AI model configuration (LLM, embeddings, GCP) |
| GET | `/api/admin/monitor/database` | DB pool stats + table row counts |
| GET | `/api/admin/monitor/logs?level=INFO` | Application logs filtered by severity |
| GET | `/api/admin/monitor/slack` | Slack bot connectivity status |
| GET | `/api/admin/monitor/resources` | CPU, memory, disk usage via psutil |
| GET | `/api/admin/monitor/rag` | RAG pipeline document/chunk counts |
| GET | `/api/admin/monitor/api-metrics` | Per-endpoint request counts and avg response times |
| GET | `/api/admin/monitor/environment` | Python version, dependency versions, config |
| GET | `/api/admin/monitor/all` | Aggregated response of all above |

## Setup

### Prerequisites

- Docker (recommended) or Python 3.11+
- GCP service account key with Vertex AI access (`secrets/gcp-sa-key.json`)
- PostgreSQL 16 with pgvector (provided by Docker Compose)
- Slack app with Socket Mode enabled

### Run with Docker Compose (recommended)

From the project root (`w7-vertex-master/`):

```bash
cp .env.example .env   # Fill in your values
docker compose up
```

The service starts automatically alongside `postgres` and `rag-pipeline`. No ports are published — Slack uses outbound WebSocket, and the frontend reaches FastAPI via the internal Docker network through nginx reverse proxy.

### Run locally (development)

```bash
cd backend_agent_api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Fill in values, point DATABASE_URL to local postgres

python main.py
```

### Run tests

```bash
cd backend_agent_api
pytest tests/
```

## Environment Variables

Set in the root `.env` file (used by `docker-compose.yml`):

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (set automatically in Docker Compose) |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID for Vertex AI |
| `GOOGLE_CLOUD_REGION` | GCP region (default: `us-central1`) |
| `LLM_CHOICE` | Gemini model name (e.g., `gemini-2.0-flash`) |
| `EMBEDDING_MODEL_CHOICE` | Embedding model (e.g., `gemini-embedding-001`) |
| `EMBEDDING_DIMENSIONS` | Vector dimensions (default: `768`) |
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack App-Level Token (`xapp-...`) |
| `JWT_SECRET_KEY` | Secret for signing JWT tokens |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID (for web login) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `BRAVE_API_KEY` | Brave Search API key (optional) |
| `SEARXNG_BASE_URL` | SearXNG URL (optional, alternative to Brave) |
| `FRONTEND_URL` | Frontend origin for OAuth redirects |

## Database

PostgreSQL 16 with pgvector. Schema migrations are in `sql/`:
- `init.sql` — Core tables (conversations, messages, documents, embeddings)
- `002_web_users.sql` — Web user accounts, refresh tokens, password resets
- `003_hierarchical_rag.sql` — Hierarchical chunks, categories, helper functions
- `004_ivfflat_probes.sql` — IVFFlat index tuning
- `005_document_sync_status.sql` — Document sync status tracking table

Tables are auto-created on first `docker compose up` via the postgres container's init scripts.

## Auth Design

- Passwords hashed with bcrypt
- 15-minute JWT access tokens (in-memory on frontend)
- Refresh tokens stored as httpOnly cookies, rotated on each `/api/auth/refresh` call
- Rate limiting on login attempts
- Google OAuth as an alternative login method
