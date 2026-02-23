"""
ColumnZoneMixin - Column zone management methods extracted from AppState.

All methods operate on shared instance state (self.*) and can call
self.emit(...) because AppState also inherits from Observable.
"""

from typing import Optional, List

from .state_types import (
    AggregationType,
    GroupColumn,
    ValueColumn,
)


class ColumnZoneMixin:
    """Mixin providing column zone management capabilities to AppState."""

    # ==================== Group Zone ====================

    @property
    def group_columns(self) -> List[GroupColumn]:
        """Ordered list of columns currently in the Group Zone.

        Output: List[GroupColumn] — live reference; order matches display order
        """
        return self._group_columns

    def add_group_column(self, name: str, index: int = -1):
        """Add a column to the Group Zone, ignoring duplicates.

        Input: name — str, column name to add; index — int, insertion position (-1 appends).
        Output: None
        Invariants: no duplicate names in _group_columns; order values are contiguous after call.
        Emits: group_zone_changed.
        """
        # 중복 방지
        if any(g.name == name for g in self._group_columns):
            return

        col = GroupColumn(name=name, order=len(self._group_columns))
        if index < 0:
            self._group_columns.append(col)
        else:
            self._group_columns.insert(index, col)
            self._reorder_groups()

        self.emit("group_zone_changed")

    def remove_group_column(self, name: str):
        """Remove a column from the Group Zone by name.

        Input: name — str, column name to remove; no-op if not present.
        Output: None
        Invariants: after call no GroupColumn with name==name remains; order values re-indexed.
        Emits: group_zone_changed.
        """
        self._group_columns = [g for g in self._group_columns if g.name != name]
        self._reorder_groups()
        self.emit("group_zone_changed")

    def reorder_group_columns(self, new_order: List[str]):
        """Reorder Group Zone columns to match the given name sequence.

        Input: new_order — List[str], column names in the desired order; names absent
               from the current group columns are silently ignored.
        Output: None
        Invariants: _group_columns contains only names present in both new_order and the
                    prior group zone; order values are re-indexed to be contiguous.
        Emits: group_zone_changed.
        """
        name_to_col = {g.name: g for g in self._group_columns}
        self._group_columns = [name_to_col[name] for name in new_order if name in name_to_col]
        self._reorder_groups()
        self.emit("group_zone_changed")

    def _reorder_groups(self):
        for i, g in enumerate(self._group_columns):
            g.order = i

    def clear_group_zone(self):
        """Remove all columns from the Group Zone.

        Output: None
        Invariants: _group_columns is empty after this call.
        Emits: group_zone_changed.
        """
        self._group_columns.clear()
        self.emit("group_zone_changed")

    # ==================== Value Zone ====================

    @property
    def value_columns(self) -> List[ValueColumn]:
        """Ordered list of columns currently in the Value Zone.

        Output: List[ValueColumn] — live reference; order matches display order
        """
        return self._value_columns

    def add_value_column(
        self,
        name: str,
        aggregation: AggregationType = AggregationType.SUM,
        index: int = -1
    ):
        """Add a column to the Value Zone with automatic color assignment.

        Duplicate column names are allowed when paired with different aggregations.

        Input: name — str, column name to add; aggregation — AggregationType (default SUM);
               index — int, insertion position (-1 appends to end).
        Output: None
        Invariants: color is auto-assigned from a 10-color palette cycling by position;
                    order values are contiguous after insertion.
        Emits: value_zone_changed.
        """
        # 중복 허용 (같은 컬럼 다른 집계)
        col = ValueColumn(
            name=name,
            aggregation=aggregation,
            order=len(self._value_columns)
        )

        # 색상 자동 할당
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
        col.color = colors[len(self._value_columns) % len(colors)]

        if index < 0:
            self._value_columns.append(col)
        else:
            self._value_columns.insert(index, col)
            self._reorder_values()

        self.emit("value_zone_changed")

    def remove_value_column(self, index: int):
        """Remove a Value Zone column by zero-based list index.

        Input: index — int, zero-based position to remove; no-op if out of range.
        Output: None
        Invariants: order values are re-indexed to be contiguous after removal.
        Emits: value_zone_changed (only when a column was actually removed).
        """
        if 0 <= index < len(self._value_columns):
            self._value_columns.pop(index)
            self._reorder_values()
            self.emit("value_zone_changed")

    def update_value_column(
        self,
        index: int,
        aggregation: Optional[AggregationType] = None,
        color: Optional[str] = None,
        use_secondary_axis: Optional[bool] = None,
        formula: Optional[str] = None
    ):
        """Update properties of an existing Value Zone column by index.

        Only non-None arguments are applied. No-op if the index is out of range.

        Input: index — int, zero-based column position; aggregation — AggregationType or None;
               color — hex color string or None; use_secondary_axis — bool or None;
               formula — expression string or None.
        Output: None
        Emits: value_zone_changed if any property was updated and index is in range.
        """
        if 0 <= index < len(self._value_columns):
            if aggregation is not None:
                self._value_columns[index].aggregation = aggregation
            if color is not None:
                self._value_columns[index].color = color
            if use_secondary_axis is not None:
                self._value_columns[index].use_secondary_axis = use_secondary_axis
            if formula is not None:
                self._value_columns[index].formula = formula
            self.emit("value_zone_changed")

    def _reorder_values(self):
        for i, v in enumerate(self._value_columns):
            v.order = i

    def clear_value_zone(self):
        """Remove all columns from the Value Zone.

        Output: None
        Invariants: _value_columns is empty after this call.
        Emits: value_zone_changed.
        """
        self._value_columns.clear()
        self.emit("value_zone_changed")

    def remove_value_column_by_name(self, name: str):
        """Remove all Value Zone columns whose name matches the given string.

        Input: name — str, column name to remove; all matching entries are dropped.
        Output: None
        Invariants: no ValueColumn with name==name remains in self._value_columns.
        Emits: value_zone_changed signal.
        """
        self._value_columns = [v for v in self._value_columns if v.name != name]
        self._reorder_values()
        self.emit("value_zone_changed")

    def get_primary_values(self) -> List[ValueColumn]:
        """Return Value Zone columns assigned to the primary (left) Y axis.

        Output: List[ValueColumn] — filtered subset of _value_columns where use_secondary_axis is False
        """
        return [v for v in self._value_columns if not v.use_secondary_axis]

    def get_secondary_values(self) -> List[ValueColumn]:
        """Return Value Zone columns assigned to the secondary (right) Y axis.

        Output: List[ValueColumn] — filtered subset of _value_columns where use_secondary_axis is True
        """
        return [v for v in self._value_columns if v.use_secondary_axis]

    def has_secondary_axis(self) -> bool:
        """Return True if at least one Value Zone column is assigned to the secondary axis.

        Output: bool — True when any ValueColumn has use_secondary_axis == True
        """
        return any(v.use_secondary_axis for v in self._value_columns)

    # ==================== Hover Zone ====================

    @property
    def hover_columns(self) -> List[str]:
        """Ordered list of column names shown in the chart hover tooltip.

        Output: List[str] — live reference; names appear in tooltip in this order
        """
        return self._hover_columns

    def add_hover_column(self, name: str):
        """Add a column to the hover tooltip, ignoring duplicates.

        Input: name — str, column name to add.
        Output: None
        Emits: hover_zone_changed signal if name was not already present.
        """
        if name not in self._hover_columns:
            self._hover_columns.append(name)
            self.emit("hover_zone_changed")

    def remove_hover_column(self, name: str):
        """Remove a column from the hover tooltip by name.

        Input: name — str, column name to remove. No-op if not present.
        Output: None
        Emits: hover_zone_changed signal if name was present.
        """
        if name in self._hover_columns:
            self._hover_columns.remove(name)
            self.emit("hover_zone_changed")

    def clear_hover_columns(self):
        """Remove all columns from the hover tooltip zone.

        Output: None
        Emits: hover_zone_changed signal.
        """
        self._hover_columns.clear()
        self.emit("hover_zone_changed")

    # ==================== X Column ====================

    @property
    def x_column(self) -> Optional[str]:
        """Column name used as the X axis, or None if not set."""
        return self._x_column

    def set_x_column(self, name: Optional[str]):
        """Set the X axis column.

        Input: name — str, column name for the X axis, or None to clear.
        Output: None
        Invariants: self.x_column == name after this call.
        Emits: chart_settings_changed.
        """
        self._x_column = name
        self.emit("chart_settings_changed")
