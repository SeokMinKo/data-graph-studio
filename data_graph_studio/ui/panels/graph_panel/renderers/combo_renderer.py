"""
Combo Chart Rendering Mixin for GraphPanel.

Extracted from graph_panel.py as part of the Phase 1 GOAT refactoring.
Uses the mixin pattern so that ``self`` still resolves to the GraphPanel
instance — avoiding the need to pass 5+ dependencies through constructors.

Attributes accessed on ``self`` (from GraphPanel):
    state, engine, main_graph, options_panel, stat_panel,
    _apply_y_formula (method)
"""

import logging

import numpy as np

import pyqtgraph as pg
from PySide6.QtGui import QColor

from .....core.state import ChartType


logger = logging.getLogger(__name__)

class ComboChartMixin:
    """Mixin providing combo chart rendering methods for GraphPanel."""

    # ------------------------------------------------------------------
    # Low-level series renderers (stateless helpers — no self.xxx access)
    # ------------------------------------------------------------------

    def _render_combo_series(self, x_data, y_data, col_chart_type, color, pen, label,
                              line_width, marker_size, marker_border, graph, options):
        """Render a single series in combo chart on the given graph widget."""
        if col_chart_type == "bar":
            w = (x_data.max() - x_data.min()) / len(x_data) * 0.8 if len(x_data) > 1 else 0.8
            bar = pg.BarGraphItem(x=x_data, height=y_data, width=w,
                                  pen=pg.mkPen(color, width=0.5),
                                  brush=pg.mkBrush(QColor(color).red(), QColor(color).green(), QColor(color).blue(), 160),
                                  name=label)
            graph.addItem(bar)
            graph._plot_items.append(bar)
        elif col_chart_type == "scatter":
            sc_pen = pg.mkPen(color, width=1) if marker_border else pg.mkPen(None)
            sc = pg.ScatterPlotItem(x_data, y_data, size=marker_size,
                                    pen=sc_pen, brush=pg.mkBrush(color), name=label)
            graph.addItem(sc)
            graph._scatter_items.append(sc)
        elif col_chart_type == "area":
            curve = pg.PlotCurveItem(x_data, y_data, pen=pen, name=label,
                                     fillLevel=0, brush=pg.mkBrush(QColor(color).red(), QColor(color).green(), QColor(color).blue(), 80))
            graph.addItem(curve)
            graph._plot_items.append(curve)
        else:
            # Default: line
            item = graph.plot(x_data, y_data, pen=pen, name=label)
            graph._plot_items.append(item)

    def _render_combo_series_vb(self, x_data, y_data, col_chart_type, color, pen, label,
                                line_width, marker_size, marker_border, vb, graph, options):
        """Render a single series in combo chart on a secondary ViewBox."""
        item = None
        if col_chart_type == "bar":
            w = (x_data.max() - x_data.min()) / len(x_data) * 0.8 if len(x_data) > 1 else 0.8
            item = pg.BarGraphItem(x=x_data, height=y_data, width=w,
                                  pen=pg.mkPen(color, width=0.5),
                                  brush=pg.mkBrush(QColor(color).red(), QColor(color).green(), QColor(color).blue(), 160),
                                  name=label)
        elif col_chart_type == "scatter":
            sc_pen = pg.mkPen(color, width=1) if marker_border else pg.mkPen(None)
            item = pg.ScatterPlotItem(x_data, y_data, size=marker_size,
                                    pen=sc_pen, brush=pg.mkBrush(color), name=label)
        elif col_chart_type == "area":
            item = pg.PlotCurveItem(x_data, y_data, pen=pen, name=label,
                                     fillLevel=0, brush=pg.mkBrush(QColor(color).red(), QColor(color).green(), QColor(color).blue(), 80))
        else:
            item = pg.PlotCurveItem(x_data, y_data, pen=pen, name=label)

        if item is not None:
            vb.addItem(item)
            graph._secondary_vb_items.append(item)

    # ------------------------------------------------------------------
    # High-level combo chart orchestrator
    # ------------------------------------------------------------------

    def _refresh_combo_chart(self, working_df, x_data, x_col, x_categorical_labels,
                              x_is_categorical, options, legend_settings, groups=None):
        """Render combo chart with dual Y axes for multiple value columns.

        When groups is provided, renders each group as a separate series with
        distinct colors.
        """
        self.main_graph.clear_plot()

        if working_df is None:
            return

        value_cols = self.state.value_columns

        # Fix 2: warn when more than 2 Y columns are added — only left and
        # right axes are supported; additional columns fall back to primary axis.
        if len(value_cols) > 2:
            self.main_graph.setTitle(
                "Only left and right Y-axes supported. Additional columns will be ignored.",
                color='#F59E0B', size='10pt'
            )
        else:
            self.main_graph.setTitle("")

        options.get('chart_type', ChartType.LINE)
        bg_color = options.get('bg_color', QColor('#323D4A'))
        self.main_graph.setBackground(bg_color.name())
        line_width = options.get('line_width', 2)

        from ...theme import ColorPalette
        custom_palette = options.get('color_palette')
        if custom_palette and hasattr(custom_palette, 'colors'):
            default_colors = list(custom_palette.colors)
        elif isinstance(custom_palette, (list, tuple)) and custom_palette:
            default_colors = list(custom_palette)
        else:
            default_colors = list(ColorPalette.default().colors)

        # Apply axis options
        axis_label_color = '#111827' if self.main_graph._is_light else '#E2E8F0'
        self.main_graph.setLabel('bottom', options.get('x_title') or x_col or 'Index',
                                 **{'font-size': '14px', 'color': axis_label_color})
        if x_categorical_labels:
            self.main_graph._x_axis.set_categorical(x_categorical_labels)
        else:
            self.main_graph._x_axis.clear_categorical()

        grid_x = options.get('grid_x', True)
        grid_y = options.get('grid_y', True)
        grid_alpha = options.get('grid_opacity', 0.3)
        self.main_graph.showGrid(x=grid_x, y=grid_y, alpha=grid_alpha)

        title = options.get('title')
        if title:
            self.main_graph.setTitle(title)

        # Legend
        if legend_settings.get('show', True):
            self.main_graph.legend.show()
        else:
            self.main_graph.legend.hide()

        # Per-column chart type mapping from UI
        combo_series_types = self.options_panel.get_combo_series_chart_types()
        marker_border = options.get('marker_border', False)
        marker_size = options.get('marker_size', 6)

        # Secondary ViewBox for dual axis
        secondary_vb = None

        # Group colors (distinct palette for groups)
        group_colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
            '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
        ]

        for idx, vc in enumerate(value_cols):
            y_col_name = vc.name
            if y_col_name not in working_df.columns:
                continue

            y_data_full = working_df[y_col_name].to_numpy()
            formula = vc.formula or ""
            if formula:
                y_data_full = self._apply_y_formula(y_data_full, formula, y_col_name)

            base_color = vc.color or default_colors[idx % len(default_colors)]
            col_chart_type = combo_series_types.get(y_col_name, "line")

            # Handle groups: render each group as separate series
            if groups is not None and len(groups) > 0:
                for g_idx, (group_name, mask) in enumerate(groups.items()):
                    x_group = x_data[mask]
                    y_group = y_data_full[mask]
                    if len(x_group) == 0:
                        continue

                    # Color: use group index for distinct colors
                    color = group_colors[g_idx % len(group_colors)]
                    pen = pg.mkPen(color, width=line_width)
                    label = f"{y_col_name} ({group_name})"

                    if idx == 0:
                        # Primary axis
                        if g_idx == 0:
                            self.main_graph.setLabel('left', y_col_name, color=base_color, **{'font-size': '14px'})
                            self.main_graph.getAxis('left').setPen(pg.mkPen(base_color))
                            self.main_graph._data_x = x_data
                            self.main_graph._data_y = y_data_full
                        self._render_combo_series(x_group, y_group, col_chart_type, color, pen, label,
                                                  line_width, marker_size, marker_border,
                                                  self.main_graph, options)
                    elif idx == 1:
                        # Secondary axis
                        if g_idx == 0:
                            self.main_graph.showAxis('right')
                            ax_right = self.main_graph.getAxis('right')
                            ax_right.setLabel(y_col_name, color=base_color)
                            ax_right.setPen(pg.mkPen(base_color))

                            secondary_vb = pg.ViewBox()
                            self.main_graph._secondary_vb = secondary_vb
                            self.main_graph.scene().addItem(secondary_vb)
                            ax_right.linkToView(secondary_vb)
                            secondary_vb.setXLink(self.main_graph)

                            def _sync_vb():
                                secondary_vb.setGeometry(self.main_graph.getViewBox().sceneBoundingRect())
                                secondary_vb.linkedViewChanged(self.main_graph.getViewBox(), secondary_vb.XAxis)
                            self.main_graph.getViewBox().sigResized.connect(_sync_vb)
                            _sync_vb()

                        self._render_combo_series_vb(x_group, y_group, col_chart_type, color, pen, label,
                                                     line_width, marker_size, marker_border,
                                                     secondary_vb, self.main_graph, options)
                    else:
                        # 3rd+ column: primary axis
                        self._render_combo_series(x_group, y_group, col_chart_type, color, pen, label,
                                                  line_width, marker_size, marker_border,
                                                  self.main_graph, options)
            else:
                # No groups: original behavior
                color = base_color
                pen = pg.mkPen(color, width=line_width)
                label = y_col_name
                if formula:
                    label = f"{y_col_name} [{formula}]"

                if idx == 0:
                    self.main_graph.setLabel('left', label, color=color, **{'font-size': '14px'})
                    self.main_graph.getAxis('left').setPen(pg.mkPen(color))
                    self._render_combo_series(x_data, y_data_full, col_chart_type, color, pen, label,
                                              line_width, marker_size, marker_border,
                                              self.main_graph, options)
                    self.main_graph._data_x = x_data
                    self.main_graph._data_y = y_data_full
                elif idx == 1:
                    self.main_graph.showAxis('right')
                    ax_right = self.main_graph.getAxis('right')
                    ax_right.setLabel(label, color=color)
                    ax_right.setPen(pg.mkPen(color))

                    secondary_vb = pg.ViewBox()
                    self.main_graph._secondary_vb = secondary_vb
                    self.main_graph.scene().addItem(secondary_vb)
                    ax_right.linkToView(secondary_vb)
                    secondary_vb.setXLink(self.main_graph)

                    self._render_combo_series_vb(x_data, y_data_full, col_chart_type, color, pen, label,
                                                 line_width, marker_size, marker_border,
                                                 secondary_vb, self.main_graph, options)

                    def _sync_vb():
                        secondary_vb.setGeometry(self.main_graph.getViewBox().sceneBoundingRect())
                        secondary_vb.linkedViewChanged(self.main_graph.getViewBox(), secondary_vb.XAxis)
                    self.main_graph.getViewBox().sigResized.connect(_sync_vb)
                    _sync_vb()
                else:
                    # TODO (P1-3): 3rd+ value columns fall back to primary axis.
                    # Implement additional Y axes (offset right axes) for 3+ different
                    # units. Requires UI for axis assignment and spaced axis rendering.
                    self._render_combo_series(x_data, y_data_full, col_chart_type, color, pen, label,
                                              line_width, marker_size, marker_border,
                                              self.main_graph, options)

        # Update series names for legend
        series_names = [vc.name for vc in value_cols if vc.name in working_df.columns]
        self.options_panel.set_series(series_names)

        # P1-5: Stats for ALL Y columns (not just first)
        if value_cols:
            valid_cols = [vc for vc in value_cols if vc.name in working_df.columns]
            if valid_cols:
                y_first = working_df[valid_cols[0].name].to_numpy()
                self.stat_panel.update_histograms(x_data, y_first)

                if len(valid_cols) >= 2:
                    stats_by_col = {}
                    pcts_by_col = {}
                    for vc in valid_cols:
                        col_stats = self.engine.get_statistics(vc.name)
                        stats_by_col[vc.name] = col_stats
                        # Percentiles
                        try:
                            y_arr = working_df[vc.name].to_numpy()
                            clean = y_arr[~np.isnan(y_arr)]
                            if len(clean) > 0:
                                pct_list = [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100]
                                pct_vals = np.percentile(clean, pct_list)
                                pcts_by_col[vc.name] = {f"P{p}": float(v) for p, v in zip(pct_list, pct_vals)}
                        except Exception:
                            logger.warning("combo_renderer.update_stats.percentiles.error", exc_info=True)
                    self.stat_panel.update_multi_y_stats(stats_by_col, pcts_by_col)
                else:
                    stats = self.engine.get_statistics(valid_cols[0].name)
                    self.stat_panel.update_stats(stats)

    # ------------------------------------------------------------------
    # Overlay comparison renderer (combo-adjacent, uses main_graph heavily)
    # ------------------------------------------------------------------

    def _refresh_overlay_comparison(self):
        """
        Overlay comparison mode - render multiple datasets on the same chart.

        Each dataset is rendered with a unique color overlaid on the same chart.
        """
        from .....graph.sampling import DataSampler
        from .....core.state import ChartType

        options = self.options_panel.get_chart_options()
        legend_settings = self.options_panel.get_legend_settings()
        max_points = options.get('max_points', 10000)

        # Clear existing plot
        self.main_graph.clear_plot()

        # Get comparison datasets
        dataset_ids = self.state.comparison_dataset_ids
        colors = self.state.get_comparison_colors()

        # X column
        x_col = self.state.x_column

        all_series_data = []
        total_points = 0

        for dataset_id in dataset_ids:
            dataset = self.engine.get_dataset(dataset_id)
            if not dataset or not dataset.df:
                continue

            metadata = self.state.get_dataset_metadata(dataset_id)
            color = metadata.color if metadata else colors.get(dataset_id, '#1f77b4')
            name = metadata.name if metadata else dataset_id

            df = dataset.df

            # Get X data
            if not x_col or x_col not in df.columns:
                x_data = np.arange(len(df))
            else:
                x_data = df[x_col].to_numpy()

            # Get Y data - use first value column or first numeric column
            y_col_name = None
            if self.state.value_columns:
                y_col_name = self.state.value_columns[0].name
                if y_col_name not in df.columns:
                    y_col_name = None

            if not y_col_name:
                # Find first numeric column
                for col in df.columns:
                    dtype = str(df[col].dtype)
                    if dtype.startswith(('Int', 'Float', 'UInt')):
                        y_col_name = col
                        break

            if not y_col_name:
                continue

            y_data = df[y_col_name].to_numpy()

            # Apply sampling if needed
            if len(x_data) > max_points:
                try:
                    valid_mask = ~(np.isnan(x_data.astype(float)) | np.isnan(y_data.astype(float)))
                    x_valid = x_data[valid_mask].astype(np.float64)
                    y_valid = y_data[valid_mask].astype(np.float64)

                    if len(x_valid) > max_points:
                        x_sampled, y_sampled = DataSampler.auto_sample(
                            x_valid, y_valid, max_points=max_points
                        )
                    else:
                        x_sampled, y_sampled = x_valid, y_valid
                except (ValueError, TypeError):
                    x_sampled, y_sampled = x_data, y_data
            else:
                x_sampled, y_sampled = x_data, y_data

            total_points += len(x_sampled)

            # Hover data for compare overlay
            hover_columns = self.state.hover_columns
            series_hover = {}
            if hover_columns:
                for col in hover_columns:
                    if col in df.columns:
                        col_data = df[col].to_list()
                        if len(col_data) > max_points and len(x_sampled) < len(col_data):
                            step = max(1, len(col_data) // max(1, len(x_sampled)))
                            col_data = col_data[::step][:len(x_sampled)]
                        else:
                            col_data = col_data[:len(x_sampled)]
                        series_hover[col] = col_data

            all_series_data.append({
                'x': x_sampled,
                'y': y_sampled,
                'name': name,
                'color': color,
                'dataset_id': dataset_id,
                'hover_data': series_hover,
            })

        # Plot all series
        if all_series_data:
            self.main_graph.plot_multi_series(
                all_series_data,
                chart_type=options.get('chart_type', ChartType.LINE),
                options=options,
                legend_settings=legend_settings
            )

            # Enable hover in compare overlay
            hover_columns = self.state.hover_columns
            if hover_columns:
                # For multi-series hover we embed hover_data in each series dict.
                # set_hover_data is still used to set which columns are shown.
                self.main_graph.set_hover_data(hover_columns, {})
            else:
                self.main_graph.set_hover_data([], {})

            # Update sampling status
            self.main_graph.update_sampling_status(
                displayed_points=total_points,
                total_points=sum(len(self.engine.get_dataset(did).df)
                               for did in dataset_ids
                               if self.engine.get_dataset(did) and self.engine.get_dataset(did).df is not None),
                is_sampled=total_points < sum(len(self.engine.get_dataset(did).df)
                                            for did in dataset_ids
                                            if self.engine.get_dataset(did) and self.engine.get_dataset(did).df is not None),
                algorithm="Multi-Dataset"
            )

            # Update options panel with series names
            series_names = [s['name'] for s in all_series_data]
            self.options_panel.set_series(series_names)
