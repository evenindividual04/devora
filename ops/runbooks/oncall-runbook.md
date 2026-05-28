# Devora On-Call Runbook

## Primary signals
- `analysis.failed` counter growth
- queued vs completed delta
- `/health/ready` dependency failures
- OAuth exchange failure spikes

## Incident triage (first 10 minutes)
1. Check `/health/ready`.
2. Check `analysis.failed` and queue lag metrics.
3. Inspect recent logs by `x-request-id` and `analysis_id`.
4. Determine scope: API-only, worker-only, OAuth-only, or data-store dependency.

## Common incidents
### Queue lag growth
- Verify worker process is running.
- Check Redis health and connectivity.
- Requeue stuck `failed_permanent` jobs selectively.

### OAuth exchange failures
- Verify GitHub OAuth credentials and callback URL.
- Inspect outbound network/access restrictions.
- Check GitHub API incident status.

### High failure rate
- Inspect `failure_reason` of recent dead-letter jobs.
- Roll back last deploy if new failure signature introduced.
- Disable private analysis scope if token/scope failures dominate.

## Recovery actions
- Requeue endpoint: `POST /ops/requeue/{analysis_id}` (admin token)
- Scale worker replicas
- Rollback to last healthy release

## Escalation
- Escalate to backend owner if critical alert lasts >15m.
- Escalate to infra owner for DB/Redis outage.
