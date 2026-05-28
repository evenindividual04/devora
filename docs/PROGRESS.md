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

## Session 2026-05-29 — Signals + Eval Harness (feat/signals-eval-fidelity)

### Area A — High-value signals (all implemented)
- [x] `pr_review_ratio` = reviewed PRs / (authored+1) — doc rank #1 Very High
- [x] `authorship_dominance` — avg user commit share over top repos (DOA proxy) — rank #2 Very High
- [x] `language_entropy` — byte-weighted Shannon H — rank #6 High
- [x] `weekday_commit_ratio` — % commits Mon–Fri — rank #7 High
- [x] `issue_resolution_rate` = closed / (opened+1) — rank #9 Medium
- [x] `human_commit_ratio` — after bot filtering
- [x] Archetype scorer updated: review_bonus + dominance_bonus → OSS Maintainer; weekday_commit_ratio → Product Engineer / Hobbyist; entropy → Full-stack Generalist / Hobbyist

### Area B — Data-collection fidelity (REST heuristics)
- [x] `GitHubCommit` enriched: `author_login`, `author_date`, `committer_date`, `file_names`
- [x] `fetch_commits` populates all new fields from commit-detail response
- [x] Bot filter: `*[bot]`, `dependabot`, `github-actions`, `renovate` → excluded from ratios
- [x] Trivial commit flag: `_touches_source()` — only `.py`/`.go` etc count; `.md`/`.yml`/`.lock` don't
- [x] Backdating heuristic: `backdated_commit_ratio` when `|committer_date − author_date| > 30d`
- [x] `fetch_user_pr_issue_counts` → deprecated wrapper over `fetch_user_collaboration_counts` (returns `CollaborationCounts` dataclass with 4 fields)
- [x] `fetch_repo_languages(username, repo)` → `dict[str, int]` byte map
- [x] `fetch_contributors(username, repo)` → `list[(login, contributions)]`
- [x] Config: `github_signal_repos: int = 5`
- [x] Pipeline wired: repo languages + contributors fetched for top-N own repos

### Area C — LLM-as-Judge eval harness (full)
- [x] `app/eval/dimensions.py` — 6 dimensions (specificity, authenticity, falsifiability, tonal_appropriateness, structural_coherence, noise_to_signal) with 1-5 rubrics + CoT prompts
- [x] `app/eval/judges.py` — `DeterministicAuthenticityJudge` (always-on, offline-safe), `GeminiJudgeProvider` (google.genai pattern), `OpenAICompatibleJudgeProvider` (Groq/OpenRouter)
- [x] `app/services/eval_service.py` — `ReadmeEvaluator`: panel aggregation, graceful fallback to deterministic
- [x] `app/eval/monitoring.py` — `population_stability_index` (+0.01 empty-bin guard), `ks_statistic`
- [x] Contracts: `DimensionScore`, `EvalResult` added to `contracts.py`; `AnalysisRecord.eval` field added
- [x] `GET /analysis/{id}/eval` — returns cached or on-demand eval
- [x] `GET /ops/eval/summary` — admin: per-dimension distribution + PSI + banned-phrase incidence
- [x] Async sampling in pipeline: `eval_sample_rate` (default 0.1) triggers `asyncio.create_task`
- [x] Config: `eval_judge_providers`, `eval_openai_*`, `eval_sample_rate`

### Tests
- 288 passed, 5 skipped (Gemini canary — rate limited, expected)
- `tests/test_analysis_signals.py` — 46 tests (new: bot filter, trivial commit, backdating, weekday, entropy, PR review ratio, DOA, issue resolution, CollaborationCounts, fetch_repo_languages, fetch_contributors)
- `tests/test_eval_monitoring.py` — PSI/K-S math
- `tests/test_eval_service.py` — deterministic judge, aggregation, contracts
- `tests/eval/test_canary.py` — 5 fixtures (good/mediocre/bad), skips when Gemini rate-limited
- Overall coverage: 92%

## What's Next

### Priority order

1. **Archetype calibration** — weights hand-tuned; track distribution across real users via `GET /ops/eval/summary`.

2. **Frontend: signals panel** — expose `pr_review_ratio`, `language_entropy`, `weekday_commit_ratio` in `ResultsPanel`. The endpoint exists.

3. **Phase 2: GraphQL migration** — see `docs/PHASE2_GRAPHQL.md` for the complete plan.

4. **OpenAI-compatible judge** — wire Groq/OpenRouter free Llama for cross-family diversity by setting `eval_openai_*` env vars.

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
