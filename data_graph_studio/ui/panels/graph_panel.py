"""
Graph Panel - 메인 그래프 + 옵션 + 범례 + 통계
"""

from typing import Optional, List, Dict, Any
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QScrollArea, QSplitter, QToolButton, QButtonGroup,
    QSizePolicy, QGroupBox, QDialog, QDialogButtonBox,
    QLineEdit, QColorDialog, QPushButton, QSlider,
    QTabWidget, QListWidget, QListWidgetItem, QGridLayout,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtGui import QMouseEvent, QColor, QIcon, QPixmap, QPainter, QBrush

from ..floatable import FloatableSection, FloatButton, FloatWindow
from .sliding_window import SlidingWindowWidget
from .graph_widgets import ColorButton, ExpandedChartDialog, ClickablePlotWidget, FormattedAxisItem
from .data_tab import DataTab

from ...core.state import AppState, ChartType, ToolMode, ComparisonMode, AggregationType
from ...core.data_engine import DataEngine
from ...core.expression_engine import ExpressionEngine, ExpressionError
from ...graph.sampling import DataSampler
from ..drawing import (
    DrawingManager, DrawingStyle, LineStyle,
    LineDrawing, CircleDrawing, RectDrawing, TextDrawing,
    DrawingStyleDialog, RectStyleDialog, TextInputDialog,
    snap_to_angle
)
from .empty_state import EmptyStateWidget
import polars as pl
import pyqtgraph as pg

# Import extracted classes
from .graph_options_panel import GraphOptionsPanel
from .legend_settings_panel import LegendSettingsPanel
from .stat_panel import StatPanel
from .main_graph import MainGraph




# ==================== Graph Panel ====================

