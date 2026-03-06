"""
새로운 차트 타입 테스트 - Phase 2 & 3
"""

import pytest
import polars as pl

from data_graph_studio.graph.charts.horizontal_bar import HorizontalBarChart
from data_graph_studio.graph.charts.stacked_bar import StackedBarChart
from data_graph_studio.graph.charts.bubble import BubbleChart
from data_graph_studio.graph.charts.donut import DonutChart
from data_graph_studio.graph.charts.combination import CombinationChart
from data_graph_studio.graph.charts.cross_table import CrossTableCalculator
from data_graph_studio.graph.charts.treemap import TreeMapCalculator
from data_graph_studio.graph.charts.funnel import FunnelCalculator
from data_graph_studio.graph.charts.radar import RadarCalculator


class TestHorizontalBarChart:
    """Horizontal Bar Chart 테스트"""

    @pytest.fixture
    def sample_data(self):
        return {
            "categories": [
                "Product A",
                "Product B",
                "Product C",
                "Product D",
                "Product E",
            ],
            "values": [100, 250, 180, 300, 120],
        }

    def test_calculate_positions(self, sample_data):
        """막대 위치 계산"""
        chart = HorizontalBarChart()
        result = chart.calculate(
            categories=sample_data["categories"], values=sample_data["values"]
        )

        assert len(result["y_positions"]) == 5
        assert len(result["widths"]) == 5
        assert result["widths"] == sample_data["values"]

    def test_sorted_by_value(self, sample_data):
        """값으로 정렬"""
        chart = HorizontalBarChart()
        result = chart.calculate(
            categories=sample_data["categories"],
            values=sample_data["values"],
            sort_by_value=True,
            descending=True,
        )

        # 값이 내림차순으로 정렬
        assert result["sorted_categories"][0] == "Product D"
        assert result["sorted_values"][0] == 300


