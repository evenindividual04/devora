from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from datetime import UTC, datetime, timedelta

from app.models.contracts import ArchetypeResult, EvidenceRef, GitHubCommit, GitHubRepo, Signal

_TRIVIAL_EXTENSIONS = {".md", ".txt", ".yml", ".yaml", ".json", ".lock", ".gitignore", ".cfg", ".ini", ".toml", ".rst", ".xml"}
_BOT_LOGINS = {"dependabot", "github-actions", "renovate", "snyk-bot", "greenkeeper"}


def _is_bot_commit(commit: GitHubCommit) -> bool:
    login = commit.author_login
    if login is None:
        return False
    login_lower = login.lower()
    if "[bot]" in login_lower:
        return True
    return any(bot in login_lower for bot in _BOT_LOGINS)


def _touches_source(commit: GitHubCommit) -> bool:
    """True when commit changes at least one non-trivial source file."""
    if not commit.file_names:
        return True  # unknown → conservative assumption
    return any(
        not any(f.endswith(ext) for ext in _TRIVIAL_EXTENSIONS)
        for f in commit.file_names
    )


def _language_entropy(byte_map: dict[str, int]) -> float:
    """Byte-weighted Shannon entropy H = -Σ pᵢ log₂ pᵢ."""
    total = sum(byte_map.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in byte_map.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy

_FEAT_PREFIXES = {"feat", "add", "new", "create", "introduce", "implement"}
_FIX_PREFIXES = {"fix", "bug", "patch", "resolve", "hotfix", "repair", "revert"}
_REFACTOR_PREFIXES = {"refactor", "clean", "restructure", "rename", "move", "reorganize", "simplify"}
_INFRA_PREFIXES = {"ci", "docker", "deploy", "config", "build", "deps", "chore", "release", "bump", "version", "devops"}
_DOCS_PREFIXES = {"docs", "readme", "doc", "documentation", "comment", "changelog"}

_ML_KEYWORDS = {"ml", "model", "train", "data", "deep", "llm", "ai", "nlp", "neural", "inference", "embedding", "vector", "torch", "tensorflow", "keras"}
_SYSTEMS_KEYWORDS = {"kernel", "runtime", "compiler", "vm", "scheduler", "allocator", "memory", "concurrency", "distributed", "consensus", "raft", "grpc"}
_TOOLING_KEYWORDS = {"cli", "tool", "sdk", "lib", "library", "plugin", "extension", "framework", "util"}
_INFRA_KEYWORDS = {"infra", "k8s", "kubernetes", "terraform", "ansible", "helm", "cloud", "aws", "gcp", "azure", "monitoring", "observability"}

_COURSEWORK_WORDS = {"hw", "homework", "assignment", "leetcode", "leet", "dsa", "exercises", "tutorial", "pset", "problem", "solutions"}
_COURSEWORK_PATTERN = re.compile(r"^(cs|cse|ece|ee|cop|cis)\d+", re.IGNORECASE)
_HACKATHON_WORDS = {"hackathon", "hacktoberfest"}
_RESEARCH_WORDS = {"paper", "thesis", "research", "experiment", "experiments", "reproduce", "replication", "arxiv", "survey"}
_INFRA_LANGS = {"Shell", "HCL", "Dockerfile"}
_PORTFOLIO_WORDS = {"portfolio", "showcase", "resume", "cv"}


def _score_repo(repo: GitHubRepo, commit_count: int, six_months_ago: datetime) -> float:
    score = 0.0
    score += min(repo.stars * 0.5, 20.0)          # community adoption, capped
    score += min(commit_count * 0.3, 6.0)          # depth of work
    if repo.updated_at >= six_months_ago:
        score += 3.0                               # actively maintained
    if not repo.is_fork:
        score += 2.0                               # original work
    type_bonus = {"OSS": 4.0, "production": 3.0, "project": 2.5, "research": 2.0, "infra": 1.5, "portfolio": 1.0}
    score += type_bonus.get(_classify_repo(repo, commit_count), 0.0)
    return score


def _classify_repo(repo: GitHubRepo, commit_count: int) -> str:
    name_parts = set(re.split(r"[-_.\s]", repo.name.lower()))
    topic_words = {t.lower() for t in repo.topics}
    desc_words = set(re.split(r"\W+", (repo.description or "").lower())) - {""}
    all_words = name_parts | topic_words | desc_words

    if bool(all_words & _COURSEWORK_WORDS) or _COURSEWORK_PATTERN.match(repo.name):
        return "coursework"
    if bool(all_words & _HACKATHON_WORDS):
        return "hackathon"
    if bool(all_words & _RESEARCH_WORDS):
        return "research"
    if not repo.is_fork and repo.stars >= 10:
        return "OSS"
    if (repo.language in _INFRA_LANGS) or bool(all_words & _INFRA_KEYWORDS):
        return "infra"
    if not repo.is_fork and commit_count >= 15 and repo.stars > 0:
        return "production"
    if bool(all_words & _PORTFOLIO_WORDS):
        return "portfolio"
    if not repo.is_fork and commit_count >= 5 and bool(repo.description):
        return "project"
    return "personal"


def _classify_commit(message: str) -> str:
    """Return the dominant commit type for a message."""
    first_line = message.split("\n")[0].lower().strip()
    # Conventional commits: "type: description" or "type(scope): description"
    m = re.match(r"^(\w+)(?:\([^)]+\))?:\s*", first_line)
    if m:
        prefix = m.group(1)
        if prefix in _FEAT_PREFIXES:
            return "feat"
        if prefix in _FIX_PREFIXES:
            return "fix"
        if prefix in _REFACTOR_PREFIXES:
            return "refactor"
        if prefix in _INFRA_PREFIXES:
            return "infra"
        if prefix in _DOCS_PREFIXES:
            return "docs"
    # Fallback: keyword scan in first line
    words = set(re.findall(r"\b\w+\b", first_line))
    if words & _FIX_PREFIXES:
        return "fix"
    if words & _FEAT_PREFIXES:
        return "feat"
    if words & _REFACTOR_PREFIXES:
        return "refactor"
    if words & _INFRA_PREFIXES:
        return "infra"
    if words & _DOCS_PREFIXES:
        return "docs"
    return "other"


def _message_quality(message: str) -> float:
    """Score 0-1: penalises one-word/wip/vague messages."""
    first = message.split("\n")[0].strip()
    if len(first) < 10:
        return 0.1
    boring = {"wip", "update", "fix", "cleanup", "changes", "misc", "temp", "test"}
    if first.lower() in boring:  # pragma: no cover
        return 0.2  # pragma: no cover
    if len(first) > 30:
        return 1.0
    return 0.6


def _repo_matches(name: str, topics: list[str], keywords: set[str]) -> bool:
    parts = set(re.split(r"[-_]", name.lower())) | {t.lower() for t in topics}
    return bool(parts & keywords)


class AnalysisService:
    def compute_signals(
        self,
        repos: list[GitHubRepo],
        commits: list[GitHubCommit],
        pr_count: int = 0,
        issue_count: int = 0,
        reviewed_pr_count: int = 0,
        closed_issue_count: int = 0,
        repo_languages: dict[str, dict[str, int]] | None = None,
        contributors: dict[str, list[tuple[str, int]]] | None = None,
        username: str | None = None,
    ) -> tuple[list[Signal], ArchetypeResult, list[str]]:
        signals: list[Signal] = []
        now = datetime.now(UTC)
        six_months_ago = now - timedelta(days=180)

        # ── Commit classification ──────────────────────────────────────────
        type_counts: Counter[str] = Counter()
        for c in commits:
            type_counts[_classify_commit(c.message)] += 1
        total = len(commits) or 1

        commit_evidence = [
            EvidenceRef(source_type="commit", source_id=c.sha, excerpt=c.message.split("\n")[0][:80])
            for c in commits[:5]
        ]

        def _ratio_signal(name: str, key: str, confidence: float) -> Signal:
            return Signal(
                name=name,
                value=round(type_counts[key] / total, 3),
                confidence=confidence,
                evidence_refs=commit_evidence,
                timeframe="sampled_recent",
            )

        signals.append(_ratio_signal("feature_ratio", "feat", 0.74))
        signals.append(_ratio_signal("fix_ratio", "fix", 0.74))
        signals.append(_ratio_signal("refactor_ratio", "refactor", 0.68))
        signals.append(_ratio_signal("infra_ratio", "infra", 0.65))
        signals.append(_ratio_signal("docs_ratio", "docs", 0.62))

        # ── Message quality ────────────────────────────────────────────────
        msg_quality = sum(_message_quality(c.message) for c in commits) / (len(commits) or 1)
        signals.append(Signal(
            name="commit_message_quality",
            value=round(msg_quality, 3),
            confidence=0.60,
            evidence_refs=commit_evidence,
            timeframe="sampled_recent",
        ))

        # ── Churn & commit size ────────────────────────────────────────────
        # Use median of human, source-touching commits to resist outliers and bots.
        source_commits = [c for c in commits if not _is_bot_commit(c) and _touches_source(c)]
        churn_values = [c.additions + c.deletions for c in source_commits]
        if not churn_values:
            churn_values = [c.additions + c.deletions for c in commits]
        median_churn = statistics.median(churn_values) if churn_values else 0.0
        signals.append(Signal(
            name="avg_churn_per_commit",
            value=round(median_churn, 1),
            confidence=0.61,
            evidence_refs=commit_evidence,
            timeframe="sampled_recent",
        ))

        # ── Activity consistency (commits/week estimate) ───────────────────
        if commits:
            oldest = min(c.committed_at for c in commits)
            span_days = max((now - oldest).days, 1)
            commits_per_week = len(commits) / (span_days / 7)
        else:
            commits_per_week = 0.0
        signals.append(Signal(
            name="commits_per_week",
            value=round(min(commits_per_week, 50.0), 2),
            confidence=0.58,
            evidence_refs=commit_evidence,
            timeframe="sampled_recent",
        ))

        # ── Repository signals ─────────────────────────────────────────────
        own_repos = [r for r in repos if not r.is_fork]
        forked_repos = [r for r in repos if r.is_fork]

        repo_evidence = [
            EvidenceRef(source_type="repo", source_id=r.name, excerpt=f"{r.language} · ⭐{r.stars}")
            for r in repos[:5]
        ]

        # Language distribution (own repos only — forks skew the language picture)
        lang_counts: Counter[str] = Counter(r.language for r in own_repos if r.language != "Unknown")
        top_languages = [lang for lang, _ in lang_counts.most_common(3)]
        language_diversity = len(lang_counts)
        signals.append(Signal(
            name="language_diversity",
            value=language_diversity,
            confidence=0.82,
            evidence_refs=repo_evidence,
            timeframe="all_time",
        ))
        if top_languages:
            signals.append(Signal(
                name="primary_language",
                value=top_languages[0],
                confidence=0.85,
                evidence_refs=repo_evidence,
                timeframe="all_time",
            ))

        # Active repo ratio (own repos only)
        active_own = [r for r in own_repos if r.updated_at >= six_months_ago]
        active_ratio = len(active_own) / (len(own_repos) or 1)
        signals.append(Signal(
            name="active_repo_ratio",
            value=round(active_ratio, 3),
            confidence=0.72,
            evidence_refs=repo_evidence,
            timeframe="last_6_months",
        ))

        # Stars (own repos)
        max_stars = max((r.stars for r in own_repos), default=0)
        avg_stars = sum(r.stars for r in own_repos) / (len(own_repos) or 1)
        signals.append(Signal(
            name="max_stars",
            value=max_stars,
            confidence=0.90,
            evidence_refs=repo_evidence,
            timeframe="all_time",
        ))
        signals.append(Signal(
            name="avg_stars",
            value=round(avg_stars, 2),
            confidence=0.85,
            evidence_refs=repo_evidence,
            timeframe="all_time",
        ))

        # Repo count (own) and fork ratio
        signals.append(Signal(
            name="repo_count",
            value=len(own_repos),
            confidence=0.95,
            evidence_refs=repo_evidence,
            timeframe="all_time",
        ))
        fork_ratio = len(forked_repos) / (len(repos) or 1)
        signals.append(Signal(
            name="fork_ratio",
            value=round(fork_ratio, 3),
            confidence=0.80,
            evidence_refs=repo_evidence,
            timeframe="all_time",
        ))

        # ── Bot filter + data-fidelity signals (Area B) ───────────────────
        human_commits = [c for c in commits if not _is_bot_commit(c)]
        human_commit_ratio = len(human_commits) / (len(commits) or 1) if commits else 1.0
        signals.append(Signal(
            name="human_commit_ratio",
            value=round(human_commit_ratio, 3),
            confidence=0.80,
            evidence_refs=commit_evidence,
            timeframe="sampled_recent",
        ))

        # Backdating heuristic: |committer_date - author_date| > 30d
        backdated = sum(
            1 for c in commits
            if c.author_date and c.committer_date and abs((c.committer_date - c.author_date).days) > 30
        )
        backdated_ratio = backdated / (len(commits) or 1)
        signals.append(Signal(
            name="backdated_commit_ratio",
            value=round(backdated_ratio, 3),
            confidence=0.40,  # weak proxy — rebases also cause divergence
            evidence_refs=commit_evidence,
            timeframe="sampled_recent",
        ))

        # ── Collaboration signals ──────────────────────────────────────────
        signals.append(Signal(
            name="pr_authored_count",
            value=pr_count,
            confidence=0.85 if pr_count > 0 else 0.50,
            evidence_refs=[],
            timeframe="all_time",
        ))
        signals.append(Signal(
            name="issue_authored_count",
            value=issue_count,
            confidence=0.85 if issue_count > 0 else 0.50,
            evidence_refs=[],
            timeframe="all_time",
        ))

        # ── High-value signals (Area A) ────────────────────────────────────
        # #1 Very High: PR review ratio
        pr_review_ratio = reviewed_pr_count / (pr_count + 1)
        signals.append(Signal(
            name="pr_review_ratio",
            value=round(pr_review_ratio, 3),
            confidence=0.80 if reviewed_pr_count > 0 or pr_count > 0 else 0.40,
            evidence_refs=[],
            timeframe="all_time",
        ))

        # #9 Medium: Issue resolution rate
        issue_resolution_rate = closed_issue_count / (issue_count + 1)
        signals.append(Signal(
            name="issue_resolution_rate",
            value=round(issue_resolution_rate, 3),
            confidence=0.70 if issue_count > 0 else 0.40,
            evidence_refs=[],
            timeframe="all_time",
        ))

        # #7 High: Weekday commit ratio (Mon–Fri = weekday() 0–4)
        weekday_commits = sum(1 for c in commits if c.committed_at.weekday() < 5)
        weekday_commit_ratio = weekday_commits / (len(commits) or 1)
        signals.append(Signal(
            name="weekday_commit_ratio",
            value=round(weekday_commit_ratio if commits else 0.0, 3),
            confidence=0.65,
            evidence_refs=commit_evidence,
            timeframe="sampled_recent",
        ))

        # #6 High: Language entropy (byte-weighted Shannon entropy over repo_languages)
        if repo_languages:
            combined: Counter[str] = Counter()
            for byte_map in repo_languages.values():
                combined.update(byte_map)
            entropy_val = _language_entropy(dict(combined))
            signals.append(Signal(
                name="language_entropy",
                value=round(entropy_val, 4),
                confidence=0.75,
                evidence_refs=repo_evidence,
                timeframe="all_time",
            ))

        # #2 Very High: Authorship dominance (DOA proxy) over top repos
        if contributors and username:
            shares: list[float] = []
            for repo_contribs in contributors.values():
                total_c = sum(cnt for _, cnt in repo_contribs)
                if total_c == 0:
                    continue
                user_c = next((cnt for login, cnt in repo_contribs if login == username), 0)
                shares.append(user_c / total_c)
            if shares:
                dominance = sum(shares) / len(shares)
                signals.append(Signal(
                    name="authorship_dominance",
                    value=round(dominance, 3),
                    confidence=0.75,
                    evidence_refs=repo_evidence,
                    timeframe="all_time",
                ))

        # ── Domain bias (repo names + topics) ─────────────────────────────
        ml_bias = sum(1 for r in repos if _repo_matches(r.name, r.topics, _ML_KEYWORDS)) / (len(repos) or 1)
        infra_bias = sum(1 for r in repos if _repo_matches(r.name, r.topics, _INFRA_KEYWORDS)) / (len(repos) or 1)
        tooling_bias = sum(1 for r in repos if _repo_matches(r.name, r.topics, _TOOLING_KEYWORDS)) / (len(repos) or 1)
        systems_bias = sum(1 for r in repos if _repo_matches(r.name, r.topics, _SYSTEMS_KEYWORDS)) / (len(repos) or 1)

        signals.append(Signal(name="ml_domain_bias", value=round(ml_bias, 3), confidence=0.65, evidence_refs=repo_evidence, timeframe="all_time"))
        signals.append(Signal(name="infra_domain_bias", value=round(infra_bias, 3), confidence=0.65, evidence_refs=repo_evidence, timeframe="all_time"))
        signals.append(Signal(name="tooling_domain_bias", value=round(tooling_bias, 3), confidence=0.65, evidence_refs=repo_evidence, timeframe="all_time"))
        signals.append(Signal(name="systems_domain_bias", value=round(systems_bias, 3), confidence=0.65, evidence_refs=repo_evidence, timeframe="all_time"))

        # ── Repo classification ────────────────────────────────────────────
        commit_counts: Counter[str] = Counter(c.repo_name for c in commits)
        repo_types: Counter[str] = Counter(
            _classify_repo(r, commit_counts.get(r.name, 0)) for r in own_repos
        )
        dominant_type = repo_types.most_common(1)[0][0] if repo_types else "personal"

        signals.append(Signal(
            name="dominant_repo_type",
            value=dominant_type,
            confidence=0.70,
            evidence_refs=repo_evidence,
            timeframe="all_time",
        ))
        for label in ("production", "OSS", "project", "personal", "research", "infra", "hackathon", "coursework", "portfolio"):
            count = repo_types.get(label, 0)
            signals.append(Signal(
                name=f"{label}_repo_count",
                value=count,
                confidence=0.75,
                evidence_refs=repo_evidence,
                timeframe="all_time",
            ))

        production_count = repo_types.get("production", 0)
        oss_count = repo_types.get("OSS", 0)
        research_count = repo_types.get("research", 0)

        # ── Temporal / evolution signals ───────────────────────────────────
        # Based on sampled commits only — not the complete commit history.
        monthly_activity: Counter[tuple[int, int]] = Counter()
        for c in commits:
            monthly_activity[(c.committed_at.year, c.committed_at.month)] += 1

        def _month_key(offset_days: int) -> tuple[int, int]:
            d = now - timedelta(days=offset_days)
            return (d.year, d.month)

        recent_90 = sum(monthly_activity.get(_month_key(30 * i), 0) for i in range(3))
        prior_90 = sum(monthly_activity.get(_month_key(30 * (i + 3)), 0) for i in range(3))

        if recent_90 == 0 and prior_90 == 0:
            trajectory = "inactive"
        elif prior_90 == 0 and recent_90 > 0:
            trajectory = "burst"
        elif recent_90 > prior_90 * 1.5:
            trajectory = "growing"
        elif recent_90 < prior_90 * 0.5:
            trajectory = "declining"
        else:
            trajectory = "stable"

        months_active = sum(1 for i in range(12) if monthly_activity.get(_month_key(30 * i), 0) > 0)

        streak = 0
        for i in range(12):
            if monthly_activity.get(_month_key(30 * i), 0) > 0:
                streak += 1
            else:
                break

        three_months_ago = now - timedelta(days=90)
        recent_own = [r for r in own_repos if r.updated_at >= three_months_ago]
        older_own = [r for r in own_repos if r.updated_at < three_months_ago]
        recent_lang_counts = Counter(r.language for r in recent_own if r.language != "Unknown")
        older_lang_counts = Counter(r.language for r in older_own if r.language != "Unknown")
        recent_top_lang = recent_lang_counts.most_common(1)[0][0] if recent_lang_counts else None
        older_top_lang = older_lang_counts.most_common(1)[0][0] if older_lang_counts else None
        lang_shifted = bool(recent_top_lang and older_top_lang and recent_top_lang != older_top_lang)

        signals.append(Signal(
            name="activity_trajectory",
            value=trajectory,
            confidence=0.60,
            evidence_refs=commit_evidence,
            timeframe="last_6_months",
        ))
        signals.append(Signal(
            name="months_active_last_year",
            value=months_active,
            confidence=0.58,
            evidence_refs=commit_evidence,
            timeframe="last_12_months",
        ))
        signals.append(Signal(
            name="streak_months",
            value=streak,
            confidence=0.58,
            evidence_refs=commit_evidence,
            timeframe="recent",
        ))
        signals.append(Signal(
            name="language_shifted",
            value=1.0 if lang_shifted else 0.0,
            confidence=0.55 if (recent_own and older_own) else 0.30,
            evidence_refs=repo_evidence,
            timeframe="last_3_months_vs_prior",
        ))
        if recent_top_lang:
            signals.append(Signal(
                name="recent_primary_language",
                value=recent_top_lang,
                confidence=0.70 if len(recent_own) >= 3 else 0.45,
                evidence_refs=repo_evidence,
                timeframe="last_3_months",
            ))

        # ── Archetype inference (multi-label, rule-based) ──────────────────
        primary_lang = top_languages[0] if top_languages else "Unknown"
        frontend_langs = {"JavaScript", "TypeScript", "CSS", "HTML", "Vue", "Svelte"}
        backend_langs = {"Python", "Go", "Java", "Rust", "C#", "Ruby", "Elixir"}
        systems_langs = {"C", "C++", "Rust", "Zig", "Assembly"}

        # PR score only counts toward OSS if there's actual OSS evidence (stars or oss repos)
        has_oss_evidence = avg_stars > 5 or oss_count > 0 or max_stars >= 10
        oss_pr_score = min(pr_count / 50.0, 0.4) if has_oss_evidence else min(pr_count / 200.0, 0.1)

        # New signal scalars for archetype wiring (default neutral when absent)
        review_bonus = min(pr_review_ratio * 0.15, 0.15)  # #1: review activity → seniority
        dominance_val = 0.0
        if contributors and username:
            shares_for_score = []
            for repo_contribs in contributors.values():
                total_c = sum(cnt for _, cnt in repo_contribs)
                if total_c == 0:
                    continue
                user_c = next((cnt for login, cnt in repo_contribs if login == username), 0)
                shares_for_score.append(user_c / total_c)
            if shares_for_score:
                dominance_val = sum(shares_for_score) / len(shares_for_score)
        dominance_bonus = dominance_val * 0.2  # #2: DOA proxy → OSS Maintainer

        entropy_val_score = 0.0
        if repo_languages:
            combined_score: Counter[str] = Counter()
            for byte_map in repo_languages.values():
                combined_score.update(byte_map)
            entropy_val_score = _language_entropy(dict(combined_score))

        scores: dict[str, float] = {
            "ML Experimenter": ml_bias * 2.0 + (0.4 if primary_lang == "Python" else 0.0) + min(research_count * 0.1, 0.3),
            # Systems Builder absorbs infra signal so every archetype maps to a template
            "Systems Builder": systems_bias * 2.0 + infra_bias * 1.0 + (0.3 if primary_lang in systems_langs else 0.0) + (0.1 if trajectory == "stable" else 0.0) + type_counts["infra"] / total * 0.5 + min(repo_types.get("infra", 0) * 0.1, 0.3),
            # entropy and lang_shifted both boost Full-stack Generalist
            "Full-stack Generalist": (0.3 if (lang_counts.keys() & frontend_langs) and (lang_counts.keys() & backend_langs) else 0.0) + (0.15 if lang_shifted else 0.0) + (language_diversity * 0.04) + min(entropy_val_score * 0.05, 0.15),
            "Tooling Developer": tooling_bias * 1.5 + (0.2 if primary_lang in {"Go", "Rust", "Python"} else 0.0),
            "Academic Researcher": (0.3 if primary_lang == "Python" else 0.0) + type_counts["docs"] / total + min(research_count * 0.2, 0.5),
            # review_bonus + dominance_bonus boost OSS Maintainer (ranks #1 and #2 signals)
            "OSS Maintainer": (0.4 if avg_stars > 5 else 0.0) + type_counts["fix"] / total * 0.5 + oss_pr_score + fork_ratio * 0.3 + min(oss_count * 0.15, 0.5) + (0.2 if months_active >= 8 and has_oss_evidence else 0.0) + review_bonus + dominance_bonus,
            # weekday_commit_ratio > 0.8 suggests professional engineer
            "Product Engineer": type_counts["feat"] / total * 0.8 + (0.3 if max_stars > 10 else 0.0) + min(production_count * 0.1, 0.4) + (0.2 if trajectory == "growing" else 0.0) + (0.15 if streak >= 3 else 0.0) + (0.15 if weekday_commit_ratio > 0.8 else 0.0),
            # low weekday ratio (weekend/hobby coding) boosts Hobbyist
            "Hobbyist Explorer": (0.5 if dominant_type == "personal" else 0.0) + min(len(own_repos) / 30.0, 0.3) + (language_diversity * 0.05) + (0.2 if trajectory in {"growing", "burst"} else 0.0) + (0.1 if months_active >= 6 else 0.0) + (0.1 if weekday_commit_ratio < 0.4 else 0.0) + min(entropy_val_score * 0.03, 0.09),
        }

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_archetype, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0

        # Separation-based confidence: how decisively top beats second place
        if top_score + second_score > 0:
            archetype_confidence = round(min(top_score / (top_score + second_score), 0.95), 2)
        else:
            archetype_confidence = 0.5

        # Thin data cap: few repos or commits means we can't be very confident
        thin_data = len([r for r in repos if not r.is_fork]) < 3 or len(commits) < 5
        if thin_data:
            archetype_confidence = min(archetype_confidence, 0.55)

        # Only show alternates that are meaningfully close (≥85% of top score)
        threshold = top_score * 0.85
        alternates = [name for name, score in ranked[1:4] if score >= threshold]

        archetype = ArchetypeResult(
            top_archetype=top_archetype,
            alternates=alternates,
            confidence=archetype_confidence,
            supporting_evidence=repo_evidence + commit_evidence[:2],
            limited_data=thin_data,
        )

        scored = sorted(
            own_repos,
            key=lambda r: _score_repo(r, commit_counts.get(r.name, 0), six_months_ago),
            reverse=True,
        )
        standout_repos = [r.name for r in scored[:5]]

        return signals, archetype, standout_repos