class GraphPanel(QWidget):
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
        self.state.hover_zone_changed.connect(self.refresh)
        self.state.selection_changed.connect(self._on_selection_changed)
        self.options_panel.option_changed.connect(self.refresh)

        # Filter signal from DataTab (Item 15)
        self.options_panel.data_tab.filter_changed.connect(self._on_filter_changed)

        # Connect graph selection to state
        self.main_graph.points_selected.connect(self._on_graph_points_selected)

        # Connect sliding window signals
        self.x_sliding_window.range_changed.connect(self._on_x_window_changed)
        self.y_sliding_window.range_changed.connect(self._on_y_window_changed)

        # Connect view range changes to update sliding windows
        self.main_graph.plotItem.sigRangeChanged.connect(self._on_graph_range_changed)

        # Grid View signal
        self.state.grid_view_changed.connect(self._on_grid_view_changed)

        # Update Grid View split columns when filter columns change
        self.options_panel.data_tab.filter_changed.connect(self._update_grid_split_columns)
        
        # Empty state signals (will be connected by MainWindow to handle file open)
        # self._empty_state.open_file_requested is exposed for external connection

    def _on_grid_view_changed(self):
        """Handle Grid View settings change"""
        self.refresh()

    def _update_grid_split_columns(self, filter_dict=None):
        """Update Grid View split column options based on filter panel selections"""
        # Get columns that have filter selections (from DataTab)
        filter_columns = list(self._active_filter.keys()) if self._active_filter else []

        # Also include group columns if any
        group_col_names = [gc.name for gc in self.state.group_columns]
        all_columns = list(set(filter_columns + group_col_names))

        self.options_panel.update_grid_split_columns(all_columns)

    def _on_value_zone_changed(self):
        """Handle value zone changes — auto-switch chart type for combo."""
        num_values = len(self.state.value_columns)
        current_type = self.state._chart_settings.chart_type

        if num_values >= 2 and current_type != ChartType.COMBINATION:
            # Remember the original chart type before auto-switching
            self._pre_combo_chart_type = current_type
            # Auto-switch to Combination when 2+ value columns
            self.state.set_chart_type(ChartType.COMBINATION)
            # Update combo box UI without re-triggering signal
            self.options_panel.chart_type_combo.blockSignals(True)
            for i in range(self.options_panel.chart_type_combo.count()):
                if self.options_panel.chart_type_combo.itemData(i) == ChartType.COMBINATION:
                    self.options_panel.chart_type_combo.setCurrentIndex(i)
                    break
            self.options_panel.chart_type_combo.blockSignals(False)
            # Show per-column chart type UI
            self.options_panel._combo_series_widget.setVisible(True)
            self.options_panel._rebuild_combo_series_ui()
        elif num_values <= 1 and self.state._chart_settings.chart_type == ChartType.COMBINATION:
            # Revert to the original chart type before combo was activated
            restore_type = getattr(self, '_pre_combo_chart_type', ChartType.LINE)
            self.state.set_chart_type(restore_type)
            self.options_panel.chart_type_combo.blockSignals(True)
            for i in range(self.options_panel.chart_type_combo.count()):
                if self.options_panel.chart_type_combo.itemData(i) == restore_type:
                    self.options_panel.chart_type_combo.setCurrentIndex(i)
                    break
            self.options_panel.chart_type_combo.blockSignals(False)
            # Hide per-column chart type UI
            self.options_panel._combo_series_widget.setVisible(False)
        elif current_type == ChartType.COMBINATION and num_values >= 2:
            # Value columns changed while still in Combination — rebuild UI
            self.options_panel._combo_series_widget.setVisible(True)
            self.options_panel._rebuild_combo_series_ui()

        self.refresh()

    def _on_filter_changed(self, filter_dict):
        """Handle filter changes from DataTab (Item 15)."""
        self._active_filter = dict(filter_dict) if filter_dict else {}
        self.refresh()

    def _on_graph_points_selected(self, indices: list):
        """Handle selection from graph (rect select, lasso select)"""
        if indices:
            self.state.select_rows(indices)

    def _on_x_window_changed(self, min_val: float, max_val: float):
        """Handle X-axis sliding window range change"""
        if self._sliding_window_enabled and self._x_window_enabled:
            self.main_graph.setXRange(min_val, max_val, padding=0)

    def _on_y_window_changed(self, min_val: float, max_val: float):
        """Handle Y-axis sliding window range change"""
        if self._sliding_window_enabled and self._y_window_enabled:
            self.main_graph.setYRange(min_val, max_val, padding=0)

    def _on_graph_range_changed(self, vb, ranges):
        """Update sliding windows when graph range changes"""
        if not self._sliding_window_enabled:
            return

        x_range, y_range = ranges
        if self._x_window_enabled:
            self.x_sliding_window.set_window(x_range[0], x_range[1])
        if self._y_window_enabled:
            self.y_sliding_window.set_window(y_range[0], y_range[1])

    def set_sliding_window_enabled(self, enabled: bool, x_enabled: bool = True, y_enabled: bool = True):
        """Enable or disable sliding window controls"""
        self._sliding_window_enabled = enabled
        self._x_window_enabled = x_enabled
        self._y_window_enabled = y_enabled

        self.x_sliding_window.setVisible(enabled and x_enabled)
        self.y_sliding_window.setVisible(enabled and y_enabled)

        if enabled:
            self._update_sliding_window_data()

    def _update_sliding_window_data(self):
        """Update sliding window data from current graph data"""
        if self.main_graph._data_x is not None:
            self.x_sliding_window.set_data(self.main_graph._data_x)
        if self.main_graph._data_y is not None:
            self.y_sliding_window.set_data(self.main_graph._data_y)

    def _on_group_changed(self):
        """그룹 변경 시 범례 업데이트"""
        if self.state.group_columns:
            groups = self._build_group_masks()
            if groups:
                self.options_panel.set_series(list(groups.keys()))
        else:
            # Single series
            if self.state.value_columns:
                self.options_panel.set_series([self.state.value_columns[0].name])
            else:
                self.options_panel.set_series(["Data"])
        self.refresh()

    def _aggregate_values(self, values: np.ndarray, agg: AggregationType) -> float:
        """Aggregate values using selected aggregation type"""
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
        """Refresh graph"""
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
            _lg.debug("[DEBUG-CRASH] graph_panel.refresh() skipped - already refreshing")
            return
        self._refreshing = True
        try:
            self._do_refresh()
        except Exception as e:
            _lg.error(f"graph_panel.refresh() error: {e}")
        finally:
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

        # Apply filter (Item 15) — work on a filtered view of the DataFrame
        working_df = self.engine.df
        if self._active_filter and working_df is not None:
            for f_col, f_vals in self._active_filter.items():
                if f_col in working_df.columns and f_vals:
                    # Cast filter values to match column dtype for robust comparison
                    try:
                        working_df = working_df.filter(pl.col(f_col).cast(pl.Utf8).is_in(f_vals))
                    except Exception:
                        pass
            if len(working_df) == 0:
                self.main_graph.clear_plot()
                return

        # X column (from state, set by X Zone)
        x_col = self.state.x_column
        x_categorical_labels = None
        x_is_categorical = False

        if not x_col:
            # In windowed mode, use visible rows for index to avoid length mismatch
            if self.engine.is_windowed and working_df is not None:
                x_data = np.arange(len(working_df))
            else:
                x_data = np.arange(len(working_df) if working_df is not None else self.engine.row_count)
            options['x_title'] = options.get('x_title') or 'Index'
        else:
            # Check if X column is categorical
            x_is_categorical = self.engine.is_column_categorical(x_col)

            if x_is_categorical:
                # Get unique values as labels
                x_categorical_labels = self.engine.get_unique_values(x_col, limit=500)
                # Map values to indices
                value_to_idx = {v: i for i, v in enumerate(x_categorical_labels)}
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
                        # Fallback: treat as categorical
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
                # If no numeric columns, try any column (might be categorical)
                if self.engine.columns:
                    y_col_name = self.engine.columns[0]
                else:
                    return

        # Check if Y column is categorical
        y_is_categorical = self.engine.is_column_categorical(y_col_name)

        if y_is_categorical:
            # Get unique values as labels
            y_categorical_labels = self.engine.get_unique_values(y_col_name, limit=500)
            # Map values to indices
            value_to_idx = {v: i for i, v in enumerate(y_categorical_labels)}
            y_raw = working_df[y_col_name].to_list()
            y_data = np.array([value_to_idx.get(v, 0) for v in y_raw], dtype=np.float64)
        else:
            y_data = working_df[y_col_name].to_numpy()

        # Apply Y formula if specified
        if y_formula and not y_is_categorical:
            y_data = self._apply_y_formula(y_data, y_formula, y_col_name)
            # Update title to show formula
            if y_formula:
                options['y_title'] = options.get('y_title') or f"{y_col_name} [{y_formula}]"
        else:
            options['y_title'] = options.get('y_title') or y_col_name

        # Groups (already built above for combo chart, but might be None if no group columns)
        # Re-build here if we didn't return early from combo chart path
        if groups is None and self.state.group_columns:
            groups = self._build_group_masks(working_df)

        # Total points for status display
        total_points = len(x_data)

        # Determine if we need OpenGL acceleration
        # Auto-enable OpenGL for large datasets (>50K points) or when showing all data
        OPENGL_THRESHOLD = 50000
        needs_opengl = total_points > OPENGL_THRESHOLD or (show_all_data and total_points > max_points)
        self.main_graph.enable_opengl(needs_opengl)

        # Sampling logic - skip for categorical data or small datasets
        is_sampled = False
        algorithm_used = ""

        # Helper function to apply sampling algorithm
        def _apply_sampling(x_arr, y_arr, n_points, algo):
            """Apply sampling algorithm to data arrays"""
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

        # Don't sample categorical data
        if x_is_categorical or y_is_categorical:
            x_sampled, y_sampled = x_data, y_data
        elif show_all_data:
            # Show all data - no sampling
            x_sampled, y_sampled = x_data, y_data
        elif total_points > max_points:
            # Apply sampling
            try:
                valid_mask = ~(np.isnan(x_data.astype(float)) | np.isnan(y_data.astype(float)))
                x_valid = x_data[valid_mask].astype(np.float64)
                y_valid = y_data[valid_mask].astype(np.float64)

                if len(x_valid) > max_points:
                    is_sampled = True

                    # Group-aware sampling: sample each group separately to preserve group structure
                    if groups is not None and len(groups) > 0:
                        # Calculate points per group (proportional to group size)
                        group_sizes = {name: np.sum(mask[valid_mask]) for name, mask in groups.items()}
                        total_valid = sum(group_sizes.values())
                        
                        # Ensure minimum points per group (at least 10 or 1% of max_points)
                        min_points_per_group = max(10, max_points // 100)
                        
                        x_sampled_list = []
                        y_sampled_list = []
                        new_groups = {}
                        current_offset = 0
                        
                        for group_name, mask in groups.items():
                            # Get valid data for this group
                            group_valid_mask = mask[valid_mask]
                            x_group = x_valid[group_valid_mask]
                            y_group = y_valid[group_valid_mask]
                            
                            if len(x_group) == 0:
                                continue
                            
                            # Calculate proportional points for this group
                            group_ratio = len(x_group) / total_valid if total_valid > 0 else 0
                            group_points = max(min_points_per_group, int(max_points * group_ratio))
                            
                            # Apply sampling if group has more points than allocated
                            if len(x_group) > group_points:
                                x_group_sampled, y_group_sampled = _apply_sampling(
                                    x_group, y_group, group_points, sampling_algorithm
                                )
                            else:
                                x_group_sampled, y_group_sampled = x_group, y_group
                            
                            # Create new group mask for sampled data
                            group_len = len(x_group_sampled)
                            new_mask = np.zeros(0, dtype=bool)  # Will be resized later
                            
                            x_sampled_list.append(x_group_sampled)
                            y_sampled_list.append(y_group_sampled)
                            new_groups[group_name] = (current_offset, group_len)
                            current_offset += group_len
                        
                        # Concatenate all sampled data
                        if x_sampled_list:
                            x_sampled = np.concatenate(x_sampled_list)
                            y_sampled = np.concatenate(y_sampled_list)
                            
                            # Build new group masks for concatenated data
                            total_sampled = len(x_sampled)
                            groups = {}
                            for group_name, (offset, length) in new_groups.items():
                                mask = np.zeros(total_sampled, dtype=bool)
                                mask[offset:offset + length] = True
                                groups[group_name] = mask
                        else:
                            x_sampled, y_sampled = x_valid, y_valid
                    else:
                        # No groups - sample entire dataset
                        if sampling_algorithm == 'auto':
                            x_sampled, y_sampled = DataSampler.auto_sample(
                                x_valid, y_valid, max_points=max_points
                            )
                            # Determine which algorithm was used
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
                    
                    # Set algorithm used for display
                    if not algorithm_used:
                        if sampling_algorithm == 'auto':
                            is_sorted = np.all(x_valid[:-1] <= x_valid[1:])
                            algorithm_used = "LTTB" if is_sorted else "Min-Max"
                        else:
                            algorithm_used = sampling_algorithm.upper()
                else:
                    x_sampled, y_sampled = x_valid, y_valid
            except (ValueError, TypeError):
                # Fallback if sampling fails
                x_sampled, y_sampled = x_data, y_data
        else:
            x_sampled, y_sampled = x_data, y_data

        # Plot data with categorical labels
        self.main_graph.plot_data(
            x_sampled, y_sampled,
            groups=groups,
            chart_type=options.get('chart_type', ChartType.LINE),
            options=options,
            legend_settings=legend_settings,
            x_categorical_labels=x_categorical_labels,
            y_categorical_labels=y_categorical_labels
        )

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
            for col in hover_columns:
                if col in working_df.columns:
                    col_data = working_df[col].to_list()
                    # Apply same sampling if needed
                    if len(col_data) > max_points and len(x_sampled) < len(col_data):
                        # Simple downsampling for hover data
                        step = len(col_data) // len(x_sampled)
                        col_data = col_data[::step][:len(x_sampled)]
                    hover_data[col] = col_data
            self.main_graph.set_hover_data(hover_columns, hover_data)
        else:
            self.main_graph.set_hover_data([], {})

        # Update stats - compute group aggregation for pie chart
        group_data = None
        if groups is not None and len(groups) > 0:
            # Calculate aggregated Y values for each group for pie chart
            try:
                group_data = {}
                agg_type = AggregationType.SUM
                if self.state.value_columns:
                    agg_type = self.state.value_columns[0].aggregation
                for group_name, mask in groups.items():
                    group_y = y_sampled[mask]
                    val = self._aggregate_values(group_y, agg_type)
                    group_data[group_name] = abs(val) if val else 0.0
                # Discard if all zeros
                if all(v == 0.0 for v in group_data.values()):
                    group_data = None
            except Exception:
                group_data = None

        self.stat_panel.update_histograms(x_sampled, y_sampled, group_data)
        if self.state.value_columns:
            stats = self.engine.get_statistics(self.state.value_columns[0].name)

            # X-Diff and Y-Diff (Max - Min) for full data
            try:
                clean_x = x_sampled[~np.isnan(x_sampled)]
                clean_y = y_sampled[~np.isnan(y_sampled)]
                if len(clean_x) > 0:
                    stats['X-Diff'] = float(np.max(clean_x) - np.min(clean_x))
                if len(clean_y) > 0:
                    stats['Y-Diff'] = float(np.max(clean_y) - np.min(clean_y))
            except Exception:
                pass

            # Percentiles for summary
            percentiles = {}
            try:
                clean_y = y_sampled[~np.isnan(y_sampled)]
                if len(clean_y) > 0:
                    pct_list = [0, 1, 2, 3, 4, 5, 10, 25, 50, 75, 90, 95, 97, 99, 99.7, 99.9, 99.99, 100]
                    pct_vals = np.percentile(clean_y, pct_list)
                    percentiles = {f"P{p}": float(v) for p, v in zip(pct_list, pct_vals)}
            except Exception:
                percentiles = {}

            # Groupby counts & sums
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
        # Use original data for navigation, not sampled data
        sliding_window_enabled = options.get('sliding_window_enabled', False)
        x_window_enabled = options.get('x_sliding_window', True)
        y_window_enabled = options.get('y_sliding_window', True)

        self._sliding_window_enabled = sliding_window_enabled
        self._x_window_enabled = x_window_enabled
        self._y_window_enabled = y_window_enabled

        self.x_sliding_window.setVisible(sliding_window_enabled and x_window_enabled)
        self.y_sliding_window.setVisible(sliding_window_enabled and y_window_enabled)

        if sliding_window_enabled:
            # Use plotted data (sampled) to keep distribution aligned with visible points
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
        """Apply formula transformation to Y data

        Args:
            y_data: Original Y data as numpy array
            formula: Formula string (e.g., "y*2", "LOG(y)", "y+100")
            col_name: Original column name

        Returns:
            Transformed Y data
        """
        if not formula or not formula.strip():
            return y_data

        try:
            # Create expression engine
            expr_engine = ExpressionEngine()

            # Replace 'y' in formula with column reference
            # Support both 'y' and 'Y' as references
            adjusted_formula = formula.replace('Y', col_name).replace('y', col_name)

            # Create a temporary DataFrame with the Y data
            temp_df = pl.DataFrame({col_name: y_data.tolist()})

            # Evaluate formula
            result_series = expr_engine.evaluate(adjusted_formula, temp_df)

            # Convert back to numpy array
            return result_series.to_numpy()

        except ExpressionError as e:
            print(f"Formula error: {e}")
            return y_data
        except Exception as e:
            print(f"Error applying formula '{formula}': {e}")
            return y_data

    # ==================== Combo Chart (Item 14) ====================

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

    def _refresh_combo_chart(self, working_df, x_data, x_col, x_categorical_labels,
                              x_is_categorical, options, legend_settings, groups=None):
        """Render combo chart with dual Y axes for multiple value columns.
        
        When groups is provided, renders each group as a separate series with distinct colors.
        """
        self.main_graph.clear_plot()

        if working_df is None:
            return

        value_cols = self.state.value_columns
        chart_type = options.get('chart_type', ChartType.LINE)
        bg_color = options.get('bg_color', QColor('#323D4A'))
        self.main_graph.setBackground(bg_color.name())
        line_width = options.get('line_width', 2)

        default_colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        ]

        # Apply axis options
        self.main_graph.setLabel('bottom', options.get('x_title') or x_col or 'Index',
                                 **{'font-size': '14px', 'color': '#E2E8F0'})
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
                    self._render_combo_series(x_data, y_data_full, col_chart_type, color, pen, label,
                                              line_width, marker_size, marker_border,
                                              self.main_graph, options)

        # Update series names for legend
        series_names = [vc.name for vc in value_cols if vc.name in working_df.columns]
        self.options_panel.set_series(series_names)

        # Stats for first Y column
        if value_cols and value_cols[0].name in working_df.columns:
            y_first = working_df[value_cols[0].name].to_numpy()
            self.stat_panel.update_histograms(x_data, y_first)
            stats = self.engine.get_statistics(value_cols[0].name)
            self.stat_panel.update_stats(stats)

    def _refresh_statistical_chart(self, chart_type: ChartType, options: Dict, legend_settings: Dict):
        """Render Box Plot, Violin Plot, or Heatmap using specialised chart classes."""
        self.main_graph.clear_plot()
        # Clear any leftover title/axis labels from previous chart types
        self.main_graph.setTitle("")

        df = self.engine.df
        if df is None:
            return

        # Apply filter (Item 15)
        if self._active_filter:
            for f_col, f_vals in self._active_filter.items():
                if f_col in df.columns and f_vals:
                    try:
                        df = df.filter(pl.col(f_col).cast(pl.Utf8).is_in(f_vals))
                    except Exception:
                        pass
            if len(df) == 0:
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

        default_colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        ]

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
        from ...graph.charts.box_plot import BoxPlotChart

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
            med_line = pg.PlotCurveItem(
                [i - 0.3, i + 0.3], [s['median'], s['median']],
                pen=pg.mkPen('#ffffff', width=3),
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
            from ...graph.charts.violin_plot import ViolinPlotChart
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

        from ...graph.charts.heatmap import HeatmapChart
        chart = HeatmapChart()

        try:
            agg_str = 'sum'
            if self.state.value_columns:
                agg_str = self.state.value_columns[0].aggregation.value
            matrix, row_labels, col_labels = chart.create_matrix(df, row_col, col_col, y_col, agg=agg_str)
        except Exception as e:
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

    def _refresh_overlay_comparison(self):
        """
        Overlay comparison mode - render multiple datasets on the same chart.

        각 데이터셋을 고유한 색상으로 같은 차트에 오버레이하여 표시
        """
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

    def _on_chart_settings_changed(self):
        """Sync chart type from state to options panel and refresh"""
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
        """Handle selection state change - highlight selected points and update stats"""
        selected_rows = list(self.state.selection.selected_rows)
        
        # Update graph highlight
        self.main_graph.highlight_selection(selected_rows)
        
        # Update stat panel with selected data statistics
        if selected_rows and self.engine.is_loaded:
            self._update_stats_for_selection(selected_rows)
        else:
            # Show stats for all data
            if self.state.value_columns and self.engine.is_loaded:
                stats = self.engine.get_statistics(self.state.value_columns[0].name)
                self.stat_panel.update_stats(stats)

    def _update_stats_for_selection(self, selected_rows: list):
        """Update stat panel with statistics for selected rows only"""
        if not self.engine.is_loaded or not selected_rows:
            return
        
        try:
            # Get selected data
            df = self.engine.df
            if df is None:
                return
            
            # Filter to selected rows
            selected_indices = [i for i in selected_rows if 0 <= i < len(df)]
            if not selected_indices:
                return
            
            # Get Y column name - try value_columns first, then any numeric column
            y_col_name = None
            if self.state.value_columns:
                y_col_name = self.state.value_columns[0].name
            
            if not y_col_name or y_col_name not in df.columns:
                # Find first numeric column
                for col in self.engine.columns:
                    dtype = self.engine.dtypes.get(col, '')
                    if dtype.startswith(('Int', 'Float', 'UInt')):
                        y_col_name = col
                        break
            
            if not y_col_name or y_col_name not in df.columns:
                # Still no column found - show basic stats
                stats = {
                    'Selected': len(selected_rows),
                    'Total': len(df),
                }
                self.stat_panel.update_stats(stats)
                return
            
            # Get selected data for Y column
            y_data = df[y_col_name].to_numpy()
            selected_y = y_data[selected_indices]
            
            # Get X data
            x_col = self.state.x_column
            if x_col and x_col in df.columns:
                x_data_full = df[x_col].to_numpy()
                selected_x = x_data_full[selected_indices]
            else:
                selected_x = np.array(selected_indices, dtype=float)
            
            # Calculate statistics for selection
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
            
            # X-Diff and Y-Diff for selection
            if len(clean_x) > 0:
                stats['X-Diff'] = float(np.max(clean_x) - np.min(clean_x))
            if len(clean_y) > 0:
                stats['Y-Diff'] = float(np.max(clean_y) - np.min(clean_y))
            
            self.stat_panel.update_stats(stats)
            
            # Update histograms with selected data
            self.stat_panel.update_histograms(selected_x, selected_y)
            
        except Exception as e:
            print(f"Error updating stats for selection: {e}")
    
    def _build_group_masks(self, df_override=None) -> Dict[str, np.ndarray]:
        if not self.state.group_columns or not self.engine.is_loaded:
            return None
        
        df = df_override if df_override is not None else self.engine.df
        n_rows = len(df)
        group_cols = [g.name for g in self.state.group_columns]
        groups = {}
        
        if len(group_cols) == 1:
            col = group_cols[0]
            unique_values = df[col].unique().sort().to_list()
            
            for val in unique_values:
                group_name = str(val) if val is not None else "(Empty)"
                if val is None:
                    mask = df[col].is_null().to_numpy().astype(bool)
                else:
                    mask = (df[col] == val).to_numpy().astype(bool)
                groups[group_name] = mask
        else:
            combined = df.select(group_cols)
            unique_combos = combined.unique().sort(group_cols)
            
            for row in unique_combos.iter_rows():
                parts = [str(v) if v is not None else "(Empty)" for v in row]
                group_name = " / ".join(parts)
                
                mask = np.ones(n_rows, dtype=bool)
                for col, val in zip(group_cols, row):
                    if val is None:
                        mask &= df[col].is_null().to_numpy().astype(bool)
                    else:
                        mask &= (df[col] == val).to_numpy().astype(bool)
                
                groups[group_name] = mask
        
        return groups
    
    def reset_view(self):
        self.main_graph.reset_view()
    
    def autofit(self):
        """Auto-fit view with margin based on current data"""
        try:
            x = getattr(self.main_graph, "_data_x", None)
            y = getattr(self.main_graph, "_data_y", None)
            if x is None or y is None or len(x) == 0 or len(y) == 0:
                self.main_graph.autoRange()
                return

            # Convert and filter finite values
            x_arr = np.asarray(x, dtype=float)
            y_arr = np.asarray(y, dtype=float)
            finite = np.isfinite(x_arr) & np.isfinite(y_arr)
            if not np.any(finite):
                self.main_graph.autoRange()
                return

            x_min, x_max = np.min(x_arr[finite]), np.max(x_arr[finite])
            y_min, y_max = np.min(y_arr[finite]), np.max(y_arr[finite])

            # Margin: 5% of range (min 1.0)
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
        """컬럼 목록 설정 (범례 초기화용)"""
        # Initialize legend with first numeric column
        numeric_cols = [
            col for col in columns
            if self.engine.dtypes.get(col, '').startswith(('Int', 'Float'))
        ]
        if numeric_cols:
            self.options_panel.set_series([numeric_cols[0]])

    def get_chart_options(self) -> Dict[str, Any]:
        """Get current chart options from the options panel"""
        return self.options_panel.get_chart_options()

    def get_legend_settings(self) -> Dict[str, Any]:
        """Get current legend settings from the options panel"""
        return self.options_panel.get_legend_settings()

    def apply_options(self, options: Dict[str, Any]):
        """Apply chart options to the options panel"""
        if not options:
            return

        # Apply chart title
        if 'title' in options and options['title']:
            self.options_panel.chart_title_edit.setText(options['title'])
        if 'subtitle' in options and options['subtitle']:
            self.options_panel.chart_subtitle_edit.setText(options['subtitle'])

        # Apply X-axis options
        if 'x_title' in options and options['x_title']:
            self.options_panel.x_title_edit.setText(options['x_title'])
        if 'x_format' in options:
            x_format = options['x_format']
            if x_format:
                # Find matching preset or set custom
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
                self.options_panel.x_format_combo.setCurrentIndex(0)  # Auto

        if 'x_log' in options:
            self.options_panel.x_log_check.setChecked(options['x_log'])
        if 'x_reverse' in options:
            self.options_panel.x_reverse_check.setChecked(options['x_reverse'])

        # Apply Y-axis options
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
                self.options_panel.y_format_combo.setCurrentIndex(0)  # Auto

        if 'y_min' in options and options['y_min'] is not None:
            self.options_panel.y_min_spin.setValue(options['y_min'])
        if 'y_max' in options and options['y_max'] is not None:
            self.options_panel.y_max_spin.setValue(options['y_max'])
        if 'y_log' in options:
            self.options_panel.y_log_check.setChecked(options['y_log'])
        if 'y_reverse' in options:
            self.options_panel.y_reverse_check.setChecked(options['y_reverse'])

        # Apply grid options
        if 'grid_x' in options:
            self.options_panel.grid_x_check.setChecked(options['grid_x'])
        if 'grid_y' in options:
            self.options_panel.grid_y_check.setChecked(options['grid_y'])
        if 'grid_opacity' in options:
            self.options_panel.grid_opacity_slider.setValue(int(options['grid_opacity'] * 100))

        # Apply style options
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

        # Apply background color
        if 'bg_color' in options and options['bg_color']:
            from PySide6.QtGui import QColor
            if isinstance(options['bg_color'], str):
                self.options_panel.bg_color_btn.set_color(QColor(options['bg_color']))

        # Apply sampling options
        if 'show_all_data' in options:
            self.options_panel.show_all_data_check.setChecked(options['show_all_data'])
        if 'max_points' in options:
            self.options_panel.max_points_slider.setValue(options['max_points'] // 1000)

        # Apply sliding window options
        if 'sliding_window_enabled' in options:
            self.options_panel.sliding_window_check.setChecked(options['sliding_window_enabled'])
        if 'x_sliding_window' in options:
            self.options_panel.x_sliding_window_check.setChecked(options['x_sliding_window'])
        if 'y_sliding_window' in options:
            self.options_panel.y_sliding_window_check.setChecked(options['y_sliding_window'])

    # ==================== Drawing Methods ====================

    def get_drawing_manager(self) -> DrawingManager:
        """Get the drawing manager"""
        return self._drawing_manager

    def set_drawing_style(self, style: DrawingStyle):
        """Set the current drawing style for new drawings"""
        self._drawing_manager.current_style = style
        self.main_graph.set_drawing_style(style)

    def set_drawing_color(self, color_hex: str):
        """Set the stroke color for new drawings"""
        self._drawing_manager.current_style.stroke_color = color_hex
        self.main_graph._current_drawing_style.stroke_color = color_hex

    def get_drawings_data(self) -> Dict[str, Any]:
        """Get all drawings as serializable dict (for saving)"""
        return self._drawing_manager.to_dict()

    def load_drawings_data(self, data: Dict[str, Any]):
        """Load drawings from serialized dict"""
        self._drawing_manager.from_dict(data)

    def clear_drawings(self):
        """Clear all drawings"""
        self._drawing_manager.clear()

    def undo_drawing(self) -> bool:
        """Undo last drawing action"""
        return self._drawing_manager.undo()

    def redo_drawing(self) -> bool:
        """Redo last undone action"""
        return self._drawing_manager.redo()

    def delete_selected_drawing(self) -> bool:
        """Delete the currently selected drawing"""
        return self._drawing_manager.delete_selected()

    def show_drawing_style_dialog(self):
        """Show dialog to configure drawing style"""
        dialog = DrawingStyleDialog("Drawing Style", self)
        dialog.set_style(self._drawing_manager.current_style)
        if dialog.exec() == QDialog.Accepted:
            style = dialog.get_style()
            self.set_drawing_style(style)

    # ==================== Grid View (Facet Grid) ====================

    def _refresh_grid_view(self, options: Dict[str, Any], legend_settings: Dict[str, Any]):
        """Render Grid View with multiple faceted charts"""
        from ...core.state import GridDirection

        # Hide main graph, show grid container
        self.main_graph.setVisible(False)
        self._grid_container.setVisible(True)

        split_by = options.get('split_by')
        direction = options.get('direction', GridDirection.WRAP)
        max_columns = options.get('max_columns', 4)

        # Get the working DataFrame (with filters applied)
        working_df = self.engine.df
        if self._active_filter and working_df is not None:
            for f_col, f_vals in self._active_filter.items():
                if f_col in working_df.columns and f_vals:
                    try:
                        working_df = working_df.filter(pl.col(f_col).cast(pl.Utf8).is_in(f_vals))
                    except Exception:
                        pass

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
            n_rows = 1
        elif direction == GridDirection.COLUMN:
            n_cols = 1
            n_rows = n_facets
        else:  # WRAP
            n_cols = min(max_columns, n_facets)
            n_rows = (n_facets + n_cols - 1) // n_cols

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
        default_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

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

            # Plot data
            color = default_colors[idx % len(default_colors)]
            pen = pg.mkPen(color=color, width=line_width)

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

            cell_layout.addWidget(plot_widget, 1)
            self._grid_layout.addWidget(cell_widget, row, col)
            self._grid_cells.append(plot_widget)
            all_cells.append(plot_widget)

        # Synchronize axes across all cells
        if len(all_cells) > 1 and len(all_x_data) > 0 and len(all_y_data) > 0:
            self._sync_grid_axes(all_cells, all_x_data, all_y_data)

    def _clear_grid_cells(self):
        """Clear all grid cells"""
        # Remove widgets from layout
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._grid_cells.clear()
        self._grid_cell_labels.clear()

    def _sync_grid_axes(self, cells: List[pg.PlotWidget], all_x: List, all_y: List):
        """Synchronize axis ranges across all grid cells"""
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
            import logging
            logging.getLogger(__name__).warning(f"Failed to sync grid axes: {e}")
