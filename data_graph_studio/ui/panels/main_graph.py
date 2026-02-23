"""
MainGraph - 메인 그래프 위젯 with hover tooltip support
"""

from typing import List

import logging

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from .graph_widgets import FormattedAxisItem
from ...core.state import AppState, ToolMode
from ..adapters.app_state_adapter import AppStateAdapter
from ..drawing import DrawingStyle

from ._graph_selection_mixin import _GraphSelectionMixin
from ._graph_drawing_mixin import _GraphDrawingMixin
from ._graph_tooltip_mixin import _GraphTooltipMixin
from ._graph_reference_mixin import _GraphReferenceMixin
from ._graph_plot_mixin import _GraphPlotMixin

logger = logging.getLogger(__name__)


# ==================== Annotation Item ====================

from ._annotation_item import AnnotationItem  # noqa: F401  (re-exported)


# ==================== Main Graph ====================

class MainGraph(
    _GraphSelectionMixin,
    _GraphDrawingMixin,
    _GraphTooltipMixin,
    _GraphReferenceMixin,
    _GraphPlotMixin,
    pg.PlotWidget,
):
    """메인 그래프 위젯 with hover tooltip support"""

    points_selected = Signal(list)

    def __init__(self, state: AppState):
        # Create custom axes
        self._x_axis = FormattedAxisItem('bottom')
        self._y_axis = FormattedAxisItem('left')

        super().__init__(axisItems={'bottom': self._x_axis, 'left': self._y_axis})
        self.state = state
        self._state_adapter = AppStateAdapter(state, parent=self)
        self._is_light = False  # Default: dark (midnight) theme

        # Ensure Y-axis label is not clipped (0 = auto-calculate)
        self._y_axis.setWidth(0)
        self.getPlotItem().getViewBox().setDefaultPadding(0.05)

        self.setBackground('#1E293B')
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setLabel('left', '')
        self.setLabel('bottom', '')

        self.legend = self.addLegend()
        self._legend_visible = True
        self._legend_position = (1, 1)  # Default: top right
        self._legend_default_anchor = ((1, 0), (1, 0), (-10, 10))  # top-right default

        # Make legend draggable
        try:
            self.legend.setFlag(
                self.legend.GraphicsItemFlag.ItemIsMovable, True
            )
        except Exception:
            logger.warning("main_graph.init.legend_movable.error", exc_info=True)

        self._plot_items = []
        self._scatter_items = []
        self._secondary_vb = None  # Secondary ViewBox for dual axis
        self._secondary_vb_items = []  # Items in secondary ViewBox
        self._data_x = None
        self._data_y = None

        # Multi-series (Compare/Overlay) hover support
        # series: [{'x': np.ndarray, 'y': np.ndarray, 'name': str, 'hover_data': {col: list}}, ...]
        self._multi_series_data = None

        # Selection highlight scatter
        self._selection_scatter = None

        # Hover data columns
        self._hover_columns: List[str] = []
        self._hover_data = None
        self._tooltip_item = None

        # Selection ROI
        self._selection_roi = None
        self._selection_start = None
        self._is_selecting = False

        # Lasso selection
        self._lasso_points = []  # List of (x, y) points for lasso path
        self._lasso_path_item = None  # Visual path item

        # Drawing mode
        self._is_drawing = False
        self._drawing_start = None
        self._drawing_preview_item = None
        self._drawing_manager = None
        self._current_drawing_style = DrawingStyle()
        self._shift_pressed = False

        # Drawing drag-move state
        self._dragging_drawing_id = None
        self._drag_last_pos = None  # (x, y) in view coords

        # View range undo/redo stack
        self._view_range_stack: list = []  # undo stack
        self._view_range_redo: list = []   # redo stack
        self._view_range_max = 50
        self._view_range_recording = True  # prevent recursive push
        self._last_recorded_range = None

        # Sampling status label
        self._sampling_label = pg.TextItem(
            text="",
            anchor=(0, 0),
            color='#C2C8D1'  # Dark theme default
        )
        self._sampling_label.setZValue(1000)
        self._sampling_label.setFont(pg.QtGui.QFont('Arial', 9))
        self.addItem(self._sampling_label)
        self._sampling_label.hide()

        # Reference lines and bands
        self._ref_lines: List[pg.InfiniteLine] = []
        self._ref_labels: List[pg.TextItem] = []
        self._ref_bands: List[pg.LinearRegionItem] = []
        self._ref_band_labels: List[pg.TextItem] = []

        # Trendline items
        self._trendline_items: list = []

        # Crosshair
        self._crosshair_enabled = True
        _ch_color = '#9CA3AF' if self._is_light else '#D1D5DB'
        _ch_pen = pg.mkPen(color=_ch_color, width=1, style=Qt.DashLine)
        self._crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=_ch_pen)
        self._crosshair_h = pg.InfiniteLine(angle=0, movable=False, pen=_ch_pen)
        self._crosshair_v.setZValue(999)
        self._crosshair_h.setZValue(999)
        for line in (self._crosshair_v, self._crosshair_h):
            line.setVisible(False)
            self.addItem(line)

        # Annotations
        self._annotations: List[AnnotationItem] = []

        # OpenGL state
        self._opengl_enabled = False

        # Enable mouse tracking for hover
        self.setMouseTracking(True)
        self.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        self.scene().sigMouseMoved.connect(self._on_mouse_moved)

        # Replace pyqtgraph default right-click menu with our own
        try:
            self.plotItem.vb.setMenuEnabled(False)
        except Exception:
            logger.warning("main_graph.init.disable_menu.error", exc_info=True)

        self._grid_visible = True

        # Connect to tool mode changes (via adapter)
        self._state_adapter.tool_mode_changed.connect(self._on_tool_mode_changed)

        # Apply initial tool mode
        self._on_tool_mode_changed()

    def enable_opengl(self, enable: bool = True):
        """Enable or disable OpenGL acceleration"""
        if enable and not self._opengl_enabled:
            try:
                self.useOpenGL(True)
                self._opengl_enabled = True
            except Exception as e:
                logger.error("main_graph.opengl_enable_error", extra={"error": str(e)}, exc_info=True)
        elif not enable and self._opengl_enabled:
            try:
                self.useOpenGL(False)
                self._opengl_enabled = False
            except Exception:
                logger.warning("main_graph.opengl_disable.error", exc_info=True)

    def update_sampling_status(
        self,
        displayed_points: int,
        total_points: int,
        is_sampled: bool,
        algorithm: str = ""
    ):
        """Update sampling status label"""
        if is_sampled and total_points > displayed_points:
            algo_text = f" [{algorithm}]" if algorithm else ""
            text = f"Showing {displayed_points:,} of {total_points:,} points{algo_text}"
            self._sampling_label.setText(text)

            # Position at top-left of the plot
            view_range = self.viewRange()
            x_pos = view_range[0][0]
            y_pos = view_range[1][1]
            self._sampling_label.setPos(x_pos, y_pos)
            self._sampling_label.show()
        else:
            self._sampling_label.hide()

    def _update_sampling_label_position(self):
        """Update sampling label position when view changes"""
        if self._sampling_label.isVisible():
            view_range = self.viewRange()
            x_pos = view_range[0][0]
            y_pos = view_range[1][1]
            self._sampling_label.setPos(x_pos, y_pos)

    def _on_tool_mode_changed(self):
        """Handle tool mode changes"""
        mode = self.state.tool_mode
        vb = self.plotItem.vb

        # Clear any existing selection ROI
        if self._selection_roi is not None:
            self.removeItem(self._selection_roi)
            self._selection_roi = None
        self._is_selecting = False

        # Clear any drawing in progress
        self._is_drawing = False
        if hasattr(self, '_drawing_preview_item') and self._drawing_preview_item is not None:
            self.removeItem(self._drawing_preview_item)
            self._drawing_preview_item = None

        if mode == ToolMode.ZOOM:
            # Zoom mode: left-click-drag to zoom into rect
            vb.setMouseMode(pg.ViewBox.RectMode)
            vb.setMouseEnabled(x=True, y=True)
            self.setCursor(Qt.CrossCursor)
        elif mode == ToolMode.PAN:
            # Pan mode: left-click-drag to pan
            vb.setMouseMode(pg.ViewBox.PanMode)
            vb.setMouseEnabled(x=True, y=True)
            self.setCursor(Qt.OpenHandCursor)
        elif mode in [ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT]:
            # Selection mode: disable default interactions
            vb.setMouseMode(pg.ViewBox.PanMode)  # Disable rect zoom
            vb.setMouseEnabled(x=False, y=False)  # Disable panning
            self.setCursor(Qt.CrossCursor)
        elif mode in [ToolMode.LINE_DRAW, ToolMode.ARROW_DRAW, ToolMode.CIRCLE_DRAW,
                      ToolMode.RECT_DRAW, ToolMode.TEXT_DRAW]:
            # Drawing mode: disable default interactions
            vb.setMouseMode(pg.ViewBox.PanMode)
            vb.setMouseEnabled(x=False, y=False)
            # Disable OpenGL in drawing mode to ensure custom items render
            self.enable_opengl(False)
            self.setCursor(Qt.CrossCursor)
        else:
            # Default mode
            vb.setMouseMode(pg.ViewBox.PanMode)
            vb.setMouseEnabled(x=True, y=True)
            self.setCursor(Qt.ArrowCursor)

    # ==================== Annotations ====================

    def add_annotation(self, text: str, data_x: float, data_y: float,
                       offset_x: float = 0.0, offset_y: float = 0.0) -> AnnotationItem:
        """Add a data-anchored annotation at (data_x, data_y)."""
        # Auto-compute offset from view range if not provided
        if offset_x == 0.0 and offset_y == 0.0:
            vr = self.viewRange()
            offset_x = (vr[0][1] - vr[0][0]) * 0.05
            offset_y = (vr[1][1] - vr[1][0]) * 0.08
        ann = AnnotationItem(text, data_x, data_y, offset_x, offset_y)
        self._annotations.append(ann)
        ann.add_to(self)
        return ann

    def remove_annotation(self, ann: AnnotationItem):
        """Remove a single annotation."""
        if ann in self._annotations:
            ann.remove_from(self)
            self._annotations.remove(ann)

    def clear_annotations(self):
        """Remove all annotations."""
        for ann in self._annotations:
            ann.remove_from(self)
        self._annotations.clear()

    def get_annotations_data(self) -> list:
        """Return serialisable list of annotation dicts."""
        return [a.to_dict() for a in self._annotations]

    def load_annotations(self, data: list):
        """Load annotations from serialised dicts."""
        self.clear_annotations()
        for d in data:
            ann = AnnotationItem.from_dict(d)
            self._annotations.append(ann)
            ann.add_to(self)

    # ==================== View helpers ====================

    def reset_view(self):
        try:
            self.getViewBox().autoRange(padding=0.05)
        except Exception:
            logger.warning("main_graph.reset_view.autorange.error", exc_info=True)
            self.autoRange()
        self.setLogMode(x=False, y=False)

    def _fit_to_selection(self):
        """Fit view range to selected points (best-effort)."""
        import numpy as np
        if self._data_x is None or self._data_y is None:
            self.reset_view()
            return

        sel = list(self.state.selection.selected_rows)
        if not sel:
            self.reset_view()
            return

        try:
            valid = [i for i in sel if 0 <= i < len(self._data_x)]
            if not valid:
                self.reset_view()
                return
            xs = self._data_x[valid]
            ys = self._data_y[valid]
            xs = xs[~np.isnan(xs.astype(float))] if hasattr(xs, 'astype') else xs
            ys = ys[~np.isnan(ys.astype(float))] if hasattr(ys, 'astype') else ys
            if len(xs) == 0 or len(ys) == 0:
                self.reset_view()
                return
            x_min, x_max = float(np.min(xs)), float(np.max(xs))
            y_min, y_max = float(np.min(ys)), float(np.max(ys))
            x_pad = (x_max - x_min) * 0.08 or 1.0
            y_pad = (y_max - y_min) * 0.08 or 1.0
            self.setXRange(x_min - x_pad, x_max + x_pad, padding=0)
            self.setYRange(y_min - y_pad, y_max + y_pad, padding=0)
        except Exception:
            logger.warning("main_graph.fit_to_selection.error", exc_info=True)
            self.reset_view()

    def _find_graph_panel(self):
        """Walk up parent chain to find GraphPanel instance."""
        from .graph_panel import GraphPanel
        widget = self.parent()
        while widget is not None:
            if isinstance(widget, GraphPanel):
                return widget
            widget = widget.parent() if hasattr(widget, 'parent') else None
        return None

    def _reset_legend_position(self):
        """Reset legend to default top-right position."""
        try:
            self.legend.anchor((1, 0), (1, 0), offset=(-10, 10))
        except Exception:
            logger.warning("main_graph.reset_legend_position.error", exc_info=True)

    def _toggle_grid(self):
        self._grid_visible = not getattr(self, '_grid_visible', True)
        self.showGrid(x=self._grid_visible, y=self._grid_visible, alpha=0.3)

    def _toggle_crosshair(self):
        self._crosshair_enabled = not self._crosshair_enabled
        if not self._crosshair_enabled:
            self._crosshair_v.setVisible(False)
            self._crosshair_h.setVisible(False)

    # ==================== Mouse / keyboard pass-throughs ====================

    def _on_mouse_clicked(self, event):
        """Handle mouse click - selection/drawing is handled via press/move/release"""
        # Selection and drawing modes are fully handled by
        # mousePressEvent / mouseMoveEvent / mouseReleaseEvent.
        # This handler is kept for potential future single-click actions.
        pass

    def wheelEvent(self, event):
        """휠 줌 후 view range 기록"""
        super().wheelEvent(event)
        self.push_view_range()

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key_Shift:
            self._shift_pressed = True
        elif event.key() == Qt.Key_Delete:
            # Delete selected drawing
            if self._drawing_manager:
                self._drawing_manager.delete_selected()
        elif event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            # Undo: view range first, then drawing
            if not self.undo_view_range():
                if self._drawing_manager:
                    self._drawing_manager.undo()
        elif event.key() == Qt.Key_Y and event.modifiers() & Qt.ControlModifier:
            # Redo: view range first, then drawing
            if not self.redo_view_range():
                if self._drawing_manager:
                    self._drawing_manager.redo()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Handle key release events"""
        if event.key() == Qt.Key_Shift:
            self._shift_pressed = False
        super().keyReleaseEvent(event)

    # ==================== Theme ====================

    def apply_theme(self, is_light: bool):
        """Apply theme colors to main graph"""
        self._is_light = is_light
        bg_color = '#F8FAFC' if is_light else '#1E293B'
        grid_color = '#E5E7EB' if is_light else '#374151'
        text_color = '#111827' if is_light else '#F1F5F9'

        self.setBackground(bg_color)

        # Update axis colors
        for axis_name in ['bottom', 'left']:
            axis = self.getAxis(axis_name)
            if axis:
                axis.setPen(pg.mkPen(grid_color))
                axis.setTextPen(pg.mkPen(text_color))

        # Update sampling label color
        if hasattr(self, '_sampling_label'):
            label_color = '#6B7280' if is_light else '#C2C8D1'
            self._sampling_label.setColor(label_color)

        # Update crosshair colors
        if hasattr(self, '_crosshair_v'):
            ch_color = '#9CA3AF' if is_light else '#D1D5DB'
            ch_pen = pg.mkPen(color=ch_color, width=1, style=Qt.DashLine)
            self._crosshair_v.setPen(ch_pen)
            self._crosshair_h.setPen(ch_pen)

        # Reset tooltip so it gets recreated with correct theme colors
        if hasattr(self, '_tooltip_item') and self._tooltip_item is not None:
            self.removeItem(self._tooltip_item)
            self._tooltip_item = None


# ==================== Graph Panel ====================
