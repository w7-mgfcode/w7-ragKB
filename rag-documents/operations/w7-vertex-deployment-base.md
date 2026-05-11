# w7-vertex-master Deployment Base

This document defines the canonical deployment base for the `w7-vertex-master` (OpenClaw + Vertex AI) system.

## Primary Deployment Base

- Platform: Google Cloud Platform (GCP)
- Compute: single VM
- Machine type: `e2-medium` (2 vCPU, 4 GB RAM)
- OS: Ubuntu 22.04 LTS
- Region: `us-central1`
- Storage: 50 GB SSD

## Runtime Stack

- Orchestration: Docker Compose
- Services:
  - `postgres` (PostgreSQL 16 + pgvector)
  - `slack-bot` (FastAPI + Slack adapter + Gateway control plane)
  - `rag-pipeline` (document ingestion and embedding generation)
  - `frontend` (nginx serving React build)

## Network Model

- External exposure:
  - Frontend on TCP `8080` (LAN/dev)
  - Production target should terminate TLS on `443` with domain
- Internal service communication:
  - Docker bridge network only
- Gateway control plane:
  - `ws://127.0.0.1:18789` (internal loopback)

## Data Layer

- Database: PostgreSQL 16 with pgvector extension
- Vector dimensions: `768`
- Embedding model: `gemini-embedding-001`
- Core DB objects include:
  - `conversations`, `messages`
  - `channels`, `sessions`, `session_messages`
  - `documents`, `document_metadata`, `document_rows`

## Operations Baseline

- Process supervision: `systemd` units for compose services
- Mandatory backup before updates:
  - `pg_dump` database backup
  - `.env` backup
- Rollback baseline:
  - checkout previous commit
  - restore DB backup
  - rebuild and restart compose services

## Resource Budget

- Total RAM budget: 4 GB
- Recommended caps:
  - postgres: 1 GB
  - slack-bot: 1.5 GB
  - rag-pipeline: 1 GB
  - frontend: 512 MB

## Note

If asked "deployment base", the authoritative short answer is:

`GCP us-central1, Ubuntu 22.04 VM (e2-medium, 2 vCPU/4GB), Docker Compose stack with PostgreSQL+pgvector, backend agent, RAG pipeline, and frontend nginx.`
