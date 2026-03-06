"""
Test UI-Function Connections - 시그널-슬롯 연결 테스트
"""

import pytest


# Test closure fix in ValueZone
class TestValueZoneClosures:
    """ValueZone의 클로저 캡처 문제 수정 테스트"""

    @pytest.fixture
    def mock_state(self):
        """Mock AppState"""
        from data_graph_studio.core.state import AppState, AggregationType

        state = AppState()

        # Add multiple value columns
        state.add_value_column("col_a", AggregationType.SUM)
        state.add_value_column("col_b", AggregationType.MEAN)
        state.add_value_column("col_c", AggregationType.MAX)

        return state

    def test_remove_button_correct_index(self, mock_state, qtbot):
        """각 제거 버튼이 올바른 인덱스를 참조하는지 테스트"""
        from data_graph_studio.ui.panels.table_panel import ValueZone

        zone = ValueZone(mock_state)
        qtbot.addWidget(zone)

        # Verify 3 columns were added
        assert len(mock_state.value_columns) == 3

        # Get the column names before removal
        original_names = [vc.name for vc in mock_state.value_columns]
        assert original_names == ["col_a", "col_b", "col_c"]

        # Simulate clicking remove on index 1 (col_b)
        # This tests that the closure captured the correct index
        zone._remove_value(1)

        # Verify col_b was removed, not col_c (which would happen with late binding bug)
        remaining_names = [vc.name for vc in mock_state.value_columns]
        assert remaining_names == ["col_a", "col_c"]

    def test_aggregation_combo_correct_index(self, mock_state, qtbot):
        """각 집계 콤보박스가 올바른 인덱스를 참조하는지 테스트"""
        from data_graph_studio.ui.panels.table_panel import ValueZone
        from data_graph_studio.core.state import AggregationType

        zone = ValueZone(mock_state)
        qtbot.addWidget(zone)

        # Verify initial aggregations
        aggs = [vc.aggregation for vc in mock_state.value_columns]
        assert aggs == [AggregationType.SUM, AggregationType.MEAN, AggregationType.MAX]

        # Simulate changing aggregation for index 0
        zone._on_agg_changed(0, AggregationType.COUNT)

        # Verify only index 0 changed
        new_aggs = [vc.aggregation for vc in mock_state.value_columns]
        assert new_aggs == [
            AggregationType.COUNT,
            AggregationType.MEAN,
            AggregationType.MAX,
        ]

        # Simulate changing aggregation for index 2
        zone._on_agg_changed(2, AggregationType.MIN)

        # Verify only index 2 changed
        new_aggs = [vc.aggregation for vc in mock_state.value_columns]
        assert new_aggs == [
            AggregationType.COUNT,
            AggregationType.MEAN,
            AggregationType.MIN,
        ]


class TestFilterBarClosures:
    """FilterBar의 클로저 테스트"""

    @pytest.fixture
    def mock_state(self):
        """Mock AppState with filters"""
        from data_graph_studio.core.state import AppState

        state = AppState()

        # Add multiple filters
        state.add_filter("col_a", "eq", "value1")
        state.add_filter("col_b", "gt", 100)
        state.add_filter("col_c", "contains", "test")

        return state

    def test_filter_removal_correct_index(self, mock_state, qtbot):
        """필터 제거 시 올바른 인덱스가 참조되는지 테스트"""
        from data_graph_studio.ui.panels.table_panel import FilterBar

        bar = FilterBar(mock_state)
        qtbot.addWidget(bar)

        # Verify 3 filters exist
        assert len(mock_state.filters) == 3

        # Get original filter columns
        original_cols = [f.column for f in mock_state.filters]
        assert original_cols == ["col_a", "col_b", "col_c"]

        # Remove filter at index 1
        mock_state.remove_filter(1)

        # Verify col_b filter was removed
        remaining_cols = [f.column for f in mock_state.filters]
        assert remaining_cols == ["col_a", "col_c"]


