"""Reference lines, bands, and trendline overlays for MainGraph."""
from __future__ import annotations

import logging

import numpy as np

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QInputDialog

logger = logging.getLogger(__name__)


class _GraphReferenceMixin:
    """Mixin providing reference line and trendline overlays for MainGraph."""

    def add_reference_line(self, value: float, orientation='horizontal',
                           color='#EF4444', style=Qt.DashLine, width=1,
                           label: str = None):
        """Add a reference line at a specific value."""
        angle = 0 if orientation == 'horizontal' else 90
        line = pg.InfiniteLine(
            pos=value, angle=angle,
            pen=pg.mkPen(color, width=width, style=style)
        )
        line.setZValue(50)
        self.addItem(line)
        self._ref_lines.append(line)

        if label:
            lbl_color = color
            label_item = pg.TextItem(label, anchor=(0, 1), color=lbl_color)
            label_item.setZValue(51)
            if orientation == 'horizontal':
                vr = self.viewRange()
                label_item.setPos(vr[0][0], value)
            else:
                vr = self.viewRange()
                label_item.setPos(value, vr[1][1])
            self.addItem(label_item)
            self._ref_labels.append(label_item)

    def add_reference_band(self, y_min: float, y_max: float,
                           color='#3B82F6', alpha=0.1, label: str = None):
        """Add a horizontal band between two values."""
        band_color = QColor(color)
        band_color.setAlphaF(alpha)
        region = pg.LinearRegionItem(
            values=(y_min, y_max),
            orientation='horizontal',
            brush=pg.mkBrush(band_color),
            pen=pg.mkPen(color, width=1, style=Qt.DotLine),
            movable=False
        )
        region.setZValue(10)
        self.addItem(region)
        self._ref_bands.append(region)

        if label:
            lbl_color = color
            label_item = pg.TextItem(label, anchor=(0, 1), color=lbl_color)
            label_item.setZValue(11)
            vr = self.viewRange()
            label_item.setPos(vr[0][0], y_max)
            self.addItem(label_item)
            self._ref_band_labels.append(label_item)

    def clear_reference_lines(self):
        """Remove all reference lines and bands."""
        for item in self._ref_lines:
            self.removeItem(item)
        self._ref_lines.clear()
        for item in self._ref_labels:
            self.removeItem(item)
        self._ref_labels.clear()
        for item in self._ref_bands:
            self.removeItem(item)
        self._ref_bands.clear()
        for item in self._ref_band_labels:
            self.removeItem(item)
        self._ref_band_labels.clear()

    def _add_mean_line(self):
        """Add mean reference line from current Y data."""
        if self._data_y is None or len(self._data_y) == 0:
            return
        y = self._data_y.astype(float)
        y = y[~np.isnan(y)]
        if len(y) == 0:
            return
        mean_val = float(np.mean(y))
        self.add_reference_line(mean_val, label=f'Mean: {mean_val:.4g}')

    def _add_median_line(self):
        """Add median reference line from current Y data."""
        if self._data_y is None or len(self._data_y) == 0:
            return
        y = self._data_y.astype(float)
        y = y[~np.isnan(y)]
        if len(y) == 0:
            return
        med_val = float(np.median(y))
        self.add_reference_line(med_val, color='#8B5CF6', label=f'Median: {med_val:.4g}')

    def _add_custom_line(self):
        """Add a custom reference line via input dialog."""
        val, ok = QInputDialog.getDouble(self, "Custom Reference Line", "Value:", 0.0, -1e15, 1e15, 4)
        if ok:
            self.add_reference_line(val, color='#10B981', label=f'Ref: {val:.4g}')

    def _add_sigma_band(self):
        """Add ±1σ band around mean."""
        if self._data_y is None or len(self._data_y) == 0:
            return
        y = self._data_y.astype(float)
        y = y[~np.isnan(y)]
        if len(y) == 0:
            return
        mean_val = float(np.mean(y))
        std_val = float(np.std(y))
        self.add_reference_band(
            mean_val - std_val, mean_val + std_val,
            color='#6366F1', alpha=0.08,
            label=f'±1σ ({mean_val - std_val:.4g} – {mean_val + std_val:.4g})'
        )
        # Also add mean line
        self.add_reference_line(mean_val, color='#6366F1', style=Qt.DashDotLine,
                                label=f'μ: {mean_val:.4g}')

    def add_trendline(self, x_data, y_data, degree=1, color='#F59E0B',
                      label=None, is_exponential=False):
        """Add polynomial or exponential trendline."""
        # Clean NaN
        mask = ~(np.isnan(x_data.astype(float)) | np.isnan(y_data.astype(float)))
        x_clean = x_data[mask].astype(float)
        y_clean = y_data[mask].astype(float)
        if len(x_clean) < 2:
            return

        try:
            if is_exponential:
                # Exponential fit: y = a * exp(b * x)
                y_pos = y_clean[y_clean > 0]
                x_pos = x_clean[y_clean > 0]
                if len(y_pos) < 2:
                    return
                log_y = np.log(y_pos)
                coeffs = np.polyfit(x_pos, log_y, 1)
                x_smooth = np.linspace(x_clean.min(), x_clean.max(), 200)
                y_smooth = np.exp(coeffs[1]) * np.exp(coeffs[0] * x_smooth)
                # R² on original scale
                y_pred = np.exp(coeffs[1]) * np.exp(coeffs[0] * x_pos)
                ss_res = np.sum((y_pos - y_pred) ** 2)
                ss_tot = np.sum((y_pos - np.mean(y_pos)) ** 2)
                deg_label = 'Exp'
            else:
                coeffs = np.polyfit(x_clean, y_clean, degree)
                poly = np.poly1d(coeffs)
                x_smooth = np.linspace(x_clean.min(), x_clean.max(), 200)
                y_smooth = poly(x_smooth)
                # R²
                y_pred = poly(x_clean)
                ss_res = np.sum((y_clean - y_pred) ** 2)
                ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)
                deg_label = f'deg={degree}'

            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

            pen = pg.mkPen(color, width=2, style=Qt.DashDotLine)
            curve_name = label or f'Trend ({deg_label})'
            item = self.plot(x_smooth, y_smooth, pen=pen, name=curve_name)
            self._trendline_items.append(item)

            # R² text
            text_color = color
            r2_text = pg.TextItem(f'R² = {r_squared:.4f}', anchor=(1, 0), color=text_color)
            r2_text.setZValue(52)
            r2_text.setPos(float(x_smooth[-1]), float(y_smooth[-1]))
            self.addItem(r2_text)
            self._trendline_items.append(r2_text)
        except Exception:
            logger.exception("main_graph.draw_trendline.error")

    def clear_trendlines(self):
        """Remove all trendlines."""
        for item in self._trendline_items:
            self.removeItem(item)
        self._trendline_items.clear()

    def _add_trendline_degree(self, degree: int):
        """Add trendline with given polynomial degree from current data."""
        if self._data_x is None or self._data_y is None:
            return
        colors = {1: '#F59E0B', 2: '#EC4899', 3: '#14B8A6'}
        self.add_trendline(self._data_x, self._data_y, degree=degree,
                           color=colors.get(degree, '#F59E0B'))

    def _add_exponential_trendline(self):
        """Add exponential trendline from current data."""
        if self._data_x is None or self._data_y is None:
            return
        self.add_trendline(self._data_x, self._data_y, degree=1,
                           color='#F97316', is_exponential=True)
