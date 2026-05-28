# Devora — Engineering Learnings

Lessons learned during development. Read before starting a new feature. Update whenever something bites you or surprises you.

---

## Architecture

### Worker embedded vs separate
`RUN_WORKER_IN_API=true` runs the consumer as an `asyncio.create_task` inside the FastAPI lifespan. Fine for dev, but a crash in the worker brings down the API process. In prod, always set `RUN_WORKER_IN_API=false` and run `python -m app.workers.run` separately.

### Dual-mode queue gotcha
The queue (`app/queue/manager.py`) creates a new `asyncio.Queue` instance if the running event loop changes. This matters in tests — if you create the queue manager in one loop and use it in another (e.g. pytest-asyncio with `function` scope), you'll silently get a new empty queue. Solution: always use `queue_manager` as a module-level singleton and let it self-heal via `_ensure_local_queue()`.

### Double-fetch was a real cost
Before the fix, every analysis run hit the GitHub API for repos *twice* — once in `PipelineWorker.fetch_repos()` and once inside `fetch_commits()`. Fixed by passing `repos` into `fetch_commits(repos=None)`. If you add a new method that needs the repo list, always accept it as a parameter rather than re-fetching.

---

## GitHub Client

### Search API for PR/issue counts
`GET /search/issues?q=type:pr+author:{username}&per_page=1` returns `total_count` in the JSON envelope — you get the full lifetime count in one request with no pagination. The search API has a separate rate limit (10/min unauth, 30/min auth) so wrap it in a try/except and return `(0, 0)` on failure rather than surfacing a hard error.

### `fetch_repos` doesn't paginate
`per_page=100` but no Link-header pagination. Users with >100 repos silently get the first 100. Fix when this becomes a real constraint.

### Topics are more reliable than name keywords
`repo.topics` is a curated, explicit list set by the repo owner. Repo name keyword matching (`_repo_name_matches`) catches incidental matches (e.g. a repo called `my-library` triggering `tooling`). Combining both — as `_repo_matches(name, topics, keywords)` now does — gives higher confidence domain signals.

---

## Analysis Engine

### Commit data is sampled, not complete
`fetch_commits` fetches only `GITHUB_MAX_REPOS` repos (default 30), `GITHUB_COMMITS_PER_REPO` commits each. Signals like `commits_per_week`, `months_active_last_year`, and `activity_trajectory` are computed over this sample. A highly active user whose recent activity is in repos outside the sample can appear "inactive". Confidence values (0.55–0.65 for temporal signals) are intentional — don't raise them without a better data source.

### Priority-ordered classifier vs multi-label scoring
For `_classify_repo`, a priority-ordered decision tree (`coursework` > `hackathon` > `research` > `OSS` > ...) beats a scored multi-label approach. With a scored approach, a research project with 10 stars would tie with an OSS project — but the keyword signal for "research" is higher confidence than star count for "OSS". Decision trees make the override logic explicit and auditable.

### `repo_name` on commits unlocks per-repo grouping
Adding `repo_name: str = ""` to `GitHubCommit` was cheap but important — it lets `compute_signals` count commits per repo (`Counter(c.repo_name for c in commits)`) which feeds both `_classify_repo` and `_score_repo`. Without it, all classification would be based on repo metadata alone.

### Temporal signals need bucket smoothing
Comparing month-by-month commit counts is noisy when working with a sample. Using 90-day buckets (recent 90 days vs prior 90 days) smooths out repos that had a burst in one specific month. Don't go finer than 30-day granularity with sampled data.

### Archetype scoring: weights need real data
The scoring weights (`ml_bias * 2.0`, etc.) are hand-tuned. The confidence formula (`top_score / sum(scores)`) produces a minimum of 0.40 even when only one archetype fires weakly. Track the top archetype distribution across real users — if 80% get "Product Engineer", the weights are off. Don't raise confidence floors without calibration data.

### `_score_repo` for standout ranking
The quality score weights: stars (capped at 20 to prevent viral repos dominating), commit depth (capped at 6), recency (+3), original work (+2), classification bonus (OSS +4, production +3, research +2). Stars are capped because a viral repo from 5 years ago with no recent commits is less "standout" than an actively-developed production service with moderate stars.

---

## LLM / Narrative

### Gemini sometimes returns JSON with markdown fences
Even with `"return only valid JSON"` in the system prompt, Gemini Flash occasionally wraps output in ` ```json ... ``` `. The report generator already handles this with a strip. Watch for it if you add more JSON-output prompts.

### Two-stage prompting > one big prompt
Initial instinct was to combine identity synthesis and README generation into one prompt. Splitting into (1) signals → identity context and (2) context → README gives noticeably more coherent output — the model can "plan" before writing. Keep this pattern.

