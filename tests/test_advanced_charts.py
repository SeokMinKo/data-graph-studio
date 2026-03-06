"""
Tests for Advanced Charts (Box Plot, Violin, Heatmap, Candlestick, Waterfall)
"""

import pytest
import numpy as np
import polars as pl
from datetime import date

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_graph_studio.graph.charts.box_plot import BoxPlotChart
from data_graph_studio.graph.charts.violin_plot import ViolinPlotChart
from data_graph_studio.graph.charts.heatmap import HeatmapChart
from data_graph_studio.graph.charts.candlestick import CandlestickChart
from data_graph_studio.graph.charts.waterfall import WaterfallChart


class TestBoxPlotChart:
    """Box Plot 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "Category": ["A"] * 100 + ["B"] * 100 + ["C"] * 100,
                "Value": list(np.random.normal(10, 2, 100))
                + list(np.random.normal(15, 3, 100))
                + list(np.random.normal(12, 1.5, 100)),
            }
        )

    @pytest.fixture
    def chart(self):
        return BoxPlotChart()

    def test_calculate_stats(self, chart, sample_data):
        """Box plot 통계 계산"""
        stats = chart.calculate_stats(sample_data, "Category", "Value")

        assert "A" in stats
        assert "B" in stats
        assert "C" in stats

        # 각 카테고리 통계 확인
        for cat in ["A", "B", "C"]:
            assert "median" in stats[cat]
            assert "q1" in stats[cat]
            assert "q3" in stats[cat]
            assert "whisker_low" in stats[cat]
            assert "whisker_high" in stats[cat]
            assert "outliers" in stats[cat]

    def test_median_calculation(self, chart, sample_data):
        """중앙값 계산 확인"""
        stats = chart.calculate_stats(sample_data, "Category", "Value")

        # A 그룹의 중앙값은 대략 10 근처
        assert 8 < stats["A"]["median"] < 12
        # B 그룹의 중앙값은 대략 15 근처
        assert 12 < stats["B"]["median"] < 18

    def test_quartile_order(self, chart, sample_data):
        """사분위수 순서: Q1 < median < Q3"""
        stats = chart.calculate_stats(sample_data, "Category", "Value")

        for cat in ["A", "B", "C"]:
            assert stats[cat]["q1"] <= stats[cat]["median"]
            assert stats[cat]["median"] <= stats[cat]["q3"]

    def test_whisker_range(self, chart, sample_data):
        """Whisker 범위: 1.5 * IQR 이내"""
        stats = chart.calculate_stats(sample_data, "Category", "Value")

        for cat in ["A", "B", "C"]:
            iqr = stats[cat]["q3"] - stats[cat]["q1"]
            assert stats[cat]["whisker_low"] >= stats[cat]["q1"] - 1.5 * iqr
            assert stats[cat]["whisker_high"] <= stats[cat]["q3"] + 1.5 * iqr

    def test_outlier_detection(self, chart):
        """이상치 탐지"""
        # 명확한 이상치가 있는 데이터
        data = pl.DataFrame(
            {
                "Category": ["A"] * 10,
                "Value": [
                    10,
                    11,
                    10,
                    11,
                    10,
                    11,
                    10,
                    11,
                    100,
                    -50,
                ],  # 100, -50 are outliers
            }
        )

        stats = chart.calculate_stats(data, "Category", "Value")
        assert len(stats["A"]["outliers"]) >= 2


class TestViolinPlotChart:
    """Violin Plot 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "Category": ["A"] * 100 + ["B"] * 100,
                "Value": list(np.random.normal(10, 2, 100))
                + list(
                    np.concatenate(
                        [np.random.normal(8, 1, 50), np.random.normal(14, 1, 50)]
                    )
                ),  # Bimodal
            }
        )

    @pytest.fixture
    def chart(self):
        return ViolinPlotChart()

    def test_calculate_density(self, chart, sample_data):
        """KDE 밀도 계산"""
        density = chart.calculate_density(sample_data, "Category", "Value")

        assert "A" in density
        assert "B" in density

        for cat in ["A", "B"]:
            assert "x" in density[cat]
            assert "y" in density[cat]
            assert len(density[cat]["x"]) == len(density[cat]["y"])

    def test_density_normalized(self, chart, sample_data):
        """밀도가 정규화됨"""
        density = chart.calculate_density(sample_data, "Category", "Value")

        for cat in ["A", "B"]:
            # 최대값이 1 이하
            max_density = max(density[cat]["y"])
            assert max_density <= 1.0

    def test_bimodal_detection(self, chart, sample_data):
        """Bimodal 분포 감지"""
        density = chart.calculate_density(sample_data, "Category", "Value")

        # B 카테고리는 bimodal이므로 두 개의 피크가 있어야 함
        y_values = density["B"]["y"]
        peaks = 0
        for i in range(1, len(y_values) - 1):
            if y_values[i] > y_values[i - 1] and y_values[i] > y_values[i + 1]:
                peaks += 1

        # At least 2 peaks for bimodal (might have noise peaks)
        assert peaks >= 2

    def test_include_box_stats(self, chart, sample_data):
        """Box plot 통계 포함"""
        density = chart.calculate_density(
            sample_data, "Category", "Value", include_box=True
        )

        for cat in ["A", "B"]:
            assert "median" in density[cat]
            assert "q1" in density[cat]
            assert "q3" in density[cat]


