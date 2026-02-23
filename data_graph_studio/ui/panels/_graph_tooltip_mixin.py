"""Mouse hover tooltip and nearest-point detection for MainGraph."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np

import pyqtgraph as pg
from PySide6.QtWidgets import QInputDialog

logger = logging.getLogger(__name__)


class _GraphTooltipMixin:
    """Mixin providing hover tooltip behavior for MainGraph."""

    def _on_mouse_moved(self, pos):
        """Handle mouse move for hover tooltip"""
        if not self._hover_columns:
            self._hide_tooltip()
            return

        # Convert scene position to view coordinates
        mouse_point = self.plotItem.vb.mapSceneToView(pos)
        mx, my = mouse_point.x(), mouse_point.y()

        # Update crosshair position
        if self._crosshair_enabled and self.plotItem.vb.sceneBoundingRect().contains(pos):
            has_data = (self._data_x is not None and len(self._data_x) > 0) or bool(self._multi_series_data)
            self._crosshair_v.setPos(mx)
            self._crosshair_h.setPos(my)
            self._crosshair_v.setVisible(has_data)
            self._crosshair_h.setVisible(has_data)
        else:
            self._crosshair_v.setVisible(False)
            self._crosshair_h.setVisible(False)

        # Calculate distance to each point (normalized)
        view_range = self.viewRange()
        x_range = view_range[0][1] - view_range[0][0]
        y_range = view_range[1][1] - view_range[1][0]
        if x_range == 0 or y_range == 0:
            self._hide_tooltip()
            return

        # Multi-series hover (Compare/Overlay)
        if self._multi_series_data:
            best = None  # (dist, series_name, idx, x, y, hover_data)
            try:
                for series in self._multi_series_data:
                    x = series.get('x')
                    y = series.get('y')
                    if x is None or y is None or len(x) == 0:
                        continue

                    dx = (x - mx) / x_range
                    dy = (y - my) / y_range
                    distances = np.sqrt(dx**2 + dy**2)
                    distances = np.where(np.isnan(distances), np.inf, distances)
                    if np.all(np.isinf(distances)):
                        continue

                    idx = int(np.argmin(distances))
                    dist = float(distances[idx])
                    if np.isinf(dist):
                        continue

                    if best is None or dist < best[0]:
                        best = (
                            dist,
                            series.get('name', ''),
                            idx,
                            float(x[idx]),
                            float(y[idx]),
                            series.get('hover_data') or {},
                        )

                # Adaptive hover threshold based on total points across series
                _total_pts = sum(len(s.get('x', [])) for s in self._multi_series_data)
                _hover_thresh = 0.05 * max(1.0, min(3.0, 1000 / max(_total_pts, 1)))
                if best and best[0] < _hover_thresh:
                    _, series_name, idx, x_val, y_val, hover_data = best
                    self._show_tooltip(idx, x_val, y_val, series_name=series_name, hover_data=hover_data)
                else:
                    self._hide_tooltip()
            except Exception:
                logger.warning("main_graph.on_mouse_moved.multi_series_hover.error", exc_info=True)
                self._hide_tooltip()
            return

        # Single-series hover
        if self._data_x is None or self._data_y is None or self._hover_data is None:
            self._hide_tooltip()
            return
        if len(self._data_x) == 0:
            self._hide_tooltip()
            return

        try:
            dx = (self._data_x - mx) / x_range
            dy = (self._data_y - my) / y_range
            distances = np.sqrt(dx**2 + dy**2)
            distances = np.where(np.isnan(distances), np.inf, distances)
            if np.all(np.isinf(distances)):
                self._hide_tooltip()
                return

            nearest_idx = int(np.argmin(distances))
            min_dist = float(distances[nearest_idx])
            # Adaptive hover threshold
            _n_pts = len(self._data_x) if self._data_x is not None else 0
            _hover_thresh = 0.05 * max(1.0, min(3.0, 1000 / max(_n_pts, 1)))
            if min_dist < _hover_thresh and not np.isinf(min_dist):
                self._show_tooltip(nearest_idx, float(self._data_x[nearest_idx]), float(self._data_y[nearest_idx]))
            else:
                self._hide_tooltip()
        except Exception:
            logger.warning("main_graph.on_mouse_moved.single_series_hover.error", exc_info=True)
            self._hide_tooltip()

    def _show_tooltip(
        self,
        idx: int,
        x_val: float,
        y_val: float,
        series_name: str = "",
        hover_data: Optional[Dict[str, list]] = None,
    ):
        """Show tooltip at data point"""
        if self._tooltip_item is None:
            fill_color = '#FFFFFF' if self._is_light else '#323D4A'
            border_color = '#CCCCCC' if self._is_light else '#4A5568'
            text_color = '#111827' if self._is_light else '#E2E8F0'
            self._tooltip_item = pg.TextItem(anchor=(0, 1), fill=fill_color, border=border_color, color=text_color)
            self._tooltip_item.setZValue(1000)
            self.addItem(self._tooltip_item)

        hover_data = hover_data if hover_data is not None else (self._hover_data or {})

        # Build tooltip text
        lines = []
        if series_name:
            lines.append(f"Series: {series_name}")
        lines.extend([f"X: {self._format_value(x_val)}", f"Y: {self._format_value(y_val)}"])

        for col in self._hover_columns:
            if col in hover_data and idx < len(hover_data[col]):
                val = hover_data[col][idx]
                lines.append(f"{col}: {self._format_value(val)}")

        self._tooltip_item.setText("\n".join(lines))
        self._tooltip_item.setPos(x_val, y_val)
        self._tooltip_item.show()

    def _hide_tooltip(self):
        """Hide tooltip"""
        if self._tooltip_item is not None:
            self._tooltip_item.hide()

    def _format_value(self, val) -> str:
        """Format value for display"""
        if val is None:
            return "N/A"
        if isinstance(val, float):
            if abs(val) >= 1000000:
                return f"{val:.2e}"
            elif abs(val) >= 100:
                return f"{val:.1f}"
            else:
                return f"{val:.3f}"
        return str(val)

    def set_hover_data(self, hover_columns: List[str], hover_data: Dict[str, list]):
        """Set hover data columns and values"""
        self._hover_columns = hover_columns or []
        self._hover_data = hover_data or {}

    def _find_nearest_data_point(self, x: float, y: float):
        """Find the nearest data point to (x, y) in data coordinates.

        Returns (nearest_x, nearest_y, index) or None.
        """
        if self._data_x is None or self._data_y is None or len(self._data_x) == 0:
            return None
        vr = self.viewRange()
        x_range = max(vr[0][1] - vr[0][0], 1e-10)
        y_range = max(vr[1][1] - vr[1][0], 1e-10)
        # Normalised distance
        dx = (self._data_x - x) / x_range
        dy = (self._data_y - y) / y_range
        dist = dx * dx + dy * dy
        idx = int(np.nanargmin(dist))
        return float(self._data_x[idx]), float(self._data_y[idx]), idx

    def _prompt_add_annotation(self, data_x: float, data_y: float):
        """Show dialog and add annotation at given data point."""
        text, ok = QInputDialog.getText(
            self, "Add Annotation",
            f"Annotation text for point ({data_x:.4g}, {data_y:.4g}):"
        )
        if ok and text.strip():
            self.add_annotation(text.strip(), data_x, data_y)
