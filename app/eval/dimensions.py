"""Six eval dimensions with 1-5 rubrics.

Source: docs/LLM-as-Judge for README Evaluation.md §Dimensions.
Each dimension prompt is single-dimension isolated (one per LLM call).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    name: str
    description: str
    rubric: str
    reference_based: bool = False  # True = passes signals JSON for FACTS grounding


DIMENSIONS: list[Dimension] = [
    Dimension(
        name="specificity",
        description="How specific and unique are the claims to this developer?",
        rubric="""\
Score 1-5 for SPECIFICITY. Judge ONLY this dimension.

1: Entirely generic — could apply to any developer ("loves coding", "works on web apps")
2: Mostly generic with one or two concrete details
3: Mix — some specific repo/stat mentions but padded with generic filler
4: Mostly specific — most claims are unique to this developer
5: Fully specific — every sentence is exclusively true of this developer; no filler

Penalise: sentences copy-pasteable onto another developer's profile without changing.
Reward: repo names, star counts, commit ratios, language specifics, dates.

Think step by step, then output JSON: {"reasoning": "...", "score": N}
Do not overthink. Bias toward lower scores for vague profiles.""",
    ),
    Dimension(
        name="authenticity",
        description="Does the voice feel human and genuine, not templated?",
        rubric="""\
Score 1-5 for AUTHENTICITY. Judge ONLY this dimension.

1: Full of clichés, HR-speak, or buzzwords ("passionate developer", "synergy", "leverage")
2: Several clichéd phrases mixed with real content
3: Mostly authentic but one or two corporate phrases slip through
4: Sounds human; minor awkwardness but no clichés
5: Completely natural, direct voice; reads like a developer wrote it about themselves

SEVERELY penalise (score ≤2) any of: passionate developer, always learning, tech enthusiast,
innovative solutions, fast learner, team player, synergy, leverage, utilize, cutting-edge,
state-of-the-art, best practices, hard worker, dedicated professional.

Think step by step, then output JSON: {"reasoning": "...", "score": N}""",
    ),
    Dimension(
        name="falsifiability",
        description="Are claims checkable against the provided signal evidence?",
        rubric="""\
Score 1-5 for FALSIFIABILITY. Judge ONLY this dimension.
You are provided with a JSON snapshot of extracted signals (evidence).

1: All claims are vague opinions with no verifiable link to signals
2: Some claims could be checked but most are ungrounded
3: About half of claims trace to measurable signals
4: Most claims are grounded in signals or observable data
5: Every claim is either measurable (stat, count, ratio) or directly traceable to a signal

Cross-check: if a claim says "high review activity" but pr_review_ratio=0.0, flag it.
Reward: exact numbers, repo names, ratios, dates.

Think step by step, then output JSON: {"reasoning": "...", "score": N}""",
        reference_based=True,
    ),
    Dimension(
        name="tonal_appropriateness",
        description="Is the tone suitable for a developer profile README?",
        rubric="""\
Score 1-5 for TONAL APPROPRIATENESS. Judge ONLY this dimension.

1: Wrong register (too casual/slang, or overly formal/corporate)
2: Mostly wrong register with occasional correct tone
3: Acceptable but inconsistent
4: Appropriate developer tone with minor lapses
5: Perfectly pitched — direct, technical, human; no HR language and no excessive informality

Think step by step, then output JSON: {"reasoning": "...", "score": N}""",
    ),
    Dimension(
        name="structural_coherence",
        description="Does the README flow logically and have a clear structure?",
        rubric="""\
Score 1-5 for STRUCTURAL COHERENCE. Judge ONLY this dimension.

1: Random or incoherent ordering; no logical flow
2: Some structure but sections feel disconnected
3: Adequate structure but some non-sequiturs
4: Good flow; sections connect naturally
5: Excellent flow — anchor → trajectory → evidence → invitation follows naturally

Think step by step, then output JSON: {"reasoning": "...", "score": N}""",
    ),
    Dimension(
        name="noise_to_signal",
        description="Is content dense, or padded with filler?",
        rubric="""\
Score 1-5 for NOISE-TO-SIGNAL RATIO. Judge ONLY this dimension.

1: Mostly padding (>60% filler sentences)
2: More filler than signal
3: Balanced — roughly equal signal and filler
4: Mostly signal with minor padding
5: Pure signal — every sentence adds unique information

Filler examples: "I am always eager to learn new things", "I enjoy collaborating with teams".
Signal examples: exact numbers, specific project names, measurable outcomes.

Think step by step, then output JSON: {"reasoning": "...", "score": N}""",
    ),
]

DIMENSION_MAP: dict[str, Dimension] = {d.name: d for d in DIMENSIONS}
