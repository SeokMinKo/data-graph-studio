"""
Curve Fitting - Spotfire 스타일 Lines & Curves

추세선, 회귀 분석, 예측 기능을 제공합니다.
"""

from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from scipy import optimize
from scipy import stats


class FitType(Enum):
    """피팅 타입"""

    LINEAR = "linear"  # 선형 회귀 (y = ax + b)
    POLYNOMIAL = "polynomial"  # 다항식 회귀 (y = a_n*x^n + ... + a_1*x + a_0)
    EXPONENTIAL = "exponential"  # 지수 회귀 (y = a * e^(bx))
    POWER = "power"  # 거듭제곱 회귀 (y = a * x^b)
    LOGARITHMIC = "logarithmic"  # 로그 회귀 (y = a * ln(x) + b)
    LOGISTIC = "logistic"  # 로지스틱 회귀 (y = L / (1 + e^(-k(x-x0))))
    GAUSSIAN = "gaussian"  # 가우시안 피팅


@dataclass
class CurveFitSettings:
    """곡선 피팅 설정"""

    fit_type: FitType = FitType.LINEAR
    degree: int = 2  # 다항식 차수
    show_equation: bool = True
    show_r_squared: bool = True
    show_confidence_band: bool = False
    confidence_level: float = 0.95
    line_color: str = "#FF0000"
    line_width: float = 2.0
    line_style: str = "solid"  # solid, dashed, dotted


@dataclass
class ForecastSettings:
    """예측 설정"""

    forward_periods: int = 0  # 미래 예측 기간
    backward_periods: int = 0  # 과거 예측 (백캐스팅)
    period_size: float = 1.0  # 기간 크기


@dataclass
class CurveFitResult:
    """곡선 피팅 결과"""

    fit_type: FitType
    coefficients: np.ndarray
    r_squared: float
    std_error: float
    p_value: Optional[float] = None
    residuals: Optional[np.ndarray] = None
    predict_func: Optional[Callable] = None

    # 추가 통계
    adjusted_r_squared: Optional[float] = None
    f_statistic: Optional[float] = None
    aic: Optional[float] = None  # Akaike Information Criterion
    bic: Optional[float] = None  # Bayesian Information Criterion

    def get_equation_string(self, precision: int = 4) -> str:
        """수식 문자열 반환"""
        coeffs = self.coefficients

        if self.fit_type == FitType.LINEAR:
            a, b = coeffs[0], coeffs[1]
            sign = "+" if b >= 0 else "-"
            return f"y = {a:.{precision}f}x {sign} {abs(b):.{precision}f}"

        elif self.fit_type == FitType.POLYNOMIAL:
            terms = []
            degree = len(coeffs) - 1
            for i, c in enumerate(coeffs):
                power = degree - i
                if power == 0:
                    terms.append(f"{c:.{precision}f}")
                elif power == 1:
                    terms.append(f"{c:.{precision}f}x")
                else:
                    terms.append(f"{c:.{precision}f}x^{power}")
            return "y = " + " + ".join(terms)

        elif self.fit_type == FitType.EXPONENTIAL:
            a, b = coeffs[0], coeffs[1]
            return f"y = {a:.{precision}f} * e^({b:.{precision}f}x)"

        elif self.fit_type == FitType.POWER:
            a, b = coeffs[0], coeffs[1]
            return f"y = {a:.{precision}f} * x^{b:.{precision}f}"

        elif self.fit_type == FitType.LOGARITHMIC:
            a, b = coeffs[0], coeffs[1]
            sign = "+" if b >= 0 else "-"
            return f"y = {a:.{precision}f} * ln(x) {sign} {abs(b):.{precision}f}"

        elif self.fit_type == FitType.LOGISTIC:
            L, k, x0 = coeffs[0], coeffs[1], coeffs[2]
            return f"y = {L:.{precision}f} / (1 + e^(-{k:.{precision}f}(x - {x0:.{precision}f})))"

        return "Unknown equation"

    def get_statistics_string(self) -> str:
        """통계 문자열 반환"""
        lines = [f"R² = {self.r_squared:.4f}", f"Std Error = {self.std_error:.4f}"]

        if self.adjusted_r_squared is not None:
            lines.append(f"Adj R² = {self.adjusted_r_squared:.4f}")

        if self.p_value is not None:
            lines.append(f"p-value = {self.p_value:.4e}")

        if self.f_statistic is not None:
            lines.append(f"F-statistic = {self.f_statistic:.4f}")

        return "\n".join(lines)


