# w7-ragKB — Frontend

React 18 + TypeScript + Vite web application for interacting with the w7-ragKB AI agent. Provides a chat interface with real-time streaming, conversation management, and an admin dashboard.

Authentication uses self-hosted JWT auth via the backend FastAPI server — no external auth providers.

## Tech Stack

- **Framework**: React 18 + TypeScript
- **Build**: Vite
- **UI**: Shadcn UI (Radix UI) + Tailwind CSS
- **Auth**: JWT via `auth-client.ts` (in-memory access tokens + httpOnly refresh cookies)
- **API**: REST calls via `authFetch` wrapper with automatic token refresh
- **Testing**: Vitest (unit) + Playwright (e2e)
- **Production server**: nginx (reverse proxies `/api/` → backend FastAPI)

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/               # Shadcn UI primitives
│   │   ├── admin/            # Admin dashboard
│   │   │   ├── SystemMonitor.tsx      # System monitor container
│   │   │   ├── HealthCards.tsx        # Service health status cards
│   │   │   ├── ResourceGauges.tsx     # CPU/memory/disk progress bars
│   │   │   ├── DatabaseMetrics.tsx    # DB pool stats + row counts
│   │   │   ├── LogViewer.tsx          # Filterable application log viewer
│   │   │   ├── ModelConfigPanel.tsx   # AI model configuration display
│   │   │   ├── RagStatus.tsx          # RAG pipeline document stats
│   │   │   ├── ApiMetricsTable.tsx    # Per-endpoint request metrics
│   │   │   ├── EnvironmentInfo.tsx    # Python/dependency versions
│   │   │   ├── UsersTable.tsx         # User management table
│   │   │   └── ConversationsTable.tsx # Conversation browser
│   │   ├── documents/        # Document browser + sync management
│   │   │   ├── DocumentTree.tsx           # Hierarchical tree with sync badges
│   │   │   ├── DocumentViewer.tsx         # Rendered markdown viewer
│   │   │   ├── DocumentEditor.tsx         # Markdown editor
│   │   │   ├── SearchBar.tsx              # Search with debounce
│   │   │   ├── StatsPanel.tsx             # Aggregate statistics
│   │   │   ├── CreateDocumentDialog.tsx   # New document dialog
│   │   │   ├── BulkActionsToolbar.tsx     # Bulk delete/move/reindex
│   │   │   ├── SyncStatusBadge.tsx        # Sync status indicator
│   │   │   ├── ConflictResolutionDialog.tsx # Conflict resolution
│   │   │   └── ReindexDialog.tsx          # Re-index confirmation
│   │   ├── auth/             # Login, register, password reset
│   │   ├── chat/             # Chat interface + streaming
│   │   ├── sidebar/          # Conversation sidebar
│   │   └── util/             # Utility components
│   ├── hooks/
│   │   ├── useAuth.tsx       # Auth state + login/logout/register
│   │   ├── useAdmin.ts       # Admin data fetching via authFetch
│   │   ├── useDocuments.ts   # Document CRUD + sync hooks (React Query)
│   │   ├── useDocumentWebSocket.ts # Real-time sync via WebSocket
│   │   ├── useSystemMonitor.ts # System monitor data fetching + refresh
│   │   ├── useConversationRating.ts
│   │   ├── use-mobile.tsx
│   │   └── use-toast.ts
│   ├── lib/
│   │   ├── auth-client.ts    # JWT auth client (login, register, refresh, authFetch)
│   │   ├── api.ts            # API calls using authFetch
│   │   ├── documents-api.ts  # Document CRUD + sync + reindex API client
│   │   ├── langfuse.ts       # LangFuse integration
│   │   └── utils.ts          # General utilities
│   ├── pages/                # Route pages
│   ├── types/
│   │   ├── database.types.ts   # Standalone TypeScript types
│   │   ├── documents.ts        # Document, sync status, and conflict types
│   │   └── systemMonitor.ts    # System monitor data interfaces
│   ├── App.tsx
│   └── main.tsx
├── src/__tests__/            # Vitest unit tests
│   └── components/documents/
│       └── SyncStatusBadge.test.tsx  # Sync badge rendering tests
├── tests/                    # Playwright e2e tests
│   ├── auth.spec.ts          # Authentication flow tests
│   ├── chat.spec.ts          # Chat interface tests
│   ├── admin-system-monitor.spec.ts  # System monitor tab tests
│   └── mocks.ts              # Shared mock data and route handlers
├── nginx.conf                # Reverse proxy config (/api/ → slack-bot:8000)
├── Dockerfile                # Multi-stage build (Vite → nginx)
├── .env.example
├── package.json
├── vite.config.ts
└── tailwind.config.ts
```

## Auth Flow

1. User registers or logs in via the frontend form
2. Backend returns a short-lived JWT access token (15 min) in the response body + sets an httpOnly refresh cookie
3. `auth-client.ts` stores the access token in memory (not localStorage)
4. `authFetch` wraps all API calls with `Authorization: Bearer <token>` and auto-refreshes on 401
5. On page reload, the refresh cookie silently obtains a new access token via `/api/auth/refresh`

Google OAuth is also supported as an alternative login method.

## Setup

### Run with Docker Compose (recommended)

From the project root (`w7-vertex-master/`):

```bash
docker compose up
```

The frontend container builds the React app and serves it via nginx on port 8080 (internal). nginx proxies `/api/*` requests to the `slack-bot` service on port 8000.

No ports are published externally by default — access is through the Docker network.

### Local development

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The dev server runs at `http://localhost:5173` by default.

### Run tests

```bash
cd frontend
npx playwright install
npm test
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `VITE_API_BASE_URL` | Backend API base URL. Leave empty for same-origin (nginx proxy handles it in production) |
| `VITE_AGENT_ENDPOINT` | Agent streaming endpoint |
| `VITE_ENABLE_STREAMING` | Enable SSE streaming (`true`/`false`) |
| `VITE_LANGFUSE_HOST_WITH_PROJECT` | LangFuse dashboard link (optional, admin UI) |
| `VITE_LANGFUSE_PUBLIC_KEY` | LangFuse public key for feedback (optional) |
| `VITE_LANGFUSE_HOST` | LangFuse host URL (optional) |

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server with HMR |
| `npm run build` | Production build → `dist/` |
| `npm run preview` | Preview production build locally |
| `npm run lint` | Run ESLint |
| `npm test` | Run Playwright e2e tests |

## nginx Reverse Proxy

In production (Docker), nginx serves the built React app and proxies API requests:

```
/api/*  →  http://slack-bot:8000  (FastAPI backend)
/*      →  index.html             (React SPA)
```

This means the frontend and backend share the same origin — no CORS configuration needed.

## Docker Build

The Dockerfile uses a multi-stage build:
1. **Build stage**: `node:18` installs deps and runs `vite build`
2. **Production stage**: `nginx:alpine` serves the static files

No build args needed for auth — the frontend discovers the API at the same origin via nginx.
