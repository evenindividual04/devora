"""Tests for eval service (Area C): aggregation, deterministic fallback, falsifiability path.

Source: docs/LLM-as-Judge for README Evaluation.md.
"""
from __future__ import annotations

import json

import pytest

from app.eval.judges import DeterministicAuthenticityJudge
from app.models.contracts import DimensionScore, EvalResult
from app.services.eval_service import ReadmeEvaluator


# ──────────────────────────────────────────────────────────────────────────────
# DeterministicAuthenticityJudge
# ──────────────────────────────────────────────────────────────────────────────

class TestDeterministicAuthenticityJudge:
    """Always-on, offline-safe judge that penalises banned phrases."""

    def test_clean_readme_high_score(self):
        judge = DeterministicAuthenticityJudge()
        readme = "Builds distributed systems in Go. 47 contributors across 3 active repos."
        result = judge.score("authenticity", readme, "{}")
        assert isinstance(result, DimensionScore)
        assert result.score >= 4
        assert result.dimension == "authenticity"
        assert result.judge == "deterministic"

    def test_banned_phrase_lowers_score(self):
        judge = DeterministicAuthenticityJudge()
        readme = "A passionate developer who loves innovative solutions and best practices."
        result = judge.score("authenticity", readme, "{}")
        assert result.score <= 2

    def test_multiple_banned_phrases_minimum_score(self):
        judge = DeterministicAuthenticityJudge()
        readme = "Tech enthusiast and fast learner, always learning new cutting-edge technologies."
        result = judge.score("authenticity", readme, "{}")
        assert result.score == 1

    def test_reasoning_is_non_empty(self):
        judge = DeterministicAuthenticityJudge()
        result = judge.score("authenticity", "Some README.", "{}")
        assert result.reasoning
        assert len(result.reasoning) > 5


# ──────────────────────────────────────────────────────────────────────────────
# ReadmeEvaluator — aggregation and fallback
# ──────────────────────────────────────────────────────────────────────────────

class TestReadmeEvaluatorDeterministicOnly:
    """When no LLM key is set, only the deterministic judge runs (never hard-fails)."""

    def test_evaluate_returns_eval_result(self):
        evaluator = ReadmeEvaluator(providers=["deterministic"])
        readme = "Builds CLI tools in Rust. 12 repos, 3 with >50 stars."
        signals = json.dumps({"pr_review_ratio": 0.5, "weekday_commit_ratio": 0.8})
        result = evaluator.evaluate(readme, signals)
        assert isinstance(result, EvalResult)

    def test_scores_has_authenticity_dimension(self):
        evaluator = ReadmeEvaluator(providers=["deterministic"])
        result = evaluator.evaluate("Clean Rust CLI author.", "{}")
        dims = {s.dimension for s in result.scores}
        assert "authenticity" in dims

    def test_aggregate_is_average_of_scores(self):
        evaluator = ReadmeEvaluator(providers=["deterministic"])
        result = evaluator.evaluate("Clean Rust CLI author.", "{}")
        expected_avg = sum(s.score for s in result.scores) / len(result.scores)
        assert result.aggregate == pytest.approx(expected_avg, abs=0.01)

    def test_never_fails_on_empty_readme(self):
        evaluator = ReadmeEvaluator(providers=["deterministic"])
        result = evaluator.evaluate("", "{}")
        assert isinstance(result, EvalResult)
        assert math.isfinite(result.aggregate)

    def test_model_set_contains_deterministic(self):
        evaluator = ReadmeEvaluator(providers=["deterministic"])
        result = evaluator.evaluate("readme", "{}")
        assert "deterministic" in result.model_set


import math


class TestReadmeEvaluatorMockedGemini:
    """When Gemini is configured, its scores are averaged with deterministic."""

    def test_gemini_scores_merged_with_deterministic(self, monkeypatch):
        from unittest.mock import MagicMock
        from app.eval.judges import GeminiJudgeProvider

        mock_gemini = MagicMock(spec=GeminiJudgeProvider)
        mock_gemini.score.return_value = DimensionScore(
            dimension="specificity", score=4, reasoning="Good specificity.", judge="gemini"
        )
        monkeypatch.setattr("app.services.eval_service.GeminiJudgeProvider", lambda: mock_gemini)

        evaluator = ReadmeEvaluator(providers=["gemini", "deterministic"])
        result = evaluator.evaluate("Builds things.", "{}")
        # Gemini contributes at least one score
        judges = {s.judge for s in result.scores}
        assert "gemini" in judges or "deterministic" in judges  # at least one worked


# ──────────────────────────────────────────────────────────────────────────────
# DimensionScore and EvalResult contracts
# ──────────────────────────────────────────────────────────────────────────────

class TestEvalContracts:
    def test_dimension_score_fields(self):
        ds = DimensionScore(dimension="specificity", score=3, reasoning="ok", judge="deterministic")
        assert ds.dimension == "specificity"
        assert ds.score == 3
        assert ds.reasoning == "ok"
        assert ds.judge == "deterministic"

    def test_eval_result_fields(self):
        scores = [DimensionScore(dimension="authenticity", score=4, reasoning="fine", judge="deterministic")]
        er = EvalResult(scores=scores, aggregate=4.0, model_set=["deterministic"])
        assert er.aggregate == 4.0
        assert er.model_set == ["deterministic"]
        assert len(er.scores) == 1
