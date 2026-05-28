# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (Python / FastAPI)

```bash
uv sync                                        # install dependencies
uv run alembic upgrade head                    # apply migrations
uv run uvicorn app.main:app --reload           # start API (dev)
uv run python -m app.workers.run               # start worker (when RUN_WORKER_IN_API=false)
uv run pytest -q                               # all tests
uv run pytest tests/test_api.py::test_name -q # single test
uv run alembic check                           # verify no pending migrations
```

### Frontend (Next.js 14 / TypeScript)

```bash
cd frontend && npm install
npm run dev    # dev server (set NEXT_PUBLIC_API_BASE=http://localhost:8000)
npm run build  # production build
npm test       # vitest
```

### Docker (full stack with Postgres + Redis)

```bash
cp .env.example .env   # fill in secrets before first run
docker compose up -d --build
```

## Architecture

### Request lifecycle

`POST /analysis/run` → enqueues an `analysis_id` → `QueueManager` → `Consumer` polls and calls `PipelineWorker.run()` → results written back to the analysis store.

The worker runs **embedded in the API process** by default in dev (`RUN_WORKER_IN_API=true`, `asyncio.Queue`). In production (`RUN_WORKER_IN_API=false`, `USE_REDIS_QUEUE=true`), it runs as a separate process using Redis BLPOP.

### Key modules

| Path | Role |
|------|------|
| `app/main.py` | FastAPI app, lifespan (worker task, queue/db teardown) |
| `app/core/config.py` | All settings via `pydantic-settings` / `.env` |
| `app/api/routes.py` | All route handlers in one file, grouped by sub-router |
| `app/models/contracts.py` | Pydantic models for requests, responses, and the central `AnalysisRecord` |
| `app/db/models.py` + `app/db/session.py` | SQLAlchemy ORM models and async session factory |
| `app/repositories/` | One store per domain entity (analysis, user, session, share, oauth, audit, owner) |
| `app/queue/manager.py` | Dual-mode queue (in-memory asyncio.Queue or Redis) |
| `app/workers/consumer.py` | Poll loop with retry + backoff + dead-letter on permanent failure |
| `app/workers/pipeline.py` | Orchestrates GitHub fetch → signal analysis → narrative generation |
| `app/services/` | `AuthService` (JWT + bcrypt), `AnalysisService` (signal extraction), `NarrativeService` (README/report), `GitHubClient` (httpx) |
| `alembic/versions/` | Sequential migrations; always run `alembic check` after schema changes |
| `frontend/` | Next.js app; communicates with backend via `NEXT_PUBLIC_API_BASE` |

### Auth model

- Session auth with access (60 min) + refresh (7 days) JWTs.
- Refresh tokens are stored in `session_store` (DB) and rotated on each use. Logout revokes the JTI.
- Role model: `user` / `admin`. `require_admin` dependency gates `/ops/*`.
- Rate limiting is composite: `{user_id|anon}:{ip}:{path}`.

### Analysis states

`queued` → `ingesting` → `analyzing` → `completed` | `failed` | `failed_permanent`

Failed jobs retry up to `WORKER_MAX_ATTEMPTS` with exponential backoff. `failed_permanent` items appear in `GET /ops/dead-letter` and can be requeued via `POST /ops/requeue/{id}`.

### Dev vs production

In `app_env=dev` the startup guard is skipped, so placeholder secrets from `config.py` defaults work. Any other env value requires real secrets for `API_KEY` and `SHARE_TOKEN_SECRET`, or the process refuses to start.

OAuth tokens stored in the DB are encrypted at rest using the `OAUTH_TOKEN_ENC_KEY` (`app/services/crypto_service.py`).
