"""
Statistical Chart Rendering Mixin for GraphPanel.

Extracted from graph_panel.py as part of the Phase 1 GOAT refactoring.
Uses the mixin pattern so that ``self`` still resolves to the GraphPanel
instance — avoiding the need to pass 5+ dependencies through constructors.

Attributes accessed on ``self`` (from GraphPanel):
    state, engine, main_graph, stat_panel, _active_filter,
    _render_box_plot (self-referential within the mixin)
"""

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from .....core.state import ChartType


class StatisticalChartMixin:
    """Mixin providing statistical chart rendering methods for GraphPanel."""

    def _refresh_statistical_chart(self, chart_type: ChartType, options: Dict, legend_settings: Dict):
        """Render Box Plot, Violin Plot, or Heatmap using specialised chart classes."""
        self.main_graph.clear_plot()
        # Clear any leftover title/axis labels from previous chart types
        self.main_graph.setTitle("")

        df = self.engine.get_filtered_df(self._active_filter)
        if df is None:
            return

        # Apply filter (Item 15) — lazy push-down already applied in get_filtered_df
        if self._active_filter and len(df) == 0:
            # Fix 3: show message when filters exclude all rows in statistical charts
            self.main_graph.setTitle(
                "No data matches current filters",
                color='#94A3B8', size='12pt'
            )
            return

        # Determine category (X/Group) and value (Y) columns
        x_col = self.state.x_column
        group_cols = [g.name for g in self.state.group_columns]

        # Category column: prefer group column, fallback to X
        cat_col = group_cols[0] if group_cols else x_col
        if not cat_col:
            # Need a categorical column for box/violin; use first string column
            for col in self.engine.columns:
                if self.engine.is_column_categorical(col):
                    cat_col = col
                    break
            if not cat_col:
                # Fallback: create a dummy single-category column
                cat_col = None

        # Value column
        y_col_name = None
        if self.state.value_columns:
            y_col_name = self.state.value_columns[0].name
        if not y_col_name:
            numeric_cols = [
                c for c in self.engine.columns
                if self.engine.dtypes.get(c, '').startswith(('Int', 'Float'))
            ]
            y_col_name = numeric_cols[0] if numeric_cols else None

        if not y_col_name or y_col_name not in df.columns:
            return

        bg_color = options.get('bg_color', QColor('#323D4A'))
        self.main_graph.setBackground(bg_color.name())

        from ...theme import ColorPalette
        custom_palette = options.get('color_palette')
        if custom_palette and hasattr(custom_palette, 'colors'):
            default_colors = list(custom_palette.colors)
        elif isinstance(custom_palette, (list, tuple)) and custom_palette:
            default_colors = list(custom_palette)
        else:
            default_colors = list(ColorPalette.default().colors)

        if chart_type == ChartType.BOX:
            self._render_box_plot(df, cat_col, y_col_name, options, default_colors)
        elif chart_type == ChartType.VIOLIN:
            self._render_violin_plot(df, cat_col, y_col_name, options, default_colors)
        elif chart_type == ChartType.HEATMAP:
            self._render_heatmap(df, cat_col, y_col_name, options, group_cols)

        # Update stats
        if self.state.value_columns:
            stats = self.engine.get_statistics(y_col_name)
            self.stat_panel.update_stats(stats)

    # -- Box Plot rendering --------------------------------------------------

    def _render_box_plot(self, df, cat_col, y_col, options, colors):
        """Render a box plot on the main graph."""
        from .....graph.charts.box_plot import BoxPlotChart

        chart = BoxPlotChart()
        pw = self.main_graph

        if cat_col and cat_col in df.columns:
            stats = chart.calculate_stats(df, cat_col, y_col)
        else:
            # Single box for the entire column
            stats = {'All': {}}
            y_data = df[y_col].drop_nulls().to_numpy()
            y_data = y_data[~np.isnan(y_data)]
            if len(y_data) == 0:
                return
            q1, med, q3 = np.percentile(y_data, [25, 50, 75])
            iqr = q3 - q1
            wl = float(y_data[y_data >= q1 - 1.5 * iqr].min()) if np.any(y_data >= q1 - 1.5 * iqr) else q1
            wh = float(y_data[y_data <= q3 + 1.5 * iqr].max()) if np.any(y_data <= q3 + 1.5 * iqr) else q3
            outliers = y_data[(y_data < q1 - 1.5 * iqr) | (y_data > q3 + 1.5 * iqr)]
            stats['All'] = {
                'median': float(med), 'q1': float(q1), 'q3': float(q3),
                'whisker_low': wl, 'whisker_high': wh,
                'outliers': outliers.tolist(),
                'min': float(y_data.min()), 'max': float(y_data.max()),
                'mean': float(y_data.mean()), 'std': float(y_data.std()),
                'count': len(y_data),
            }

        categories = list(stats.keys())
        if not categories:
            return

        for i, cat in enumerate(categories):
            s = stats[cat]
            color = colors[i % len(colors)]

            # Box (IQR)
            box = pg.QtWidgets.QGraphicsRectItem(i - 0.3, s['q1'], 0.6, s['q3'] - s['q1'])
            box.setPen(pg.mkPen(color, width=2))
            box.setBrush(pg.mkBrush(QColor(color).red(), QColor(color).green(), QColor(color).blue(), 80))
            pw.addItem(box)
            self.main_graph._plot_items.append(box)

            # Median line
            median_color = '#1E293B' if self.main_graph._is_light else '#ffffff'
            med_line = pg.PlotCurveItem(
                [i - 0.3, i + 0.3], [s['median'], s['median']],
                pen=pg.mkPen(median_color, width=3),
            )
            pw.addItem(med_line)
            self.main_graph._plot_items.append(med_line)

            # Whiskers
            for wy in (s['whisker_low'], s['whisker_high']):
                cap = pg.PlotCurveItem([i - 0.15, i + 0.15], [wy, wy], pen=pg.mkPen(color, width=2))
                pw.addItem(cap)
                self.main_graph._plot_items.append(cap)
            stem = pg.PlotCurveItem([i, i], [s['whisker_low'], s['q1']], pen=pg.mkPen(color, width=1, style=Qt.DashLine))
            pw.addItem(stem)
            self.main_graph._plot_items.append(stem)
            stem2 = pg.PlotCurveItem([i, i], [s['q3'], s['whisker_high']], pen=pg.mkPen(color, width=1, style=Qt.DashLine))
            pw.addItem(stem2)
            self.main_graph._plot_items.append(stem2)

            # Outliers
            if s.get('outliers'):
                ox = [i] * len(s['outliers'])
                oy = s['outliers']
                scatter = pg.ScatterPlotItem(ox, oy, size=6, pen=pg.mkPen(color), brush=pg.mkBrush(color), symbol='o')
                pw.addItem(scatter)
                self.main_graph._scatter_items.append(scatter)

        # Axis labels
        ax = pw.getAxis('bottom')
        ticks = [(i, str(cat)) for i, cat in enumerate(categories)]
        ax.setTicks([ticks, []])
        pw.setLabel('bottom', cat_col or '')
        pw.setLabel('left', y_col)
        title = options.get('title')
        if title:
            pw.setTitle(title)

        # Auto-fit view range to show all boxes
        n = len(categories)
        if n > 0:
            all_vals = []
            for s in stats.values():
                all_vals.extend([s['whisker_low'], s['whisker_high']])
                all_vals.extend(s.get('outliers', []))
            y_min, y_max = min(all_vals), max(all_vals)
            y_pad = (y_max - y_min) * 0.1 or 1.0
            pw.setXRange(-0.5, n - 0.5, padding=0.05)
            pw.setYRange(y_min - y_pad, y_max + y_pad, padding=0)

    # -- Violin Plot rendering -----------------------------------------------

    def _render_violin_plot(self, df, cat_col, y_col, options, colors):
        """Render a violin plot on the main graph."""
        try:
            from .....graph.charts.violin_plot import ViolinPlotChart
        except ImportError:
            # scipy not available
            self._render_box_plot(df, cat_col, y_col, options, colors)
            return

        chart = ViolinPlotChart()
        pw = self.main_graph

        if cat_col and cat_col in df.columns:
            try:
                density = chart.calculate_density(df, cat_col, y_col, include_box=True)
            except Exception:
                logger.warning("statistical_renderer.render_violin.kde_categorical.error", exc_info=True)
                # Fallback to box plot if KDE fails
                self._render_box_plot(df, cat_col, y_col, options, colors)
                return
        else:
            # Single violin
            y_data = df[y_col].drop_nulls().to_numpy()
            y_data = y_data[~np.isnan(y_data)]
            if len(y_data) < 2:
                return
            try:
                from scipy import stats as scipy_stats
                kde = scipy_stats.gaussian_kde(y_data)
                d_min, d_max = y_data.min(), y_data.max()
                margin = (d_max - d_min) * 0.1
                x_pts = np.linspace(d_min - margin, d_max + margin, 100)
                y_pts = kde(x_pts)
                if y_pts.max() > 0:
                    y_pts = y_pts / y_pts.max()
                density = {'All': {
                    'x': x_pts.tolist(), 'y': y_pts.tolist(),
                    'median': float(np.median(y_data)),
                    'q1': float(np.percentile(y_data, 25)),
                    'q3': float(np.percentile(y_data, 75)),
                }}
            except Exception:
                logger.warning("statistical_renderer.render_violin.kde_single.error", exc_info=True)
                self._render_box_plot(df, cat_col, y_col, options, colors)
                return

        categories = list(density.keys())
        if not categories:
            return

        width = 0.8
        for i, cat in enumerate(categories):
            data = density[cat]
            color = colors[i % len(colors)]
            x_arr = np.array(data['x'])
            y_arr = np.array(data['y']) * width / 2

            # Violin polygon (left + right mirrored)
            left_x = i - y_arr
            right_x = i + y_arr
            path_x = np.concatenate([left_x, right_x[::-1]])
            path_y = np.concatenate([x_arr, x_arr[::-1]])

            # Use QPainterPath polygon for violin shape
            from PySide6.QtGui import QPainterPath, QPolygonF
            from PySide6.QtCore import QPointF
            poly = QPolygonF([QPointF(float(px), float(py)) for px, py in zip(path_x, path_y)])
            pp = QPainterPath()
            pp.addPolygon(poly)
            pp.closeSubpath()
            path_item = pg.QtWidgets.QGraphicsPathItem(pp)
            path_item.setPen(pg.mkPen(color, width=1.5))
            path_item.setBrush(pg.mkBrush(QColor(color).red(), QColor(color).green(), QColor(color).blue(), 60))
            pw.addItem(path_item)
            self.main_graph._plot_items.append(path_item)

            # Inner box (quartiles)
            if data.get('q1') is not None:
                q1, q3 = data['q1'], data['q3']
                inner = pg.QtWidgets.QGraphicsRectItem(i - 0.08, q1, 0.16, q3 - q1)
                inner.setPen(pg.mkPen('#ffffff', width=1))
                inner.setBrush(pg.mkBrush(255, 255, 255, 80))
                pw.addItem(inner)
                self.main_graph._plot_items.append(inner)
            if data.get('median') is not None:
                med_dot = pg.ScatterPlotItem([i], [data['median']], size=8,
                                             pen=pg.mkPen('#ffffff', width=1),
                                             brush=pg.mkBrush('#ffffff'))
                pw.addItem(med_dot)
                self.main_graph._scatter_items.append(med_dot)

        ax = pw.getAxis('bottom')
        ticks = [(i, str(cat)) for i, cat in enumerate(categories)]
        ax.setTicks([ticks, []])
        pw.setLabel('bottom', cat_col or '')
        pw.setLabel('left', y_col)
        title = options.get('title')
        if title:
            pw.setTitle(title)

        # Auto-fit view range for violin
        n = len(categories)
        if n > 0:
            all_x = [d['x'] for d in density.values() if d.get('x')]
            if all_x:
                y_min = min(min(xv) for xv in all_x)
                y_max = max(max(xv) for xv in all_x)
                y_pad = (y_max - y_min) * 0.1 or 1.0
                pw.setXRange(-0.5, n - 0.5, padding=0.05)
                pw.setYRange(y_min - y_pad, y_max + y_pad, padding=0)

    # -- Heatmap rendering ---------------------------------------------------

    def _render_heatmap(self, df, cat_col, y_col, options, group_cols):
        """Render a heatmap on the main graph."""
        pw = self.main_graph

        # Heatmap needs two categorical columns and one value column
        x_col = self.state.x_column
        row_col = group_cols[0] if group_cols else None
        col_col = x_col if x_col and x_col != row_col else None

        if not row_col or not col_col:
            # Need at least 2 categorical dimensions — fallback message
            pw.setTitle("Heatmap requires Group By + X-Axis columns")
            pw.setLabel('left', '')
            pw.setLabel('bottom', '')
            return

        from .....graph.charts.heatmap import HeatmapChart
        chart = HeatmapChart()

        try:
            agg_str = 'sum'
            if self.state.value_columns:
                agg_str = self.state.value_columns[0].aggregation.value
            matrix, row_labels, col_labels = chart.create_matrix(df, row_col, col_col, y_col, agg=agg_str)
        except Exception as e:
            logger.exception("statistical_renderer.render_heatmap.create_matrix.error")
            pw.setTitle(f"Heatmap error: {e}")
            return

        if matrix.size == 0:
            return

        # Use pyqtgraph ImageItem
        import pyqtgraph as pg
        img = pg.ImageItem()
        # Normalise matrix to 0-255 for a colormap
        vmin = np.nanmin(matrix)
        vmax = np.nanmax(matrix)
        if vmax == vmin:
            normed = np.zeros_like(matrix)
        else:
            normed = (matrix - vmin) / (vmax - vmin)
        normed = np.nan_to_num(normed, nan=0.0)

        # Apply a viridis-like LUT
        lut = np.array([
            [68, 1, 84, 255], [72, 35, 116, 255], [64, 67, 135, 255],
            [52, 94, 141, 255], [41, 120, 142, 255], [32, 144, 140, 255],
            [34, 167, 132, 255], [68, 190, 112, 255], [121, 209, 81, 255],
            [189, 222, 38, 255], [253, 231, 37, 255],
        ], dtype=np.uint8)
        # Expand to 256-step LUT
        full_lut = np.zeros((256, 4), dtype=np.uint8)
        for c in range(4):
            full_lut[:, c] = np.interp(np.linspace(0, 1, 256),
                                        np.linspace(0, 1, len(lut)), lut[:, c])

        img.setImage(normed.T * 255)
        img.setLookupTable(full_lut)
        img.setRect(0, 0, len(col_labels), len(row_labels))
        pw.addItem(img)
        self.main_graph._plot_items.append(img)

        # Annotations (cell values)
        max_cells = 200
        if matrix.size <= max_cells:
            for ri, rl in enumerate(row_labels):
                for ci, cl in enumerate(col_labels):
                    v = matrix[ri, ci]
                    if not np.isnan(v):
                        txt = pg.TextItem(f"{v:.1f}", anchor=(0.5, 0.5), color='w')
                        txt.setPos(ci + 0.5, ri + 0.5)
                        pw.addItem(txt)
                        self.main_graph._plot_items.append(txt)

        # Axis labels
        ax_bottom = pw.getAxis('bottom')
        ax_left = pw.getAxis('left')
        ax_bottom.setTicks([[(i + 0.5, str(c)) for i, c in enumerate(col_labels)], []])
        ax_left.setTicks([[(i + 0.5, str(r)) for i, r in enumerate(row_labels)], []])
        pw.setLabel('bottom', col_col)
        pw.setLabel('left', row_col)

        title = options.get('title')
        if title:
            pw.setTitle(title)

        # Auto-fit view range for heatmap
        pw.setXRange(0, len(col_labels), padding=0.02)
        pw.setYRange(0, len(row_labels), padding=0.02)

        # Add colorbar label
        cb_label = f"{y_col} ({vmin:.1f} – {vmax:.1f})"
        pw.setTitle(cb_label if not title else title)
