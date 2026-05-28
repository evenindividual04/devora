# Devora — Session Progress Tracker

Use this file to hand off context between Claude Code sessions. Update it at the end of every session.

---

## Product Vision (tl;dr)

Developer identity platform. Input: GitHub username + optional OAuth. Output: personalized README, engineering archetype, behavioral signals, report. **Not** a template generator — a behavioral analysis engine that uses LLM only for the final narrative synthesis step.

Full planning docs: `ChatGPT-GitHub Profile Analyzer Tool.md` (root of repo)

---

## Architecture at a Glance

```
POST /analysis/run
  → Worker (async queue: asyncio.Queue dev / Redis prod)
  → PipelineWorker.run()
      → GitHubClient.fetch_repos()
      → GitHubClient.fetch_commits(repos=repos)        ← repos passed in (no double-fetch)
      → GitHubClient.fetch_user_pr_issue_counts()
      → AnalysisService.compute_signals()              ← deterministic layer
          returns (signals, archetype, standout_repos)
      → NarrativeService.build_readme/report()         ← LLM layer (Gemini Flash)
  → stored in DB → GET /analysis/{id}/readme|report|signals
```

Key config flags: `RUN_WORKER_IN_API=true` (dev embeds worker), `USE_REDIS_QUEUE=false` (dev uses asyncio.Queue), `GEMINI_API_KEY` (empty → falls back to deterministic provider), `GITHUB_MAX_REPOS=30`, `GITHUB_COMMITS_PER_REPO=15`.

---

## What's Done

### Infrastructure (complete, production-quality)
- [x] FastAPI app, lifespan, middleware
- [x] Session auth: register / login / refresh / logout (JWT, JTI revocation)
- [x] Role model: user / admin
- [x] GitHub OAuth for private repo access (token encrypted at rest)
- [x] Async worker pipeline: consumer poll loop, retry + backoff, dead-letter
- [x] Dual-mode queue (asyncio.Queue dev / Redis prod)
- [x] Share links: signed JWT, expiry, owner/admin revocation
- [x] Ownership ACL, audit logging, rate limiting, metrics, health endpoints
- [x] Alembic migrations (3 versions)

### Analysis Engine — session 2026-05-28 #1
- [x] 17 real signals (commit type ratios, message quality, churn, language diversity, active repo ratio, stars, domain bias)
- [x] 8-archetype multi-label engine (ML Experimenter, Systems Builder, Infra Tinkerer, Full-stack Generalist, Tooling Specialist, Research Hacker, OSS Maintainer, Product Engineer)
- [x] Gemini Flash narrative provider with 2-stage prompting, anti-genericity guard, graceful fallback

### Session 2026-05-28 #2 — full priority list completed

#### 1. GitHub client enrichment
- [x] `GitHubRepo` gains `description`, `topics: list[str]`, `is_fork: bool`
- [x] `GitHubCommit` gains `repo_name: str` (enables per-repo commit counting)
- [x] `fetch_commits(repos=None)` — accepts repos param, eliminates double-fetch
- [x] `fetch_user_pr_issue_counts()` — search API (`type:pr/issue author:X`), returns `(0,0)` on error
- [x] `GITHUB_MAX_REPOS=30`, `GITHUB_COMMITS_PER_REPO=15` configurable in settings

#### 2. HonestyMode expansion
- [x] 6 modes: `authentic` (default) | `polished` | `recruiter` | `playful` | `technical` | `brutally_honest`
- [x] Each wired to a distinct tone instruction; `brutally_honest` explicitly permits naming weaknesses

#### 3. Repo classification
- [x] `_classify_repo(repo, commit_count)` → `toy | coursework | production | hackathon | research | infra | OSS | portfolio`
- [x] Priority-ordered decision tree; topics + name matching; own repos only
- [x] 9 new signals: `dominant_repo_type` + `{label}_repo_count` × 8
- [x] Classification boosts archetype scores (Research Hacker, Infra Tinkerer, OSS Maintainer, Product Engineer)

#### 4. Frontend basic UI
- [x] `/analyze` is now a full single-page flow: form → inline polling → results (no page navigation)
- [x] `ResultsPanel`: archetype card + README in styled `<pre>` + copy-markdown button
- [x] `api.ts` refactored: `HonestyMode` exported, all 6 modes, shared `apiFetch` with `r.ok` check

