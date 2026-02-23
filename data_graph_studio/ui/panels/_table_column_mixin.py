"""Column operations behavior for TablePanel."""
from __future__ import annotations

import logging
import polars as pl


from PySide6.QtWidgets import QMessageBox, QDialog

from .conditional_formatting import ConditionalFormatDialog


logger = logging.getLogger(__name__)

class _TableColumnMixin:
    """Mixin: column type conversion, freeze, visibility, and conditional formatting for TablePanel.

    Requires self to be a TablePanel instance with:
      self.engine              - DataEngine (is_loaded, df, drop_column, cast_column)
      self.state               - AppState (x_column, set_x_column, remove_group_column,
                                 remove_value_column_by_name, hover_columns, remove_hover_column,
                                 unhide_column, get_column_order, set_column_order,
                                 toggle_column_visibility, hidden_columns, add_filter,
                                 add_group_column, add_value_column, add_hover_column)
      self.graph_panel         - graph panel with refresh()
      self.table_model         - PolarsTableModel (set_conditional_format, remove_conditional_format)
      self.hidden_bar          - HiddenColumnsBar
      self._frozen_columns     - List[str]
      self._update_table_model() - method
      self._update_hidden_bar()  - method (defined here)
    """

    def _on_column_order_changed(self, order):
        """Update column order in state and refresh model"""
        if not order:
            return
        self.state.set_column_order(order)
        # Refresh table to apply new order
        self._update_table_model(self.engine.df if self.engine.is_loaded else None)

    # ==================== Filter & Column Handlers ====================

    def _on_exclude_value(self, column: str, filter_info: tuple):
        """Handle exclude value from cell context menu"""
        operator, value = filter_info
        self.state.add_filter(column, operator, value)

    def _on_hide_column(self, column: str):
        """Handle hide column from header context menu"""
        self.state.toggle_column_visibility(column)
        self._update_hidden_bar()
        self._update_table_model()

    def _on_exclude_column(self, column: str):
        """Handle exclude (drop) column from data"""
        if not self.engine.is_loaded or not column:
            return
        # Confirm destructive action
        reply = QMessageBox.question(
            self, "Exclude Column",
            f"Remove column '{column}' from the active dataset?\n\nThis cannot be undone (reload to restore).",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            # Drop from active dataset df
            df = self.engine.df
            if df is None or column not in df.columns:
                return
            self.engine.drop_column(column)
            # Clean state references
            if self.state.x_column == column:
                self.state.set_x_column(None)
            # Remove from groups/values/hover
            self.state.remove_group_column(column)
            self.state.remove_value_column_by_name(column)
            if column in self.state.hover_columns:
                self.state.remove_hover_column(column)
            # Hidden/column order cleanup
            self.state.unhide_column(column)
            if column in self.state.get_column_order():
                self.state.set_column_order([c for c in self.state.get_column_order() if c != column])

            # Refresh UI
            self._update_table_model(self.engine.df)
            self.graph_panel.refresh() if hasattr(self, 'graph_panel') else None
        except Exception as e:
            logger.exception("table_column_mixin.exclude_column.error")
            QMessageBox.warning(self, "Exclude Column", f"Failed to exclude column: {e}")

    def _on_column_action(self, action: str):
        """Handle column actions from header context menu (Set as X/Y/Group/Hover)"""
        feedback = ""
        if action.startswith("X:"):
            column = action[2:]
            self.state.set_x_column(column)
            feedback = f"Set '{column}' as X-Axis"
        elif action.startswith("G:"):
            column = action[2:]
            self.state.add_group_column(column)
            feedback = f"Added '{column}' to Group By"
        elif action.startswith("V:"):
            column = action[2:]
            self.state.add_value_column(column)
            feedback = f"Added '{column}' to Y-Axis"
        elif action.startswith("H:"):
            column = action[2:]
            self.state.add_hover_column(column)
            feedback = f"Added '{column}' to Hover"

        # Show statusbar feedback
        if feedback:
            main_window = self.window()
            if main_window and hasattr(main_window, 'statusbar'):
                main_window.statusbar.showMessage(feedback, 3000)

    def _on_show_column(self, column: str):
        """Show a hidden column"""
        self.state.unhide_column(column)
        self._update_hidden_bar()
        self._update_table_model()

    def _on_show_all_columns(self):
        """Show all hidden columns"""
        hidden = list(self.state.hidden_columns)
        for col in hidden:
            self.state.unhide_column(col)
        self._update_hidden_bar()
        self._update_table_model()

    def _update_hidden_bar(self):
        """Update hidden columns bar"""
        hidden = list(self.state.hidden_columns)
        self.hidden_bar.update_hidden_columns(hidden)

    # ==================== F5: Column Type Conversion ====================

    def _on_column_type_convert(self, column_name: str, target_type: str):
        """Handle column type conversion from header menu."""
        if not self.engine.is_loaded:
            return
        dtype_map = {
            "Int64": pl.Int64,
            "Float64": pl.Float64,
            "String": pl.Utf8,
            "Date": pl.Date,
            "Boolean": pl.Boolean,
        }
        target = dtype_map.get(target_type)
        if target is None:
            return
        try:
            success = self.engine.cast_column(column_name, target)
            if success:
                self._update_table_model(self.engine.df)
                main_window = self.window()
                if main_window and hasattr(main_window, 'statusBar'):
                    main_window.statusBar().showMessage(
                        f"Converted '{column_name}' to {target_type}", 3000
                    )
            else:
                QMessageBox.warning(self, "Type Conversion", f"Failed to convert '{column_name}' to {target_type}")
        except Exception as e:
            logger.exception("table_column_mixin.convert_column_type.error")
            QMessageBox.warning(self, "Type Conversion", f"Error: {e}")

    # ==================== F3: Conditional Formatting ====================

    def _on_conditional_format_requested(self, column_name: str):
        """Show conditional formatting dialog for a column."""
        dialog = ConditionalFormatDialog(column_name, self)
        if dialog.exec() == QDialog.Accepted:
            fmt = dialog.get_format()
            if fmt:
                self.table_model.set_conditional_format(column_name, fmt)
            else:
                self.table_model.remove_conditional_format(column_name)

    # ==================== F7: Freeze Columns ====================

    def _on_freeze_column(self, column_name: str):
        """Freeze a column (pin to left)."""
        if column_name not in self._frozen_columns:
            self._frozen_columns.append(column_name)
            self._update_table_model()

    def _on_unfreeze_column(self, column_name: str):
        """Unfreeze a column."""
        if column_name in self._frozen_columns:
            self._frozen_columns.remove(column_name)
            self._update_table_model()
