from __future__ import annotations

import time

from app.core.config import settings
from app.core.metrics import metrics
from app.models.contracts import AnalysisRecord
from app.repositories.analysis_store import store
from app.repositories.oauth_store import oauth_store
from app.services.analysis_service import AnalysisService
from app.services.github_client import GitHubClient
from app.services.narrative_service import NarrativeService


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
        pr_count, issue_count = await github.fetch_user_pr_issue_counts(record.username)

        record.status = "analyzing"
        await store.update(record)

        signals, archetype, standout_repos = self.analysis.compute_signals(repos, commits, pr_count=pr_count, issue_count=issue_count)
        readme, report = self.narrative.build_both(record.username, record.honesty_mode, signals, archetype, standout_repos)

        record.signals = signals
        record.archetype = archetype
        record.readme = readme
        record.report = report
        record.status = "completed"
        record.last_duration_ms = (time.perf_counter() - started) * 1000.0
        metrics.incr("analysis.completed")
        metrics.timing("analysis.duration_ms", record.last_duration_ms)
        return await store.update(record)


worker = PipelineWorker()
