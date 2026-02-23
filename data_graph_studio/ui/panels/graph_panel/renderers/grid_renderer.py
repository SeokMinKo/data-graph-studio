"""
Grid View (Facet Grid) Rendering Mixin for GraphPanel.

Extracted from graph_panel.py as part of the Phase 1 GOAT refactoring.
Uses the mixin pattern so that ``self`` still resolves to the GraphPanel
instance — avoiding the need to pass 5+ dependencies through constructors.

Attributes accessed on ``self`` (from GraphPanel):
    state, engine, main_graph,
    _grid_container, _grid_layout, _grid_cells, _grid_cell_labels,
    _active_filter
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

import numpy as np
import polars as pl
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from .....core.state import ChartType


class GridChartMixin:
    """Mixin providing grid/facet view rendering methods for GraphPanel."""

    def _refresh_grid_view(self, options: Dict[str, Any], legend_settings: Dict[str, Any]):
        """Render Grid View with multiple faceted charts."""
        from .....core.state import GridDirection

        # Hide main graph, show grid container
        self.main_graph.setVisible(False)
        self._grid_container.setVisible(True)

        split_by = options.get('split_by')
        direction = options.get('direction', GridDirection.WRAP)
        max_columns = options.get('max_columns', 4)

        # Get the working DataFrame (filters pushed to Polars lazy layer)
        working_df = self.engine.get_filtered_df(self._active_filter)

        if working_df is None or len(working_df) == 0:
            self._clear_grid_cells()
            return

        # Get unique values for split column
        if split_by not in working_df.columns:
            self._clear_grid_cells()
            return

        split_values = working_df[split_by].unique().to_list()
        split_values = [v for v in split_values if v is not None]  # Remove nulls
        split_values = sorted(split_values, key=lambda x: str(x))

        n_facets = len(split_values)
        if n_facets == 0:
            self._clear_grid_cells()
            return

        # Calculate grid dimensions based on direction
        if direction == GridDirection.ROW:
            n_cols = n_facets
        elif direction == GridDirection.COLUMN:
            n_cols = 1
        else:  # WRAP
            n_cols = min(max_columns, n_facets)
            (n_facets + n_cols - 1) // n_cols

        # Clear existing grid cells
        self._clear_grid_cells()

        # Create grid cells for each facet
        chart_type = options.get('chart_type', ChartType.LINE)
        line_width = options.get('line_width', 2)
        marker_size = options.get('marker_size', 6)
        show_points = options.get('show_points', True)
        bg_color = options.get('bg_color', QColor('#323D4A'))
        grid_alpha = options.get('grid_opacity', 0.3)

        # Colors for series
        from ...theme import ColorPalette
        custom_palette = options.get('color_palette')
        if custom_palette and hasattr(custom_palette, 'colors'):
            default_colors = list(custom_palette.colors)
        elif isinstance(custom_palette, (list, tuple)) and custom_palette:
            default_colors = list(custom_palette)
        else:
            default_colors = list(ColorPalette.default().colors)

        # Get X and Y column info
        x_col = self.state.x_column
        y_col_name = None
        if self.state.value_columns:
            y_col_name = self.state.value_columns[0].name
        else:
            numeric_cols = [col for col in self.engine.columns
                           if self.engine.dtypes.get(col, '').startswith(('Int', 'Float'))]
            if numeric_cols:
                y_col_name = numeric_cols[0]

        if not y_col_name or y_col_name not in working_df.columns:
            self._clear_grid_cells()
            return

        # Store all cell plots for axis synchronization
        all_cells = []
        all_x_data = []
        all_y_data = []

        for idx, split_val in enumerate(split_values):
            row = idx // n_cols
            col = idx % n_cols

            # Create cell container
            cell_widget = QWidget()
            cell_layout = QVBoxLayout(cell_widget)
            cell_layout.setContentsMargins(2, 2, 2, 2)
            cell_layout.setSpacing(2)

            # Label for this facet
            label = QLabel(f"{split_by}: {split_val}")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-weight: bold; color: #E2E8F0; padding: 2px;")
            cell_layout.addWidget(label)
            self._grid_cell_labels.append(label)

            # Create PlotWidget for this facet
            plot_widget = pg.PlotWidget()
            plot_widget.setBackground(bg_color.name())
            plot_widget.showGrid(x=True, y=True, alpha=grid_alpha)

            # Filter data for this facet
            try:
                facet_df = working_df.filter(pl.col(split_by).cast(pl.Utf8) == str(split_val))
            except Exception:
                logger.warning("grid_renderer.facet_filter.cast_error", exc_info=True)
                facet_df = working_df.filter(pl.col(split_by) == split_val)

            if len(facet_df) == 0:
                cell_layout.addWidget(plot_widget, 1)
                self._grid_layout.addWidget(cell_widget, row, col)
                self._grid_cells.append(plot_widget)
                all_cells.append(plot_widget)
                continue

            # Get X data
            if x_col and x_col in facet_df.columns:
                x_data = facet_df[x_col].to_numpy()
            else:
                x_data = np.arange(len(facet_df))

            # Get Y data
            y_data = facet_df[y_col_name].to_numpy()

            all_x_data.extend(x_data.tolist())
            all_y_data.extend(y_data.tolist())

            # P1-4: Group support in grid view — overlay groups within each facet
            group_col_names = [gc.name for gc in self.state.group_columns]
            has_groups = bool(group_col_names) and all(gc in facet_df.columns for gc in group_col_names)

            # Group colors
            _grid_group_colors = [
                '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
            ]

            if has_groups:
                # Build group masks for this facet
                facet_indexed = facet_df.with_row_index("__row_idx__")
                facet_grouped = facet_indexed.group_by(group_col_names).agg(
                    pl.col("__row_idx__").alias("__indices__")
                )
                for g_idx, row in enumerate(facet_grouped.iter_rows()):
                    vals = row[:-1]
                    indices = row[-1]
                    if len(group_col_names) == 1:
                        str(vals[0]) if vals[0] is not None else "(Empty)"
                    else:
                        " / ".join(str(v) if v is not None else "(Empty)" for v in vals)

                    g_color = _grid_group_colors[g_idx % len(_grid_group_colors)]
                    g_pen = pg.mkPen(color=g_color, width=line_width)
                    g_x = x_data[list(indices)]
                    g_y = y_data[list(indices)]
                    if len(g_x) == 0:
                        continue

                    self._plot_grid_series(plot_widget, g_x, g_y, chart_type, g_color, g_pen,
                                           line_width, marker_size, show_points)
            else:
                # No groups — single series per facet (original behavior)
                color = default_colors[idx % len(default_colors)]
                pen = pg.mkPen(color=color, width=line_width)
                self._plot_grid_series(plot_widget, x_data, y_data, chart_type, color, pen,
                                       line_width, marker_size, show_points)

            cell_layout.addWidget(plot_widget, 1)
            self._grid_layout.addWidget(cell_widget, row, col)
            self._grid_cells.append(plot_widget)
            all_cells.append(plot_widget)

        # Synchronize axes across all cells
        if len(all_cells) > 1 and len(all_x_data) > 0 and len(all_y_data) > 0:
            self._sync_grid_axes(all_cells, all_x_data, all_y_data)

    def _plot_grid_series(self, plot_widget, x_data, y_data, chart_type, color, pen,
                          line_width, marker_size, show_points):
        """Helper to plot a single series on a grid cell PlotWidget."""
        if chart_type == ChartType.LINE:
            plot_widget.plot(x_data, y_data, pen=pen)
            if show_points and marker_size > 0:
                scatter = pg.ScatterPlotItem(x_data, y_data, size=marker_size,
                                              brush=pg.mkBrush(color))
                plot_widget.addItem(scatter)
        elif chart_type == ChartType.SCATTER:
            scatter = pg.ScatterPlotItem(x_data, y_data, size=marker_size,
                                          brush=pg.mkBrush(color))
            plot_widget.addItem(scatter)
        elif chart_type == ChartType.BAR:
            w = (x_data.max() - x_data.min()) / len(x_data) * 0.8 if len(x_data) > 1 else 0.8
            bar = pg.BarGraphItem(x=x_data, height=y_data, width=w,
                                   brush=pg.mkBrush(QColor(color).red(),
                                                   QColor(color).green(),
                                                   QColor(color).blue(), 180))
            plot_widget.addItem(bar)
        elif chart_type == ChartType.AREA:
            fill_color = QColor(color)
            fill_color.setAlpha(80)
            plot_widget.plot(x_data, y_data, pen=pen, fillLevel=0, brush=fill_color)
        else:
            plot_widget.plot(x_data, y_data, pen=pen)

    def _clear_grid_cells(self):
        """Clear all grid cells."""
        # Remove widgets from layout
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._grid_cells.clear()
        self._grid_cell_labels.clear()

    def _sync_grid_axes(self, cells: List[pg.PlotWidget], all_x: List, all_y: List):
        """Synchronize axis ranges across all grid cells."""
        # Calculate global range
        try:
            x_arr = np.array([x for x in all_x if x is not None and not np.isnan(x)])
            y_arr = np.array([y for y in all_y if y is not None and not np.isnan(y)])

            if len(x_arr) == 0 or len(y_arr) == 0:
                return

            x_min, x_max = float(np.min(x_arr)), float(np.max(x_arr))
            y_min, y_max = float(np.min(y_arr)), float(np.max(y_arr))

            # Add some padding
            x_pad = (x_max - x_min) * 0.05 if x_max > x_min else 0.5
            y_pad = (y_max - y_min) * 0.05 if y_max > y_min else 0.5

            # Set same range for all cells
            for cell in cells:
                cell.setXRange(x_min - x_pad, x_max + x_pad, padding=0)
                cell.setYRange(y_min - y_pad, y_max + y_pad, padding=0)

            # Link X and Y axes for synchronized zoom/pan
            if len(cells) > 1:
                main_vb = cells[0].getViewBox()
                for cell in cells[1:]:
                    cell.getViewBox().setXLink(main_vb)
                    cell.getViewBox().setYLink(main_vb)

        except Exception as e:
            logger.warning(f"Failed to sync grid axes: {e}", exc_info=True)
