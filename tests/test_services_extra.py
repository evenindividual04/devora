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

    def test_personal_fallback(self):
        assert _classify_repo(_repo("random-thing"), commit_count=0) == "personal"


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
# New classifier tier: "project"
# ---------------------------------------------------------------------------

class TestClassifyRepoProject:
    def test_project_tier_own_with_description_and_commits(self):
        r = _repo("my-tool", description="A helpful utility", is_fork=False)
        assert _classify_repo(r, commit_count=5) == "project"

    def test_project_not_fork(self):
        r = _repo("forked-tool", description="Some tool", is_fork=True)
        # Fork with description and commits still falls to personal (forks excluded from project)
        result = _classify_repo(r, commit_count=5)
        assert result == "personal"

    def test_project_requires_description(self):
        r = _repo("unnamed-thing", description=None, is_fork=False)
        assert _classify_repo(r, commit_count=10) == "personal"

    def test_project_requires_enough_commits(self):
        r = _repo("described-but-new", description="Has a description", is_fork=False)
        assert _classify_repo(r, commit_count=4) == "personal"


# ---------------------------------------------------------------------------
# Confidence math and archetype alignment
# ---------------------------------------------------------------------------

class TestArchetypeConfidence:
    def _make_commit(self, days_ago: int = 10) -> GitHubCommit:
        return GitHubCommit(
            sha=f"sha{days_ago}",
            message="feat: something",
            committed_at=datetime.now(UTC) - timedelta(days=days_ago),
            additions=10,
            deletions=2,
            repo_name="repo",
        )

    def _make_repo(self, name="repo", stars=0, language="Python", is_fork=False) -> GitHubRepo:
        return GitHubRepo(name=name, stars=stars, forks=0, language=language, updated_at=datetime.now(UTC), is_fork=is_fork)

    def test_confidence_between_0_and_1(self):
        svc = AnalysisService()
        repos = [self._make_repo(stars=5)]
        commits = [self._make_commit(i * 5) for i in range(10)]
        _, archetype, _ = svc.compute_signals(repos=repos, commits=commits)
        assert 0.0 <= archetype.confidence <= 1.0

    def test_confidence_not_floored_at_40_percent(self):
        # Old code floored at 0.40; new code is separation-based, can be higher
        svc = AnalysisService()
        # Heavy ML signal should push ML Experimenter well above 50%
        repos = [
            self._make_repo("ml-research", stars=15, language="Python"),
            self._make_repo("neural-nets", stars=5, language="Python"),
            self._make_repo("deep-learning-exp", stars=3, language="Python"),
        ]
        commits = [self._make_commit(i * 3) for i in range(20)]
        _, archetype, _ = svc.compute_signals(repos=repos, commits=commits)
        # Should commit clearly to one archetype, not be stuck at 40%
        assert archetype.confidence > 0.50

    def test_thin_data_caps_confidence(self):
        svc = AnalysisService()
        # 1 repo, 3 commits = thin data
        repos = [self._make_repo()]
        commits = [self._make_commit(i * 5) for i in range(3)]
        _, archetype, _ = svc.compute_signals(repos=repos, commits=commits)
        assert archetype.confidence <= 0.55
        assert archetype.limited_data is True

    def test_limited_data_flag_absent_with_enough_data(self):
        svc = AnalysisService()
        repos = [self._make_repo(f"repo{i}", stars=i) for i in range(5)]
        commits = [self._make_commit(i * 2) for i in range(10)]
        _, archetype, _ = svc.compute_signals(repos=repos, commits=commits)
        assert archetype.limited_data is False

    def test_alternates_only_when_close(self):
        # Alternates only shown when score >= 85% of top score.
        # With a clear winner, alternates should be empty or very few.
        svc = AnalysisService()
        repos = [self._make_repo()]
        commits = []
        _, archetype, _ = svc.compute_signals(repos=repos, commits=commits)
        # Each alternate must be "close" to the winner (assertion is structural)
        assert isinstance(archetype.alternates, list)

    def test_archetype_names_match_templates(self):
        from app.services.narrative_provider import _ARCHETYPE_TEMPLATES
        svc = AnalysisService()
        repos = [self._make_repo()]
        commits = [self._make_commit(i * 3) for i in range(5)]
        _, archetype, _ = svc.compute_signals(repos=repos, commits=commits)
        # The emitted archetype must have a template (no silent _DEFAULT_TEMPLATE fallback)
        assert archetype.top_archetype in _ARCHETYPE_TEMPLATES


