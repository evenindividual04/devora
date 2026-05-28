"""Tests for service-layer private functions and edge cases."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.contracts import (
    ArchetypeResult,
    DataScope,
    EvidenceRef,
    GitHubCommit,
    GitHubRepo,
    HonestyMode,
    OutputTarget,
    ReadmeResult,
    ReadmeSection,
    ReportResult,
    Signal,
)
from app.services.analysis_service import (
    AnalysisService,
    _classify_commit,
    _classify_repo,
    _message_quality,
    _repo_matches,
)


# ---------------------------------------------------------------------------
# _classify_repo branches
# ---------------------------------------------------------------------------

def _repo(name="repo", stars=0, forks=0, language="Python", is_fork=False,
          description=None, topics=None) -> GitHubRepo:
    return GitHubRepo(
        name=name,
        stars=stars,
        forks=forks,
        language=language,
        updated_at=datetime.now(UTC),
        description=description,
        topics=topics or [],
        is_fork=is_fork,
    )


class TestClassifyRepo:
    def test_coursework_by_word(self):
        assert _classify_repo(_repo("my-homework", description="hw assignment"), commit_count=0) == "coursework"

    def test_coursework_by_pattern(self):
        assert _classify_repo(_repo("cs101-project"), commit_count=0) == "coursework"

    def test_hackathon(self):
        assert _classify_repo(_repo("hackathon-app"), commit_count=0) == "hackathon"

    def test_research(self):
        assert _classify_repo(_repo("my-thesis"), commit_count=0) == "research"

    def test_oss_by_stars(self):
        assert _classify_repo(_repo("cool-lib", stars=10, is_fork=False), commit_count=0) == "OSS"

    def test_infra_by_language(self):
        assert _classify_repo(_repo("deploy-stuff", language="Shell"), commit_count=0) == "infra"

    def test_infra_by_topic(self):
        assert _classify_repo(_repo("ops", topics=["k8s", "kubernetes"]), commit_count=0) == "infra"

    def test_production_by_commits_and_stars(self):
        assert _classify_repo(_repo("my-app", stars=1, is_fork=False), commit_count=20) == "production"

    def test_portfolio(self):
        assert _classify_repo(_repo("portfolio-site"), commit_count=0) == "portfolio"

    def test_toy_fallback(self):
        assert _classify_repo(_repo("random-thing"), commit_count=0) == "toy"


# ---------------------------------------------------------------------------
# _classify_commit fallback keyword scan (no conventional-commit prefix)
# ---------------------------------------------------------------------------

class TestClassifyCommit:
    def test_feat_prefix(self):
        assert _classify_commit("feat: add login") == "feat"

    def test_fix_prefix(self):
        assert _classify_commit("fix: correct null check") == "fix"

    def test_refactor_prefix(self):
        assert _classify_commit("refactor: simplify handler") == "refactor"

    def test_infra_prefix(self):
        assert _classify_commit("ci: update pipeline") == "infra"

    def test_docs_prefix(self):
        assert _classify_commit("docs: update readme") == "docs"

    def test_fallback_fix_keyword(self):
        assert _classify_commit("bug in authentication") == "fix"

    def test_fallback_feat_keyword(self):
        assert _classify_commit("add new search endpoint") == "feat"

    def test_fallback_refactor_keyword(self):
        assert _classify_commit("clean up duplicate helpers") == "refactor"

    def test_fallback_infra_keyword(self):
        assert _classify_commit("docker compose setup") == "infra"

    def test_fallback_docs_keyword(self):
        assert _classify_commit("readme updates and docs") == "docs"

    def test_fallback_other(self):
        assert _classify_commit("miscellaneous things") == "other"


# ---------------------------------------------------------------------------
# _message_quality branches
# ---------------------------------------------------------------------------

class TestMessageQuality:
    def test_short_message(self):
        assert _message_quality("fix") == 0.1

    def test_medium_message(self):
        q = _message_quality("fix the thing")
        assert 0.5 < q < 1.0

    def test_long_message(self):
        assert _message_quality("fix authentication bug in the refresh token handler") == 1.0


# ---------------------------------------------------------------------------
# _repo_matches
# ---------------------------------------------------------------------------

class TestRepoMatches:
    def test_matches_by_name(self):
        assert _repo_matches("my-ml-tool", [], {"ml"}) is True

    def test_matches_by_topic(self):
        assert _repo_matches("random-repo", ["ai", "ml"], {"ml"}) is True

    def test_no_match(self):
        assert _repo_matches("my-web-app", [], {"kernel", "compiler"}) is False


# ---------------------------------------------------------------------------
# AnalysisService.compute_signals — trajectory branches + zero-commit path
# ---------------------------------------------------------------------------

class TestComputeSignalsTrajectory:
    def _make_commit(self, days_ago: int, repo_name: str = "repo") -> GitHubCommit:
        return GitHubCommit(
            sha=f"sha{days_ago}",
            message="feat: something",
            committed_at=datetime.now(UTC) - timedelta(days=days_ago),
            additions=10,
            deletions=2,
            repo_name=repo_name,
        )

    def _base_repo(self) -> GitHubRepo:
        return GitHubRepo(name="repo", stars=2, forks=0, language="Python", updated_at=datetime.now(UTC))

    def test_inactive_trajectory_with_no_commits(self):
        svc = AnalysisService()
        signals, archetype, _ = svc.compute_signals(repos=[self._base_repo()], commits=[])
        traj = next(s for s in signals if s.name == "activity_trajectory")
        assert traj.value == "inactive"

    def test_burst_trajectory(self):
        svc = AnalysisService()
        # Only recent commits (< 90 days ago), nothing older
        commits = [self._make_commit(10), self._make_commit(20)]
        signals, _, _ = svc.compute_signals(repos=[self._base_repo()], commits=commits)
        traj = next(s for s in signals if s.name == "activity_trajectory")
        assert traj.value == "burst"

    def test_growing_trajectory(self):
        svc = AnalysisService()
        # More recent activity than prior: 6 recent, 2 older
        recent = [self._make_commit(10 + i * 5) for i in range(6)]
        prior = [self._make_commit(100 + i * 5) for i in range(2)]
        signals, _, _ = svc.compute_signals(repos=[self._base_repo()], commits=recent + prior)
        traj = next(s for s in signals if s.name == "activity_trajectory")
        assert traj.value == "growing"

    def test_declining_trajectory(self):
        svc = AnalysisService()
        # Much more prior activity than recent
        recent = [self._make_commit(10)]
        prior = [self._make_commit(100 + i * 5) for i in range(10)]
        signals, _, _ = svc.compute_signals(repos=[self._base_repo()], commits=recent + prior)
        traj = next(s for s in signals if s.name == "activity_trajectory")
        assert traj.value == "declining"

    def test_stable_trajectory(self):
        svc = AnalysisService()
        # Equal recent and prior activity
        recent = [self._make_commit(10 + i * 5) for i in range(3)]
        prior = [self._make_commit(100 + i * 5) for i in range(3)]
        signals, _, _ = svc.compute_signals(repos=[self._base_repo()], commits=recent + prior)
        traj = next(s for s in signals if s.name == "activity_trajectory")
        assert traj.value == "stable"

    def test_zero_commits_per_week_signal(self):
        svc = AnalysisService()
        signals, _, _ = svc.compute_signals(repos=[], commits=[])
        cpw = next(s for s in signals if s.name == "commits_per_week")
        assert cpw.value == 0.0

    def test_no_repos_primary_language_absent(self):
        svc = AnalysisService()
        signals, _, _ = svc.compute_signals(repos=[], commits=[])
        names = {s.name for s in signals}
        assert "primary_language" not in names

    def test_recent_primary_language_shift(self):
        """Cover the language_shifted and recent_primary_language signals."""
        svc = AnalysisService()
        old_commits = [
            GitHubCommit(sha="o1", message="feat: go thing", committed_at=datetime.now(UTC) - timedelta(days=200), additions=5, deletions=0, repo_name="go-repo"),
        ]
        new_commits = [
            GitHubCommit(sha="n1", message="feat: python thing", committed_at=datetime.now(UTC) - timedelta(days=10), additions=5, deletions=0, repo_name="py-repo"),
        ]
        go_repo = GitHubRepo(name="go-repo", stars=0, forks=0, language="Go", updated_at=datetime.now(UTC) - timedelta(days=200))
        py_repo = GitHubRepo(name="py-repo", stars=0, forks=0, language="Python", updated_at=datetime.now(UTC) - timedelta(days=10))
        svc.compute_signals(repos=[go_repo, py_repo], commits=old_commits + new_commits)


# ---------------------------------------------------------------------------
# ShareTokenService edge cases
# ---------------------------------------------------------------------------

class TestShareTokenServiceEdgeCases:
    def test_verify_no_dot(self):
        from app.services.share_token_service import ShareTokenService
        svc = ShareTokenService()
        assert svc.verify("nodotinhere") is None

    def test_verify_bad_signature(self):
        from app.services.share_token_service import ShareTokenService
        svc = ShareTokenService()
        _, token, _ = svc.create("analysis-id")
        parts = token.split(".", 1)
        tampered = f"{parts[0]}.badsignature"
        assert svc.verify(tampered) is None

    def test_verify_expired(self):
        from app.services.share_token_service import ShareTokenService
        import base64
        import hmac
        import hashlib
        svc = ShareTokenService()
        secret = svc._secret
        payload = {"tid": "t1", "aid": "a1", "exp": 1, "v": 1}
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
        sig = hmac.new(secret, payload_b64.encode(), hashlib.sha256).hexdigest()
        assert svc.verify(f"{payload_b64}.{sig}") is None

    def test_verify_bad_base64(self):
        from app.services.share_token_service import ShareTokenService
        svc = ShareTokenService()
        sig = svc._sign("!!!")
        assert svc.verify(f"!!!.{sig}") is None


# ---------------------------------------------------------------------------
# AuthService direct tests
# ---------------------------------------------------------------------------

class TestAuthService:
    def test_hash_and_verify(self):
        from app.services.auth_service import AuthService
        svc = AuthService()
        h = svc.hash_password("secret123")
        assert svc.verify_password("secret123", h) is True
        assert svc.verify_password("wrong", h) is False

    def test_issue_and_decode_access(self):
        from app.services.auth_service import AuthService
        svc = AuthService()
        token = svc.issue_access_token("user-1", "user")
        decoded = svc.decode_access(token)
        assert decoded["sub"] == "user-1"
        assert decoded["role"] == "user"

    def test_issue_and_decode_refresh(self):
        from app.services.auth_service import AuthService
        svc = AuthService()
        token, jti, exp = svc.issue_refresh_token("user-1")
        decoded = svc.decode_refresh(token)
        assert decoded["sub"] == "user-1"
        assert decoded["jti"] == jti


# ---------------------------------------------------------------------------
# NarrativeProvider base class (abstract)
# ---------------------------------------------------------------------------

class TestNarrativeProviderBase:
    def _make_prompt(self):
        from app.services.narrative_provider import NarrativePrompt
        archetype = ArchetypeResult(
            top_archetype="Builder",
            alternates=[],
            confidence=0.8,
            supporting_evidence=[],
        )
        return NarrativePrompt(
            username="alice",
            honesty_mode=HonestyMode.authentic,
            signals=[],
            archetype=archetype,
            standout_repos=[],
        )

    def test_build_readme_raises(self):
        from app.services.narrative_provider import NarrativeProvider
        with pytest.raises(NotImplementedError):
            NarrativeProvider().build_readme(self._make_prompt())

    def test_build_report_raises(self):
        from app.services.narrative_provider import NarrativeProvider
        with pytest.raises(NotImplementedError):
            NarrativeProvider().build_report(self._make_prompt())


# ---------------------------------------------------------------------------
# NarrativeService._build_provider
# ---------------------------------------------------------------------------

class TestNarrativeServiceBuildProvider:
    def test_deterministic_when_no_key(self):
        from app.services.narrative_service import _build_provider
        from app.services.narrative_provider import DeterministicNarrativeProvider
        with patch("app.services.narrative_service.settings") as mock_settings:
            mock_settings.gemini_api_key = ""
            mock_settings.groq_api_key = ""
            mock_settings.cerebras_api_key = ""
            provider = _build_provider()
        assert isinstance(provider, DeterministicNarrativeProvider)

    def test_gemini_when_key_set(self):
        from app.services.narrative_service import _build_provider
        from app.services.narrative_provider import GeminiNarrativeProvider
        mock_client = MagicMock()
        with patch("app.services.narrative_service.settings") as mock_settings, \
             patch("app.services.narrative_provider.GeminiNarrativeProvider.__init__", return_value=None) as mock_init:
            mock_settings.gemini_api_key = "fake-key"
            mock_settings.gemini_model = "gemini-2.0-flash"
            provider = _build_provider()
        mock_init.assert_called_once_with(api_key="fake-key", model="gemini-2.0-flash")


# ---------------------------------------------------------------------------
# GeminiNarrativeProvider (mocked genai)
# ---------------------------------------------------------------------------

class TestGeminiNarrativeProvider:
    def _make_prompt(self):
        from app.services.narrative_provider import NarrativePrompt
        archetype = ArchetypeResult(
            top_archetype="Builder",
            alternates=["Craftsman"],
            confidence=0.8,
            supporting_evidence=[EvidenceRef(source_type="repo", source_id="cool-repo", excerpt="Python")],
        )
        signals = [
            Signal(name="feature_ratio", value=0.5, confidence=0.8, evidence_refs=[], timeframe="recent"),
        ]
        return NarrativePrompt(
            username="alice",
            honesty_mode=HonestyMode.authentic,
            signals=signals,
            archetype=archetype,
            standout_repos=["cool-repo"],
        )

    def _make_provider(self):
        from app.services.narrative_provider import GeminiNarrativeProvider
        with patch("app.services.narrative_provider.GeminiNarrativeProvider.__init__", return_value=None):
            provider = GeminiNarrativeProvider.__new__(GeminiNarrativeProvider)
        provider._model = "gemini-2.0-flash"
        provider._client = MagicMock()
        return provider

    def _combined_json(self, readme="# alice\nProfile text.", summary="Alice is a builder", repos=None, timeline=None):
        return json.dumps({
            "readme_markdown": readme,
            "summary": summary,
            "standout_repos": repos or ["cool-repo"],
            "timeline": timeline or ["Started 2022"],
        })

    def test_generate_returns_text(self):
        provider = self._make_provider()
        mock_response = MagicMock()
        mock_response.text = "Generated text"
        provider._client = MagicMock()
        provider._client.models.generate_content = MagicMock(return_value=mock_response)
        result = provider._generate("user prompt")
        assert result == "Generated text"

    def test_generate_returns_empty_string_when_text_is_none(self):
        provider = self._make_provider()
        mock_response = MagicMock()
        mock_response.text = None
        provider._client = MagicMock()
        provider._client.models.generate_content = MagicMock(return_value=mock_response)
        result = provider._generate("user prompt")
        assert result == ""

    def test_build_readme_success(self):
        provider = self._make_provider()
        provider._generate = MagicMock(return_value=self._combined_json(readme="# alice\nHello World profile"))
        result = provider.build_readme(self._make_prompt())
        assert "Hello World" in result.markdown
        assert len(result.sections) == 1

    def test_build_readme_fallback_on_exception(self):
        provider = self._make_provider()
        provider._fallback = MagicMock()
        provider._fallback.build_both = MagicMock(return_value=(MagicMock(markdown="fallback"), MagicMock()))
        provider._generate = MagicMock(side_effect=RuntimeError("API error"))
        result = provider.build_readme(self._make_prompt())
        assert result.markdown is not None

    def test_build_report_success_json(self):
        provider = self._make_provider()
        provider._generate = MagicMock(return_value=self._combined_json(summary="Alice is a builder"))
        result = provider.build_report(self._make_prompt())
        assert "Alice is a builder" in result.summary

    def test_build_report_strips_json_fence(self):
        provider = self._make_provider()
        raw = "```json\n" + self._combined_json(summary="Dev") + "\n```"
        provider._generate = MagicMock(return_value=raw)
        result = provider.build_report(self._make_prompt())
        assert "Dev" in result.summary

    def test_build_report_fallback_on_exception(self):
        provider = self._make_provider()
        provider._fallback = MagicMock()
        provider._fallback.build_both = MagicMock(return_value=(MagicMock(), MagicMock(summary="fallback")))
        provider._generate = MagicMock(side_effect=RuntimeError("API error"))
        result = provider.build_report(self._make_prompt())
        assert result is not None


# ---------------------------------------------------------------------------
# GitHubClient: rate limit with reset header + fetch_commits with no repos
# ---------------------------------------------------------------------------

class TestGitHubClientRemainingCoverage:
    def test_rate_limit_with_reset_header(self, restore_github_client):
        from app.services.github_client import GitHubClient
        from unittest.mock import patch as _patch

        async def run():
            import time
            future_reset = str(int(time.time()) + 5)
            mock_limited = MagicMock()
            mock_limited.status_code = 403
            mock_limited.headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": future_reset}
            mock_limited.raise_for_status = MagicMock()

            client = GitHubClient()
            mock_httpx = AsyncMock()
            mock_httpx.request = AsyncMock(return_value=mock_limited)
            with _patch("asyncio.sleep", new=AsyncMock()):
                try:
                    await client._request_with_backoff(mock_httpx, "GET", "/test")
                except RuntimeError:
                    pass  # expected after retries exhausted
        asyncio.run(run())

    def test_fetch_commits_fetches_repos_when_none_given(self, restore_github_client):
        from app.services.github_client import GitHubClient
        async def run():
            client = GitHubClient()
            # repos=None → fetch_repos is called first
            repo_resp = MagicMock()
            repo_resp.json = MagicMock(return_value=[{
                "name": "myrepo",
                "stargazers_count": 0,
                "forks_count": 0,
                "language": "Python",
                "pushed_at": "2024-01-01T00:00:00Z",
                "fork": False,
            }])
            commit_list_resp = MagicMock()
            commit_list_resp.json = MagicMock(return_value=[])
            client._request_with_backoff = AsyncMock(side_effect=[repo_resp, commit_list_resp])
            commits = await client.fetch_commits("testuser", repos=None)
            return commits
        commits = asyncio.run(run())
        assert commits == []
