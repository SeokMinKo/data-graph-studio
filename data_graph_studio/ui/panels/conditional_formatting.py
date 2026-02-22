"""
Conditional formatting rules and dialog for table columns.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QLineEdit,
    QDialogButtonBox,
)
from PySide6.QtGui import QBrush, QColor


class ConditionalFormat:
    """Conditional formatting rule for a column."""

    HEATMAP = "heatmap"
    THRESHOLD = "threshold"
    DATA_BAR = "data_bar"

    def __init__(self, mode: str = "heatmap", min_color: str = "#2196F3",
                 max_color: str = "#F44336", threshold: float = 0,
                 threshold_color: str = "#F44336"):
        self.mode = mode
        self.min_color = QColor(min_color)
        self.max_color = QColor(max_color)
        self.threshold = threshold
        self.threshold_color = QColor(threshold_color)
        self._min_val: Optional[float] = None
        self._max_val: Optional[float] = None

    def set_range(self, min_val: float, max_val: float):
        self._min_val = min_val
        self._max_val = max_val

    def get_color(self, value) -> Optional[QBrush]:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None

        if self.mode == self.HEATMAP:
            if self._min_val is None or self._max_val is None:
                return None
            rng = self._max_val - self._min_val
            if rng == 0:
                return None
            t = max(0.0, min(1.0, (v - self._min_val) / rng))
            r = int(self.min_color.red() + t * (self.max_color.red() - self.min_color.red()))
            g = int(self.min_color.green() + t * (self.max_color.green() - self.min_color.green()))
            b = int(self.min_color.blue() + t * (self.max_color.blue() - self.min_color.blue()))
            color = QColor(r, g, b, 60)
            return QBrush(color)
        elif self.mode == self.THRESHOLD:
            if v >= self.threshold:
                return QBrush(QColor(self.threshold_color.red(), self.threshold_color.green(),
                                     self.threshold_color.blue(), 60))
            return None
        elif self.mode == self.DATA_BAR:
            # Data bar uses alpha to indicate magnitude
            if self._min_val is None or self._max_val is None:
                return None
            rng = self._max_val - self._min_val
            if rng == 0:
                return None
            t = max(0.0, min(1.0, (v - self._min_val) / rng))
            return QBrush(QColor(33, 150, 243, int(t * 80)))
        return None


# ==================== F3: Conditional Format Dialog ====================

class ConditionalFormatDialog(QDialog):
    """Dialog for configuring conditional formatting on a column."""

    def __init__(self, column_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Conditional Formatting: {column_name}")
        self.setMinimumWidth(300)
        self._column_name = column_name

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Heatmap", ConditionalFormat.HEATMAP)
        self.mode_combo.addItem("Data Bar", ConditionalFormat.DATA_BAR)
        self.mode_combo.addItem("Threshold", ConditionalFormat.THRESHOLD)
        self.mode_combo.addItem("(Remove)", "remove")
        form.addRow("Mode:", self.mode_combo)

        self.threshold_input = QLineEdit("0")
        self.threshold_input.setPlaceholderText("Threshold value")
        form.addRow("Threshold:", self.threshold_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_format(self) -> Optional[ConditionalFormat]:
        mode = self.mode_combo.currentData()
        if mode == "remove":
            return None
        try:
            threshold = float(self.threshold_input.text())
        except ValueError:
            threshold = 0
        return ConditionalFormat(mode=mode, threshold=threshold)
