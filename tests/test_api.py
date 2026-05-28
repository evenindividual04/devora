import time
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.db.models import Base
from app.db.session import engine
from app.main import app
from app.models.contracts import GitHubCommit, GitHubRepo
from app.services.github_client import CollaborationCounts, GitHubClient


async def _fake_fetch_repos(self, username: str, include_private: bool = False):
    _ = include_private
    return [
        GitHubRepo(name=f"{username}-infra", stars=10, forks=2, language="Python", updated_at=datetime.now(UTC)),
        GitHubRepo(name=f"{username}-web", stars=5, forks=1, language="TypeScript", updated_at=datetime.now(UTC)),
    ]


async def _fake_fetch_commits(self, username: str, repos=None, include_private: bool = False):
    _ = (username, repos, include_private)
    now = datetime.now(UTC)
    return [
        GitHubCommit(sha="1", message="feat: add API", committed_at=now, additions=20, deletions=4),
        GitHubCommit(sha="2", message="refactor: split module", committed_at=now, additions=12, deletions=10),
        GitHubCommit(sha="3", message="fix: edge case", committed_at=now, additions=8, deletions=2),
    ]


async def _fake_fetch_user_pr_issue_counts(self, username: str) -> tuple[int, int]:
    _ = username
    return 5, 3


async def _fake_fetch_user_collaboration_counts(self, username: str) -> CollaborationCounts:
    _ = username
    return CollaborationCounts(pr_count=5, reviewed_pr_count=2, issue_count=3, closed_issue_count=2)


async def _fake_fetch_repo_languages(self, username: str, repo_name: str) -> dict:
    _ = (username, repo_name)
    return {"Python": 8000, "Shell": 2000}


async def _fake_fetch_contributors(self, username: str, repo_name: str) -> list:
    _ = (username, repo_name)
    return [(username, 80), ("other", 20)]


GitHubClient.fetch_repos = _fake_fetch_repos
GitHubClient.fetch_commits = _fake_fetch_commits
GitHubClient.fetch_user_pr_issue_counts = _fake_fetch_user_pr_issue_counts
GitHubClient.fetch_user_collaboration_counts = _fake_fetch_user_collaboration_counts
GitHubClient.fetch_repo_languages = _fake_fetch_repo_languages
GitHubClient.fetch_contributors = _fake_fetch_contributors


def _wait_for_completed(client: TestClient, analysis_id: str, auth: dict, timeout_seconds: float = 3.0) -> None:
    start = time.time()
    while time.time() - start < timeout_seconds:
        status = client.get(f"/analysis/{analysis_id}/status", headers=auth)
        if status.status_code == 200 and status.json()["status"] == "completed":
            return
        time.sleep(0.05)
    raise AssertionError("analysis did not complete within timeout")


def _reset_db() -> None:
    import asyncio

    async def _drop_create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_drop_create())


def _register_and_auth(client: TestClient, email: str = "a@a.com") -> dict:
    reg = client.post("/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 200
    access = reg.json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


def test_list_analysis_requires_auth() -> None:
    _reset_db()
    with TestClient(app) as client:
        res = client.get("/analysis")
        assert res.status_code == 401


def test_run_and_share_flow_with_ownership() -> None:
    _reset_db()
    with TestClient(app) as client:
        auth = _register_and_auth(client)
        run = client.post(
            "/analysis/run",
            json={
                "username": "alice",
                "scope": "public",
                "honesty_mode": "authentic",
                "output_targets": ["readme", "report"],
                "include_private": False,
            },
            headers=auth,
        )
        assert run.status_code == 200
        analysis_id = run.json()["analysis_id"]
        _wait_for_completed(client, analysis_id, auth)

        share = client.post(f"/analysis/{analysis_id}/share", json={"ttl_minutes": 10}, headers=auth)
        assert share.status_code == 200
        token = share.json()["token"]

        shared = client.get(f"/share/{token}")
        assert shared.status_code == 200

        revoke = client.post(f"/shares/{token}/revoke", headers=auth)
        assert revoke.status_code == 200


def test_refresh_and_logout() -> None:
    _reset_db()
    with TestClient(app) as client:
        reg = client.post("/auth/register", json={"email": "b@b.com", "password": "password123"})
        assert reg.status_code == 200
        refresh_token = reg.json()["refresh_token"]

        refreshed = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert refreshed.status_code == 200
        access = refreshed.json()["access_token"]

        logout = client.post("/auth/logout", json={"refresh_token": refreshed.json()["refresh_token"]}, headers={"Authorization": f"Bearer {access}"})
        assert logout.status_code == 200


def test_health_ready() -> None:
    _reset_db()
    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        assert live.status_code == 200
        assert ready.status_code == 200