class TestHeatmapChart:
    """Heatmap 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "Day": ["Mon", "Tue", "Wed", "Thu", "Fri"] * 4,
                "Hour": ["9AM"] * 5 + ["12PM"] * 5 + ["3PM"] * 5 + ["6PM"] * 5,
                "Value": [
                    10,
                    20,
                    30,
                    25,
                    15,
                    40,
                    50,
                    60,
                    55,
                    45,
                    30,
                    35,
                    40,
                    38,
                    32,
                    15,
                    20,
                    25,
                    22,
                    18,
                ],
            }
        )

    @pytest.fixture
    def chart(self):
        return HeatmapChart()

    def test_create_matrix(self, chart, sample_data):
        """히트맵 매트릭스 생성"""
        matrix, row_labels, col_labels = chart.create_matrix(
            sample_data, "Day", "Hour", "Value"
        )

        assert matrix.shape == (5, 4)  # 5 days x 4 hours
        assert len(row_labels) == 5
        assert len(col_labels) == 4

    def test_value_range(self, chart, sample_data):
        """값 범위 확인"""
        matrix, _, _ = chart.create_matrix(sample_data, "Day", "Hour", "Value")

        assert matrix.min() == 10
        assert matrix.max() == 60

    def test_missing_values_handled(self, chart):
        """결측치 처리"""
        data = pl.DataFrame(
            {"X": ["A", "A", "B"], "Y": ["1", "2", "1"], "Z": [10, 20, 30]}
        )

        matrix, _, _ = chart.create_matrix(data, "X", "Y", "Z")
        # B-2 조합이 없으므로 NaN 또는 0
        assert matrix.shape == (2, 2)

    def test_color_scale(self, chart, sample_data):
        """컬러 스케일 생성"""
        matrix, _, _ = chart.create_matrix(sample_data, "Day", "Hour", "Value")
        colors = chart.get_color_scale(matrix, "viridis")

        assert colors.shape == matrix.shape + (4,)  # RGBA

    def test_aggregation(self, chart):
        """집계 함수 적용"""
        data = pl.DataFrame(
            {"X": ["A", "A", "A"], "Y": ["1", "1", "1"], "Z": [10, 20, 30]}
        )

        matrix_sum, _, _ = chart.create_matrix(data, "X", "Y", "Z", agg="sum")
        matrix_mean, _, _ = chart.create_matrix(data, "X", "Y", "Z", agg="mean")

        assert matrix_sum[0, 0] == 60
        assert matrix_mean[0, 0] == 20


class TestCandlestickChart:
    """Candlestick (OHLC) 차트 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "Date": [date(2024, 1, i) for i in range(1, 6)],
                "Open": [100, 105, 103, 108, 106],
                "High": [110, 112, 108, 115, 112],
                "Low": [98, 102, 100, 105, 103],
                "Close": [105, 103, 107, 106, 110],
                "Volume": [1000, 1200, 900, 1500, 1100],
            }
        )

    @pytest.fixture
    def chart(self):
        return CandlestickChart()

    def test_calculate_candles(self, chart, sample_data):
        """캔들 데이터 계산"""
        candles = chart.calculate_candles(
            sample_data, "Date", "Open", "High", "Low", "Close"
        )

        assert len(candles) == 5
        for candle in candles:
            assert "date" in candle
            assert "open" in candle
            assert "high" in candle
            assert "low" in candle
            assert "close" in candle
            assert "bullish" in candle

    def test_bullish_bearish_detection(self, chart, sample_data):
        """상승/하락 캔들 판별"""
        candles = chart.calculate_candles(
            sample_data, "Date", "Open", "High", "Low", "Close"
        )

        # Day 1: Open=100, Close=105 -> Bullish
        assert candles[0]["bullish"] is True

        # Day 2: Open=105, Close=103 -> Bearish
        assert candles[1]["bullish"] is False

    def test_high_low_range(self, chart, sample_data):
        """High >= max(Open, Close), Low <= min(Open, Close)"""
        candles = chart.calculate_candles(
            sample_data, "Date", "Open", "High", "Low", "Close"
        )

        for candle in candles:
            body_max = max(candle["open"], candle["close"])
            body_min = min(candle["open"], candle["close"])
            assert candle["high"] >= body_max
            assert candle["low"] <= body_min

    def test_with_volume(self, chart, sample_data):
        """거래량 포함"""
        candles = chart.calculate_candles(
            sample_data, "Date", "Open", "High", "Low", "Close", volume_col="Volume"
        )

        for candle in candles:
            assert "volume" in candle

        assert candles[0]["volume"] == 1000


