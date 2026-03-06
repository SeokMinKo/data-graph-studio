"""
Details-on-Demand Panel 테스트
"""

import pytest
import polars as pl

from data_graph_studio.core.marking import MarkingManager
from data_graph_studio.ui.panels.details_panel import (
    DetailsOnDemandModel,
    DetailsColumnConfig,
)


class TestDetailsOnDemandModel:
    """DetailsOnDemandModel 테스트"""

    @pytest.fixture
    def sample_data(self):
        """샘플 데이터"""
        return pl.DataFrame(
            {
                "id": [1, 2, 3, 4, 5],
                "name": ["Apple", "Banana", "Cherry", "Date", "Elderberry"],
                "sales": [100, 200, 150, 300, 50],
                "region": ["Asia", "Europe", "Asia", "America", "Europe"],
                "price": [1.5, 2.0, 3.5, 4.0, 2.5],
            }
        )

    @pytest.fixture
    def model(self, qtbot, sample_data):
        """DetailsOnDemandModel 인스턴스"""
        m = DetailsOnDemandModel()
        m.set_data(sample_data)
        return m

    def test_init(self, model):
        """초기화 테스트"""
        assert model.rowCount() == 0  # 마킹 없으면 행 없음
        assert model.columnCount() == 5

    def test_set_marked_indices(self, model, qtbot):
        """마킹된 인덱스 설정"""
        model.set_marked_indices({0, 2, 4})

        assert model.rowCount() == 3

    def test_get_data_for_row(self, model):
        """특정 행 데이터 조회"""
        model.set_marked_indices({1})

        row_data = model.get_row_data(0)

        assert row_data["name"] == "Banana"
        assert row_data["sales"] == 200

    def test_column_visibility(self, model):
        """컬럼 가시성 설정"""
        model.set_column_visible("price", False)
        model.set_marked_indices({0})

        visible_columns = model.get_visible_columns()

        assert "price" not in visible_columns
        assert "name" in visible_columns

    def test_column_order(self, model):
        """컬럼 순서 변경"""
        model.set_column_order(["name", "sales", "region", "id", "price"])
        model.set_marked_indices({0})

        columns = model.get_visible_columns()

        assert columns[0] == "name"
        assert columns[1] == "sales"

    def test_clear_marked(self, model):
        """마킹 클리어"""
        model.set_marked_indices({0, 1, 2})
        assert model.rowCount() == 3

        model.set_marked_indices(set())

        assert model.rowCount() == 0

    def test_empty_data(self, qtbot):
        """빈 데이터 처리"""
        model = DetailsOnDemandModel()

        assert model.rowCount() == 0
        assert model.columnCount() == 0


class TestDetailsColumnConfig:
    """컬럼 설정 테스트"""

    def test_init(self):
        """초기화"""
        config = DetailsColumnConfig(
            name="sales",
            display_name="Sales Amount",
            visible=True,
            format_string="${:,.2f}",
        )

        assert config.name == "sales"
        assert config.display_name == "Sales Amount"
        assert config.visible is True
        assert config.format_string == "${:,.2f}"

    def test_format_value(self):
        """값 포맷팅"""
        config = DetailsColumnConfig(name="sales", format_string="${:,.2f}")

        formatted = config.format_value(1234.5)

        assert formatted == "$1,234.50"

    def test_format_value_no_format(self):
        """포맷 없을 때"""
        config = DetailsColumnConfig(name="name")

        formatted = config.format_value("Apple")

        assert formatted == "Apple"

    def test_format_value_none(self):
        """None 값 포맷팅"""
        config = DetailsColumnConfig(name="value")

        formatted = config.format_value(None)

        assert formatted == ""


class TestDetailsIntegration:
    """마킹 연동 통합 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "id": [1, 2, 3, 4, 5],
                "name": ["A", "B", "C", "D", "E"],
                "value": [10, 20, 30, 40, 50],
            }
        )

    @pytest.fixture
    def marking_manager(self, qtbot):
        return MarkingManager()

    def test_marking_updates_details(self, qtbot, sample_data, marking_manager):
        """마킹 변경 시 Details 업데이트"""
        model = DetailsOnDemandModel()
        model.set_data(sample_data)

        # 마킹 시그널 연결
        marking_manager.marking_changed.connect(
            lambda name, indices: model.set_marked_indices(indices)
        )

        # 마킹
        marking_manager.mark("Main", {1, 3})

        assert model.rowCount() == 2

    def test_empty_marking_clears_details(self, qtbot, sample_data, marking_manager):
        """마킹 클리어 시 Details 비움"""
        model = DetailsOnDemandModel()
        model.set_data(sample_data)

        marking_manager.marking_changed.connect(
            lambda name, indices: model.set_marked_indices(indices)
        )

        marking_manager.mark("Main", {0, 1, 2})
        assert model.rowCount() == 3

        marking_manager.clear_marking("Main")
        assert model.rowCount() == 0


class TestDetailsExport:
    """Details 내보내기 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {"id": [1, 2, 3], "name": ["A", "B", "C"], "value": [10, 20, 30]}
        )

    @pytest.fixture
    def model(self, qtbot, sample_data):
        m = DetailsOnDemandModel()
        m.set_data(sample_data)
        m.set_marked_indices({0, 1, 2})
        return m

    def test_export_to_clipboard_text(self, model):
        """클립보드용 텍스트 내보내기"""
        text = model.export_as_text(delimiter="\t")

        lines = text.strip().split("\n")
        assert len(lines) == 4  # 헤더 + 3 데이터 행

    def test_export_to_csv(self, model, tmp_path):
        """CSV 내보내기"""
        file_path = tmp_path / "details.csv"
        model.export_to_csv(str(file_path))

        import csv

        with open(file_path, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) == 4  # 헤더 + 3 데이터 행

    def test_get_marked_dataframe(self, model):
        """마킹된 데이터프레임 반환"""
        df = model.get_marked_dataframe()

        assert len(df) == 3
        assert list(df.columns) == ["id", "name", "value"]
