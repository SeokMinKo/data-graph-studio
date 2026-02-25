"""Column operations behavior for TablePanel."""
from __future__ import annotations

import logging
import re
import time

import polars as pl

from PySide6.QtWidgets import QMessageBox, QDialog, QInputDialog

from ...core.undo_manager import UndoActionType, UndoCommand
from ..dialogs.split_column_dialog import SplitColumnDialog
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


    def _on_rename_column_requested(self, old_name: str):
        """Rename a column from header double-click request."""
        if not self.engine.is_loaded:
            return

        df = self.engine.df
        if df is None or old_name not in df.columns:
            QMessageBox.warning(self, "Rename Column", f"Column '{old_name}' was not found.")
            return

        new_name, ok = QInputDialog.getText(self, "Rename Column", "New column name:", text=old_name)
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Rename Column", "Column name cannot be empty.")
            return

        if new_name == old_name:
            QMessageBox.information(self, "Rename Column", "New name is the same as the current name.")
            return

        if new_name in df.columns:
            QMessageBox.warning(self, "Rename Column", f"Column '{new_name}' already exists.")
            return

        try:
            new_df = df.rename({old_name: new_name})
            self.engine.update_dataframe(new_df)

            if self.state.x_column == old_name:
                self.state.set_x_column(new_name)

            group_changed = False
            for group_col in self.state.group_columns:
                if group_col.name == old_name:
                    group_col.name = new_name
                    group_changed = True
            if group_changed:
                self.state.emit("group_zone_changed")

            value_changed = False
            for value_col in self.state.value_columns:
                if value_col.name == old_name:
                    value_col.name = new_name
                    value_changed = True
            if value_changed:
                self.state.emit("value_zone_changed")

            hover_columns = self.state.hover_columns
            if old_name in hover_columns:
                for idx, col_name in enumerate(hover_columns):
                    if col_name == old_name:
                        hover_columns[idx] = new_name
                self.state.emit("hover_zone_changed")

            if old_name in self.state.hidden_columns:
                self.state.unhide_column(old_name)
                self.state.hide_column(new_name)

            order = self.state.get_column_order()
            if old_name in order:
                self.state.set_column_order([new_name if c == old_name else c for c in order])

            self._update_hidden_bar()
            self._update_table_model(new_df)

            if hasattr(self, "graph_panel"):
                try:
                    if hasattr(self.graph_panel, "set_columns"):
                        self.graph_panel.set_columns(new_df.columns)
                    self.graph_panel.refresh()
                except Exception:
                    logger.exception("table_column_mixin.rename_column.graph_refresh.error")

            main_window = self.window()
            if main_window and hasattr(main_window, 'statusBar'):
                main_window.statusBar().showMessage(
                    f"Renamed column '{old_name}' to '{new_name}'", 3000
                )
            elif main_window and hasattr(main_window, 'statusbar'):
                main_window.statusbar.showMessage(
                    f"Renamed column '{old_name}' to '{new_name}'", 3000
                )
        except Exception as e:
            logger.exception("table_column_mixin.rename_column.error")
            QMessageBox.warning(self, "Rename Column", f"Failed to rename column: {e}")

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


    # ==================== Split Column (Regex) ====================

    def _on_split_column_requested(self, column_name: str):
        """Split a string column into new columns using regex capture groups."""
        if not self.engine.is_loaded:
            QMessageBox.information(self, "Split Column", "No data loaded.")
            return

        df = self.engine.df
        if df is None or column_name not in df.columns:
            QMessageBox.warning(self, "Split Column", f"Column '{column_name}' was not found.")
            return

        sample_values = (
            df.select(pl.col(column_name).cast(pl.Utf8).head(5).alias(column_name))
            .to_series(0)
            .to_list()
        )

        dialog = SplitColumnDialog(
            source_column=column_name,
            sample_values=sample_values,
            existing_columns=df.columns,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        try:
            payload = dialog.get_payload()
            pattern = str(payload["pattern"])
            mapping = payload["mapping"]

            compiled = re.compile(pattern)
            if compiled.groups <= 0:
                QMessageBox.warning(self, "Split Column", "Pattern must include at least one capture group.")
                return

            if not mapping:
                QMessageBox.warning(self, "Split Column", "No output columns were configured.")
                return

            target_names = list(mapping.values())
            if len(set(target_names)) != len(target_names):
                QMessageBox.warning(self, "Split Column", "Output column names must be unique.")
                return

            collisions = [name for name in target_names if name in df.columns and name != column_name]
            if collisions:
                QMessageBox.warning(
                    self,
                    "Split Column",
                    "Target column name already exists: " + ", ".join(collisions),
                )
                return

            new_df = self._build_split_dataframe(df, column_name, pattern, mapping)
        except re.error as e:
            QMessageBox.warning(self, "Split Column", f"Invalid regex pattern:\n{e}")
            return
        except ValueError as e:
            QMessageBox.warning(self, "Split Column", str(e))
            return
        except Exception as e:
            logger.exception("table_column_mixin.split_column.error")
            QMessageBox.warning(self, "Split Column", f"Failed to split column:\n{e}")
            return

        self._apply_split_with_undo(before_df=df, after_df=new_df, source_column=column_name, target_names=target_names)

    def _build_split_dataframe(self, df: pl.DataFrame, column_name: str, pattern: str, mapping: dict[int, str]) -> pl.DataFrame:
        if not mapping:
            raise ValueError("Pattern must include at least one capture group.")

        compiled = re.compile(pattern)
        source_values = df.select(pl.col(column_name).cast(pl.Utf8)).to_series(0).to_list()

        new_columns = []
        for group_index, new_name in mapping.items():
            idx = int(group_index)
            extracted = []
            for value in source_values:
                if value is None:
                    extracted.append(None)
                    continue
                match = compiled.search(value)
                extracted.append(match.group(idx) if match else None)
            new_columns.append(pl.Series(new_name, extracted))

        return df.with_columns(new_columns)

    def _apply_split_with_undo(self, before_df: pl.DataFrame, after_df: pl.DataFrame, source_column: str, target_names: list[str]):
        def _apply(df: pl.DataFrame):
            self.engine.update_dataframe(df)
            self.set_data(df)
            self.graph_panel.refresh()

        _apply(after_df)

        if hasattr(self.window(), '_undo_stack') and self.window()._undo_stack is not None:
            self.window()._undo_stack.record(
                UndoCommand(
                    action_type=UndoActionType.COLUMN_ADD,
                    description=f"Split column '{source_column}' into {', '.join(target_names)}",
                    do=lambda: _apply(after_df),
                    undo=lambda: _apply(before_df),
                    timestamp=time.time(),
                )
            )

        main_window = self.window()
        if main_window and hasattr(main_window, 'statusbar'):
            main_window.statusbar.showMessage(
                f"Split '{source_column}' into {len(target_names)} column(s)",
                3000,
            )

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