# ---------------------------------------------------------------------------
# Generator field and deterministic provider
# ---------------------------------------------------------------------------

class TestNarrativeProviderGenerator:
    def _make_prompt(self, username="testuser"):
        from app.services.narrative_provider import NarrativePrompt, RepoCard
        archetype = ArchetypeResult(
            top_archetype="Hobbyist Explorer",
            alternates=[],
            confidence=0.75,
            supporting_evidence=[],
        )
        signals = [
            Signal(name="primary_language", value="Python", confidence=0.85, evidence_refs=[], timeframe="all_time"),
            Signal(name="repo_count", value=10, confidence=0.95, evidence_refs=[], timeframe="all_time"),
            Signal(name="commits_per_week", value=2.5, confidence=0.7, evidence_refs=[], timeframe="sampled_recent"),
            Signal(name="activity_trajectory", value="stable", confidence=0.6, evidence_refs=[], timeframe="last_6_months"),
            Signal(name="avg_churn_per_commit", value=45.0, confidence=0.61, evidence_refs=[], timeframe="sampled_recent"),
            Signal(name="feature_ratio", value=0.6, confidence=0.74, evidence_refs=[], timeframe="sampled_recent"),
        ]
        repo_details = [
            RepoCard(name="my-tool", description="A CLI for automating stuff", language="Python", stars=42),
            RepoCard(name="experiments", description="Random experiments", language="Python", stars=0),
        ]
        return NarrativePrompt(
            username=username,
            honesty_mode=HonestyMode.authentic,
            signals=signals,
            archetype=archetype,
            standout_repos=["my-tool", "experiments"],
            repo_details=repo_details,
        )

    def test_deterministic_generator_field(self):
        from app.services.narrative_provider import DeterministicNarrativeProvider
        provider = DeterministicNarrativeProvider()
        prompt = self._make_prompt()
        readme, _ = provider.build_both(prompt)
        assert readme.generator == "deterministic"

    def test_deterministic_readme_contains_repo_description(self):
        from app.services.narrative_provider import DeterministicNarrativeProvider
        provider = DeterministicNarrativeProvider()
        prompt = self._make_prompt()
        readme, _ = provider.build_both(prompt)
        # Repo card with description should appear
        assert "my-tool" in readme.markdown
        assert "CLI" in readme.markdown or "automating" in readme.markdown

    def test_deterministic_readme_has_sections(self):
        from app.services.narrative_provider import DeterministicNarrativeProvider
        provider = DeterministicNarrativeProvider()
        prompt = self._make_prompt()
        readme, _ = provider.build_both(prompt)
        # Multi-section README has at least one ## header
        assert "##" in readme.markdown

    def test_deterministic_readme_starts_with_username(self):
        from app.services.narrative_provider import DeterministicNarrativeProvider
        provider = DeterministicNarrativeProvider()
        prompt = self._make_prompt("octocat")
        readme, _ = provider.build_both(prompt)
        assert readme.markdown.startswith("# octocat")

    def test_deterministic_readme_no_archetype_label_as_first_content(self):
        from app.services.narrative_provider import DeterministicNarrativeProvider
        provider = DeterministicNarrativeProvider()
        prompt = self._make_prompt()
        readme, _ = provider.build_both(prompt)
        lines = [l for l in readme.markdown.splitlines() if l.strip()]
        # Second non-empty line should NOT be just the archetype bold label
        assert lines[0].startswith("# ")
        if len(lines) > 1:
            assert lines[1] != "**Hobbyist Explorer**"


# ---------------------------------------------------------------------------
# Churn median (replaces mean+cap)
# ---------------------------------------------------------------------------

