"""ExportUIController - extracted from MainWindow."""
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

class ExportUIController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    def _on_export(self, format: str):
        """내보내기"""
        if not self.w.state.is_data_loaded:
            return
        
        if format == "csv":
            path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
            if path:
                self.w.engine.export_csv(path)
        elif format == "excel":
            path, _ = QFileDialog.getSaveFileName(self, "Export Excel", "", "Excel (*.xlsx)")
            if path:
                self.w.engine.export_excel(path)
        elif format == "png":
            path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG (*.png)")
            if path:
                self.w.graph_panel.export_image(path)
    

    def _on_export_dialog(self):
        """Open ExportDialog (Ctrl+E)"""
        if not self.w.state.is_data_loaded:
            self.w.statusbar.showMessage("⚠ No data loaded", 3000)
            return

        from ..dialogs.export_dialog import ExportDialog
        mode = "chart" if (self.w.state.value_columns or self.w.state.x_column) else "data"
        dlg = ExportDialog(self, mode=mode)

        # Connect dialog signals to controller
        def _handle_export(fmt, path, opts):
            if mode == "chart":
                image = self.w._capture_graph_image()
                if image and not image.isNull():
                    self.w._export_controller.export_chart_async(image, path, fmt, opts)
                else:
                    dlg.on_export_failed("No chart image available")
            else:
                df = self.w.engine.df
                if df is not None:
                    self.w._export_controller.export_data_async(df, path, fmt, opts)
                else:
                    dlg.on_export_failed("No data available")

        dlg.export_requested.connect(_handle_export)
        self.w._export_controller.progress_changed.connect(dlg.update_progress)
        self.w._export_controller.export_completed.connect(dlg.on_export_completed)
        self.w._export_controller.export_failed.connect(dlg.on_export_failed)

        dlg.exec()


    def _on_export_image(self, fmt: "ExportFormat"):
        """Export chart as image (PNG/SVG)"""
        if not self.w.state.is_data_loaded:
            return

        ext_map = {ExportFormat.PNG: ("PNG Files (*.png)", ".png"),
                   ExportFormat.SVG: ("SVG Files (*.svg)", ".svg")}
        filter_str, ext = ext_map.get(fmt, ("All Files (*)", ""))
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.value.upper()}", f"chart{ext}", filter_str)
        if not path:
            return

        image = self.w._capture_graph_image()
        if image is None or image.isNull():
            self.w.statusbar.showMessage("⚠ No chart to export", 3000)
            return

        self.w._export_controller.export_completed.connect(
            lambda p: self.w.statusbar.showMessage(f"✓ Exported to {p}", 3000))
        self.w._export_controller.export_failed.connect(
            lambda e: self.w.statusbar.showMessage(f"⚠ Export failed: {e}", 5000))
        self.w._export_controller.export_chart_async(image, path, fmt)


    def _on_export_data(self, fmt: "ExportFormat"):
        """Export data (CSV/Excel/Parquet)"""
        if not self.w.state.is_data_loaded or self.w.engine.df is None:
            return

        ext_map = {ExportFormat.CSV: ("CSV Files (*.csv)", ".csv"),
                   ExportFormat.EXCEL: ("Excel Files (*.xlsx)", ".xlsx"),
                   ExportFormat.PARQUET: ("Parquet Files (*.parquet)", ".parquet")}
        filter_str, ext = ext_map.get(fmt, ("All Files (*)", ""))
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.value.upper()}", f"data{ext}", filter_str)
        if not path:
            return

        self.w._export_controller.export_completed.connect(
            lambda p: self.w.statusbar.showMessage(f"✓ Exported to {p}", 3000))
        self.w._export_controller.export_failed.connect(
            lambda e: self.w.statusbar.showMessage(f"⚠ Export failed: {e}", 5000))
        self.w._export_controller.export_data_async(self.w.engine.df, path, fmt)


    def _capture_graph_image(self):
        """Capture the current graph panel as QImage"""
        try:
            if hasattr(self.w.graph_panel, 'main_graph') and self.w.graph_panel.main_graph:
                from pyqtgraph.exporters import ImageExporter
                from PySide6.QtGui import QImage
                import tempfile, os
                exporter = ImageExporter(self.w.graph_panel.main_graph.plotItem)
                exporter.parameters()['width'] = 1920
                temp_path = os.path.join(tempfile.gettempdir(), 'dgs_export_temp.png')
                exporter.export(temp_path)
                image = QImage(temp_path)
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                return image
        except Exception as e:
            logger.warning(f"Failed to capture graph image: {e}")
        return None

    # ============================================================
    # B-6: Theme Persistence
    # ============================================================


