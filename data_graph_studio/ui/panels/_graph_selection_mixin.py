"""Rectangular and lasso selection handling for MainGraph."""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainterPath
from PySide6.QtCore import QPointF

import pyqtgraph as pg

from ...core.state import ToolMode


class _GraphSelectionMixin:
    """Mixin providing data point selection logic for MainGraph.

    Requires: full MainGraph instance attributes set by MainGraph.__init__
    """

    def highlight_selection(self, selected_indices: List[int]):
        """Highlight selected data points on the graph"""
        # Remove previous selection highlight
        if hasattr(self, '_selection_scatter') and self._selection_scatter is not None:
            self.removeItem(self._selection_scatter)
            self._selection_scatter = None

        if not selected_indices or self._data_x is None or self._data_y is None:
            return

        # Get selected points
        valid_indices = [i for i in selected_indices if 0 <= i < len(self._data_x)]
        if not valid_indices:
            return

        selected_x = self._data_x[valid_indices]
        selected_y = self._data_y[valid_indices]

        # Create highlight scatter with distinct style
        self._selection_scatter = pg.ScatterPlotItem(
            x=selected_x,
            y=selected_y,
            size=12,
            pen=pg.mkPen('#EF4444', width=2),  # Red border
            brush=pg.mkBrush('#EF444480'),  # Semi-transparent red fill
            symbol='o',
            pxMode=True
        )
        self._selection_scatter.setZValue(100)  # Render on top
        self.addItem(self._selection_scatter)

    def mousePressEvent(self, event):
        """Handle mouse press for selection drag"""
        if self.state.tool_mode == ToolMode.RECT_SELECT:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._selection_start = pos
                self._is_selecting = True

                # Clear previous selection ROI
                if self._selection_roi is not None:
                    self.removeItem(self._selection_roi)
                    self._selection_roi = None

                # Store start position for rect
                self._rect_start_x = pos.x()
                self._rect_start_y = pos.y()

                event.accept()
                return

        elif self.state.tool_mode == ToolMode.LASSO_SELECT:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._selection_start = pos
                self._is_selecting = True

                # Clear previous lasso
                if self._lasso_path_item is not None:
                    self.removeItem(self._lasso_path_item)
                    self._lasso_path_item = None

                # Initialize lasso points
                self._lasso_points = [(pos.x(), pos.y())]

                event.accept()
                return

        # Drawing modes
        elif self.state.tool_mode in [ToolMode.LINE_DRAW, ToolMode.ARROW_DRAW, ToolMode.CIRCLE_DRAW,
                                       ToolMode.RECT_DRAW]:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._drawing_start = (pos.x(), pos.y())
                self._is_drawing = True

                # Clear any previous preview
                if self._drawing_preview_item is not None:
                    self.removeItem(self._drawing_preview_item)
                    self._drawing_preview_item = None

                event.accept()
                return

        elif self.state.tool_mode == ToolMode.TEXT_DRAW:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._handle_text_draw(pos.x(), pos.y())
                event.accept()
                return

        # Check for drawing click+drag (when not in a drawing-creation mode)
        if (
            self.state.tool_mode not in (
                ToolMode.LINE_DRAW, ToolMode.ARROW_DRAW, ToolMode.CIRCLE_DRAW,
                ToolMode.RECT_DRAW, ToolMode.TEXT_DRAW,
                ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT,
            )
            and event.button() == Qt.LeftButton
            and self._drawing_manager is not None
        ):
            pos = self.plotItem.vb.mapSceneToView(event.position())
            # Compute tolerance in data coordinates
            vr = self.viewRange()
            x_range = vr[0][1] - vr[0][0]
            tolerance = x_range * 0.02 if x_range > 0 else 5.0
            hit_id = self._drawing_manager.find_drawing_at(pos.x(), pos.y(), tolerance)
            if hit_id is not None:
                drawing = self._drawing_manager.get_drawing(hit_id)
                if drawing and not drawing.locked:
                    self._drawing_manager.select_drawing(hit_id)
                    self._dragging_drawing_id = hit_id
                    self._drag_last_pos = (pos.x(), pos.y())
                    self._drawing_manager._save_undo_state()
                    event.accept()
                    return
            else:
                # Click on empty area -> deselect
                self._drawing_manager.select_drawing(None)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for selection drag"""
        if self._is_selecting and self.state.tool_mode == ToolMode.RECT_SELECT:
            pos = self.plotItem.vb.mapSceneToView(event.position())

            # Update selection rectangle visualization
            if hasattr(self, '_rect_start_x'):
                x1 = min(self._rect_start_x, pos.x())
                y1 = min(self._rect_start_y, pos.y())
                width = abs(pos.x() - self._rect_start_x)
                height = abs(pos.y() - self._rect_start_y)

                if self._selection_roi is not None:
                    self.removeItem(self._selection_roi)

                # Draw selection rectangle
                rect = pg.QtWidgets.QGraphicsRectItem(x1, y1, width, height)
                rect.setPen(pg.mkPen((99, 102, 241), width=2, style=Qt.DashLine))
                rect.setBrush(pg.mkBrush(99, 102, 241, 30))
                self.addItem(rect)
                self._selection_roi = rect

            event.accept()
            return

        elif self._is_selecting and self.state.tool_mode == ToolMode.LASSO_SELECT:
            pos = self.plotItem.vb.mapSceneToView(event.position())

            # Add point to lasso path
            self._lasso_points.append((pos.x(), pos.y()))

            # Update lasso path visualization
            if self._lasso_path_item is not None:
                self.removeItem(self._lasso_path_item)

            if len(self._lasso_points) >= 2:
                # Create path
                path = QPainterPath()
                path.moveTo(QPointF(self._lasso_points[0][0], self._lasso_points[0][1]))
                for px, py in self._lasso_points[1:]:
                    path.lineTo(QPointF(px, py))
                # Close path back to start
                path.lineTo(QPointF(self._lasso_points[0][0], self._lasso_points[0][1]))

                # Create graphics item
                path_item = pg.QtWidgets.QGraphicsPathItem(path)
                path_item.setPen(pg.mkPen((236, 72, 153), width=2))  # Pink color
                path_item.setBrush(pg.mkBrush(236, 72, 153, 30))
                self.addItem(path_item)
                self._lasso_path_item = path_item

            event.accept()
            return

        # Drawing mode preview
        elif self._is_drawing and self.state.tool_mode in [ToolMode.LINE_DRAW,
                                                            ToolMode.ARROW_DRAW,
                                                            ToolMode.CIRCLE_DRAW,
                                                            ToolMode.RECT_DRAW]:
            pos = self.plotItem.vb.mapSceneToView(event.position())
            self._update_drawing_preview(pos.x(), pos.y())
            event.accept()
            return

        # Drawing drag-move
        if self._dragging_drawing_id is not None and self._drag_last_pos is not None:
            pos = self.plotItem.vb.mapSceneToView(event.position())
            dx = pos.x() - self._drag_last_pos[0]
            dy = pos.y() - self._drag_last_pos[1]
            drawing = self._drawing_manager.get_drawing(self._dragging_drawing_id)
            if drawing and hasattr(drawing, 'move'):
                drawing.move(dx, dy)
                self._drawing_manager.update_drawing(drawing)
                self._drag_last_pos = (pos.x(), pos.y())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release for selection, drawing, and view range recording"""
        handled = False

        if self._is_selecting and self.state.tool_mode == ToolMode.RECT_SELECT:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())

                if hasattr(self, '_rect_start_x'):
                    self._finish_rect_selection(pos)

                event.accept()
                handled = True

        elif self._is_selecting and self.state.tool_mode == ToolMode.LASSO_SELECT:
            if event.button() == Qt.LeftButton:
                self._finish_lasso_selection()
                event.accept()
                handled = True

        # Drawing mode finish
        elif self._is_drawing and self.state.tool_mode in [ToolMode.LINE_DRAW,
                                                            ToolMode.ARROW_DRAW,
                                                            ToolMode.CIRCLE_DRAW,
                                                            ToolMode.RECT_DRAW]:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._finish_drawing(pos.x(), pos.y())
                event.accept()
                handled = True

        # Drawing drag-move finish
        if self._dragging_drawing_id is not None and event.button() == Qt.LeftButton:
            self._dragging_drawing_id = None
            self._drag_last_pos = None
            handled = True

        if not handled:
            super().mouseReleaseEvent(event)

        # Always record view range after release
        self.push_view_range()

    def _finish_rect_selection(self, end_point):
        """Finish rectangle selection"""
        if self._data_x is None or self._data_y is None:
            self._cleanup_selection()
            return

        if not hasattr(self, '_rect_start_x'):
            self._cleanup_selection()
            return

        # Get bounds
        x1 = min(self._rect_start_x, end_point.x())
        x2 = max(self._rect_start_x, end_point.x())
        y1 = min(self._rect_start_y, end_point.y())
        y2 = max(self._rect_start_y, end_point.y())

        # Find points within rectangle
        selected_indices = []
        for i in range(len(self._data_x)):
            x, y = self._data_x[i], self._data_y[i]
            if x1 <= x <= x2 and y1 <= y <= y2:
                selected_indices.append(i)

        if selected_indices:
            self.points_selected.emit(selected_indices)
            self.state.select_rows(selected_indices)

        self._cleanup_selection()

    def _finish_lasso_selection(self):
        """Finish lasso selection - select points inside polygon"""
        if self._data_x is None or self._data_y is None:
            self._cleanup_lasso()
            return

        if len(self._lasso_points) < 3:
            self._cleanup_lasso()
            return

        # Use point-in-polygon algorithm
        selected_indices = []
        polygon = self._lasso_points

        for i in range(len(self._data_x)):
            x, y = self._data_x[i], self._data_y[i]
            if self._point_in_polygon(x, y, polygon):
                selected_indices.append(i)

        if selected_indices:
            self.points_selected.emit(selected_indices)
            self.state.select_rows(selected_indices)

        self._cleanup_lasso()

    def _point_in_polygon(self, x: float, y: float, polygon: list) -> bool:
        """Ray casting algorithm to check if point is inside polygon"""
        n = len(polygon)
        inside = False

        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]

            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i

        return inside

    def _cleanup_selection(self):
        """Clean up rect selection state"""
        if self._selection_roi is not None:
            self.removeItem(self._selection_roi)
            self._selection_roi = None

        self._is_selecting = False
        self._selection_start = None
        if hasattr(self, '_rect_start_x'):
            del self._rect_start_x
        if hasattr(self, '_rect_start_y'):
            del self._rect_start_y

    def _cleanup_lasso(self):
        """Clean up lasso selection state"""
        if self._lasso_path_item is not None:
            self.removeItem(self._lasso_path_item)
            self._lasso_path_item = None

        self._lasso_points = []
        self._is_selecting = False
        self._selection_start = None
