"""Canary regression gate for README quality evaluation (Area C).

Runs always: deterministic judge (no key needed).
Runs when GEMINI_API_KEY is set: Gemini judge.

Each fixture is a (readme, signals_json, expected_band) triple.
Bands: "good" ≥4.0, "mediocre" 2.5-3.9, "bad" <2.5
"""
from __future__ import annotations

import pytest

from app.services.eval_service import ReadmeEvaluator

# fmt: off
_CANARY_FIXTURES = [
    # ── GOOD: specific, falsifiable, evidence-grounded ───────────────────────
    (
        "good_specific",
        """\
Maintains `ripgrep-all`, a search tool combining ripgrep with 30+ file format parsers.
6.2k GitHub stars. 847 commits since 2019, 78% on weekdays.
Core contributor: 91% of commits authored vs 1,200 total contributor commits.
Reviews ~3 PRs per authored PR across the ecosystem.
""",
        '{"pr_review_ratio": 2.9, "weekday_commit_ratio": 0.78, "authorship_dominance": 0.91}',
        "good",
    ),
    (
        "good_evidence_rich",
        """\
Go compiler contributor since 2021. 23 merged patches to golang/go.
Focus: escape analysis and inliner improvements (12 of 23 patches touch these subsystems).
Weekday coding: 83% of 340 sampled commits. Shannon entropy across 4 languages: 1.6 bits.
""",
        '{"weekday_commit_ratio": 0.83, "language_entropy": 1.6, "pr_review_ratio": 0.4}',
        "good",
    ),
    # ── MEDIOCRE: some specifics, some generic ───────────────────────────────
    (
        "mediocre_mixed",
        """\
Software engineer with experience in Python and JavaScript.
Works on web applications and has contributed to several open source projects.
Active on GitHub with regular commits.
""",
        '{"commits_per_week": 2.1, "language_diversity": 4}',
        "mediocre",
    ),
    # ── BAD: generic, clichéd, ungrounded ────────────────────────────────────
    (
        "bad_cliches",
        """\
Passionate developer always learning and embracing innovative solutions.
Tech enthusiast with a strong foundation in best practices.
Team player who loves challenging problems and building the future.
Fast learner, dedicated professional, results-driven.
""",
        "{}",
        "bad",
    ),
    (
        "bad_empty",
        "",
        "{}",
        "bad",
    ),
]
# fmt: on

_BAND_THRESHOLDS = {"good": 4.0, "mediocre": 2.5, "bad": 0.0}


def _in_band(score: float, band: str) -> bool:
    if band == "good":
        return score >= 4.0
    if band == "mediocre":
        return 2.5 <= score < 4.0
    return score < 2.5


@pytest.mark.parametrize("fixture_id,readme,signals,expected_band", _CANARY_FIXTURES, ids=[f[0] for f in _CANARY_FIXTURES])
def test_canary_deterministic(fixture_id, readme, signals, expected_band):
    """Deterministic judge must place each fixture in the correct quality band."""
    evaluator = ReadmeEvaluator(providers=["deterministic"])
    result = evaluator.evaluate(readme, signals)
    assert _in_band(result.aggregate, expected_band), (
        f"[{fixture_id}] Expected band={expected_band!r} but aggregate={result.aggregate:.2f}. "
        f"Scores: {[(s.dimension, s.score) for s in result.scores]}"
    )


@pytest.mark.parametrize("fixture_id,readme,signals,expected_band", _CANARY_FIXTURES, ids=[f[0] for f in _CANARY_FIXTURES])
def test_canary_gemini_when_keyed(fixture_id, readme, signals, expected_band):
    """Gemini judge (when API key is present) must stay within expected band.

    Skips automatically when:
    - GEMINI_API_KEY is not set
    - Gemini is rate-limited (all scores fell back to the 3.0 fallback)
    """
    import os
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set — skipping Gemini canary")
    evaluator = ReadmeEvaluator(providers=["gemini", "deterministic"])
    result = evaluator.evaluate(readme, signals)
    # If all Gemini scores are unavailable (fallback), skip rather than fail
    gemini_scores = [s for s in result.scores if s.judge == "gemini"]
    if all(s.reasoning == "judge unavailable" for s in gemini_scores) or not gemini_scores:
        pytest.skip("Gemini API unavailable (rate limited or quota exhausted)")
    assert _in_band(result.aggregate, expected_band), (
        f"[{fixture_id}] Gemini+deterministic band mismatch. aggregate={result.aggregate:.2f}"
    )
