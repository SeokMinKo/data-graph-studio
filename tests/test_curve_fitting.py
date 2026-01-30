"""
Curve Fitting 테스트 - Spotfire 스타일 Lines & Curves
"""

import pytest
import numpy as np
from typing import List, Tuple

from data_graph_studio.graph.curve_fitting import (
    FitType,
    CurveFitSettings,
    CurveFitResult,
    CurveFitter,
    TrendLine,
    ForecastSettings,
)


class TestCurveFitter:
    """CurveFitter 클래스 테스트"""

    @pytest.fixture
    def fitter(self):
        """CurveFitter 인스턴스"""
        return CurveFitter()

    @pytest.fixture
    def linear_data(self):
        """선형 데이터 (y = 2x + 1)"""
        x = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        y = 2 * x + 1 + np.random.normal(0, 0.1, len(x))  # 약간의 노이즈
        return x, y

    @pytest.fixture
    def quadratic_data(self):
        """2차 다항식 데이터 (y = x^2 + 2x + 1)"""
        x = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        y = x**2 + 2*x + 1 + np.random.normal(0, 0.5, len(x))
        return x, y

    @pytest.fixture
    def exponential_data(self):
        """지수 데이터 (y = 2 * e^(0.3x))"""
        x = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        y = 2 * np.exp(0.3 * x) + np.random.normal(0, 0.5, len(x))
        return x, y

    def test_linear_fit(self, fitter, linear_data):
        """선형 회귀"""
        x, y = linear_data

        result = fitter.fit(x, y, FitType.LINEAR)

        assert result is not None
        assert result.fit_type == FitType.LINEAR
        assert result.r_squared > 0.95  # 높은 R² (노이즈가 작으므로)
        assert len(result.coefficients) == 2  # slope, intercept

        # 기울기 약 2, 절편 약 1
        assert 1.8 < result.coefficients[0] < 2.2
        assert 0.5 < result.coefficients[1] < 1.5

    def test_polynomial_fit(self, fitter, quadratic_data):
        """다항식 회귀"""
        x, y = quadratic_data

        settings = CurveFitSettings(fit_type=FitType.POLYNOMIAL, degree=2)
        result = fitter.fit(x, y, FitType.POLYNOMIAL, settings)

        assert result is not None
        assert result.fit_type == FitType.POLYNOMIAL
        assert result.r_squared > 0.95
        assert len(result.coefficients) == 3  # a, b, c for ax^2 + bx + c

    def test_exponential_fit(self, fitter, exponential_data):
        """지수 회귀"""
        x, y = exponential_data

        result = fitter.fit(x, y, FitType.EXPONENTIAL)

        assert result is not None
        assert result.fit_type == FitType.EXPONENTIAL
        # 지수 데이터이므로 R²가 높아야 함
        assert result.r_squared > 0.9

    def test_power_fit(self, fitter):
        """거듭제곱 회귀 (y = a * x^b)"""
        x = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        y = 3 * x**2 + np.random.normal(0, 0.5, len(x))

        result = fitter.fit(x, y, FitType.POWER)

        assert result is not None
        assert result.fit_type == FitType.POWER

    def test_logarithmic_fit(self, fitter):
        """로그 회귀 (y = a * ln(x) + b)"""
        x = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        y = 5 * np.log(x) + 2 + np.random.normal(0, 0.1, len(x))

        result = fitter.fit(x, y, FitType.LOGARITHMIC)

        assert result is not None
        assert result.fit_type == FitType.LOGARITHMIC
        assert result.r_squared > 0.95

    def test_moving_average(self, fitter, linear_data):
        """이동 평균"""
        x, y = linear_data

        result = fitter.moving_average(y, window=3)

        assert result is not None
        assert len(result) == len(y)
        # 처음과 끝은 NaN이 있을 수 있음

    def test_predict(self, fitter, linear_data):
        """예측"""
        x, y = linear_data

        result = fitter.fit(x, y, FitType.LINEAR)

        # x=11에서 예측
        predicted = fitter.predict(result, np.array([11]))

        # 약 2*11 + 1 = 23
        assert 21 < predicted[0] < 25

    def test_confidence_interval(self, fitter, linear_data):
        """신뢰 구간"""
        x, y = linear_data

        result = fitter.fit(x, y, FitType.LINEAR)

        lower, upper = fitter.confidence_interval(result, x, confidence=0.95)

        assert len(lower) == len(x)
        assert len(upper) == len(x)
        assert all(lower <= upper)

    def test_get_equation_string(self, fitter, linear_data):
        """수식 문자열"""
        x, y = linear_data

        result = fitter.fit(x, y, FitType.LINEAR)

        equation = result.get_equation_string()

        assert "x" in equation
        assert "+" in equation or "-" in equation

    def test_fit_with_empty_data(self, fitter):
        """빈 데이터"""
        x = np.array([])
        y = np.array([])

        result = fitter.fit(x, y, FitType.LINEAR)

        assert result is None

    def test_fit_with_insufficient_data(self, fitter):
        """데이터 부족"""
        x = np.array([1])
        y = np.array([2])

        result = fitter.fit(x, y, FitType.LINEAR)

        # 최소 2개 필요
        assert result is None


