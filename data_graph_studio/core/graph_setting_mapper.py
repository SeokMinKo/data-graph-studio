"""GraphSettingMapper - AppState <-> GraphSetting conversion utilities."""

from __future__ import annotations

from typing import Any

from .profile import GraphSetting
from .state import AppState, ChartType


class GraphSettingMapper:
    @staticmethod
    def from_app_state(state: AppState, name: str, dataset_id: str) -> GraphSetting:
        """Create GraphSetting from current AppState"""
        chart_type = state._chart_settings.chart_type
        if isinstance(chart_type, ChartType):
            chart_type = chart_type.value

        setting = GraphSetting(
            id=dataset_id,
            name=name,
            chart_type=chart_type,
            x_column=state._x_column,
            group_columns=tuple(state._group_columns),
            value_columns=tuple(state._value_columns),
            hover_columns=list(state._hover_columns),
            filters=list(state._filters),
            sorts=list(state._sorts),
        )
        return setting

    @staticmethod
    def to_app_state(setting: GraphSetting, state: AppState) -> None:
        """Apply GraphSetting to AppState with signal batching"""
        state.begin_batch_update()
        try:
            chart_type: Any = setting.chart_type
            if isinstance(chart_type, ChartType):
                resolved_chart_type = chart_type
            else:
                try:
                    resolved_chart_type = ChartType(chart_type)
                except Exception:
                    resolved_chart_type = state._chart_settings.chart_type
            state._chart_settings.chart_type = resolved_chart_type

            state._x_column = setting.x_column
            state._group_columns = list(setting.group_columns)
            state._value_columns = list(setting.value_columns)
            state._hover_columns = list(setting.hover_columns)
            state._filters = list(setting.filters)
            state._sorts = list(setting.sorts)
        finally:
            state.end_batch_update()
