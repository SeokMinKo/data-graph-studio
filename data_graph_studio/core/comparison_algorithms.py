"""
Comparison Algorithms — pure statistical helpers extracted from comparison_engine.py

Contains standalone functions that do not depend on DatasetManager:
- select_test_type      — pick t-test vs Mann-Whitney based on normality
- interpret_test_result — format a human-readable test interpretation
- run_normality_test    — Shapiro-Wilk / D'Agostino-Pearson normality check
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import numpy as np

try:
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from data_graph_studio.core.constants import (
    SHAPIRO_WILK_MAX_SAMPLE,
    NORMALITY_SIGNIFICANCE_LEVEL,
    STATISTICAL_SAMPLE_THRESHOLD,
)

logger = logging.getLogger(__name__)


def select_test_type(data_a: np.ndarray, data_b: np.ndarray) -> str:
    """정규성에 따라 적절한 검정 방법을 선택한다.

    Args:
        data_a: 첫 번째 데이터.
        data_b: 두 번째 데이터.

    Returns:
        검정 유형 문자열 ('ttest' | 'mannwhitney').
    """
    if not HAS_SCIPY:
        return "ttest"

    if len(data_a) >= STATISTICAL_SAMPLE_THRESHOLD and len(data_b) >= STATISTICAL_SAMPLE_THRESHOLD:
        return "ttest"

    try:
        sample_a = data_a[:SHAPIRO_WILK_MAX_SAMPLE] if len(data_a) > SHAPIRO_WILK_MAX_SAMPLE else data_a
        sample_b = data_b[:SHAPIRO_WILK_MAX_SAMPLE] if len(data_b) > SHAPIRO_WILK_MAX_SAMPLE else data_b
        _, p_a = scipy_stats.shapiro(sample_a) if len(sample_a) >= 3 else (0, 1)
        _, p_b = scipy_stats.shapiro(sample_b) if len(sample_b) >= 3 else (0, 1)
        return "ttest" if p_a >= NORMALITY_SIGNIFICANCE_LEVEL and p_b >= NORMALITY_SIGNIFICANCE_LEVEL else "mannwhitney"
    except (ValueError, TypeError):
        logger.debug("comparison_algorithms.select_test_type.failed", exc_info=True)
        return "ttest"


def interpret_test_result(
    test_name: str,
    p_value: float,
    effect_size: float,
    name_a: str,
    name_b: str,
) -> str:
    """검정 결과를 해석한다.

    Args:
        test_name: 검정 이름.
        p_value: p-value.
        effect_size: 효과 크기 (Cohen's d).
        name_a: 데이터셋 A 이름.
        name_b: 데이터셋 B 이름.

    Returns:
        해석 문자열.
    """
    if p_value < 0.001:
        sig_text = "highly significant (p < 0.001)"
    elif p_value < 0.01:
        sig_text = "very significant (p < 0.01)"
    elif p_value < 0.05:
        sig_text = "significant (p < 0.05)"
    else:
        sig_text = "not significant (p ≥ 0.05)"

    abs_effect = abs(effect_size)
    if abs_effect < 0.2:
        effect_text = "negligible"
    elif abs_effect < 0.5:
        effect_text = "small"
    elif abs_effect < 0.8:
        effect_text = "medium"
    else:
        effect_text = "large"

    direction = f"{name_a} > {name_b}" if effect_size > 0 else (
        f"{name_a} < {name_b}" if effect_size < 0 else f"{name_a} ≈ {name_b}")

    return (
        f"The difference between datasets is {sig_text}. "
        f"Effect size is {effect_text} (d={effect_size:.3f}). "
        f"Direction: {direction}"
    )


def run_normality_test(data: np.ndarray) -> Dict[str, Any]:
    """정규성 검정을 수행한다 (Shapiro-Wilk or D'Agostino-Pearson).

    Args:
        data: 검정할 numpy 배열 (nulls already dropped).

    Returns:
        검정 결과 딕셔너리 with keys:
            test_name, statistic, p_value, is_normal, interpretation
        or {"error": ...} on failure.
    """
    if not HAS_SCIPY:
        return {"error": "scipy is not installed"}

    if len(data) < 3:
        return {"error": "Not enough data points"}

    try:
        if len(data) <= SHAPIRO_WILK_MAX_SAMPLE:
            stat, p_val = scipy_stats.shapiro(data[:SHAPIRO_WILK_MAX_SAMPLE])
            test_name = "Shapiro-Wilk"
        else:
            stat, p_val = scipy_stats.normaltest(data)
            test_name = "D'Agostino-Pearson"

        is_normal = p_val >= NORMALITY_SIGNIFICANCE_LEVEL
        interpretation = (
            f"Data appears to be normally distributed (p = {p_val:.4f})"
            if is_normal else
            f"Data is not normally distributed (p = {p_val:.4f})"
        )

        return {
            "test_name": test_name,
            "statistic": float(stat),
            "p_value": float(p_val),
            "is_normal": is_normal,
            "interpretation": interpretation,
        }
    except (ValueError, TypeError, ArithmeticError) as e:
        return {"error": str(e)}