class TestTrendLine:
    """TrendLine 클래스 테스트"""

    def test_init(self):
        """초기화"""
        trend = TrendLine(
            name="Linear Trend",
            fit_type=FitType.LINEAR,
            color="#FF0000"
        )

        assert trend.name == "Linear Trend"
        assert trend.fit_type == FitType.LINEAR
        assert trend.color == "#FF0000"
        assert trend.visible is True

    def test_calculate(self):
        """추세선 계산"""
        trend = TrendLine(
            name="Linear",
            fit_type=FitType.LINEAR
        )

        x = np.array([1, 2, 3, 4, 5], dtype=float)
        y = np.array([2, 4, 6, 8, 10], dtype=float)

        result = trend.calculate(x, y)

        assert result is not None
        assert trend.result is not None
        assert trend.result.r_squared > 0.99

    def test_get_line_points(self):
        """추세선 포인트 생성"""
        trend = TrendLine(
            name="Linear",
            fit_type=FitType.LINEAR
        )

        x = np.array([1, 2, 3, 4, 5], dtype=float)
        y = np.array([2, 4, 6, 8, 10], dtype=float)

        trend.calculate(x, y)

        line_x, line_y = trend.get_line_points(num_points=100)

        assert len(line_x) == 100
        assert len(line_y) == 100
        assert line_x[0] >= 1
        assert line_x[-1] <= 5


class TestForecast:
    """예측 기능 테스트"""

    @pytest.fixture
    def fitter(self):
        return CurveFitter()

    def test_forecast_forward(self, fitter):
        """미래 예측"""
        x = np.array([1, 2, 3, 4, 5], dtype=float)
        y = np.array([10, 20, 30, 40, 50], dtype=float)

        result = fitter.fit(x, y, FitType.LINEAR)

        forecast_settings = ForecastSettings(
            forward_periods=3,
            backward_periods=0
        )

        forecast_x, forecast_y = fitter.forecast(result, x, forecast_settings)

        assert len(forecast_x) == 3
        assert forecast_x[0] > 5  # x의 마지막 값보다 큼

    def test_forecast_backward(self, fitter):
        """과거 예측 (백캐스팅)"""
        x = np.array([5, 6, 7, 8, 9], dtype=float)
        y = np.array([10, 12, 14, 16, 18], dtype=float)

        result = fitter.fit(x, y, FitType.LINEAR)

        forecast_settings = ForecastSettings(
            forward_periods=0,
            backward_periods=2
        )

        forecast_x, forecast_y = fitter.forecast(result, x, forecast_settings)

        assert len(forecast_x) == 2
        assert all(fx < 5 for fx in forecast_x)  # x의 첫 값보다 작음


class TestCurveFitSettings:
    """CurveFitSettings 테스트"""

    def test_default_settings(self):
        """기본 설정"""
        settings = CurveFitSettings()

        assert settings.fit_type == FitType.LINEAR
        assert settings.degree == 2
        assert settings.show_equation is True
        assert settings.show_r_squared is True

    def test_custom_settings(self):
        """커스텀 설정"""
        settings = CurveFitSettings(
            fit_type=FitType.POLYNOMIAL,
            degree=3,
            show_equation=False,
            confidence_level=0.99
        )

        assert settings.fit_type == FitType.POLYNOMIAL
        assert settings.degree == 3
        assert settings.show_equation is False
        assert settings.confidence_level == 0.99
