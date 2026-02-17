"""DataOpsController - extracted from MainWindow."""
from __future__ import annotations

import os
import gc
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, List, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QMenu, QToolBar, QStatusBar, QFileDialog, QMessageBox,
    QProgressDialog, QApplication, QLabel, QDialog, QFrame,
    QInputDialog, QTabWidget, QColorDialog, QPushButton, QDockWidget
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QColor

from ...core.state import ToolMode, ChartType, ComparisonMode, AggregationType
from ...core.export_controller import ExportFormat
from ...core.updater import (
    get_current_version, check_github_latest, is_update_available,
    download_asset, read_sha256_file, sha256sum, run_windows_installer,
)
from ..dialogs.streaming_dialog import StreamingDialog
from ..dialogs.command_palette_dialog import CommandPaletteDialog
from ..dialogs.computed_column_dialog import ComputedColumnDialog
from ..dialogs.profile_manager_dialog import ProfileManagerDialog
from ..panels.side_by_side_layout import SideBySideLayout
from ..panels.comparison_stats_panel import ComparisonStatsPanel
from ..panels.overlay_stats_widget import OverlayStatsWidget
from ..panels.annotation_panel import AnnotationPanel
from ..panels.dashboard_panel import DashboardPanel
from ..toolbars.compare_toolbar import CompareToolbar
from ..dialogs.parsing_preview_dialog import ParsingPreviewDialog
from ..dialogs.save_setting_dialog import SaveSettingDialog
from ..dialogs.multi_file_dialog import open_multi_file_dialog
from ..wizards.new_project_wizard import NewProjectWizard
from ...core.parsing import ParsingSettings

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..main_window import MainWindow

