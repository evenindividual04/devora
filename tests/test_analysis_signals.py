"""TDD tests for high-value signals (Area A) and data-collection fidelity (Area B).

Each test is traced to its doc source:
  - "GitHub Signals for Developer Archetypes.md" (rank table)
  - "GitHub Metrics for Developer Profiling.md" (heuristics)

Test-first: all tests were written BEFORE the corresponding production code.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.models.contracts import GitHubCommit, GitHubRepo
from app.services.analysis_service import AnalysisService
from app.services.github_client import CollaborationCounts, GitHubClient


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _repo(name="myrepo", stars=0, forks=0, language="Python", days_old=10, is_fork=False) -> GitHubRepo:
    return GitHubRepo(
        name=name,
        stars=stars,
        forks=forks,
        language=language,
        updated_at=datetime.now(UTC) - timedelta(days=days_old),
        is_fork=is_fork,
    )


def _commit(
    sha="abc",
    message="feat: something",
    days_ago=1,
    additions=10,
    deletions=5,
    repo_name="myrepo",
    author_login: str | None = None,
    author_type: str | None = None,
    author_date: datetime | None = None,
    committer_date: datetime | None = None,
    file_names: list[str] | None = None,
) -> GitHubCommit:
    committed_at = datetime.now(UTC) - timedelta(days=days_ago)
    if author_date is None:
        author_date = committed_at
    if committer_date is None:
        committer_date = committed_at
    return GitHubCommit(
        sha=sha,
        message=message,
        committed_at=committed_at,
        additions=additions,
        deletions=deletions,
        repo_name=repo_name,
        author_login=author_login,
        author_date=author_date,
        committer_date=committer_date,
        file_names=file_names or [],
    )


def _get_signal(signals, name):
    return next((s for s in signals if s.name == name), None)


svc = AnalysisService()


# ──────────────────────────────────────────────────────────────────────────────
# Area B — GitHubCommit model enrichment
# ──────────────────────────────────────────────────────────────────────────────

class TestGitHubCommitModel:
    def test_has_author_login_field(self):
        """GitHubCommit must carry the committing login for bot detection."""
        c = _commit(author_login="octocat")
        assert c.author_login == "octocat"

    def test_author_login_defaults_none(self):
        c = _commit()
        assert c.author_login is None

    def test_has_author_date_field(self):
        """author_date enables backdating heuristic (Area B)."""
        t = datetime(2024, 1, 15, tzinfo=UTC)
        c = _commit(author_date=t)
        assert c.author_date == t

    def test_has_committer_date_field(self):
        t = datetime(2024, 1, 15, tzinfo=UTC)
        c = _commit(committer_date=t)
        assert c.committer_date == t

    def test_has_file_names_field(self):
        """file_names list enables trivial-commit detection."""
        c = _commit(file_names=["src/main.py", "README.md"])
        assert c.file_names == ["src/main.py", "README.md"]

    def test_file_names_defaults_empty(self):
        c = _commit()
        assert c.file_names == []

    def test_backward_compat_no_new_fields_required(self):
        """Existing callers that don't pass new fields must still work."""
        c = GitHubCommit(
            sha="x", message="fix: bug", committed_at=datetime.now(UTC),
            additions=1, deletions=0,
        )
        assert c.author_login is None
        assert c.file_names == []


# ──────────────────────────────────────────────────────────────────────────────
# Area B — Bot filter heuristic
# ──────────────────────────────────────────────────────────────────────────────