### LLM softening bias requires explicit permission to override
For `brutally_honest` mode, a system prompt saying "be direct" is insufficient — RLHF training biases models toward softening. The instruction must explicitly say "you are permitted to be unflattering" and name specific examples ("if commit quality is low, say so explicitly"). Without that explicit permission, the model will frame every weakness constructively regardless of instructions.

### Anti-genericity needs both system prompt AND post-generation strip
System prompt alone isn't sufficient — the model occasionally substitutes synonyms ("dedicated" instead of "driven"). The post-generation `anti_generic_guard()` strip catches literal phrases. Future improvement: add a validation pass asking the model to score its own output for genericity.

### Fallback to deterministic on any exception — monitor it
`GeminiNarrativeProvider` wraps both `build_readme` and `build_report` in try/except and falls back silently. A network error, quota hit, or bad response degrades rather than fails. The log says `"Gemini readme generation failed, falling back to deterministic"` — make sure this is monitored in prod.

### HonestyMode instructions: write them in first person for the model
"Write authentically" is weaker than "Write from the signals as they are — no editorialising, no softening." The model responds better to concrete behavioural instructions than abstract adjectives.

---

## Frontend

### Async poll loop in a component
Polling with `async/while + await setTimeout` inside a submit handler is simpler than `useEffect` + `setInterval` for a one-shot flow. The loop exits on terminal states (`completed`, `failed`, `failed_permanent`) and the `active` reference pattern isn't needed since state resets on each submit. Only use `useEffect`-based polling when you need to poll independently of user action.

### Status strings need humanisation on the frontend
The backend emits `"ingesting"`, `"analyzing"` etc. These are fine as API values but look raw to users. Map them to human strings (`STATUS_LABELS` dict) in the frontend rather than exposing the internal state machine vocabulary.

---

## Dev Environment

### `email-validator` was missing from deps
`pydantic`'s `EmailStr` type requires `email-validator` installed separately. Added 2026-05-28. If you see `ImportError: email-validator is not installed` — run `uv sync`.

### Tests only cover the API layer
`tests/test_api.py` tests end-to-end routes but there are no unit tests for `AnalysisService`, `NarrativeService`, or `GeminiNarrativeProvider`. The analysis engine (36+ signals, classifiers, scoring) is only smoke-tested. **Add `tests/test_analysis_service.py` before the engine gets significantly more complex.**

### Test mocks must track method signature changes
The test file monkey-patches `GitHubClient` methods. When you change a method signature (e.g. adding `repos=None` to `fetch_commits`), the mock must be updated too or you get a `TypeError` in tests. Always check `tests/test_api.py` after changing any `GitHubClient` method.

### CI requires Postgres + Redis
Local dev defaults to SQLite + in-memory queue (`USE_REDIS_QUEUE=false`). Don't assume local behaviour matches CI for anything queue- or DB-related.

### `restore_github_client` fixture must save/restore current state, not original
When `test_api.py` patches `GitHubClient` methods at module load time, `conftest.py` captures the originals before the patch. If `restore_github_client` restores originals and then yields, the real methods are live for the test. But on teardown it must restore the *current* (patched by test_api.py) state, not the originals — otherwise subsequent `test_api.py` tests run with the real (unpatched) methods. The fixture now saves-current → restores-original → yield → restores-saved.

### AsyncMock in test_api.py: don't use `new_callable=AsyncMock` with `patch.object`
The pattern `patch.object(client, method, new_callable=AsyncMock)` combined with `side_effect=[AsyncMock(), ...]` produces unawaited coroutine warnings and wrong values. Use direct assignment instead: `client.method = AsyncMock(side_effect=[...])` with `MagicMock()` (not AsyncMock) for response objects.

### GitHub languages/contributors fetch: cap to `github_signal_repos` (default 5)
Fetching languages and contributor data per repo makes 2 API calls per repo. With `github_signal_repos=5`, that's 10 extra calls per analysis. This is bounded and safe; don't increase without considering rate-limit budget (30 search-API calls + 10 signal calls = 40/analysis on authenticated requests).

### Deterministic judge: empty README scores 1/5, not 5/5
An empty README has no banned phrases, so a naive "penalise phrases" judge would score it 5/5. The fix: check `readme_md.strip()` first and return score=1 immediately. Always test the empty-input case for quality judges.

### PSI formula: normalise inputs before applying
The population_stability_index function accepts both raw counts and proportions. Normalise by dividing by the total in each distribution before applying the formula. Without normalisation, count-scale differences (e.g. 100 vs 0.25) produce meaningless PSI values.

### `google.generativeai` is deprecated — use `google.genai`
All new Gemini code should use `from google import genai; client = genai.Client(api_key=...)` pattern. The old `import google.generativeai as genai; genai.GenerativeModel(...)` pattern still works but emits a FutureWarning and will be removed. Narrative provider already uses the new SDK; eval judges now match.