class DataOpsController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    def _paste_from_clipboard(self):
        """클립보드에서 데이터 붙여넣기"""
        if not ClipboardManager.has_table_data():
            self.w.statusBar().showMessage("No valid table data in clipboard", 3000)
            return
        
        df, message = ClipboardManager.paste_as_dataframe()
        
        if df is not None and len(df) > 0:
            # 데이터 로드
            try:
                # 임시 데이터셋으로 추가
                import uuid
                dataset_id = f"clipboard_{uuid.uuid4().hex[:8]}"
                
                # 엔진에 직접 설정
                self.w.engine._df = df
                
                # 상태 업데이트
                self.w.state.set_data_loaded(True, len(df))
                self.w.state.set_column_order(df.columns)
                
                # UI 업데이트
                self.w.table_panel.set_data(df)
                self.w.graph_panel.set_columns(df.columns)
                
                # Data 탭에 컬럼 목록 전달
                if hasattr(self.w.graph_panel.options_panel, 'data_tab'):
                    self.w.graph_panel.options_panel.data_tab.set_columns(
                        df.columns, self.w.engine
                    )
                
                self.w.statusBar().showMessage(f"✓ {message}", 5000)
                
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
            QMessageBox.information(self, "Find", "No data loaded.")
            return
        
        text, ok = QInputDialog.getText(
            self, "Find Data", "Search for:",
            text=""
        )
        if ok and text.strip():
            # 테이블 패널에 검색 요청
            if hasattr(self.w.table_panel, 'find_text'):
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
            QMessageBox.information(self, "Go to Row", "No data loaded.")
            return
        
        max_row = self.w.engine.row_count
        row, ok = QInputDialog.getInt(
            self, "Go to Row", f"Enter row number (1-{max_row}):",
            value=1, min=1, max=max_row
        )
        if ok:
            if hasattr(self.w.table_panel, 'goto_row'):
                self.w.table_panel.goto_row(row - 1)  # 0-indexed
                self.w.statusbar.showMessage(f"Jumped to row {row}", 3000)
            else:
                self.w.statusbar.showMessage("Go to row functionality not available", 3000)


    def _on_filter_data(self):
        """필터 패널 토글"""
        # 필터 패널이 있으면 토글, 없으면 생성
        if hasattr(self, 'filter_panel') and self.w.filter_panel:
            self.w.filter_panel.setVisible(not self.w.filter_panel.isVisible())
        else:
            self.w.statusbar.showMessage("Filter panel toggled", 3000)
            # 필터 패널이 없는 경우 그래프 패널의 필터 기능 활성화
            if hasattr(self.w.graph_panel, 'toggle_filter'):
                self.w.graph_panel.toggle_filter()


    def _on_sort_data(self):
        """정렬 다이얼로그"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self, "Sort", "No data loaded.")
            return
        
        columns = self.w.engine.columns
        column, ok = QInputDialog.getItem(
            self, "Sort Data", "Select column to sort by:",
            columns, 0, False
        )
        if ok and column:
            # 정렬 순서 선택
            orders = ["Ascending", "Descending"]
            order, ok2 = QInputDialog.getItem(
                self, "Sort Order", "Select sort order:",
                orders, 0, False
            )
            if ok2:
                ascending = (order == "Ascending")
                self.w.statusbar.showMessage(f"Sorted by '{column}' ({order})", 3000)
                # TODO: 실제 정렬 구현
                # self.w.engine.sort_data(column, ascending)
                # self.w._on_data_loaded()


    def _on_add_calculated_field(self):
        """계산 필드 추가 다이얼로그 (FR-B3.1, FR-B3.5)."""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self, "Add Calculated Field", "데이터를 먼저 로드하세요.")
            return

        df = self.w.engine.df
        if df is None or df.is_empty():
            QMessageBox.warning(self, "Add Calculated Field", "No data available.")
            return

        dialog = ComputedColumnDialog(df, parent=self)
        dialog.column_created.connect(self.w._on_computed_column_created)
        dialog.exec()


    def _on_computed_column_created(self, defn, series):
        """Handle computed column result — add to engine and refresh UI (FR-B3.2)."""
        from ..core.undo_manager import UndoCommand, UndoActionType

        try:
            col_name = defn.name if hasattr(defn, 'name') else str(defn)
            before_df = self.w.engine.df
            if before_df is None:
                return

            after_df = before_df.with_columns(series.alias(col_name))

            def _apply_df(df):
                # Update engine
                self.w.engine._df = df

                # Sync state/UI
                try:
                    self.w.state.set_column_order(self.w.engine.columns)
                except Exception:
                    pass

                self.w.table_panel.set_data(df)

                try:
                    self.w.graph_panel.set_columns(self.w.engine.columns)
                    if hasattr(self.w.graph_panel.options_panel, 'data_tab'):
                        self.w.graph_panel.options_panel.data_tab.set_columns(
                            self.w.engine.columns, self.w.engine
                        )
                except Exception:
                    pass

                self.w.graph_panel.refresh()

            # Apply
            _apply_df(after_df)

            # Record undo/redo
            self.w._undo_stack.record(
                UndoCommand(
                    action_type=UndoActionType.COLUMN_ADD,
                    description=f"Add computed column '{col_name}'",
                    do=lambda: _apply_df(after_df),
                    undo=lambda: _apply_df(before_df),
                    timestamp=time.time(),
                )
            )

            self.w.statusbar.showMessage(f"Computed column '{col_name}' added", 3000)
        except Exception as e:
            logger.error(f"Failed to add computed column: {e}", exc_info=True)
            QMessageBox.warning(self, "Add Calculated Field", f"Failed to add column:\n{e}")


    def _on_remove_duplicates(self):
        """중복 제거"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self, "Remove Duplicates", "No data loaded.")
            return
        
        reply = QMessageBox.question(
            self, "Remove Duplicates",
            f"This will remove duplicate rows from the data.\n"
            f"Current rows: {self.w.engine.row_count:,}\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # TODO: 실제 중복 제거 구현
            self.w.statusbar.showMessage("Duplicate removal feature coming soon", 3000)


    def _on_data_summary(self):
        """데이터 요약 다이얼로그"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self, "Data Summary", "No data loaded.")
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