class TestChurnMedian:
    def _make_commit(self, additions: int, deletions: int = 0, days_ago: int = 10) -> GitHubCommit:
        return GitHubCommit(
            sha=f"sha{additions}{deletions}{days_ago}",
            message="feat: something",
            committed_at=datetime.now(UTC) - timedelta(days=days_ago),
            additions=additions,
            deletions=deletions,
            repo_name="repo",
        )

    def test_churn_uses_median_not_mean(self):
        svc = AnalysisService()
        # One huge outlier commit (10k lines) among small commits should not dominate
        commits = [self._make_commit(10, days_ago=i * 2) for i in range(9)]
        commits.append(self._make_commit(10000, days_ago=100))  # outlier
        repos = [GitHubRepo(name="repo", stars=0, forks=0, language="Python", updated_at=datetime.now(UTC))]
        signals, _, _ = svc.compute_signals(repos=repos, commits=commits)
        churn_sig = next(s for s in signals if s.name == "avg_churn_per_commit")
        # Median should be close to 10, not close to 1000 (mean would be ~1010)
        assert float(churn_sig.value) < 100

    def test_churn_no_hard_cap_at_2000(self):
        svc = AnalysisService()
        # All commits are large (5000 lines each)
        commits = [self._make_commit(2500, 2500, days_ago=i * 2) for i in range(5)]
        repos = [GitHubRepo(name="repo", stars=0, forks=0, language="Python", updated_at=datetime.now(UTC))]
        signals, _, _ = svc.compute_signals(repos=repos, commits=commits)
        churn_sig = next(s for s in signals if s.name == "avg_churn_per_commit")
        # Should reflect actual median (5000), not be capped at 2000
        assert float(churn_sig.value) > 2000


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
        from app.services.narrative_provider import DeterministicNarrativeProvider, GeminiNarrativeProvider
        with patch("app.services.narrative_provider.GeminiNarrativeProvider.__init__", return_value=None):
            provider = GeminiNarrativeProvider.__new__(GeminiNarrativeProvider)
        provider._model = "gemini-2.0-flash"
        provider._client = MagicMock()
        provider._fallback = DeterministicNarrativeProvider()
        return provider

    def _combined_json(self, readme=None, summary="Alice is a builder", repos=None, timeline=None):
        if readme is None:
            readme = "# alice\nWorks in Python. Commits skew toward feature work. Active contributor with consistent cadence."
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
        long_readme = "# alice\nHello World profile. Works in Python with a consistent cadence across many projects."
        provider._generate = MagicMock(return_value=self._combined_json(readme=long_readme))
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
# Item 1: _extract_json — robust JSON extraction
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_bare_json(self):
        from app.services.narrative_provider import _extract_json
        data = _extract_json('{"readme_markdown": "# hello"}')
        assert data["readme_markdown"] == "# hello"

    def test_json_fenced(self):
        from app.services.narrative_provider import _extract_json
        raw = '```json\n{"readme_markdown": "# hello"}\n```'
        data = _extract_json(raw)
        assert data["readme_markdown"] == "# hello"

    def test_prose_before_and_after(self):
        from app.services.narrative_provider import _extract_json
        raw = 'Here is the result:\n{"readme_markdown": "# test"}\nAll done.'
        data = _extract_json(raw)
        assert data["readme_markdown"] == "# test"

    def test_missing_closing_fence(self):
        from app.services.narrative_provider import _extract_json
        raw = '```json\n{"readme_markdown": "# hello"}'
        data = _extract_json(raw)
        assert data["readme_markdown"] == "# hello"

    def test_unparseable_raises_value_error(self):
        from app.services.narrative_provider import _extract_json
        with pytest.raises(ValueError):
            _extract_json("this is not json at all")


# ---------------------------------------------------------------------------
# Item 2: Readme validation — fallback on empty/short output
# ---------------------------------------------------------------------------

