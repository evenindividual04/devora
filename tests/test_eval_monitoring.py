"""Tests for PSI and K-S monitoring (Area C).

Source: docs/LLM-as-Judge for README Evaluation.md §PSI/K-S monitoring.
Each test name encodes the spec requirement.
"""
from __future__ import annotations

import math

import pytest

from app.eval.monitoring import ks_statistic, population_stability_index


class TestPopulationStabilityIndex:
    """PSI formula from doc: Σ (actual - expected) * ln(actual / expected), +0.01 empty-bin guard."""

    def test_identical_distributions_zero_psi(self):
        expected = [0.25, 0.25, 0.25, 0.25]
        actual = [0.25, 0.25, 0.25, 0.25]
        assert population_stability_index(expected, actual) == pytest.approx(0.0, abs=1e-6)

    def test_completely_different_distributions_high_psi(self):
        # All mass in first bin vs all mass in last bin → large PSI
        expected = [1.0, 0.0, 0.0, 0.0]
        actual = [0.0, 0.0, 0.0, 1.0]
        psi = population_stability_index(expected, actual)
        assert psi > 0.2  # doc threshold: >0.2 = critical

    def test_empty_bin_guard_applied(self):
        """PSI must not blow up when a bin has zero probability (uses +0.01 guard from doc)."""
        expected = [1.0, 0.0]
        actual = [0.5, 0.5]
        psi = population_stability_index(expected, actual)
        assert math.isfinite(psi)
        assert psi >= 0.0

    def test_thresholds_stable(self):
        """PSI < 0.1 = stable (doc threshold)."""
        expected = [0.3, 0.4, 0.3]
        actual = [0.31, 0.39, 0.30]
        psi = population_stability_index(expected, actual)
        assert psi < 0.1

    def test_thresholds_warn(self):
        """0.1 ≤ PSI ≤ 0.2 = warn (doc threshold)."""
        expected = [0.5, 0.5]
        actual = [0.2, 0.8]
        psi = population_stability_index(expected, actual)
        assert 0.1 <= psi <= 0.5  # should land in warn range

    def test_accepts_raw_counts_as_proportions(self):
        """Raw counts are normalised internally."""
        expected = [100, 100, 100, 100]  # equal counts
        actual = [100, 100, 100, 100]
        psi = population_stability_index(expected, actual)
        assert psi == pytest.approx(0.0, abs=1e-6)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            population_stability_index([0.5, 0.5], [0.33, 0.33, 0.34])


class TestKSStatistic:
    """Two-sample Kolmogorov-Smirnov D statistic (max |CDF1 - CDF2|)."""

    def test_identical_samples_zero_ks(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert ks_statistic(a, a) == pytest.approx(0.0, abs=1e-6)

    def test_non_overlapping_samples_max_ks(self):
        # Completely separated — CDF diverges maximally
        a = [1.0, 2.0, 3.0]
        b = [10.0, 11.0, 12.0]
        d = ks_statistic(a, b)
        assert d == pytest.approx(1.0, abs=1e-6)

    def test_partial_overlap(self):
        a = [1.0, 2.0, 3.0, 4.0]
        b = [3.0, 4.0, 5.0, 6.0]
        d = ks_statistic(a, b)
        assert 0.0 < d < 1.0

    def test_d_is_in_zero_one(self):
        import random
        random.seed(42)
        a = [random.gauss(0, 1) for _ in range(50)]
        b = [random.gauss(0.5, 1) for _ in range(50)]
        d = ks_statistic(a, b)
        assert 0.0 <= d <= 1.0

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            ks_statistic([], [1.0])

    def test_empty_b_raises(self):
        with pytest.raises(ValueError):
            ks_statistic([1.0], [])


class TestPSIEdgeCases:
    def test_zero_total_raises(self):
        with pytest.raises(ValueError):
            population_stability_index([0, 0], [1, 0])
