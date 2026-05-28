# conftest.py: save originals before test_api.py's module-level patches overwrite them.
from __future__ import annotations

import pytest

from app.services.github_client import GitHubClient

_orig_fetch_repos = GitHubClient.fetch_repos
_orig_fetch_commits = GitHubClient.fetch_commits
_orig_fetch_user_pr_issue_counts = GitHubClient.fetch_user_pr_issue_counts
_orig_fetch_user_collaboration_counts = GitHubClient.fetch_user_collaboration_counts
_orig_fetch_repo_languages = GitHubClient.fetch_repo_languages
_orig_fetch_contributors = GitHubClient.fetch_contributors


@pytest.fixture
def restore_github_client():
    """Temporarily restore GitHubClient to its real implementation for unit tests.

    Saves the current class-level methods before restoring originals, and puts
    the saved (possibly monkey-patched by test_api.py) methods back on teardown.
    This prevents the fixture from permanently undoing test_api.py's patches.
    """
    saved = {
        "fetch_repos": GitHubClient.fetch_repos,
        "fetch_commits": GitHubClient.fetch_commits,
        "fetch_user_pr_issue_counts": GitHubClient.fetch_user_pr_issue_counts,
        "fetch_user_collaboration_counts": GitHubClient.fetch_user_collaboration_counts,
        "fetch_repo_languages": GitHubClient.fetch_repo_languages,
        "fetch_contributors": GitHubClient.fetch_contributors,
    }
    GitHubClient.fetch_repos = _orig_fetch_repos
    GitHubClient.fetch_commits = _orig_fetch_commits
    GitHubClient.fetch_user_pr_issue_counts = _orig_fetch_user_pr_issue_counts
    GitHubClient.fetch_user_collaboration_counts = _orig_fetch_user_collaboration_counts
    GitHubClient.fetch_repo_languages = _orig_fetch_repo_languages
    GitHubClient.fetch_contributors = _orig_fetch_contributors
    yield
    GitHubClient.fetch_repos = saved["fetch_repos"]
    GitHubClient.fetch_commits = saved["fetch_commits"]
    GitHubClient.fetch_user_pr_issue_counts = saved["fetch_user_pr_issue_counts"]
    GitHubClient.fetch_user_collaboration_counts = saved["fetch_user_collaboration_counts"]
    GitHubClient.fetch_repo_languages = saved["fetch_repo_languages"]
    GitHubClient.fetch_contributors = saved["fetch_contributors"]