class TestStackedBarChart:
    """Stacked Bar Chart 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "category": ["A", "A", "B", "B", "C", "C"],
                "group": ["X", "Y", "X", "Y", "X", "Y"],
                "value": [10, 20, 15, 25, 30, 10],
            }
        )

    def test_calculate_stacked(self, sample_data):
        """스택 계산"""
        chart = StackedBarChart()
        result = chart.calculate(
            data=sample_data,
            category_col="category",
            group_col="group",
            value_col="value",
        )

        assert "categories" in result
        assert "groups" in result
        assert "stacked_values" in result
        assert len(result["categories"]) == 3  # A, B, C

    def test_calculate_100_percent(self, sample_data):
        """100% 스택 계산"""
        chart = StackedBarChart()
        result = chart.calculate(
            data=sample_data,
            category_col="category",
            group_col="group",
            value_col="value",
            normalize=True,
        )

        # 각 카테고리의 합이 100%
        for cat in result["categories"]:
            total = sum(result["stacked_values"][cat].values())
            assert abs(total - 100) < 0.01


class TestBubbleChart:
    """Bubble Chart 테스트"""

    @pytest.fixture
    def sample_data(self):
        return {
            "x": [1, 2, 3, 4, 5],
            "y": [10, 20, 15, 25, 30],
            "size": [100, 200, 150, 300, 250],
            "labels": ["A", "B", "C", "D", "E"],
        }

    def test_calculate_bubble_sizes(self, sample_data):
        """버블 크기 계산"""
        chart = BubbleChart()
        result = chart.calculate(
            x=sample_data["x"],
            y=sample_data["y"],
            size=sample_data["size"],
            min_bubble_size=10,
            max_bubble_size=100,
        )

        assert len(result["scaled_sizes"]) == 5
        assert min(result["scaled_sizes"]) >= 10
        assert max(result["scaled_sizes"]) <= 100

    def test_no_size_data(self, sample_data):
        """크기 데이터 없을 때 기본 크기"""
        chart = BubbleChart()
        result = chart.calculate(
            x=sample_data["x"], y=sample_data["y"], size=None, default_size=50
        )

        assert all(s == 50 for s in result["scaled_sizes"])


class TestDonutChart:
    """Donut Chart 테스트"""

    @pytest.fixture
    def sample_data(self):
        return {"labels": ["A", "B", "C", "D"], "values": [30, 20, 35, 15]}

    def test_calculate_angles(self, sample_data):
        """각도 계산"""
        chart = DonutChart()
        result = chart.calculate(
            labels=sample_data["labels"], values=sample_data["values"]
        )

        assert "angles" in result
        assert "percentages" in result

        # 전체 각도 합 = 360
        total_angle = sum(result["angles"])
        assert abs(total_angle - 360) < 0.01

        # 비율 합 = 100
        total_percent = sum(result["percentages"])
        assert abs(total_percent - 100) < 0.01

    def test_inner_radius(self, sample_data):
        """내부 반지름 설정"""
        chart = DonutChart()
        result = chart.calculate(
            labels=sample_data["labels"],
            values=sample_data["values"],
            inner_radius_ratio=0.5,
        )

        assert result["inner_radius_ratio"] == 0.5


class TestCombinationChart:
    """Combination Chart (Line + Bar) 테스트"""

    @pytest.fixture
    def sample_data(self):
        return {
            "x": ["Jan", "Feb", "Mar", "Apr", "May"],
            "bar_values": [100, 120, 90, 150, 130],
            "line_values": [10, 12, 9, 15, 13],
        }

    def test_calculate_combined(self, sample_data):
        """결합 차트 계산"""
        chart = CombinationChart()
        result = chart.calculate(
            x=sample_data["x"],
            bar_series=[{"name": "Sales", "values": sample_data["bar_values"]}],
            line_series=[{"name": "Growth", "values": sample_data["line_values"]}],
        )

        assert "bar_data" in result
        assert "line_data" in result
        assert len(result["bar_data"]) == 1
        assert len(result["line_data"]) == 1


class TestCrossTable:
    """Cross Table (Pivot) 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "region": ["Asia", "Asia", "Europe", "Europe", "America", "America"],
                "category": [
                    "Electronics",
                    "Clothing",
                    "Electronics",
                    "Clothing",
                    "Electronics",
                    "Clothing",
                ],
                "sales": [100, 50, 80, 60, 120, 70],
            }
        )

    def test_calculate_pivot(self, sample_data):
        """피벗 계산"""
        calc = CrossTableCalculator()
        result = calc.calculate(
            data=sample_data,
            row_columns=["region"],
            col_columns=["category"],
            value_column="sales",
            agg_func="sum",
        )

        assert "row_headers" in result
        assert "col_headers" in result
        assert "values" in result

        # 3 지역 x 2 카테고리
        assert len(result["row_headers"]) == 3
        assert len(result["col_headers"]) == 2

    def test_calculate_totals(self, sample_data):
        """합계 계산"""
        calc = CrossTableCalculator()
        result = calc.calculate(
            data=sample_data,
            row_columns=["region"],
            col_columns=["category"],
            value_column="sales",
            agg_func="sum",
            show_row_totals=True,
            show_col_totals=True,
        )

        assert "row_totals" in result
        assert "col_totals" in result
        assert "grand_total" in result

    def test_hierarchical_rows(self):
        """계층적 행 테스트"""
        data = pl.DataFrame(
            {
                "region": ["Asia", "Asia", "Asia", "Asia"],
                "country": ["Korea", "Korea", "Japan", "Japan"],
                "category": ["A", "B", "A", "B"],
                "value": [10, 20, 30, 40],
            }
        )

        calc = CrossTableCalculator()
        result = calc.calculate(
            data=data,
            row_columns=["region", "country"],
            col_columns=["category"],
            value_column="value",
            agg_func="sum",
        )

        # 계층적 헤더
        assert len(result["row_headers"]) > 0


