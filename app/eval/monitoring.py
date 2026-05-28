"""PSI and K-S monitoring for eval score distributions.

Source: docs/LLM-as-Judge for README Evaluation.md §PSI/K-S monitoring.
Pure Python, no extra dependencies.
"""
from __future__ import annotations

import math


def population_stability_index(
    expected: list[float],
    actual: list[float],
    epsilon: float = 0.01,
) -> float:
    """Compute PSI between two score distributions.

    Accepts raw counts or proportions; normalises internally.
    Uses +epsilon empty-bin guard from the doc spec.

    Thresholds (from doc):
      PSI < 0.1  → stable
      0.1–0.2    → warn
      > 0.2      → critical
    """
    if len(expected) != len(actual):
        raise ValueError(f"expected and actual must have same length, got {len(expected)} vs {len(actual)}")

    e_total = sum(expected)
    a_total = sum(actual)
    if e_total == 0 or a_total == 0:
        raise ValueError("distributions must be non-empty")

    psi = 0.0
    for e_i, a_i in zip(expected, actual):
        e_p = (e_i / e_total) + epsilon
        a_p = (a_i / a_total) + epsilon
        psi += (a_p - e_p) * math.log(a_p / e_p)
    return psi


def ks_statistic(sample_a: list[float], sample_b: list[float]) -> float:
    """Two-sample Kolmogorov-Smirnov D statistic: max |CDF_a(x) - CDF_b(x)|.

    Pure Python, O(n log n). Returns value in [0, 1].
    """
    if not sample_a or not sample_b:
        raise ValueError("samples must be non-empty")

    sorted_a = sorted(sample_a)
    sorted_b = sorted(sample_b)
    n_a = len(sorted_a)
    n_b = len(sorted_b)

    all_vals = sorted(set(sorted_a + sorted_b))
    max_d = 0.0
    for x in all_vals:
        cdf_a = sum(1 for v in sorted_a if v <= x) / n_a
        cdf_b = sum(1 for v in sorted_b if v <= x) / n_b
        max_d = max(max_d, abs(cdf_a - cdf_b))
    return max_d
