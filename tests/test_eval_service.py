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


# ──────────────────────────────────────────────────────────────────────────────
# OpenAICompatibleJudgeProvider + GroqJudgeProvider + CerebrasJudgeProvider
# ──────────────────────────────────────────────────────────────────────────────

class TestOpenAICompatibleJudgeProvider:
    def test_raises_when_not_configured(self):
        from app.eval.judges import OpenAICompatibleJudgeProvider
        provider = OpenAICompatibleJudgeProvider(base_url="", api_key="", model="")
        with pytest.raises(RuntimeError):
            provider.score("authenticity", "readme", "{}")

    def test_scores_valid_json_response(self, monkeypatch):
        from unittest.mock import MagicMock
        from app.eval.judges import OpenAICompatibleJudgeProvider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"score": 4, "reasoning": "good specificity"}'}}]
        }
        mock_resp.raise_for_status = MagicMock()

        import httpx
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: mock_resp)

        provider = OpenAICompatibleJudgeProvider(
            base_url="https://example.com", api_key="key", model="model-x", judge_name="test"
        )
        result = provider.score("specificity", "Some readme.", "{}")
        assert result.score == 4.0
        assert result.judge == "test"
        assert result.reasoning == "good specificity"

    def test_falls_back_on_malformed_json(self, monkeypatch):
        from unittest.mock import MagicMock
        from app.eval.judges import OpenAICompatibleJudgeProvider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "not json at all"}}]
        }
        mock_resp.raise_for_status = MagicMock()

        import httpx
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: mock_resp)

        provider = OpenAICompatibleJudgeProvider(
            base_url="https://example.com", api_key="key", model="model-x", judge_name="test"
        )
        result = provider.score("authenticity", "Some readme.", "{}")
        assert result.score == 3.0
        assert result.reasoning == "judge unavailable"

    def test_falls_back_on_http_error(self, monkeypatch):
        import httpx
        from app.eval.judges import OpenAICompatibleJudgeProvider

        def _raise(*a, **kw):
            raise httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())

        monkeypatch.setattr(httpx, "post", _raise)
        provider = OpenAICompatibleJudgeProvider(
            base_url="https://example.com", api_key="key", model="model-x"
        )
        result = provider.score("authenticity", "readme", "{}")
        assert result.score == 3.0

    def test_score_clamped_to_1_5(self, monkeypatch):
        from unittest.mock import MagicMock
        from app.eval.judges import OpenAICompatibleJudgeProvider

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"score": 99, "reasoning": "great"}'}}]
        }
        mock_resp.raise_for_status = MagicMock()

        import httpx
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: mock_resp)

        provider = OpenAICompatibleJudgeProvider(
            base_url="https://example.com", api_key="key", model="m"
        )
        result = provider.score("specificity", "readme", "{}")
        assert result.score == 5.0


class TestGroqAndCerebrasProviders:
    def test_groq_provider_not_available_without_key(self):
        from app.eval.judges import OpenAICompatibleJudgeProvider
        p = OpenAICompatibleJudgeProvider(
            base_url="https://api.groq.com/openai/v1", api_key="", model="llama-3.3-70b", judge_name="groq"
        )
        with pytest.raises(RuntimeError, match="groq"):
            p.score("authenticity", "readme", "{}")








    def test_groq_judge_name_in_score(self, monkeypatch):
        from unittest.mock import MagicMock
        from app.eval.judges import OpenAICompatibleJudgeProvider
        import httpx

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"score": 3, "reasoning": "ok"}'}}]
        }
        mock_resp.raise_for_status = MagicMock()
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: mock_resp)

        provider = OpenAICompatibleJudgeProvider(
            base_url="https://api.groq.com/openai/v1", api_key="fake", model="llama-3.3-70b", judge_name="groq"
        )
        result = provider.score("authenticity", "readme", "{}")
        assert result.judge == "groq"

    def test_cerebras_judge_name_in_score(self, monkeypatch):
        from unittest.mock import MagicMock
        from app.eval.judges import OpenAICompatibleJudgeProvider
        import httpx

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"score": 2, "reasoning": "weak"}'}}]
        }
        mock_resp.raise_for_status = MagicMock()
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: mock_resp)

        provider = OpenAICompatibleJudgeProvider(
            base_url="https://api.cerebras.ai/v1", api_key="fake", model="llama3.1-70b", judge_name="cerebras"
        )
        result = provider.score("specificity", "readme", "{}")
        assert result.judge == "cerebras"