class TestBotFilter:
    """human_commit_ratio = human commits / total commits (doc: Critical filter)"""

    def test_dependabot_excluded(self):
        commits = [
            _commit(sha="1", author_login="dependabot[bot]"),
            _commit(sha="2", author_login="alice"),
        ]
        signals, _, _ = svc.compute_signals([_repo()], commits)
        sig = _get_signal(signals, "human_commit_ratio")
        assert sig is not None
        assert sig.value == pytest.approx(0.5)

    def test_github_actions_excluded(self):
        commits = [
            _commit(sha="1", author_login="github-actions[bot]"),
            _commit(sha="2", author_login="github-actions"),
            _commit(sha="3", author_login="bob"),
        ]
        signals, _, _ = svc.compute_signals([_repo()], commits)
        sig = _get_signal(signals, "human_commit_ratio")
        assert sig.value == pytest.approx(1 / 3, abs=0.01)

    def test_all_human_commits(self):
        commits = [_commit(sha=str(i), author_login="alice") for i in range(5)]
        signals, _, _ = svc.compute_signals([_repo()], commits)
        sig = _get_signal(signals, "human_commit_ratio")
        assert sig.value == pytest.approx(1.0)

    def test_no_commits_gives_ratio_one(self):
        signals, _, _ = svc.compute_signals([_repo()], [])
        sig = _get_signal(signals, "human_commit_ratio")
        assert sig is not None
        assert sig.value == pytest.approx(1.0)

    def test_author_login_none_treated_as_human(self):
        """If author_login is absent we cannot confirm bot, so count as human."""
        commits = [_commit(sha="1", author_login=None)]
        signals, _, _ = svc.compute_signals([_repo()], commits)
        sig = _get_signal(signals, "human_commit_ratio")
        assert sig.value == pytest.approx(1.0)


# ──────────────────────────────────────────────────────────────────────────────
# Area B — Trivial commit flag (touches_source)
# ──────────────────────────────────────────────────────────────────────────────

class TestTrivialCommitFlag:
    """touches_source = True when at least one non-trivial file is changed."""

    def test_source_file_is_not_trivial(self):
        c = _commit(file_names=["src/main.py", "README.md"])
        # touches_source is computed by the service, not stored on the model
        from app.services.analysis_service import _touches_source
        assert _touches_source(c) is True

    def test_only_docs_and_config_is_trivial(self):
        from app.services.analysis_service import _touches_source
        c = _commit(file_names=["README.md", ".github/workflows/ci.yml", "package.json"])
        assert _touches_source(c) is False

    def test_empty_file_list_treated_as_source(self):
        """When we don't know touched files, assume source (conservative)."""
        from app.services.analysis_service import _touches_source
        c = _commit(file_names=[])
        assert _touches_source(c) is True

    def test_lock_file_is_trivial(self):
        from app.services.analysis_service import _touches_source
        c = _commit(file_names=["poetry.lock"])
        assert _touches_source(c) is False


# ──────────────────────────────────────────────────────────────────────────────
# Area B — Backdating heuristic
# ──────────────────────────────────────────────────────────────────────────────

class TestBackdatingHeuristic:
    """backdated_commit_ratio: |committer_date - author_date| > 30 days (doc: weak proxy)."""

    def test_large_gap_counts_as_backdated(self):
        now = datetime.now(UTC)
        c1 = _commit(sha="1", author_date=now - timedelta(days=60), committer_date=now)
        c2 = _commit(sha="2", author_date=now - timedelta(days=1), committer_date=now)
        signals, _, _ = svc.compute_signals([_repo()], [c1, c2])
        sig = _get_signal(signals, "backdated_commit_ratio")
        assert sig is not None
        assert sig.value == pytest.approx(0.5)

    def test_small_gap_not_backdated(self):
        now = datetime.now(UTC)
        c = _commit(sha="1", author_date=now - timedelta(days=5), committer_date=now)
        signals, _, _ = svc.compute_signals([_repo()], [c])
        sig = _get_signal(signals, "backdated_commit_ratio")
        assert sig.value == pytest.approx(0.0)

    def test_no_commits_gives_ratio_zero(self):
        signals, _, _ = svc.compute_signals([_repo()], [])
        sig = _get_signal(signals, "backdated_commit_ratio")
        assert sig is not None
        assert sig.value == pytest.approx(0.0)


# ──────────────────────────────────────────────────────────────────────────────
# Area A — weekday_commit_ratio (doc rank #7 High)
# ──────────────────────────────────────────────────────────────────────────────

