"""GraphSettingMapper - AppState <-> GraphSetting conversion utilities."""

from __future__ import annotations

import uuid
from typing import Any

from .profile import GraphSetting
from .state import AppState, ChartType, ValueColumn, GroupColumn


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
        # 직접 내부 속성을 변경하고 마지막에 시그널 한 번만 발행
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

            # group_columns: 문자열이면 GroupColumn으로 변환
            state._group_columns = [
                g if isinstance(g, GroupColumn) else GroupColumn(name=str(g))
                for g in setting.group_columns
            ]

            # value_columns: 문자열이면 ValueColumn으로 변환
            state._value_columns = [
                v if isinstance(v, ValueColumn) else ValueColumn(name=str(v))
                for v in setting.value_columns
            ]

            state._hover_columns = [str(h) for h in setting.hover_columns]
            state._filters = list(setting.filters)
            state._sorts = list(setting.sorts)

            # Apply chart_settings
            if setting.chart_settings:
                cs = state._chart_settings
                for key, value in setting.chart_settings.items():
                    if hasattr(cs, key):
                        setattr(cs, key, value)
        except Exception:
            pass

        # 변경 완료 후 시그널 발행 (UI 갱신 트리거)
        try:
            state.chart_settings_changed.emit()
            state.value_zone_changed.emit()
            state.group_zone_changed.emit()
            state.hover_zone_changed.emit()
        except Exception:
            pass
