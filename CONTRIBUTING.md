# Contributing to w7-ragKB

Thanks for considering a contribution. This file is the authoritative entry point
for contributors. Two stale copies exist (`.github/CONTRIBUTING.md` and the broken
symlink `docs/development/CONTRIBUTING.md`) — both are scheduled for removal once
v0.1.0 is cut. Prefer this file.

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker 24+ and Docker Compose
- PostgreSQL 16 with pgvector (provided by the Compose stack)
- A GCP service-account key with Vertex AI access

## Repository layout

The active product lives under `w7-vertex-master/`. Almost every command in this
file is run from there:

```
.
├── CLAUDE.md               # authoritative project conventions
├── CHANGELOG.md            # release history
├── CONTRIBUTING.md         # this file
├── README.md               # entry point for visitors
├── docs/                   # top-level documentation (some pages are being
│                           # reconciled with w7-vertex-master/docs/)
├── LICENSE                 # MIT
└── w7-vertex-master/
    ├── backend_agent_api/  # Pydantic AI agent, FastAPI, gateway, channel adapters
    ├── backend_rag_pipeline/ # Document ingestion worker
    ├── frontend/           # React 18 + Vite + Tailwind + shadcn-ui SPA
    ├── sql/                # PostgreSQL migrations (init.sql, 002–005)
    ├── docker-compose.yml  # four-service stack
    ├── systemd/            # VM unit files
    └── .env.example        # environment template
```

## Local development

### Backend

```bash
cd w7-vertex-master
python -m venv .venv && source .venv/bin/activate
pip install -r backend_agent_api/requirements.txt
pip install -r backend_rag_pipeline/requirements.txt
pip install black ruff mypy pytest pytest-asyncio pytest-cov hypothesis

cp .env.example .env
# Fill in GOOGLE_CLOUD_PROJECT, JWT_SECRET_KEY, POSTGRES_PASSWORD, Slack tokens.

# Run the agent service in the foreground:
python backend_agent_api/main.py
```

### Frontend

```bash
cd w7-vertex-master/frontend
npm install
npm run dev          # Vite dev server on the port printed at startup
```

### Database

The Compose stack runs PostgreSQL with pgvector and applies migrations at
container start. For local Postgres outside Compose:

```bash
psql -h localhost -U postgres -d w7ragkb -f w7-vertex-master/sql/init.sql
psql -h localhost -U postgres -d w7ragkb -f w7-vertex-master/sql/002_web_users.sql
# (etc. for 003, 004, 005 — see release-boundary.md for the canonical ordering once
# the migration collisions in sql/ are resolved.)
```

### Full Compose stack

```bash
cd w7-vertex-master
docker compose up -d
docker compose logs -f slack-bot
```

`deploy.py` is an alternative entry point that wraps `docker compose` with
deployment profiles (`--type local|cloud`, `--down`). The `--type local` profile
is the supported default; `--type cloud` is currently waiting on a missing
`docker-compose.caddy.yml` companion file.

## Tests

Backend (from `w7-vertex-master/backend_agent_api/`):

```bash
pytest tests/                       # unit
pytest tests/test_pbt_*.py          # property-based (Hypothesis)
pytest tests/ -v -m integration     # integration (requires a live DB)
pytest tests/ --cov=. --cov-report=html
```

Frontend (from `w7-vertex-master/frontend/`):

```bash
npm run test:unit                   # vitest
npx playwright test                 # e2e
```

A PR is expected to leave both suites green for the code paths it touches.

## Code conventions

Per [`CLAUDE.md`](CLAUDE.md):

- **Python:** `snake_case`, Black formatting, Ruff linting. DB modules prefixed
  `db_`, Vertex AI modules prefixed `vertex_`.
- **TypeScript:** camelCase filenames, PascalCase component names, ESLint.
- **SQL:** parameterized queries only via `asyncpg`. Never string-interpolate
  user input.
- **Tests:** `test_*.py` (unit), `test_pbt_*.py` (property-based with Hypothesis),
  `*.spec.ts` (Playwright e2e).
- **Runtime budgets:** the project targets a 4 GB GCP VM. Per-service memory
  limits in `docker-compose.yml` are load-bearing; do not exceed them.
  `asyncpg` pool max is 20. Concurrent Playwright browsers cap at 3.
  Sessions archive after 60 minutes of inactivity.
- **Secrets:** environment variables or Docker secrets only — never hardcode
  credentials, never commit `*-key.json` or `secrets/`.

## Commit and PR workflow

1. Branch from `main` (e.g. `feat/document-search-suggestions`).
2. Use [Conventional Commits](https://www.conventionalcommits.org/) with a scope:
   `feat(api): …`, `fix(rag): …`, `test(backend): …`, `chore(infra): …`,
   `docs(architecture): …`.
3. Run the relevant test suites before pushing.
4. Open a PR against `main`. The PR description should explain *why* — the diff
   already shows the *what*.
5. CI must pass before merge. CI currently runs on the configured remote; the
   remote is being reconciled (see `release-boundary.md`).

## Security

Report security issues privately rather than via public Issues. See
[SECURITY.md](SECURITY.md) for the disclosure policy and expected response time.

## Questions

Open an Issue once the GitHub remote is reconciled. Until then, capture the
question in `.kiro/specs/` or `.agents/plans/` as appropriate so it lands in
the existing planning surface.
