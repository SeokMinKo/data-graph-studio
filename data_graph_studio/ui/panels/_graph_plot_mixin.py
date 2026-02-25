"""Core plot rendering and context menu for MainGraph."""
from __future__ import annotations

import csv
import logging
from typing import Dict, List, Optional

import numpy as np

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QAction
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMenu

from ...core.state import ChartType, ToolMode
from ..drawing import DrawingStyleDialog

logger = logging.getLogger(__name__)


class _GraphPlotMixin:
    """Mixin providing plot rendering, export, and view management for MainGraph."""

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

        # Title
        title = options.get('title')
        if title:
            self.setTitle(title)

        # Log scale
        x_log = bool(options.get('x_log'))
        y_log = bool(options.get('y_log'))
        self.setLogMode(x=x_log, y=y_log)

        # Y-axis range
        y_min = options.get('y_min')
        y_max = options.get('y_max')
        if y_min is not None and y_max is not None:
            self.setYRange(y_min, y_max)

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
            pg.mkBrush(color=color)
            fill_color = QColor(color)
            fill_color.setAlpha(50)
            item = self.plot(x, y, pen=pen, fillLevel=0, brush=fill_color, name=name)

        else:
            item = self.plot(x, y, pen=pen, name=name)

        self._plot_items.append(item)

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
            logger.warning("main_graph.render_complete.autorange.error", exc_info=True)
            self.autoRange()

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

    def contextMenuEvent(self, event):
        """Build and display the right-click context menu."""
        pos = self.plotItem.vb.mapSceneToView(event.pos())
        menu = QMenu(self)
        self._build_view_menu(menu)
        self._build_export_menu(menu)
        menu.addSeparator()
        self._build_tools_menu(menu)
        self._build_draw_menu(menu)
        menu.addSeparator()
        self._build_reference_menu(menu)
        menu.addSeparator()
        self._build_annotations_menu(menu, pos)
        menu.exec(event.globalPos())

    def _build_view_menu(self, menu: QMenu) -> None:
        """Add view-control actions: fit, grid, minimap, crosshair, legend, copy."""
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

    def _build_export_menu(self, menu: QMenu) -> None:
        """Add Export submenu: save image, export CSV."""
        export_menu = menu.addMenu("Export")

        export_img = QAction("Save Image…", self)
        export_img.triggered.connect(self._export_plot_image)
        export_menu.addAction(export_img)

        export_csv = QAction("Export Data (CSV)…", self)
        export_csv.setEnabled(self._data_x is not None or bool(self._multi_series_data))
        export_csv.triggered.connect(self._export_plot_data_csv)
        export_menu.addAction(export_csv)

    def _build_tools_menu(self, menu: QMenu) -> None:
        """Add Tool submenu: pan, zoom, rect select, lasso select."""
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

    def _build_draw_menu(self, menu: QMenu) -> None:
        """Add Draw submenu: drawing tool modes, style dialog, and undo/redo/delete/clear ops."""
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
        style_act.triggered.connect(lambda: self._open_drawing_style_dialog())
        draw_menu.addAction(style_act)

        if self._drawing_manager:
            draw_menu.addSeparator()
            undo_d = QAction("Undo Drawing", self)
            undo_d.triggered.connect(self._drawing_manager.undo)
            draw_menu.addAction(undo_d)

            redo_d = QAction("Redo Drawing", self)
            redo_d.triggered.connect(self._drawing_manager.redo)
            draw_menu.addAction(redo_d)

            del_sel = QAction("Delete Selected Drawing", self)
            del_sel.setEnabled(self._drawing_manager.get_selected_id() is not None)
            del_sel.triggered.connect(self._drawing_manager.delete_selected)
            draw_menu.addAction(del_sel)

            clear_d = QAction("Clear All Drawings", self)
            clear_d.triggered.connect(self._drawing_manager.clear)
            draw_menu.addAction(clear_d)

    def _open_drawing_style_dialog(self) -> None:
        """Open the Drawing Style dialog and apply any accepted changes."""
        try:
            dlg = DrawingStyleDialog("Drawing Style", self)
            dlg.set_style(self._current_drawing_style)
            if dlg.exec() == QDialog.Accepted:
                self.set_drawing_style(dlg.get_style())
        except Exception:
            logger.exception("main_graph.open_style_dialog.error")

    def _add_annotation_at_pos(self, vx: float, vy: float) -> None:
        """Find the nearest data point to (vx, vy) in view coords and prompt to annotate."""
        result = self._find_nearest_data_point(vx, vy)
        if result:
            self._prompt_add_annotation(result[0], result[1])

    def _build_reference_menu(self, menu: QMenu) -> None:
        """Add Reference Lines and Trendline submenus."""
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

        self._build_trendline_menu(menu, has_data)

    def _build_trendline_menu(self, menu: QMenu, has_data: bool) -> None:
        """Add Trendline submenu: polynomial degrees, exponential, and clear."""
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

    def _build_annotations_menu(self, menu: QMenu, pos) -> None:
        """Add Annotations submenu and Selection submenu."""
        has_data = self._data_y is not None and len(self._data_y) > 0

        ann_menu = menu.addMenu("Annotations")
        add_ann_act = QAction("Add Annotation at Nearest Point…", self)
        add_ann_act.setEnabled(has_data)
        add_ann_act.triggered.connect(
            lambda: self._add_annotation_at_pos(pos.x(), pos.y())
        )
        ann_menu.addAction(add_ann_act)

        clear_ann_act = QAction("Clear All Annotations", self)
        clear_ann_act.setEnabled(bool(self._annotations))
        clear_ann_act.triggered.connect(self.clear_annotations)
        ann_menu.addAction(clear_ann_act)

        menu.addSeparator()
        sel_menu = menu.addMenu("Selection")
        clear_sel = QAction("Clear Selection", self)
        clear_sel.setEnabled(bool(self.state.selection.selected_rows))
        clear_sel.triggered.connect(self.state.clear_selection)
        sel_menu.addAction(clear_sel)

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
        except Exception:
            logger.exception("main_graph.export_plot_image.error")

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
        except Exception:
            logger.exception("main_graph.export_plot_data_csv.error")

    def _copy_plot_image(self):
        try:
            pix = self.grab()
            QApplication.clipboard().setPixmap(pix)
        except Exception:
            logger.exception("main_graph.copy_plot_image.error")

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
