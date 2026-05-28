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

### Fallback to deterministic on any exception — now observable
`GeminiNarrativeProvider` catches all exceptions and falls back to the deterministic provider. Now logs at WARNING (not debug) with the reason. `ReadmeResult.generator` is set to the model id on success or `"deterministic"` on fallback — surfaced in the API response and the UI caption. If you see `deterministic fallback` in the UI, check logs for the cause.

### Silent LLM fallback root cause: markdown-in-JSON-string
Gemini Flash (2.0-flash-lite) was generating invalid JSON when the prompt asked for a full README markdown inside a JSON string field — the markdown contained quotes, curly braces, and newlines that broke JSON parsing. Fix: add `response_schema=_NARRATIVE_JSON_SCHEMA` to `GenerateContentConfig`. With a schema, the SDK enforces field structure at the protocol level before returning text, eliminating parse failures. Upgrade to `gemini-2.5-flash` which handles structured output more reliably.

### Archetype names must match template keys exactly
The scorer's `scores` dict keys must exactly match keys in `_ARCHETYPE_TEMPLATES`. A mismatch causes silent fallback to `_DEFAULT_TEMPLATE` — the archetype is shown correctly in the headline but the narrative framing is generic. Maintain a test that asserts every emitted archetype has a template entry.

### Confidence math: top/sum across N archetypes is structurally weak
With 8 archetypes, `top_score / sum(scores)` has a minimum of 1/8 ≈ 0.125, floored at 0.40. This makes the confidence metric meaningless — every analysis shows 40–92% regardless of how clearly the data points to one archetype. Use separation-based `top/(top+second)` instead, which measures how decisively the winner beats second place: 0.9 means the winner has 9× the score of second. Cap at 0.95; apply a thin-data cap when <3 own repos or <5 commits.

### Classifier "toy" label was dismissive
Calling repos "toy" in signals like `toy_repo_count` and `dominant_repo_type` let that language leak into the narrative ("24 toy repos"). Renamed to "personal" (neutral). Added a "project" tier for repos that have ≥5 commits and a description — these are substantive personal projects that deserve a higher signal score than unstarred repos.

### Churn mean+cap masks real patterns
`avg_churn_per_commit = min(mean(churns), 2000)` was unreliable: one massive merge commit (10k+ lines) inflates the mean, and the 2000 cap makes large-commit developers look identical. Fix: use `statistics.median` on human+source-touching commits (bots and doc-only commits excluded). Median is robust to outliers and bots. Drop the cap — if a developer genuinely lands 5000-line commits, that's a real signal.

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

### `github_max_repos`/`github_commits_per_repo` cost tradeoff
These two settings drive the bulk of API call volume. At defaults (30 repos × 15 commits = up to 450 commit-detail calls per analysis). Raising `github_max_repos` beyond 30 hits the secondary rate limit quickly for unauthenticated requests; raising `github_commits_per_repo` beyond 15 improves temporal signal accuracy but adds latency with diminishing returns (the 16th–30th commit per repo rarely shifts the trajectory buckets). Tune both together — doubling one without the other gives lopsided coverage (many repos shallow vs few repos deep).

### `github_signal_repos` cost tradeoff: cap to `github_signal_repos` (default 5)
Fetching languages and contributor data per repo makes 2 API calls per repo. With `github_signal_repos=5`, that's 10 extra calls per analysis. This is bounded and safe; don't increase without considering rate-limit budget (30 search-API calls + 10 signal calls = 40/analysis on authenticated requests).

### Deterministic judge: empty README scores 1/5, not 5/5
An empty README has no banned phrases, so a naive "penalise phrases" judge would score it 5/5. The fix: check `readme_md.strip()` first and return score=1 immediately. Always test the empty-input case for quality judges.

### PSI formula: normalise inputs before applying
The population_stability_index function accepts both raw counts and proportions. Normalise by dividing by the total in each distribution before applying the formula. Without normalisation, count-scale differences (e.g. 100 vs 0.25) produce meaningless PSI values.

### `google.generativeai` is deprecated — use `google.genai`
All new Gemini code should use `from google import genai; client = genai.Client(api_key=...)` pattern. The old `import google.generativeai as genai; genai.GenerativeModel(...)` pattern still works but emits a FutureWarning and will be removed. Narrative provider already uses the new SDK; eval judges now match.

---

## Caching

### Never pass async Redis clients across event loop boundaries
`redis.asyncio.Redis` is bound to the event loop it was created in. If you call `asyncio.run()` inside a thread that was spun up by `asyncio.to_thread()`, a new event loop is created — but the existing Redis client was bound to the outer loop and will error or deadlock. The fix: perform all cache I/O in the async context *before* dispatching to `to_thread`. In `pipeline.py`, the narrative cache check (`await cache.get(key)`) happens before `asyncio.to_thread(build_both, ...)` — never inside the thread.

### Cache the right abstraction level: network boundary > function boundary
Putting the cache at the HTTP client level (inside `GitHubClient`) is far more valuable than caching inside `compute_signals()`. The former eliminates network calls entirely; the latter only saves CPU. Cache as close to the external I/O as possible.

### Signal fingerprint must be sorted for stable cache keys
`_narrative_cache_key` sorts signals by name before hashing: `sorted([{"n": s.name, ...} for s in signals], key=lambda x: x["n"])`. Signal order from `compute_signals` isn't guaranteed to be stable if the underlying dict iteration order changes or signals are conditionally appended. Sort before hashing; otherwise two identical analyses can produce different cache keys.

### Write-through + invalidate-before-write on analysis records
The pattern in `AnalysisStore.update()` is: `await cache.delete(key)` → DB write → `await cache.set(key, ...)` only if `status == "completed"`. The delete happens *before* the DB write so a concurrent reader can't serve stale cached data during the write window. In-progress records are never cached — polling clients always get fresh status from the DB.

### `RedisCache` lazy connect: first-call ping determines availability
The cache class attempts `Redis.from_url(...).ping()` on the first `get`/`set` call. If Redis is down, `self._redis` stays `None` and every subsequent call is a no-op (no exception, no retry). This is intentional: the cache is an optimisation, not a correctness dependency. The downside is that a Redis restart isn't picked up automatically — `cache.close()` resets `_redis = None` so the next call will re-probe.

### HTTP `Cache-Control` headers: inject via `Response` parameter, not middleware
FastAPI's dependency injection pattern (`async def handler(response: Response, ...)`) is the cleanest way to set response headers on a per-route basis without touching the return type. Middleware-based cache headers are harder to make conditional (e.g. "only cache if status==completed"). Use the `Response` parameter injection for anything that depends on the response content.

### `fetch_commits` cache key uses `username:include_private`, not repo list
Caching commits by hashing the full repo list would be correct but produces huge keys and defeats the point (you'd need to fetch repos first to build the key). In practice, `pipeline.py` always calls `fetch_repos` (which is also cached) then passes the full list to `fetch_commits` — the two calls are always consistent within a TTL window. Only consider a finer-grained key if there's a caller that passes custom subsets.