class CurveFitter:
    """
    곡선 피팅 계산기

    다양한 회귀 모델을 지원하고 예측 기능을 제공합니다.
    """

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        fit_type: FitType,
        settings: Optional[CurveFitSettings] = None,
    ) -> Optional[CurveFitResult]:
        """
        곡선 피팅 수행

        Args:
            x: X 데이터
            y: Y 데이터
            fit_type: 피팅 타입
            settings: 피팅 설정

        Returns:
            피팅 결과 또는 None (실패 시)
        """
        if len(x) < 2 or len(y) < 2:
            return None

        if settings is None:
            settings = CurveFitSettings(fit_type=fit_type)

        # NaN 제거
        mask = ~(np.isnan(x) | np.isnan(y))
        x = x[mask]
        y = y[mask]

        if len(x) < 2:
            return None

        try:
            if fit_type == FitType.LINEAR:
                return self._fit_linear(x, y)
            elif fit_type == FitType.POLYNOMIAL:
                return self._fit_polynomial(x, y, settings.degree)
            elif fit_type == FitType.EXPONENTIAL:
                return self._fit_exponential(x, y)
            elif fit_type == FitType.POWER:
                return self._fit_power(x, y)
            elif fit_type == FitType.LOGARITHMIC:
                return self._fit_logarithmic(x, y)
            elif fit_type == FitType.LOGISTIC:
                return self._fit_logistic(x, y)
            elif fit_type == FitType.GAUSSIAN:
                return self._fit_gaussian(x, y)
        except Exception:
            return None

        return None

    def _fit_linear(self, x: np.ndarray, y: np.ndarray) -> CurveFitResult:
        """선형 회귀"""
        # scipy.stats.linregress 사용
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        coefficients = np.array([slope, intercept])
        r_squared = r_value**2

        # 잔차 계산
        y_pred = slope * x + intercept
        residuals = y - y_pred

        # 예측 함수
        def predict_func(x_new):
            return slope * x_new + intercept

        # Adjusted R²
        n = len(x)
        p = 1  # 독립 변수 수
        adj_r_squared = (
            1 - (1 - r_squared) * (n - 1) / (n - p - 1) if n > p + 1 else r_squared
        )

        return CurveFitResult(
            fit_type=FitType.LINEAR,
            coefficients=coefficients,
            r_squared=r_squared,
            std_error=std_err,
            p_value=p_value,
            residuals=residuals,
            predict_func=predict_func,
            adjusted_r_squared=adj_r_squared,
        )

    def _fit_polynomial(
        self, x: np.ndarray, y: np.ndarray, degree: int
    ) -> CurveFitResult:
        """다항식 회귀"""
        # numpy polyfit 사용
        coefficients = np.polyfit(x, y, degree)

        # 예측 함수
        poly = np.poly1d(coefficients)
        y_pred = poly(x)

        # R² 계산
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        # 잔차
        residuals = y - y_pred

        # 표준 오차
        n = len(x)
        p = degree
        std_error = np.sqrt(ss_res / (n - p - 1)) if n > p + 1 else 0

        # Adjusted R²
        adj_r_squared = (
            1 - (1 - r_squared) * (n - 1) / (n - p - 1) if n > p + 1 else r_squared
        )

        return CurveFitResult(
            fit_type=FitType.POLYNOMIAL,
            coefficients=coefficients,
            r_squared=r_squared,
            std_error=std_error,
            residuals=residuals,
            predict_func=poly,
            adjusted_r_squared=adj_r_squared,
        )

    def _fit_exponential(self, x: np.ndarray, y: np.ndarray) -> CurveFitResult:
        """지수 회귀 (y = a * e^(bx))"""
        # 로그 변환으로 선형화
        # ln(y) = ln(a) + bx

        # 양수값만 사용
        mask = y > 0
        if np.sum(mask) < 2:
            # 양수 데이터 부족 시 기본값 반환
            return CurveFitResult(
                fit_type=FitType.EXPONENTIAL,
                coefficients=np.array([1.0, 0.0]),
                r_squared=0.0,
                std_error=0.0,
            )

        x_valid = x[mask]
        y_valid = y[mask]
        log_y = np.log(y_valid)

        # 선형 회귀
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_valid, log_y)

        a = np.exp(intercept)
        b = slope
        coefficients = np.array([a, b])

        # 예측 함수
        def predict_func(x_new):
            return a * np.exp(b * x_new)

        # R² (원본 스케일에서)
        y_pred = predict_func(x_valid)
        ss_res = np.sum((y_valid - y_pred) ** 2)
        ss_tot = np.sum((y_valid - np.mean(y_valid)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        return CurveFitResult(
            fit_type=FitType.EXPONENTIAL,
            coefficients=coefficients,
            r_squared=r_squared,
            std_error=std_err,
            predict_func=predict_func,
        )

    def _fit_power(self, x: np.ndarray, y: np.ndarray) -> CurveFitResult:
        """거듭제곱 회귀 (y = a * x^b)"""
        # 로그 변환으로 선형화
        # ln(y) = ln(a) + b*ln(x)

        mask = (x > 0) & (y > 0)
        if np.sum(mask) < 2:
            return CurveFitResult(
                fit_type=FitType.POWER,
                coefficients=np.array([1.0, 1.0]),
                r_squared=0.0,
                std_error=0.0,
            )

        x_valid = x[mask]
        y_valid = y[mask]
        log_x = np.log(x_valid)
        log_y = np.log(y_valid)

        slope, intercept, r_value, p_value, std_err = stats.linregress(log_x, log_y)

        a = np.exp(intercept)
        b = slope
        coefficients = np.array([a, b])

        def predict_func(x_new):
            return a * np.power(x_new, b)

        # R² 계산
        y_pred = predict_func(x_valid)
        ss_res = np.sum((y_valid - y_pred) ** 2)
        ss_tot = np.sum((y_valid - np.mean(y_valid)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        return CurveFitResult(
            fit_type=FitType.POWER,
            coefficients=coefficients,
            r_squared=r_squared,
            std_error=std_err,
            predict_func=predict_func,
        )

    def _fit_logarithmic(self, x: np.ndarray, y: np.ndarray) -> CurveFitResult:
        """로그 회귀 (y = a * ln(x) + b)"""
        mask = x > 0
        if np.sum(mask) < 2:
            return CurveFitResult(
                fit_type=FitType.LOGARITHMIC,
                coefficients=np.array([1.0, 0.0]),
                r_squared=0.0,
                std_error=0.0,
            )

        x_valid = x[mask]
        y_valid = y[mask]
        log_x = np.log(x_valid)

        slope, intercept, r_value, p_value, std_err = stats.linregress(log_x, y_valid)

        coefficients = np.array([slope, intercept])
        r_squared = r_value**2

        def predict_func(x_new):
            return slope * np.log(x_new) + intercept

        residuals = y_valid - predict_func(x_valid)

        return CurveFitResult(
            fit_type=FitType.LOGARITHMIC,
            coefficients=coefficients,
            r_squared=r_squared,
            std_error=std_err,
            residuals=residuals,
            predict_func=predict_func,
        )

    def _fit_logistic(self, x: np.ndarray, y: np.ndarray) -> CurveFitResult:
        """로지스틱 회귀 (y = L / (1 + e^(-k(x-x0))))"""

        def logistic(x, L, k, x0):
            return L / (1 + np.exp(-k * (x - x0)))

        # 초기 추정값
        L0 = np.max(y)
        k0 = 1.0
        x0_init = np.median(x)

        try:
            popt, pcov = optimize.curve_fit(
                logistic, x, y, p0=[L0, k0, x0_init], maxfev=5000
            )

            L, k, x0 = popt
            coefficients = np.array([L, k, x0])

            def predict_func(x_new):
                return logistic(x_new, L, k, x0)

            y_pred = predict_func(x)
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            std_error = np.sqrt(np.diag(pcov)).mean() if pcov is not None else 0

            return CurveFitResult(
                fit_type=FitType.LOGISTIC,
                coefficients=coefficients,
                r_squared=r_squared,
                std_error=std_error,
                predict_func=predict_func,
            )

        except Exception:
            return CurveFitResult(
                fit_type=FitType.LOGISTIC,
                coefficients=np.array([1.0, 1.0, 0.0]),
                r_squared=0.0,
                std_error=0.0,
            )

    def _fit_gaussian(self, x: np.ndarray, y: np.ndarray) -> CurveFitResult:
        """가우시안 피팅 (y = a * exp(-((x-mu)^2)/(2*sigma^2)))"""

        def gaussian(x, a, mu, sigma):
            return a * np.exp(-((x - mu) ** 2) / (2 * sigma**2))

        # 초기 추정값
        a0 = np.max(y)
        mu0 = x[np.argmax(y)]
        sigma0 = np.std(x)

        try:
            popt, pcov = optimize.curve_fit(
                gaussian, x, y, p0=[a0, mu0, sigma0], maxfev=5000
            )

            a, mu, sigma = popt
            coefficients = np.array([a, mu, sigma])

            def predict_func(x_new):
                return gaussian(x_new, a, mu, sigma)

            y_pred = predict_func(x)
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            std_error = np.sqrt(np.diag(pcov)).mean() if pcov is not None else 0

            return CurveFitResult(
                fit_type=FitType.GAUSSIAN,
                coefficients=coefficients,
                r_squared=r_squared,
                std_error=std_error,
                predict_func=predict_func,
            )

        except Exception:
            return CurveFitResult(
                fit_type=FitType.GAUSSIAN,
                coefficients=np.array([1.0, 0.0, 1.0]),
                r_squared=0.0,
                std_error=0.0,
            )

    def predict(self, result: CurveFitResult, x_new: np.ndarray) -> np.ndarray:
        """
        피팅 결과로 예측

        Args:
            result: 피팅 결과
            x_new: 예측할 X 값

        Returns:
            예측된 Y 값
        """
        if result.predict_func is None:
            # 예측 함수가 없으면 계수로 직접 계산
            if result.fit_type == FitType.LINEAR:
                return result.coefficients[0] * x_new + result.coefficients[1]
            elif result.fit_type == FitType.POLYNOMIAL:
                poly = np.poly1d(result.coefficients)
                return poly(x_new)

            return np.zeros_like(x_new)

        return result.predict_func(x_new)

    def forecast(
        self, result: CurveFitResult, x: np.ndarray, settings: ForecastSettings
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        미래/과거 예측

        Args:
            result: 피팅 결과
            x: 원본 X 데이터
            settings: 예측 설정

        Returns:
            (예측 X, 예측 Y) 튜플
        """
        forecast_x = []

        # 미래 예측
        if settings.forward_periods > 0:
            x_max = np.max(x)
            for i in range(1, settings.forward_periods + 1):
                forecast_x.append(x_max + i * settings.period_size)

        # 과거 예측
        if settings.backward_periods > 0:
            x_min = np.min(x)
            for i in range(1, settings.backward_periods + 1):
                forecast_x.insert(0, x_min - i * settings.period_size)

        if not forecast_x:
            return np.array([]), np.array([])

        forecast_x = np.array(forecast_x)
        forecast_y = self.predict(result, forecast_x)

        return forecast_x, forecast_y

    def moving_average(self, y: np.ndarray, window: int = 3) -> np.ndarray:
        """
        이동 평균 계산

        Args:
            y: Y 데이터
            window: 윈도우 크기

        Returns:
            이동 평균 배열
        """
        if len(y) < window:
            return y.copy()

        result = np.full_like(y, np.nan, dtype=float)

        for i in range(len(y)):
            start = max(0, i - window // 2)
            end = min(len(y), i + window // 2 + 1)
            result[i] = np.nanmean(y[start:end])

        return result

    def exponential_moving_average(
        self, y: np.ndarray, alpha: float = 0.3
    ) -> np.ndarray:
        """
        지수 이동 평균 (EMA)

        Args:
            y: Y 데이터
            alpha: 평활 계수 (0 < alpha <= 1)

        Returns:
            EMA 배열
        """
        result = np.zeros_like(y, dtype=float)
        result[0] = y[0]

        for i in range(1, len(y)):
            result[i] = alpha * y[i] + (1 - alpha) * result[i - 1]

        return result

    def confidence_interval(
        self, result: CurveFitResult, x: np.ndarray, confidence: float = 0.95
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        신뢰 구간 계산

        Args:
            result: 피팅 결과
            x: X 데이터
            confidence: 신뢰 수준

        Returns:
            (하한, 상한) 튜플
        """
        y_pred = self.predict(result, x)
        n = len(x)

        # t-분포 임계값
        alpha = 1 - confidence
        t_crit = stats.t.ppf(1 - alpha / 2, n - 2)

        # 예측 오차
        se = result.std_error

        # 신뢰 구간
        margin = t_crit * se

        lower = y_pred - margin
        upper = y_pred + margin

        return lower, upper

    def prediction_interval(
        self, result: CurveFitResult, x: np.ndarray, confidence: float = 0.95
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        예측 구간 계산 (개별 관측치의 범위)

        Args:
            result: 피팅 결과
            x: X 데이터
            confidence: 신뢰 수준

        Returns:
            (하한, 상한) 튜플
        """
        y_pred = self.predict(result, x)
        n = len(x)

        alpha = 1 - confidence
        t_crit = stats.t.ppf(1 - alpha / 2, n - 2)

        se = result.std_error

        # 예측 구간은 신뢰 구간보다 넓음
        margin = t_crit * se * np.sqrt(1 + 1 / n)

        lower = y_pred - margin
        upper = y_pred + margin

        return lower, upper


@dataclass
class TrendLine:
    """
    추세선

    시각화에 표시할 추세선을 정의합니다.
    """

    name: str
    fit_type: FitType
    color: str = "#FF0000"
    width: float = 2.0
    style: str = "solid"
    visible: bool = True
    show_equation: bool = True
    show_r_squared: bool = True
    show_confidence_band: bool = False
    confidence_level: float = 0.95

    # 계산된 결과
    result: Optional[CurveFitResult] = None
    _fitter: CurveFitter = field(default_factory=CurveFitter)
    _x_data: Optional[np.ndarray] = None
    _y_data: Optional[np.ndarray] = None

    def calculate(
        self, x: np.ndarray, y: np.ndarray, settings: Optional[CurveFitSettings] = None
    ) -> Optional[CurveFitResult]:
        """
        추세선 계산

        Args:
            x: X 데이터
            y: Y 데이터
            settings: 피팅 설정

        Returns:
            피팅 결과
        """
        self._x_data = x
        self._y_data = y

        if settings is None:
            settings = CurveFitSettings(fit_type=self.fit_type)

        self.result = self._fitter.fit(x, y, self.fit_type, settings)
        return self.result

    def get_line_points(
        self,
        num_points: int = 100,
        x_min: Optional[float] = None,
        x_max: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        추세선 렌더링용 포인트 생성

        Args:
            num_points: 포인트 수
            x_min: X 최소값
            x_max: X 최대값

        Returns:
            (X 배열, Y 배열) 튜플
        """
        if self.result is None or self._x_data is None:
            return np.array([]), np.array([])

        if x_min is None:
            x_min = np.min(self._x_data)
        if x_max is None:
            x_max = np.max(self._x_data)

        x_line = np.linspace(x_min, x_max, num_points)
        y_line = self._fitter.predict(self.result, x_line)

        return x_line, y_line

    def get_confidence_band(
        self, num_points: int = 100
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        신뢰 구간 밴드 생성

        Returns:
            (X 배열, 하한 Y, 상한 Y) 튜플
        """
        if self.result is None or self._x_data is None:
            return np.array([]), np.array([]), np.array([])

        x_line = np.linspace(np.min(self._x_data), np.max(self._x_data), num_points)
        lower, upper = self._fitter.confidence_interval(
            self.result, x_line, self.confidence_level
        )

        return x_line, lower, upper

    def get_label_text(self) -> str:
        """레이블 텍스트 생성"""
        if self.result is None:
            return self.name

        parts = [self.name]

        if self.show_equation:
            parts.append(self.result.get_equation_string())

        if self.show_r_squared:
            parts.append(f"R² = {self.result.r_squared:.4f}")

        return "\n".join(parts)


class TrendLineManager:
    """
    추세선 관리자

    여러 추세선을 관리합니다.
    """

    def __init__(self):
        self._trend_lines: Dict[str, TrendLine] = {}

    def add_trend_line(self, name: str, fit_type: FitType, **kwargs) -> TrendLine:
        """추세선 추가"""
        trend = TrendLine(name=name, fit_type=fit_type, **kwargs)
        self._trend_lines[name] = trend
        return trend

    def remove_trend_line(self, name: str) -> None:
        """추세선 제거"""
        if name in self._trend_lines:
            del self._trend_lines[name]

    def get_trend_line(self, name: str) -> Optional[TrendLine]:
        """추세선 조회"""
        return self._trend_lines.get(name)

    def get_all_trend_lines(self) -> List[TrendLine]:
        """모든 추세선 반환"""
        return list(self._trend_lines.values())

    def calculate_all(self, x: np.ndarray, y: np.ndarray) -> None:
        """모든 추세선 계산"""
        for trend in self._trend_lines.values():
            if trend.visible:
                trend.calculate(x, y)

    def clear(self) -> None:
        """모든 추세선 클리어"""
        self._trend_lines.clear()
