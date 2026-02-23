"""
Tests for comparison_algorithms.py

Covers:
- select_test_type: normal path (large sample, small normal, small non-normal),
  boundary (tiny samples), error (empty array, single element)
- interpret_test_result: significance thresholds, effect size labels, direction text
- run_normality_test: Shapiro-Wilk normal path, non-normal path, boundary (< 3 points),
  large dataset triggers D'Agostino-Pearson
"""

from __future__ import annotations

import numpy as np
import pytest

from data_graph_studio.core.comparison_algorithms import (
    HAS_SCIPY,
    interpret_test_result,
    run_normality_test,
    select_test_type,
)


# ---------------------------------------------------------------------------
# select_test_type
# ---------------------------------------------------------------------------

class TestSelectTestType:
    """Tests for select_test_type."""

    def test_large_samples_always_ttest(self):
        """Both samples >= 30 → always ttest regardless of normality."""
        rng = np.random.default_rng(0)
        # Exponential distribution — not normal, but large N → ttest
        a = rng.exponential(scale=1.0, size=50)
        b = rng.exponential(scale=2.0, size=50)
        assert select_test_type(a, b) == "ttest"

    def test_small_normal_samples_returns_ttest(self):
        """Small samples that pass Shapiro-Wilk → ttest."""
        if not HAS_SCIPY:
            pytest.skip("scipy not installed")
        rng = np.random.default_rng(42)
        a = rng.normal(0, 1, 20)
        b = rng.normal(0, 1, 20)
        result = select_test_type(a, b)
        # Both drawn from normal distribution; Shapiro should pass → ttest
        assert result == "ttest"

    def test_small_non_normal_samples_returns_mannwhitney(self):
        """Small samples that fail Shapiro-Wilk → mannwhitney."""
        if not HAS_SCIPY:
            pytest.skip("scipy not installed")
        # Bimodal distribution — very likely to fail normality
        a = np.concatenate([np.full(10, 0.0), np.full(10, 100.0)])
        b = np.concatenate([np.full(10, 0.0), np.full(10, 100.0)])
        result = select_test_type(a, b)
        assert result == "mannwhitney"

    def test_tiny_sample_below_3_treated_as_normal(self):
        """Sample size < 3 skips Shapiro → p defaults to 1 → ttest."""
        a = np.array([1.0, 2.0])  # len 2 < 3
        b = np.array([3.0, 4.0])
        # Should not raise; Shapiro is skipped, defaults to ttest
        result = select_test_type(a, b)
        assert result == "ttest"

    def test_empty_array_returns_ttest(self):
        """Empty arrays skip Shapiro and fall back to ttest."""
        a = np.array([])
        b = np.array([1.0, 2.0, 3.0])
        result = select_test_type(a, b)
        assert result == "ttest"


# ---------------------------------------------------------------------------
# interpret_test_result
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("p_value,expected_sig", [
    (0.0005, "highly significant (p < 0.001)"),
    (0.005,  "very significant (p < 0.01)"),
    (0.03,   "significant (p < 0.05)"),
    (0.1,    "not significant (p ≥ 0.05)"),
])
def test_interpret_significance_thresholds(p_value, expected_sig):
    text = interpret_test_result("ttest", p_value, 0.0, "A", "B")
    assert expected_sig in text


@pytest.mark.parametrize("effect_size,expected_label", [
    (0.1,  "negligible"),
    (0.3,  "small"),
    (0.6,  "medium"),
    (1.0,  "large"),
    (-0.9, "large"),   # negative large effect still labelled large
])
def test_interpret_effect_size_labels(effect_size, expected_label):
    text = interpret_test_result("ttest", 0.5, effect_size, "A", "B")
    assert expected_label in text


def test_interpret_direction_positive():
    text = interpret_test_result("ttest", 0.01, 0.5, "GroupA", "GroupB")
    assert "GroupA > GroupB" in text


def test_interpret_direction_negative():
    text = interpret_test_result("ttest", 0.01, -0.5, "GroupA", "GroupB")
    assert "GroupA < GroupB" in text


def test_interpret_direction_zero_effect():
    text = interpret_test_result("ttest", 0.8, 0.0, "GroupA", "GroupB")
    assert "GroupA ≈ GroupB" in text


def test_interpret_contains_effect_value():
    """d= value is formatted to 3 decimal places."""
    text = interpret_test_result("ttest", 0.04, 0.456, "A", "B")
    assert "d=0.456" in text


# ---------------------------------------------------------------------------
# run_normality_test
# ---------------------------------------------------------------------------

class TestRunNormalityTest:

    def test_normal_data_shapiro_wilk(self):
        """Normally distributed data → Shapiro-Wilk, is_normal True."""
        if not HAS_SCIPY:
            pytest.skip("scipy not installed")
        rng = np.random.default_rng(7)
        data = rng.normal(0, 1, 100)
        result = run_normality_test(data)
        assert "error" not in result
        assert result["test_name"] == "Shapiro-Wilk"
        assert result["is_normal"] == True  # noqa: E712 (np.bool_ compat)
        assert result["p_value"] >= 0.05

    def test_non_normal_data_detected(self):
        """Clearly non-normal data (uniform integers) → is_normal False."""
        if not HAS_SCIPY:
            pytest.skip("scipy not installed")
        # Uniform distribution fails normality test with enough points
        rng = np.random.default_rng(99)
        data = rng.uniform(0, 1, 500)
        result = run_normality_test(data)
        assert "error" not in result
        # p_value should be very small; is_normal False
        assert result["is_normal"] == False  # noqa: E712 (np.bool_ compat)

    def test_large_dataset_uses_dagostino(self):
        """Dataset > 5000 points → D'Agostino-Pearson test."""
        if not HAS_SCIPY:
            pytest.skip("scipy not installed")
        rng = np.random.default_rng(1)
        data = rng.normal(0, 1, 6000)
        result = run_normality_test(data)
        assert "error" not in result
        assert result["test_name"] == "D'Agostino-Pearson"

    def test_result_keys_present(self):
        """Result dict contains all expected keys."""
        if not HAS_SCIPY:
            pytest.skip("scipy not installed")
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = run_normality_test(data)
        assert "error" not in result
        for key in ("test_name", "statistic", "p_value", "is_normal", "interpretation"):
            assert key in result

    def test_too_few_points_returns_error(self):
        """< 3 data points → error key in result."""
        data = np.array([1.0, 2.0])
        result = run_normality_test(data)
        assert "error" in result
        assert "enough" in result["error"].lower()

    def test_single_element_returns_error(self):
        """Single element array → error."""
        result = run_normality_test(np.array([42.0]))
        assert "error" in result

    def test_empty_array_returns_error(self):
        """Empty array → error."""
        result = run_normality_test(np.array([]))
        assert "error" in result

    def test_statistic_is_float(self):
        """statistic field is a Python float, not numpy scalar."""
        if not HAS_SCIPY:
            pytest.skip("scipy not installed")
        data = np.linspace(0, 1, 50)
        result = run_normality_test(data)
        if "error" not in result:
            assert isinstance(result["statistic"], float)
            assert isinstance(result["p_value"], float)
