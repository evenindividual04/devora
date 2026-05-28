from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.core.config import settings
from app.models.contracts import GitHubCommit, GitHubRepo


@dataclass
class CollaborationCounts:
    pr_count: int
    reviewed_pr_count: int
    issue_count: int
    closed_issue_count: int


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _request_with_backoff(self, client: httpx.AsyncClient, method: str, path: str, params: dict | None = None):
        delay = 1.0
        for _ in range(4):
            resp = await client.request(method, path, params=params, headers=self._headers())
            if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
                reset = resp.headers.get("x-ratelimit-reset")
                if reset:
                    wait_for = max(1, int(reset) - int(datetime.now(UTC).timestamp()))
                    await asyncio.sleep(min(wait_for, 10))
                else:
                    await asyncio.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("GitHub API rate limit retries exhausted")

    @staticmethod
    def _next_page_url(link_header: str | None) -> str | None:
        if not link_header:
            return None
        for part in link_header.split(","):
            url_part, *rel_parts = part.strip().split(";")
            if any('rel="next"' in r for r in rel_parts):
                return url_part.strip().lstrip("<").rstrip(">")
        return None

    def _parse_repo(self, r: dict) -> GitHubRepo:
        pushed = r.get("pushed_at") or r.get("updated_at")
        return GitHubRepo(
            name=r["name"],
            stars=r.get("stargazers_count", 0),
            forks=r.get("forks_count", 0),
            language=r.get("language") or "Unknown",
            updated_at=datetime.fromisoformat(pushed.replace("Z", "+00:00")),
            description=r.get("description"),
            topics=r.get("topics") or [],
            is_fork=r.get("fork", False),
        )

    async def fetch_repos(self, username: str, include_private: bool = False) -> list[GitHubRepo]:
        limit = settings.github_max_repos
        per_page = min(limit, 100)
        # Use /user/repos only when fetching the token owner's own private repos
        if include_private and self.token:
            visibility = "all"
            path = "/user/repos"
        else:
            visibility = "public"
            path = f"/users/{username}/repos"
        repos: list[GitHubRepo] = []

        async with httpx.AsyncClient(base_url=settings.github_api_base, timeout=30.0) as client:
            next_url: str | None = f"{settings.github_api_base}{path}"
            params: dict | None = {"per_page": per_page, "sort": "updated", "visibility": visibility}

            while next_url and len(repos) < limit:
                resp = await self._request_with_backoff(client, "GET", next_url, params=params)
                params = None  # only sent on first request; subsequent URLs are fully qualified
                raw: list[dict] = resp.json()
                if self.token and raw and raw[0].get("owner", {}).get("login", "") != username:
                    raw = [r for r in raw if r.get("owner", {}).get("login") == username]
                for r in raw:
                    if len(repos) >= limit:
                        break
                    repos.append(self._parse_repo(r))
                next_url = self._next_page_url(resp.headers.get("Link"))

        return repos

    async def fetch_commits(
        self,
        username: str,
        repos: list[GitHubRepo] | None = None,
        include_private: bool = False,
    ) -> list[GitHubCommit]:
        if repos is None:
            repos = await self.fetch_repos(username, include_private=include_private)
        commits: list[GitHubCommit] = []
        async with httpx.AsyncClient(base_url=settings.github_api_base, timeout=30.0) as client:
            for repo in repos[: settings.github_max_repos]:
                path = f"/repos/{username}/{repo.name}/commits"
                try:
                    resp = await self._request_with_backoff(
                        client, "GET", path, params={"per_page": settings.github_commits_per_repo}
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 409:
                        continue  # empty repo
                    raise
                for c in resp.json():
                    detail = await self._request_with_backoff(client, "GET", f"/repos/{username}/{repo.name}/commits/{c['sha']}")
                    d = detail.json()
                    commit_obj = d.get("commit", {})
                    committed_at = commit_obj.get("committer", {}).get("date")
                    author_date_str = commit_obj.get("author", {}).get("date")
                    stats = d.get("stats", {})
                    if not committed_at:
                        continue
                    author_info = d.get("author") or {}
                    file_names = [f["filename"] for f in d.get("files", []) if "filename" in f]
                    commits.append(
                        GitHubCommit(
                            sha=d["sha"],
                            message=commit_obj.get("message", ""),
                            committed_at=datetime.fromisoformat(committed_at.replace("Z", "+00:00")),
                            additions=stats.get("additions", 0),
                            deletions=stats.get("deletions", 0),
                            repo_name=repo.name,
                            author_login=author_info.get("login"),
                            author_date=datetime.fromisoformat(author_date_str.replace("Z", "+00:00")) if author_date_str else None,
                            committer_date=datetime.fromisoformat(committed_at.replace("Z", "+00:00")),
                            file_names=file_names,
                        )
                    )
        return commits

    async def fetch_user_pr_issue_counts(self, username: str) -> tuple[int, int]:
        """Deprecated: use fetch_user_collaboration_counts instead."""
        cc = await self.fetch_user_collaboration_counts(username)
        return cc.pr_count, cc.issue_count

    async def fetch_user_collaboration_counts(self, username: str) -> CollaborationCounts:
        """Return collaboration counts (authored PRs, reviewed PRs, issues, closed issues)."""
        async with httpx.AsyncClient(base_url=settings.github_api_base, timeout=15.0) as client:
            try:
                pr_resp = await self._request_with_backoff(
                    client, "GET", "/search/issues",
                    params={"q": f"type:pr author:{username}", "per_page": 1},
                )
                reviewed_resp = await self._request_with_backoff(
                    client, "GET", "/search/issues",
                    params={"q": f"type:pr reviewed-by:{username}", "per_page": 1},
                )
                issue_resp = await self._request_with_backoff(
                    client, "GET", "/search/issues",
                    params={"q": f"type:issue author:{username}", "per_page": 1},
                )
                closed_resp = await self._request_with_backoff(
                    client, "GET", "/search/issues",
                    params={"q": f"type:issue author:{username} is:closed", "per_page": 1},
                )
                return CollaborationCounts(
                    pr_count=pr_resp.json().get("total_count", 0),
                    reviewed_pr_count=reviewed_resp.json().get("total_count", 0),
                    issue_count=issue_resp.json().get("total_count", 0),
                    closed_issue_count=closed_resp.json().get("total_count", 0),
                )
            except Exception:
                return CollaborationCounts(0, 0, 0, 0)

    async def fetch_repo_languages(self, username: str, repo_name: str) -> dict[str, int]:
        """Return byte map {language: bytes} for a repo via /repos/{owner}/{repo}/languages."""
        async with httpx.AsyncClient(base_url=settings.github_api_base, timeout=15.0) as client:
            try:
                resp = await self._request_with_backoff(
                    client, "GET", f"/repos/{username}/{repo_name}/languages"
                )
                return resp.json()
            except Exception:
                return {}

    async def fetch_contributors(self, username: str, repo_name: str) -> list[tuple[str, int]]:
        """Return [(login, contributions)] for a repo, sorted by contributions desc."""
        async with httpx.AsyncClient(base_url=settings.github_api_base, timeout=15.0) as client:
            try:
                resp = await self._request_with_backoff(
                    client, "GET", f"/repos/{username}/{repo_name}/contributors",
                    params={"per_page": 100, "anon": "false"},
                )
                return [(c["login"], c["contributions"]) for c in resp.json() if "login" in c]
            except Exception:
                return []
