"""
State Management 테스트
"""

import pytest
from unittest.mock import MagicMock

from data_graph_studio.core.state import (
    AppState, SelectionState, GroupColumn, ValueColumn,
    AggregationType, ChartType, ToolMode, FilterCondition, SortCondition
)


class TestSelectionState:
    """SelectionState 클래스 테스트"""
    
    def test_init(self):
        """초기화 테스트"""
        selection = SelectionState()
        assert selection.has_selection is False
        assert selection.selection_count == 0
    
    def test_select(self):
        """선택 테스트"""
        selection = SelectionState()
        selection.select([1, 2, 3])
        
        assert selection.has_selection is True
        assert selection.selection_count == 3
        assert 1 in selection.selected_rows
        assert 2 in selection.selected_rows
        assert 3 in selection.selected_rows
    
    def test_select_add(self):
        """추가 선택 테스트"""
        selection = SelectionState()
        selection.select([1, 2])
        selection.select([3, 4], add=True)
        
        assert selection.selection_count == 4
    
    def test_select_replace(self):
        """대체 선택 테스트"""
        selection = SelectionState()
        selection.select([1, 2])
        selection.select([3, 4], add=False)
        
        assert selection.selection_count == 2
        assert 1 not in selection.selected_rows
        assert 3 in selection.selected_rows
    
    def test_deselect(self):
        """선택 해제 테스트"""
        selection = SelectionState()
        selection.select([1, 2, 3])
        selection.deselect([2])
        
        assert selection.selection_count == 2
        assert 2 not in selection.selected_rows
    
    def test_toggle(self):
        """토글 테스트"""
        selection = SelectionState()
        selection.toggle(1)
        assert 1 in selection.selected_rows
        
        selection.toggle(1)
        assert 1 not in selection.selected_rows
    
    def test_clear(self):
        """클리어 테스트"""
        selection = SelectionState()
        selection.select([1, 2, 3])
        selection.highlighted_rows.update([4, 5])
        selection.clear()
        
        assert selection.has_selection is False
        assert len(selection.highlighted_rows) == 0


