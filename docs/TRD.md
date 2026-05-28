# Technical Requirements Document (TRD)

## Architecture
- `api-gateway`: FastAPI endpoints, orchestration entrypoint.
- `ingestion-service`: GitHub data acquisition (GraphQL/REST in production).
- `analysis-service`: deterministic signal extraction and archetype classification.
- `narrative-service`: evidence-grounded README/report synthesis.

## Storage
- Postgres (planned): normalized users/repos/commits/signals/reports.
- Redis (planned): cache and short-lived orchestration state.
- Object storage (planned): report snapshots and share payload artifacts.
- Current scaffold: in-memory store for rapid development.

## Processing Model
- Async job-style pipeline: ingest -> analyze -> synthesize.
- Idempotency key built from `(username, scope, honesty_mode, include_private, window)`.

## Auth Modes
- Public-only anonymous mode.
- OAuth-scoped private analysis mode with explicit consent.

## Reliability
- Graceful partial-failure handling required in production ingestion.
- Rate-limit aware fetchers with fallback/backoff strategy.