class TestWeekdayCommitRatio:
    """% commits that land on Mon–Fri (weekdays)."""

    def test_all_weekday_commits(self):
        # Monday = weekday 0
        monday = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)  # Jan 15 2024 is a Monday
        commits = [_commit(sha=str(i), days_ago=0) for i in range(3)]
        for c in commits:
            object.__setattr__(c, "committed_at", monday) if hasattr(c, "__setattr__") else None
        # Override committed_at directly since it's a Pydantic model
        commits = [
            GitHubCommit(sha=str(i), message="feat: x", committed_at=monday,
                         additions=1, deletions=0)
            for i in range(3)
        ]
        signals, _, _ = svc.compute_signals([_repo()], commits)
        sig = _get_signal(signals, "weekday_commit_ratio")
        assert sig is not None
        assert sig.value == pytest.approx(1.0)

    def test_all_weekend_commits(self):
        saturday = datetime(2024, 1, 13, 12, 0, tzinfo=UTC)  # Jan 13 2024 is a Saturday
        commits = [
            GitHubCommit(sha=str(i), message="feat: x", committed_at=saturday,
                         additions=1, deletions=0)
            for i in range(3)
        ]
        signals, _, _ = svc.compute_signals([_repo()], commits)
        sig = _get_signal(signals, "weekday_commit_ratio")
        assert sig.value == pytest.approx(0.0)

    def test_mixed_weekday_and_weekend(self):
        monday = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        saturday = datetime(2024, 1, 13, 12, 0, tzinfo=UTC)
        commits = [
            GitHubCommit(sha="1", message="feat: x", committed_at=monday, additions=1, deletions=0),
            GitHubCommit(sha="2", message="feat: x", committed_at=saturday, additions=1, deletions=0),
        ]
        signals, _, _ = svc.compute_signals([_repo()], commits)
        sig = _get_signal(signals, "weekday_commit_ratio")
        assert sig.value == pytest.approx(0.5)

    def test_no_commits_gives_zero(self):
        signals, _, _ = svc.compute_signals([_repo()], [])
        sig = _get_signal(signals, "weekday_commit_ratio")
        assert sig is not None
        assert sig.value == pytest.approx(0.0)


# ──────────────────────────────────────────────────────────────────────────────
# Area A — language_entropy (doc rank #6 High)
# ──────────────────────────────────────────────────────────────────────────────

class TestLanguageEntropy:
    """Byte-weighted Shannon entropy H = -Σ pᵢ log₂ pᵢ (doc: #6 High validity)."""

    def test_two_equal_languages_max_entropy_for_two(self):
        # H({Py:500, Go:500}) = log2(2) = 1.0
        entropy = _compute_entropy({"Python": 500, "Go": 500})
        assert entropy == pytest.approx(1.0, abs=1e-6)

    def test_single_language_zero_entropy(self):
        entropy = _compute_entropy({"Python": 1000})
        assert entropy == pytest.approx(0.0, abs=1e-6)

    def test_empty_map_zero_entropy(self):
        entropy = _compute_entropy({})
        assert entropy == pytest.approx(0.0, abs=1e-6)

    def test_known_byte_map(self):
        # {Py:800, Go:200}: p1=0.8, p2=0.2 → H = -(0.8*log2(0.8) + 0.2*log2(0.2))
        expected = -(0.8 * math.log2(0.8) + 0.2 * math.log2(0.2))
        entropy = _compute_entropy({"Python": 800, "Go": 200})
        assert entropy == pytest.approx(expected, abs=1e-6)

    def test_language_entropy_signal_in_compute_signals(self):
        """compute_signals emits language_entropy when repo_languages is provided."""
        repo = _repo()
        signals, _, _ = svc.compute_signals(
            [repo], [], repo_languages={"myrepo": {"Python": 800, "Go": 200}}
        )
        sig = _get_signal(signals, "language_entropy")
        assert sig is not None
        expected = -(0.8 * math.log2(0.8) + 0.2 * math.log2(0.2))
        assert sig.value == pytest.approx(expected, abs=1e-3)

    def test_language_entropy_absent_when_no_repo_languages(self):
        """When repo_languages not provided, signal is omitted gracefully."""
        signals, _, _ = svc.compute_signals([_repo()], [])
        sig = _get_signal(signals, "language_entropy")
        # If absent, fine; if present with 0.0, also fine — just not misleading
        if sig is not None:
            assert sig.value == pytest.approx(0.0, abs=0.01)


