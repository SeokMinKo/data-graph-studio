"""
Graph Panel - 메인 그래프 + 옵션 + 범례 + 통계

Coordinator module. Rendering logic is delegated to mixin classes:
  - ComboChartMixin     (renderers/combo_renderer.py)
  - StatisticalChartMixin (renderers/statistical_renderer.py)
  - GridChartMixin      (renderers/grid_renderer.py)
  - DrawingToolsMixin   (drawing_tools.py)
"""

import logging
from typing import Optional, List, Dict, Any

import numpy as np
import polars as pl
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSplitter, QDialog, QGridLayout
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor

from ....core.state import AppState, ChartType, ComparisonMode, AggregationType
from ....core.data_engine import DataEngine
from ....core.expression_engine import ExpressionEngine, ExpressionError
from ....graph.sampling import DataSampler
from ...drawing import (
    DrawingManager, DrawingStyle, DrawingStyleDialog
)
from ..empty_state import EmptyStateWidget
from ..sliding_window import SlidingWindowWidget
from ..graph_widgets import ColorButton, ExpandedChartDialog, ClickablePlotWidget, FormattedAxisItem  # noqa: F401
from ..graph_options_panel import GraphOptionsPanel
from ..stat_panel import StatPanel
from ..main_graph import MainGraph
from ..minimap_widget import MinimapWidget

from .renderers import ComboChartMixin, StatisticalChartMixin, GridChartMixin
from .drawing_tools import DrawingToolsMixin

_lg = logging.getLogger(__name__)


# ==================== Graph Panel ====================

