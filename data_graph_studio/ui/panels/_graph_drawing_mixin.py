"""Free-form drawing tools (line, rect, text) for MainGraph."""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtCore import QLineF
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import QDialog

import pyqtgraph as pg

from ...core.state import ToolMode
from ..drawing import (
    DrawingManager, DrawingStyle, LineDrawing, ArrowDrawing,
    CircleDrawing, RectDrawing, DrawingStyleDialog, TextInputDialog,
    snap_to_angle,
)

logger = logging.getLogger(__name__)


class _GraphDrawingMixin:
    """Mixin providing drawing tool management for MainGraph."""

    def set_drawing_manager(self, manager: DrawingManager):
        """Set the drawing manager"""
        self._drawing_manager = manager

    def get_drawing_manager(self) -> Optional[DrawingManager]:
        """Get the drawing manager"""
        return self._drawing_manager

    def set_drawing_style(self, style: DrawingStyle):
        """Set the current drawing style"""
        self._current_drawing_style = style

    def _update_drawing_preview(self, x: float, y: float):
        """Update drawing preview while dragging"""
        if not self._drawing_start:
            return

        x1, y1 = self._drawing_start
        x2, y2 = x, y

        # Apply Shift constraint
        if self._shift_pressed:
            if self.state.tool_mode in (ToolMode.LINE_DRAW, ToolMode.ARROW_DRAW):
                # Snap to 45-degree angles
                x2, y2 = snap_to_angle(x1, y1, x2, y2, 45.0)
            elif self.state.tool_mode == ToolMode.CIRCLE_DRAW:
                # Make perfect circle
                radius = max(abs(x2 - x1), abs(y2 - y1))
                x2 = x1 + radius if x2 > x1 else x1 - radius
                y2 = y1 + radius if y2 > y1 else y1 - radius
            elif self.state.tool_mode == ToolMode.RECT_DRAW:
                # Make perfect square
                size = max(abs(x2 - x1), abs(y2 - y1))
                x2 = x1 + size if x2 > x1 else x1 - size
                y2 = y1 + size if y2 > y1 else y1 - size

        # Remove old preview
        if self._drawing_preview_item is not None:
            self.removeItem(self._drawing_preview_item)
            self._drawing_preview_item = None

        # Create preview based on tool mode
        style = self._current_drawing_style
        pen = pg.mkPen(
            color=style.stroke_color,
            width=style.stroke_width,
            style=style.line_style.to_qt()
        )
        try:
            pen.setCosmetic(True)
        except Exception:
            logger.warning("main_graph.drawing_preview.set_cosmetic.error", exc_info=True)

        if self.state.tool_mode in (ToolMode.LINE_DRAW, ToolMode.ARROW_DRAW):
            # Line/Arrow preview (arrow head is drawn on final object)
            line = pg.QtWidgets.QGraphicsLineItem(QLineF(x1, y1, x2, y2))
            line.setPen(pen)
            self.addItem(line)
            self._drawing_preview_item = line

        elif self.state.tool_mode == ToolMode.CIRCLE_DRAW:
            # Circle/ellipse preview
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            rx = abs(x2 - x1) / 2
            ry = abs(y2 - y1) / 2
            ellipse = pg.QtWidgets.QGraphicsEllipseItem(
                cx - rx, cy - ry, rx * 2, ry * 2
            )
            ellipse.setPen(pen)
            if style.fill_color:
                fill = QColor(style.fill_color)
                fill.setAlphaF(style.fill_opacity)
                ellipse.setBrush(QBrush(fill))
            self.addItem(ellipse)
            self._drawing_preview_item = ellipse

        elif self.state.tool_mode == ToolMode.RECT_DRAW:
            # Rectangle preview
            rect_x = min(x1, x2)
            rect_y = min(y1, y2)
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            rect = pg.QtWidgets.QGraphicsRectItem(rect_x, rect_y, width, height)
            rect.setPen(pen)
            if style.fill_color:
                fill = QColor(style.fill_color)
                fill.setAlphaF(style.fill_opacity)
                rect.setBrush(QBrush(fill))
            self.addItem(rect)
            self._drawing_preview_item = rect

    def _finish_drawing(self, x: float, y: float):
        """Finish drawing and create the object"""
        if not self._drawing_start or not self._drawing_manager:
            self._cleanup_drawing()
            return

        x1, y1 = self._drawing_start
        x2, y2 = x, y

        # Apply Shift constraint
        if self._shift_pressed:
            if self.state.tool_mode in (ToolMode.LINE_DRAW, ToolMode.ARROW_DRAW):
                x2, y2 = snap_to_angle(x1, y1, x2, y2, 45.0)
            elif self.state.tool_mode == ToolMode.CIRCLE_DRAW:
                radius = max(abs(x2 - x1), abs(y2 - y1))
                x2 = x1 + radius if x2 > x1 else x1 - radius
                y2 = y1 + radius if y2 > y1 else y1 - radius
            elif self.state.tool_mode == ToolMode.RECT_DRAW:
                size = max(abs(x2 - x1), abs(y2 - y1))
                x2 = x1 + size if x2 > x1 else x1 - size
                y2 = y1 + size if y2 > y1 else y1 - size

        # Create drawing object
        style = DrawingStyle(
            stroke_color=self._current_drawing_style.stroke_color,
            stroke_width=self._current_drawing_style.stroke_width,
            line_style=self._current_drawing_style.line_style,
            fill_color=self._current_drawing_style.fill_color,
            fill_opacity=self._current_drawing_style.fill_opacity,
        )

        drawing = None

        if self.state.tool_mode == ToolMode.LINE_DRAW:
            drawing = LineDrawing(
                x1=x1, y1=y1, x2=x2, y2=y2,
                style=style
            )
        elif self.state.tool_mode == ToolMode.ARROW_DRAW:
            drawing = ArrowDrawing(
                x1=x1, y1=y1, x2=x2, y2=y2,
                style=style
            )
        elif self.state.tool_mode == ToolMode.CIRCLE_DRAW:
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            rx = abs(x2 - x1) / 2
            ry = abs(y2 - y1) / 2
            drawing = CircleDrawing(
                cx=cx, cy=cy, rx=rx, ry=ry,
                style=style
            )
        elif self.state.tool_mode == ToolMode.RECT_DRAW:
            rect_x = min(x1, x2)
            rect_y = min(y1, y2)
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            drawing = RectDrawing(
                x=rect_x, y=rect_y, width=width, height=height,
                style=style
            )

        if drawing:
            self._drawing_manager.add_drawing(drawing)

        self._cleanup_drawing()

    def _handle_text_draw(self, x: float, y: float):
        """Handle text drawing - show dialog"""
        if not self._drawing_manager:
            return

        dialog = TextInputDialog(self)
        if dialog.exec() == QDialog.Accepted:
            text_drawing = dialog.get_text_drawing(x, y)
            self._drawing_manager.add_drawing(text_drawing)

    def _cleanup_drawing(self):
        """Clean up drawing state"""
        if self._drawing_preview_item is not None:
            self.removeItem(self._drawing_preview_item)
            self._drawing_preview_item = None

        self._is_drawing = False
        self._drawing_start = None
