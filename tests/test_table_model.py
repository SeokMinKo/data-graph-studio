"""
Table Model 테스트 (가상 스크롤)
"""

import pytest
import polars as pl
from PySide6.QtCore import Qt, QModelIndex

from data_graph_studio.ui.panels.table_panel import PolarsTableModel


class TestPolarsTableModel:
    """PolarsTableModel 테스트"""

    @pytest.fixture
    def model(self):
        """테이블 모델 인스턴스"""
        return PolarsTableModel()

    @pytest.fixture
    def sample_df(self):
        """샘플 데이터프레임"""
        return pl.DataFrame(
            {
                "id": list(range(10000)),
                "name": [f"item_{i}" for i in range(10000)],
                "value": [i * 1.5 for i in range(10000)],
                "category": ["A", "B", "C"] * 3333 + ["A"],
            }
        )

    @pytest.fixture
    def small_df(self):
        """작은 데이터프레임"""
        return pl.DataFrame(
            {"id": [1, 2, 3], "name": ["a", "b", "c"], "value": [1.0, 2.0, 3.0]}
        )

    # ==================== 초기화 테스트 ====================

    def test_init(self, model):
        """초기화 테스트"""
        assert model.rowCount() == 0
        assert model.columnCount() == 0

    def test_set_dataframe(self, model, sample_df):
        """데이터프레임 설정 테스트"""
        model.set_dataframe(sample_df)

        assert model.rowCount() == 10000
        assert model.columnCount() == 4

    def test_set_none_dataframe(self, model, sample_df):
        """None 설정 테스트"""
        model.set_dataframe(sample_df)
        model.set_dataframe(None)

        assert model.rowCount() == 0
        assert model.columnCount() == 0

    # ==================== 데이터 접근 테스트 ====================

    def test_data_display_role(self, model, small_df):
        """DisplayRole 데이터 접근 테스트"""
        model.set_dataframe(small_df)

        index = model.index(0, 0)
        assert model.data(index, Qt.DisplayRole) == "1"

        index = model.index(0, 1)
        assert model.data(index, Qt.DisplayRole) == "a"

        index = model.index(0, 2)
        assert model.data(index, Qt.DisplayRole) == "1.0"

    def test_data_invalid_index(self, model, small_df):
        """잘못된 인덱스 테스트"""
        model.set_dataframe(small_df)

        # 유효하지 않은 인덱스
        index = QModelIndex()
        assert model.data(index, Qt.DisplayRole) is None

    def test_data_null_value(self, model):
        """NULL 값 테스트"""
        df = pl.DataFrame({"id": [1, None, 3], "name": ["a", "b", None]})
        model.set_dataframe(df)

        # None 값은 빈 문자열로
        index = model.index(1, 0)
        assert model.data(index, Qt.DisplayRole) == ""

        index = model.index(2, 1)
        assert model.data(index, Qt.DisplayRole) == ""

    # ==================== 헤더 테스트 ====================

    def test_header_data_horizontal(self, model, small_df):
        """가로 헤더 테스트"""
        model.set_dataframe(small_df)

        assert model.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "id"
        assert model.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "name"
        assert model.headerData(2, Qt.Horizontal, Qt.DisplayRole) == "value"

    def test_header_data_vertical(self, model, small_df):
        """세로 헤더 테스트"""
        model.set_dataframe(small_df)

        assert model.headerData(0, Qt.Vertical, Qt.DisplayRole) == "1"
        assert model.headerData(1, Qt.Vertical, Qt.DisplayRole) == "2"
        assert model.headerData(2, Qt.Vertical, Qt.DisplayRole) == "3"

    def test_header_data_invalid_section(self, model, small_df):
        """잘못된 섹션 헤더 테스트"""
        model.set_dataframe(small_df)

        assert model.headerData(100, Qt.Horizontal, Qt.DisplayRole) is None

    # ==================== 컬럼 이름 테스트 ====================

    def test_get_column_name(self, model, small_df):
        """컬럼 이름 가져오기 테스트"""
        model.set_dataframe(small_df)

        assert model.get_column_name(0) == "id"
        assert model.get_column_name(1) == "name"
        assert model.get_column_name(2) == "value"

    def test_get_column_name_invalid(self, model, small_df):
        """잘못된 인덱스로 컬럼 이름 테스트"""
        model.set_dataframe(small_df)

        assert model.get_column_name(-1) is None
        assert model.get_column_name(100) is None

    # ==================== 가상 스크롤 (청크 로딩) 테스트 ====================

    def test_column_cache_loading_first(self, model, sample_df):
        """첫 번째 컬럼 캐시 로딩 테스트"""
        model.set_dataframe(sample_df)

        # 처음 행 접근
        index = model.index(0, 0)
        value = model.data(index, Qt.DisplayRole)

        assert value == "0"
        # 컬럼 캐시에 로드됨
        assert 0 in model._column_cache

    def test_column_cache_loading_middle(self, model, sample_df):
        """중간 행 데이터 접근 테스트"""
        model.set_dataframe(sample_df)

        # 5000번째 행 접근
        index = model.index(5000, 0)
        value = model.data(index, Qt.DisplayRole)

        assert value == "5000"
        # 같은 컬럼이므로 컬럼 0이 캐시에 있어야 함
        assert 0 in model._column_cache

    def test_column_cache_loading_last(self, model, sample_df):
        """마지막 행 데이터 접근 테스트"""
        model.set_dataframe(sample_df)

        # 마지막 행 접근
        index = model.index(9999, 0)
        value = model.data(index, Qt.DisplayRole)

        assert value == "9999"

    def test_cache_cleared_on_new_dataframe(self, model, sample_df):
        """새 데이터프레임 설정 시 캐시 클리어 테스트"""
        model.set_dataframe(sample_df)

        # 캐시 채우기
        index = model.index(0, 0)
        model.data(index, Qt.DisplayRole)
        assert len(model._column_cache) > 0

        # 새 데이터프레임 설정
        new_df = pl.DataFrame({"x": [1, 2, 3]})
        model.set_dataframe(new_df)

        # 캐시가 클리어됨
        assert len(model._column_cache) == 0

    def test_sequential_access(self, model, sample_df):
        """순차 접근 테스트"""
        model.set_dataframe(sample_df)

        # 순차적으로 여러 행 접근
        for i in range(0, 100):
            index = model.index(i, 0)
            value = model.data(index, Qt.DisplayRole)
            assert value == str(i)

    def test_random_access(self, model, sample_df):
        """랜덤 접근 테스트"""
        model.set_dataframe(sample_df)

        # 무작위 순서로 접근
        for row in [5000, 100, 9000, 2500, 7500]:
            index = model.index(row, 0)
            value = model.data(index, Qt.DisplayRole)
            assert value == str(row)

    # ==================== 성능 테스트 ====================

    def test_column_cache_efficiency(self, model, sample_df):
        """컬럼 캐시 효율성 테스트"""
        model.set_dataframe(sample_df)

        # 여러 행 접근 (같은 컬럼)
        for i in range(0, 1000, 100):
            index = model.index(i, 0)
            model.data(index, Qt.DisplayRole)

        # 컬럼 캐시에는 접근한 컬럼만 존재
        assert len(model._column_cache) == 1  # 컬럼 0만 캐시됨

    def test_large_dataframe(self):
        """대용량 데이터프레임 테스트 (MAX_DISPLAY_ROWS 제한)"""
        model = PolarsTableModel()

        # 100만 행 데이터
        df = pl.DataFrame(
            {"id": list(range(1_000_000)), "value": list(range(1_000_000))}
        )

        model.set_dataframe(df)

        # MAX_DISPLAY_ROWS 제한으로 인해 100,000개만 표시
        assert model.rowCount() == model.MAX_DISPLAY_ROWS
        assert model.get_actual_row_count() == 1_000_000

        # 표시 범위 내 데이터 접근
        index = model.index(50_000, 0)
        value = model.data(index, Qt.DisplayRole)
        assert value == "50000"


