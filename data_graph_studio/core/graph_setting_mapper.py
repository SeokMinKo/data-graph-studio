"""GraphSettingMapper - AppState <-> GraphSetting conversion utilities."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from .profile import GraphSetting
from .state import AppState, ChartType, ValueColumn, GroupColumn

logger = logging.getLogger(__name__)


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

        # Serialize GroupColumn/ValueColumn objects to dicts for storage
        group_cols = []
        for g in state._group_columns:
            if isinstance(g, GroupColumn):
                group_cols.append({
                    'name': g.name,
                    'selected_values': list(g.selected_values),
                    'order': g.order,
                })
            else:
                group_cols.append(g)

        value_cols = []
        for v in state._value_columns:
            if isinstance(v, ValueColumn):
                value_cols.append({
                    'name': v.name,
                    'aggregation': v.aggregation.value if hasattr(v.aggregation, 'value') else str(v.aggregation),
                    'color': v.color,
                    'use_secondary_axis': v.use_secondary_axis,
                    'order': v.order,
                    'formula': v.formula,
                })
            else:
                value_cols.append(v)

        setting = GraphSetting(
            id=str(uuid.uuid4()),  # Generate new UUID
            name=name,
            dataset_id=dataset_id,  # Pass dataset_id
            chart_type=chart_type,
            x_column=state._x_column,
            group_columns=tuple(group_cols),
            value_columns=tuple(value_cols),
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
        # 직접 내부 속성을 변경하고 마지막에 시그널 한 번만 발행
        try:
            chart_type: Any = setting.chart_type
            if isinstance(chart_type, ChartType):
                resolved_chart_type = chart_type
            else:
                try:
                    # 대소문자 무시하여 변환 (e.g. "Scatter" → "scatter")
                    resolved_chart_type = ChartType(str(chart_type).lower())
                except Exception:
                    resolved_chart_type = state._chart_settings.chart_type
            state._chart_settings.chart_type = resolved_chart_type

            state._x_column = setting.x_column

            # group_columns: dict/str → GroupColumn 변환
            state._group_columns = []
            for g in setting.group_columns:
                if isinstance(g, GroupColumn):
                    state._group_columns.append(g)
                elif isinstance(g, dict):
                    state._group_columns.append(GroupColumn(
                        name=g.get('name', ''),
                        selected_values=set(g.get('selected_values', [])),
                        order=g.get('order', 0),
                    ))
                else:
                    state._group_columns.append(GroupColumn(name=str(g)))

            # value_columns: dict/str → ValueColumn 변환
            from .state import AggregationType
            state._value_columns = []
            for v in setting.value_columns:
                if isinstance(v, ValueColumn):
                    state._value_columns.append(v)
                elif isinstance(v, dict):
                    try:
                        agg = AggregationType(v.get('aggregation', 'sum'))
                    except ValueError:
                        agg = AggregationType.SUM
                    state._value_columns.append(ValueColumn(
                        name=v.get('name', ''),
                        aggregation=agg,
                        color=v.get('color', '#1f77b4'),
                        use_secondary_axis=v.get('use_secondary_axis', False),
                        order=v.get('order', 0),
                        formula=v.get('formula', ''),
                    ))
                else:
                    state._value_columns.append(ValueColumn(name=str(v)))

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
            logger.debug("[DEBUG-CRASH] emitting chart_settings_changed")
            state.chart_settings_changed.emit()
            logger.debug("[DEBUG-CRASH] emitting value_zone_changed")
            state.value_zone_changed.emit()
            logger.debug("[DEBUG-CRASH] emitting group_zone_changed")
            state.group_zone_changed.emit()
            logger.debug("[DEBUG-CRASH] emitting hover_zone_changed")
            state.hover_zone_changed.emit()
            logger.debug("[DEBUG-CRASH] all signals emitted OK")
        except Exception as e:
            logger.error(f"[DEBUG-CRASH] signal emit failed: {e}", exc_info=True)
        finally:
            state.end_batch_update()
