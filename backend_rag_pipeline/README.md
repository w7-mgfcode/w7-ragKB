# w7-ragKB — RAG Pipeline

Document processing service that watches local files or Google Drive, extracts text, generates Vertex AI embeddings, and stores chunks in PostgreSQL 16 with pgvector for vector similarity search.

Supports continuous monitoring (for Docker deployment) and single-run mode (for cron/scheduled jobs).

## Features

- **Dual source**: Local directory watcher or Google Drive watcher
- **File types**: PDF, text, HTML, CSV, Excel, Word, images, Google Workspace docs
- **Text processing**: Extraction, chunking (configurable size/overlap), Vertex AI embeddings
- **Vector storage**: PostgreSQL 16 + pgvector via asyncpg
- **State management**: Pipeline state tracked in the database for consistent processing across restarts
- **Deployment modes**: Continuous (watch loop) or single-run (for cron jobs)

## Project Structure

```
backend_rag_pipeline/
├── docker_entrypoint.py        # Unified entry point (continuous or single-run)
├── common/
│   ├── db_handler.py           # Document storage via asyncpg
│   ├── text_processor.py       # Text chunking + Vertex AI embeddings
│   └── state_manager.py        # Pipeline state tracking in PostgreSQL
├── Local_Files/
│   ├── main.py                 # Local file watcher entry point
│   ├── file_watcher.py         # File change detection
│   └── config.json             # Local pipeline config
├── Google_Drive/
│   ├── main.py                 # Google Drive watcher entry point
│   ├── drive_watcher.py        # Drive change detection
│   └── config.json             # Drive pipeline config
├── tests/
│   ├── conftest.py
│   ├── test_db_handler.py
│   ├── test_text_processor.py
│   ├── test_docker_entrypoint.py
│   └── test_per_chunk_error_handling.py
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Setup

### Run with Docker Compose (recommended)

From the project root (`w7-vertex-master/`):

```bash
cp .env.example .env   # Fill in your values
mkdir -p rag-documents  # For local file pipeline — drop documents here
docker compose up
```

The pipeline starts alongside `postgres` and `slack-bot`. Documents placed in `./rag-documents/` are automatically processed.

For Google Drive mode, set `RAG_PIPELINE_TYPE=google_drive` in `.env` and mount credentials to `./google-credentials/`.

### Run locally (development)

```bash
cd backend_rag_pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Local files pipeline
python docker_entrypoint.py --pipeline local --mode continuous --interval 60

# Google Drive pipeline
python docker_entrypoint.py --pipeline google_drive --mode continuous --interval 60

# Single-run mode (for cron)
python docker_entrypoint.py --pipeline local --mode single
```

### Run tests

```bash
cd backend_rag_pipeline
pytest tests/
```

## Environment Variables

Set in the root `.env` file (used by `docker-compose.yml`):

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (set automatically in Docker Compose) |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID for Vertex AI |
| `GOOGLE_CLOUD_REGION` | GCP region (default: `us-central1`) |
| `EMBEDDING_MODEL_CHOICE` | Vertex AI embedding model (e.g., `gemini-embedding-001`) |
| `EMBEDDING_DIMENSIONS` | Vector dimensions (default: `768`, must match pgvector column) |
| `RAG_PIPELINE_TYPE` | `local` or `google_drive` |
| `RUN_MODE` | `continuous` (default) or `single` |
| `RAG_PIPELINE_ID` | Unique ID for database state tracking |

## How It Works

1. **Initialization**: Connects to PostgreSQL via asyncpg. Authenticates with Google Drive if using that source. Loads previous state from `rag_pipeline_state` table when `RAG_PIPELINE_ID` is set.
2. **Monitoring**: Periodically checks the source for new, updated, or deleted files.
3. **Processing**: Extracts text → chunks it → generates Vertex AI embeddings → upserts into the `documents` table with pgvector.
4. **Deletion sync**: When a source file is deleted, its chunks are removed from PostgreSQL.

## Database Tables

- **`documents`**: Content chunks with pgvector embeddings and file metadata (JSONB)
- **`rag_pipeline_state`**: Pipeline state tracking (`last_check_time`, `known_files` as JSONB)

Schema migrations are in `sql/init.sql` and `sql/9-rag_pipeline_state.sql`.

## Configuration

Each pipeline has a `config.json` controlling:
- `supported_mime_types` — File types to process
- `text_processing.default_chunk_size` — Target chunk size (default: 400 chars)
- `text_processing.default_chunk_overlap` — Overlap between chunks
- Pipeline-specific settings (watch directory, Google Drive folder ID, export MIME types)

When `RAG_PIPELINE_ID` is set, runtime state is stored in PostgreSQL instead of config files.