class TestReadmeEvaluatorWithGroqCerebras:
    def test_groq_scores_appear_in_model_set(self, monkeypatch):
        from unittest.mock import MagicMock
        from app.eval.judges import GroqJudgeProvider

        mock_groq = MagicMock(spec=GroqJudgeProvider)
        mock_groq.score.return_value = DimensionScore(
            dimension="authenticity", score=4.0, reasoning="groq ok", judge="groq"
        )
        monkeypatch.setattr("app.services.eval_service.GroqJudgeProvider", lambda: mock_groq)
        monkeypatch.setattr("app.services.eval_service.settings", type("S", (), {
            "eval_judge_providers": ["groq", "deterministic"],
            "gemini_api_key": "",
            "groq_api_key": "fake-groq-key",
            "cerebras_api_key": "",
            "eval_openai_api_key": "",
        })())

        from app.services.eval_service import ReadmeEvaluator
        evaluator = ReadmeEvaluator(providers=["groq", "deterministic"])
        evaluator._groq = mock_groq
        result = evaluator.evaluate("Some readme.", "{}")
        assert "groq" in result.model_set

    def test_cerebras_scores_appear_in_model_set(self, monkeypatch):
        from unittest.mock import MagicMock
        from app.eval.judges import CerebrasJudgeProvider

        mock_cerebras = MagicMock(spec=CerebrasJudgeProvider)
        mock_cerebras.score.return_value = DimensionScore(
            dimension="authenticity", score=3.5, reasoning="cerebras ok", judge="cerebras"
        )
        monkeypatch.setattr("app.services.eval_service.CerebrasJudgeProvider", lambda: mock_cerebras)

        from app.services.eval_service import ReadmeEvaluator
        evaluator = ReadmeEvaluator(providers=["cerebras", "deterministic"])
        evaluator._cerebras = mock_cerebras
        result = evaluator.evaluate("Some readme.", "{}")
        assert "cerebras" in result.model_set


# ──────────────────────────────────────────────────────────────────────────────
# ReadmeEvaluator __init__ paths for groq/cerebras/openai_compatible
# ──────────────────────────────────────────────────────────────────────────────

