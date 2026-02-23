"""
Statistical Analysis - Time Series Module

시계열 분석 관련 클래스를 제공합니다.
"""

import logging
from typing import Dict, Any, Optional
import numpy as np
from scipy.signal import find_peaks

from .metrics import get_metrics

logger = logging.getLogger(__name__)


class TimeSeriesAnalyzer:
    """Time series analysis utilities: smoothing, decomposition, autocorrelation, stationarity.

    All methods accept raw numpy arrays and return numpy arrays or dicts.
    No state is maintained between calls.
    """

    def moving_average(
        self,
        values: np.ndarray,
        window: int = 5
    ) -> np.ndarray:
        """Compute a simple trailing moving average.

        Input:
            values — np.ndarray, 1-D array of numeric time series values.
            window — int > 0, number of periods in the trailing window (default 5).
        Output: np.ndarray (float) — same length as values; the first (window-1) elements
            are NaN because insufficient history is available.
        Invariants: result[i] = mean(values[i-window+1 : i+1]) for i >= window-1.
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
        """Apply simple exponential smoothing (Holt's level-only model).

        Input:
            values — np.ndarray, 1-D numeric time series; must have at least one element.
            alpha — float in (0, 1], smoothing coefficient (default 0.3). Higher values
                give more weight to recent observations.
        Output: np.ndarray (float) — smoothed series; same length as values;
            result[0] == values[0].
        Invariants: result[i] = alpha * values[i] + (1-alpha) * result[i-1].
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
        """Decompose a time series into trend, seasonal, and residual components.

        Input:
            values — np.ndarray, 1-D numeric time series.
            period — int > 0, length of the seasonal cycle (default 12).
            model — str, 'additive' or 'multiplicative'. Additive: value = trend +
                seasonal + residual. Multiplicative: value = trend * seasonal * residual.
        Output: Dict[str, np.ndarray] with keys 'trend', 'seasonal', 'residual';
            each array is the same length as values. 'trend' contains NaN for the first
            (period-1) positions (from moving_average).
        Invariants:
            - trend computed via moving_average(values, window=period).
            - seasonal pattern is the per-position nanmean of the detrended series.
        """
        with get_metrics().timed_operation("statistics.timeseries.decompose"):
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
        """Compute the autocorrelation function (ACF) up to max_lag.

        Input:
            values — np.ndarray, 1-D numeric time series.
            max_lag — int >= 0, maximum lag to compute (default 20).
        Output: np.ndarray of float, shape (max_lag+1,); acf[0] == 1.0 always.
        Invariants:
            - When variance is 0 (constant series), returns np.ones(max_lag+1).
            - acf[lag] = Cov(values[lag:], values[:-lag]) / Var(values).
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
        """Compute the partial autocorrelation function (PACF) via the Durbin-Levinson algorithm.

        Input:
            values — np.ndarray, 1-D numeric time series.
            max_lag — int >= 0, maximum lag to compute (default 10).
        Output: np.ndarray of float, shape (max_lag+1,); pacf[0] == 1.0, pacf[1] == acf[1].
        Invariants: Uses autocorrelation() internally; pacf[k] is the partial correlation
            at lag k after removing linear effects of shorter lags.
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
        """Run a simplified Augmented Dickey-Fuller (ADF) stationarity test.

        Input: values — np.ndarray, 1-D numeric time series; must have at least 3 elements.
        Output: Dict[str, Any] with keys:
            'statistic' (float) — the ADF t-statistic.
            'p_value' (float) — approximate p-value (0.01/0.05/0.10/0.50 discretized).
            'is_stationary' (bool) — True when p_value < 0.05.
            'critical_values' (dict, on success) — {0.01: -3.43, 0.05: -2.86, 0.10: -2.57}.
        Raises: nothing — NumPy errors (e.g., singular matrix) are logged at WARNING
            and return {'statistic': 0, 'p_value': 1.0, 'is_stationary': False}.
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

        except (ValueError, TypeError, ArithmeticError) as e:
            logger.warning("statistics.stationarity_test.failed", extra={"error": str(e)}, exc_info=True)
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
        """Detect the dominant seasonal period using ACF peak detection.

        Input:
            values — np.ndarray, 1-D numeric time series.
            max_period — int, maximum lag to examine in the ACF (default 50).
        Output: Optional[int] — lag of the first ACF peak with height > 0.1;
            None when no such peak is found.
        Invariants: Uses scipy.signal.find_peaks on acf[1:] (lag-0 excluded).
        """
        acf = self.autocorrelation(values, max_period)

        # 피크 찾기
        peaks, _ = find_peaks(acf[1:], height=0.1)

        if len(peaks) > 0:
            return int(peaks[0] + 1)

        return None
