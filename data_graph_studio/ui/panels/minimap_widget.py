"""Minimap widget for graph zoom overview."""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Signal
from PySide6.QtGui import QColor


class MinimapWidget(pg.PlotWidget):
    """StarCraft-style minimap for dataset overview + viewport navigation.

    Features
    --------
    - Always renders full dataset extent (overview)
    - Displays current main-graph viewport as a draggable rectangle (ROI)
    - Dragging the rectangle emits x/y range updates
    - Internal downsampling cap for performance (50k points)
    """

    MAX_OVERVIEW_POINTS = 50_000

    # x_min, x_max, y_min, y_max
    region_changed = Signal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(96)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()
        self.setMenuEnabled(False)

        # Compact axes style
        self.getAxis("left").hide()
        self.getAxis("bottom").setHeight(14)
        self.getAxis("bottom").setStyle(tickLength=-4)

        # Overview data plot
        self._data_item: Optional[pg.PlotDataItem] = None

        # Full data bounds (x_min, x_max, y_min, y_max)
        self._data_bounds: Optional[Tuple[float, float, float, float]] = None

        # Guard for recursive updates while syncing with main graph
        self._syncing_region = False

        # Viewport rectangle
        self._viewport_roi = pg.RectROI(
            [0.0, 0.0],
            [1.0, 1.0],
            pen=pg.mkPen("#3B82F6", width=1.5),
            movable=True,
            removable=False,
            rotatable=False,
            resizable=False,
        )
        self._viewport_roi.setZValue(10)
        self.addItem(self._viewport_roi)
        self._viewport_roi.sigRegionChanged.connect(self._on_viewport_changed)

        self._is_light = False
        self.apply_theme(False)

    # ----------------------------- data API -----------------------------

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray) -> None:
        """Set overview data (capped to MAX_OVERVIEW_POINTS for performance)."""
        if self._data_item is not None:
            self.removeItem(self._data_item)
            self._data_item = None

        if x_data is None or y_data is None:
            self._data_bounds = None
            return

        try:
            x_arr = np.asarray(x_data, dtype=np.float64)
            y_arr = np.asarray(y_data, dtype=np.float64)
        except (ValueError, TypeError):
            self._data_bounds = None
            return

        if x_arr.size == 0 or y_arr.size == 0:
            self._data_bounds = None
            return

        mask = ~(np.isnan(x_arr) | np.isnan(y_arr))
        x_arr = x_arr[mask]
        y_arr = y_arr[mask]
        if x_arr.size == 0:
            self._data_bounds = None
            return

        x_min = float(np.min(x_arr))
        x_max = float(np.max(x_arr))
        y_min = float(np.min(y_arr))
        y_max = float(np.max(y_arr))

        # avoid degenerate bounds
        if x_min == x_max:
            x_max = x_min + 1.0
        if y_min == y_max:
            y_max = y_min + 1.0

        self._data_bounds = (x_min, x_max, y_min, y_max)

        # Downsample for minimap rendering only
        if x_arr.size > self.MAX_OVERVIEW_POINTS:
            step = int(np.ceil(x_arr.size / self.MAX_OVERVIEW_POINTS))
            x_arr = x_arr[::step]
            y_arr = y_arr[::step]

        line_color = "#94A3B8" if self._is_light else "#64748B"
        fill_color = QColor("#CBD5E1" if self._is_light else "#334155")
        fill_color.setAlpha(95)

        self._data_item = self.plot(
            x_arr,
            y_arr,
            pen=pg.mkPen(line_color, width=1),
            fillLevel=float(np.min(y_arr)) if y_arr.size else 0.0,
            brush=fill_color,
        )

        self.setXRange(x_min, x_max, padding=0.01)
        self.setYRange(y_min, y_max, padding=0.05)

        # Ensure viewport exists inside bounds
        self._clamp_viewport_to_bounds()

    def get_data_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        return self._data_bounds

    # --------------------------- region sync API ---------------------------

    def set_region(self, x_min: float, x_max: float, y_min: Optional[float] = None, y_max: Optional[float] = None) -> None:
        """Set viewport rectangle from main graph view range."""
        if self._data_bounds is None:
            return

        bx_min, bx_max, by_min, by_max = self._data_bounds

        if y_min is None or y_max is None:
            # Backward-compatible: if only x-range provided, keep current y-range
            pos = self._viewport_roi.pos()
            size = self._viewport_roi.size()
            y_min = float(pos.y())
            y_max = float(pos.y() + size.y())

        # normalize & clamp
        x1, x2 = sorted((float(x_min), float(x_max)))
        y1, y2 = sorted((float(y_min), float(y_max)))
        x1 = max(bx_min, min(x1, bx_max))
        x2 = max(bx_min, min(x2, bx_max))
        y1 = max(by_min, min(y1, by_max))
        y2 = max(by_min, min(y2, by_max))

        if x1 == x2:
            x2 = min(bx_max, x1 + max((bx_max - bx_min) * 0.01, 1e-6))
        if y1 == y2:
            y2 = min(by_max, y1 + max((by_max - by_min) * 0.01, 1e-6))

        self._syncing_region = True
        try:
            self._viewport_roi.setPos((x1, y1), finish=False)
            self._viewport_roi.setSize((x2 - x1, y2 - y1), finish=False)
        finally:
            self._syncing_region = False

    def _on_viewport_changed(self) -> None:
        if self._syncing_region or self._data_bounds is None:
            return

        self._clamp_viewport_to_bounds()

        pos = self._viewport_roi.pos()
        size = self._viewport_roi.size()
        x_min = float(pos.x())
        y_min = float(pos.y())
        x_max = x_min + float(size.x())
        y_max = y_min + float(size.y())

        self.region_changed.emit(x_min, x_max, y_min, y_max)

    def _clamp_viewport_to_bounds(self) -> None:
        if self._data_bounds is None:
            return

        bx_min, bx_max, by_min, by_max = self._data_bounds
        pos = self._viewport_roi.pos()
        size = self._viewport_roi.size()

        width = float(size.x())
        height = float(size.y())
        if width <= 0:
            width = max((bx_max - bx_min) * 0.1, 1e-6)
        if height <= 0:
            height = max((by_max - by_min) * 0.1, 1e-6)

        width = min(width, bx_max - bx_min)
        height = min(height, by_max - by_min)

        x = float(pos.x())
        y = float(pos.y())

        x = min(max(x, bx_min), bx_max - width)
        y = min(max(y, by_min), by_max - height)

        self._syncing_region = True
        try:
            self._viewport_roi.setPos((x, y), finish=False)
            self._viewport_roi.setSize((width, height), finish=False)
        finally:
            self._syncing_region = False

    # ----------------------------- styling -----------------------------

    def apply_theme(self, is_light: bool) -> None:
        self._is_light = is_light

        bg = "#F8FAFC" if is_light else "#0B1220"
        self.setBackground(bg)

        border = QColor("#3B82F6")
        border.setAlpha(190)
        self._viewport_roi.setPen(pg.mkPen(border, width=1.5))

        axis_color = "#94A3B8" if is_light else "#475569"
        self.getAxis("bottom").setPen(pg.mkPen(axis_color))
        self.getAxis("bottom").setTextPen(pg.mkPen(axis_color))

    def clear_minimap(self) -> None:
        if self._data_item is not None:
            self.removeItem(self._data_item)
            self._data_item = None
        self._data_bounds = None