def _compute_entropy(byte_map: dict) -> float:
    """Helper that wraps the module-level function we'll implement."""
    from app.services.analysis_service import _language_entropy
    return _language_entropy(byte_map)


# ──────────────────────────────────────────────────────────────────────────────
# Area A — pr_review_ratio (doc rank #1 Very High)
# ──────────────────────────────────────────────────────────────────────────────

class TestPrReviewRatio:
    """reviewed / (authored + 1) — guards against div-by-zero."""

    def test_basic_ratio(self):
        signals, _, _ = svc.compute_signals(
            [_repo()], [], pr_count=10, reviewed_pr_count=5
        )
        sig = _get_signal(signals, "pr_review_ratio")
        assert sig is not None
        # reviewed / (authored + 1) = 5 / 11
        assert sig.value == pytest.approx(5 / 11, abs=0.01)

    def test_zero_authored_prs(self):
        signals, _, _ = svc.compute_signals(
            [_repo()], [], pr_count=0, reviewed_pr_count=3
        )
        sig = _get_signal(signals, "pr_review_ratio")
        assert sig is not None
        assert sig.value == pytest.approx(3.0, abs=0.01)  # 3 / (0+1) = 3.0

    def test_zero_reviewed_and_zero_authored(self):
        signals, _, _ = svc.compute_signals([_repo()], [])
        sig = _get_signal(signals, "pr_review_ratio")
        assert sig is not None
        assert sig.value == pytest.approx(0.0, abs=0.01)  # 0 / 1 = 0

    def test_no_divide_by_zero(self):
        """ratio is always finite."""
        signals, _, _ = svc.compute_signals([_repo()], [], pr_count=0, reviewed_pr_count=0)
        sig = _get_signal(signals, "pr_review_ratio")
        assert math.isfinite(sig.value)


# ──────────────────────────────────────────────────────────────────────────────
# Area A — authorship_dominance (doc rank #2 Very High, DOA proxy)
# ──────────────────────────────────────────────────────────────────────────────

class TestAuthorshipDominance:
    """Avg user commit share over top repos: user_commits / total_contributors_commits."""

    def test_sole_contributor(self):
        # contributor data: {repo: [(login, count)]}
        contrib = {"myrepo": [("alice", 100)]}
        signals, _, _ = svc.compute_signals(
            [_repo()], [], contributors=contrib, username="alice"
        )
        sig = _get_signal(signals, "authorship_dominance")
        assert sig is not None
        assert sig.value == pytest.approx(1.0, abs=0.01)

    def test_shared_contribution(self):
        contrib = {"myrepo": [("alice", 30), ("bob", 70)]}
        signals, _, _ = svc.compute_signals(
            [_repo()], [], contributors=contrib, username="alice"
        )
        sig = _get_signal(signals, "authorship_dominance")
        assert sig.value == pytest.approx(30 / 100, abs=0.01)

    def test_multiple_repos_averaged(self):
        contrib = {
            "repo1": [("alice", 80), ("bob", 20)],  # 0.8
            "repo2": [("alice", 10), ("carol", 90)],  # 0.1
        }
        signals, _, _ = svc.compute_signals(
            [_repo("repo1"), _repo("repo2")], [],
            contributors=contrib, username="alice"
        )
        sig = _get_signal(signals, "authorship_dominance")
        assert sig.value == pytest.approx(0.45, abs=0.01)  # (0.8+0.1)/2

    def test_absent_when_no_contributor_data(self):
        signals, _, _ = svc.compute_signals([_repo()], [])
        sig = _get_signal(signals, "authorship_dominance")
        # When not provided, signal should be omitted or have confidence 0
        if sig is not None:
            assert sig.confidence < 0.3


# ──────────────────────────────────────────────────────────────────────────────
# Area A — issue_resolution_rate (doc rank #9 Medium)
# ──────────────────────────────────────────────────────────────────────────────

