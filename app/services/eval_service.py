"""ReadmeEvaluator: aggregates judge scores across all six dimensions.

Source: docs/LLM-as-Judge for README Evaluation.md §Service.
Falls back to deterministic judge when no LLM key is set (never hard-fails).
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.eval.dimensions import DIMENSIONS
from app.eval.judges import CerebrasJudgeProvider, DeterministicAuthenticityJudge, GeminiJudgeProvider, GroqJudgeProvider, OpenAICompatibleJudgeProvider
from app.models.contracts import DimensionScore, EvalResult

logger = logging.getLogger(__name__)


class ReadmeEvaluator:
    def __init__(self, providers: list[str] | None = None) -> None:
        if providers is None:
            providers = settings.eval_judge_providers
        self._providers = providers
        self._det_judge = DeterministicAuthenticityJudge()
        self._gemini: GeminiJudgeProvider | None = None
        self._groq: GroqJudgeProvider | None = None
        self._cerebras: CerebrasJudgeProvider | None = None
        self._oai: OpenAICompatibleJudgeProvider | None = None

        if "gemini" in providers and settings.gemini_api_key:
            try:
                self._gemini = GeminiJudgeProvider()
            except Exception as exc:
                logger.warning("Gemini judge init failed: %s", exc)

        if "groq" in providers and settings.groq_api_key:
            try:
                self._groq = GroqJudgeProvider()
            except Exception as exc:
                logger.warning("Groq judge init failed: %s", exc)

        if "cerebras" in providers and settings.cerebras_api_key:
            try:
                self._cerebras = CerebrasJudgeProvider()
            except Exception as exc:
                logger.warning("Cerebras judge init failed: %s", exc)

        if "openai_compatible" in providers and settings.eval_openai_api_key:
            try:
                self._oai = OpenAICompatibleJudgeProvider(
                    base_url=settings.eval_openai_base_url,
                    api_key=settings.eval_openai_api_key,
                    model=settings.eval_openai_model,
                )
            except Exception as exc:
                logger.warning("OpenAI-compatible judge init failed: %s", exc)

    def evaluate(self, readme: str, signals_json: str) -> EvalResult:
        """Score readme across all six dimensions; aggregate as mean."""
        all_scores: list[DimensionScore] = []
        used_judges: set[str] = set()

        for dim in DIMENSIONS:
            dim_scores: list[DimensionScore] = []

            # Deterministic judge always runs for authenticity;
            # for other dimensions it provides a baseline when no LLM is available
            if "deterministic" in self._providers or not (self._gemini or self._oai):
                try:
                    ds = self._det_judge.score(dim.name, readme, signals_json)
                    dim_scores.append(ds)
                    used_judges.add("deterministic")
                except Exception as exc:
                    logger.warning("Deterministic judge failed for %s: %s", dim.name, exc)

            # Gemini
            if self._gemini and "gemini" in self._providers:
                try:
                    ds = self._gemini.score(dim.name, readme, signals_json)
                    dim_scores.append(ds)
                    used_judges.add("gemini")
                except Exception as exc:
                    logger.warning("Gemini judge failed for %s: %s", dim.name, exc)

            # Groq
            if self._groq and "groq" in self._providers:
                try:
                    ds = self._groq.score(dim.name, readme, signals_json)
                    dim_scores.append(ds)
                    used_judges.add("groq")
                except Exception as exc:
                    logger.warning("Groq judge failed for %s: %s", dim.name, exc)

            # Cerebras
            if self._cerebras and "cerebras" in self._providers:
                try:
                    ds = self._cerebras.score(dim.name, readme, signals_json)
                    dim_scores.append(ds)
                    used_judges.add("cerebras")
                except Exception as exc:
                    logger.warning("Cerebras judge failed for %s: %s", dim.name, exc)

            # OpenAI-compatible (generic)
            if self._oai and "openai_compatible" in self._providers:
                try:
                    ds = self._oai.score(dim.name, readme, signals_json)
                    dim_scores.append(ds)
                    used_judges.add("openai_compatible")
                except Exception as exc:
                    logger.warning("OAI judge failed for %s: %s", dim.name, exc)

            if dim_scores:
                # Average panel scores per dimension, then pick best representation
                avg_score = sum(s.score for s in dim_scores) / len(dim_scores)
                # Carry the first score's reasoning; mark the dimension
                rep = dim_scores[0]
                all_scores.append(DimensionScore(
                    dimension=dim.name,
                    score=round(avg_score, 2),
                    reasoning=rep.reasoning,
                    judge=rep.judge,
                ))

        if not all_scores:
            # Fallback: deterministic on all dims
            for dim in DIMENSIONS:
                ds = self._det_judge.score(dim.name, readme, signals_json)
                all_scores.append(ds)
                used_judges.add("deterministic")

        aggregate = sum(s.score for s in all_scores) / len(all_scores)
        return EvalResult(
            scores=all_scores,
            aggregate=round(aggregate, 3),
            model_set=sorted(used_judges),
        )


_evaluator: ReadmeEvaluator | None = None


def get_evaluator() -> ReadmeEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = ReadmeEvaluator()
    return _evaluator
