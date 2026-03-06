"""
Table Search Enhancement 테스트
"""

import pytest
import polars as pl
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


# QApplication이 필요한 테스트를 위한 fixture
@pytest.fixture(scope="module")
def qapp():
    """QApplication 인스턴스"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestSearchDebouncing:
    """검색 디바운싱 테스트"""

    def test_debounce_timer_setup(self, qapp):
        """디바운스 타이머 설정 확인"""
        from data_graph_studio.core.state import AppState
        from data_graph_studio.core.data_engine import DataEngine

        AppState()
        DataEngine()

        # TablePanel에 search_debounce_timer가 있어야 함
        # 이 테스트는 구현 후 활성화
        # panel = TablePanel(state, engine)
        # assert hasattr(panel, '_search_debounce_timer')
        # assert panel._search_debounce_timer.interval() == 300
        pass

    def test_debounce_prevents_rapid_search(self, qapp):
        """빠른 타이핑 시 검색 지연"""
        # 구현 후 테스트 활성화
        pass


class TestSearchResultCount:
    """검색 결과 카운트 테스트"""

    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame(
            {
                "name": ["Alice", "Bob", "Charlie", "David", "Alice2"],
                "value": [10, 20, 30, 40, 50],
            }
        )

    def test_search_result_count_display(self, qapp, sample_df):
        """검색 결과 카운트 표시"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = sample_df

        # 'Alice' 검색 시 2개 결과
        result = engine.search("Alice")
        assert len(result) == 2

    def test_search_no_results(self, qapp, sample_df):
        """검색 결과 없음"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = sample_df

        # 존재하지 않는 값 검색
        result = engine.search("XYZ")
        assert len(result) == 0

    def test_search_all_results(self, qapp, sample_df):
        """빈 검색어 시 전체 결과"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = sample_df

        # 빈 검색어는 전체 데이터 반환 (빈 패턴 매치로 모든 행 반환)
        result = engine.search("")
        # 빈 문자열 검색은 모든 행과 매치되거나 원본 반환
        assert result is None or len(result) == len(sample_df)


class TestSearchCaseSensitivity:
    """대소문자 구분 검색 테스트"""

    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame(
            {"name": ["Alice", "ALICE", "alice", "Bob"], "value": [1, 2, 3, 4]}
        )

    def test_case_insensitive_search(self, sample_df):
        """UT-10: 대소문자 구분 없는 검색 (기본)"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = sample_df

        # 기본: 대소문자 구분 없음
        result = engine.search("alice", case_sensitive=False)
        assert len(result) == 3

    def test_case_sensitive_search(self, sample_df):
        """대소문자 구분 검색"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = sample_df

        # 대소문자 구분
        result = engine.search("alice", case_sensitive=True)
        assert len(result) == 1
        assert result["name"][0] == "alice"


class TestSearchColumnSelection:
    """검색 컬럼 선택 테스트"""

    @pytest.fixture
    def multi_col_df(self):
        return pl.DataFrame(
            {
                "name": ["Alice", "Bob", "Charlie"],
                "city": ["Seoul", "Tokyo", "Alice City"],
                "value": [10, 20, 30],
            }
        )

    def test_search_specific_columns(self, multi_col_df):
        """특정 컬럼만 검색"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = multi_col_df

        # 'name' 컬럼만 검색
        result = engine.search("Alice", columns=["name"])
        assert len(result) == 1

        # 'city' 컬럼만 검색 (Alice City 포함)
        result = engine.search("Alice", columns=["city"])
        assert len(result) == 1
        assert result["city"][0] == "Alice City"

    def test_search_all_columns(self, multi_col_df):
        """전체 컬럼 검색"""
        from data_graph_studio.core.data_engine import DataEngine

        engine = DataEngine()
        engine._df = multi_col_df

        # 전체 컬럼 검색 (Alice in name, Alice City in city)
        result = engine.search("Alice")
        assert len(result) == 2


class TestSearchIntegrationWithSort:
    """검색 + 정렬 통합 테스트"""

    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame(
            {"name": ["Alice", "Bob", "Alice2", "Charlie"], "value": [30, 10, 20, 40]}
        )

    def test_search_then_sort(self, sample_df):
        """IT-4: 검색 후 정렬"""
        from data_graph_studio.core.data_engine import DataEngine
        from data_graph_studio.ui.panels.table_panel import PolarsTableModel

        engine = DataEngine()
        engine._df = sample_df

        # 검색
        search_result = engine.search("Alice")
        assert len(search_result) == 2

        # 정렬
        model = PolarsTableModel()
        model.set_dataframe(search_result)
        model.sort(1, Qt.AscendingOrder)  # value 기준 정렬

        # Alice2 (value=20)가 먼저, Alice (value=30)가 나중
        assert model.data(model.index(0, 0), Qt.DisplayRole) == "Alice2"
        assert model.data(model.index(1, 0), Qt.DisplayRole) == "Alice"
