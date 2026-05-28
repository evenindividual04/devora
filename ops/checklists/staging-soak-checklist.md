# Staging Soak Checklist (24h)

## Preconditions
- Migrations applied to staging DB.
- API and worker running from candidate release.
- Real GitHub OAuth app credentials configured.
- Alerts wired and firing tests completed.

## Smoke tests
1. Register/login/logout flow works.
2. Public analysis run completes.
3. Private analysis run completes with proper OAuth scope.
4. Share create/get/revoke works for owner.
5. Non-owner share revoke blocked.
6. Dead-letter + requeue workflow works.

## Soak targets
- Failed jobs <2% over 24h.
- No sustained queue growth >15m.
- p95 analysis completion within launch threshold.
- No OAuth outage longer than 5m.

## Exit criteria
- All smoke tests pass.
- No critical alerts unresolved.
- On-call handoff complete with dashboards + runbook.
