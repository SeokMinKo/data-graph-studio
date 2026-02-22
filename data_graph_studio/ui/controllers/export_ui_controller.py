"""ExportUIController - extracted from MainWindow."""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QApplication, QMessageBox

from ...core.export_controller import ExportFormat

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..main_window import MainWindow

class ExportUIController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    # ============================================================
    # Export Image (PNG/SVG/PDF)
    # ============================================================

    def _on_export_image(self, fmt: "ExportFormat"):
        """Export chart as image (PNG/SVG/PDF)"""
        if not self.w.state.is_data_loaded:
            return

        ext_map = {ExportFormat.PNG: ("PNG Files (*.png)", ".png"),
                   ExportFormat.SVG: ("SVG Files (*.svg)", ".svg"),
                   ExportFormat.PDF: ("PDF Files (*.pdf)", ".pdf")}
        filter_str, ext = ext_map.get(fmt, ("All Files (*)", ""))
        path, _ = QFileDialog.getSaveFileName(self.w, f"Export {fmt.value.upper()}", f"chart{ext}", filter_str)
        if not path:
            return

        image = self.w._capture_graph_image()
        if image is None or image.isNull():
            self.w.statusbar.showMessage("⚠ No chart to export", 3000)
            return

        # One-shot signal connections via lambda + disconnect
        adapter = self.w._export_controller_adapter

        def _on_completed(p):
            self.w.statusbar.showMessage(f"✓ Exported to {p}", 3000)
            try:
                adapter.export_completed.disconnect(_on_completed)
            except RuntimeError:
                pass

        def _on_failed(e):
            self.w.statusbar.showMessage(f"⚠ Export failed: {e}", 5000)
            try:
                adapter.export_failed.disconnect(_on_failed)
            except RuntimeError:
                pass

        adapter.export_completed.connect(_on_completed)
        adapter.export_failed.connect(_on_failed)
        self.w._export_controller.export_chart_async(image, path, fmt)

    # ============================================================
    # Export Data (CSV/Excel/Parquet)
    # ============================================================

    def _on_export_data(self, fmt: "ExportFormat"):
        """Export data (CSV/Excel/Parquet)"""
        if not self.w.state.is_data_loaded or self.w.engine.df is None:
            return

        ext_map = {ExportFormat.CSV: ("CSV Files (*.csv)", ".csv"),
                   ExportFormat.EXCEL: ("Excel Files (*.xlsx)", ".xlsx"),
                   ExportFormat.PARQUET: ("Parquet Files (*.parquet)", ".parquet")}
        filter_str, ext = ext_map.get(fmt, ("All Files (*)", ""))
        path, _ = QFileDialog.getSaveFileName(self.w, f"Export {fmt.value.upper()}", f"data{ext}", filter_str)
        if not path:
            return

        # One-shot signal connections
        adapter = self.w._export_controller_adapter

        def _on_completed(p):
            self.w.statusbar.showMessage(f"✓ Exported to {p}", 3000)
            try:
                adapter.export_completed.disconnect(_on_completed)
            except RuntimeError:
                pass

        def _on_failed(e):
            self.w.statusbar.showMessage(f"⚠ Export failed: {e}", 5000)
            try:
                adapter.export_failed.disconnect(_on_failed)
            except RuntimeError:
                pass

        adapter.export_completed.connect(_on_completed)
        adapter.export_failed.connect(_on_failed)
        self.w._export_controller.export_data_async(self.w.engine.df, path, fmt)

    # ============================================================
    # Export Dialog (Ctrl+E)
    # ============================================================

    def _on_export_dialog(self):
        """Open ExportDialog (Ctrl+E)"""
        if not self.w.state.is_data_loaded:
            self.w.statusbar.showMessage("⚠ No data loaded", 3000)
            return

        from ..dialogs.export_dialog import ExportDialog
        mode = "chart" if (self.w.state.value_columns or self.w.state.x_column) else "data"
        dlg = ExportDialog(self.w, mode=mode)

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
        adapter = self.w._export_controller_adapter
        adapter.progress_changed.connect(dlg.update_progress)
        adapter.export_completed.connect(dlg.on_export_completed)
        adapter.export_failed.connect(dlg.on_export_failed)

        dlg.exec()

    # ============================================================
    # Report Export with format parameter
    # ============================================================

    def _on_export_report_format(self, fmt: str):
        """Export report in specified format (html/pptx/docx/markdown/pdf)"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self.w, "Export Report", "No data loaded.")
            return

        try:
            from ..dialogs.report_dialog import ReportDialog
            dialog = ReportDialog(self.w.engine, self.w.state, self.w.graph_panel, self.w)
            # Pre-select format if the dialog supports it
            if hasattr(dialog, 'set_format'):
                dialog.set_format(fmt)
            dialog.exec()
        except ImportError:
            ext_map = {
                "html": ("HTML Report (*.html)", ".html"),
                "pptx": ("PowerPoint (*.pptx)", ".pptx"),
                "docx": ("Word Document (*.docx)", ".docx"),
                "markdown": ("Markdown (*.md)", ".md"),
                "pdf": ("PDF Report (*.pdf)", ".pdf"),
            }
            filter_str, ext = ext_map.get(fmt, ("All Files (*)", ""))
            file_path, _ = QFileDialog.getSaveFileName(
                self.w, f"Export Report ({fmt.upper()})", f"report{ext}", filter_str
            )
            if file_path:
                self.w.statusbar.showMessage(f"Report exported to {file_path}", 3000)

    # ============================================================
    # Clipboard Copy
    # ============================================================

    def _copy_chart_to_clipboard(self):
        """Copy current chart image to clipboard"""
        if not self.w.state.is_data_loaded:
            self.w.statusbar.showMessage("⚠ No data loaded", 3000)
            return

        image = self._capture_graph_image()
        if image and not image.isNull():
            QApplication.clipboard().setImage(image)
            self.w.statusbar.showMessage("✓ Chart copied to clipboard", 3000)
        else:
            self.w.statusbar.showMessage("⚠ No chart to copy", 3000)

    def _copy_data_to_clipboard(self):
        """Copy current data to clipboard as TSV"""
        if not self.w.state.is_data_loaded or self.w.engine.df is None:
            self.w.statusbar.showMessage("⚠ No data loaded", 3000)
            return

        try:
            tsv = self.w.engine.df.write_csv(separator="\t")
            QApplication.clipboard().setText(tsv)
            rows = len(self.w.engine.df)
            self.w.statusbar.showMessage(f"✓ {rows:,} rows copied to clipboard", 3000)
        except Exception as e:
            self.w.statusbar.showMessage(f"⚠ Copy failed: {e}", 5000)

    # ============================================================
    # Batch Export
    # ============================================================

    def _on_batch_export(self):
        """Export all datasets"""
        if not self.w.state.is_data_loaded:
            self.w.statusbar.showMessage("⚠ No data loaded", 3000)
            return

        directory = QFileDialog.getExistingDirectory(self.w, "Select Export Directory")
        if not directory:
            return

        datasets = self.w.engine.list_datasets() if hasattr(self.w.engine, 'list_datasets') else []
        if not datasets:
            # Single dataset mode
            path = os.path.join(directory, "data_export.csv")
            self.w._export_controller.export_data_async(self.w.engine.df, path, ExportFormat.CSV)
            self.w.statusbar.showMessage(f"✓ Exporting to {directory}", 3000)
            return

        exported = 0
        for ds in datasets:
            ds_name = getattr(ds, 'name', str(ds)) if not isinstance(ds, str) else ds
            ds_id = getattr(ds, 'id', ds) if not isinstance(ds, str) else ds
            df = self.w.engine.get_dataset_df(ds_id) if hasattr(self.w.engine, 'get_dataset_df') else None
            if df is not None:
                safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in ds_name)
                path = os.path.join(directory, f"{safe_name}.csv")
                self.w._export_controller.export_data_sync(df, path, ExportFormat.CSV)
                exported += 1

        self.w.statusbar.showMessage(f"✓ Exported {exported} dataset(s) to {directory}", 5000)

    # ============================================================
    # Auto Export (file watch integration)
    # ============================================================

    def _on_toggle_auto_export(self, checked: bool):
        """Toggle auto-export on file change"""
        if not hasattr(self.w, '_auto_export_enabled'):
            self.w._auto_export_enabled = False
            self.w._auto_export_path = None
            self.w._auto_export_format = ExportFormat.CSV

        if checked:
            path, _ = QFileDialog.getSaveFileName(
                self.w, "Auto-Export Destination", "auto_export.csv",
                "CSV (*.csv);;Excel (*.xlsx);;Parquet (*.parquet)"
            )
            if path:
                self.w._auto_export_enabled = True
                self.w._auto_export_path = path
                if path.endswith('.xlsx'):
                    self.w._auto_export_format = ExportFormat.EXCEL
                elif path.endswith('.parquet'):
                    self.w._auto_export_format = ExportFormat.PARQUET
                else:
                    self.w._auto_export_format = ExportFormat.CSV
                self.w.statusbar.showMessage(f"✓ Auto-export enabled → {path}", 3000)
            else:
                checked = False

        if not checked:
            self.w._auto_export_enabled = False
            self.w.statusbar.showMessage("Auto-export disabled", 3000)

    def _do_auto_export(self):
        """Perform auto-export (called on file change)"""
        if not getattr(self.w, '_auto_export_enabled', False):
            return
        path = getattr(self.w, '_auto_export_path', None)
        fmt = getattr(self.w, '_auto_export_format', ExportFormat.CSV)
        if path and self.w.engine.df is not None:
            self.w._export_controller.export_data_async(self.w.engine.df, path, fmt)
            logger.info("export_ui_controller.auto_exported", extra={"path": path})

    # ============================================================
    # Capture Graph Image
    # ============================================================

    def _capture_graph_image(self):
        """Capture the current graph panel as QImage"""
        try:
            if hasattr(self.w.graph_panel, 'main_graph') and self.w.graph_panel.main_graph:
                from pyqtgraph.exporters import ImageExporter
                from PySide6.QtGui import QImage
                import tempfile
                import os
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
            logger.warning("export_ui_controller.graph_image_capture_failed", extra={"error": e})
        return None

    # ============================================================
    # B-6: Theme Persistence
    # ============================================================