class TestWaterfallChart:
    """Waterfall 차트 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "Category": ["Start", "Revenue", "COGS", "Expenses", "Tax", "End"],
                "Value": [0, 1000, -400, -300, -50, 0],
                "Type": [
                    "start",
                    "increase",
                    "decrease",
                    "decrease",
                    "decrease",
                    "total",
                ],
            }
        )

    @pytest.fixture
    def chart(self):
        return WaterfallChart()

    def test_calculate_waterfall(self, chart, sample_data):
        """Waterfall 데이터 계산"""
        result = chart.calculate_waterfall(sample_data, "Category", "Value", "Type")

        assert len(result) == 6
        for item in result:
            assert "category" in item
            assert "value" in item
            assert "start" in item
            assert "end" in item
            assert "type" in item

    def test_running_total(self, chart, sample_data):
        """누적 합계 계산"""
        result = chart.calculate_waterfall(sample_data, "Category", "Value", "Type")

        # Start: 0
        # Revenue: 0 + 1000 = 1000
        # COGS: 1000 - 400 = 600
        # Expenses: 600 - 300 = 300
        # Tax: 300 - 50 = 250
        # End (total): 250

        assert result[0]["end"] == 0  # Start
        assert result[1]["end"] == 1000  # After Revenue
        assert result[2]["end"] == 600  # After COGS
        assert result[3]["end"] == 300  # After Expenses
        assert result[4]["end"] == 250  # After Tax

    def test_start_end_positions(self, chart, sample_data):
        """시작/끝 위치 계산"""
        result = chart.calculate_waterfall(sample_data, "Category", "Value", "Type")

        # Increase: start < end
        assert result[1]["start"] < result[1]["end"]

        # Decrease: start > end
        assert result[2]["start"] > result[2]["end"]

    def test_bar_colors(self, chart, sample_data):
        """막대 색상"""
        result = chart.calculate_waterfall(sample_data, "Category", "Value", "Type")

        # Type에 따른 색상
        assert result[0]["color"] == "gray"  # start
        assert result[1]["color"] == "green"  # increase
        assert result[2]["color"] == "red"  # decrease
        assert result[5]["color"] == "blue"  # total

    def test_auto_type_detection(self, chart):
        """Type 자동 감지"""
        data = pl.DataFrame(
            {
                "Category": ["A", "B", "C", "D"],
                "Value": [100, 50, -30, 0],  # No explicit type
            }
        )

        result = chart.calculate_waterfall(data, "Category", "Value", type_col=None)

        # 양수는 increase, 음수는 decrease
        assert result[0]["type"] == "start"
        assert result[1]["type"] == "increase"
        assert result[2]["type"] == "decrease"


class TestChartRegistry:
    """차트 레지스트리 테스트"""

    def test_get_chart_by_type(self):
        """타입으로 차트 조회"""
        from data_graph_studio.graph.charts import get_chart

        box = get_chart("box")
        violin = get_chart("violin")
        heatmap = get_chart("heatmap")
        candlestick = get_chart("candlestick")
        waterfall = get_chart("waterfall")

        assert isinstance(box, BoxPlotChart)
        assert isinstance(violin, ViolinPlotChart)
        assert isinstance(heatmap, HeatmapChart)
        assert isinstance(candlestick, CandlestickChart)
        assert isinstance(waterfall, WaterfallChart)

    def test_unknown_chart_type(self):
        """알 수 없는 차트 타입"""
        from data_graph_studio.graph.charts import get_chart

        result = get_chart("unknown")
        assert result is None