class GraphPanel(ComboChartMixin, StatisticalChartMixin, GridChartMixin, DrawingToolsMixin, QWidget):
    """
    Graph Panel - Main container

    Layout:
    ┌──────────────┬───────────────────────────┬──────────┐
    │   Options    │       Main Graph          │  Stats   │
    │ (280px)      │    + Sliding Windows      │ (180px)  │
    │ (Chart/      │                           │          │
    │  Legend/     │                           │          │
    │  Axes/Style) │                           │          │
    └──────────────┴───────────────────────────┴──────────┘

    Rendering is delegated to mixin classes:
      ComboChartMixin, StatisticalChartMixin, GridChartMixin, DrawingToolsMixin
    """

    def __init__(self, state: AppState, engine: DataEngine):
        super().__init__()
        self.state = state
        self.engine = engine

        # Sliding window state
        self._sliding_window_enabled = False
        self._x_window_enabled = True
        self._y_window_enabled = True

        # Active filter (Item 15): {col: [values]}
        self._active_filter: Dict[str, list] = {}

        # Mapping from original DataFrame row indices to sampled array indices
        # Used by selection highlight to correctly map state.selection rows
        self._sampled_original_indices: Optional[np.ndarray] = None

        # P1-2: Categorical mapping cache {col_name: (labels_tuple, value_to_idx_dict)}
        self._categorical_cache: Dict[str, tuple] = {}

        # Minimap state
        self._minimap_enabled = False
        self._minimap_syncing = False  # guard against infinite loop

        # Debounced refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(30)
        self._refresh_timer.timeout.connect(self.refresh)

        # Debounced style-only refresh timer (no data recomputation)
        self._style_refresh_timer = QTimer(self)
        self._style_refresh_timer.setSingleShot(True)
        self._style_refresh_timer.setInterval(30)
        self._style_refresh_timer.timeout.connect(self._do_style_refresh)

        # Cache of the last options dict — used to detect style-only changes
        self._last_options_snapshot: Optional[Dict] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setObjectName("themeSplitter")

        # Options Panel (left) - now includes Legend as a tab
        self.options_panel = GraphOptionsPanel(self.state)
        self.splitter.addWidget(self.options_panel)

        # Center panel with main graph and sliding windows
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)

        # Stack widget for empty state vs graph view
        from PySide6.QtWidgets import QStackedWidget
        self._center_stack = QStackedWidget()

        # Page 0: Empty State
        self._empty_state = EmptyStateWidget()
        self._center_stack.addWidget(self._empty_state)

        # Page 1: Graph container with Y sliding window
        graph_container = QWidget()
        graph_layout = QHBoxLayout(graph_container)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(2)

        # Y-axis sliding window (left of graph)
        self.y_sliding_window = SlidingWindowWidget(orientation='vertical')
        self.y_sliding_window.setVisible(False)  # Hidden by default
        graph_layout.addWidget(self.y_sliding_window)

        # Main Graph (single view mode)
        self.main_graph = MainGraph(self.state)
        graph_layout.addWidget(self.main_graph, 1)

        # Grid View Container (facet mode) - hidden by default
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        self._grid_layout.setSpacing(4)
        self._grid_container.setVisible(False)
        graph_layout.addWidget(self._grid_container, 1)

        # List to hold grid cell PlotWidgets
        self._grid_cells: List[pg.PlotWidget] = []
        self._grid_cell_labels: List[QLabel] = []

        self._center_stack.addWidget(graph_container)

        # Default to empty state
        self._center_stack.setCurrentIndex(0)

        center_layout.addWidget(self._center_stack, 1)

        # Minimap (below graph, above sliding window)
        self.minimap = MinimapWidget()
        self.minimap.setVisible(False)
        center_layout.addWidget(self.minimap)

        # X-axis sliding window (below graph)
        self.x_sliding_window = SlidingWindowWidget(orientation='horizontal')
        self.x_sliding_window.setVisible(False)  # Hidden by default
        center_layout.addWidget(self.x_sliding_window)

        self.splitter.addWidget(center_widget)

        # Stat Panel (right) - no float button
        self.stat_panel = StatPanel(self.state)
        self.splitter.addWidget(self.stat_panel)

        # Splitter sizes: Options(280) + Graph(stretch) + Stats(360) - Stats doubled
        self.splitter.setSizes([280, 500, 360])
        self.splitter.setStretchFactor(0, 0)  # Options: fixed
        self.splitter.setStretchFactor(1, 1)  # Graph: stretch
        self.splitter.setStretchFactor(2, 0)  # Stats: fixed (2x width)

        layout.addWidget(self.splitter)

        # Initialize DrawingManager with a visible default color
        self._drawing_manager = DrawingManager(self.main_graph)
        self._drawing_manager.current_style.stroke_color = "#FF0000"
        self._drawing_manager.current_style.stroke_width = 2.0
        self.main_graph._current_drawing_style.stroke_color = "#FF0000"
        self.main_graph._current_drawing_style.stroke_width = 2.0
        self.main_graph.set_drawing_manager(self._drawing_manager)

    def _connect_signals(self):
        self.state.chart_settings_changed.connect(self._on_chart_settings_changed)
        self.state.group_zone_changed.connect(self._on_group_changed)
        self.state.value_zone_changed.connect(self._on_value_zone_changed)
        self.state.hover_zone_changed.connect(self._schedule_refresh)
        self.state.selection_changed.connect(self._on_selection_changed)
        self.options_panel.option_changed.connect(self._on_options_panel_changed)

        # Filter signal from DataTab (Item 15)
        self.options_panel.data_tab.filter_changed.connect(self._on_filter_changed)

        # Connect graph selection to state
        self.main_graph.points_selected.connect(self._on_graph_points_selected)

        # Connect sliding window signals
        self.x_sliding_window.range_changed.connect(self._on_x_window_changed)
        self.y_sliding_window.range_changed.connect(self._on_y_window_changed)

        # Connect view range changes to update sliding windows
        self.main_graph.plotItem.sigRangeChanged.connect(self._on_graph_range_changed)

        # Minimap signals
        self.minimap.region_changed.connect(self._on_minimap_region_changed)
        self.main_graph.plotItem.sigRangeChanged.connect(self._on_main_graph_range_for_minimap)

        # Grid View signal
        self.state.grid_view_changed.connect(self._on_grid_view_changed)

        # Update Grid View split columns when filter columns change
        self.options_panel.data_tab.filter_changed.connect(self._update_grid_split_columns)

        # Empty state signals (will be connected by MainWindow to handle file open)
        # self._empty_state.open_file_requested is exposed for external connection

    # Keys whose change never requires data recomputation.
    _STYLE_ONLY_KEYS = frozenset({
        'line_width', 'line_style', 'marker_size', 'marker_shape',
        'marker_border', 'fill_opacity', 'bg_color',
        'show_labels', 'show_points', 'smooth',
    })

    def _on_options_panel_changed(self):
        """Route option_changed to style-only or full refresh based on what changed."""
        try:
            current = self.options_panel.get_chart_options()
            prev = self._last_options_snapshot

            if prev is not None:
                changed_keys = {k for k in set(current) | set(prev) if current.get(k) != prev.get(k)}
                if changed_keys and changed_keys.issubset(self._STYLE_ONLY_KEYS):
                    self._last_options_snapshot = current
                    self._schedule_style_refresh()
                    return
        except Exception:
            pass

        try:
            self._last_options_snapshot = self.options_panel.get_chart_options()
        except Exception:
            pass
        self._schedule_refresh()

    def _schedule_refresh(self, *args):
        """Debounced refresh - coalesces rapid changes into single refresh."""
        self._refresh_timer.start()

    def _schedule_style_refresh(self, *args):
        """Debounced style-only refresh."""
        self._style_refresh_timer.start()

    def _do_style_refresh(self):
        """Apply visual-property changes to existing plot items in-place."""
        plot_items = getattr(self.main_graph, '_plot_items', [])
        scatter_items = getattr(self.main_graph, '_scatter_items', [])
        if not plot_items and not scatter_items:
            self.refresh()
            return

        options = self.options_panel.get_chart_options()
        chart_type = options.get('chart_type', ChartType.LINE)
        if chart_type in (ChartType.BOX, ChartType.VIOLIN, ChartType.HEATMAP):
            self.refresh()
            return
        grid_enabled = options.get('enabled', False)
        if grid_enabled:
            self.refresh()
            return

        line_width = options.get('line_width', 2)
        marker_size = options.get('marker_size', 6)
        bg_color = options.get('bg_color', QColor('#323D4A'))
        fill_opacity = options.get('fill_opacity', 0.3)

        self.main_graph.setBackground(bg_color.name())

        for item in plot_items:
            try:
                existing_pen = item.opts.get('pen') if hasattr(item, 'opts') else None
                if existing_pen is None and hasattr(item, 'pen'):
                    existing_pen = item.pen()
                if existing_pen is not None:
                    new_pen = pg.mkPen(existing_pen)
                    new_pen.setWidth(line_width)
                    if hasattr(item, 'setPen'):
                        item.setPen(new_pen)
                if chart_type == ChartType.AREA and hasattr(item, 'opts'):
                    existing_brush = item.opts.get('brush')
                    if existing_brush is not None:
                        c = QColor(existing_brush.color())
                        c.setAlphaF(fill_opacity)
                        item.setBrush(pg.mkBrush(c))
            except Exception:
                pass

        for item in scatter_items:
            try:
                item.setSize(marker_size)
            except Exception:
                pass

    def _on_grid_view_changed(self):
        """Handle Grid View settings change."""
        self.refresh()

    def _update_grid_split_columns(self, filter_dict=None):
        """Update Grid View split column options based on filter panel selections."""
        filter_columns = list(self._active_filter.keys()) if self._active_filter else []
        group_col_names = [gc.name for gc in self.state.group_columns]
        all_columns = list(set(filter_columns + group_col_names))
        self.options_panel.update_grid_split_columns(all_columns)

    def _on_value_zone_changed(self):
        """Handle value zone changes — auto-switch chart type for combo."""
        num_values = len(self.state.value_columns)
        current_type = self.state._chart_settings.chart_type

        if num_values >= 2 and current_type != ChartType.COMBINATION:
            self._pre_combo_chart_type = current_type
            self.state.set_chart_type(ChartType.COMBINATION)
            self.options_panel.chart_type_combo.blockSignals(True)
            for i in range(self.options_panel.chart_type_combo.count()):
                if self.options_panel.chart_type_combo.itemData(i) == ChartType.COMBINATION:
                    self.options_panel.chart_type_combo.setCurrentIndex(i)
                    break
            self.options_panel.chart_type_combo.blockSignals(False)
            self.options_panel._combo_series_widget.setVisible(True)
            self.options_panel._rebuild_combo_series_ui()
        elif num_values <= 1 and self.state._chart_settings.chart_type == ChartType.COMBINATION:
            restore_type = getattr(self, '_pre_combo_chart_type', ChartType.LINE)
            self.state.set_chart_type(restore_type)
            self.options_panel.chart_type_combo.blockSignals(True)
            for i in range(self.options_panel.chart_type_combo.count()):
                if self.options_panel.chart_type_combo.itemData(i) == restore_type:
                    self.options_panel.chart_type_combo.setCurrentIndex(i)
                    break
            self.options_panel.chart_type_combo.blockSignals(False)
            self.options_panel._combo_series_widget.setVisible(False)
        elif current_type == ChartType.COMBINATION and num_values >= 2:
            self.options_panel._combo_series_widget.setVisible(True)
            self.options_panel._rebuild_combo_series_ui()

        self.refresh()

    def _on_filter_changed(self, filter_dict):
        """Handle filter changes from DataTab (Item 15)."""
        self._active_filter = dict(filter_dict) if filter_dict else {}
        self.refresh()

    def _on_graph_points_selected(self, indices: list):
        """Handle selection from graph (rect select, lasso select)."""
        if indices:
            self.state.select_rows(indices)

    def _on_x_window_changed(self, min_val: float, max_val: float):
        """Handle X-axis sliding window range change."""
        if self._sliding_window_enabled and self._x_window_enabled:
            self.main_graph.setXRange(min_val, max_val, padding=0)

    def _on_y_window_changed(self, min_val: float, max_val: float):
        """Handle Y-axis sliding window range change."""
        if self._sliding_window_enabled and self._y_window_enabled:
            self.main_graph.setYRange(min_val, max_val, padding=0)

    def _on_graph_range_changed(self, vb, ranges):
        """Update sliding windows when graph range changes."""
        if not self._sliding_window_enabled:
            return

        x_range, y_range = ranges
        if self._x_window_enabled:
            self.x_sliding_window.set_window(x_range[0], x_range[1])
        if self._y_window_enabled:
            self.y_sliding_window.set_window(y_range[0], y_range[1])

    def set_sliding_window_enabled(self, enabled: bool, x_enabled: bool = True, y_enabled: bool = True):
        """Enable or disable sliding window controls."""
        self._sliding_window_enabled = enabled
        self._x_window_enabled = x_enabled
        self._y_window_enabled = y_enabled

        self.x_sliding_window.setVisible(enabled and x_enabled)
        self.y_sliding_window.setVisible(enabled and y_enabled)

        if enabled:
            self._update_sliding_window_data()

    def _update_sliding_window_data(self):
        """Update sliding window data from current graph data."""
        if self.main_graph._data_x is not None:
            self.x_sliding_window.set_data(self.main_graph._data_x)
        if self.main_graph._data_y is not None:
            self.y_sliding_window.set_data(self.main_graph._data_y)

    # ==================== Minimap ====================

    def toggle_minimap(self, enabled: Optional[bool] = None):
        """Toggle minimap visibility."""
        if enabled is None:
            enabled = not self._minimap_enabled
        self._minimap_enabled = enabled
        self.minimap.setVisible(enabled)
        if enabled:
            self._schedule_refresh()

    def _on_minimap_region_changed(self, x_min: float, x_max: float):
        """User dragged minimap region → update main graph."""
        if self._minimap_syncing:
            return
        self._minimap_syncing = True
        try:
            self.main_graph.setXRange(x_min, x_max, padding=0)
        finally:
            self._minimap_syncing = False

    def _on_main_graph_range_for_minimap(self, vb, ranges):
        """Main graph range changed → update minimap region."""
        if not self._minimap_enabled or self._minimap_syncing:
            return
        self._minimap_syncing = True
        try:
            x_range = ranges[0]
            self.minimap.set_region(x_range[0], x_range[1])
        finally:
            self._minimap_syncing = False

    def _on_group_changed(self):
        """그룹 변경 시 범례 업데이트."""
        if self.state.group_columns:
            groups = self._build_group_masks()
            if groups:
                self.options_panel.set_series(list(groups.keys()))
        else:
            if self.state.value_columns:
                self.options_panel.set_series([self.state.value_columns[0].name])
            else:
                self.options_panel.set_series(["Data"])
        self.refresh()

    def _aggregate_values(self, values: np.ndarray, agg: AggregationType) -> float:
        """Aggregate values using selected aggregation type."""
        if values is None or len(values) == 0:
            return 0.0
        clean = values[~np.isnan(values)]
        if len(clean) == 0:
            return 0.0
        if agg == AggregationType.MEAN:
            return float(np.mean(clean))
        if agg == AggregationType.COUNT:
            return float(len(clean))
        if agg == AggregationType.MIN:
            return float(np.min(clean))
        if agg == AggregationType.MAX:
            return float(np.max(clean))
        return float(np.sum(clean))

    def refresh(self):
        """Refresh graph."""
        import logging as _logging
        _lg = _logging.getLogger(__name__)
        _lg.debug("[DEBUG-CRASH] graph_panel.refresh() called")

        # Show empty state if no data loaded
        if not self.engine.is_loaded:
            _lg.debug("[DEBUG-CRASH] graph_panel.refresh() - showing empty state")
            self._center_stack.setCurrentIndex(0)  # Empty state
            return

        # Data is loaded - show graph view
        self._center_stack.setCurrentIndex(1)  # Graph view

        # Guard against reentrant calls (can cause access violation in pyqtgraph)
        if getattr(self, '_refreshing', False):
            _lg.debug("Skipping reentrant refresh")
            return
        self._refreshing = True
        # P1-7: Suppress visual updates during refresh to avoid blank flash
        self.main_graph.setUpdatesEnabled(False)
        try:
            self._do_refresh()
        except Exception as e:
            _lg.error(f"graph_panel.refresh() error: {e}")
        finally:
            self.main_graph.setUpdatesEnabled(True)
            self._refreshing = False

    def _do_refresh(self):
        """Internal refresh implementation."""

        # Check if we're in overlay comparison mode
        if (self.state.comparison_mode == ComparisonMode.OVERLAY and
                len(self.state.comparison_dataset_ids) >= 2):
            self._refresh_overlay_comparison()
            return

        # Get options including legend settings
        options = self.options_panel.get_chart_options()
        legend_settings = self.options_panel.get_legend_settings()

        # Check if Grid View is enabled
        grid_enabled = options.get('enabled', False)  # from get_grid_view_settings()
        grid_split_by = options.get('split_by')

        if grid_enabled and grid_split_by:
            self._refresh_grid_view(options, legend_settings)
            return

        # Single graph mode - hide grid container, show main graph
        self._grid_container.setVisible(False)
        self.main_graph.setVisible(True)

        # Intercept statistical chart types that need special handling
        chart_type = options.get('chart_type', ChartType.LINE)
        if chart_type in (ChartType.BOX, ChartType.VIOLIN, ChartType.HEATMAP):
            self._refresh_statistical_chart(chart_type, options, legend_settings)
            return

        # Get sampling settings from options
        show_all_data = options.get('show_all_data', False)
        max_points = options.get('max_points', 10000)
        sampling_algorithm = options.get('sampling_algorithm', 'auto')

        # Apply filter (Item 15) — push predicates to Polars lazy layer before collect
        working_df = self.engine.get_filtered_df(self._active_filter)
        if working_df is not None and self._active_filter and len(working_df) == 0:
            self.main_graph.clear_plot()
            self.main_graph.setTitle(
                "No data matches current filters",
                color='#94A3B8', size='12pt'
            )
            return

        # X column (from state, set by X Zone)
        x_col = self.state.x_column
        x_categorical_labels = None
        x_is_categorical = False

        # P1-2: Invalidate categorical cache if X column changed
        if x_col and x_col not in self._categorical_cache:
            self._categorical_cache.clear()  # New X col → clear stale entries

        if not x_col:
            if self.engine.is_windowed and working_df is not None:
                x_data = np.arange(len(working_df))
            else:
                x_data = np.arange(len(working_df) if working_df is not None else self.engine.row_count)
            options['x_title'] = options.get('x_title') or 'Index'
        else:
            x_is_categorical = self.engine.is_column_categorical(x_col)

            if x_is_categorical:
                cache_key = x_col
                cached = self._categorical_cache.get(cache_key)
                if cached is not None:
                    x_categorical_labels, value_to_idx = cached
                else:
                    x_categorical_labels = self.engine.get_unique_values(x_col, limit=500)
                    value_to_idx = {v: i for i, v in enumerate(x_categorical_labels)}
                    self._categorical_cache[cache_key] = (x_categorical_labels, value_to_idx)
                x_raw = working_df[x_col].to_list()
                x_data = np.array([value_to_idx.get(v, 0) for v in x_raw], dtype=np.float64)
            else:
                x_data = working_df[x_col].to_numpy()

            options['x_title'] = options.get('x_title') or x_col

        # Coerce non-numeric X data (e.g., datetime strings) to numeric for plotting
        if not x_is_categorical and x_data is not None and len(x_data) > 0:
            try:
                if getattr(x_data, "dtype", None) is not None and x_data.dtype.kind in ("U", "S", "O"):
                    s = pl.Series("x", x_data)
                    parsed = s.str.strptime(pl.Datetime, strict=False)
                    if parsed.null_count() < len(parsed):
                        x_data = parsed.dt.timestamp("ms").to_numpy()
                        options['x_format'] = options.get('x_format') or 'time'
                    else:
                        x_categorical_labels = self.engine.get_unique_values(x_col, limit=500) if x_col else list(dict.fromkeys(x_data))[:500]
                        value_to_idx = {v: i for i, v in enumerate(x_categorical_labels)}
                        x_data = np.array([value_to_idx.get(v, 0) for v in x_data], dtype=np.float64)
                        x_is_categorical = True
                        self._x_axis.set_categorical(x_categorical_labels)
            except Exception:
                pass

        # Build group masks early (needed for combo chart too)
        groups = None
        if self.state.group_columns:
            groups = self._build_group_masks(working_df)

        # Item 14: combo chart when 2+ Y columns are selected
        if len(self.state.value_columns) >= 2:
            self._refresh_combo_chart(working_df, x_data, x_col, x_categorical_labels,
                                       x_is_categorical, options, legend_settings, groups)
            return

        # Y column
        y_formula = ""
        y_categorical_labels = None
        y_is_categorical = False

        if self.state.value_columns:
            value_col = self.state.value_columns[0]
            y_col_name = value_col.name
            y_formula = value_col.formula or ""
        else:
            numeric_cols = [
                col for col in self.engine.columns
                if self.engine.dtypes.get(col, '').startswith(('Int', 'Float'))
            ]
            if numeric_cols:
                y_col_name = numeric_cols[0]
            else:
                if self.engine.columns:
                    y_col_name = self.engine.columns[0]
                else:
                    return

        # Check if Y column is categorical
        y_is_categorical = self.engine.is_column_categorical(y_col_name)

        if y_is_categorical:
            y_categorical_labels = self.engine.get_unique_values(y_col_name, limit=500)
            value_to_idx = {v: i for i, v in enumerate(y_categorical_labels)}
            y_raw = working_df[y_col_name].to_list()
            y_data = np.array([value_to_idx.get(v, 0) for v in y_raw], dtype=np.float64)
        else:
            y_data = working_df[y_col_name].to_numpy()

        # Apply Y formula if specified
        if y_formula and not y_is_categorical:
            y_data = self._apply_y_formula(y_data, y_formula, y_col_name)
            if y_formula:
                options['y_title'] = options.get('y_title') or f"{y_col_name} [{y_formula}]"
        else:
            options['y_title'] = options.get('y_title') or y_col_name

        if groups is None and self.state.group_columns:
            groups = self._build_group_masks(working_df)

        total_points = len(x_data)

        OPENGL_THRESHOLD = 50000
        needs_opengl = total_points > OPENGL_THRESHOLD or (show_all_data and total_points > max_points)
        self.main_graph.enable_opengl(needs_opengl)

        is_sampled = False
        algorithm_used = ""

        def _apply_sampling(x_arr, y_arr, n_points, algo):
            """Apply sampling algorithm to data arrays."""
            if algo == 'auto':
                return DataSampler.auto_sample(x_arr, y_arr, max_points=n_points)
            elif algo == 'lttb':
                return DataSampler.lttb(x_arr, y_arr, threshold=n_points)
            elif algo == 'minmax':
                return DataSampler.min_max_per_bucket(x_arr, y_arr, n_buckets=max(1, n_points // 2))
            elif algo == 'random':
                return DataSampler.random_sample(x_arr, y_arr, n_samples=n_points)
            else:
                return DataSampler.auto_sample(x_arr, y_arr, max_points=n_points)

        if x_is_categorical or y_is_categorical:
            x_sampled, y_sampled = x_data, y_data
        elif show_all_data:
            x_sampled, y_sampled = x_data, y_data
        elif total_points > max_points:
            try:
                valid_mask = ~(np.isnan(x_data.astype(float)) | np.isnan(y_data.astype(float)))
                x_valid = x_data[valid_mask].astype(np.float64)
                y_valid = y_data[valid_mask].astype(np.float64)

                if len(x_valid) > max_points:
                    is_sampled = True

                    if groups is not None and len(groups) > 0:
                        group_sizes = {name: np.sum(mask[valid_mask]) for name, mask in groups.items()}
                        total_valid = sum(group_sizes.values())
                        min_points_per_group = max(10, max_points // 100)

                        x_sampled_list = []
                        y_sampled_list = []
                        original_indices_list = []
                        new_groups = {}
                        current_offset = 0
                        valid_indices = np.where(valid_mask)[0]

                        for group_name, mask in groups.items():
                            group_valid_mask = mask[valid_mask]
                            x_group = x_valid[group_valid_mask]
                            y_group = y_valid[group_valid_mask]
                            group_orig_indices = valid_indices[group_valid_mask]

                            if len(x_group) == 0:
                                continue

                            group_ratio = len(x_group) / total_valid if total_valid > 0 else 0
                            group_points = max(min_points_per_group, int(max_points * group_ratio))

                            if len(x_group) > group_points:
                                x_group_sampled, y_group_sampled = _apply_sampling(
                                    x_group, y_group, group_points, sampling_algorithm
                                )
                                try:
                                    x_g_f = x_group.astype(np.float64)
                                    x_gs_f = x_group_sampled.astype(np.float64)
                                    if np.all(x_g_f[:-1] <= x_g_f[1:]) and len(x_g_f) > 0:
                                        matched = np.searchsorted(x_g_f, x_gs_f).clip(0, len(x_g_f) - 1)
                                    else:
                                        step = max(1, len(x_group) // max(1, len(x_group_sampled)))
                                        matched = np.arange(0, len(x_group), step)[:len(x_group_sampled)]
                                    group_sampled_orig = group_orig_indices[matched]
                                except Exception:
                                    group_sampled_orig = group_orig_indices[:len(x_group_sampled)]
                            else:
                                x_group_sampled, y_group_sampled = x_group, y_group
                                group_sampled_orig = group_orig_indices

                            group_len = len(x_group_sampled)
                            np.zeros(0, dtype=bool)

                            x_sampled_list.append(x_group_sampled)
                            y_sampled_list.append(y_group_sampled)
                            original_indices_list.append(group_sampled_orig)
                            new_groups[group_name] = (current_offset, group_len)
                            current_offset += group_len

                        if x_sampled_list:
                            x_sampled = np.concatenate(x_sampled_list)
                            y_sampled = np.concatenate(y_sampled_list)

                            if original_indices_list:
                                self._sampled_original_indices = np.concatenate(original_indices_list)

                            total_sampled = len(x_sampled)
                            groups = {}
                            for group_name, (offset, length) in new_groups.items():
                                mask = np.zeros(total_sampled, dtype=bool)
                                mask[offset:offset + length] = True
                                groups[group_name] = mask
                        else:
                            x_sampled, y_sampled = x_valid, y_valid
                    else:
                        if sampling_algorithm == 'auto':
                            x_sampled, y_sampled = DataSampler.auto_sample(
                                x_valid, y_valid, max_points=max_points
                            )
                            is_sorted = np.all(x_valid[:-1] <= x_valid[1:])
                            algorithm_used = "LTTB" if is_sorted else "Min-Max"
                        elif sampling_algorithm == 'lttb':
                            x_sampled, y_sampled = DataSampler.lttb(
                                x_valid, y_valid, threshold=max_points
                            )
                            algorithm_used = "LTTB"
                        elif sampling_algorithm == 'minmax':
                            x_sampled, y_sampled = DataSampler.min_max_per_bucket(
                                x_valid, y_valid, n_buckets=max_points // 2
                            )
                            algorithm_used = "Min-Max"
                        elif sampling_algorithm == 'random':
                            x_sampled, y_sampled = DataSampler.random_sample(
                                x_valid, y_valid, n_samples=max_points
                            )
                            algorithm_used = "Random"
                        else:
                            x_sampled, y_sampled = DataSampler.auto_sample(
                                x_valid, y_valid, max_points=max_points
                            )
                            algorithm_used = "Auto"

                    if not algorithm_used:
                        if sampling_algorithm == 'auto':
                            is_sorted = np.all(x_valid[:-1] <= x_valid[1:])
                            algorithm_used = "LTTB" if is_sorted else "Min-Max"
                        else:
                            algorithm_used = sampling_algorithm.upper()
                else:
                    x_sampled, y_sampled = x_valid, y_valid
            except (ValueError, TypeError):
                x_sampled, y_sampled = x_data, y_data
        else:
            x_sampled, y_sampled = x_data, y_data

        # Track which original rows survived sampling (for selection highlight)
        if is_sampled and len(x_sampled) < total_points:
            try:
                x_orig_f = x_data.astype(np.float64) if hasattr(x_data, 'astype') else np.array(x_data, dtype=np.float64)
                x_samp_f = x_sampled.astype(np.float64) if hasattr(x_sampled, 'astype') else np.array(x_sampled, dtype=np.float64)
                if np.all(x_orig_f[:-1] <= x_orig_f[1:]) and len(x_orig_f) > 0:
                    self._sampled_original_indices = np.searchsorted(x_orig_f, x_samp_f).clip(0, len(x_orig_f) - 1)
                else:
                    step = max(1, len(x_data) // max(1, len(x_sampled)))
                    self._sampled_original_indices = np.arange(0, len(x_data), step)[:len(x_sampled)]
            except Exception:
                self._sampled_original_indices = None
        else:
            self._sampled_original_indices = None

        # P2-3: Disable log scale on categorical axes (log(0) → -inf)
        if x_is_categorical:
            options['x_log'] = False
        if y_is_categorical:
            options['y_log'] = False

        self.main_graph.plot_data(
            x_sampled, y_sampled,
            groups=groups,
            chart_type=options.get('chart_type', ChartType.LINE),
            options=options,
            legend_settings=legend_settings,
            x_categorical_labels=x_categorical_labels,
            y_categorical_labels=y_categorical_labels
        )

        # Update minimap
        if self._minimap_enabled:
            chart_type = options.get('chart_type', ChartType.LINE)
            if chart_type in (ChartType.LINE, ChartType.SCATTER, ChartType.AREA):
                self.minimap.set_data(x_sampled, y_sampled)
                vr = self.main_graph.viewRange()
                self.minimap.set_region(vr[0][0], vr[0][1])
                self.minimap.setVisible(True)
            else:
                self.minimap.setVisible(False)
        else:
            self.minimap.setVisible(False)

        # Update sampling status label
        displayed_points = len(x_sampled)
        self.main_graph.update_sampling_status(
            displayed_points=displayed_points,
            total_points=total_points,
            is_sampled=is_sampled,
            algorithm=algorithm_used
        )

        # Set hover data
        hover_columns = self.state.hover_columns
        if hover_columns:
            hover_data = {}
            sampled_indices = self._sampled_original_indices if (
                self._sampled_original_indices is not None and len(self._sampled_original_indices) == len(x_sampled)
            ) else None

            for col in hover_columns:
                if col in working_df.columns:
                    col_data = working_df[col].to_list()
                    if sampled_indices is not None and len(col_data) > len(x_sampled):
                        col_data = [col_data[i] for i in sampled_indices if i < len(col_data)]
                    elif len(col_data) > len(x_sampled):
                        col_data = col_data[:len(x_sampled)]
                    hover_data[col] = col_data
            self.main_graph.set_hover_data(hover_columns, hover_data)
        else:
            self.main_graph.set_hover_data([], {})

        # Update stats - compute group aggregation for pie chart
        group_data = None
        if groups is not None and len(groups) > 0:
            try:
                group_data = {}
                agg_type = AggregationType.SUM
                if self.state.value_columns:
                    agg_type = self.state.value_columns[0].aggregation
                for group_name, mask in groups.items():
                    group_y = y_sampled[mask]
                    val = self._aggregate_values(group_y, agg_type)
                    group_data[group_name] = abs(val) if val else 0.0
                if all(v == 0.0 for v in group_data.values()):
                    group_data = None
            except Exception:
                group_data = None

        self.stat_panel.update_histograms(x_sampled, y_sampled, group_data)
        if self.state.value_columns:
            stats = self.engine.get_statistics(self.state.value_columns[0].name)

            try:
                clean_x = x_sampled[~np.isnan(x_sampled)]
                clean_y = y_sampled[~np.isnan(y_sampled)]
                if len(clean_x) > 0:
                    stats['X-Diff'] = float(np.max(clean_x) - np.min(clean_x))
                if len(clean_y) > 0:
                    stats['Y-Diff'] = float(np.max(clean_y) - np.min(clean_y))
            except Exception:
                pass

            percentiles = {}
            try:
                clean_y = y_sampled[~np.isnan(y_sampled)]
                if len(clean_y) > 0:
                    pct_list = [0, 1, 2, 3, 4, 5, 10, 25, 50, 75, 90, 95, 97, 99, 99.7, 99.9, 99.99, 100]
                    pct_vals = np.percentile(clean_y, pct_list)
                    percentiles = {f"P{p}": float(v) for p, v in zip(pct_list, pct_vals)}
            except Exception:
                percentiles = {}

            group_counts = {}
            group_sums = {}
            if groups is not None and len(groups) > 0:
                try:
                    for group_name, mask in groups.items():
                        group_y = y_sampled[mask]
                        group_counts[group_name] = int(np.sum(~np.isnan(group_y)))
                        group_sums[group_name] = float(np.nansum(group_y))
                except Exception:
                    group_counts = {}
                    group_sums = {}

            self.stat_panel.update_stats(stats, percentiles, group_counts, group_sums)

        # Update sliding windows with full data for navigation
        sliding_window_enabled = options.get('sliding_window_enabled', False)
        x_window_enabled = options.get('x_sliding_window', True)
        y_window_enabled = options.get('y_sliding_window', True)

        self._sliding_window_enabled = sliding_window_enabled
        self._x_window_enabled = x_window_enabled
        self._y_window_enabled = y_window_enabled

        self.x_sliding_window.setVisible(sliding_window_enabled and x_window_enabled)
        self.y_sliding_window.setVisible(sliding_window_enabled and y_window_enabled)

        if sliding_window_enabled:
            if x_window_enabled and not x_is_categorical:
                try:
                    self.x_sliding_window.set_data(x_sampled.astype(float) if hasattr(x_sampled, 'astype') else np.array(x_sampled, dtype=float))
                except (ValueError, TypeError):
                    pass
            if y_window_enabled and not y_is_categorical:
                try:
                    self.y_sliding_window.set_data(y_sampled.astype(float) if hasattr(y_sampled, 'astype') else np.array(y_sampled, dtype=float))
                except (ValueError, TypeError):
                    pass

    def _apply_y_formula(self, y_data: np.ndarray, formula: str, col_name: str) -> np.ndarray:
        """Apply formula transformation to Y data."""
        if not formula or not formula.strip():
            return y_data

        try:
            expr_engine = ExpressionEngine()
            adjusted_formula = formula.replace('Y', col_name).replace('y', col_name)
            temp_df = pl.DataFrame({col_name: y_data.tolist()})
            result_series = expr_engine.evaluate(adjusted_formula, temp_df)
            return result_series.to_numpy()

        except ExpressionError as e:
            _lg.warning(f"Formula error: {e}")
            self._show_formula_error(str(e))
            return y_data
        except Exception as e:
            _lg.warning(f"Error applying formula '{formula}': {e}")
            self._show_formula_error(str(e))
            return y_data

    def _show_formula_error(self, message: str):
        """Display formula error to user via the graph title."""
        self.main_graph.setTitle(f"⚠ 수식 오류: {message}", color='#EF4444', size='11pt')

    def _on_chart_settings_changed(self):
        """Sync chart type from state to options panel and refresh."""
        try:
            ct = self.state.chart_settings.chart_type
            if ct and self.options_panel.chart_type_combo.currentData() != ct:
                idx = self.options_panel.chart_type_combo.findData(ct)
                if idx >= 0:
                    self.options_panel.chart_type_combo.blockSignals(True)
                    self.options_panel.chart_type_combo.setCurrentIndex(idx)
                    self.options_panel.chart_type_combo.blockSignals(False)
        except Exception:
            pass
        self.refresh()

    def _on_selection_changed(self):
        """Handle selection state change - highlight selected points and update stats."""
        selected_rows = list(self.state.selection.selected_rows)

        if self._sampled_original_indices is not None and selected_rows:
            orig_to_sampled = {int(orig): sampled for sampled, orig in enumerate(self._sampled_original_indices)}
            mapped_rows = [orig_to_sampled[r] for r in selected_rows if r in orig_to_sampled]
            self.main_graph.highlight_selection(mapped_rows)
        else:
            self.main_graph.highlight_selection(selected_rows)

        if selected_rows and self.engine.is_loaded:
            self._update_stats_for_selection(selected_rows)
        else:
            if self.state.value_columns and self.engine.is_loaded:
                stats = self.engine.get_statistics(self.state.value_columns[0].name)
                self.stat_panel.update_stats(stats)

    def _update_stats_for_selection(self, selected_rows: list):
        """P1-6: Update stat panel with statistics for selected rows only."""
        if not self.engine.is_loaded or not selected_rows:
            return

        try:
            df = self.engine.df
            if df is None:
                return

            selected_indices = [i for i in selected_rows if 0 <= i < len(df)]
            if not selected_indices:
                return

            sel_idx = np.array(selected_indices, dtype=np.intp)

            y_col_name = None
            if self.state.value_columns:
                y_col_name = self.state.value_columns[0].name

            if not y_col_name or y_col_name not in df.columns:
                for col in self.engine.columns:
                    dtype = self.engine.dtypes.get(col, '')
                    if dtype.startswith(('Int', 'Float', 'UInt')):
                        y_col_name = col
                        break

            if not y_col_name or y_col_name not in df.columns:
                stats = {
                    'Selected': len(selected_rows),
                    'Total': len(df),
                }
                self.stat_panel.update_stats(stats)
                return

            y_data = df[y_col_name].to_numpy()
            selected_y = y_data[sel_idx]

            x_col = self.state.x_column
            if x_col and x_col in df.columns:
                x_data_full = df[x_col].to_numpy()
                selected_x = x_data_full[sel_idx]
            else:
                selected_x = np.array(selected_indices, dtype=float)

            clean_y = selected_y[~np.isnan(selected_y.astype(float))]
            clean_x = selected_x[~np.isnan(selected_x.astype(float))]
            if len(clean_y) == 0:
                return

            stats = {
                'Selected': len(selected_rows),
                'Mean': float(np.mean(clean_y)),
                'Median': float(np.median(clean_y)),
                'Std': float(np.std(clean_y)),
                'Min': float(np.min(clean_y)),
                'Max': float(np.max(clean_y)),
            }

            if len(clean_x) > 0:
                stats['X-Diff'] = float(np.max(clean_x) - np.min(clean_x))
            if len(clean_y) > 0:
                stats['Y-Diff'] = float(np.max(clean_y) - np.min(clean_y))

            self.stat_panel.update_stats(stats)
            self.stat_panel.update_histograms(selected_x, selected_y)

        except Exception as e:
            _lg.error("graph_panel.update_stats_error", extra={"error": str(e)})

    def _build_group_masks(self, df_override=None) -> Dict[str, np.ndarray]:
        if not self.state.group_columns or not self.engine.is_loaded:
            return None

        df = df_override if df_override is not None else self.engine.df
        n_rows = len(df)
        group_cols = [g.name for g in self.state.group_columns]
        groups = {}

        indexed = df.with_row_index("__row_idx__")
        grouped = indexed.group_by(group_cols).agg(
            pl.col("__row_idx__").alias("__indices__")
        )

        for row in grouped.iter_rows():
            vals = row[:-1]
            indices = row[-1]

            if len(group_cols) == 1:
                group_name = str(vals[0]) if vals[0] is not None else "(Empty)"
            else:
                parts = [str(v) if v is not None else "(Empty)" for v in vals]
                group_name = " / ".join(parts)

            mask = np.zeros(n_rows, dtype=bool)
            mask[indices] = True
            groups[group_name] = mask

        return groups

    def reset_view(self):
        self.main_graph.reset_view()

    def autofit(self):
        """Auto-fit view with margin based on current data."""
        try:
            x = getattr(self.main_graph, "_data_x", None)
            y = getattr(self.main_graph, "_data_y", None)
            if x is None or y is None or len(x) == 0 or len(y) == 0:
                self.main_graph.autoRange()
                return

            x_arr = np.asarray(x, dtype=float)
            y_arr = np.asarray(y, dtype=float)
            finite = np.isfinite(x_arr) & np.isfinite(y_arr)
            if not np.any(finite):
                self.main_graph.autoRange()
                return

            x_min, x_max = np.min(x_arr[finite]), np.max(x_arr[finite])
            y_min, y_max = np.min(y_arr[finite]), np.max(y_arr[finite])

            x_range = max(x_max - x_min, 1.0)
            y_range = max(y_max - y_min, 1.0)
            x_pad = x_range * 0.05
            y_pad = y_range * 0.05

            self.main_graph.setXRange(x_min - x_pad, x_max + x_pad, padding=0)
            self.main_graph.setYRange(y_min - y_pad, y_max + y_pad, padding=0)
        except Exception:
            self.main_graph.autoRange()

    def export_image(self, path: str):
        exporter = pg.exporters.ImageExporter(self.main_graph.plotItem)
        exporter.export(path)

    def clear(self):
        self.main_graph.clear_plot()
        self.stat_panel.update_histograms(None, None)
        self.stat_panel.update_stats(None)

    def set_columns(self, columns: List[str]):
        """컬럼 목록 설정 (범례 초기화용)."""
        numeric_cols = [
            col for col in columns
            if self.engine.dtypes.get(col, '').startswith(('Int', 'Float'))
        ]
        if numeric_cols:
            self.options_panel.set_series([numeric_cols[0]])

    def get_chart_options(self) -> Dict[str, Any]:
        """Get current chart options from the options panel."""
        return self.options_panel.get_chart_options()

    def get_legend_settings(self) -> Dict[str, Any]:
        """Get current legend settings from the options panel."""
        return self.options_panel.get_legend_settings()

    def apply_options(self, options: Dict[str, Any]):
        """Apply chart options to the options panel."""
        if not options:
            return

        if 'title' in options and options['title']:
            self.options_panel.chart_title_edit.setText(options['title'])
        if 'subtitle' in options and options['subtitle']:
            self.options_panel.chart_subtitle_edit.setText(options['subtitle'])

        if 'x_title' in options and options['x_title']:
            self.options_panel.x_title_edit.setText(options['x_title'])
        if 'x_format' in options:
            x_format = options['x_format']
            if x_format:
                format_map = {
                    'number': "Number (#,##0)",
                    'decimal': "Decimal (#,##0.00)",
                    'scientific': "Scientific (0.00E+00)",
                    'percent': "Percent (0.0%)",
                    'k': "K (#,##0,\"K\")",
                    'm': "M (#,##0,,\"M\")",
                    'b': "B (#,##0,,,\"B\")",
                    'bytes': "KB/MB/GB",
                    'time': "ms/s/min",
                }
                if x_format in format_map:
                    idx = self.options_panel.x_format_combo.findText(format_map[x_format])
                    if idx >= 0:
                        self.options_panel.x_format_combo.setCurrentIndex(idx)
                else:
                    self.options_panel.x_format_combo.setCurrentText(x_format)
            else:
                self.options_panel.x_format_combo.setCurrentIndex(0)

        if 'x_log' in options:
            self.options_panel.x_log_check.setChecked(options['x_log'])
        if 'x_reverse' in options:
            self.options_panel.x_reverse_check.setChecked(options['x_reverse'])

        if 'y_title' in options and options['y_title']:
            self.options_panel.y_title_edit.setText(options['y_title'])
        if 'y_format' in options:
            y_format = options['y_format']
            if y_format:
                format_map = {
                    'number': "Number (#,##0)",
                    'decimal': "Decimal (#,##0.00)",
                    'scientific': "Scientific (0.00E+00)",
                    'percent': "Percent (0.0%)",
                    'k': "K (#,##0,\"K\")",
                    'm': "M (#,##0,,\"M\")",
                    'b': "B (#,##0,,,\"B\")",
                    'bytes': "KB/MB/GB",
                    'time': "ms/s/min",
                }
                if y_format in format_map:
                    idx = self.options_panel.y_format_combo.findText(format_map[y_format])
                    if idx >= 0:
                        self.options_panel.y_format_combo.setCurrentIndex(idx)
                else:
                    self.options_panel.y_format_combo.setCurrentText(y_format)
            else:
                self.options_panel.y_format_combo.setCurrentIndex(0)

        if 'y_min' in options and options['y_min'] is not None:
            self.options_panel.y_min_spin.setValue(options['y_min'])
        if 'y_max' in options and options['y_max'] is not None:
            self.options_panel.y_max_spin.setValue(options['y_max'])
        if 'y_log' in options:
            self.options_panel.y_log_check.setChecked(options['y_log'])
        if 'y_reverse' in options:
            self.options_panel.y_reverse_check.setChecked(options['y_reverse'])

        if 'grid_x' in options:
            self.options_panel.grid_x_check.setChecked(options['grid_x'])
        if 'grid_y' in options:
            self.options_panel.grid_y_check.setChecked(options['grid_y'])
        if 'grid_opacity' in options:
            self.options_panel.grid_opacity_slider.setValue(int(options['grid_opacity'] * 100))

        if 'show_labels' in options:
            self.options_panel.show_labels_check.setChecked(options['show_labels'])
        if 'show_points' in options:
            self.options_panel.show_points_check.setChecked(options['show_points'])
        if 'smooth' in options:
            self.options_panel.smooth_check.setChecked(options['smooth'])
        if 'line_width' in options:
            self.options_panel.line_width_spin.setValue(options['line_width'])
        if 'marker_size' in options:
            self.options_panel.marker_size_spin.setValue(options['marker_size'])
        if 'fill_opacity' in options:
            self.options_panel.fill_opacity_spin.setValue(options['fill_opacity'])

        if 'bg_color' in options and options['bg_color']:
            from PySide6.QtGui import QColor
            if isinstance(options['bg_color'], str):
                self.options_panel.bg_color_btn.set_color(QColor(options['bg_color']))

        if 'show_all_data' in options:
            self.options_panel.show_all_data_check.setChecked(options['show_all_data'])
        if 'max_points' in options:
            self.options_panel.max_points_slider.setValue(options['max_points'] // 1000)

        if 'sliding_window_enabled' in options:
            self.options_panel.sliding_window_check.setChecked(options['sliding_window_enabled'])
        if 'x_sliding_window' in options:
            self.options_panel.x_sliding_window_check.setChecked(options['x_sliding_window'])
        if 'y_sliding_window' in options:
            self.options_panel.y_sliding_window_check.setChecked(options['y_sliding_window'])
