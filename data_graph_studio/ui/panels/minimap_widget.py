"""Minimap widget for graph zoom overview"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor


class MinimapWidget(pg.PlotWidget):
    """
    A compact plot showing the full dataset with a draggable region
    indicating the current zoom level of the main graph.

    Height: 70px fixed
    Features:
    - Full dataset rendered as simplified line/area
    - LinearRegionItem for current view range
    - Dragging region updates main graph view
    - Main graph zoom/pan updates region position
    """

    region_changed = Signal(float, float)  # x_min, x_max

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()
        self.setMenuEnabled(False)

        # Remove axis labels for compact look
        self.getAxis('left').hide()
        self.getAxis('bottom').setHeight(15)
        self.getAxis('bottom').setStyle(tickLength=-5)

        # Region selector
        self._region = pg.LinearRegionItem(swapMode='sort')
        self._region.setZValue(10)
        self.addItem(self._region)
        self._region.sigRegionChanged.connect(self._on_region_changed)

        # Data plot item
        self._data_item = None
        self._fill_item = None

        # Theme
        self._is_light = False
        self.apply_theme(False)

    def set_data(self, x_data: np.ndarray, y_data: np.ndarray):
        """Set the overview data. Downsample if needed for performance."""
        # Remove old items
        if self._data_item:
            self.removeItem(self._data_item)
        if self._fill_item:
            self.removeItem(self._fill_item)

        if x_data is None or y_data is None or len(x_data) == 0:
            self._data_item = None
            return

        # Ensure float arrays for safe math
        try:
            x_data = np.asarray(x_data, dtype=np.float64)
            y_data = np.asarray(y_data, dtype=np.float64)
        except (ValueError, TypeError):
            self._data_item = None
            return

        # Remove NaN
        mask = ~(np.isnan(x_data) | np.isnan(y_data))
        x_data = x_data[mask]
        y_data = y_data[mask]
        if len(x_data) == 0:
            self._data_item = None
            return

        # Downsample to max 500 points for performance
        if len(x_data) > 500:
            step = len(x_data) // 500
            x_data = x_data[::step]
            y_data = y_data[::step]

        # Plot as filled area for visual weight
        line_color = '#94A3B8' if self._is_light else '#64748B'
        fill_color = QColor('#CBD5E1' if self._is_light else '#334155')
        fill_color.setAlpha(100)

        pen = pg.mkPen(line_color, width=1)
        fill_level = float(y_data.min()) if len(y_data) > 0 else 0
        self._data_item = self.plot(
            x_data, y_data, pen=pen,
            fillLevel=fill_level, brush=fill_color,
        )

        # Auto range
        self.setXRange(float(x_data.min()), float(x_data.max()), padding=0.01)
        self.setYRange(float(y_data.min()), float(y_data.max()), padding=0.05)

    def set_region(self, x_min: float, x_max: float):
        """Update the visible region (called when main graph zooms/pans)"""
        self._region.blockSignals(True)
        self._region.setRegion([x_min, x_max])
        self._region.blockSignals(False)

    def _on_region_changed(self):
        """User dragged the region"""
        min_val, max_val = self._region.getRegion()
        self.region_changed.emit(min_val, max_val)

    def apply_theme(self, is_light: bool):
        self._is_light = is_light
        bg = '#F1F5F9' if is_light else '#0F172A'
        self.setBackground(bg)

        region_color = QColor('#3B82F6')
        region_color.setAlpha(40)
        border_color = QColor('#3B82F6')
        border_color.setAlpha(150)
        self._region.setBrush(region_color)
        # Lines on edges
        for line in self._region.lines:
            line.setPen(pg.mkPen(border_color, width=1))

        # Axis
        axis_color = '#94A3B8' if is_light else '#475569'
        self.getAxis('bottom').setPen(pg.mkPen(axis_color))
        self.getAxis('bottom').setTextPen(pg.mkPen(axis_color))

    def clear_minimap(self):
        if self._data_item:
            self.removeItem(self._data_item)
            self._data_item = None
        if self._fill_item:
            self.removeItem(self._fill_item)
            self._fill_item = None
