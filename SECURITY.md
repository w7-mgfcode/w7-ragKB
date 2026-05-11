# Security Policy

w7-ragKB processes user authentication credentials, conversation history,
documents that may contain sensitive material, and outbound calls to Vertex AI
and third-party messaging platforms. Security reports are taken seriously.

## Supported versions

| Version | Status | Receives security fixes |
|---------|--------|-------------------------|
| `main` branch | Active development | Yes |
| `v0.1.0` | Planned, not yet tagged | Will be supported once cut |
| `openclaw-freeze-v1` (historical tag) | Archive only | No |

## Reporting a vulnerability

**Do not open a public GitHub Issue or Pull Request for security reports.**

Until a contact channel is published on the reconciled GitHub remote, please use
the following:

- Open a GitHub Security Advisory (private) on the repository once it is publicly
  reachable.
- If the repository is private and you do not have access, contact the project
  maintainer through the channel by which you discovered the project.

Include in your report:

- A description of the vulnerability and its potential impact.
- The component affected (e.g. `backend_agent_api/auth_router.py`, the Compose
  service named `slack-bot`, the `rag-pipeline` ingestion worker).
- A minimal reproduction, including the smallest config or input that triggers
  the issue.
- Whether you have a suggested fix.

You can expect:

- Acknowledgement within 5 business days.
- A triage decision (accepted / declined / needs more info) within 10 business
  days of acknowledgement.
- For accepted issues, coordination on disclosure timing before any public
  patch announcement.

## Scope

In scope for security reports:

- Authentication and session handling (`auth_router`, `auth_middleware`,
  `token_manager`, `rate_limiter`).
- SQL handling — the project's convention is parameterized queries only via
  `asyncpg`; any string interpolation of user input qualifies.
- The agent's tool surface: RAG retrieval, web search, SQL execution, browser
  automation, code execution, image analysis. Sandbox escape and unintended
  capability access are in scope.
- Docker Compose configuration, including secret mounting and port exposure.
- The session-isolation model: cross-session data leaks, tool-allowlist
  bypasses, DM-pairing or webhook authentication bypasses.

Out of scope:

- Volumetric DoS without an authentication bypass or amplification factor.
- Vulnerabilities in third-party services (Slack, Telegram, Discord, Vertex AI,
  Google Drive) that we cannot fix in this project.
- Findings that require physical access to the host VM or a privileged
  PostgreSQL account.

## Hardening defaults

The runtime intentionally minimizes attack surface:

- Zero inbound ports except the frontend on `8080`.
- All platform integrations (Slack Socket Mode, Telegram, Discord, Vertex AI)
  are outbound only.
- The Control Plane WebSocket binds to `127.0.0.1:18789` and is not reachable
  from outside the host.
- Web auth uses bcrypt-hashed passwords, 15-minute JWT access tokens, and
  httpOnly refresh cookies rotated on every refresh call.
- Secrets are environment variables or Docker secrets — never committed.

If you find a configuration in the codebase or documentation that contradicts
the above, please report it.
