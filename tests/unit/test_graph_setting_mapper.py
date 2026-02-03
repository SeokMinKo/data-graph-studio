"""
Tests for GraphSettingMapper
"""

from unittest.mock import MagicMock

import pytest

from data_graph_studio.core.graph_setting_mapper import GraphSettingMapper
from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.state import AppState, ChartType, GroupColumn, ValueColumn


@pytest.fixture
def state(qtbot):
    return AppState()


def test_from_app_state_creates_setting(state):
    state._chart_settings.chart_type = ChartType.BAR
    state._x_column = "x"
    state._group_columns = [{"name": "group"}]
    state._value_columns = [{"name": "value"}]
    state._hover_columns = ["hover"]
    state._filters = [{"column": "col", "operator": "eq", "value": 1}]
    state._sorts = [{"column": "col", "descending": True}]

    setting = GraphSettingMapper.from_app_state(state, name="My Setting", dataset_id="ds1")

    assert setting.dataset_id == "ds1"
    assert setting.name == "My Setting"
    assert setting.chart_type == "bar"
    assert setting.x_column == "x"
    assert setting.group_columns == ({"name": "group"},)
    assert setting.value_columns == ({"name": "value"},)
    assert setting.hover_columns == ("hover",)
    assert setting.filters == ({"column": "col", "operator": "eq", "value": 1},)
    assert setting.sorts == ({"column": "col", "descending": True},)


def test_to_app_state_applies_setting(state):
    state.begin_batch_update = MagicMock()
    state.end_batch_update = MagicMock()

    setting = GraphSetting(
        id="setting-1",
        name="Setting",
        dataset_id="ds1",
        chart_type="line",
        x_column="x",
        group_columns=({"name": "g1"},),
        value_columns=({"name": "v1"},),
        hover_columns=("h1",),
        filters=({"column": "f1", "operator": "eq", "value": 10},),
        sorts=({"column": "s1", "descending": False},),
    )

    GraphSettingMapper.to_app_state(setting, state)

    assert state._chart_settings.chart_type == ChartType.LINE
    assert state._x_column == "x"
    # Mapper converts dicts to GroupColumn/ValueColumn objects
    assert len(state._group_columns) == 1
    assert state._group_columns[0].name == "g1"
    assert len(state._value_columns) == 1
    assert state._value_columns[0].name == "v1"
    assert state._hover_columns == ["h1"]
    assert state._filters == [{"column": "f1", "operator": "eq", "value": 10}]
    assert state._sorts == [{"column": "s1", "descending": False}]


def test_round_trip_preserves_data(state):
    state._chart_settings.chart_type = ChartType.SCATTER
    state._x_column = "x"
    state._group_columns = [{"name": "g1"}, {"name": "g2"}]
    state._value_columns = [{"name": "v1"}, {"name": "v2"}]
    state._hover_columns = ["h1", "h2"]
    state._filters = [{"column": "f1", "operator": "gt", "value": 5}]
    state._sorts = [{"column": "s1", "descending": True}]

    setting = GraphSettingMapper.from_app_state(state, name="Round Trip", dataset_id="ds2")

    new_state = AppState()
    new_state.begin_batch_update = MagicMock()
    new_state.end_batch_update = MagicMock()

    GraphSettingMapper.to_app_state(setting, new_state)

    assert new_state._chart_settings.chart_type == ChartType.SCATTER
    assert new_state._x_column == "x"
    # After round trip, group/value columns become GroupColumn/ValueColumn objects
    assert len(new_state._group_columns) == 2
    assert new_state._group_columns[0].name == "g1"
    assert new_state._group_columns[1].name == "g2"
    assert len(new_state._value_columns) == 2
    assert new_state._value_columns[0].name == "v1"
    assert new_state._value_columns[1].name == "v2"
    assert new_state._hover_columns == ["h1", "h2"]
    assert new_state._filters == [{"column": "f1", "operator": "gt", "value": 5}]
    assert new_state._sorts == [{"column": "s1", "descending": True}]


def test_signal_batching(state):
    order = []

    def begin():
        order.append("begin")

    def end():
        order.append("end")

    state.begin_batch_update = begin
    state.end_batch_update = end

    setting = GraphSetting(
        id="setting-2",
        name="Setting",
        dataset_id="ds1",
        chart_type="bar",
        x_column="x",
        group_columns=(),
        value_columns=(),
        hover_columns=(),
        filters=(),
        sorts=(),
    )

    GraphSettingMapper.to_app_state(setting, state)

    assert order == ["begin", "end"]