class TestIssueResolutionRate:
    """closed / (opened + 1) — guards against div-by-zero."""

    def test_basic_resolution_rate(self):
        signals, _, _ = svc.compute_signals(
            [_repo()], [], issue_count=20, closed_issue_count=15
        )
        sig = _get_signal(signals, "issue_resolution_rate")
        assert sig is not None
        assert sig.value == pytest.approx(15 / 21, abs=0.01)

    def test_zero_issues_opened(self):
        signals, _, _ = svc.compute_signals([_repo()], [])
        sig = _get_signal(signals, "issue_resolution_rate")
        assert sig is not None
        assert sig.value == pytest.approx(0.0, abs=0.01)

    def test_no_divide_by_zero(self):
        signals, _, _ = svc.compute_signals(
            [_repo()], [], issue_count=0, closed_issue_count=0
        )
        sig = _get_signal(signals, "issue_resolution_rate")
        assert math.isfinite(sig.value)


# ──────────────────────────────────────────────────────────────────────────────
# Area B+A — CollaborationCounts dataclass in github_client
# ──────────────────────────────────────────────────────────────────────────────

class TestCollaborationCounts:
    """fetch_user_collaboration_counts returns a CollaborationCounts dataclass."""

    def test_dataclass_has_expected_fields(self):
        cc = CollaborationCounts(pr_count=10, reviewed_pr_count=5, issue_count=20, closed_issue_count=15)
        assert cc.pr_count == 10
        assert cc.reviewed_pr_count == 5
        assert cc.issue_count == 20
        assert cc.closed_issue_count == 15

    @pytest.mark.asyncio
    async def test_fetch_returns_collaboration_counts(self, restore_github_client):
        """fetch_user_collaboration_counts returns CollaborationCounts, not a tuple."""
        from unittest.mock import MagicMock
        client = GitHubClient(token="fake")

        def make_resp(total):
            r = MagicMock()
            r.json.return_value = {"total_count": total}
            return r

        client._request_with_backoff = AsyncMock(side_effect=[
            make_resp(10),  # authored PRs
            make_resp(5),   # reviewed PRs
            make_resp(20),  # authored issues
            make_resp(15),  # closed issues
        ])
        cc = await client.fetch_user_collaboration_counts("alice")

        assert isinstance(cc, CollaborationCounts)
        assert cc.pr_count == 10
        assert cc.reviewed_pr_count == 5
        assert cc.issue_count == 20
        assert cc.closed_issue_count == 15


# ──────────────────────────────────────────────────────────────────────────────
# Area B — fetch_repo_languages in github_client
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchRepoLanguages:
    @pytest.mark.asyncio
    async def test_returns_byte_map(self, restore_github_client):
        from unittest.mock import MagicMock
        client = GitHubClient(token="fake")
        r = MagicMock()
        r.json.return_value = {"Python": 8000, "Go": 2000}
        client._request_with_backoff = AsyncMock(return_value=r)
        result = await client.fetch_repo_languages("alice", "myrepo")
        assert result == {"Python": 8000, "Go": 2000}

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, restore_github_client):
        client = GitHubClient(token="fake")
        client._request_with_backoff = AsyncMock(
            side_effect=httpx.HTTPStatusError("404", request=AsyncMock(), response=AsyncMock(status_code=404))
        )
        result = await client.fetch_repo_languages("alice", "myrepo")
        assert result == {}


# ──────────────────────────────────────────────────────────────────────────────
# Area B — fetch_contributors in github_client
# ──────────────────────────────────────────────────────────────────────────────

class TestFetchContributors:
    @pytest.mark.asyncio
    async def test_returns_login_count_pairs(self, restore_github_client):
        from unittest.mock import MagicMock
        client = GitHubClient(token="fake")
        r = MagicMock()
        r.json.return_value = [
            {"login": "alice", "contributions": 80},
            {"login": "bob", "contributions": 20},
        ]
        client._request_with_backoff = AsyncMock(return_value=r)
        result = await client.fetch_contributors("alice", "myrepo")
        assert result == [("alice", 80), ("bob", 20)]

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, restore_github_client):
        client = GitHubClient(token="fake")
        client._request_with_backoff = AsyncMock(side_effect=Exception("network error"))
        result = await client.fetch_contributors("alice", "myrepo")
        assert result == []
