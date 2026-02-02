"""GraphSettingMapper - AppState <-> GraphSetting conversion utilities."""

from __future__ import annotations

import uuid
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

        # Build chart_settings dict from AppState
        chart_settings_dict = {}
        if hasattr(state, '_chart_settings') and state._chart_settings:
            cs = state._chart_settings
            for attr in ['show_legend', 'show_grid', 'show_markers', 'line_width', 
                         'marker_size', 'opacity', 'color_palette']:
                if hasattr(cs, attr):
                    chart_settings_dict[attr] = getattr(cs, attr)

        setting = GraphSetting(
            id=str(uuid.uuid4()),  # Generate new UUID
            name=name,
            dataset_id=dataset_id,  # Pass dataset_id
            chart_type=chart_type,
            x_column=state._x_column,
            group_columns=tuple(state._group_columns),
            value_columns=tuple(state._value_columns),
            hover_columns=tuple(state._hover_columns),
            filters=tuple(state._filters),
            sorts=tuple(state._sorts),
            chart_settings=chart_settings_dict,
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
            
            # Apply chart_settings
            if setting.chart_settings:
                cs = state._chart_settings
                for key, value in setting.chart_settings.items():
                    if hasattr(cs, key):
                        setattr(cs, key, value)
        finally:
            state.end_batch_update()
