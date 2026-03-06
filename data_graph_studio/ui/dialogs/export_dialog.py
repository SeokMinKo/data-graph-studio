"""
Export Dialog — PRD FR-4.6, FR-4.9

Provides:
- ExportDialog: modal dialog for export configuration
  - File format selection (PNG / SVG / PDF / CSV / Parquet / Excel)
  - Resolution presets (Current / 1920×1080 / 3840×2160 / Custom)
  - DPI spinner
  - Background colour (transparent / white / dark)
  - Legend toggle
  - Stats summary toggle (PDF only)
  - Progress bar + Cancel button (FR-4.9)
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QFileDialog,
    QLineEdit,
    QWidget,
)

from data_graph_studio.core.export_controller import ExportFormat, ExportOptions


# ---------------------------------------------------------------------------
# Resolution presets
# ---------------------------------------------------------------------------
_RESOLUTION_PRESETS = {
    "Current": (None, None),
    "Full HD (1920×1080)": (1920, 1080),
    "4K UHD (3840×2160)": (3840, 2160),
    "Custom": (None, None),
}


class ExportDialog(QDialog):
    """
    Export Settings Dialog — FR-4.6 / FR-4.9.

    Signals:
        export_requested(ExportFormat, str, ExportOptions)
            format, output_path, options
    """

    export_requested = Signal(object, str, object)  # ExportFormat, path, ExportOptions

    def __init__(self, parent: Optional[QWidget] = None, mode: str = "chart"):
        """
        Args:
            mode: "chart" or "data" — controls which format/options are shown.
        """
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(420)
        self._mode = mode
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- Format ---
        fmt_group = QGroupBox("Format")
        fmt_layout = QFormLayout(fmt_group)

        self.format_combo = QComboBox()
        self.format_combo.setToolTip("Select the output file format")
        if self._mode == "chart":
            self.format_combo.addItem("PNG", ExportFormat.PNG)
            self.format_combo.addItem("SVG", ExportFormat.SVG)
            self.format_combo.addItem("PDF", ExportFormat.PDF)
        else:
            self.format_combo.addItem("CSV", ExportFormat.CSV)
            self.format_combo.addItem("Parquet", ExportFormat.PARQUET)
            self.format_combo.addItem("Excel (.xlsx)", ExportFormat.EXCEL)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        fmt_layout.addRow("File format:", self.format_combo)

        # Output path
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Choose output file…")
        self.path_edit.setToolTip("Output file path")
        path_row.addWidget(self.path_edit)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setToolTip("Choose export file location")
        self.browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.browse_btn)
        fmt_layout.addRow("Save to:", path_row)

        layout.addWidget(fmt_group)

        # --- Chart options (hidden for data mode) ---
        self.chart_group = QGroupBox("Chart Options")
        chart_layout = QFormLayout(self.chart_group)

        # Resolution
        self.resolution_combo = QComboBox()
        self.resolution_combo.setToolTip("Select output image resolution")
        for label in _RESOLUTION_PRESETS:
            self.resolution_combo.addItem(label)
        self.resolution_combo.currentTextChanged.connect(self._on_resolution_changed)
        chart_layout.addRow("Resolution:", self.resolution_combo)

        # Custom size row
        self.custom_size_widget = QWidget()
        cs_layout = QHBoxLayout(self.custom_size_widget)
        cs_layout.setContentsMargins(0, 0, 0, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setToolTip("Custom image width in pixels")
        self.width_spin.setRange(100, 7680)
        self.width_spin.setValue(1920)
        cs_layout.addWidget(QLabel("W:"))
        cs_layout.addWidget(self.width_spin)
        self.height_spin = QSpinBox()
        self.height_spin.setToolTip("Custom image height in pixels")
        self.height_spin.setRange(100, 4320)
        self.height_spin.setValue(1080)
        cs_layout.addWidget(QLabel("H:"))
        cs_layout.addWidget(self.height_spin)
        self.custom_size_widget.setVisible(False)
        chart_layout.addRow("", self.custom_size_widget)

        # DPI
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setToolTip("Dots per inch — higher values for print quality")
        self.dpi_spin.setRange(72, 600)
        self.dpi_spin.setValue(96)
        chart_layout.addRow("DPI:", self.dpi_spin)

        # Background
        self.bg_combo = QComboBox()
        self.bg_combo.setToolTip("Background color for exported chart")
        self.bg_combo.addItems(["White", "Transparent", "Dark"])
        chart_layout.addRow("Background:", self.bg_combo)

        # Legend
        self.legend_check = QCheckBox("Include legend")
        self.legend_check.setToolTip("Include chart legend in export")
        self.legend_check.setChecked(True)
        chart_layout.addRow("", self.legend_check)

        # Stats (PDF only)
        self.stats_check = QCheckBox("Include statistics summary")
        self.stats_check.setToolTip("Append statistical summary page (PDF only)")
        self.stats_check.setChecked(False)
        chart_layout.addRow("", self.stats_check)

        layout.addWidget(self.chart_group)

        if self._mode != "chart":
            self.chart_group.setVisible(False)

        # --- Progress (FR-4.9) ---
        self.progress_group = QGroupBox("Progress")
        pg_layout = QVBoxLayout(self.progress_group)
        self.status_label = QLabel("Ready")
        pg_layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        pg_layout.addWidget(self.progress_bar)
        self.progress_group.setVisible(False)
        layout.addWidget(self.progress_group)

        # --- Buttons ---
        self.button_box = QDialogButtonBox()
        self.export_btn = self.button_box.addButton(
            "Export", QDialogButtonBox.AcceptRole
        )
        self.export_btn.setToolTip("Start export with current settings")
        self.cancel_btn = self.button_box.addButton(QDialogButtonBox.Cancel)
        self.cancel_btn.setToolTip("Cancel and close dialog")
        self.button_box.accepted.connect(self._on_export)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_format_changed(self, _index: int) -> None:
        fmt = self.format_combo.currentData()
        # Show/hide stats checkbox only for PDF
        self.stats_check.setVisible(fmt == ExportFormat.PDF)

    def _on_resolution_changed(self, text: str) -> None:
        self.custom_size_widget.setVisible(text == "Custom")

    def _browse(self) -> None:
        fmt = self.format_combo.currentData()
        ext_map = {
            ExportFormat.PNG: "PNG Files (*.png)",
            ExportFormat.SVG: "SVG Files (*.svg)",
            ExportFormat.PDF: "PDF Files (*.pdf)",
            ExportFormat.CSV: "CSV Files (*.csv)",
            ExportFormat.PARQUET: "Parquet Files (*.parquet)",
            ExportFormat.EXCEL: "Excel Files (*.xlsx)",
        }
        filter_str = ext_map.get(fmt, "All Files (*)")
        path, _ = QFileDialog.getSaveFileName(self, "Export", "", filter_str)
        if path:
            self.path_edit.setText(path)

    def _on_export(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            return

        fmt = self.format_combo.currentData()
        opts = self._build_options()

        # Show progress
        self.progress_group.setVisible(True)
        self.status_label.setText("Exporting…")
        self.export_btn.setEnabled(False)

        self.export_requested.emit(fmt, path, opts)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def _build_options(self) -> ExportOptions:
        """Build ExportOptions from current dialog state."""
        # Resolution
        res_text = self.resolution_combo.currentText()
        preset = _RESOLUTION_PRESETS.get(res_text, (None, None))
        if res_text == "Custom":
            w, h = self.width_spin.value(), self.height_spin.value()
        else:
            w, h = preset

        bg_map = {"White": "white", "Transparent": "transparent", "Dark": "dark"}
        bg = bg_map.get(self.bg_combo.currentText(), "white")

        fmt = self.format_combo.currentData()
        page_size = "A4"  # default; could add a combo for PDF

        return ExportOptions(
            width=w,
            height=h,
            dpi=self.dpi_spin.value(),
            background=bg,
            include_legend=self.legend_check.isChecked(),
            include_stats=self.stats_check.isChecked()
            if fmt == ExportFormat.PDF
            else False,
            page_size=page_size,
        )

    @Slot(int)
    def update_progress(self, value: int) -> None:
        """Called by ExportController.progress_changed."""
        self.progress_bar.setValue(value)
        if value < 50:
            self.status_label.setText("Rendering chart…")
        elif value < 100:
            self.status_label.setText("Writing file…")
        else:
            self.status_label.setText("Complete ✓")
            self.export_btn.setEnabled(True)

    @Slot(str)
    def on_export_completed(self, path: str) -> None:
        """Called on success."""
        self.status_label.setText(f"Exported to {path}")
        self.progress_bar.setValue(100)
        self.export_btn.setEnabled(True)

    @Slot(str)
    def on_export_failed(self, error: str) -> None:
        """Called on failure."""
        self.status_label.setText(f"Error: {error}")
        self.progress_bar.setValue(0)
        self.export_btn.setEnabled(True)
