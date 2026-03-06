"""DataOpsController - extracted from MainWindow."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QInputDialog, QMessageBox
from PySide6.QtCore import Qt

from ..dialogs.computed_column_dialog import ComputedColumnDialog
from ...core.clipboard_manager import ClipboardManager

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..main_window import MainWindow


class DataOpsController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: "MainWindow"):
        self.w = main_window

    def _paste_from_clipboard(self):
        """클립보드에서 데이터 붙여넣기"""
        if not ClipboardManager.has_table_data():
            self.w.statusBar().showMessage("No valid table data in clipboard", 3000)
            return

        df, message = ClipboardManager.paste_as_dataframe()

        if df is not None and len(df) > 0:
            try:
                # Use official DatasetManager API instead of direct _df assignment
                dataset_id = self.w.engine.load_dataset_from_dataframe(
                    df, name="Clipboard Data", source_path="clipboard"
                )
                if dataset_id:
                    self.w.engine.activate_dataset(dataset_id)
                    # Update state
                    memory_bytes = df.estimated_size()
                    self.w.state.add_dataset(
                        dataset_id=dataset_id,
                        name="Clipboard Data",
                        row_count=len(df),
                        column_count=len(df.columns),
                        memory_bytes=memory_bytes,
                    )
                    self.w.state.set_data_loaded(True, len(df))
                    self.w.state.set_column_order(df.columns)
                    self.w._on_data_loaded()
                    self.w.statusBar().showMessage(f"✓ {message}", 5000)
                else:
                    self.w.statusBar().showMessage(
                        "Failed to load clipboard data", 5000
                    )
            except Exception as e:
                self.w.statusBar().showMessage(f"Paste error: {e}", 5000)
        else:
            self.w.statusBar().showMessage(message, 3000)

    def _on_import_from_clipboard(self):
        """클립보드에서 데이터 직접 임포트"""
        self.w._paste_from_clipboard()

    def _on_find_data(self):
        """데이터 검색 다이얼로그"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self.w, "Find", "No data loaded.")
            return

        text, ok = QInputDialog.getText(self.w, "Find Data", "Search for:", text="")
        if ok and text.strip():
            # 테이블 패널에 검색 요청
            if hasattr(self.w.table_panel, "find_text"):
                found = self.w.table_panel.find_text(text.strip())
                if found:
                    self.w.statusbar.showMessage(f"Found matches for '{text}'", 3000)
                else:
                    self.w.statusbar.showMessage(f"No matches found for '{text}'", 3000)
            else:
                self.w.statusbar.showMessage("Search functionality not available", 3000)

    def _on_goto_row(self):
        """특정 행으로 이동"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self.w, "Go to Row", "No data loaded.")
            return

        max_row = self.w.engine.row_count
        row, ok = QInputDialog.getInt(
            self.w,
            "Go to Row",
            f"Enter row number (1-{max_row}):",
            value=1,
            min=1,
            max=max_row,
        )
        if ok:
            if hasattr(self.w.table_panel, "goto_row"):
                self.w.table_panel.goto_row(row - 1)  # 0-indexed
                self.w.statusbar.showMessage(f"Jumped to row {row}", 3000)
            else:
                self.w.statusbar.showMessage(
                    "Go to row functionality not available", 3000
                )

    def _on_filter_data(self):
        """필터 패널 토글"""
        # 필터 패널이 있으면 토글, 없으면 생성
        if hasattr(self.w, "filter_panel") and self.w.filter_panel:
            self.w.filter_panel.setVisible(not self.w.filter_panel.isVisible())
        else:
            self.w.statusbar.showMessage("Filter panel toggled", 3000)
            # 필터 패널이 없는 경우 그래프 패널의 필터 기능 활성화
            if hasattr(self.w.graph_panel, "toggle_filter"):
                self.w.graph_panel.toggle_filter()

    def _on_sort_data(self):
        """정렬 다이얼로그"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self.w, "Sort", "No data loaded.")
            return

        columns = self.w.engine.columns
        column, ok = QInputDialog.getItem(
            self.w, "Sort Data", "Select column to sort by:", columns, 0, False
        )
        if ok and column:
            # 정렬 순서 선택
            orders = ["Ascending", "Descending"]
            order, ok2 = QInputDialog.getItem(
                self.w, "Sort Order", "Select sort order:", orders, 0, False
            )
            if ok2:
                from ...core.undo_manager import UndoCommand, UndoActionType

                descending = order == "Descending"
                # Capture current sort state for undo (reverse operation, no df copy)
                old_sort_col = column
                old_sort_desc = descending

                def _apply_sort(col, desc):
                    df = self.w.engine.df
                    sorted_df = df.sort(col, descending=desc)
                    self.w.engine.update_dataframe(sorted_df)
                    self.w.table_panel.set_data(sorted_df)
                    self.w.graph_panel.refresh()

                def _undo_sort():
                    # Reverse sort: sort by same column in opposite direction
                    _apply_sort(old_sort_col, not old_sort_desc)

                _apply_sort(column, descending)

                self.w._undo_stack.record(
                    UndoCommand(
                        action_type=UndoActionType.COLUMN_ADD,
                        description=f"Sort by '{column}' ({order})",
                        do=lambda: _apply_sort(column, descending),
                        undo=_undo_sort,
                        timestamp=time.time(),
                    )
                )
                self.w.statusbar.showMessage(f"Sorted by '{column}' ({order})", 3000)

    def _on_add_calculated_field(self):
        """계산 필드 추가 다이얼로그 (FR-B3.1, FR-B3.5)."""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(
                self.w, "Add Calculated Field", "데이터를 먼저 로드하세요."
            )
            return

        df = self.w.engine.df
        if df is None or df.is_empty():
            QMessageBox.warning(self.w, "Add Calculated Field", "No data available.")
            return

        dialog = ComputedColumnDialog(df, parent=self.w)
        dialog.column_created.connect(self.w._on_computed_column_created)
        dialog.exec()

    def _on_computed_column_created(self, defn, series):
        """Handle computed column result — add to engine and refresh UI (FR-B3.2)."""
        from ...core.undo_manager import UndoCommand, UndoActionType

        try:
            col_name = defn.name if hasattr(defn, "name") else str(defn)
            current_df = self.w.engine.df
            if current_df is None:
                return

            after_df = current_df.with_columns(series.alias(col_name))

            def _refresh_ui():
                df = self.w.engine.df
                try:
                    self.w.state.set_column_order(self.w.engine.columns)
                except Exception:
                    pass
                self.w.table_panel.set_data(df)
                try:
                    self.w.graph_panel.set_columns(self.w.engine.columns)
                    if hasattr(self.w.graph_panel.options_panel, "data_tab"):
                        self.w.graph_panel.options_panel.data_tab.set_columns(
                            self.w.engine.columns, self.w.engine
                        )
                except Exception:
                    pass
                self.w.graph_panel.refresh()

            def _do_add():
                df = self.w.engine.df
                new_df = df.with_columns(series.alias(col_name))
                self.w.engine.update_dataframe(new_df)
                _refresh_ui()

            def _undo_add():
                # Reverse operation: drop the column instead of restoring full df
                self.w.engine.drop_column(col_name)
                _refresh_ui()

            # Apply
            self.w.engine.update_dataframe(after_df)
            _refresh_ui()

            # Record undo/redo (reverse operation: drop column, no df copy)
            self.w._undo_stack.record(
                UndoCommand(
                    action_type=UndoActionType.COLUMN_ADD,
                    description=f"Add computed column '{col_name}'",
                    do=_do_add,
                    undo=_undo_add,
                    timestamp=time.time(),
                )
            )

            self.w.statusbar.showMessage(f"Computed column '{col_name}' added", 3000)
        except Exception as e:
            logger.error(f"Failed to add computed column: {e}", exc_info=True)
            QMessageBox.warning(
                self.w, "Add Calculated Field", f"Failed to add column:\n{e}"
            )

    def _on_remove_duplicates(self):
        """중복 제거"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self.w, "Remove Duplicates", "No data loaded.")
            return

        reply = QMessageBox.question(
            self.w,
            "Remove Duplicates",
            f"This will remove duplicate rows from the data.\n"
            f"Current rows: {self.w.engine.row_count:,}\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            from ...core.undo_manager import UndoCommand, UndoActionType
            import polars as pl

            current_df = self.w.engine.df
            # Save original row indices for undo (lightweight vs full df copy)
            pl.arange(0, len(current_df), eager=True)
            after_df = current_df.unique()
            removed = len(current_df) - len(after_df)

            # Store only the indices of kept rows for undo reference
            # We need to keep original row order to restore — store the duplicate mask
            dup_mask = current_df.is_duplicated()
            # Save the full df only if there are duplicates (unavoidable for true undo)
            # But store just the removed rows for memory efficiency
            removed_rows_df = current_df.filter(dup_mask)

            def _apply_remove():
                df = self.w.engine.df
                new_df = df.unique()
                self.w.engine.update_dataframe(new_df)
                self.w.table_panel.set_data(new_df)
                self.w.graph_panel.refresh()

            def _undo_remove():
                # Restore by concatenating removed rows back
                df = self.w.engine.df
                restored = pl.concat([df, removed_rows_df], how="vertical_relaxed")
                self.w.engine.update_dataframe(restored)
                self.w.table_panel.set_data(restored)
                self.w.graph_panel.refresh()

            self.w.engine.update_dataframe(after_df)
            self.w.table_panel.set_data(after_df)
            self.w.graph_panel.refresh()

            self.w._undo_stack.record(
                UndoCommand(
                    action_type=UndoActionType.COLUMN_ADD,
                    description=f"Remove {removed:,} duplicate rows",
                    do=_apply_remove,
                    undo=_undo_remove,
                    timestamp=time.time(),
                )
            )
            self.w.statusbar.showMessage(f"Removed {removed:,} duplicate rows", 3000)

    def _on_data_summary(self):
        """데이터 요약 다이얼로그"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self.w, "Data Summary", "No data loaded.")
            return

        # 간단한 요약 정보 표시
        summary = f"""
        <h2>Data Summary</h2>
        <table>
            <tr><td><b>Rows:</b></td><td>{self.w.engine.row_count:,}</td></tr>
            <tr><td><b>Columns:</b></td><td>{self.w.engine.column_count}</td></tr>
        </table>
        <h3>Columns:</h3>
        <ul>
        """
        for col in self.w.engine.columns[:20]:  # 최대 20개만 표시
            summary += f"<li>{col}</li>"
        if len(self.w.engine.columns) > 20:
            summary += f"<li>... and {len(self.w.engine.columns) - 20} more</li>"
        summary += "</ul>"

        msg = QMessageBox(self.w)
        msg.setWindowTitle("Data Summary")
        msg.setTextFormat(Qt.RichText)
        msg.setText(summary)
        msg.setIcon(QMessageBox.Information)
        msg.exec()