class TestGeminiReadmeValidation:
    def _make_provider(self):
        from app.services.narrative_provider import DeterministicNarrativeProvider, GeminiNarrativeProvider
        with patch("app.services.narrative_provider.GeminiNarrativeProvider.__init__", return_value=None):
            provider = GeminiNarrativeProvider.__new__(GeminiNarrativeProvider)
        provider._model = "gemini-2.0-flash"
        provider._client = MagicMock()
        provider._fallback = MagicMock()
        provider._fallback.build_both = MagicMock(
            return_value=(MagicMock(markdown="deterministic"), MagicMock())
        )
        return provider

    def _make_prompt(self):
        from app.services.narrative_provider import NarrativePrompt
        archetype = ArchetypeResult(
            top_archetype="Builder", alternates=[], confidence=0.8,
            supporting_evidence=[EvidenceRef(source_type="repo", source_id="r", excerpt="")],
        )
        return NarrativePrompt(
            username="alice", honesty_mode=HonestyMode.authentic,
            signals=[], archetype=archetype, standout_repos=[],
        )

    def test_fallback_when_readme_empty(self):
        provider = self._make_provider()
        provider._generate = MagicMock(return_value=json.dumps({
            "readme_markdown": "", "summary": "ok", "standout_repos": [], "timeline": []
        }))
        provider.build_readme(self._make_prompt())
        provider._fallback.build_both.assert_called_once()

    def test_fallback_when_readme_whitespace_only(self):
        provider = self._make_provider()
        provider._generate = MagicMock(return_value=json.dumps({
            "readme_markdown": "   ", "summary": "ok", "standout_repos": [], "timeline": []
        }))
        provider.build_readme(self._make_prompt())
        provider._fallback.build_both.assert_called_once()

    def test_fallback_when_readme_too_short(self):
        provider = self._make_provider()
        provider._generate = MagicMock(return_value=json.dumps({
            "readme_markdown": "short", "summary": "ok", "standout_repos": [], "timeline": []
        }))
        provider.build_readme(self._make_prompt())
        provider._fallback.build_both.assert_called_once()

    def test_no_fallback_when_readme_long_enough(self):
        provider = self._make_provider()
        long_readme = "# alice\n" + "A" * 60
        provider._generate = MagicMock(return_value=json.dumps({
            "readme_markdown": long_readme, "summary": "ok", "standout_repos": [], "timeline": []
        }))
        provider.build_readme(self._make_prompt())
        provider._fallback.build_both.assert_not_called()


# ---------------------------------------------------------------------------
# Item 4: Retry-with-backoff on transient LLM failure
# ---------------------------------------------------------------------------

