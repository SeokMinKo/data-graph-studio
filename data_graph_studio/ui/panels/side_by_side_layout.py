"""
Side-by-Side Layout - 병렬 비교 레이아웃

여러 데이터셋을 독립된 패널에 병렬로 표시
스크롤/줌 동기화 지원 (ViewSyncManager 사용)
"""

from typing import Optional, List, Dict, TYPE_CHECKING
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSplitter, QCheckBox,
    QPushButton
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor

from ...core.data_engine import DataEngine
from ...core.state import AppState
from ...core.view_sync import ViewSyncManager

if TYPE_CHECKING:
    from ...core.profile import GraphSetting


class MiniGraphWidget(QWidget):
    """미니 그래프 위젯 (병렬 비교용)

    Supports two modes:
      1. Dataset mode (graph_setting=None) — uses AppState for columns/chart type.
      2. Profile mode (graph_setting provided) — uses GraphSetting for columns/chart type.

    Duck-typing interface for ViewSyncManager:
      - set_view_range(x_range, y_range, sync_x, sync_y)
      - set_selection(indices)
    """

    activated = Signal(str)  # dataset_id
    view_range_changed = Signal(str, list, list)  # dataset_id, x_range, y_range
    selection_changed = Signal(str, list)  # dataset_id, [x_min, x_max]
    row_selection_changed = Signal(str, list)  # dataset_id, row_indices

    def __init__(
        self,
        dataset_id: str,
        engine: DataEngine,
        state: AppState,
        graph_setting: 'Optional[GraphSetting]' = None,
        parent=None,
    ):
        super().__init__(parent)
        self.dataset_id = dataset_id
        self.engine = engine
        self.state = state
        self.graph_setting = graph_setting
        self.plot_widget = None
        self._is_syncing = False  # 동기화 중인지 추적 (무한 루프 방지)
        self._selected_indices: list = []
        self._selection_region = None  # LinearRegionItem for drag selection
        self._is_selection_syncing = False  # selection sync guard

        # Stored plot data for selection matching
        self._plot_x_data = None  # np.ndarray
        self._plot_y_data = None  # np.ndarray

        # Highlight scatter for selection sync
        self._highlight_scatter = None

        # Rect selection state
        self._rect_selecting = False
        self._rect_start = None  # (x, y) in view coords
        self._rect_roi = None    # QGraphicsRectItem for visual feedback
        self._current_tool_mode = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # Effective columns (profile vs state)
    # ------------------------------------------------------------------

    @property
    def effective_x_column(self) -> Optional[str]:
        """X column: from graph_setting if present, else from state."""
        if self.graph_setting is not None:
            return self.graph_setting.x_column
        return self.state.x_column

    @property
    def effective_value_columns(self) -> list:
        """Value columns: from graph_setting (tuple of dicts) or state (list of ValueColumn).

        When graph_setting is provided, returns list(graph_setting.value_columns).
        When not, returns state.value_columns (list of ValueColumn dataclass instances).
        """
        if self.graph_setting is not None:
            return list(self.graph_setting.value_columns)
        return list(self.state.value_columns)

    @property
    def effective_chart_type(self) -> str:
        """Chart type string."""
        if self.graph_setting is not None:
            return self.graph_setting.chart_type or "line"
        try:
            return self.state.chart_settings.chart_type.value
        except Exception:
            return "line"

    @property
    def effective_chart_settings(self) -> dict:
        """Chart style settings (line_width, marker_size, opacity, etc.)."""
        if self.graph_setting is not None:
            return dict(self.graph_setting.chart_settings) if self.graph_setting.chart_settings else {}
        try:
            cs = self.state._chart_settings
            result = {}
            for attr in ['show_legend', 'show_grid', 'show_markers', 'line_width',
                         'marker_size', 'opacity', 'color_palette']:
                if hasattr(cs, attr):
                    result[attr] = getattr(cs, attr)
            return result
        except Exception:
            return {}

    @property
    def effective_group_columns(self) -> list:
        """Group columns: from graph_setting if present, else from state."""
        if self.graph_setting is not None:
            return list(self.graph_setting.group_columns)
        return [gc.name for gc in self.state.group_columns] if self.state.group_columns else []

    @property
    def effective_hover_columns(self) -> list:
        """Hover columns: from graph_setting if present, else from state."""
        if self.graph_setting is not None:
            return list(self.graph_setting.hover_columns)
        return list(self.state.hover_columns) if hasattr(self.state, 'hover_columns') else []

    @property
    def _header_name(self) -> str:
        """Display name for the header."""
        if self.graph_setting is not None:
            return self.graph_setting.name
        metadata = self.state.get_dataset_metadata(self.dataset_id)
        return metadata.name if metadata else self.dataset_id

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 헤더 — always use dataset color for background
        metadata = self.state.get_dataset_metadata(self.dataset_id)
        color = metadata.color if metadata else '#1f77b4'

        header = QFrame()
        header.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
        header.setFixedHeight(30)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        name_label = QLabel(self._header_name)
        name_label.setStyleSheet("color: white; font-weight: bold;")
        header_layout.addWidget(name_label)

        # 행 수
        dataset = self.engine.get_dataset(self.dataset_id)
        row_count = dataset.row_count if dataset else 0
        rows_label = QLabel(f"{row_count:,} rows")
        rows_label.setStyleSheet("color: rgba(255,255,255,0.8);")
        header_layout.addWidget(rows_label)

        layout.addWidget(header)

        # 그래프 플레이스홀더
        try:
            import pyqtgraph as pg

            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground(self._resolve_bg_color())
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setMinimumHeight(150)
            layout.addWidget(self.plot_widget, 1)

            # ViewBox 범위 변경 시그널 연결
            self.plot_widget.getViewBox().sigRangeChanged.connect(self._on_view_range_changed)

            # Selection region (LinearRegionItem) — hidden by default
            self._selection_region = pg.LinearRegionItem(
                values=(0, 1),
                brush=pg.mkBrush(41, 128, 185, 50),  # semi-transparent blue
                pen=pg.mkPen('#2980b9', width=1),
                movable=True,
            )
            self._selection_region.setZValue(10)
            self._selection_region.hide()
            self.plot_widget.addItem(self._selection_region)
            self._selection_region.sigRegionChangeFinished.connect(
                self._on_selection_region_changed
            )

            # Enable right-click drag to create selection region
            self.plot_widget.scene().sigMouseClicked.connect(self._on_plot_mouse_clicked)

            # 간단한 데이터 플롯
            self._plot_data(color)
        except ImportError:
            # PyQtGraph 없으면 플레이스홀더
            placeholder = QLabel("Graph")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setObjectName("graphPlaceholder")
            placeholder.setMinimumHeight(150)
            layout.addWidget(placeholder, 1)

        # 통계 요약
        stats_frame = QFrame()
        stats_frame.setObjectName("statsFrame")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(8, 4, 8, 4)

        if dataset and dataset.df is not None:
            # Use effective_value_columns for stats (not just first numeric col)
            eff_cols = self.effective_value_columns
            stat_col_names = []
            for vc in eff_cols:
                if hasattr(vc, 'name'):
                    stat_col_names.append(vc.name)
                elif isinstance(vc, dict):
                    stat_col_names.append(vc.get('name', ''))

            # Fallback to first numeric column
            if not stat_col_names:
                numeric_cols = self.engine.get_numeric_columns(self.dataset_id)
                if numeric_cols:
                    stat_col_names = [numeric_cols[0]]

            for col in stat_col_names:
                if col and col in dataset.df.columns:
                    try:
                        series = dataset.df[col]
                        label_prefix = f"{col}: " if len(stat_col_names) > 1 else ""
                        stats_layout.addWidget(QLabel(f"{label_prefix}Mean: {series.mean():.2f}"))
                        stats_layout.addWidget(QLabel(f"Min: {series.min():.2f}"))
                        stats_layout.addWidget(QLabel(f"Max: {series.max():.2f}"))
                    except Exception:
                        pass

        stats_layout.addStretch()
        layout.addWidget(stats_frame)

    # Color palette for multi-series / group-by rendering
    COLOR_PALETTE = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
        '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5',
        '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5',
    ]

    def _plot_data(self, color: str):
        """Plot data respecting effective chart type, value columns, group-by, and style.

        Supports: line, scatter, bar chart types.
        Renders all value columns (not just the first).
        Supports group_by with per-group coloring.
        Applies chart_settings (grid, legend, line_width, etc.) from profile.
        """
        import numpy as np

        dataset = self.engine.get_dataset(self.dataset_id)
        if not dataset or dataset.df is None:
            return

        df = dataset.df
        x_col = self.effective_x_column
        chart_type = self.effective_chart_type
        value_cols = self.effective_value_columns
        group_cols = self.effective_group_columns
        # Store hover columns for future tooltip support
        self._hover_columns = self.effective_hover_columns

        # Apply chart style settings (grid, legend) to plot widget
        cs = self.effective_chart_settings
        if self.plot_widget is not None:
            show_grid = cs.get('show_grid', True)
            self.plot_widget.showGrid(x=show_grid, y=show_grid, alpha=0.3)
            show_legend = cs.get('show_legend', False)
            if show_legend:
                self.plot_widget.addLegend()

        # --- Resolve X data ---
        if x_col and x_col in df.columns:
            try:
                x_data_full = df[x_col].to_numpy()
            except Exception:
                x_data_full = np.arange(len(df))
        else:
            x_data_full = np.arange(len(df))

        # Store for selection matching
        self._plot_x_data = x_data_full

        # --- Resolve Y column names ---
        y_col_names: list = []
        y_col_colors: dict = {}
        if value_cols:
            for vc in value_cols:
                if hasattr(vc, 'name'):
                    name = vc.name
                    vc_color = getattr(vc, 'color', None)
                elif isinstance(vc, dict):
                    name = vc.get('name', '')
                    vc_color = vc.get('color', None)
                else:
                    continue
                if name and name in df.columns:
                    y_col_names.append(name)
                    if vc_color:
                        y_col_colors[name] = vc_color

        # Fallback: use first numeric column
        if not y_col_names:
            numeric_cols = self.engine.get_numeric_columns(self.dataset_id)
            if numeric_cols:
                y_col_names = [numeric_cols[0]]

        if not y_col_names:
            return

        # Store all Y column data for multi-column selection matching
        self._plot_y_data_dict = {}
        for yc in y_col_names:
            try:
                self._plot_y_data_dict[yc] = df[yc].to_numpy()
            except Exception:
                pass
        # Backward compat: _plot_y_data = first Y column
        try:
            self._plot_y_data = df[y_col_names[0]].to_numpy()
        except Exception:
            self._plot_y_data = None

        try:
            import pyqtgraph as pg
        except ImportError:
            return

        # --- Group-by rendering ---
        if group_cols:
            # Use first group column for coloring
            grp_col = group_cols[0] if isinstance(group_cols[0], str) else group_cols[0].get('name', '')
            if grp_col and grp_col in df.columns:
                self._plot_grouped(df, x_data_full, x_col, y_col_names, grp_col, chart_type, pg, np)
                return

        # --- Multi-column rendering (no group-by) ---
        color_idx = 0
        for y_col in y_col_names:
            try:
                y_data = df[y_col].to_numpy()
            except Exception:
                continue

            pen_color = y_col_colors.get(y_col) or self.COLOR_PALETTE[color_idx % len(self.COLOR_PALETTE)]
            x_sampled, y_sampled = self._sample(x_data_full, y_data, np)
            self._render_series(x_sampled, y_sampled, pen_color, chart_type, pg, np, name=y_col)
            color_idx += 1

    def _plot_grouped(self, df, x_data_full, x_col, y_col_names, grp_col, chart_type, pg, np):
        """Render grouped data with per-group colors."""
        try:
            groups = df[grp_col].unique()
        except Exception:
            return

        color_idx = 0
        for group_val in groups:
            if group_val is None:
                mask = df[grp_col].is_null().to_numpy().astype(bool)
            else:
                mask = (df[grp_col] == group_val).to_numpy().astype(bool)
            indices = np.where(mask)[0]

            if len(indices) == 0:
                continue

            x_grp = x_data_full[indices]
            grp_color = self.COLOR_PALETTE[color_idx % len(self.COLOR_PALETTE)]

            for y_col in y_col_names:
                try:
                    y_grp = df[y_col].to_numpy()[indices]
                except Exception:
                    continue

                x_sampled, y_sampled = self._sample(x_grp, y_grp, np)
                label = f"{group_val}" if len(y_col_names) == 1 else f"{group_val}/{y_col}"
                self._render_series(x_sampled, y_sampled, grp_color, chart_type, pg, np, name=label)

            color_idx += 1

    def _get_style(self) -> dict:
        """Safely extract numeric style values from chart_settings."""
        try:
            cs = self.effective_chart_settings
        except Exception:
            cs = {}
        def _num(key, default):
            v = cs.get(key, default)
            return v if isinstance(v, (int, float)) else default
        def _bool(key, default):
            v = cs.get(key, default)
            return bool(v) if isinstance(v, (bool, int)) else default
        return {
            'line_width': _num('line_width', 2),
            'marker_size': _num('marker_size', 5),
            'opacity': _num('opacity', 1.0),
            'show_markers': _bool('show_markers', False),
        }

    def _render_series(self, x_data, y_data, color, chart_type, pg, np, name: str = ""):
        """Render a single data series based on chart_type and chart_settings."""
        style = self._get_style()
        line_width = style['line_width']
        marker_size = style['marker_size']
        opacity = style['opacity']
        show_markers = style['show_markers']

        try:
            # Apply opacity to color
            pen_color = pg.mkColor(color)
            brush_color = pg.mkColor(color)
            if opacity < 1.0:
                try:
                    pen_color.setAlphaF(opacity)
                    brush_color.setAlphaF(opacity)
                except Exception:
                    pass

            if chart_type == "scatter":
                scatter = pg.ScatterPlotItem(
                    x=x_data.astype(float),
                    y=y_data.astype(float),
                    pen=pg.mkPen(None),
                    brush=pg.mkBrush(brush_color),
                    size=marker_size,
                    name=name,
                )
                self.plot_widget.addItem(scatter)
            elif chart_type == "bar":
                bar = pg.BarGraphItem(
                    x=x_data.astype(float),
                    height=y_data.astype(float),
                    width=0.6,
                    brush=pg.mkBrush(brush_color),
                    name=name,
                )
                self.plot_widget.addItem(bar)
            else:
                # Default: line
                pen = pg.mkPen(pen_color, width=line_width)
                self.plot_widget.plot(
                    x_data, y_data,
                    pen=pen,
                    name=name,
                )
                # Add markers on top of line if show_markers is enabled
                if show_markers:
                    scatter = pg.ScatterPlotItem(
                        x=x_data.astype(float),
                        y=y_data.astype(float),
                        pen=pg.mkPen(None),
                        brush=pg.mkBrush(brush_color),
                        size=marker_size,
                    )
                    self.plot_widget.addItem(scatter)
        except Exception:
            pass

    def _sample(self, x_data, y_data, np, max_points: int = None):
        """Downsample arrays based on profile/state sampling settings."""
        cs = self.effective_chart_settings
        # If show_all_data is set, skip sampling entirely
        if cs.get('show_all_data', False):
            return x_data, y_data
        if max_points is None:
            max_points = cs.get('max_points', 10000)
        if len(x_data) > max_points:
            step = len(x_data) // max_points
            return x_data[::step], y_data[::step]
        return x_data, y_data

    # ------------------------------------------------------------------
    # Background color resolution
    # ------------------------------------------------------------------

    def _resolve_bg_color(self) -> str:
        """Resolve background color from graph_setting > chart_settings > theme default.

        Priority:
          1. graph_setting.chart_settings['bg_color']
          2. state.chart_settings.bg_color (if present)
          3. Theme-aware default: dark '#1E293B'
        """
        # 1. From profile's chart_settings
        if self.graph_setting is not None:
            cs = self.graph_setting.chart_settings
            if cs:
                bg = cs.get('bg_color') if isinstance(cs, dict) else getattr(cs, 'bg_color', None)
                if bg:
                    return bg if isinstance(bg, str) else bg.name() if hasattr(bg, 'name') else str(bg)

        # 2. From state chart_settings
        try:
            state_cs = self.state._chart_settings
            bg = getattr(state_cs, 'bg_color', None)
            if bg:
                return bg if isinstance(bg, str) else bg.name() if hasattr(bg, 'name') else str(bg)
        except Exception:
            pass

        # 3. Theme-aware default (dark theme)
        return '#1E293B'

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def autofit(self):
        """Auto-fit view to data range."""
        if self.plot_widget is not None:
            self.plot_widget.getViewBox().autoRange()

    def _remove_rect_roi(self, roi):
        """Remove a rect selection ROI from the plot."""
        try:
            if self.plot_widget is not None and roi is not None:
                self.plot_widget.removeItem(roi)
                if self._rect_roi is roi:
                    self._rect_roi = None
        except (RuntimeError, ValueError):
            pass

    def set_tool_mode(self, mode) -> None:
        """Apply tool mode from toolbar.

        Supported:
          RECT_SELECT / LASSO_SELECT → rect drag selection on the plot.
          ZOOM / PAN → normal pyqtgraph interaction.
          Draw modes → ignored (not supported in mini graph).
        """
        from ...core.state import ToolMode

        self._current_tool_mode = mode

        if self.plot_widget is None:
            return

        vb = self.plot_widget.getViewBox()

        # Clean up any in-progress rect selection
        self._rect_selecting = False
        self._rect_start = None
        if self._rect_roi is not None:
            self.plot_widget.removeItem(self._rect_roi)
            self._rect_roi = None

        if mode in (ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT):
            # Disable default pan/zoom so our mouse events work
            vb.setMouseEnabled(x=False, y=False)
            # Install event filter on the plot widget for mouse events
            self.plot_widget.viewport().installEventFilter(self)
        elif mode == ToolMode.PAN:
            vb.setMouseEnabled(x=True, y=True)
            vb.setMouseMode(vb.PanMode)
            self.plot_widget.viewport().removeEventFilter(self)
        elif mode == ToolMode.ZOOM:
            vb.setMouseEnabled(x=True, y=True)
            vb.setMouseMode(vb.RectMode)
            self.plot_widget.viewport().removeEventFilter(self)
        else:
            # Draw modes — not supported, just re-enable normal interaction
            vb.setMouseEnabled(x=True, y=True)
            self.plot_widget.viewport().removeEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle mouse events for rect selection in MiniGraphWidget."""
        from PySide6.QtCore import QEvent
        from ...core.state import ToolMode
        import pyqtgraph as pg

        if self.plot_widget is None or self._current_tool_mode not in (
            ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT
        ):
            return super().eventFilter(obj, event)

        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = self.plot_widget.getViewBox().mapSceneToView(
                self.plot_widget.mapToScene(event.position().toPoint())
            )
            self._rect_start = (pos.x(), pos.y())
            self._rect_selecting = True

            # Remove old rect
            if self._rect_roi is not None:
                self.plot_widget.removeItem(self._rect_roi)
                self._rect_roi = None

            return True

        elif event.type() == QEvent.MouseMove and self._rect_selecting:
            pos = self.plot_widget.getViewBox().mapSceneToView(
                self.plot_widget.mapToScene(event.position().toPoint())
            )
            x1, y1 = self._rect_start
            x2, y2 = pos.x(), pos.y()

            rx = min(x1, x2)
            ry = min(y1, y2)
            rw = abs(x2 - x1)
            rh = abs(y2 - y1)

            # Update visual rect
            if self._rect_roi is not None:
                self.plot_widget.removeItem(self._rect_roi)

            from PySide6.QtWidgets import QGraphicsRectItem
            from PySide6.QtGui import QBrush

            rect = QGraphicsRectItem(rx, ry, rw, rh)
            rect.setPen(pg.mkPen((99, 102, 241), width=2, style=Qt.DashLine))
            rect.setBrush(QBrush(QColor(99, 102, 241, 30)))
            self.plot_widget.addItem(rect)
            self._rect_roi = rect

            return True

        elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self._rect_selecting:
            pos = self.plot_widget.getViewBox().mapSceneToView(
                self.plot_widget.mapToScene(event.position().toPoint())
            )
            self._finish_rect_selection(pos.x(), pos.y())
            return True

        return super().eventFilter(obj, event)

    def _finish_rect_selection(self, end_x: float, end_y: float):
        """Finish rectangle selection, match data points, and emit row indices."""
        import numpy as np

        if self._rect_start is None:
            self._rect_selecting = False
            return

        x1, y1 = self._rect_start
        x_min = min(x1, end_x)
        x_max = max(x1, end_x)
        y_min = min(y1, end_y)
        y_max = max(y1, end_y)

        # Match actual data points within the rectangle (all Y columns)
        row_indices = []
        if self._plot_x_data is not None:
            try:
                x_arr = np.asarray(self._plot_x_data, dtype=float)
                x_mask = (x_arr >= x_min) & (x_arr <= x_max)

                # Hit-test across all Y columns
                y_data_sources = getattr(self, '_plot_y_data_dict', {})
                if not y_data_sources and self._plot_y_data is not None:
                    y_data_sources = {"_default": self._plot_y_data}

                combined_mask = np.zeros(len(x_arr), dtype=bool)
                for y_arr_raw in y_data_sources.values():
                    try:
                        y_arr = np.asarray(y_arr_raw, dtype=float)
                        y_mask = (y_arr >= y_min) & (y_arr <= y_max)
                        combined_mask |= (x_mask & y_mask)
                    except Exception:
                        pass

                row_indices = np.where(combined_mask)[0].tolist()
            except Exception:
                row_indices = []

        # Highlight locally
        self.highlight_selection(row_indices)

        # Emit row indices for cross-panel sync
        self.row_selection_changed.emit(self.dataset_id, row_indices)

        # Also emit x-range for backward compat (ViewSyncManager)
        self._selected_indices = [x_min, x_max]
        self.selection_changed.emit(self.dataset_id, [x_min, x_max])

        # Clean up
        self._rect_selecting = False
        self._rect_start = None

        # Keep the rect visible briefly, then auto-remove after 2s
        if self._rect_roi is not None:
            from PySide6.QtCore import QTimer
            roi = self._rect_roi
            QTimer.singleShot(2000, lambda: self._remove_rect_roi(roi))

    def highlight_selection(self, row_indices: list):
        """Highlight selected data points by row indices using a ScatterPlotItem overlay."""
        import numpy as np

        # Remove previous highlight
        if self._highlight_scatter is not None:
            try:
                if self.plot_widget is not None:
                    self.plot_widget.removeItem(self._highlight_scatter)
            except (RuntimeError, ValueError):
                pass
            self._highlight_scatter = None

        if (
            not row_indices
            or self.plot_widget is None
            or self._plot_x_data is None
            or self._plot_y_data is None
        ):
            return

        try:
            import pyqtgraph as pg

            x_arr = np.asarray(self._plot_x_data, dtype=float)
            y_arr = np.asarray(self._plot_y_data, dtype=float)
            valid = [i for i in row_indices if 0 <= i < len(x_arr)]
            if not valid:
                return

            sel_x = x_arr[valid]
            sel_y = y_arr[valid]

            scatter = pg.ScatterPlotItem(
                x=sel_x,
                y=sel_y,
                size=10,
                pen=pg.mkPen('#EF4444', width=2),
                brush=pg.mkBrush('#EF444480'),
                symbol='o',
                pxMode=True,
            )
            scatter.setZValue(200)
            self.plot_widget.addItem(scatter)
            self._highlight_scatter = scatter
        except Exception:
            pass

    def refresh(self):
        """새로고침 — clear and replot (safe re-render)."""
        try:
            if self.plot_widget is not None:
                self.plot_widget.clear()
                metadata = self.state.get_dataset_metadata(self.dataset_id)
                color = metadata.color if metadata else '#1f77b4'
                self._plot_data(color)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # ViewSyncManager duck-typing interface
    # ------------------------------------------------------------------

    def set_view_range(self, x_range, y_range, sync_x: bool = True, sync_y: bool = True):
        """외부에서 뷰 범위 설정 (동기화용).

        When x_range/y_range are None → auto-range.
        """
        if self.plot_widget is None:
            return

        # Handle auto-range request from ViewSyncManager.reset_all_views()
        if x_range is None and y_range is None:
            self.plot_widget.getViewBox().autoRange()
            return

        self._is_syncing = True
        try:
            viewbox = self.plot_widget.getViewBox()
            if sync_x and sync_y:
                viewbox.setRange(xRange=x_range, yRange=y_range, padding=0)
            elif sync_x:
                viewbox.setRange(xRange=x_range, padding=0)
            elif sync_y:
                viewbox.setRange(yRange=y_range, padding=0)
        finally:
            # QTimer로 동기화 플래그 리셋 (이벤트 루프 후에)
            QTimer.singleShot(50, self._reset_sync_flag)

    def set_selection(self, indices: list):
        """Highlight selected data points in the plot (ViewSyncManager duck-typing).

        ``indices`` is expected to be a two-element list ``[x_min, x_max]``
        representing an X-axis range, or an empty list to clear.
        """
        self._selected_indices = list(indices)
        if self._selection_region is None:
            return

        self._is_selection_syncing = True
        try:
            if len(indices) == 2:
                self._selection_region.setRegion(indices)
                self._selection_region.show()
            else:
                self._selection_region.hide()
        finally:
            QTimer.singleShot(50, self._reset_selection_sync_flag)

    def get_view_range(self) -> tuple:
        """현재 뷰 범위 반환"""
        if self.plot_widget is None:
            return (None, None)
        viewbox = self.plot_widget.getViewBox()
        rect = viewbox.viewRange()
        return (list(rect[0]), list(rect[1]))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_view_range_changed(self, viewbox, ranges):
        """ViewBox 범위 변경 처리"""
        if self._is_syncing:
            return  # 동기화 중이면 무시 (무한 루프 방지)

        x_range = list(ranges[0])
        y_range = list(ranges[1])
        self.view_range_changed.emit(self.dataset_id, x_range, y_range)

    def _reset_sync_flag(self):
        """동기화 플래그 리셋"""
        self._is_syncing = False

    def _reset_selection_sync_flag(self):
        """Selection 동기화 플래그 리셋"""
        self._is_selection_syncing = False

    def _on_selection_region_changed(self):
        """User finished dragging the selection region."""
        if self._is_selection_syncing:
            return
        if self._selection_region is None:
            return
        region = list(self._selection_region.getRegion())
        self._selected_indices = region
        self.selection_changed.emit(self.dataset_id, region)

    def _on_plot_mouse_clicked(self, event):
        """Handle mouse click on plot scene — double-click to create/toggle selection."""
        if event.double():
            if self._selection_region is None:
                return
            if self._selection_region.isVisible():
                # Double-click clears selection
                self._selection_region.hide()
                self._selected_indices = []
                self.selection_changed.emit(self.dataset_id, [])
            else:
                # Double-click creates a selection region at current view center
                vb = self.plot_widget.getViewBox()
                view_range = vb.viewRange()
                x_min, x_max = view_range[0]
                width = (x_max - x_min) * 0.2  # 20% of visible range
                center = (x_min + x_max) / 2
                self._selection_region.setRegion([center - width / 2, center + width / 2])
                self._selection_region.show()
                region = list(self._selection_region.getRegion())
                self._selected_indices = region
                self.selection_changed.emit(self.dataset_id, region)

    def mousePressEvent(self, event):
        """클릭 시 활성화"""
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.dataset_id)
        super().mousePressEvent(event)


class SideBySideLayout(QWidget):
    """
    병렬 비교 레이아웃

    여러 데이터셋을 독립된 패널에 나란히 표시.
    Sync logic delegated to ViewSyncManager (Module H refactor).
    """

    dataset_activated = Signal(str)  # dataset_id

    MAX_PANELS = 6  # 최대 동시 표시 패널 수
    MIN_PANEL_WIDTH = 200  # 최소 패널 너비 (px)

    def __init__(self, engine: DataEngine, state: AppState, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.state = state

        self._panels: Dict[str, MiniGraphWidget] = {}

        # ViewSyncManager replaces internal sync logic (Module H)
        self._view_sync_manager = ViewSyncManager()

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 동기화 옵션
        options_frame = QFrame()
        options_frame.setObjectName("syncOptionsFrame")
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(8, 4, 8, 4)

        options_layout.addWidget(QLabel("Sync:"))

        # Scroll checkbox → controls ViewSyncManager.sync_x
        self.sync_scroll_cb = QCheckBox("Scroll")
        self.sync_scroll_cb.setChecked(self._view_sync_manager.sync_x)
        self.sync_scroll_cb.setToolTip("Synchronize horizontal scrolling across panels")
        self.sync_scroll_cb.stateChanged.connect(self._on_sync_scroll_changed)
        options_layout.addWidget(self.sync_scroll_cb)

        # Zoom checkbox → controls ViewSyncManager.sync_y
        self.sync_zoom_cb = QCheckBox("Zoom")
        self.sync_zoom_cb.setChecked(self._view_sync_manager.sync_y)
        self.sync_zoom_cb.setToolTip("Synchronize zoom level across panels")
        self.sync_zoom_cb.stateChanged.connect(self._on_sync_zoom_changed)
        options_layout.addWidget(self.sync_zoom_cb)

        options_layout.addStretch()

        # 리셋 버튼
        self.reset_btn = QPushButton("Reset Views")
        self.reset_btn.setFixedWidth(80)
        self.reset_btn.setToolTip("Reset view to fit all data")
        self.reset_btn.clicked.connect(self.reset_all_views)
        options_layout.addWidget(self.reset_btn)

        layout.addWidget(options_frame)

        # 패널 스플리터
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter, 1)

    def _connect_signals(self):
        """시그널 연결"""
        self.state.comparison_settings_changed.connect(self.refresh)
        self.state.dataset_added.connect(self._on_dataset_added)
        self.state.dataset_removed.connect(self._on_dataset_removed)

    # ------------------------------------------------------------------
    # Sync checkbox handlers → delegate to ViewSyncManager
    # ------------------------------------------------------------------

    def _on_sync_scroll_changed(self, checkbox_state):
        checked = checkbox_state == Qt.Checked.value if isinstance(checkbox_state, int) else checkbox_state == Qt.Checked
        self._view_sync_manager.sync_x = checked
        self.state.update_comparison_settings(sync_scroll=checked)

    def _on_sync_zoom_changed(self, checkbox_state):
        checked = checkbox_state == Qt.Checked.value if isinstance(checkbox_state, int) else checkbox_state == Qt.Checked
        self._view_sync_manager.sync_y = checked
        self.state.update_comparison_settings(sync_zoom=checked)

    # ------------------------------------------------------------------
    # Dataset lifecycle
    # ------------------------------------------------------------------

    def _on_dataset_added(self, dataset_id: str):
        """데이터셋 추가됨"""
        self.refresh()

    def _on_dataset_removed(self, dataset_id: str):
        """데이터셋 제거됨"""
        if dataset_id in self._panels:
            panel = self._panels[dataset_id]
            self._view_sync_manager.unregister_panel(dataset_id)
            self.splitter.widget(self.splitter.indexOf(panel)).setParent(None)
            del self._panels[dataset_id]

    # ------------------------------------------------------------------
    # Refresh (public API preserved)
    # ------------------------------------------------------------------

    def refresh(self):
        """비교 대상 데이터셋으로 패널 새로고침"""
        # Clear ViewSyncManager and existing panels
        self._view_sync_manager.clear()

        while self.splitter.count() > 0:
            widget = self.splitter.widget(0)
            widget.setParent(None)
        self._panels.clear()

        # 비교 대상 데이터셋
        dataset_ids = self.state.comparison_dataset_ids[:self.MAX_PANELS]

        if not dataset_ids:
            # 활성 데이터셋만 표시
            active_id = self.state.active_dataset_id
            if active_id:
                dataset_ids = [active_id]

        for dataset_id in dataset_ids:
            panel = MiniGraphWidget(dataset_id, self.engine, self.state)
            panel.activated.connect(self._on_panel_activated)
            # Route view_range_changed through ViewSyncManager
            panel.view_range_changed.connect(
                lambda src_id, xr, yr: self._view_sync_manager.on_source_range_changed(src_id, xr, yr)
            )
            # Route selection_changed through ViewSyncManager
            panel.selection_changed.connect(
                lambda src_id, region: self._view_sync_manager.on_source_selection_changed(src_id, region)
            )
            # Route row_selection_changed → always sync highlight to other panels
            panel.row_selection_changed.connect(
                lambda src_id, indices, _did=dataset_id: self._on_row_selection(_did, indices)
            )
            self._panels[dataset_id] = panel
            self._view_sync_manager.register_panel(dataset_id, panel)
            self.splitter.addWidget(panel)

        # 동일 크기로 분할
        if self.splitter.count() > 0:
            sizes = [self.splitter.width() // self.splitter.count()] * self.splitter.count()
            self.splitter.setSizes(sizes)

    # ------------------------------------------------------------------
    # Public API (preserved)
    # ------------------------------------------------------------------

    def reset_all_views(self):
        """모든 패널의 뷰를 자동 범위로 리셋"""
        self._view_sync_manager.reset_all_views()

    def set_comparison_datasets(self, dataset_ids: List[str]):
        """비교 대상 데이터셋 설정"""
        self.state.set_comparison_datasets(dataset_ids[:self.MAX_PANELS])
        self.refresh()

    def sync_all_panels_to(self, source_id: str):
        """특정 패널의 뷰 범위로 모든 패널 동기화 (backward compat)."""
        if source_id not in self._panels:
            return

        source_panel = self._panels[source_id]
        x_range, y_range = source_panel.get_view_range()

        if x_range is None or y_range is None:
            return

        self._view_sync_manager.on_source_range_changed(source_id, x_range, y_range)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_row_selection(self, source_id: str, row_indices: list):
        """Propagate row selection highlight via ViewSyncManager."""
        self._view_sync_manager.on_source_row_selection_changed(source_id, row_indices)

    def _on_panel_activated(self, dataset_id: str):
        """패널 활성화"""
        self.dataset_activated.emit(dataset_id)