#### 5. Evolution / timeline signals
- [x] 5 new signals: `activity_trajectory`, `months_active_last_year`, `streak_months`, `language_shifted`, `recent_primary_language`
- [x] Trajectory: recent 90-day vs prior 90-day commit buckets → growing / declining / stable / burst / inactive
- [x] Archetype boosts: Systems Builder ← stable, OSS Maintainer ← consistent (≥8 months), Product Engineer ← growing + streak ≥3

#### 6. Report validation — standout_repos ranking
- [x] `_score_repo(repo, commit_count, six_months_ago)` → float (stars, depth, recency, own-work, classification bonus)
- [x] `compute_signals` returns `(signals, archetype, standout_repos)` — top-5 own repos ranked by score
- [x] `NarrativePrompt.standout_repos` threaded through both Gemini and deterministic providers

**Signal count: 36+ (was 17 at start of session 1, 4 before that). 4/4 tests passing.**

---

## What's Next

### Priority order

1. **Unit tests for AnalysisService** — currently only the API layer is tested. The signal engine now has 36+ signals and several interacting classifiers with no isolation tests. Add `tests/test_analysis_service.py` covering: `_classify_repo`, `_score_repo`, trajectory computation, archetype scoring edge cases.

2. **Repo classification: description-based signals** — `description` field is now fetched but `_classify_repo` only uses name + topics. Description text (e.g. "A machine learning experiment reproducing...") could improve classification accuracy significantly.

3. **GitHub client: pagination** — `fetch_repos` fetches `per_page=100` but doesn't paginate. Users with >100 repos silently get the first 100 only. Add Link-header pagination.

4. **Frontend: signals panel** — `ResultsPanel` shows archetype + README but not the signal breakdown. A collapsible signals table (name / value / confidence) would make the product inspectable. The `/analysis/{id}/signals` endpoint already exists.

5. **Frontend: auth flow** — the analyze page works unauthenticated (server returns 401 or the worker fails). The `LoginForm` component exists but isn't surfaced. Wire it up so unauthenticated requests redirect to login.

6. **Archetype calibration** — the confidence formula (`top_score / sum(scores)`) produces a floor of 0.40 even when only one archetype fires. Needs real user data to tune weights. Track the distribution of top archetypes to detect drift.

7. **Evolution signals: language timeline per repo** — current language shift uses `repo.updated_at` as a proxy for "recent". For higher accuracy, fetch the languages breakdown per repo (`GET /repos/{owner}/{repo}/languages`) to get line-count weighted language data.

---

## Known Issues / Tech Debt

- No unit tests for `AnalysisService`, `NarrativeService`, or `GeminiNarrativeProvider` — only API layer is tested.
- Archetype confidence formula is naive (score / sum of scores). Needs calibration once more test data exists.
- `fetch_repos` does not paginate — users with >100 repos silently truncated.
- Temporal signals are over a commit *sample*, not the full history. `months_active_last_year` can be 0 for an active user if their recent activity is in repos not in the sample.

---

## File Map (non-obvious ones)

| File | Purpose |
|------|---------|
| `app/services/analysis_service.py` | Signal computation: `_classify_repo`, `_score_repo`, `compute_signals` → `(signals, archetype, standout_repos)` |
| `app/services/narrative_provider.py` | `GeminiNarrativeProvider` + `DeterministicNarrativeProvider` + `NarrativePrompt` + prompt builders |
| `app/services/narrative_service.py` | Picks provider, builds `NarrativePrompt`, delegates |
| `app/services/github_client.py` | `fetch_repos`, `fetch_commits(repos=)`, `fetch_user_pr_issue_counts` |
| `app/workers/pipeline.py` | Orchestrates fetch → analyze → narrate → store |
| `app/queue/manager.py` | Dual-mode queue (asyncio / Redis) |
| `app/core/config.py` | All settings (pydantic-settings, reads `.env`) |
| `frontend/components/AnalysisForm.tsx` | Full analysis flow: form + async poll loop + results |
| `frontend/components/ResultsPanel.tsx` | Archetype card + README display + copy button |
| `frontend/lib/api.ts` | Typed API client, `apiFetch` helper, `HonestyMode` type |

---

## Last Session: 2026-05-28 #2

**Done:** All 6 priority items — GitHub client enrichment, HonestyMode ×6, repo classification (8 types), frontend single-page flow, temporal/evolution signals (5 new), standout_repos quality ranking.
**Signal count:** 36+ (was 17).
**Tests:** 4/4 passing. Frontend build: clean.
**Stopped at:** Updated PROGRESS.md + LEARNINGS.md.