class TestPolarsTableModelEdgeCases:
    """PolarsTableModel 엣지 케이스 테스트"""

    @pytest.fixture
    def model(self):
        return PolarsTableModel()

    def test_empty_dataframe(self, model):
        """빈 데이터프레임 테스트"""
        df = pl.DataFrame()
        model.set_dataframe(df)

        assert model.rowCount() == 0
        assert model.columnCount() == 0

    def test_single_row(self, model):
        """단일 행 테스트"""
        df = pl.DataFrame({"x": [1]})
        model.set_dataframe(df)

        assert model.rowCount() == 1
        index = model.index(0, 0)
        assert model.data(index, Qt.DisplayRole) == "1"

    def test_single_column(self, model):
        """단일 컬럼 테스트"""
        df = pl.DataFrame({"x": [1, 2, 3]})
        model.set_dataframe(df)

        assert model.columnCount() == 1

    def test_various_dtypes(self, model):
        """다양한 데이터 타입 테스트"""
        df = pl.DataFrame(
            {
                "int_col": [1, 2, 3],
                "float_col": [1.5, 2.5, 3.5],
                "str_col": ["a", "b", "c"],
                "bool_col": [True, False, True],
                "date_col": pl.Series(
                    ["2023-01-01", "2023-01-02", "2023-01-03"]
                ).str.strptime(pl.Date, "%Y-%m-%d"),
            }
        )
        model.set_dataframe(df)

        # 각 타입이 문자열로 잘 변환되는지
        index = model.index(0, 0)
        assert model.data(index, Qt.DisplayRole) == "1"

        index = model.index(0, 1)
        assert model.data(index, Qt.DisplayRole) == "1.5"

        index = model.index(0, 2)
        assert model.data(index, Qt.DisplayRole) == "a"

        index = model.index(0, 3)
        assert model.data(index, Qt.DisplayRole) in ["True", "true"]

    def test_unicode_strings(self, model):
        """유니코드 문자열 테스트"""
        df = pl.DataFrame({"name": ["한글", "日本語", "中文", "émoji 🎉"]})
        model.set_dataframe(df)

        index = model.index(0, 0)
        assert model.data(index, Qt.DisplayRole) == "한글"

        index = model.index(3, 0)
        assert model.data(index, Qt.DisplayRole) == "émoji 🎉"

    def test_special_characters(self, model):
        """특수 문자 테스트"""
        df = pl.DataFrame(
            {"text": ["line1\nline2", "tab\there", 'quote"test', "single'quote"]}
        )
        model.set_dataframe(df)

        index = model.index(0, 0)
        assert "line1" in model.data(index, Qt.DisplayRole)
