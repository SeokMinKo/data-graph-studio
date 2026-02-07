"""
MainGraph - 메인 그래프 위젯 with hover tooltip support
"""

from typing import Optional, List, Dict, Any

import numpy as np

from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush

from .graph_widgets import FormattedAxisItem
from ...core.state import AppState, ChartType, ToolMode
from ..drawing import (
    DrawingManager, DrawingStyle, LineStyle,
    LineDrawing, CircleDrawing, RectDrawing, TextDrawing,
    DrawingStyleDialog, RectStyleDialog, TextInputDialog,
    snap_to_angle
)
import pyqtgraph as pg




# ==================== Main Graph ====================

class MainGraph(pg.PlotWidget):
    """메인 그래프 위젯 with hover tooltip support"""

    points_selected = Signal(list)

    def __init__(self, state: AppState):
        # Create custom axes
        self._x_axis = FormattedAxisItem('bottom')
        self._y_axis = FormattedAxisItem('left')

        super().__init__(axisItems={'bottom': self._x_axis, 'left': self._y_axis})
        self.state = state

        # Ensure Y-axis label is not clipped
        self._y_axis.setWidth(60)
        self.getPlotItem().getViewBox().setDefaultPadding(0.05)

        self.setBackground('w')
        self.showGrid(x=True, y=True, alpha=0.15)
        self.setLabel('left', '')
        self.setLabel('bottom', '')

        self.legend = self.addLegend()
        self._legend_visible = True
        self._legend_position = (1, 1)  # Default: top right

        self._plot_items = []
        self._scatter_items = []
        self._secondary_vb = None  # Secondary ViewBox for dual axis
        self._secondary_vb_items = []  # Items in secondary ViewBox
        self._data_x = None
        self._data_y = None

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
            color='#C2C8D1'
        )
        self._sampling_label.setZValue(1000)
        self._sampling_label.setFont(pg.QtGui.QFont('Arial', 9))
        self.addItem(self._sampling_label)
        self._sampling_label.hide()

        # OpenGL state
        self._opengl_enabled = False

        # Enable mouse tracking for hover
        self.setMouseTracking(True)
        self.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        self.scene().sigMouseMoved.connect(self._on_mouse_moved)

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
                print(f"Failed to enable OpenGL: {e}")
        elif not enable and self._opengl_enabled:
            try:
                self.useOpenGL(False)
                self._opengl_enabled = False
            except Exception:
                pass

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
        elif mode in [ToolMode.LINE_DRAW, ToolMode.CIRCLE_DRAW, 
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

        # Apply options
        x_label = options.get('x_title', 'X')
        y_label = options.get('y_title', 'Y')
        self.setLabel('bottom', x_label, **{'font-size': '14px', 'color': '#E2E8F0'})
        self.setLabel('left', y_label, **{'font-size': '14px', 'color': '#E2E8F0'})
        
        # Grid
        grid_x = options.get('grid_x', True)
        grid_y = options.get('grid_y', True)
        grid_alpha = options.get('grid_opacity', 0.3)
        self.showGrid(x=grid_x, y=grid_y, alpha=grid_alpha)
        
        # Background
        bg_color = options.get('bg_color', QColor('#323D4A'))
        self.setBackground(bg_color.name())
        
        # Title
        title = options.get('title')
        if title:
            self.setTitle(title)
        
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
        
        # Default colors
        default_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        
        # Get series colors from legend settings
        series_colors = {}
        series_visible = {}
        for s in legend_settings.get('series', []):
            series_colors[s['name']] = s.get('color', default_colors[0])
            series_visible[s['name']] = s.get('visible', True)
        
        if groups:
            for i, (group_name, mask) in enumerate(groups.items()):
                if not series_visible.get(group_name, True):
                    continue  # Skip hidden series
                
                color = series_colors.get(group_name, default_colors[i % len(default_colors)])
                self._plot_series(
                    x_data[mask], y_data[mask],
                    chart_type, color, group_name,
                    line_width, marker_size, line_style, marker_symbol,
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
                    label = pg.TextItem(f"{yi:.2f}", anchor=(0.5, 1), color='#E2E8F0')
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
                    label = pg.TextItem(f"{yi:.2f}", anchor=(0.5, 1), color='#E2E8F0')
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
        # Clear selection highlight
        if hasattr(self, '_selection_scatter') and self._selection_scatter is not None:
            self.removeItem(self._selection_scatter)
            self._selection_scatter = None

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

        # Apply axis settings
        x_title = options.get('x_title', '')
        y_title = options.get('y_title', '')
        if x_title:
            self.setLabel('bottom', x_title, **{'font-size': '14px', 'color': '#E2E8F0'})
        if y_title:
            self.setLabel('left', y_title, **{'font-size': '14px', 'color': '#E2E8F0'})

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

        # Store first series data for selection
        if series_data:
            self._data_x = series_data[0]['x']
            self._data_y = series_data[0]['y']

        # Update legend settings
        if legend_settings:
            self._update_legend_settings(legend_settings)

        # Auto-range to fit all data with margin
        try:
            self.getViewBox().autoRange(padding=0.05)
        except Exception:
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
            self.autoRange()
        self.setLogMode(x=False, y=False)
    
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
        elif self.state.tool_mode in [ToolMode.LINE_DRAW, ToolMode.CIRCLE_DRAW, 
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
                ToolMode.LINE_DRAW, ToolMode.CIRCLE_DRAW,
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

    def _on_mouse_moved(self, pos):
        """Handle mouse move for hover tooltip"""
        if self._data_x is None or self._data_y is None:
            self._hide_tooltip()
            return

        if not self._hover_columns or not self._hover_data:
            self._hide_tooltip()
            return

        # Convert scene position to view coordinates
        mouse_point = self.plotItem.vb.mapSceneToView(pos)
        mx, my = mouse_point.x(), mouse_point.y()

        # Find nearest point
        if len(self._data_x) == 0:
            self._hide_tooltip()
            return

        # Calculate distance to each point (normalized)
        view_range = self.viewRange()
        x_range = view_range[0][1] - view_range[0][0]
        y_range = view_range[1][1] - view_range[1][0]

        if x_range == 0 or y_range == 0:
            self._hide_tooltip()
            return

        # Normalized distance (handle NaN values)
        try:
            dx = (self._data_x - mx) / x_range
            dy = (self._data_y - my) / y_range
            distances = np.sqrt(dx**2 + dy**2)

            # Replace NaN distances with infinity so they're not selected
            distances = np.where(np.isnan(distances), np.inf, distances)

            if np.all(np.isinf(distances)):
                self._hide_tooltip()
                return

            nearest_idx = np.argmin(distances)
            min_dist = distances[nearest_idx]

            # Only show tooltip if close enough (within 5% of view range)
            if min_dist < 0.05 and not np.isinf(min_dist):
                self._show_tooltip(nearest_idx, self._data_x[nearest_idx], self._data_y[nearest_idx])
            else:
                self._hide_tooltip()
        except Exception:
            self._hide_tooltip()

    def _show_tooltip(self, idx: int, x_val: float, y_val: float):
        """Show tooltip at data point"""
        if self._tooltip_item is None:
            self._tooltip_item = pg.TextItem(anchor=(0, 1), fill='w', border='k')
            self._tooltip_item.setZValue(1000)
            self.addItem(self._tooltip_item)

        # Build tooltip text
        lines = [f"X: {self._format_value(x_val)}", f"Y: {self._format_value(y_val)}"]

        for col in self._hover_columns:
            if col in self._hover_data and idx < len(self._hover_data[col]):
                val = self._hover_data[col][idx]
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
            if len(self._view_range_stack) > self._view_range_max:
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
            if self.state.tool_mode == ToolMode.LINE_DRAW:
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
            pass

        if self.state.tool_mode == ToolMode.LINE_DRAW:
            # Line preview
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
            if self.state.tool_mode == ToolMode.LINE_DRAW:
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

    def apply_theme(self, is_light: bool):
        """Apply theme colors to main graph"""
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


# ==================== Graph Panel ====================

