# Changelog

All notable changes to w7-ragKB are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/); the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

This entry tracks work landing on `main` after the v0.1.0 cut. Update with each PR.

### Added
- _(no entries yet)_

### Changed
- _(no entries yet)_

### Fixed
- _(no entries yet)_

### Security
- _(no entries yet)_

---

## [v0.1.0] — planned, not yet tagged

First semver-tagged release under the **w7-ragKB** identity. Supersedes the historical
`openclaw-freeze-v1` tag.

This project releases via the GitHub-auto-generated source archive only — `docker-compose.yml`
builds from local source contexts, so the source archive *is* the deployable artifact.
No additional release assets are uploaded.

### Added
- Multi-channel AI agent platform built on Pydantic AI + Vertex AI Gemini, served through
  Slack Socket Mode, Telegram, Discord, and an authenticated React web frontend over a
  single in-process WebSocket gateway.
- Document ingestion pipeline supporting local files and Google Drive, indexed into
  PostgreSQL 16 + pgvector with hierarchical chunking and category routing.
- Four-service Docker Compose stack (`postgres`, `slack-bot`, `rag-pipeline`, `frontend`)
  with hard per-service memory limits sized for a single GCP `e2-medium` (4 GB RAM) VM.
- `deploy.py` Compose wrapper with `--type local` (join an existing `localai` AI stack)
  and `--type cloud` (standalone) deployment profiles, plus `--down` teardown.
- REST API surface across `/api/auth/*`, `/api/conversations`, `/api/agent`,
  `/api/admin/*`, `/api/documents/*`, `/api/knowledge-base/*`, and
  `/api/admin/monitor/*` — see `w7-vertex-master/backend_agent_api/README.md`.
- React 18 / Vite / Tailwind / shadcn-ui frontend with admin dashboard, chat UI,
  document browser, and admin monitor.
- Database schema with parameterized-only access via `asyncpg`: `init.sql` plus
  migrations `002_web_users.sql`, `003_hierarchical_rag.sql`, `004_ivfflat_probes.sql`,
  `005_document_sync_status.sql`.
- systemd units for non-Compose VM deployments (`slack-bot.service`,
  `rag-pipeline.service`).

### Changed
- Rebranded from "OpenClaw Integration" to **w7-ragKB**. The historical
  `openclaw-freeze-v1` tag remains as an archive marker; the canonical project
  description is now in `CLAUDE.md` and `README.md`.

### Security
- Web auth uses bcrypt-hashed passwords, 15-minute JWT access tokens, and httpOnly
  refresh cookies rotated on every refresh call.
- Login rate-limited in-memory.
- All inter-service traffic is internal: zero inbound public ports except the
  frontend on 8080; the Control Plane WebSocket binds to `127.0.0.1`.

### Known constraints at this release
- SQL migration ordinal collisions (multiple `003_*.sql` and `004_*.sql` files in
  `w7-vertex-master/sql/`) must be resolved before this version can be cut. The
  release ships only the canonical entries listed under "Added".
- The Live KB Browser subsystem (`kb_browser_*`, `kb_*_service.py`, frontend
  `kb-browser/` components, and `006_live_kb_browser.sql`) is in-flight on
  `feature/rag-document-browser` and is not part of the v0.1.0 release surface
  unless explicitly landed first.
- `deploy.py --type cloud` requires a `docker-compose.caddy.yml` companion file
  that is not yet checked in. The `--type local` profile is fully supported.
- The configured GitHub remote `w7-l7ab/openclaw-integration` does not resolve
  via `gh repo view`; remote reconciliation is required before publishing the
  release.
