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
        if hasattr(state, "_chart_settings") and state._chart_settings:
            cs = state._chart_settings
            for attr in [
                "show_legend",
                "show_grid",
                "show_markers",
                "line_width",
                "marker_size",
                "opacity",
                "color_palette",
                "title",
                "subtitle",
            ]:
                if hasattr(cs, attr):
                    chart_settings_dict[attr] = getattr(cs, attr)

        # Serialize GroupColumn/ValueColumn objects to dicts for storage
        group_cols = []
        for g in state.group_columns:
            if isinstance(g, GroupColumn):
                group_cols.append(
                    {
                        "name": g.name,
                        "selected_values": list(g.selected_values),
                        "order": g.order,
                        "encoding": (
                            g.encoding.value if hasattr(g.encoding, "value") else "both"
                        ),
                    }
                )
            else:
                group_cols.append(g)

        value_cols = []
        for v in state.value_columns:
            if isinstance(v, ValueColumn):
                value_cols.append(
                    {
                        "name": v.name,
                        "aggregation": v.aggregation.value
                        if hasattr(v.aggregation, "value")
                        else str(v.aggregation),
                        "color": v.color,
                        "use_secondary_axis": v.use_secondary_axis,
                        "order": v.order,
                        "formula": v.formula,
                    }
                )
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

        # --- chart_type ---
        try:
            chart_type: Any = setting.chart_type
            if isinstance(chart_type, ChartType):
                resolved_chart_type = chart_type
            else:
                try:
                    resolved_chart_type = ChartType(str(chart_type).lower())
                except Exception:
                    resolved_chart_type = state._chart_settings.chart_type
            state._chart_settings.chart_type = resolved_chart_type
        except Exception as e:
            logger.warning("Failed to apply chart_type: %s", e)

        # --- x_column ---
        try:
            state._x_column = setting.x_column
        except Exception as e:
            logger.warning("Failed to apply x_column: %s", e)

        # --- group_columns ---
        # When group is locked, skip applying profile's group_columns
        # so the current (shared) grouping is preserved across profile switches.
        try:
            if not state.group_locked:
                state.clear_group_zone()
                normalized_groups: list[GroupColumn] = []
                for g in setting.group_columns:
                    if isinstance(g, GroupColumn):
                        normalized_groups.append(g)
                    elif isinstance(g, dict):
                        from .state import GroupEncoding

                        try:
                            enc = GroupEncoding(g.get("encoding", "both"))
                        except ValueError:
                            enc = GroupEncoding.BOTH
                        normalized_groups.append(
                            GroupColumn(
                                name=g.get("name", ""),
                                selected_values=set(g.get("selected_values", [])),
                                order=g.get("order", 0),
                                encoding=enc,
                            )
                        )
                    else:
                        normalized_groups.append(GroupColumn(name=str(g)))

                normalized_groups.sort(key=lambda col: col.order)
                for gc in normalized_groups:
                    state.add_group_column(gc.name)
                    for current in state.group_columns:
                        if current.name == gc.name:
                            current.selected_values = set(gc.selected_values)
                            current.order = gc.order
                            current.encoding = gc.encoding
                            break
            else:
                logger.debug("Group lock ON — skipping group_columns from profile")
        except Exception as e:
            logger.warning("Failed to apply group_columns: %s", e)

        # --- value_columns ---
        try:
            from .state import AggregationType

            state.clear_value_zone()
            normalized_values: list[ValueColumn] = []
            for v in setting.value_columns:
                if isinstance(v, ValueColumn):
                    normalized_values.append(v)
                elif isinstance(v, dict):
                    try:
                        agg = AggregationType(v.get("aggregation", "sum"))
                    except ValueError:
                        agg = AggregationType.SUM
                    normalized_values.append(
                        ValueColumn(
                            name=v.get("name", ""),
                            aggregation=agg,
                            color=v.get("color", "#1f77b4"),
                            use_secondary_axis=v.get("use_secondary_axis", False),
                            order=v.get("order", 0),
                            formula=v.get("formula", ""),
                        )
                    )
                else:
                    normalized_values.append(ValueColumn(name=str(v)))

            normalized_values.sort(key=lambda col: col.order)
            for vc in normalized_values:
                state.add_value_column(vc.name, aggregation=vc.aggregation)
                idx = len(state.value_columns) - 1
                state.update_value_column(
                    idx,
                    color=vc.color,
                    use_secondary_axis=vc.use_secondary_axis,
                    formula=vc.formula,
                )
        except Exception as e:
            logger.warning("Failed to apply value_columns: %s", e)

        # --- hover/filters/sorts ---
        try:
            state._hover_columns = [str(h) for h in setting.hover_columns]
        except Exception as e:
            logger.warning("Failed to apply hover_columns: %s", e)

        try:
            state._filters = list(setting.filters)
        except Exception as e:
            logger.warning("Failed to apply filters: %s", e)

        try:
            state._sorts = list(setting.sorts)
        except Exception as e:
            logger.warning("Failed to apply sorts: %s", e)

        # --- chart_settings ---
        try:
            cs = state._chart_settings
            # Reset key fields first so one profile's title/subtitle does not leak
            # into another profile that leaves them unset.
            defaults = {
                "show_legend": True,
                "show_grid": True,
                "show_markers": False,
                "line_width": 2,
                "marker_size": 6,
                "opacity": 1.0,
                "color_palette": "default",
                "title": None,
                "subtitle": None,
            }
            for key, value in defaults.items():
                if hasattr(cs, key):
                    setattr(cs, key, value)

            if setting.chart_settings:
                for key, value in setting.chart_settings.items():
                    if hasattr(cs, key):
                        try:
                            setattr(cs, key, value)
                        except Exception as e:
                            logger.warning(
                                "Failed to apply chart_setting '%s': %s", key, e
                            )
        except Exception as e:
            logger.warning("Failed to apply chart_settings: %s", e)

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
