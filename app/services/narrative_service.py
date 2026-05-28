from __future__ import annotations

import logging

from app.core.config import settings
from app.models.contracts import ArchetypeResult, HonestyMode, ReadmeResult, ReportResult, Signal
from app.services.narrative_provider import DeterministicNarrativeProvider, GeminiNarrativeProvider, NarrativePrompt, NarrativeProvider, OpenAICompatibleNarrativeProvider

logger = logging.getLogger(__name__)


def _build_provider() -> NarrativeProvider:
    if settings.gemini_api_key:
        logger.info("narrative_provider=gemini model=%s", settings.gemini_model)
        return GeminiNarrativeProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    if settings.groq_api_key:
        logger.info("narrative_provider=groq model=%s", settings.groq_model)
        return OpenAICompatibleNarrativeProvider(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            provider_name="groq",
        )
    if settings.cerebras_api_key:
        logger.info("narrative_provider=cerebras model=%s", settings.cerebras_model)
        return OpenAICompatibleNarrativeProvider(
            base_url="https://api.cerebras.ai/v1",
            api_key=settings.cerebras_api_key,
            model=settings.cerebras_model,
            provider_name="cerebras",
        )
    logger.info("narrative_provider=deterministic (no LLM key set)")
    return DeterministicNarrativeProvider()


class NarrativeService:
    def __init__(self) -> None:
        self.provider = _build_provider()

    def _prompt(self, username: str, honesty_mode: HonestyMode, signals: list[Signal], archetype: ArchetypeResult, standout_repos: list[str]) -> NarrativePrompt:
        return NarrativePrompt(username=username, honesty_mode=honesty_mode, signals=signals, archetype=archetype, standout_repos=standout_repos)

    def build_both(self, username: str, honesty_mode: HonestyMode, signals: list[Signal], archetype: ArchetypeResult, standout_repos: list[str]) -> tuple[ReadmeResult, ReportResult]:
        return self.provider.build_both(self._prompt(username, honesty_mode, signals, archetype, standout_repos))
