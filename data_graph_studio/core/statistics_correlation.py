"""
Statistical Analysis - Correlation Module

상관 분석 관련 클래스를 제공합니다.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
import polars as pl
from scipy import stats

logger = logging.getLogger(__name__)


class CorrelationMethod(Enum):
    """상관 계수 방법"""
    PEARSON = "pearson"      # 피어슨 (선형 관계)
    SPEARMAN = "spearman"    # 스피어만 (순위 기반)
    KENDALL = "kendall"      # 켄달 타우 (순위 기반)


@dataclass
class CorrelationResult:
    """상관 분석 결과"""
    matrix: np.ndarray
    columns: List[str]
    method: CorrelationMethod
    p_value_matrix: Optional[np.ndarray] = None

    def get_correlation(self, col1: str, col2: str) -> float:
        """Return the pre-computed correlation coefficient between two columns.

        Input: col1 — str, first column name (must be in self.columns);
               col2 — str, second column name (must be in self.columns).
        Output: float — correlation coefficient in [-1.0, 1.0].
        Raises: ValueError — if col1 or col2 is not in self.columns.
        """
        i = self.columns.index(col1)
        j = self.columns.index(col2)
        return self.matrix[i, j]

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        """Convert the correlation matrix to a nested dictionary.

        Output: Dict[str, Dict[str, float]] — outer key is col1, inner key is col2,
                value is the correlation coefficient between them.
        """
        result = {}
        for i, col1 in enumerate(self.columns):
            result[col1] = {}
            for j, col2 in enumerate(self.columns):
                result[col1][col2] = self.matrix[i, j]
        return result


class CorrelationAnalyzer:
    """
    상관 분석기

    변수 간 상관관계를 분석합니다.
    """

    def calculate_correlation(
        self,
        data: pl.DataFrame,
        columns: List[str],
        method: CorrelationMethod = CorrelationMethod.PEARSON
    ) -> CorrelationResult:
        """Compute a pairwise correlation matrix for the specified columns.

        Input: data — pl.DataFrame, source data; columns — List[str], column names to analyse
               (non-existent columns are silently skipped); method — CorrelationMethod.
        Output: CorrelationResult — contains the n×n matrix, p-value matrix, column list,
                and method used.
        Invariants: diagonal of the correlation matrix is always 1.0; p-value diagonal is NaN.
        """
        # 데이터 추출
        logger.debug("statistics.calculate_correlation", extra={"method": method.value, "columns": columns})
        valid_columns = [c for c in columns if c in data.columns]
        subset = data.select(valid_columns).to_numpy()

        n = len(valid_columns)
        matrix = np.zeros((n, n))
        p_matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i, j] = 1.0
                    p_matrix[i, j] = np.nan
                else:
                    corr, p_value = self.pairwise_correlation(
                        subset[:, i], subset[:, j], method
                    )
                    matrix[i, j] = corr
                    p_matrix[i, j] = p_value

        return CorrelationResult(
            matrix=matrix,
            columns=valid_columns,
            method=method,
            p_value_matrix=p_matrix
        )

    def pairwise_correlation(
        self,
        x: np.ndarray,
        y: np.ndarray,
        method: CorrelationMethod = CorrelationMethod.PEARSON
    ) -> Tuple[float, float]:
        """Compute the correlation coefficient and p-value for two numeric arrays.

        Input: x — np.ndarray, first variable; y — np.ndarray, second variable (same length);
               method — CorrelationMethod (PEARSON, SPEARMAN, or KENDALL).
        Output: Tuple[float, float] — (correlation_coefficient, p_value); returns (0.0, 1.0)
                when fewer than 3 non-NaN paired observations remain after masking.
        Invariants: NaN values are excluded from both arrays jointly before computation.
        """
        # NaN 제거
        mask = ~(np.isnan(x) | np.isnan(y))
        x_clean = x[mask]
        y_clean = y[mask]

        if len(x_clean) < 3:
            return 0.0, 1.0

        if method == CorrelationMethod.PEARSON:
            corr, p_value = stats.pearsonr(x_clean, y_clean)
        elif method == CorrelationMethod.SPEARMAN:
            corr, p_value = stats.spearmanr(x_clean, y_clean)
        elif method == CorrelationMethod.KENDALL:
            corr, p_value = stats.kendalltau(x_clean, y_clean)
        else:
            corr, p_value = 0.0, 1.0

        return corr, p_value

    def get_p_value_matrix(self, result: CorrelationResult) -> np.ndarray:
        """Return the p-value matrix from a CorrelationResult.

        Input: result — CorrelationResult produced by calculate_correlation.
        Output: np.ndarray — n×n matrix of p-values; diagonal entries are NaN.
        """
        return result.p_value_matrix

    def get_significant_pairs(
        self,
        result: CorrelationResult,
        alpha: float = 0.05,
        min_correlation: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Return column pairs whose correlation is statistically significant and meets the minimum threshold.

        Input: result — CorrelationResult from calculate_correlation; alpha — float, significance
               level (default 0.05); min_correlation — float, minimum absolute correlation value
               (default 0.0).
        Output: List[Dict[str, Any]] — each entry has keys 'col1', 'col2', 'correlation',
                'p_value'; sorted by absolute correlation descending.
        Invariants: only upper-triangle pairs are checked (no duplicates); diagonal is excluded.
        """
        pairs = []
        n = len(result.columns)

        for i in range(n):
            for j in range(i + 1, n):
                corr = result.matrix[i, j]
                p_value = result.p_value_matrix[i, j]

                if p_value < alpha and abs(corr) >= min_correlation:
                    pairs.append({
                        "col1": result.columns[i],
                        "col2": result.columns[j],
                        "correlation": corr,
                        "p_value": p_value
                    })

        return sorted(pairs, key=lambda x: abs(x["correlation"]), reverse=True)
