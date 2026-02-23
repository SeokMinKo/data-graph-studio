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
        """Ordered list of columns currently in the Group Zone."""
        return self._group_columns

    def add_group_column(self, name: str, index: int = -1):
        """
        Add a column to the Group Zone, ignoring duplicates.

        Args:
            name: Column name to add.
            index: Position to insert at. -1 appends to the end.

        Emits:
            group_zone_changed signal.
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
        """
        Remove a column from the Group Zone by name.

        Args:
            name: Column name to remove. No-op if not present.

        Emits:
            group_zone_changed signal.
        """
        self._group_columns = [g for g in self._group_columns if g.name != name]
        self._reorder_groups()
        self.emit("group_zone_changed")

    def reorder_group_columns(self, new_order: List[str]):
        """
        Reorder Group Zone columns to match the given name sequence.

        Args:
            new_order: Column names in the desired order. Names not present in
                the current group columns are silently ignored.

        Emits:
            group_zone_changed signal.
        """
        name_to_col = {g.name: g for g in self._group_columns}
        self._group_columns = [name_to_col[name] for name in new_order if name in name_to_col]
        self._reorder_groups()
        self.emit("group_zone_changed")

    def _reorder_groups(self):
        for i, g in enumerate(self._group_columns):
            g.order = i

    def clear_group_zone(self):
        """
        Remove all columns from the Group Zone.

        Emits:
            group_zone_changed signal.
        """
        self._group_columns.clear()
        self.emit("group_zone_changed")

    # ==================== Value Zone ====================

    @property
    def value_columns(self) -> List[ValueColumn]:
        """Ordered list of columns currently in the Value Zone."""
        return self._value_columns

    def add_value_column(
        self,
        name: str,
        aggregation: AggregationType = AggregationType.SUM,
        index: int = -1
    ):
        """
        Add a column to the Value Zone with automatic color assignment.

        Duplicate column names are allowed when combined with different aggregations.

        Args:
            name: Column name to add.
            aggregation: Aggregation function to apply. Defaults to SUM.
            index: Position to insert at. -1 appends to the end.

        Emits:
            value_zone_changed signal.
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
        """
        Remove a Value Zone column by list index.

        Args:
            index: Zero-based index of the column to remove. No-op if out of range.

        Emits:
            value_zone_changed signal.
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
        """
        Update properties of an existing Value Zone column.

        Only non-None arguments are applied. No-op if the index is out of range.

        Args:
            index: Zero-based index of the column to update.
            aggregation: New aggregation function, or None to leave unchanged.
            color: New hex color string, or None to leave unchanged.
            use_secondary_axis: Assign to secondary Y axis if True, or None to leave unchanged.
            formula: Y-value formula expression (e.g. "y*2"), or None to leave unchanged.

        Emits:
            value_zone_changed signal if any property was updated.
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
        """
        Remove all columns from the Value Zone.

        Emits:
            value_zone_changed signal.
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
        """Return Value Zone columns assigned to the primary (left) Y axis."""
        return [v for v in self._value_columns if not v.use_secondary_axis]

    def get_secondary_values(self) -> List[ValueColumn]:
        """Return Value Zone columns assigned to the secondary (right) Y axis."""
        return [v for v in self._value_columns if v.use_secondary_axis]

    def has_secondary_axis(self) -> bool:
        """Return True if at least one Value Zone column is assigned to the secondary axis."""
        return any(v.use_secondary_axis for v in self._value_columns)

    # ==================== Hover Zone ====================

    @property
    def hover_columns(self) -> List[str]:
        """Ordered list of column names shown in the chart hover tooltip."""
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
        """
        Set the X axis column.

        Args:
            name: Column name to use for the X axis, or None to clear.

        Emits:
            chart_settings_changed signal.
        """
        self._x_column = name
        self.emit("chart_settings_changed")
