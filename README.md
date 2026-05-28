# GitHub Profile Analyzer Backend (Private Beta Ready)

Production-oriented backend + auth-gated frontend scaffolding for GitHub identity analysis and evidence-grounded README/report generation.

## Implemented
- Session auth: register/login/refresh/logout.
- Role model: user/admin.
- Ownership checks for analyses and shares.
- OAuth token encryption at rest.
- Rate limiting (user+IP+route).
- Worker retries, dead-letter status, requeue ops endpoint.
- Share links with signed expiry and owner/admin revocation.
- Audit logging for run/share/requeue actions.
- Health/readiness and metrics endpoint.

## Core endpoints
- Auth/session:
  - `POST /auth/register`
  - `POST /auth/login`
  - `POST /auth/refresh`
  - `POST /auth/logout`
- Analysis:
  - `POST /analysis/run`
  - `GET /analysis`
  - `GET /analysis/{id}`
  - `GET /analysis/{id}/status|signals|readme|report`
- Share:
  - `POST /analysis/{id}/share`
  - `GET /share/{token}`
  - `POST /shares/{token}/revoke`
- Ops/admin:
  - `GET /ops/dead-letter`
  - `POST /ops/requeue/{analysis_id}`
  - `GET /ops/metrics`
- Health:
  - `GET /health/live`
  - `GET /health/ready`

## Run
```bash
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run python -m app.workers.run
```

## Docker
```bash
docker compose up -d --build
```

## Frontend
```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE=http://localhost:8000`.
