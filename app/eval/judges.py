"""Judge providers for LLM-as-Judge eval (Area C).

Source: docs/LLM-as-Judge for README Evaluation.md §Judge providers.
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

from app.eval.dimensions import DIMENSION_MAP, DIMENSIONS
from app.models.contracts import DimensionScore

logger = logging.getLogger(__name__)

# Reuse banned-phrase list from narrative provider
from app.services.narrative_provider import _BANNED_PHRASES


class JudgeProvider(Protocol):
    def score(self, dimension: str, readme_md: str, signals_json: str) -> DimensionScore:
        ...


class DeterministicAuthenticityJudge:
    """Offline-safe judge: penalises banned phrases, always on.

    Score formula:
      Start at 5; subtract 1 per unique banned phrase found (capped at floor=1).
      For non-authenticity dimensions defaults to a neutral 3.
    """

    def score(self, dimension: str, readme_md: str, signals_json: str) -> DimensionScore:
        text_lower = readme_md.lower()
        found = [p for p in _BANNED_PHRASES if p.lower() in text_lower]

        # Empty README is universally bad regardless of dimension
        if not readme_md.strip():
            return DimensionScore(
                dimension=dimension,
                score=1.0,
                reasoning="Empty README — no content to evaluate.",
                judge="deterministic",
            )

        if dimension == "authenticity":
            raw_score = max(1, 5 - len(found))
            reasoning = (
                f"Found {len(found)} banned phrase(s): {found[:5]}" if found
                else "No banned phrases detected."
            )
        else:
            # Deterministic judge only judges authenticity reliably
            raw_score = max(1, 4 - len(found))
            reasoning = (
                f"Deterministic score for {dimension}. "
                f"{'Banned phrases detected: ' + str(found[:3]) if found else 'No banned phrases.'}"
            )

        return DimensionScore(
            dimension=dimension,
            score=float(raw_score),
            reasoning=reasoning,
            judge="deterministic",
        )


class GeminiJudgeProvider:
    """Gemini-based judge. Reuses google.genai Client from GeminiNarrativeProvider."""

    def __init__(self) -> None:
        from app.core.config import settings
        try:
            from google import genai  # type: ignore[import-untyped]
            self._client = genai.Client(api_key=settings.gemini_api_key)
            self._model_name = settings.gemini_model
            self._available = bool(settings.gemini_api_key)
        except Exception:
            self._available = False

    def score(self, dimension: str, readme_md: str, signals_json: str) -> DimensionScore:
        if not self._available:
            raise RuntimeError("Gemini not configured")
        dim = DIMENSION_MAP.get(dimension)
        if not dim:
            raise ValueError(f"Unknown dimension: {dimension}")

        prompt_parts = [dim.rubric, f"\n\n---\nREADME:\n{readme_md}"]
        if dim.reference_based:
            prompt_parts.append(f"\n\nSIGNALS (reference evidence):\n{signals_json}")

        try:
            from google.genai import types  # type: ignore[import-untyped]
            resp = self._client.models.generate_content(
                model=self._model_name,
                contents="\n".join(prompt_parts),
                config=types.GenerateContentConfig(max_output_tokens=300),
            )
            text = (resp.text or "").strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return DimensionScore(
                    dimension=dimension,
                    score=float(max(1, min(5, data.get("score", 3)))),
                    reasoning=data.get("reasoning", ""),
                    judge="gemini",
                )
        except Exception as exc:
            logger.warning("Gemini judge failed for %s: %s", dimension, exc)
        return DimensionScore(dimension=dimension, score=3.0, reasoning="judge unavailable", judge="gemini")


class OpenAICompatibleJudgeProvider:
    """OpenAI-compatible judge for cross-family diversity (Groq, OpenRouter free Llama)."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._available = bool(api_key and base_url and model)

    def score(self, dimension: str, readme_md: str, signals_json: str) -> DimensionScore:
        if not self._available:
            raise RuntimeError("OpenAI-compatible judge not configured")
        dim = DIMENSION_MAP.get(dimension)
        if not dim:
            raise ValueError(f"Unknown dimension: {dimension}")

        import httpx
        prompt = dim.rubric + f"\n\n---\nREADME:\n{readme_md}"
        if dim.reference_based:
            prompt += f"\n\nSIGNALS:\n{signals_json}"

        try:
            resp = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={"model": self._model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 256},
                timeout=20.0,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return DimensionScore(
                    dimension=dimension,
                    score=float(max(1, min(5, data.get("score", 3)))),
                    reasoning=data.get("reasoning", ""),
                    judge="openai_compatible",
                )
        except Exception as exc:
            logger.warning("OpenAI-compatible judge failed for %s: %s", dimension, exc)
        return DimensionScore(dimension=dimension, score=3.0, reasoning="judge unavailable", judge="openai_compatible")
