[![Release](https://img.shields.io/github/v/release/w7-mgfcode/w7-ragKB)](https://github.com/w7-mgfcode/w7-ragKB/releases)
[![License](https://img.shields.io/github/license/w7-mgfcode/w7-ragKB)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Node](https://img.shields.io/badge/node-20%2B-green.svg)](https://nodejs.org/)

# w7-ragKB

> Multi-channel AI agent platform with Retrieval-Augmented Generation, grounding Vertex AI Gemini in a pgvector document corpus and serving Slack, Telegram, Discord, and a React web UI from a single 4 GB GCP VM.

---

## What this is

w7-ragKB ingests documents (local files or Google Drive), indexes them with pgvector embeddings, and answers questions through a Pydantic AI agent backed by Vertex AI Gemini. The same agent is reachable from Slack Socket Mode, Telegram, Discord, and an authenticated React web frontend, all coordinated through a single in-process WebSocket gateway. The runtime is intentionally minimal: zero inbound ports except the frontend on 8080, all platform integrations are outbound, and the four-service Docker Compose stack fits inside a GCP `e2-medium` (2 vCPU, 4 GB RAM) VM.

## Quick Start

Prerequisites: Docker 24+ and a GCP service-account key with Vertex AI access.

Run everything from this directory.

```bash
cp .env.example .env
# Fill in GOOGLE_CLOUD_PROJECT, JWT_SECRET_KEY, POSTGRES_PASSWORD, Slack tokens, etc.

mkdir -p secrets
# Drop your GCP service-account JSON in secrets/gcp-sa-key.json (mounted as a Docker secret).

docker compose up -d
docker compose ps
```

Alternative: `deploy.py` wraps `docker compose` with two profiles —
`--type local --project localai` joins an existing `localai` AI stack on the
same host, and `--type cloud` runs the stack standalone with its own reverse
proxy. The cloud profile currently requires a `docker-compose.caddy.yml`
companion file that is not yet included; the local profile works as shipped.

The web frontend is reachable at `http://localhost:8080`. The agent, gateway, and RAG pipeline run in the background and do not expose ports. To follow logs:

```bash
docker compose logs -f slack-bot
docker compose logs -f rag-pipeline
```

## How it works

Four layers, single host:

```
┌───────────────────────────────────────────────────────────────┐
│  External                                                     │
│   Slack │ Telegram │ Discord │ WhatsApp │ Web (port 8080)     │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│  Gateway       Control Plane WebSocket (127.0.0.1:18789)      │
│                Channel adapters: Slack / Telegram / Discord   │
├───────────────────────────────────────────────────────────────┤
│  Session       SessionManager — isolated contexts per         │
│                user/channel with tool allowlists              │
├───────────────────────────────────────────────────────────────┤
│  Agent         Pydantic AI + Vertex AI Gemini                 │
│                Tools: RAG, web search, SQL, browser           │
│                (Playwright/CDP), code exec, image analysis    │
├───────────────────────────────────────────────────────────────┤
│  Data          PostgreSQL 16 + pgvector (asyncpg pool)        │
└───────────────────────────────────────────────────────────────┘
```

The agent service (`backend_agent_api/main.py`) boots the DB pool, SessionManager, ResourceManager, sync + WebSocket managers, the cron scheduler, the control plane, the Slack adapter, and the FastAPI HTTP server in one `asyncio.gather`, then tears them down in reverse on SIGINT/SIGTERM. The RAG ingestion worker (`backend_rag_pipeline/`) runs as a separate container watching local files and Google Drive.

## Documentation

| Doc | Description |
|-----|-------------|
| [Backend API reference](backend_agent_api/README.md) | Endpoint inventory (Auth, Data, Chat, Admin, Documents, Knowledge Base, System Monitor), environment variables, auth design, DB schema overview. |
| [Deployment guide](docs/operations/DEPLOYMENT.md) | Compose-based and systemd-based deployment on a GCP VM. |
| [Document browser guide](docs/product/DOCUMENT_BROWSER_GUIDE.md) | Product-level walkthrough of the document management UI. |
| [Document sync runbook](docs/operations/SYNC_RUNBOOK.md) | Recovering from filesystem ↔ database sync conflicts. |
| [Telegram / Discord / webhook setup](docs/) | Channel-specific configuration notes (`setup-telegram.md`, `setup-discord.md`, `setup-webhooks.md`). Slack uses Socket Mode — see the backend API reference for token configuration. |
| [Cron job setup](docs/setup-cron-jobs.md) | Configuring proactive scheduled agent tasks. |
| [Frontend integration guide](docs/frontend-integration-guide.md) | Wiring the React SPA against the FastAPI backend. |

## Releases

`v0.1.0` is the first tagged release under the w7-ragKB identity. Download the source archive or the `w7-ragKB-v0.1.0.tar.gz` asset from the [Releases page](https://github.com/w7-mgfcode/w7-ragKB/releases). See [`CHANGELOG.md`](CHANGELOG.md) for release notes.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for dev setup, test commands, code conventions, and the commit + PR workflow.

## Security

Report security issues privately rather than through public Issues. See [`SECURITY.md`](SECURITY.md) for the disclosure policy.

## License

[MIT](LICENSE).
