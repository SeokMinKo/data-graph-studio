"""TraceCompareDialog - Compare two ftrace files side by side."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QDialogButtonBox, QGroupBox, QFormLayout,
)
from PySide6.QtCore import Qt

from ...core.state import ComparisonMode

logger = logging.getLogger(__name__)

# Available converters (must match FtraceParser._converters keys)
_CONVERTERS = ["", "blocklayer", "sched"]


class TraceCompareDialog(QDialog):
    """Dialog to select two ftrace files and comparison parameters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Traces")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- File selection ---
        file_group = QGroupBox("Trace Files")
        file_layout = QFormLayout(file_group)

        # Trace A
        trace_a_row = QHBoxLayout()
        self._path_a_edit = QLineEdit()
        self._path_a_edit.setPlaceholderText("Select trace file (Before)...")
        self._path_a_edit.setReadOnly(True)
        trace_a_row.addWidget(self._path_a_edit)
        browse_a = QPushButton("Browse...")
        browse_a.clicked.connect(lambda: self._browse("a"))
        trace_a_row.addWidget(browse_a)
        file_layout.addRow("Trace A (Before):", trace_a_row)

        # Trace B
        trace_b_row = QHBoxLayout()
        self._path_b_edit = QLineEdit()
        self._path_b_edit.setPlaceholderText("Select trace file (After)...")
        self._path_b_edit.setReadOnly(True)
        trace_b_row.addWidget(self._path_b_edit)
        browse_b = QPushButton("Browse...")
        browse_b.clicked.connect(lambda: self._browse("b"))
        trace_b_row.addWidget(browse_b)
        file_layout.addRow("Trace B (After):", trace_b_row)

        layout.addWidget(file_group)

        # --- Options ---
        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)

        self._converter_combo = QComboBox()
        self._converter_combo.addItem("(raw events)", "")
        self._converter_combo.addItem("Block Layer", "blocklayer")
        self._converter_combo.addItem("Scheduler", "sched")
        self._converter_combo.setCurrentIndex(1)  # default: blocklayer
        options_layout.addRow("Converter:", self._converter_combo)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Overlay", ComparisonMode.OVERLAY.value)
        self._mode_combo.addItem("Side by Side", ComparisonMode.SIDE_BY_SIDE.value)
        self._mode_combo.addItem("Difference", ComparisonMode.DIFFERENCE.value)
        options_layout.addRow("Compare Mode:", self._mode_combo)

        layout.addWidget(options_group)

        # --- Buttons ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setText("Compare")
        self._ok_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self, which: str):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Trace File ({'Before' if which == 'a' else 'After'})",
            "",
            "Ftrace Files (*.txt *.dat *.log);;All Files (*)",
        )
        if path:
            edit = self._path_a_edit if which == "a" else self._path_b_edit
            edit.setText(path)
            self._validate()

    def _validate(self):
        has_both = bool(self._path_a_edit.text()) and bool(self._path_b_edit.text())
        self._ok_button.setEnabled(has_both)

    # --- Public accessors ---

    @property
    def path_a(self) -> str:
        return self._path_a_edit.text()

    @property
    def path_b(self) -> str:
        return self._path_b_edit.text()

    @property
    def converter(self) -> str:
        return self._converter_combo.currentData()

    @property
    def compare_mode(self) -> ComparisonMode:
        return ComparisonMode(self._mode_combo.currentData())
