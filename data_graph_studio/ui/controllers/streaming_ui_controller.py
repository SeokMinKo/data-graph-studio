"""StreamingUIController - extracted from MainWindow."""
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

class StreamingUIController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    def _on_streaming_play(self, checked: bool = False):
        """Start/resume streaming — Play 연속 클릭 방어 (FR-B2.6)."""
        if self.w._streaming_controller.state == "live":
            return  # already playing
        if not self.w.state.is_data_loaded:
            self.w.statusbar.showMessage("⚠ No data loaded — cannot start streaming", 4000)
            self.w._streaming_play_action.setChecked(False)
            return
        if self.w._streaming_controller.state == "paused":
            self.w._streaming_controller.resume()
        else:
            # Open config dialog for fresh start
            self.w._on_start_streaming_dialog()


    def _on_streaming_pause(self):
        """Pause/resume streaming playback"""
        if self.w._streaming_controller.state == "live":
            self.w._streaming_controller.pause()
        elif self.w._streaming_controller.state == "paused":
            self.w._streaming_controller.resume()


    def _on_streaming_stop(self):
        """Stop streaming — current data is kept (FR-B2.7)."""
        self.w._streaming_controller.stop()


    def _on_streaming_speed_changed(self, text: str):
        """Change streaming speed"""
        try:
            speed = float(text.replace('x', ''))
            self.w._streaming_controller.set_poll_interval(
                max(500, int(self.w._streaming_controller.poll_interval_ms / speed))
            )
        except (ValueError, ZeroDivisionError):
            pass


    def _on_streaming_window_changed(self, text: str):
        """Change streaming window size"""
        pass  # Window size is a display-level concept; no-op for now


    def _on_start_streaming_dialog(self):
        """Open the streaming configuration dialog and start streaming (FR-B2.1)."""
        if not self.w.state.is_data_loaded:
            self.w.statusbar.showMessage("⚠ No data loaded — load data first", 4000)
            return
        initial_path = self.w._streaming_controller.current_path or ""
        dlg = StreamingDialog(
            self,
            initial_path=initial_path,
            initial_interval_ms=self.w._streaming_controller.poll_interval_ms,
            initial_mode="tail",
        )
        if dlg.exec() != QDialog.Accepted:
            return

        file_path = dlg.file_path
        if not file_path:
            return

        # Configure and start
        self.w._streaming_controller.set_poll_interval(dlg.interval_ms)
        ok = self.w._streaming_controller.start(file_path, mode=dlg.mode)
        if not ok:
            QMessageBox.warning(
                self, "Streaming Error",
                f"Could not start streaming for:\n{file_path}\n\n"
                "The file may not exist or is not accessible.",
            )


    def _on_pause_streaming(self):
        """Toggle pause/resume for streaming."""
        if self.w._streaming_controller.state == "live":
            self.w._streaming_controller.pause()
        elif self.w._streaming_controller.state == "paused":
            self.w._streaming_controller.resume()


    def _on_stop_streaming(self):
        """Stop the active streaming session."""
        self.w._streaming_controller.stop()

    @Slot(str)

    def _on_streaming_state_changed(self, new_state: str):
        """Handle streaming state transitions — update toolbar and status bar (FR-B2.4)."""
        is_active = new_state in ("live", "paused")

        # Toolbar buttons
        self.w._streaming_play_action.setEnabled(new_state != "live")
        self.w._streaming_play_action.setChecked(new_state == "live")
        self.w._streaming_pause_action.setEnabled(is_active)
        self.w._streaming_stop_action.setEnabled(is_active)

        # Pause button label
        if new_state == "paused":
            self.w._streaming_pause_action.setText("▶")
            self.w._streaming_pause_action.setToolTip("Resume Streaming")
        else:
            self.w._streaming_pause_action.setText("⏸")
            self.w._streaming_pause_action.setToolTip("Pause Streaming")

        # Menu actions
        self.w._start_streaming_action.setEnabled(new_state == "off")
        self.w._stop_streaming_action.setEnabled(is_active)

        # Status bar (FR-B2.4)
        if new_state == "live":
            self.w.statusbar.showMessage("Streaming: 🟢 active", 3000)
        elif new_state == "paused":
            self.w.statusbar.showMessage("Streaming: ⏸ paused", 3000)
        elif new_state == "off":
            self.w.statusbar.showMessage("Streaming stopped", 3000)

    @Slot(str, int)

    def _on_streaming_data_updated(self, file_path: str, new_row_count: int):
        """Handle incoming streaming data — reload file and refresh graph."""
        try:
            if not self.w.engine.is_loaded:
                # First load via engine
                dataset_id = self.w.engine.load_dataset(file_path)
                if dataset_id:
                    dataset = self.w.engine.get_dataset(dataset_id)
                    if dataset:
                        memory_bytes = (
                            dataset.df.estimated_size()
                            if dataset and dataset.df is not None
                            else 0
                        )
                        self.w.state.add_dataset(
                            dataset_id=dataset_id,
                            name=dataset.name if dataset.name else Path(file_path).stem,
                            file_path=file_path,
                            row_count=self.w.engine.row_count,
                            column_count=self.w.engine.column_count,
                            memory_bytes=memory_bytes,
                        )
                    self.w._on_dataset_activated(dataset_id)
                return

            # Re-load the active dataset from disk
            success = self.w.engine.load_file(file_path, optimize_memory=True)
            if success:
                self.w.state.set_data_loaded(True, self.w.engine.row_count)
                self.w.table_panel.set_data(self.w.engine.df)
                self.w.graph_panel.refresh()
                if new_row_count > 0:
                    self.w.statusbar.showMessage(
                        f"Streaming: +{new_row_count} rows", 2000
                    )
        except Exception as e:
            logger.error(f"Streaming data update error: {e}", exc_info=True)
            self.w.statusbar.showMessage(f"Streaming error: {e}", 5000)