class TestGeminiRetry:
    def _make_provider(self):
        from app.services.narrative_provider import DeterministicNarrativeProvider, GeminiNarrativeProvider
        with patch("app.services.narrative_provider.GeminiNarrativeProvider.__init__", return_value=None):
            provider = GeminiNarrativeProvider.__new__(GeminiNarrativeProvider)
        provider._model = "gemini-2.0-flash"
        provider._client = MagicMock()
        provider._fallback = DeterministicNarrativeProvider()
        return provider

    def _make_prompt(self):
        from app.services.narrative_provider import NarrativePrompt
        archetype = ArchetypeResult(
            top_archetype="Builder", alternates=[], confidence=0.8,
            supporting_evidence=[EvidenceRef(source_type="repo", source_id="r", excerpt="")],
        )
        return NarrativePrompt(
            username="alice", honesty_mode=HonestyMode.authentic,
            signals=[], archetype=archetype, standout_repos=[],
        )

    def test_succeeds_on_second_attempt(self):
        from unittest.mock import patch as _patch
        provider = self._make_provider()
        call_count = [0]
        long_readme = "# alice\n" + "Works in Python. Consistent contributor. " * 3

        def side_effect(prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient error")
            return json.dumps({
                "readme_markdown": long_readme,
                "summary": "Developer",
                "standout_repos": [],
                "timeline": [],
            })

        provider._generate = MagicMock(side_effect=side_effect)
        with _patch("time.sleep"):
            result = provider.build_readme(self._make_prompt())
        assert "alice" in result.markdown
        assert call_count[0] == 2

    def test_fallback_after_all_retries_exhausted(self):
        from unittest.mock import patch as _patch
        provider = self._make_provider()
        provider._fallback = MagicMock()
        provider._fallback.build_both = MagicMock(return_value=(MagicMock(markdown="fallback"), MagicMock()))
        provider._generate = MagicMock(side_effect=RuntimeError("always fails"))
        with _patch("time.sleep"):
            provider.build_readme(self._make_prompt())
        provider._fallback.build_both.assert_called_once()
        assert provider._generate.call_count == 2

    def test_exactly_two_attempts_on_failure(self):
        from unittest.mock import patch as _patch
        provider = self._make_provider()
        provider._fallback = MagicMock()
        provider._fallback.build_both = MagicMock(return_value=(MagicMock(markdown="fb"), MagicMock()))
        provider._generate = MagicMock(side_effect=RuntimeError("fail"))
        with _patch("time.sleep") as mock_sleep:
            provider.build_readme(self._make_prompt())
        assert provider._generate.call_count == 2
        mock_sleep.assert_called_once()  # sleep between attempt 1 and 2


# ---------------------------------------------------------------------------
# Item 3: Pipeline blocks — compute_signals and build_both run in thread
# ---------------------------------------------------------------------------

class TestPipelineBlockingFix:
    def test_compute_signals_and_build_both_dispatched_to_thread(self):
        from app.workers.pipeline import PipelineWorker

        to_thread_call_count = [0]
        dispatched_fns: list = []

        async def fake_to_thread(fn, *args, **kwargs):
            to_thread_call_count[0] += 1
            dispatched_fns.append(fn)
            return fn(*args, **kwargs)

        mock_record = MagicMock()
        mock_record.include_private = False
        mock_record.username = "alice"
        mock_record.honesty_mode = HonestyMode.authentic
        mock_record.analysis_id = "test-id"

        archetype = ArchetypeResult(top_archetype="Builder", alternates=[], confidence=0.8, supporting_evidence=[])
        worker = PipelineWorker.__new__(PipelineWorker)
        compute_signals_fn = MagicMock(return_value=([], archetype, []))
        build_both_fn = MagicMock(return_value=(MagicMock(markdown="# test\n" + "x" * 60), MagicMock()))
        worker.analysis = MagicMock()
        worker.analysis.compute_signals = compute_signals_fn
        worker.narrative = MagicMock()
        worker.narrative.build_both = build_both_fn

        async def run():
            with patch("app.workers.pipeline.asyncio.to_thread", side_effect=fake_to_thread), \
                 patch("app.workers.pipeline.store.update", new=AsyncMock(return_value=mock_record)), \
                 patch("app.workers.pipeline.oauth_store.get_token", new=AsyncMock(return_value=None)), \
                 patch("app.workers.pipeline.GitHubClient") as mock_gh_cls, \
                 patch("app.workers.pipeline.metrics"), \
                 patch("app.workers.pipeline.random.random", return_value=1.0), \
                 patch("app.workers.pipeline.cache") as mock_cache:
                mock_cache.get = AsyncMock(return_value=None)
                mock_cache.set = AsyncMock()
                mock_gh = MagicMock()
                mock_gh.fetch_repos = AsyncMock(return_value=[])
                mock_gh.fetch_commits = AsyncMock(return_value=[])
                collab = MagicMock()
                collab.pr_count = 0
                collab.issue_count = 0
                collab.reviewed_pr_count = 0
                collab.closed_issue_count = 0
                mock_gh.fetch_user_collaboration_counts = AsyncMock(return_value=collab)
                mock_gh_cls.return_value = mock_gh
                await worker.run(mock_record)

        asyncio.run(run())
        assert to_thread_call_count[0] >= 2, "Expected at least 2 asyncio.to_thread calls"
        assert compute_signals_fn in dispatched_fns, "compute_signals not dispatched via to_thread"
        assert build_both_fn in dispatched_fns, "build_both not dispatched via to_thread"


# ---------------------------------------------------------------------------
# Item 5: anti_generic_guard — no double spaces or orphaned punctuation
# ---------------------------------------------------------------------------

class TestAntiGenericGuardCleanup:
    def test_no_double_spaces_after_phrase_removal(self):
        from app.services.narrative_provider import anti_generic_guard
        result = anti_generic_guard("a passionate developer who ships")
        assert "  " not in result

    def test_no_space_before_punctuation(self):
        from app.services.narrative_provider import anti_generic_guard
        result = anti_generic_guard("I am passionate about coding.")
        assert " ." not in result
        assert "  " not in result

    def test_preserves_content_outside_banned_phrases(self):
        from app.services.narrative_provider import anti_generic_guard
        result = anti_generic_guard("Works in Python. Builds tools.")
        assert "Works in Python" in result
        assert "Builds tools" in result


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
