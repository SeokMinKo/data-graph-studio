"""
MiniGraphWidget — PRD v2 Feature 1 (§9.1)

Lightweight chart widget for dashboard cells.
- Independent zoom/pan
- LTTB downsampling (NFR-1.4)
- Cell header: profile name + row count
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from ...core.dashboard_layout import MIN_CELL_WIDTH, MIN_CELL_HEIGHT
from ...graph.sampling import DataSampler

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover – allow import when pyqtgraph unavailable
    pg = None  # type: ignore

if TYPE_CHECKING:
    pass


class MiniGraphWidget(QFrame):
    """
    Compact chart widget placed in each dashboard cell.

    Signals
    -------
    focused : emitted when user clicks on this widget.
    x_range_changed : (xmin, xmax) emitted on zoom/pan — used for sync.
    y_range_changed : (ymin, ymax) emitted on zoom/pan — used for sync.
    """

    focused = Signal()
    x_range_changed = Signal(float, float)
    y_range_changed = Signal(float, float)

    def __init__(
        self,
        profile_name: str = "",
        row_count: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._profile_name = profile_name
        self._row_count = row_count
        self._x_data: Optional[np.ndarray] = None
        self._y_data: Optional[np.ndarray] = None
        self._plot_item = None

        self.setMinimumSize(MIN_CELL_WIDTH, MIN_CELL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self._build_ui()

    # -- UI -----------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        # Header: profile name + row count
        header_text = self._profile_name or "(empty)"
        if self._row_count:
            header_text += f"  ({self._row_count:,} rows)"
        self._header = QLabel(header_text)
        self._header.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #333;"
            "text-overflow: ellipsis; white-space: nowrap;"
        )
        self._header.setMaximumHeight(18)
        layout.addWidget(self._header)

        # Chart area
        if pg is not None:
            self._plot = pg.PlotWidget()
            self._plot.setBackground("w")
            self._plot.showGrid(x=True, y=True, alpha=0.15)
            self._plot.getViewBox().sigRangeChanged.connect(self._on_range_changed)
            layout.addWidget(self._plot, stretch=1)
        else:
            placeholder = QLabel("pyqtgraph not available")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(placeholder, stretch=1)

    # -- data ---------------------------------------------------------------

    def set_data(
        self,
        x: np.ndarray,
        y: np.ndarray,
        color: str = "#1f77b4",
        line_width: int = 1,
    ) -> None:
        """
        Set chart data with automatic LTTB downsampling (NFR-1.4).

        Downsamples when data points > cell_width * 4.
        """
        self._x_data = x
        self._y_data = y

        if pg is None:
            return

        threshold = max(self.width(), MIN_CELL_WIDTH) * 4
        if len(x) > threshold:
            sx, sy = DataSampler.lttb(x, y, threshold)
        else:
            sx, sy = x, y

        self._plot.clear()
        pen = pg.mkPen(color=color, width=line_width)
        self._plot_item = self._plot.plot(sx, sy, pen=pen)

    def refresh_sampling(self) -> None:
        """Re-downsample after zoom/resize using original data."""
        if self._x_data is not None and self._y_data is not None:
            self.set_data(self._x_data, self._y_data)

    # -- sync helpers -------------------------------------------------------

    def set_x_range(self, xmin: float, xmax: float) -> None:
        if pg is not None:
            self._plot.setXRange(xmin, xmax, padding=0)

    def set_y_range(self, ymin: float, ymax: float) -> None:
        if pg is not None:
            self._plot.setYRange(ymin, ymax, padding=0)

    def _on_range_changed(self, vb, ranges) -> None:
        if ranges and len(ranges) >= 2:
            xr = ranges[0]
            yr = ranges[1]
            self.x_range_changed.emit(float(xr[0]), float(xr[1]))
            self.y_range_changed.emit(float(yr[0]), float(yr[1]))

    # -- focus --------------------------------------------------------------

    def mousePressEvent(self, event):  # noqa: N802
        self.focused.emit()
        super().mousePressEvent(event)

    # -- cleanup ------------------------------------------------------------

    def cleanup(self) -> None:
        """Disconnect signals, prepare for deletion (§10.1)."""
        if pg is not None and hasattr(self, "_plot"):
            try:
                self._plot.getViewBox().sigRangeChanged.disconnect(self._on_range_changed)
            except (RuntimeError, TypeError):
                pass
            self._plot.clear()
