"""
Statistical Analysis - Time Series Module

시계열 분석 관련 클래스를 제공합니다.
"""

import logging
from typing import Dict, Any, Optional
import numpy as np
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)


class TimeSeriesAnalyzer:
    """
    시계열 분석기

    이동 평균, 분해, 자기상관 분석 등을 제공합니다.
    """

    def moving_average(
        self,
        values: np.ndarray,
        window: int = 5
    ) -> np.ndarray:
        """
        이동 평균

        Args:
            values: 시계열 값
            window: 윈도우 크기

        Returns:
            이동 평균 배열
        """
        result = np.full_like(values, np.nan, dtype=float)

        for i in range(window - 1, len(values)):
            result[i] = np.mean(values[i - window + 1:i + 1])

        return result

    def exponential_smoothing(
        self,
        values: np.ndarray,
        alpha: float = 0.3
    ) -> np.ndarray:
        """
        지수 평활

        Args:
            values: 시계열 값
            alpha: 평활 계수 (0 < alpha <= 1)

        Returns:
            평활된 배열
        """
        result = np.zeros_like(values, dtype=float)
        result[0] = values[0]

        for i in range(1, len(values)):
            result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]

        return result

    def decompose(
        self,
        values: np.ndarray,
        period: int = 12,
        model: str = "additive"
    ) -> Dict[str, np.ndarray]:
        """
        시계열 분해 (트렌드 + 계절성 + 잔차)

        Args:
            values: 시계열 값
            period: 계절성 주기
            model: 분해 모델 ("additive" 또는 "multiplicative")

        Returns:
            {"trend", "seasonal", "residual"} 딕셔너리
        """
        n = len(values)

        # 트렌드 (이동 평균)
        trend = self.moving_average(values, window=period)

        # 계절성 제거된 값
        if model == "additive":
            detrended = values - trend
        else:
            detrended = values / np.where(trend != 0, trend, 1)

        # 계절성 패턴 추출
        seasonal = np.zeros(n)
        for i in range(period):
            indices = np.arange(i, n, period)
            valid = ~np.isnan(detrended[indices])
            if np.sum(valid) > 0:
                pattern = np.nanmean(detrended[indices])
                seasonal[indices] = pattern

        # 잔차
        if model == "additive":
            residual = values - trend - seasonal
        else:
            residual = values / (trend * seasonal + 1e-10)

        return {
            "trend": trend,
            "seasonal": seasonal,
            "residual": residual
        }

    def autocorrelation(
        self,
        values: np.ndarray,
        max_lag: int = 20
    ) -> np.ndarray:
        """
        자기상관 함수 (ACF)

        Args:
            values: 시계열 값
            max_lag: 최대 시차

        Returns:
            자기상관 계수 배열
        """
        n = len(values)
        mean = np.mean(values)
        var = np.var(values)

        if var == 0:
            return np.ones(max_lag + 1)

        acf = np.zeros(max_lag + 1)

        for lag in range(max_lag + 1):
            if lag == 0:
                acf[0] = 1.0
            else:
                cov = np.sum((values[lag:] - mean) * (values[:-lag] - mean)) / n
                acf[lag] = cov / var

        return acf

    def partial_autocorrelation(
        self,
        values: np.ndarray,
        max_lag: int = 10
    ) -> np.ndarray:
        """
        편자기상관 함수 (PACF)

        Args:
            values: 시계열 값
            max_lag: 최대 시차

        Returns:
            편자기상관 계수 배열
        """
        acf = self.autocorrelation(values, max_lag)
        pacf = np.zeros(max_lag + 1)
        pacf[0] = 1.0

        if max_lag > 0:
            pacf[1] = acf[1]

        # Durbin-Levinson 알고리즘
        phi = np.zeros((max_lag + 1, max_lag + 1))
        phi[1, 1] = acf[1]

        for k in range(2, max_lag + 1):
            numerator = acf[k] - sum(phi[k-1, j] * acf[k-j] for j in range(1, k))
            denominator = 1 - sum(phi[k-1, j] * acf[j] for j in range(1, k))

            if denominator == 0:
                phi[k, k] = 0
            else:
                phi[k, k] = numerator / denominator

            for j in range(1, k):
                phi[k, j] = phi[k-1, j] - phi[k, k] * phi[k-1, k-j]

            pacf[k] = phi[k, k]

        return pacf

    def stationarity_test(
        self,
        values: np.ndarray
    ) -> Dict[str, Any]:
        """
        정상성 검정 (Augmented Dickey-Fuller Test 단순화)

        Returns:
            {"statistic", "p_value", "is_stationary"} 딕셔너리
        """
        # 단순화된 ADF 테스트 (1차 차분 사용)
        diff = np.diff(values)
        lagged = values[:-1]

        # 회귀: diff = alpha + beta * lagged + error
        X = np.column_stack([np.ones(len(lagged)), lagged])
        try:
            coeffs = np.linalg.lstsq(X, diff, rcond=None)[0]
            beta = coeffs[1]

            # 잔차
            residuals = diff - X @ coeffs
            se = np.sqrt(np.sum(residuals**2) / (len(diff) - 2))

            # t-통계량
            X_inv = np.linalg.inv(X.T @ X)
            se_beta = se * np.sqrt(X_inv[1, 1])
            t_stat = beta / se_beta if se_beta != 0 else 0

            # ADF 임계값 (근사)
            critical_values = {0.01: -3.43, 0.05: -2.86, 0.10: -2.57}

            # p-value 근사
            if t_stat < critical_values[0.01]:
                p_value = 0.01
            elif t_stat < critical_values[0.05]:
                p_value = 0.05
            elif t_stat < critical_values[0.10]:
                p_value = 0.10
            else:
                p_value = 0.5

            return {
                "statistic": t_stat,
                "p_value": p_value,
                "is_stationary": p_value < 0.05,
                "critical_values": critical_values
            }

        except Exception as e:
            logger.warning("statistics.stationarity_test.failed", extra={"error": str(e)})
            return {
                "statistic": 0,
                "p_value": 1.0,
                "is_stationary": False
            }

    def detect_seasonality(
        self,
        values: np.ndarray,
        max_period: int = 50
    ) -> Optional[int]:
        """
        계절성 주기 탐지

        Returns:
            탐지된 주기 또는 None
        """
        acf = self.autocorrelation(values, max_period)

        # 피크 찾기
        peaks, _ = find_peaks(acf[1:], height=0.1)

        if len(peaks) > 0:
            return int(peaks[0] + 1)

        return None