class TestAppState:
    """AppState 클래스 테스트"""
    
    @pytest.fixture
    def state(self, qtbot):
        """AppState 인스턴스"""
        return AppState()
    
    # ==================== Data State ====================
    
    def test_init(self, state):
        """초기화 테스트"""
        assert state.is_data_loaded is False
        assert state.total_rows == 0
        assert state.visible_rows == 0
    
    def test_set_data_loaded(self, state, qtbot):
        """데이터 로드 상태 테스트"""
        with qtbot.waitSignal(state.data_loaded):
            state.set_data_loaded(True, 1000)
        
        assert state.is_data_loaded is True
        assert state.total_rows == 1000
        assert state.visible_rows == 1000
    
    def test_set_data_cleared(self, state, qtbot):
        """데이터 클리어 테스트"""
        state.set_data_loaded(True, 1000)
        
        with qtbot.waitSignal(state.data_cleared):
            state.set_data_loaded(False)
        
        assert state.is_data_loaded is False
    
    # ==================== Group Zone ====================
    
    def test_add_group_column(self, state, qtbot):
        """그룹 컬럼 추가 테스트"""
        with qtbot.waitSignal(state.group_zone_changed):
            state.add_group_column("category")
        
        assert len(state.group_columns) == 1
        assert state.group_columns[0].name == "category"
    
    def test_add_group_column_duplicate(self, state):
        """중복 그룹 컬럼 방지 테스트"""
        state.add_group_column("category")
        state.add_group_column("category")  # 중복
        
        assert len(state.group_columns) == 1
    
    def test_remove_group_column(self, state, qtbot):
        """그룹 컬럼 제거 테스트"""
        state.add_group_column("category")
        state.add_group_column("region")
        
        with qtbot.waitSignal(state.group_zone_changed):
            state.remove_group_column("category")
        
        assert len(state.group_columns) == 1
        assert state.group_columns[0].name == "region"
    
    def test_reorder_group_columns(self, state, qtbot):
        """그룹 컬럼 순서 변경 테스트"""
        state.add_group_column("a")
        state.add_group_column("b")
        state.add_group_column("c")
        
        with qtbot.waitSignal(state.group_zone_changed):
            state.reorder_group_columns(["c", "a", "b"])
        
        assert state.group_columns[0].name == "c"
        assert state.group_columns[1].name == "a"
        assert state.group_columns[2].name == "b"
    
    def test_clear_group_zone(self, state, qtbot):
        """그룹 존 클리어 테스트"""
        state.add_group_column("a")
        state.add_group_column("b")
        
        with qtbot.waitSignal(state.group_zone_changed):
            state.clear_group_zone()
        
        assert len(state.group_columns) == 0
    
    # ==================== Value Zone ====================
    
    def test_add_value_column(self, state, qtbot):
        """밸류 컬럼 추가 테스트"""
        with qtbot.waitSignal(state.value_zone_changed):
            state.add_value_column("sales", AggregationType.SUM)
        
        assert len(state.value_columns) == 1
        assert state.value_columns[0].name == "sales"
        assert state.value_columns[0].aggregation == AggregationType.SUM
    
    def test_add_value_column_auto_color(self, state):
        """밸류 컬럼 자동 색상 할당 테스트"""
        state.add_value_column("sales")
        state.add_value_column("profit")
        
        assert state.value_columns[0].color != state.value_columns[1].color
    
    def test_remove_value_column(self, state, qtbot):
        """밸류 컬럼 제거 테스트"""
        state.add_value_column("sales")
        state.add_value_column("profit")
        
        with qtbot.waitSignal(state.value_zone_changed):
            state.remove_value_column(0)
        
        assert len(state.value_columns) == 1
        assert state.value_columns[0].name == "profit"
    
    def test_update_value_column(self, state, qtbot):
        """밸류 컬럼 업데이트 테스트"""
        state.add_value_column("sales", AggregationType.SUM)
        
        with qtbot.waitSignal(state.value_zone_changed):
            state.update_value_column(0, aggregation=AggregationType.MEAN, color="#ff0000")
        
        assert state.value_columns[0].aggregation == AggregationType.MEAN
        assert state.value_columns[0].color == "#ff0000"
    
    def test_clear_value_zone(self, state, qtbot):
        """밸류 존 클리어 테스트"""
        state.add_value_column("sales")
        state.add_value_column("profit")
        
        with qtbot.waitSignal(state.value_zone_changed):
            state.clear_value_zone()
        
        assert len(state.value_columns) == 0
    
    # ==================== X Column ====================
    
    def test_set_x_column(self, state, qtbot):
        """X 컬럼 설정 테스트"""
        with qtbot.waitSignal(state.chart_settings_changed):
            state.set_x_column("date")
        
        assert state.x_column == "date"
    
    # ==================== Filters ====================
    
    def test_add_filter(self, state, qtbot):
        """필터 추가 테스트"""
        with qtbot.waitSignal(state.filter_changed):
            state.add_filter("sales", "gt", 100)
        
        assert len(state.filters) == 1
        assert state.filters[0].column == "sales"
        assert state.filters[0].operator == "gt"
        assert state.filters[0].value == 100
    
    def test_remove_filter(self, state, qtbot):
        """필터 제거 테스트"""
        state.add_filter("sales", "gt", 100)
        state.add_filter("region", "eq", "US")
        
        with qtbot.waitSignal(state.filter_changed):
            state.remove_filter(0)
        
        assert len(state.filters) == 1
        assert state.filters[0].column == "region"
    
    def test_toggle_filter(self, state, qtbot):
        """필터 활성화/비활성화 테스트"""
        state.add_filter("sales", "gt", 100)
        assert state.filters[0].enabled is True
        
        with qtbot.waitSignal(state.filter_changed):
            state.toggle_filter(0)
        
        assert state.filters[0].enabled is False
    
    def test_clear_filters(self, state, qtbot):
        """필터 클리어 테스트"""
        state.add_filter("sales", "gt", 100)
        state.add_filter("region", "eq", "US")
        
        with qtbot.waitSignal(state.filter_changed):
            state.clear_filters()
        
        assert len(state.filters) == 0
    
    # ==================== Sorts ====================
    
    def test_set_sort(self, state, qtbot):
        """정렬 설정 테스트"""
        with qtbot.waitSignal(state.sort_changed):
            state.set_sort("sales", descending=True)
        
        assert len(state.sorts) == 1
        assert state.sorts[0].column == "sales"
        assert state.sorts[0].descending is True
    
    def test_set_sort_multiple(self, state, qtbot):
        """다중 정렬 테스트"""
        state.set_sort("category")
        
        with qtbot.waitSignal(state.sort_changed):
            state.set_sort("sales", descending=True, add=True)
        
        assert len(state.sorts) == 2
    
    def test_clear_sorts(self, state, qtbot):
        """정렬 클리어 테스트"""
        state.set_sort("sales")
        
        with qtbot.waitSignal(state.sort_changed):
            state.clear_sorts()
        
        assert len(state.sorts) == 0
    
    # ==================== Selection ====================
    
    def test_select_rows(self, state, qtbot):
        """행 선택 테스트"""
        with qtbot.waitSignal(state.selection_changed):
            state.select_rows([1, 2, 3])
        
        assert state.selection.selection_count == 3
    
    def test_deselect_rows(self, state, qtbot):
        """행 선택 해제 테스트"""
        state.select_rows([1, 2, 3])
        
        with qtbot.waitSignal(state.selection_changed):
            state.deselect_rows([2])
        
        assert state.selection.selection_count == 2
    
    def test_toggle_row(self, state, qtbot):
        """행 토글 테스트"""
        with qtbot.waitSignal(state.selection_changed):
            state.toggle_row(5)
        
        assert 5 in state.selection.selected_rows
    
    def test_clear_selection(self, state, qtbot):
        """선택 클리어 테스트"""
        state.select_rows([1, 2, 3])
        
        with qtbot.waitSignal(state.selection_changed):
            state.clear_selection()
        
        assert state.selection.has_selection is False
    
    def test_select_all(self, state, qtbot):
        """전체 선택 테스트"""
        state.set_data_loaded(True, 100)
        
        with qtbot.waitSignal(state.selection_changed):
            state.select_all()
        
        assert state.selection.selection_count == 100
    
    # ==================== Chart Settings ====================
    
    def test_set_chart_type(self, state, qtbot):
        """차트 타입 설정 테스트"""
        with qtbot.waitSignal(state.chart_settings_changed):
            state.set_chart_type(ChartType.BAR)
        
        assert state.chart_settings.chart_type == ChartType.BAR
    
    def test_update_chart_settings(self, state, qtbot):
        """차트 설정 업데이트 테스트"""
        with qtbot.waitSignal(state.chart_settings_changed):
            state.update_chart_settings(
                line_width=3,
                marker_size=10,
                show_data_labels=True
            )
        
        assert state.chart_settings.line_width == 3
        assert state.chart_settings.marker_size == 10
        assert state.chart_settings.show_data_labels is True
    
    # ==================== Tool Mode ====================
    
    def test_set_tool_mode(self, state, qtbot):
        """툴 모드 설정 테스트"""
        with qtbot.waitSignal(state.tool_mode_changed):
            state.set_tool_mode(ToolMode.ZOOM)
        
        assert state.tool_mode == ToolMode.ZOOM
    
    # ==================== Layout ====================
    
    def test_layout_ratios(self, state):
        """레이아웃 비율 테스트"""
        assert sum(state.layout_ratios.values()) == pytest.approx(1.0, rel=0.01)
    
    def test_set_layout_ratio(self, state):
        """레이아웃 비율 변경 테스트"""
        state.set_layout_ratio('graph', 0.5)
        
        # 합이 여전히 1이어야 함
        assert sum(state.layout_ratios.values()) == pytest.approx(1.0, rel=0.01)
    
    # ==================== Column Order ====================
    
    def test_column_order(self, state):
        """컬럼 순서 테스트"""
        order = ["a", "b", "c"]
        state.set_column_order(order)
        
        assert state.get_column_order() == order
    
    def test_toggle_column_visibility(self, state):
        """컬럼 가시성 토글 테스트"""
        state.set_column_order(["a", "b", "c"])
        
        state.toggle_column_visibility("b")
        assert state.get_visible_columns() == ["a", "c"]
        
        state.toggle_column_visibility("b")
        assert state.get_visible_columns() == ["a", "b", "c"]
    
    # ==================== Reset ====================
    
    def test_reset(self, state, qtbot):
        """전체 초기화 테스트"""
        # 데이터 설정
        state.set_data_loaded(True, 1000)
        state.add_group_column("category")
        state.add_value_column("sales")
        state.add_filter("sales", "gt", 100)
        state.select_rows([1, 2, 3])
        
        with qtbot.waitSignal(state.data_cleared):
            state.reset()
        
        assert state.is_data_loaded is False
        assert len(state.group_columns) == 0
        assert len(state.value_columns) == 0
        assert len(state.filters) == 0
        assert state.selection.has_selection is False