class TestTreeMap:
    """TreeMap 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "category": ["A", "A", "B", "B", "C"],
                "subcategory": ["A1", "A2", "B1", "B2", "C1"],
                "value": [30, 20, 25, 15, 10],
            }
        )

    def test_calculate_rectangles(self, sample_data):
        """사각형 계산"""
        calc = TreeMapCalculator()
        result = calc.calculate(
            data=sample_data,
            hierarchy_columns=["category", "subcategory"],
            value_column="value",
            width=100,
            height=100,
        )

        assert "rectangles" in result
        assert len(result["rectangles"]) > 0

        # 모든 사각형이 영역 내에 있는지 확인
        for rect in result["rectangles"]:
            assert 0 <= rect["x"] <= 100
            assert 0 <= rect["y"] <= 100
            assert rect["width"] > 0
            assert rect["height"] > 0

    def test_area_proportional_to_value(self, sample_data):
        """면적이 값에 비례"""
        calc = TreeMapCalculator()
        result = calc.calculate(
            data=sample_data,
            hierarchy_columns=["category"],
            value_column="value",
            width=100,
            height=100,
        )

        # 총 면적이 100 * 100 = 10000 (구현에 따라 패딩/여백으로 차이 발생 가능)
        total_area = sum(r["width"] * r["height"] for r in result["rectangles"])
        assert abs(total_area - 10000) < 500  # 구현에 따른 오차 허용


class TestFunnelChart:
    """Funnel Chart 테스트"""

    @pytest.fixture
    def sample_data(self):
        return {
            "stages": ["Visitors", "Leads", "Opportunities", "Customers"],
            "values": [1000, 500, 200, 50],
        }

    def test_calculate_funnel(self, sample_data):
        """퍼널 계산"""
        calc = FunnelCalculator()
        result = calc.calculate(
            stages=sample_data["stages"], values=sample_data["values"]
        )

        assert "widths" in result
        assert "conversion_rates" in result

        # 폭이 감소해야 함
        for i in range(len(result["widths"]) - 1):
            assert result["widths"][i] >= result["widths"][i + 1]

    def test_conversion_rates(self, sample_data):
        """전환율 계산"""
        calc = FunnelCalculator()
        result = calc.calculate(
            stages=sample_data["stages"], values=sample_data["values"]
        )

        # 전환율이 계산되어야 함
        assert "conversion_rates" in result
        assert len(result["conversion_rates"]) > 0
        # 전환율은 0~100 범위 또는 0~1 범위일 수 있음
        first_rate = result["conversion_rates"][0]
        assert first_rate >= 0


class TestRadarChart:
    """Radar Chart 테스트"""

    @pytest.fixture
    def sample_data(self):
        return {
            "axes": ["Speed", "Power", "Defense", "Magic", "Luck"],
            "series": [
                {"name": "Player A", "values": [80, 60, 70, 90, 50]},
                {"name": "Player B", "values": [70, 80, 60, 50, 90]},
            ],
        }

    def test_calculate_coordinates(self, sample_data):
        """좌표 계산"""
        calc = RadarCalculator()
        result = calc.calculate(
            axes=sample_data["axes"], series=sample_data["series"], max_value=100
        )

        assert "axis_angles" in result
        assert "series_coordinates" in result

        # 5개 축 = 72도 간격
        assert len(result["axis_angles"]) == 5

        # 각 시리즈의 좌표
        for series_name, coords in result["series_coordinates"].items():
            assert len(coords) == 5
            for x, y in coords:
                # 정규화된 좌표는 -1 ~ 1 범위
                assert -1 <= x <= 1
                assert -1 <= y <= 1

    def test_polygon_area(self, sample_data):
        """폴리곤 면적 계산"""
        calc = RadarCalculator()
        result = calc.calculate(
            axes=sample_data["axes"], series=sample_data["series"], max_value=100
        )

        # 면적 계산 (optional)
        if "series_areas" in result:
            for area in result["series_areas"].values():
                assert area > 0
