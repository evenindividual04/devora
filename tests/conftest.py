# conftest.py is imported before any test module, so we capture the original
# GitHubClient methods here — before test_api.py's module-level monkey-patches
# can overwrite them.
from __future__ import annotations

import pytest

from app.services.github_client import GitHubClient

_orig_fetch_repos = GitHubClient.fetch_repos
_orig_fetch_commits = GitHubClient.fetch_commits
_orig_fetch_user_pr_issue_counts = GitHubClient.fetch_user_pr_issue_counts


@pytest.fixture
def restore_github_client():
    """Restore GitHubClient to its real implementation for unit tests."""
    GitHubClient.fetch_repos = _orig_fetch_repos
    GitHubClient.fetch_commits = _orig_fetch_commits
    GitHubClient.fetch_user_pr_issue_counts = _orig_fetch_user_pr_issue_counts
    yield
    GitHubClient.fetch_repos = _orig_fetch_repos
    GitHubClient.fetch_commits = _orig_fetch_commits
    GitHubClient.fetch_user_pr_issue_counts = _orig_fetch_user_pr_issue_counts
