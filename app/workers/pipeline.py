from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time

from app.core.cache import cache
from app.core.config import settings
from app.core.metrics import metrics
from app.models.contracts import AnalysisRecord, ArchetypeResult, HonestyMode, ReadmeResult, ReportResult, Signal
from app.repositories.analysis_store import store
from app.repositories.oauth_store import oauth_store
from app.services.analysis_service import AnalysisService
from app.services.github_client import GitHubClient
from app.services.narrative_provider import RepoCard
from app.services.narrative_service import NarrativeService


def _narrative_cache_key(
    username: str,
    honesty_mode: HonestyMode,
    signals: list[Signal],
    archetype: ArchetypeResult,
) -> str:
    signals_fp = json.dumps(
        sorted([{"n": s.name, "v": s.value} for s in signals], key=lambda x: x["n"]),
        default=str,
    )
    raw = f"{username}:{honesty_mode.value}:{signals_fp}:{archetype.top_archetype}:{archetype.confidence:.2f}"
    return "narrative:" + hashlib.sha256(raw.encode()).hexdigest()[:24]

logger = logging.getLogger(__name__)


class PipelineWorker:
    def __init__(self) -> None:
        self.analysis = AnalysisService()
        self.narrative = NarrativeService()

    async def run(self, record: AnalysisRecord) -> AnalysisRecord:
        started = time.perf_counter()
        record.status = "ingesting"
        await store.update(record)

        token = await oauth_store.get_token(record.username) if record.include_private else None
        github = GitHubClient(token=token or settings.github_token or None)

        repos = await github.fetch_repos(record.username, include_private=record.include_private)
        commits = await github.fetch_commits(record.username, repos=repos, include_private=record.include_private)
        collab = await github.fetch_user_collaboration_counts(record.username)

        # Fetch language bytes and contributor data for top own repos (Area B/A)
        own_repos = [r for r in repos if not r.is_fork]
        top_repos = own_repos[:settings.github_signal_repos]
        repo_languages: dict[str, dict[str, int]] = {}
        contributors: dict[str, list[tuple[str, int]]] = {}
        for repo in top_repos:
            repo_languages[repo.name] = await github.fetch_repo_languages(record.username, repo.name)
            contributors[repo.name] = await github.fetch_contributors(record.username, repo.name)

        record.status = "analyzing"
        await store.update(record)

        signals, archetype, standout_repos = await asyncio.to_thread(
            self.analysis.compute_signals,
            repos, commits,
            pr_count=collab.pr_count,
            issue_count=collab.issue_count,
            reviewed_pr_count=collab.reviewed_pr_count,
            closed_issue_count=collab.closed_issue_count,
            repo_languages=repo_languages or None,
            contributors=contributors or None,
            username=record.username,
        )
        # Build repo cards for the narrative (standout repos with descriptions)
        repo_map = {r.name: r for r in repos}
        repo_details = [
            RepoCard(
                name=name,
                description=repo_map[name].description or "",
                language=repo_map[name].language,
                stars=repo_map[name].stars,
            )
            for name in standout_repos
            if name in repo_map
        ]

        narrative_key = _narrative_cache_key(record.username, record.honesty_mode, signals, archetype)
        cached_narrative = await cache.get(narrative_key)
        if cached_narrative:
            readme = ReadmeResult.model_validate(cached_narrative["readme"])
            report = ReportResult.model_validate(cached_narrative["report"])
        else:
            readme, report = await asyncio.to_thread(
                self.narrative.build_both,
                record.username, record.honesty_mode, signals, archetype, standout_repos, repo_details,
            )
            await cache.set(narrative_key, {
                "readme": readme.model_dump(mode="json"),
                "report": report.model_dump(mode="json"),
            }, settings.cache_narrative_ttl)

        record.signals = signals
        record.archetype = archetype
        record.readme = readme
        record.report = report
        record.status = "completed"
        record.last_duration_ms = (time.perf_counter() - started) * 1000.0
        metrics.incr("analysis.completed")
        metrics.timing("analysis.duration_ms", record.last_duration_ms)
        updated = await store.update(record)

        # Async eval sampling — fire and forget, does not block the pipeline
        if random.random() < settings.eval_sample_rate:
            asyncio.create_task(self._run_eval(updated))

        return updated

    async def _run_eval(self, record: AnalysisRecord) -> None:
        try:
            from app.services.eval_service import get_evaluator
            evaluator = get_evaluator()
            signals_json = json.dumps({s.name: s.value for s in record.signals})
            readme_md = record.readme.markdown if record.readme else ""
            eval_result = await asyncio.to_thread(evaluator.evaluate, readme_md, signals_json)
            eval_result.analysis_id = record.analysis_id
            record.eval = eval_result
            await store.update(record)
            metrics.incr("eval.sampled")
        except Exception as exc:
            logger.warning("Async eval sampling failed for %s: %s", record.analysis_id, exc)


worker = PipelineWorker()
