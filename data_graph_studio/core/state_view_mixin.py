"""
ViewSettingsMixin - View settings methods extracted from AppState.

All methods operate on shared instance state (self.*) and can call
self.emit(...) because AppState also inherits from Observable.
"""

from typing import Optional, List, Dict, Any, Set
import copy
import time

from .state_types import (
    ChartType,
    ToolMode,
    GridDirection,
    GridViewSettings,
    ChartSettings,
)
from .undo_manager import UndoCommand, UndoActionType


class ViewSettingsMixin:
    """Mixin providing view settings management capabilities to AppState."""

    # ==================== Chart Settings ====================

    @property
    def chart_settings(self) -> ChartSettings:
        """Current chart configuration including type, axes, and style options."""
        return self._chart_settings

    def set_chart_type(self, chart_type: ChartType):
        """
        Change the active chart type and record an undo entry.

        Args:
            chart_type: ChartType enum value to apply.

        Emits:
            chart_settings_changed signal.
        """
        before = copy.deepcopy(self._chart_settings)
        self._chart_settings.chart_type = chart_type
        self.emit("chart_settings_changed")
        after = copy.deepcopy(self._chart_settings)

        def _apply(settings: ChartSettings):
            self._undo_paused += 1
            try:
                self._chart_settings = copy.deepcopy(settings)
                self.emit("chart_settings_changed")
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        if before != after:
            self._push_undo(
                UndoCommand(
                    action_type=UndoActionType.CHART_SETTINGS,
                    description=f"Chart: Type → {chart_type.value}",
                    do=lambda: _apply(after),
                    undo=lambda: _apply(before),
                    timestamp=time.time(),
                )
            )

    def update_chart_settings(self, **kwargs):
        """
        Update one or more chart settings fields and record an undo entry.

        Only fields that exist on ChartSettings and whose values differ from the
        current state are applied. No-op if nothing changed.

        Args:
            **kwargs: ChartSettings attribute names and their new values
                (e.g. line_width=3, y_log_scale=True).

        Emits:
            chart_settings_changed signal if any field changed.
        """
        before = copy.deepcopy(self._chart_settings)
        changed = False
        for key, value in kwargs.items():
            if hasattr(self._chart_settings, key):
                if getattr(self._chart_settings, key) != value:
                    setattr(self._chart_settings, key, value)
                    changed = True
        if not changed:
            return
        self.emit("chart_settings_changed")
        after = copy.deepcopy(self._chart_settings)

        def _apply(settings: ChartSettings):
            self._undo_paused += 1
            try:
                self._chart_settings = copy.deepcopy(settings)
                self.emit("chart_settings_changed")
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        keys = ", ".join(sorted(kwargs.keys()))
        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.CHART_SETTINGS,
                description=f"Chart: Update ({keys})",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    # ==================== Tool Mode ====================

    @property
    def tool_mode(self) -> ToolMode:
        """Currently active chart interaction tool mode."""
        return self._tool_mode

    def set_tool_mode(self, mode: ToolMode):
        """
        Set the active chart tool mode.

        Args:
            mode: ToolMode enum value to activate.

        Emits:
            tool_mode_changed signal.
        """
        self._tool_mode = mode
        self.emit("tool_mode_changed")

    # ==================== Grid View ====================

    @property
    def grid_view_settings(self) -> GridViewSettings:
        """Current grid view configuration (split column, direction, column count, shared axis flags)."""
        return self._chart_settings.grid_view

    def set_grid_view_enabled(self, enabled: bool):
        """Enable or disable grid view mode.

        Input: enabled — bool; True to activate grid view, False to deactivate.
        Output: None
        Emits: grid_view_changed signal if the value changed.
        """
        if self._chart_settings.grid_view.enabled != enabled:
            self._chart_settings.grid_view.enabled = enabled
            self.emit("grid_view_changed")

    def set_grid_view_split_by(self, column: Optional[str]):
        """Set the column used to split data into grid view panels.

        Input: column — str or None; column name to split on, or None to clear.
        Output: None
        Emits: grid_view_changed signal if the value changed.
        """
        if self._chart_settings.grid_view.split_by != column:
            self._chart_settings.grid_view.split_by = column
            self.emit("grid_view_changed")

    def set_grid_view_direction(self, direction: GridDirection):
        """Set the layout direction of grid view panels (horizontal or vertical).

        Input: direction — GridDirection enum value.
        Output: None
        Emits: grid_view_changed signal if the value changed.
        """
        if self._chart_settings.grid_view.direction != direction:
            self._chart_settings.grid_view.direction = direction
            self.emit("grid_view_changed")

    def update_grid_view_settings(self, **kwargs):
        """Update one or more GridViewSettings fields in a single call.

        Only fields that exist on GridViewSettings and whose values differ are applied.
        No-op if nothing changed.

        Input: **kwargs — GridViewSettings attribute names and their new values
            (e.g. columns=3, share_x_axis=True).
        Output: None
        Emits: grid_view_changed signal if any field changed.
        """
        changed = False
        for key, value in kwargs.items():
            if hasattr(self._chart_settings.grid_view, key):
                current = getattr(self._chart_settings.grid_view, key)
                if current != value:
                    setattr(self._chart_settings.grid_view, key, value)
                    changed = True
        if changed:
            self.emit("grid_view_changed")

    # ==================== Layout ====================

    @property
    def layout_ratios(self) -> Dict[str, float]:
        """Height ratios for 'summary', 'graph', and 'table' panels (sum to 1.0)."""
        return self._layout_ratios

    def set_layout_ratio(self, section: str, ratio: float):
        """
        Set the height ratio for a layout section, redistributing the remainder.

        The difference between the old and new ratio is spread evenly across all
        other sections to keep the total at 1.0.

        Args:
            section: Layout section key — one of 'summary', 'graph', or 'table'.
            ratio: New ratio for the section. Ignored if the section key is unknown.
        """
        if section in self._layout_ratios:
            # 비율 조정 (합이 1이 되도록)
            old_ratio = self._layout_ratios[section]
            diff = ratio - old_ratio

            other_sections = [k for k in self._layout_ratios if k != section]
            for other in other_sections:
                self._layout_ratios[other] -= diff / len(other_sections)

            self._layout_ratios[section] = ratio

    # ==================== Column Order ====================

    def set_column_order(self, order: List[str]):
        """
        Set the display order of table columns.

        Args:
            order: Full list of column names in the desired display order.
        """
        self._column_order = order

    def get_column_order(self) -> List[str]:
        """
        Return the current column display order.

        Returns:
            List of column names in display order.
        """
        return self._column_order

    @property
    def hidden_columns(self) -> Set[str]:
        """Read-only access to hidden columns set."""
        return frozenset(self._hidden_columns)

    def hide_column(self, column: str):
        """Hide a specific column."""
        self._hidden_columns.add(column)

    def unhide_column(self, column: str):
        """Unhide a specific column."""
        self._hidden_columns.discard(column)

    def is_column_hidden(self, column: str) -> bool:
        """Check if a column is hidden."""
        return column in self._hidden_columns

    def toggle_column_visibility(self, column: str):
        """
        Toggle whether a column is hidden in the table view.

        Args:
            column: Column name to show if hidden, or hide if visible.
        """
        if column in self._hidden_columns:
            self._hidden_columns.remove(column)
        else:
            self._hidden_columns.add(column)

    def get_visible_columns(self) -> List[str]:
        """
        Return the ordered list of columns that are not hidden.

        Returns:
            Column names from _column_order that are not in _hidden_columns.
        """
        return [c for c in self._column_order if c not in self._hidden_columns]

    # ==================== Summary Update ====================

    def update_summary(self, stats: Dict[str, Any]):
        """Emit a summary_updated signal carrying the given statistics payload.

        Input: stats — Dict[str, Any], computed summary statistics to display in the panel.
        Output: None
        Emits: summary_updated signal with stats as the payload.
        """
        self.emit("summary_updated", stats)