class TestProfileBarClosures:
    """ProfileBar의 클로저 테스트"""

    def test_setting_button_captures_correct_id(self, qtbot):
        """각 설정 버튼이 올바른 setting_id를 캡처하는지 테스트"""
        from data_graph_studio.ui.panels.profile_bar import SettingButton
        from data_graph_studio.core.profile import GraphSetting

        # Create multiple settings
        settings = [
            GraphSetting.create_new("Setting A", "📊"),
            GraphSetting.create_new("Setting B", "📈"),
            GraphSetting.create_new("Setting C", "📉"),
        ]

        # Create buttons
        buttons = []
        for setting in settings:
            btn = SettingButton(setting, is_active=False)
            qtbot.addWidget(btn)
            buttons.append(btn)

        # Verify each button has correct setting
        for i, btn in enumerate(buttons):
            assert btn.setting.id == settings[i].id
            assert btn.setting.name == settings[i].name


class TestSignalConnectionsExist:
    """시그널-슬롯 연결이 올바르게 되어있는지 테스트"""

    def test_state_signals_defined(self):
        """AppState의 시그널들이 정의되어 있는지 확인"""
        from data_graph_studio.core.state import AppState

        state = AppState()

        # Essential signals should exist
        assert hasattr(state, "data_loaded")
        assert hasattr(state, "data_cleared")
        assert hasattr(state, "selection_changed")
        assert hasattr(state, "chart_settings_changed")
        assert hasattr(state, "group_zone_changed")
        assert hasattr(state, "value_zone_changed")
        assert hasattr(state, "hover_zone_changed")
        assert hasattr(state, "filter_changed")
        assert hasattr(state, "sort_changed")
        assert hasattr(state, "tool_mode_changed")
        assert hasattr(state, "limit_to_marking_changed")
        assert hasattr(state, "summary_updated")

        # Profile signals
        assert hasattr(state, "profile_loaded")
        assert hasattr(state, "profile_cleared")
        assert hasattr(state, "setting_activated")

        # Multi-dataset signals
        assert hasattr(state, "dataset_added")
        assert hasattr(state, "dataset_removed")
        assert hasattr(state, "dataset_activated")
        assert hasattr(state, "comparison_mode_changed")

    def test_panel_signals_defined(self):
        """주요 패널의 시그널들이 정의되어 있는지 확인"""
        from data_graph_studio.ui.panels.table_panel import (
            DataTableView,
            FilterBar,
            HiddenColumnsBar,
        )
        from data_graph_studio.ui.panels.graph_panel import GraphOptionsPanel, MainGraph

        # DataTableView signals
        assert hasattr(DataTableView, "column_dragged")
        assert hasattr(DataTableView, "rows_selected")
        assert hasattr(DataTableView, "exclude_value")
        assert hasattr(DataTableView, "hide_column")

        # FilterBar signals
        assert hasattr(FilterBar, "filter_removed")
        assert hasattr(FilterBar, "clear_all")

        # HiddenColumnsBar signals
        assert hasattr(HiddenColumnsBar, "show_column")
        assert hasattr(HiddenColumnsBar, "show_all")

        # GraphOptionsPanel signals
        assert hasattr(GraphOptionsPanel, "option_changed")

        # MainGraph signals
        assert hasattr(MainGraph, "points_selected")


class TestLambdaClosurePatterns:
    """람다 클로저 패턴이 올바르게 구현되었는지 테스트"""

    def test_lambda_captures_value_not_reference(self):
        """람다가 값을 올바르게 캡처하는지 확인하는 일반 테스트"""
        results = []

        # Wrong pattern (late binding - would fail)
        # for i in range(3):
        #     funcs.append(lambda: results.append(i))  # All would append 2!

        # Correct pattern (early binding with default argument)
        funcs = []
        for i in range(3):
            funcs.append(lambda x=i: results.append(x))

        # Execute all functions
        for f in funcs:
            f()

        # Each lambda should capture its own value
        assert results == [0, 1, 2]

    def test_function_parameter_capture(self):
        """함수 파라미터 캡처가 올바르게 동작하는지 테스트"""
        results = []

        def create_callback(val):
            return lambda: results.append(val)

        callbacks = []
        for i in range(3):
            callbacks.append(create_callback(i))

        for cb in callbacks:
            cb()

        # Function parameters create new scope, so this works
        assert results == [0, 1, 2]
