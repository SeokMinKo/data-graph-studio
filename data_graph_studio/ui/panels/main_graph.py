"""
MainGraph - 메인 그래프 위젯 with hover tooltip support
"""

import math
from typing import Any, Dict, List, Optional

import csv
import logging

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QAction
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QDialog

from .graph_widgets import FormattedAxisItem
from ...core.state import AppState, ChartType, ToolMode
from ..drawing import (
    DrawingManager, DrawingStyle, LineStyle,
    LineDrawing, ArrowDrawing, CircleDrawing, RectDrawing, TextDrawing,
    DrawingStyleDialog, RectStyleDialog, TextInputDialog,
    snap_to_angle
)

logger = logging.getLogger(__name__)


# ==================== Annotation Item ====================

class AnnotationItem:
    """Data-anchored annotation with leader line.

    Renders a text label near a data point with a dashed leader line
    connecting the label to the exact data coordinates.  Both items
    are positioned in *data* coordinates so they follow zoom/pan.
    """

    def __init__(self, text: str, data_x: float, data_y: float,
                 offset_x: float = 0.0, offset_y: float = 0.0,
                 color: str = '#FBBF24', uid: str = ''):
        self.data_x = data_x
        self.data_y = data_y
        self.uid = uid or str(id(self))
        self.offset_x = offset_x
        self.offset_y = offset_y

        # Text item
        self.text_item = pg.TextItem(
            text=text,
            anchor=(0, 1),
            color=color,
            border=pg.mkPen('#888', width=1),
            fill=pg.mkBrush('#1E293BCC'),
        )
        self.text_item.setFont(pg.QtGui.QFont('Arial', 10))
        self.text_item.setZValue(200)

        # Leader line (data_point → label)
        self.leader = pg.PlotCurveItem(
            pen=pg.mkPen('#888', width=1, style=Qt.DashLine)
        )
        self.leader.setZValue(199)

        # Marker dot at the data point
        self.marker = pg.ScatterPlotItem(
            [data_x], [data_y], size=8,
            pen=pg.mkPen(color, width=2),
            brush=pg.mkBrush(color),
            symbol='o',
        )
        self.marker.setZValue(201)

        self._update_position()

    def _update_position(self):
        label_x = self.data_x + self.offset_x
        label_y = self.data_y + self.offset_y
        self.text_item.setPos(label_x, label_y)
        self.leader.setData([self.data_x, label_x], [self.data_y, label_y])

    def set_offset(self, ox: float, oy: float):
        self.offset_x = ox
        self.offset_y = oy
        self._update_position()

    def add_to(self, plot_widget: pg.PlotWidget):
        plot_widget.addItem(self.text_item)
        plot_widget.addItem(self.leader)
        plot_widget.addItem(self.marker)

    def remove_from(self, plot_widget: pg.PlotWidget):
        plot_widget.removeItem(self.text_item)
        plot_widget.removeItem(self.leader)
        plot_widget.removeItem(self.marker)

    def get_text(self) -> str:
        return self.text_item.textItem.toPlainText()

    def to_dict(self) -> dict:
        return {
            'text': self.get_text(),
            'data_x': self.data_x,
            'data_y': self.data_y,
            'offset_x': self.offset_x,
            'offset_y': self.offset_y,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'AnnotationItem':
        return cls(
            text=d['text'],
            data_x=d['data_x'],
            data_y=d['data_y'],
            offset_x=d.get('offset_x', 0.0),
            offset_y=d.get('offset_y', 0.0),
        )


# ==================== Main Graph ====================

class MainGraph(pg.PlotWidget):
    """메인 그래프 위젯 with hover tooltip support"""

    points_selected = Signal(list)

    @staticmethod
    def _normalize_range_for_log(min_val: float, max_val: float):
        """Convert a linear-domain range to log10-domain for pyqtgraph log axes."""
        try:
            lo = float(min_val)
            hi = float(max_val)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(lo) or not math.isfinite(hi):
            return None

        lo, hi = sorted((lo, hi))
        if hi <= 0:
            return None

        tiny = np.nextafter(0.0, 1.0)
        lo = max(lo, tiny)
        hi = max(hi, tiny)
        return math.log10(lo), math.log10(hi)

    def __init__(self, state: AppState):
        # Create custom axes
        self._x_axis = FormattedAxisItem('bottom')
        self._y_axis = FormattedAxisItem('left')

        super().__init__(axisItems={'bottom': self._x_axis, 'left': self._y_axis})
        self.state = state
        self._is_light = False  # Default: dark (midnight) theme

        # Ensure Y-axis tick labels remain visible.
        self._y_axis.setStyle(showValues=True, autoExpandTextSpace=True, tickTextWidth=70)
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
            logger.debug("Legend drag not supported in this pyqtgraph version")

        self._plot_items = []
        self._scatter_items = []
        self._secondary_vb = None  # Secondary ViewBox for dual axis
        self._secondary_vb_items = []  # Items in secondary ViewBox
        self._data_x = None
        self._data_y = None

        # Multi-series (Compare/Overlay) hover support
        # series: [{'x': np.ndarray, 'y': np.ndarray, 'name': str, 'hover_data': {col: list}}, ...]
        self._multi_series_data: Optional[List[Dict[str, Any]]] = None

        # Selection highlight scatter
        self._selection_scatter = None

        # Hover data columns
        self._hover_columns: List[str] = []
        self._hover_data: Optional[Dict[str, list]] = None
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
        self._drawing_manager: Optional[DrawingManager] = None
        self._current_drawing_style = DrawingStyle()
        self._shift_pressed = False

        # Drawing drag-move state
        self._dragging_drawing_id: Optional[str] = None
        self._drag_last_pos: Optional[tuple] = None  # (x, y) in view coords

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
            logger.debug("Could not disable default pyqtgraph context menu")

        self._grid_visible = True

        # Connect to tool mode changes
        self.state.tool_mode_changed.connect(self._on_tool_mode_changed)

        # Apply initial tool mode
        self._on_tool_mode_changed()

    def enable_opengl(self, enable: bool = True):
        """Enable or disable OpenGL acceleration"""
        if enable and not self._opengl_enabled:
            try:
                self.useOpenGL(True)
                self._opengl_enabled = True
            except Exception as e:
                logger.warning("Failed to enable OpenGL: %s", e)
        elif not enable and self._opengl_enabled:
            try:
                self.useOpenGL(False)
                self._opengl_enabled = False
            except Exception as e:
                logger.warning("Failed to disable OpenGL: %s", e)

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
    
    def plot_data(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        groups: Optional[Dict[str, np.ndarray]] = None,
        chart_type: ChartType = ChartType.LINE,
        options: Optional[Dict] = None,
        legend_settings: Optional[Dict] = None,
        x_categorical_labels: Optional[List[str]] = None,
        y_categorical_labels: Optional[List[str]] = None
    ):
        self.clear_plot()

        # Handle empty or None data
        if x_data is None or y_data is None:
            self._data_x = None
            self._data_y = None
            return

        if len(x_data) == 0 or len(y_data) == 0:
            self._data_x = None
            self._data_y = None
            return

        self._data_x = x_data
        self._data_y = y_data
        self._multi_series_data = None

        options = options or {}
        legend_settings = legend_settings or {'show': True, 'series': []}

        # Apply axis formats
        x_format = options.get('x_format')
        y_format = options.get('y_format')
        self._x_axis.set_format(x_format)
        self._y_axis.set_format(y_format)

        # Apply categorical labels if provided
        if x_categorical_labels:
            self._x_axis.set_categorical(x_categorical_labels)
        else:
            self._x_axis.clear_categorical()

        if y_categorical_labels:
            self._y_axis.set_categorical(y_categorical_labels)
        else:
            self._y_axis.clear_categorical()

        # Apply options — use theme-aware colors
        axis_label_color = '#111827' if self._is_light else '#E2E8F0'
        x_label = options.get('x_title', 'X')
        y_label = options.get('y_title', 'Y')
        self.setLabel('bottom', x_label, **{'font-size': '14px', 'color': axis_label_color})
        self.setLabel('left', y_label, **{'font-size': '14px', 'color': axis_label_color})
        
        # Grid
        grid_x = options.get('grid_x', True)
        grid_y = options.get('grid_y', True)
        grid_alpha = options.get('grid_opacity', 0.3)
        self.showGrid(x=grid_x, y=grid_y, alpha=grid_alpha)
        
        # Background
        default_bg = QColor('#F8FAFC') if self._is_light else QColor('#1E293B')
        bg_color = options.get('bg_color', default_bg)
        self.setBackground(bg_color.name())
        
        # Title + subtitle
        title = options.get('title')
        subtitle = options.get('subtitle')
        if title and subtitle:
            self.setTitle(f"{title}<br><span style='font-size:10pt;color:#94A3B8'>{subtitle}</span>")
        elif title:
            self.setTitle(title)
        elif subtitle:
            self.setTitle(f"<span style='font-size:10pt;color:#94A3B8'>{subtitle}</span>")
        else:
            self.setTitle("")
        
        # Y-axis range
        y_min = options.get('y_min')
        y_max = options.get('y_max')
        if y_min is not None and y_max is not None:
            self.setYRange(y_min, y_max)
        
        # Log scale
        x_log = bool(options.get('x_log'))
        y_log = bool(options.get('y_log'))
        self.setLogMode(x=x_log, y=y_log)

        # Reverse axes
        x_reverse = bool(options.get('x_reverse'))
        y_reverse = bool(options.get('y_reverse'))
        self.getViewBox().invertX(x_reverse)
        self.getViewBox().invertY(y_reverse)
        
        # Legend visibility and position
        if legend_settings.get('show', True):
            self.legend.show()
            # Apply legend position
            position = legend_settings.get('position', (1, 1))  # Default top right
            # Position format: (vertical, horizontal) where:
            # vertical: 0=bottom, 1=top, 0.5=middle
            # horizontal: 0=left, 1=right, 0.5=center
            v, h = position

            # Map position to anchor points
            # For legend.anchor(itemPos, parentPos):
            # itemPos: point on the legend item (0,0 = top-left, 1,1 = bottom-right)
            # parentPos: point on the parent viewbox (0,0 = top-left, 1,1 = bottom-right)
            if v == 1 and h == 1:  # Top Right
                self.legend.anchor((1, 0), (1, 0), offset=(-10, 10))
            elif v == 1 and h == 0:  # Top Left
                self.legend.anchor((0, 0), (0, 0), offset=(10, 10))
            elif v == 0 and h == 1:  # Bottom Right
                self.legend.anchor((1, 1), (1, 1), offset=(-10, -10))
            elif v == 0 and h == 0:  # Bottom Left
                self.legend.anchor((0, 1), (0, 1), offset=(10, -10))
            elif v == 1 and h == 0.5:  # Top Center
                self.legend.anchor((0.5, 0), (0.5, 0), offset=(0, 10))
            elif v == 0 and h == 0.5:  # Bottom Center
                self.legend.anchor((0.5, 1), (0.5, 1), offset=(0, -10))
            elif v == 0.5 and h == 1:  # Right
                self.legend.anchor((1, 0.5), (1, 0.5), offset=(-10, 0))
            elif v == 0.5 and h == 0:  # Left
                self.legend.anchor((0, 0.5), (0, 0.5), offset=(10, 0))
        else:
            self.legend.hide()
        
        # Get style options
        line_width = options.get('line_width', 2)
        marker_size = options.get('marker_size', 6)
        line_style = options.get('line_style', Qt.SolidLine)
        marker_symbol = options.get('marker_symbol', 'o')
        show_points = options.get('show_points', True)
        
        # Default colors from theme palette
        from ..theme import ColorPalette
        default_colors = list(ColorPalette.default().colors)
        
        # Get series colors from legend settings
        series_colors = {}
        series_visible = {}
        for s in legend_settings.get('series', []):
            series_colors[s['name']] = s.get('color', default_colors[0])
            series_visible[s['name']] = s.get('visible', True)
        
        # Item 14: Vary marker shapes per series for accessibility
        _marker_shapes = ['o', 's', 't', 'd', '+', 'x', 'star', 'p', 'h']

        if groups:
            group_color_map = options.get('group_color_map', {})
            group_marker_map = options.get('group_marker_map', {})
            for i, (group_name, mask) in enumerate(groups.items()):
                if not series_visible.get(group_name, True):
                    continue  # Skip hidden series

                color = group_color_map.get(
                    group_name,
                    series_colors.get(group_name, default_colors[i % len(default_colors)])
                )
                series_marker = group_marker_map.get(group_name, _marker_shapes[i % len(_marker_shapes)])
                self._plot_series(
                    x_data[mask], y_data[mask],
                    chart_type, color, group_name,
                    line_width, marker_size, line_style, series_marker,
                    show_points,
                    show_labels=options.get('show_labels', False),
                    smooth=options.get('smooth', False),
                    marker_border=options.get('marker_border', False),
                )
        else:
            color = default_colors[0]
            if legend_settings.get('series'):
                first_series = legend_settings['series'][0]
                color = first_series.get('color', color)
                if not first_series.get('visible', True):
                    return  # Hidden
            
            self._plot_series(
                x_data, y_data,
                chart_type, color, None,
                line_width, marker_size, line_style, marker_symbol,
                show_points,
                show_labels=options.get('show_labels', False),
                smooth=options.get('smooth', False),
                marker_border=options.get('marker_border', False),
            )
    
    def _plot_series(
        self,
        x: np.ndarray,
        y: np.ndarray,
        chart_type: ChartType,
        color: str,
        name: Optional[str],
        line_width: int,
        marker_size: int,
        line_style: Qt.PenStyle,
        marker_symbol: str,
        show_points: bool,
        show_labels: bool = False,
        smooth: bool = False,
        marker_border: bool = False,
    ):
        pen = pg.mkPen(color=color, width=line_width, style=line_style)
        brush = pg.mkBrush(color=color)
        marker_pen = pg.mkPen(color=color, width=1) if marker_border else pg.mkPen(None)

        # Smooth line (simple moving average)
        if chart_type == ChartType.LINE and smooth and len(y) > 3:
            window = min(9, max(3, len(y) // 50))
            kernel = np.ones(window) / window
            y = np.convolve(y, kernel, mode='same')

        if chart_type == ChartType.LINE:
            item = self.plot(x, y, pen=pen, name=name)
            if show_points and marker_size > 0:
                scatter = pg.ScatterPlotItem(x, y, size=marker_size, pen=marker_pen, brush=brush, symbol=marker_symbol)
                self.addItem(scatter)
                self._scatter_items.append(scatter)

            # Data labels (limited)
            if show_labels:
                if not hasattr(self, '_label_items'):
                    self._label_items = []
                max_labels = 200
                for i, (xi, yi) in enumerate(zip(x, y)):
                    if i >= max_labels:
                        break
                    _lbl_color = '#111827' if self._is_light else '#E2E8F0'
                    label = pg.TextItem(f"{yi:.2f}", anchor=(0.5, 1), color=_lbl_color)
                    label.setPos(xi, yi)
                    self.addItem(label)
                    self._label_items.append(label)
        elif chart_type == ChartType.SCATTER:
            if not show_points:
                return
            scatter = pg.ScatterPlotItem(x, y, size=marker_size, pen=marker_pen, brush=brush, symbol=marker_symbol, name=name)
            self.addItem(scatter)
            self._scatter_items.append(scatter)
            item = scatter
            if show_labels:
                if not hasattr(self, '_label_items'):
                    self._label_items = []
                max_labels = 200
                for i, (xi, yi) in enumerate(zip(x, y)):
                    if i >= max_labels:
                        break
                    _lbl_color = '#111827' if self._is_light else '#E2E8F0'
                    label = pg.TextItem(f"{yi:.2f}", anchor=(0.5, 1), color=_lbl_color)
                    label.setPos(xi, yi)
                    self.addItem(label)
                    self._label_items.append(label)
            
        elif chart_type == ChartType.BAR:
            width = (x.max() - x.min()) / len(x) * 0.8 if len(x) > 1 else 0.8
            item = pg.BarGraphItem(x=x, height=y, width=width, brush=brush, name=name)
            self.addItem(item)
            
        elif chart_type == ChartType.AREA:
            fill_brush = pg.mkBrush(color=color)
            fill_color = QColor(color)
            fill_color.setAlpha(50)
            item = self.plot(x, y, pen=pen, fillLevel=0, brush=fill_color, name=name)
            
        else:
            item = self.plot(x, y, pen=pen, name=name)
        
        self._plot_items.append(item)
    
    def clear_plot(self):
        for item in self._plot_items:
            self.removeItem(item)
        for item in self._scatter_items:
            self.removeItem(item)
        if hasattr(self, '_label_items'):
            for item in self._label_items:
                self.removeItem(item)
            self._label_items.clear()
        self._plot_items.clear()
        self._scatter_items.clear()
        # Clear secondary ViewBox (dual axis)
        if self._secondary_vb is not None:
            for item in self._secondary_vb_items:
                self._secondary_vb.removeItem(item)
            self._secondary_vb_items.clear()
            self.scene().removeItem(self._secondary_vb)
            self._secondary_vb = None
            self.hideAxis('right')
        self._data_x = None
        self._data_y = None
        self.legend.clear()
        # Clear trendlines (data-dependent)
        self.clear_trendlines()
        # Clear selection highlight
        if hasattr(self, '_selection_scatter') and self._selection_scatter is not None:
            self.removeItem(self._selection_scatter)
            self._selection_scatter = None
        # Note: annotations are NOT cleared on refresh — they persist.
        # Re-add them to the plot after clear.
        for ann in self._annotations:
            ann.add_to(self)

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
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, "Add Annotation",
            f"Annotation text for point ({data_x:.4g}, {data_y:.4g}):"
        )
        if ok and text.strip():
            self.add_annotation(text.strip(), data_x, data_y)

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

    def plot_multi_series(
        self,
        series_data: List[Dict],
        chart_type: ChartType = ChartType.LINE,
        options: Dict = None,
        legend_settings: Dict = None
    ):
        """
        Plot multiple data series on the same chart.

        Args:
            series_data: List of dicts with keys:
                - 'x': np.ndarray, X data
                - 'y': np.ndarray, Y data
                - 'name': str, Series name
                - 'color': str, Hex color code
                - 'dataset_id': str (optional)
            chart_type: Chart type to use
            options: Chart options
            legend_settings: Legend settings
        """
        options = options or {}
        legend_settings = legend_settings or {}

        # Clear existing plot
        self.clear_plot()

        # Apply axis settings — use theme-aware colors
        axis_label_color = '#111827' if self._is_light else '#E2E8F0'
        x_title = options.get('x_title', '')
        y_title = options.get('y_title', '')
        if x_title:
            self.setLabel('bottom', x_title, **{'font-size': '14px', 'color': axis_label_color})
        if y_title:
            self.setLabel('left', y_title, **{'font-size': '14px', 'color': axis_label_color})

        # Set log scale if specified
        x_log = options.get('x_log', False)
        y_log = options.get('y_log', False)
        self.setLogMode(x=x_log, y=y_log)

        # Get style options
        line_width = options.get('line_width', 2)
        marker_size = options.get('marker_size', 6)
        fill_opacity = options.get('fill_opacity', 0.3)

        # Plot each series
        for i, series in enumerate(series_data):
            x = series['x']
            y = series['y']
            name = series.get('name', f'Series {i+1}')
            color_hex = series.get('color', '#1f77b4')

            # Convert hex color to QColor
            color = QColor(color_hex)
            r, g, b = color.red(), color.green(), color.blue()

            # Create pen
            pen = pg.mkPen(color=color_hex, width=line_width)

            if chart_type == ChartType.LINE:
                item = self.plot(x, y, pen=pen, name=name)
                self._plot_items.append(item)

            elif chart_type == ChartType.SCATTER:
                m_border = options.get('marker_border', False)
                s_pen = pg.mkPen(color=color_hex, width=1) if m_border else pg.mkPen(None)
                scatter = pg.ScatterPlotItem(
                    x=x, y=y,
                    pen=s_pen,
                    brush=pg.mkBrush(r, g, b, 180),
                    size=marker_size,
                    name=name
                )
                self.addItem(scatter)
                self._scatter_items.append(scatter)

            elif chart_type == ChartType.BAR:
                # For bar chart, offset each series
                bar_width = 0.8 / len(series_data)
                offset = (i - len(series_data) / 2 + 0.5) * bar_width

                x_offset = x.astype(float) + offset
                bar_item = pg.BarGraphItem(
                    x=x_offset, height=y, width=bar_width * 0.9,
                    brush=pg.mkBrush(r, g, b, 200),
                    pen=pg.mkPen(color_hex),
                    name=name
                )
                self.addItem(bar_item)
                self._plot_items.append(bar_item)

            elif chart_type == ChartType.AREA:
                # Fill area under line
                curve = self.plot(x, y, pen=pen, name=name, fillLevel=0,
                                  brush=pg.mkBrush(r, g, b, int(255 * fill_opacity)))
                self._plot_items.append(curve)

            else:
                # Default to line
                item = self.plot(x, y, pen=pen, name=name)
                self._plot_items.append(item)

        # Store multi-series data for hover; keep first series as selection baseline
        self._multi_series_data = series_data or None
        if series_data:
            self._data_x = series_data[0].get('x')
            self._data_y = series_data[0].get('y')

        # Update legend settings
        if legend_settings:
            self._update_legend_settings(legend_settings)

        # Auto-range to fit all data with margin
        try:
            self.getViewBox().autoRange(padding=0.05)
        except Exception:
            logger.debug("autoRange with padding failed, falling back")
            self.autoRange()

    def _update_legend_settings(self, settings: Dict):
        """Update legend based on settings"""
        show = settings.get('show', True)
        position = settings.get('position', 'top-right')

        if show:
            self.legend.show()
            # Map position string to anchor
            pos_map = {
                'top-left': (0, 0),
                'top-right': (1, 0),
                'bottom-left': (0, 1),
                'bottom-right': (1, 1),
            }
            anchor = pos_map.get(position, (1, 0))
            self.legend.anchor(anchor, anchor)
        else:
            self.legend.hide()

    def reset_view(self):
        try:
            self.getViewBox().autoRange(padding=0.05)
        except Exception:
            logger.debug("autoRange with padding failed, falling back")
            self.autoRange()
        self.setLogMode(x=False, y=False)

    def setXRange(self, min: float, max: float, padding=None, update=True):  # noqa: A002
        """Set X range safely when log mode is enabled."""
        axis = self.getAxis('bottom')
        if getattr(axis, 'logMode', False):
            normalized = self._normalize_range_for_log(min, max)
            if normalized is None:
                return
            min, max = normalized
        return super().setXRange(min, max, padding=padding, update=update)

    def setYRange(self, min: float, max: float, padding=None, update=True):  # noqa: A002
        """Set Y range safely when log mode is enabled."""
        axis = self.getAxis('left')
        if getattr(axis, 'logMode', False):
            normalized = self._normalize_range_for_log(min, max)
            if normalized is None:
                return
            min, max = normalized
        return super().setYRange(min, max, padding=padding, update=update)

    def _fit_to_selection(self):
        """Fit view range to selected points (best-effort)."""
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
        except Exception as e:
            logger.debug("Fit to selection failed: %s", e)
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
        except Exception as e:
            logger.debug("Reset legend position failed: %s", e)

    def _toggle_grid(self):
        self._grid_visible = not getattr(self, '_grid_visible', True)
        self.showGrid(x=self._grid_visible, y=self._grid_visible, alpha=0.3)

    def _toggle_crosshair(self):
        self._crosshair_enabled = not self._crosshair_enabled
        if not self._crosshair_enabled:
            self._crosshair_v.setVisible(False)
            self._crosshair_h.setVisible(False)

    def _copy_plot_image(self):
        try:
            pix = self.grab()
            QApplication.clipboard().setPixmap(pix)
        except Exception as e:
            logger.warning("Copy plot image failed: %s", e)

    def _export_plot_image(self):
        """Save current plot as an image file."""
        try:
            default_name = "dgs-plot.png"
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Plot Image",
                default_name,
                "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)"
            )
            if not path:
                return
            pix = self.grab()
            pix.save(path)
        except Exception as e:
            logger.warning("Export plot image failed: %s", e)

    def _export_plot_data_csv(self):
        """Export currently plotted data to CSV (best-effort)."""
        try:
            default_name = "dgs-plot-data.csv"
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Plot Data (CSV)",
                default_name,
                "CSV (*.csv)"
            )
            if not path:
                return

            # Multi-series export
            if self._multi_series_data:
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    w = csv.writer(f)
                    w.writerow(["series", "x", "y"])
                    for s in self._multi_series_data:
                        name = s.get('name', '')
                        xs = s.get('x')
                        ys = s.get('y')
                        if xs is None or ys is None:
                            continue
                        n = min(len(xs), len(ys))
                        for i in range(n):
                            w.writerow([name, xs[i], ys[i]])
                return

            # Single-series export
            if self._data_x is None or self._data_y is None:
                return
            n = min(len(self._data_x), len(self._data_y))
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(["x", "y"])
                for i in range(n):
                    w.writerow([self._data_x[i], self._data_y[i]])
        except Exception as e:
            logger.warning("Export plot data CSV failed: %s", e)

    def contextMenuEvent(self, event):
        """Custom right-click menu (replace pyqtgraph default)."""
        menu = QMenu(self)

        # View
        fit_act = QAction("Fit (Auto)", self)
        fit_act.triggered.connect(self.reset_view)
        menu.addAction(fit_act)

        fit_sel_act = QAction("Fit to Selection", self)
        fit_sel_act.setEnabled(bool(self.state.selection.selected_rows))
        fit_sel_act.triggered.connect(self._fit_to_selection)
        menu.addAction(fit_sel_act)

        grid_act = QAction("Toggle Grid", self)
        grid_act.triggered.connect(self._toggle_grid)
        menu.addAction(grid_act)

        minimap_act = QAction("Toggle Minimap", self)
        minimap_act.setCheckable(True)
        # Access GraphPanel parent to check/toggle minimap
        graph_panel = self._find_graph_panel()
        if graph_panel:
            minimap_act.setChecked(graph_panel._minimap_enabled)
            minimap_act.triggered.connect(lambda checked: graph_panel.toggle_minimap(checked))
        menu.addAction(minimap_act)

        crosshair_act = QAction("Toggle Crosshair", self)
        crosshair_act.setCheckable(True)
        crosshair_act.setChecked(self._crosshair_enabled)
        crosshair_act.triggered.connect(self._toggle_crosshair)
        menu.addAction(crosshair_act)

        legend_reset_act = QAction("Reset Legend Position", self)
        legend_reset_act.triggered.connect(self._reset_legend_position)
        menu.addAction(legend_reset_act)

        copy_act = QAction("Copy Image", self)
        copy_act.triggered.connect(self._copy_plot_image)
        menu.addAction(copy_act)

        # Export
        export_menu = menu.addMenu("Export")
        export_img = QAction("Save Image…", self)
        export_img.triggered.connect(self._export_plot_image)
        export_menu.addAction(export_img)

        export_csv = QAction("Export Data (CSV)…", self)
        export_csv.setEnabled(self._data_x is not None or bool(self._multi_series_data))
        export_csv.triggered.connect(self._export_plot_data_csv)
        export_menu.addAction(export_csv)

        menu.addSeparator()

        # Tools
        tools_menu = menu.addMenu("Tool")
        for label, mode in [
            ("Pan", ToolMode.PAN),
            ("Zoom", ToolMode.ZOOM),
            ("Rect Select", ToolMode.RECT_SELECT),
            ("Lasso Select", ToolMode.LASSO_SELECT),
        ]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self.state.tool_mode == mode)
            act.triggered.connect(lambda checked=False, m=mode: self.state.set_tool_mode(m))
            tools_menu.addAction(act)

        # Draw
        draw_menu = menu.addMenu("Draw")
        for label, mode in [
            ("Line", ToolMode.LINE_DRAW),
            ("Arrow", ToolMode.ARROW_DRAW),
            ("Circle", ToolMode.CIRCLE_DRAW),
            ("Rectangle", ToolMode.RECT_DRAW),
            ("Text", ToolMode.TEXT_DRAW),
        ]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self.state.tool_mode == mode)
            act.triggered.connect(lambda checked=False, m=mode: self.state.set_tool_mode(m))
            draw_menu.addAction(act)

        draw_menu.addSeparator()

        style_act = QAction("Drawing Style…", self)
        def _open_style():
            try:
                dlg = DrawingStyleDialog("Drawing Style", self)
                dlg.set_style(self._current_drawing_style)
                if dlg.exec() == QDialog.Accepted:
                    self.set_drawing_style(dlg.get_style())
            except Exception as e:
                logger.warning("Drawing style dialog failed: %s", e)
        style_act.triggered.connect(_open_style)
        draw_menu.addAction(style_act)

        # Drawing ops
        if self._drawing_manager:
            draw_menu.addSeparator()
            undo_d = QAction("Undo Drawing", self)
            undo_d.setEnabled(True)
            undo_d.triggered.connect(self._drawing_manager.undo)
            draw_menu.addAction(undo_d)

            redo_d = QAction("Redo Drawing", self)
            redo_d.setEnabled(True)
            redo_d.triggered.connect(self._drawing_manager.redo)
            draw_menu.addAction(redo_d)

            del_sel = QAction("Delete Selected Drawing", self)
            del_sel.setEnabled(self._drawing_manager.get_selected_id() is not None)
            del_sel.triggered.connect(self._drawing_manager.delete_selected)
            draw_menu.addAction(del_sel)

            clear_d = QAction("Clear All Drawings", self)
            clear_d.triggered.connect(self._drawing_manager.clear)
            draw_menu.addAction(clear_d)

        menu.addSeparator()

        # Reference Lines
        has_data = self._data_y is not None and len(self._data_y) > 0
        ref_menu = menu.addMenu("Reference Lines")
        mean_act = QAction("Add Mean Line", self)
        mean_act.setEnabled(has_data)
        mean_act.triggered.connect(self._add_mean_line)
        ref_menu.addAction(mean_act)

        median_act = QAction("Add Median Line", self)
        median_act.setEnabled(has_data)
        median_act.triggered.connect(self._add_median_line)
        ref_menu.addAction(median_act)

        custom_act = QAction("Add Custom Line…", self)
        custom_act.triggered.connect(self._add_custom_line)
        ref_menu.addAction(custom_act)

        sigma_act = QAction("Add ±1σ Band", self)
        sigma_act.setEnabled(has_data)
        sigma_act.triggered.connect(self._add_sigma_band)
        ref_menu.addAction(sigma_act)

        ref_menu.addSeparator()
        clear_ref = QAction("Clear All", self)
        clear_ref.setEnabled(bool(self._ref_lines or self._ref_bands))
        clear_ref.triggered.connect(self.clear_reference_lines)
        ref_menu.addAction(clear_ref)

        # Trendline
        trend_menu = menu.addMenu("Trendline")
        for label_t, deg in [("Linear (1차)", 1), ("Quadratic (2차)", 2), ("Cubic (3차)", 3)]:
            t_act = QAction(label_t, self)
            t_act.setEnabled(has_data)
            t_act.triggered.connect(lambda checked=False, d=deg: self._add_trendline_degree(d))
            trend_menu.addAction(t_act)

        exp_act = QAction("Exponential", self)
        exp_act.setEnabled(has_data)
        exp_act.triggered.connect(self._add_exponential_trendline)
        trend_menu.addAction(exp_act)

        trend_menu.addSeparator()
        clear_trend = QAction("Clear Trendlines", self)
        clear_trend.setEnabled(bool(self._trendline_items))
        clear_trend.triggered.connect(self.clear_trendlines)
        trend_menu.addAction(clear_trend)

        menu.addSeparator()

        # Annotations
        ann_menu = menu.addMenu("Annotations")
        add_ann_act = QAction("Add Annotation at Nearest Point…", self)
        add_ann_act.setEnabled(has_data)
        def _add_ann_nearest():
            pos = self.plotItem.vb.mapSceneToView(event.pos())
            result = self._find_nearest_data_point(pos.x(), pos.y())
            if result:
                self._prompt_add_annotation(result[0], result[1])
        add_ann_act.triggered.connect(_add_ann_nearest)
        ann_menu.addAction(add_ann_act)

        clear_ann_act = QAction("Clear All Annotations", self)
        clear_ann_act.setEnabled(bool(self._annotations))
        clear_ann_act.triggered.connect(self.clear_annotations)
        ann_menu.addAction(clear_ann_act)

        menu.addSeparator()

        # Selection
        sel_menu = menu.addMenu("Selection")
        clear_sel = QAction("Clear Selection", self)
        clear_sel.setEnabled(bool(self.state.selection.selected_rows))
        clear_sel.triggered.connect(self.state.clear_selection)
        sel_menu.addAction(clear_sel)

        menu.exec(event.globalPos())

    def _on_mouse_clicked(self, event):
        """Handle mouse click - selection/drawing is handled via press/move/release"""
        # Selection and drawing modes are fully handled by
        # mousePressEvent / mouseMoveEvent / mouseReleaseEvent.
        # This handler is kept for potential future single-click actions.
        pass

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
                # Click on empty area → deselect
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
                from PySide6.QtGui import QPainterPath, QPolygonF
                from PySide6.QtCore import QPointF
                
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

        # Tool mode changed while selecting: cancel stale selection state.
        elif self._is_selecting:
            if getattr(self, '_lasso_points', None):
                self._cleanup_lasso()
            else:
                self._cleanup_selection()
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

        # Tool mode changed while drawing: cancel stale drawing state.
        elif self._is_drawing:
            self._cleanup_drawing()
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
            except Exception as e:
                logger.debug("Multi-series hover error: %s", e)
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
        except Exception as e:
            logger.debug("Single-series hover error: %s", e)
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

    # ==================== Drawing Methods ====================

    def set_drawing_manager(self, manager: DrawingManager):
        """Set the drawing manager"""
        self._drawing_manager = manager

    def get_drawing_manager(self) -> Optional[DrawingManager]:
        """Get the drawing manager"""
        return self._drawing_manager

    def set_drawing_style(self, style: DrawingStyle):
        """Set the current drawing style"""
        self._current_drawing_style = style

    def push_view_range(self):
        """현재 view range를 undo 스택에 저장"""
        if not self._view_range_recording:
            return
        current = self.viewRange()
        current_tuple = (tuple(current[0]), tuple(current[1]))
        if self._last_recorded_range == current_tuple:
            return
        if self._last_recorded_range is not None:
            self._view_range_stack.append(self._last_recorded_range)
            if len(self._view_range_stack) >= self._view_range_max:
                self._view_range_stack.pop(0)
            self._view_range_redo.clear()
        self._last_recorded_range = current_tuple

    def undo_view_range(self) -> bool:
        """이전 view range로 복원"""
        if not self._view_range_stack:
            return False
        # 현재 range를 redo에 저장
        current = self.viewRange()
        self._view_range_redo.append((tuple(current[0]), tuple(current[1])))
        prev = self._view_range_stack.pop()
        self._view_range_recording = False
        self.setXRange(prev[0][0], prev[0][1], padding=0)
        self.setYRange(prev[1][0], prev[1][1], padding=0)
        self._last_recorded_range = prev
        self._view_range_recording = True
        return True

    def redo_view_range(self) -> bool:
        """redo view range"""
        if not self._view_range_redo:
            return False
        current = self.viewRange()
        self._view_range_stack.append((tuple(current[0]), tuple(current[1])))
        next_range = self._view_range_redo.pop()
        self._view_range_recording = False
        self.setXRange(next_range[0][0], next_range[0][1], padding=0)
        self.setYRange(next_range[1][0], next_range[1][1], padding=0)
        self._last_recorded_range = next_range
        self._view_range_recording = True
        return True

    # mouseReleaseEvent is defined above (merged with selection/drawing handling)

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
            logger.debug("pen.setCosmetic not supported")

        if self.state.tool_mode in (ToolMode.LINE_DRAW, ToolMode.ARROW_DRAW):
            # Line/Arrow preview (arrow head is drawn on final object)
            from PySide6.QtCore import QLineF
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

    # ==================== Reference Lines & Bands ====================

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
        from PySide6.QtWidgets import QInputDialog
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

    # ==================== Trendline ====================

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
        except Exception as e:
            logger.warning("Failed to add trendline: %s", e)

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

