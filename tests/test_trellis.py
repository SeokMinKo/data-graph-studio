"""
Trellis Visualization 테스트
"""

import pytest
import polars as pl
from typing import List, Dict

from data_graph_studio.graph.trellis import (
    TrellisMode,
    TrellisSettings,
    TrellisLayout,
    TrellisCalculator,
)


class TestTrellisSettings:
    """TrellisSettings 테스트"""

    def test_init_default(self):
        """기본 초기화"""
        settings = TrellisSettings()

        assert settings.enabled is False
        assert settings.mode == TrellisMode.ROWS_AND_COLUMNS
        assert settings.row_column is None
        assert settings.col_column is None

    def test_init_with_columns(self):
        """컬럼과 함께 초기화"""
        settings = TrellisSettings(
            enabled=True,
            row_column="region",
            col_column="category"
        )

        assert settings.enabled is True
        assert settings.row_column == "region"
        assert settings.col_column == "category"


class TestTrellisCalculator:
    """TrellisCalculator 테스트"""

    @pytest.fixture
    def sample_data(self):
        """샘플 데이터"""
        return pl.DataFrame({
            "region": ["Asia", "Asia", "Europe", "Europe", "Asia", "Europe"],
            "category": ["A", "B", "A", "B", "A", "B"],
            "value": [100, 150, 200, 180, 120, 160]
        })

    @pytest.fixture
    def calculator(self):
        return TrellisCalculator()

    def test_calculate_grid_size(self, calculator, sample_data):
        """그리드 크기 계산"""
        settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.ROWS_AND_COLUMNS,
            row_column="region",
            col_column="category"
        )

        layout = calculator.calculate(sample_data, settings)

        assert layout.n_rows == 2  # Asia, Europe
        assert layout.n_cols == 2  # A, B

    def test_calculate_panels(self, calculator, sample_data):
        """패널 데이터 분할"""
        settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.ROWS_AND_COLUMNS,
            row_column="region",
            col_column="category"
        )

        layout = calculator.calculate(sample_data, settings)

        # 각 패널에 올바른 데이터가 있는지 확인
        assert len(layout.panels) == 4  # 2x2

        for panel in layout.panels:
            assert "data" in panel
            assert "row_value" in panel
            assert "col_value" in panel

    def test_calculate_row_only(self, calculator, sample_data):
        """행만 분할"""
        settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.ROWS_AND_COLUMNS,
            row_column="region",
            col_column=None
        )

        layout = calculator.calculate(sample_data, settings)

        assert layout.n_rows == 2
        assert layout.n_cols == 1

    def test_calculate_col_only(self, calculator, sample_data):
        """열만 분할"""
        settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.ROWS_AND_COLUMNS,
            row_column=None,
            col_column="category"
        )

        layout = calculator.calculate(sample_data, settings)

        assert layout.n_rows == 1
        assert layout.n_cols == 2

    def test_max_panels(self, calculator):
        """최대 패널 수 제한"""
        # 많은 고유값
        data = pl.DataFrame({
            "x": list(range(100)),
            "value": list(range(100))
        })

        settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.ROWS_AND_COLUMNS,
            row_column="x",
            max_rows=5
        )

        layout = calculator.calculate(data, settings)

        assert layout.n_rows <= 5

    def test_panel_coordinates(self, calculator, sample_data):
        """패널 좌표 계산"""
        settings = TrellisSettings(
            enabled=True,
            row_column="region",
            col_column="category"
        )

        layout = calculator.calculate(
            sample_data, settings,
            total_width=100, total_height=100
        )

        # 각 패널의 좌표 확인
        for panel in layout.panels:
            assert "x" in panel
            assert "y" in panel
            assert "width" in panel
            assert "height" in panel
            assert 0 <= panel["x"] <= 100
            assert 0 <= panel["y"] <= 100

    def test_sync_axes(self, calculator, sample_data):
        """축 동기화"""
        settings = TrellisSettings(
            enabled=True,
            row_column="region",
            col_column="category",
            sync_axes=True
        )

        layout = calculator.calculate(sample_data, settings)

        # 모든 패널이 동일한 축 범위를 가져야 함
        if layout.sync_axes:
            assert layout.shared_y_range is not None
            assert layout.shared_y_range[0] <= layout.shared_y_range[1]

    def test_disabled_trellis(self, calculator, sample_data):
        """Trellis 비활성화"""
        settings = TrellisSettings(enabled=False)

        layout = calculator.calculate(sample_data, settings)

        assert layout.n_rows == 1
        assert layout.n_cols == 1
        assert len(layout.panels) == 1


class TestTrellisMode:
    """Trellis 모드 테스트"""

    @pytest.fixture
    def calculator(self):
        return TrellisCalculator()

    def test_panels_mode(self, calculator):
        """패널 모드 (페이지네이션)"""
        data = pl.DataFrame({
            "group": ["A", "A", "B", "B", "C", "C", "D", "D"],
            "value": [1, 2, 3, 4, 5, 6, 7, 8]
        })

        settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.PANELS,
            panel_column="group",
            panels_per_page=2
        )

        layout = calculator.calculate(data, settings)

        assert layout.total_panels == 4  # A, B, C, D
        assert layout.panels_per_page == 2
        assert layout.total_pages == 2
