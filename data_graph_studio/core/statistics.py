"""
Statistical Analysis - Spotfire 스타일 통계 분석 도구

상관 분석, 클러스터링, 시계열 분석, 가설 검정 등을 제공합니다.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from scipy import stats

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
]

logger = logging.getLogger(__name__)


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


class DescriptiveStatistics:
    """
    기술 통계

    기본적인 통계량을 계산합니다.
    """

    def calculate(
        self,
        values: np.ndarray
    ) -> Dict[str, float]:
        """
        기술 통계량 계산

        Args:
            values: 데이터 배열

        Returns:
            통계량 딕셔너리
        """
        values = values[~np.isnan(values)]

        if len(values) == 0:
            logger.warning("statistics.calculate.empty_values")
            return {}

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
        """
        평균의 신뢰 구간

        Args:
            values: 데이터 배열
            confidence: 신뢰 수준

        Returns:
            (하한, 상한) 튜플
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
        """
        백분위수 계산

        Args:
            values: 데이터 배열
            percentiles: 백분위수 목록 (0-100)

        Returns:
            {백분위수: 값} 딕셔너리
        """
        values = values[~np.isnan(values)]

        if len(values) == 0:
            return {p: 0 for p in percentiles}

        results = np.percentile(values, percentiles)

        return {p: float(v) for p, v in zip(percentiles, results)}
