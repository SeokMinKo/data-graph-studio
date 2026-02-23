"""
Statistical Analysis - Spotfire 스타일 통계 분석 도구

상관 분석, 클러스터링, 시계열 분석, 가설 검정 등을 제공합니다.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple
from dataclasses import dataclass
import numpy as np
from scipy import stats

from data_graph_studio.core.metrics import get_metrics
from data_graph_studio.core.file_loader import _run_with_timeout
from data_graph_studio.core.constants import STATISTICS_TIMEOUT

from data_graph_studio.core.statistics_correlation import (
    CorrelationMethod,
    CorrelationResult,
    CorrelationAnalyzer,
)
from data_graph_studio.core.statistics_clustering import (
    ClusterMethod,
    ClusterResult,
    ClusterAnalyzer,
)
from data_graph_studio.core.statistics_timeseries import TimeSeriesAnalyzer
from data_graph_studio.core.statistics_hypothesis import (
    HypothesisTest,
    HypothesisTestResult,
    HypothesisTester,
)

__all__ = [
    "CorrelationMethod",
    "CorrelationResult",
    "CorrelationAnalyzer",
    "ClusterMethod",
    "ClusterResult",
    "ClusterAnalyzer",
    "TimeSeriesAnalyzer",
    "HypothesisTest",
    "HypothesisTestResult",
    "HypothesisTester",
    "StatisticalSummary",
    "DescriptiveStatistics",
    "IStatisticsAnalyzer",
]

logger = logging.getLogger(__name__)


class IStatisticsAnalyzer(ABC):
    """Abstract interface for statistical analysis operations."""

    @abstractmethod
    def calculate(self, data) -> dict:
        """Calculate descriptive statistics for the given data.

        Input: data — the data object to analyse (type depends on implementation)
        Output: dict — key/value mapping of statistic names to computed values
        """
        ...


@dataclass
class StatisticalSummary:
    """통계 요약"""
    mean: float
    median: float
    std: float
    var: float
    min: float
    max: float
    q1: float
    q3: float
    iqr: float
    skewness: float
    kurtosis: float
    n: int


class DescriptiveStatistics(IStatisticsAnalyzer):
    """
    기술 통계

    기본적인 통계량을 계산합니다.
    """

    def calculate(
        self,
        values: np.ndarray
    ) -> Dict[str, float]:
        """Compute descriptive statistics for a numeric array, excluding NaN values.

        Input:
            values: np.ndarray of numeric values. May contain NaN values, which are
                excluded before calculation. May be empty after NaN removal.

        Output:
            Dict with keys: mean, median, std, var, min, max, q1, q3, iqr, skewness,
            kurtosis, n, se (standard error). Returns an empty dict if all values are NaN.

        Raises:
            DataLoadError: If the operation exceeds STATISTICS_TIMEOUT seconds.

        Invariants:
            - NaN values are always stripped before any computation.
            - Returns {} (not None) when the cleaned array is empty.
            - Operation is timed via MetricsCollector.timed_operation("statistics.calculate").
            - "statistics.calculated" counter is incremented on successful computation.
        """
        return _run_with_timeout(
            lambda: self._calculate_impl(values),
            timeout_s=STATISTICS_TIMEOUT,
            operation="statistics.calculate",
        )

    def _calculate_impl(
        self,
        values: np.ndarray
    ) -> Dict[str, float]:
        """Internal implementation for calculate; runs under timeout."""
        with get_metrics().timed_operation("statistics.calculate"):
            values = values[~np.isnan(values)]

            if len(values) == 0:
                logger.warning("statistics.calculate.empty_values")
                return {}

            get_metrics().increment("statistics.calculated")
            logger.debug("statistics.calculate", extra={"n": len(values)})
            q1, median, q3 = np.percentile(values, [25, 50, 75])

            return {
                "mean": float(np.mean(values)),
                "median": float(median),
                "std": float(np.std(values)),
                "var": float(np.var(values)),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "q1": float(q1),
                "q3": float(q3),
                "iqr": float(q3 - q1),
                "skewness": float(stats.skew(values)),
                "kurtosis": float(stats.kurtosis(values)),
                "n": len(values),
                "se": float(np.std(values) / np.sqrt(len(values)))  # 표준 오차
            }

    def confidence_interval(
        self,
        values: np.ndarray,
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """Compute the confidence interval for the mean of a numeric array.

        Input:
            values: np.ndarray of numeric values. NaN values are excluded. May be empty.
            confidence: Confidence level between 0 and 1 exclusive (default 0.95).

        Output:
            Tuple (lower_bound, upper_bound) of the confidence interval for the mean.
            When fewer than 2 non-NaN values remain, returns (mean, mean) — a degenerate
            interval of width 0.

        Raises:
            None

        Invariants:
            - lower_bound <= mean <= upper_bound.
            - Width shrinks as len(values) grows (for fixed confidence and variance).
        """
        values = values[~np.isnan(values)]

        if len(values) < 2:
            mean = np.mean(values) if len(values) > 0 else 0
            return (mean, mean)

        mean = np.mean(values)
        se = stats.sem(values)
        h = se * stats.t.ppf((1 + confidence) / 2, len(values) - 1)

        return (mean - h, mean + h)

    def percentile(
        self,
        values: np.ndarray,
        percentiles: List[float]
    ) -> Dict[float, float]:
        """Compute requested percentiles for a numeric array.

        Input:
            values: np.ndarray of numeric values. NaN values are excluded.
            percentiles: List of percentile values in the range [0, 100] to compute
                (e.g., [25, 50, 75]).

        Output:
            Dict mapping each requested percentile to its computed value. Returns
            {p: 0 for p in percentiles} when all values are NaN or the array is empty.

        Raises:
            None

        Invariants:
            - All keys in the result exactly match the input percentiles list.
            - Results are monotonically non-decreasing for sorted percentiles.
        """
        values = values[~np.isnan(values)]

        if len(values) == 0:
            return {p: 0 for p in percentiles}

        results = np.percentile(values, percentiles)

        return {p: float(v) for p, v in zip(percentiles, results)}
