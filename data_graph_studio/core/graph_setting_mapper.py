"""GraphSettingMapper - AppState <-> GraphSetting conversion utilities."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from .exceptions import ValidationError
from .profile import GraphSetting
from .state import AppState, ChartType, ValueColumn, GroupColumn

logger = logging.getLogger(__name__)


class GraphSettingMapper:
    @staticmethod
    def from_app_state(state: AppState, name: str, dataset_id: str) -> GraphSetting:
        """Create a GraphSetting snapshot from the current AppState.

        Input: state — AppState, source of chart type, columns, filters, sorts, and settings
               name — str, display name for the saved setting
               dataset_id — str, dataset ID to associate with the setting
        Output: GraphSetting — fully populated setting with a new UUID; group/value columns
            are serialized to dicts for storage
        """
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
        for g in state.group_columns:
            if isinstance(g, GroupColumn):
                group_cols.append({
                    'name': g.name,
                    'selected_values': list(g.selected_values),
                    'order': g.order,
                })
            else:
                group_cols.append(g)

        value_cols = []
        for v in state.value_columns:
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
    def _resolve_chart_type(chart_type: Any, state: AppState) -> ChartType:
        """Coerce chart_type to ChartType, falling back to current state value."""
        if isinstance(chart_type, ChartType):
            return chart_type
        try:
            return ChartType(str(chart_type).lower())
        except (TypeError, AttributeError, ValueError, KeyError):
            logger.debug("graph_setting_mapper.resolve_chart_type.coerce_failed", exc_info=True)
            return state._chart_settings.chart_type

    @staticmethod
    def _apply_group_columns(setting: GraphSetting, state: AppState) -> None:
        """Normalize and apply group_columns from setting to state."""
        state.clear_group_zone()
        normalized: list[GroupColumn] = []
        for g in setting.group_columns:
            if isinstance(g, GroupColumn):
                normalized.append(g)
            elif isinstance(g, dict):
                normalized.append(GroupColumn(
                    name=g.get('name', ''),
                    selected_values=set(g.get('selected_values', [])),
                    order=g.get('order', 0),
                ))
            else:
                normalized.append(GroupColumn(name=str(g)))
        normalized.sort(key=lambda col: col.order)
        for gc in normalized:
            state.add_group_column(gc.name)
            for current in state.group_columns:
                if current.name == gc.name:
                    current.selected_values = set(gc.selected_values)
                    current.order = gc.order
                    break

    @staticmethod
    def _apply_value_columns(setting: GraphSetting, state: AppState) -> None:
        """Normalize and apply value_columns from setting to state."""
        from .state import AggregationType
        state.clear_value_zone()
        normalized: list[ValueColumn] = []
        for v in setting.value_columns:
            if isinstance(v, ValueColumn):
                normalized.append(v)
            elif isinstance(v, dict):
                try:
                    agg = AggregationType(v.get('aggregation', 'sum'))
                except ValueError:
                    agg = AggregationType.SUM
                normalized.append(ValueColumn(
                    name=v.get('name', ''),
                    aggregation=agg,
                    color=v.get('color', '#1f77b4'),
                    use_secondary_axis=v.get('use_secondary_axis', False),
                    order=v.get('order', 0),
                    formula=v.get('formula', ''),
                ))
            else:
                normalized.append(ValueColumn(name=str(v)))
        normalized.sort(key=lambda col: col.order)
        for vc in normalized:
            state.add_value_column(vc.name, aggregation=vc.aggregation)
            idx = len(state.value_columns) - 1
            state.update_value_column(
                idx, color=vc.color,
                use_secondary_axis=vc.use_secondary_axis,
                formula=vc.formula,
            )

    @staticmethod
    def to_app_state(setting: GraphSetting, state: AppState) -> None:
        """Apply a GraphSetting to AppState, restoring all chart configuration.

        Input: setting — GraphSetting, the snapshot to restore
               state — AppState, the target whose chart type, columns, filters, and sorts are overwritten
        Output: None
        Raises: ValidationError — when any attribute from setting cannot be applied to state
        Invariants: all signals (chart_settings_changed, value_zone_changed, etc.) are emitted
            inside a batch update; state is unchanged on ValidationError
        """
        state.begin_batch_update()
        try:
            state._chart_settings.chart_type = GraphSettingMapper._resolve_chart_type(
                setting.chart_type, state
            )
            state._x_column = setting.x_column
            GraphSettingMapper._apply_group_columns(setting, state)
            GraphSettingMapper._apply_value_columns(setting, state)
            state._hover_columns = [str(h) for h in setting.hover_columns]
            state._filters = list(setting.filters)
            state._sorts = list(setting.sorts)
            if setting.chart_settings:
                cs = state._chart_settings
                for key, value in setting.chart_settings.items():
                    if hasattr(cs, key):
                        setattr(cs, key, value)
        except (AttributeError, TypeError, KeyError, ValueError) as e:
            raise ValidationError(
                f"GraphSetting을 AppState에 적용하는 데 실패했습니다: {e}",
                operation="to_app_state",
                context={"setting_name": getattr(setting, "name", "")},
            ) from e
        try:
            logger.warning("graph_setting_mapper.event", extra={"signal": "chart_settings_changed"})
            state.chart_settings_changed.emit()
            logger.warning("graph_setting_mapper.event", extra={"signal": "value_zone_changed"})
            state.value_zone_changed.emit()
            logger.warning("graph_setting_mapper.event", extra={"signal": "group_zone_changed"})
            state.group_zone_changed.emit()
            logger.warning("graph_setting_mapper.event", extra={"signal": "hover_zone_changed"})
            state.hover_zone_changed.emit()
            logger.warning("graph_setting_mapper.event", extra={"signal": "all_signals_emitted_ok"})
        except (RuntimeError, AttributeError, TypeError) as e:
            logger.error("graph_setting_mapper.signal_emit_failed", extra={"error": e}, exc_info=True)
        finally:
            state.end_batch_update()
