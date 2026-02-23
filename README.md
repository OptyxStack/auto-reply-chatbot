# Support AI Assistant | RAG Chatbot for Enterprise

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**RAG (Retrieval-Augmented Generation) chatbot** – Enterprise-grade internal Support AI Assistant. Answers support questions via REST API using **hybrid retrieval** (BM25 + vector search) over your company knowledge base. Grounded answers with citations, LLM-powered, production-ready.

> 🔍 *Keywords: RAG chatbot, LLM support assistant, vector search, semantic search, knowledge base AI, customer support automation, retrieval-augmented generation*

## Table of Contents

- [Why Use This?](#why-use-this)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Project Structure](#project-structure)

## Why Use This?

- **RAG architecture**: Combines BM25 (keyword) + vector (semantic) search for accurate retrieval
- **Production-ready**: WAF, rate limiting, observability, quality gates
- **API-first**: No frontend lock-in; integrate with any client (web, mobile, Slack, etc.)
- **Pluggable**: Swap LLM, embeddings, reranker providers

For production deployments, [OptyxStack](https://optyxstack.com/) offers [AI optimization](https://optyxstack.com/ai-optimization) to tune retrieval latency and token efficiency, plus [AI recovery](https://optyxstack.com/ai-recovery) for incident response when pipelines fail.

## Features

- **API Gateway**: Nginx reverse proxy, request size limit, IP allow/blocklist, WAF (injection/jailbreak)
- **Hybrid retrieval**: OpenSearch (BM25) + Qdrant (vector) + reranking
- **Orchestrator**: State machine, model routing by query complexity
- **LLM layer**: Fallback model, Redis cache, token budget, timeout/retry
- **Guardrails**: PII masking in logs, jailbreak/injection defense
- **Grounded answers**: Citations required; reviewer gate enforces quality
- **Quality gate**: PASS / ASK_USER / RETRIEVE_MORE / ESCALATE (no infinite loops)
- **Observability**: OpenTelemetry, Prometheus (token cost, retrieval hit-rate, escalation rate, p95 latency)
- **Object storage**: MinIO for raw docs/artifacts
- **API-first**: REST API + optional React frontend for CRUD & chat

## Tech Stack

- **API**: FastAPI + Pydantic v2 + Uvicorn
- **DB**: PostgreSQL 15+
- **Cache/Queue**: Redis + Celery
- **Search**: OpenSearch (BM25), Qdrant (vector), pluggable reranker
- **Embeddings**: OpenAI (default, pluggable)
- **LLM**: OpenAI Chat Completions (default, pluggable)

## Quick Start

### Prerequisites

- Docker & docker-compose
- OpenAI API key

### Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY, ADMIN_API_KEY, etc.
```

### Run with Docker Compose

**Default** (API on port 8000, Frontend on port 5174, MinIO on 9000/9001):

```bash
docker-compose up -d
```

- **API**: http://localhost:8000
- **Frontend**: http://localhost:5174 (conversation management, chat CRUD)

**With Nginx gateway** (API behind Nginx on port 80):

```bash
docker-compose --profile full up -d
```

Then run migrations and ingest sample data:

```bash
# Option A: Inside container
docker-compose exec api alembic upgrade head
docker-compose exec api python scripts/ingest_from_source.py --files sample_docs.json

# Option B: Local (with services running)
make init-db
make ingest
```

> **Note:** `source/sample_docs.json` is included for demo. Add your own JSON files to `source/` (see `app/services/source_loaders.py` for supported formats).

### Local Development (without Docker)

1. Start dependencies: PostgreSQL, Redis, OpenSearch, Qdrant (or use docker-compose for infra only)
2. Create virtualenv and install: `pip install -r requirements.txt`
3. Set env vars and run: `uvicorn app.main:app --reload`
4. Run worker: `celery -A worker.celery_app worker --loglevel=info`
5. Migrate: `alembic upgrade head`

## API Endpoints

### Conversations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/conversations` | List conversations (pagination: `?page=1&page_size=20`, filter: `?source_type=ticket&source_id=...`) |
| POST | `/v1/conversations` | Create conversation (required: `source_type`, `source_id` – ticket or livechat) |
| GET | `/v1/conversations/{id}` | Get conversation + messages |
| PATCH | `/v1/conversations/{id}` | Update conversation metadata |
| DELETE | `/v1/conversations/{id}` | Delete conversation |
| POST | `/v1/conversations/{id}/messages` | Send message (sync response) |
| POST | `/v1/conversations/{id}/messages:stream` | Send message (SSE stream) |

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/admin/ingest` | Trigger ingestion (requires X-Admin-API-Key) |
| POST | `/v1/admin/ingest-from-source` | Ingest from source/ JSON files (sync) |

### Health & Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/health` | Health check |
| GET | `/v1/metrics` | Prometheus metrics |
| GET | `/v1/dashboard/stats` | Token cost, retrieval hit-rate, escalation rate |

## Example cURL Requests

### Create conversation

Each conversation must be linked to a ticket or livechat:

```bash
curl -X POST http://localhost:8000/v1/conversations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key" \
  -d '{"source_type": "ticket", "source_id": "TKT-12345", "metadata": {}}'
```

`source_type`: `"ticket"` or `"livechat"`

### Send message

```bash
curl -X POST http://localhost:8000/v1/conversations/{CONV_ID}/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key" \
  -H "X-External-User-Id: user-123" \
  -d '{"content": "What is your refund policy?"}'
```

### Trigger ingestion

```bash
curl -X POST http://localhost:8000/v1/admin/ingest \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: admin-key" \
  -d '{
    "documents": [
      {
        "url": "https://example.com/refund-policy",
        "title": "Refund Policy",
        "raw_text": "Full refund within 30 days...",
        "doc_type": "policy"
      }
    ]
  }'
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL (async) |
| `DATABASE_URL_SYNC` | `postgresql://...` | PostgreSQL (sync, Celery) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis |
| `OPENSEARCH_HOST` | `http://localhost:9200` | OpenSearch |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `OPENAI_API_KEY` | - | Required for embeddings/LLM |
| `API_KEY` | - | API auth (empty = dev mode) |
| `ADMIN_API_KEY` | - | Admin auth |
| `RERANKER_PROVIDER` | `local` | `local` \| `cohere` \| identity |
| `RERANKER_URL` | `http://localhost:8001/rerank` | Local reranker service |
| `MAX_REQUEST_BODY_BYTES` | 1048576 | Max request body (1MB) |
| `IP_BLOCKLIST` | - | Comma-separated IPs to block |
| `IP_ALLOWLIST` | - | Comma-separated IPs to allow |
| `OBJECT_STORAGE_URL` | - | MinIO/S3 endpoint (e.g. http://minio:9000) |

## Reranker

For production, run a local reranker service (e.g. sentence-transformers cross-encoder) that accepts:

```json
POST /rerank
{"query": "...", "documents": ["...", "..."], "top_k": 5}
```

Returns: `{"results": [{"index": 0, "relevance_score": 0.95}, ...]}`

Or use Cohere by setting `RERANKER_PROVIDER=cohere` and `COHERE_API_KEY`.

## Frontend (React)

Conversation management UI with full CRUD:

```bash
# Run dev (hot reload)
cd frontend && npm install && npm run dev
# Open http://localhost:5173

# Or use Docker
docker-compose up -d frontend
# Frontend: http://localhost:5174
```

Features: conversation list (pagination), create/delete, live chat, dashboard metrics.

## Project Structure

```
app/
  main.py              # FastAPI app
  api/routes/          # Conversations, admin, health
  services/            # Retrieval, LLM, reviewer, ingestion
  search/              # OpenSearch, Qdrant, reranker, embeddings
  db/                  # Models, session
  core/                # Config, auth, logging, rate limit, tracing
worker/
  celery_app.py
  tasks.py             # Ingestion tasks
frontend/              # React + Vite (CRUD, chat UI)
alembic/               # Migrations
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

*Maintained with support from [OptyxStack](https://optyxstack.com/) — AI infrastructure specialists. Need help with [RAG optimization](https://optyxstack.com/ai-optimization) or [production recovery](https://optyxstack.com/ai-recovery)?*
