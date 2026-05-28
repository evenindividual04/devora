"""Unit tests for services and repositories that don't require a running DB."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.models.contracts import (
    AnalysisRecord,
    DataScope,
    GitHubCommit,
    GitHubRepo,
    HonestyMode,
    OutputTarget,
)
from app.repositories.in_memory_store import InMemoryAnalysisStore
from app.services.crypto_service import decrypt_text, encrypt_text
from app.services.github_client import GitHubClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(**kwargs) -> AnalysisRecord:
    defaults = dict(
        username="testuser",
        scope=DataScope.public,
        honesty_mode=HonestyMode.authentic,
        output_targets=[OutputTarget.readme],
        include_private=False,
    )
    defaults.update(kwargs)
    return AnalysisRecord(**defaults)


# ---------------------------------------------------------------------------
# InMemoryAnalysisStore
# ---------------------------------------------------------------------------

class TestInMemoryAnalysisStore:
    def test_create_and_get(self):
        store = InMemoryAnalysisStore()
        record = _make_record()
        created = store.create(record)
        assert created is record
        fetched = store.get(record.analysis_id)
        assert fetched is record

    def test_get_missing_returns_none(self):
        store = InMemoryAnalysisStore()
        assert store.get(uuid4()) is None

    def test_update_changes_updated_at(self):
        store = InMemoryAnalysisStore()
        record = _make_record()
        store.create(record)
        original_ts = record.updated_at
        record.status = "completed"
        updated = store.update(record)
        assert updated.status == "completed"
        assert updated.updated_at >= original_ts

    def test_update_overwrites_existing(self):
        store = InMemoryAnalysisStore()
        record = _make_record()
        store.create(record)
        record.status = "analyzing"
        store.update(record)
        fetched = store.get(record.analysis_id)
        assert fetched.status == "analyzing"

    def test_multiple_records_isolated(self):
        store = InMemoryAnalysisStore()
        r1 = _make_record(username="alice")
        r2 = _make_record(username="bob")
        store.create(r1)
        store.create(r2)
        assert store.get(r1.analysis_id).username == "alice"
        assert store.get(r2.analysis_id).username == "bob"


# ---------------------------------------------------------------------------
# crypto_service
# ---------------------------------------------------------------------------

class TestCryptoService:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "my-secret-token"
        encrypted = encrypt_text(plaintext)
        assert encrypted != plaintext
        assert decrypt_text(encrypted) == plaintext

    def test_encrypt_produces_different_ciphertext_each_time(self):
        # Fernet uses a random IV per encryption
        c1 = encrypt_text("same")
        c2 = encrypt_text("same")
        assert c1 != c2

    def test_decrypt_invalid_raises(self):
        with pytest.raises(Exception):
            decrypt_text("not-valid-ciphertext")


# ---------------------------------------------------------------------------
# GitHubClient._headers
# ---------------------------------------------------------------------------

class TestGitHubClientHeaders:
    def test_headers_without_token(self):
        client = GitHubClient()
        h = client._headers()
        assert "Authorization" not in h
        assert h["Accept"] == "application/vnd.github+json"

    def test_headers_with_token(self):
        client = GitHubClient(token="abc123")
        h = client._headers()
        assert h["Authorization"] == "Bearer abc123"


# ---------------------------------------------------------------------------
# GitHubClient._request_with_backoff
# ---------------------------------------------------------------------------

class TestGitHubClientRequestWithBackoff:
    def test_successful_response_returned(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {}
        mock_resp.raise_for_status = MagicMock()

        async def run():
            client = GitHubClient()
            mock_httpx = AsyncMock()
            mock_httpx.request = AsyncMock(return_value=mock_resp)
            return await client._request_with_backoff(mock_httpx, "GET", "/test")

        result = asyncio.run(run())
        assert result is mock_resp

    def test_rate_limit_exhaustion_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"x-ratelimit-remaining": "0"}
        mock_resp.raise_for_status = MagicMock()

        async def run():
            client = GitHubClient()
            mock_httpx = AsyncMock()
            mock_httpx.request = AsyncMock(return_value=mock_resp)
            with patch("asyncio.sleep", new=AsyncMock()):
                return await client._request_with_backoff(mock_httpx, "GET", "/test")

        with pytest.raises(RuntimeError, match="rate limit retries exhausted"):
            asyncio.run(run())

    def test_non_rate_limit_403_raises_immediately(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {}
        mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError("403", request=MagicMock(), response=mock_resp))

        async def run():
            client = GitHubClient()
            mock_httpx = AsyncMock()
            mock_httpx.request = AsyncMock(return_value=mock_resp)
            return await client._request_with_backoff(mock_httpx, "GET", "/test")

        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(run())


# ---------------------------------------------------------------------------
# GitHubClient.fetch_repos
# ---------------------------------------------------------------------------

class TestGitHubClientFetchRepos:
    def _make_raw_repo(self, name: str = "my-repo") -> dict:
        return {
            "name": name,
            "stargazers_count": 5,
            "forks_count": 2,
            "language": "Python",
            "pushed_at": "2024-01-15T10:00:00Z",
            "description": "A test repo",
            "topics": ["python", "api"],
            "fork": False,
            "owner": {"login": "testuser"},
        }

    def test_fetch_repos_returns_parsed_repos(self, restore_github_client):
        raw = [self._make_raw_repo("repo-a"), self._make_raw_repo("repo-b")]

        async def run():
            client = GitHubClient()
            mock_resp = MagicMock()
            mock_resp.json = MagicMock(return_value=raw)
            client._request_with_backoff = AsyncMock(return_value=mock_resp)
            return await client.fetch_repos("testuser")

        repos = asyncio.run(run())
        assert len(repos) == 2
        assert repos[0].name == "repo-a"
        assert repos[0].stars == 5
        assert repos[0].language == "Python"
        assert repos[0].topics == ["python", "api"]
        assert repos[0].is_fork is False

    def test_fetch_repos_filters_by_owner_when_authenticated(self, restore_github_client):
        # Put the non-owner repo first so the filter condition triggers
        raw = [
            {**self._make_raw_repo("fork-repo"), "owner": {"login": "other"}},
            {**self._make_raw_repo("mine"), "owner": {"login": "testuser"}},
        ]

        async def run():
            client = GitHubClient(token="tok")
            mock_resp = MagicMock()
            mock_resp.json = MagicMock(return_value=raw)
            client._request_with_backoff = AsyncMock(return_value=mock_resp)
            return await client.fetch_repos("testuser", include_private=True)

        repos = asyncio.run(run())
        assert len(repos) == 1
        assert repos[0].name == "mine"

    def test_fetch_repos_falls_back_to_updated_at(self, restore_github_client):
        raw = [{"name": "r", "stargazers_count": 0, "forks_count": 0, "language": None, "pushed_at": None, "updated_at": "2024-03-01T00:00:00Z", "fork": False}]

        async def run():
            client = GitHubClient()
            mock_resp = MagicMock()
            mock_resp.json = MagicMock(return_value=raw)
            client._request_with_backoff = AsyncMock(return_value=mock_resp)
            return await client.fetch_repos("u")

        repos = asyncio.run(run())
        assert repos[0].language == "Unknown"
        assert repos[0].updated_at.year == 2024


# ---------------------------------------------------------------------------
# GitHubClient.fetch_commits
# ---------------------------------------------------------------------------

class TestGitHubClientFetchCommits:
    def _make_commit_list_resp(self) -> dict:
        return {"sha": "abc123"}

    def _make_commit_detail_resp(self, sha: str = "abc123") -> dict:
        return {
            "sha": sha,
            "commit": {
                "message": "feat: something",
                "committer": {"date": "2024-01-10T12:00:00Z"},
            },
            "stats": {"additions": 15, "deletions": 3},
        }

    def test_fetch_commits_with_provided_repos(self, restore_github_client):
        repos = [
            GitHubRepo(name="myrepo", stars=0, forks=0, language="Go", updated_at=datetime.now(UTC))
        ]

        async def run():
            client = GitHubClient()
            list_resp = MagicMock()
            list_resp.json = MagicMock(return_value=[{"sha": "abc"}])
            detail_resp = MagicMock()
            detail_resp.json = MagicMock(return_value=self._make_commit_detail_resp("abc"))
            client._request_with_backoff = AsyncMock(side_effect=[list_resp, detail_resp])
            return await client.fetch_commits("testuser", repos=repos)

        commits = asyncio.run(run())
        assert len(commits) == 1
        assert commits[0].sha == "abc"
        assert commits[0].additions == 15
        assert commits[0].repo_name == "myrepo"

    def test_fetch_commits_skips_missing_committed_at(self, restore_github_client):
        repos = [
            GitHubRepo(name="r", stars=0, forks=0, language="Go", updated_at=datetime.now(UTC))
        ]

        async def run():
            client = GitHubClient()
            list_resp = MagicMock()
            list_resp.json = MagicMock(return_value=[{"sha": "x"}])
            detail_resp = MagicMock()
            detail_resp.json = MagicMock(return_value={"sha": "x", "commit": {"message": "m", "committer": {}}, "stats": {}})
            client._request_with_backoff = AsyncMock(side_effect=[list_resp, detail_resp])
            return await client.fetch_commits("testuser", repos=repos)

        commits = asyncio.run(run())
        assert commits == []


# ---------------------------------------------------------------------------
# GitHubClient.fetch_user_pr_issue_counts
# ---------------------------------------------------------------------------

class TestGitHubClientPrIssueCounts:
    def test_returns_counts_from_search_api(self, restore_github_client):
        async def run():
            client = GitHubClient()
            def _resp(total):
                r = MagicMock()
                r.json = MagicMock(return_value={"total_count": total})
                return r
            # fetch_user_pr_issue_counts delegates to fetch_user_collaboration_counts
            # which makes 4 search calls: authored PRs, reviewed PRs, issues, closed issues
            client._request_with_backoff = AsyncMock(side_effect=[
                _resp(42),  # authored PRs
                _resp(0),   # reviewed PRs
                _resp(17),  # authored issues
                _resp(0),   # closed issues
            ])
            return await client.fetch_user_pr_issue_counts("testuser")

        pr_count, issue_count = asyncio.run(run())
        assert pr_count == 42
        assert issue_count == 17

    def test_returns_zeros_on_exception(self, restore_github_client):
        async def run():
            client = GitHubClient()
            client._request_with_backoff = AsyncMock(side_effect=RuntimeError("network error"))
            return await client.fetch_user_pr_issue_counts("testuser")

        pr_count, issue_count = asyncio.run(run())
        assert pr_count == 0
        assert issue_count == 0


# ---------------------------------------------------------------------------
# QueueManager (in-memory mode)
# ---------------------------------------------------------------------------

class TestQueueManagerInMemory:
    def test_enqueue_and_dequeue(self):
        from app.queue.manager import QueueManager
        from unittest.mock import patch

        async def run():
            qm = QueueManager()
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.use_redis_queue = False
                await qm.enqueue("some-id")
                result = await qm.dequeue(timeout_seconds=1)
            return result

        result = asyncio.run(run())
        assert result == "some-id"

    def test_dequeue_returns_none_on_timeout(self):
        from app.queue.manager import QueueManager
        from unittest.mock import patch

        async def run():
            qm = QueueManager()
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.use_redis_queue = False
                result = await qm.dequeue(timeout_seconds=0)
            return result

        result = asyncio.run(run())
        assert result is None

    def test_ping_returns_true_without_redis(self):
        from app.queue.manager import QueueManager
        from unittest.mock import patch

        async def run():
            qm = QueueManager()
            with patch("app.core.config.settings") as mock_settings:
                mock_settings.use_redis_queue = False
                return await qm.ping()

        assert asyncio.run(run()) is True

    def test_close_is_noop_without_redis(self):
        from app.queue.manager import QueueManager

        async def run():
            qm = QueueManager()
            await qm.close()  # should not raise

        asyncio.run(run())