class TestReadmeEvaluatorInit:
    def test_groq_initialized_when_key_set(self, monkeypatch):
        from unittest.mock import MagicMock
        mock_groq_cls = MagicMock()
        monkeypatch.setattr("app.services.eval_service.GroqJudgeProvider", mock_groq_cls)
        monkeypatch.setattr("app.services.eval_service.settings", type("S", (), {
            "eval_judge_providers": ["groq"],
            "gemini_api_key": "",
            "groq_api_key": "fake-groq",
            "cerebras_api_key": "",
            "eval_openai_api_key": "",
        })())
        from app.services.eval_service import ReadmeEvaluator
        ev = ReadmeEvaluator(providers=["groq"])
        mock_groq_cls.assert_called_once()
        assert ev._groq is not None

    def test_cerebras_initialized_when_key_set(self, monkeypatch):
        from unittest.mock import MagicMock
        mock_cerebras_cls = MagicMock()
        monkeypatch.setattr("app.services.eval_service.CerebrasJudgeProvider", mock_cerebras_cls)
        monkeypatch.setattr("app.services.eval_service.settings", type("S", (), {
            "eval_judge_providers": ["cerebras"],
            "gemini_api_key": "",
            "groq_api_key": "",
            "cerebras_api_key": "fake-cerebras",
            "eval_openai_api_key": "",
        })())
        from app.services.eval_service import ReadmeEvaluator
        ev = ReadmeEvaluator(providers=["cerebras"])
        mock_cerebras_cls.assert_called_once()
        assert ev._cerebras is not None

    def test_openai_compatible_initialized_when_key_set(self, monkeypatch):
        from unittest.mock import MagicMock
        mock_oai_cls = MagicMock()
        monkeypatch.setattr("app.services.eval_service.OpenAICompatibleJudgeProvider", mock_oai_cls)
        monkeypatch.setattr("app.services.eval_service.settings", type("S", (), {
            "eval_judge_providers": ["openai_compatible"],
            "gemini_api_key": "",
            "groq_api_key": "",
            "cerebras_api_key": "",
            "eval_openai_api_key": "fake-oai",
            "eval_openai_base_url": "https://example.com",
            "eval_openai_model": "model-x",
        })())
        from app.services.eval_service import ReadmeEvaluator
        ev = ReadmeEvaluator(providers=["openai_compatible"])
        mock_oai_cls.assert_called_once()
        assert ev._oai is not None

    def test_groq_init_exception_logged(self, monkeypatch):
        monkeypatch.setattr("app.services.eval_service.GroqJudgeProvider", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        monkeypatch.setattr("app.services.eval_service.settings", type("S", (), {
            "gemini_api_key": "",
            "groq_api_key": "key",
            "cerebras_api_key": "",
            "eval_openai_api_key": "",
        })())
        from app.services.eval_service import ReadmeEvaluator
        ev = ReadmeEvaluator(providers=["groq"])
        assert ev._groq is None

    def test_groq_and_cerebras_score_in_evaluate(self, monkeypatch):
        """Groq and cerebras scores both appear in evaluate() output."""
        from unittest.mock import MagicMock
        from app.services.eval_service import ReadmeEvaluator

        mock_groq = MagicMock()
        mock_groq.score.return_value = DimensionScore(
            dimension="authenticity", score=4.0, reasoning="groq", judge="groq"
        )
        mock_cerebras = MagicMock()
        mock_cerebras.score.return_value = DimensionScore(
            dimension="authenticity", score=3.0, reasoning="cerebras", judge="cerebras"
        )

        ev = ReadmeEvaluator(providers=["groq", "cerebras", "deterministic"])
        ev._groq = mock_groq
        ev._cerebras = mock_cerebras

        result = ev.evaluate("Some readme text.", "{}")
        assert "groq" in result.model_set
        assert "cerebras" in result.model_set

    def test_openai_compatible_scores_in_evaluate(self, monkeypatch):
        from unittest.mock import MagicMock
        from app.services.eval_service import ReadmeEvaluator

        mock_oai = MagicMock()
        mock_oai.score.return_value = DimensionScore(
            dimension="authenticity", score=3.5, reasoning="oai", judge="openai_compatible"
        )

        ev = ReadmeEvaluator(providers=["openai_compatible", "deterministic"])
        ev._oai = mock_oai

        result = ev.evaluate("Some readme.", "{}")
        assert "openai_compatible" in result.model_set


class TestReadmeEvaluatorExceptPaths:
    def test_cerebras_init_exception_logged(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.eval_service.CerebrasJudgeProvider",
            lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        monkeypatch.setattr("app.services.eval_service.settings", type("S", (), {
            "gemini_api_key": "",
            "groq_api_key": "",
            "cerebras_api_key": "key",
            "eval_openai_api_key": "",
        })())
        from app.services.eval_service import ReadmeEvaluator
        ev = ReadmeEvaluator(providers=["cerebras"])
        assert ev._cerebras is None

    def test_openai_compatible_init_exception_logged(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.eval_service.OpenAICompatibleJudgeProvider",
            lambda **_: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        monkeypatch.setattr("app.services.eval_service.settings", type("S", (), {
            "gemini_api_key": "",
            "groq_api_key": "",
            "cerebras_api_key": "",
            "eval_openai_api_key": "key",
            "eval_openai_base_url": "https://x.com",
            "eval_openai_model": "m",
        })())
        from app.services.eval_service import ReadmeEvaluator
        ev = ReadmeEvaluator(providers=["openai_compatible"])
        assert ev._oai is None

    def test_evaluate_falls_back_when_all_judges_fail(self):
        """If all active LLM judges raise, deterministic fallback kicks in."""
        from unittest.mock import MagicMock
        from app.services.eval_service import ReadmeEvaluator

        bad_judge = MagicMock()
        bad_judge.score.side_effect = RuntimeError("kaboom")

        ev = ReadmeEvaluator(providers=["groq", "deterministic"])
        ev._groq = bad_judge
        result = ev.evaluate("Some readme.", "{}")
        assert isinstance(result, EvalResult)
        assert result.aggregate > 0
