"""
StatPanel - Statistics Panel with 2x2 Grid Layout
"""

from typing import Optional, Dict, Any
import logging

import numpy as np

from PySide6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QFrame,
    QSpinBox,
    QScrollArea,
    QGroupBox,
    QGridLayout,
    QComboBox,
    QGraphicsPathItem,
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainterPath

from .graph_widgets import ClickablePlotWidget
from ...core.state import AppState
import pyqtgraph as pg

logger = logging.getLogger(__name__)

# ==================== Stat Panel ====================


class StatPanel(QFrame):
    """
    Statistics Panel with 2x2 Grid Layout - Minimal Design

    Layout:
    ┌─────────────────────────────────────┐
    │  📈 Statistics                      │
    ├──────────────────┬──────────────────┤
    │  X Distribution  │  Y Distribution  │
    ├──────────────────┼──────────────────┤
    │  Pie Chart       │  Percentile      │
    ├──────────────────┴──────────────────┤
    │  Summary                            │
    └─────────────────────────────────────┘
    """

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("StatPanel")
        self.setAccessibleName("Statistics Panel")
        self.setAccessibleDescription(
            "Shows distribution histograms and summary statistics for selected data"
        )
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(240)
        self.setMaximumWidth(560)

        self._x_data: Optional[np.ndarray] = None
        self._y_data: Optional[np.ndarray] = None
        self._x_bins: int = 30
        self._y_bins: int = 30
        self._group_data: Optional[Dict[str, float]] = None

        # P1-5: Multi-Y column stats support
        self._all_y_stats: Dict[str, Dict[str, Any]] = {}  # {col_name: stats_dict}
        self._all_y_percentiles: Dict[str, Dict[str, float]] = {}
        self._current_stats_col: Optional[str] = None

        self._setup_ui()
        self._apply_style()
        self.state.selection_changed.connect(self._on_selection_changed)

    def _apply_style(self):
        # Styles now handled by global theme stylesheet
        pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header - compact
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_layout.setSpacing(4)

        header = QLabel("📈 Stats")
        header.setObjectName("sectionHeader")
        header_layout.addWidget(header)

        # P1-5: Column selector for multi-Y stats
        self._stats_col_combo = QComboBox()
        self._stats_col_combo.setMaximumWidth(180)
        self._stats_col_combo.setToolTip("Select Y column for statistics")
        self._stats_col_combo.currentTextChanged.connect(self._on_stats_col_changed)
        self._stats_col_combo.hide()  # Hidden until multiple Y columns
        header_layout.addWidget(self._stats_col_combo)

        # Selection count label
        self._selection_label = QLabel("")
        self._selection_label.setObjectName("selectionLabel")
        self._selection_label.setStyleSheet(
            "color: #EF4444; font-weight: bold; font-size: 11px;"
        )
        self._selection_label.hide()
        header_layout.addWidget(self._selection_label)

        header_layout.addStretch()

        # Bin controls (hidden)
        self.x_bins_spin = QSpinBox()
        self.x_bins_spin.setRange(5, 200)
        self.x_bins_spin.setValue(30)
        self.x_bins_spin.valueChanged.connect(self._on_x_bins_changed)
        self.x_bins_spin.hide()

        self.y_bins_spin = QSpinBox()
        self.y_bins_spin.setRange(5, 200)
        self.y_bins_spin.setValue(30)
        self.y_bins_spin.valueChanged.connect(self._on_y_bins_changed)
        self.y_bins_spin.hide()

        layout.addLayout(header_layout)

        # 2x2 Grid for graphs - compact
        graph_grid = QGridLayout()
        graph_grid.setSpacing(4)
        graph_grid.setContentsMargins(0, 0, 0, 0)

        # Create mini plot widgets with minimal chrome
        self._mini_plot_widgets = []  # Store for theme updates

        def create_plot_group(title: str) -> tuple:
            group = QGroupBox(title)
            group.setToolTip("Double-click to expand")
            grp_layout = QVBoxLayout(group)
            grp_layout.setContentsMargins(2, 2, 2, 2)
            grp_layout.setSpacing(0)

            widget = ClickablePlotWidget()
            widget.setMinimumHeight(60)
            widget.setMaximumHeight(80)
            # Default dark background - will be updated by apply_theme()
            widget.setBackground("#2B3440")
            widget.hideAxis("bottom")
            widget.hideAxis("left")
            widget.setCursor(Qt.PointingHandCursor)
            widget.getPlotItem().setContentsMargins(0, 0, 0, 0)
            grp_layout.addWidget(widget)
            self._mini_plot_widgets.append(widget)
            return group, widget

        # X Distribution
        x_group, self.x_hist_widget = create_plot_group("X Dist")
        graph_grid.addWidget(x_group, 0, 0)

        # Y Distribution
        y_group, self.y_hist_widget = create_plot_group("Y Dist")
        graph_grid.addWidget(y_group, 0, 1)

        # GroupBy Ratio (Pie)
        pie_group, self.pie_widget = create_plot_group("GroupBy Ratio")
        graph_grid.addWidget(pie_group, 1, 0)

        # Percentile
        pct_group, self.percentile_widget = create_plot_group("Percentile")
        graph_grid.addWidget(pct_group, 1, 1)

        layout.addLayout(graph_grid)

        # Summary Stats - compact, selectable, scrollable
        stats_group = QGroupBox("Summary")
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setContentsMargins(4, 4, 4, 4)

        stats_scroll = QScrollArea()
        stats_scroll.setWidgetResizable(True)
        stats_scroll.setFrameShape(QFrame.NoFrame)
        stats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        stats_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        stats_scroll.setStyleSheet("background: transparent; border: none;")

        self.stats_label = QLabel("Load data to see statistics")
        self.stats_label.setObjectName("statsLabel")
        self.stats_label.setWordWrap(True)
        self.stats_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.stats_label.setCursor(Qt.IBeamCursor)
        stats_scroll.setWidget(self.stats_label)

        stats_layout.addWidget(stats_scroll)

        layout.addWidget(stats_group, 1)  # stretch factor 1 → fill remaining space

        # Setup hover tooltips for mini graphs
        self._setup_mini_graph_hover()

    def _setup_mini_graph_hover(self):
        """Setup mouse hover tooltip for mini stat graphs"""
        for widget in self._mini_plot_widgets:
            hover_label = pg.TextItem(text="", anchor=(0, 1), color="#E2E8F0")
            hover_label.setZValue(1000)
            hover_label.setFont(pg.QtGui.QFont("Arial", 9))
            hover_label.hide()
            widget.addItem(hover_label)
            widget._hover_label = hover_label
            widget.setMouseTracking(True)

            proxy = pg.SignalProxy(
                widget.scene().sigMouseMoved,
                rateLimit=30,
                slot=lambda evt, w=widget: self._on_mini_graph_hover(evt, w),
            )
            widget._hover_proxy = proxy  # prevent GC

    def _on_mini_graph_hover(self, evt, widget):
        """Show x,y value on mini graph hover"""
        pos = evt[0]
        vb = widget.getPlotItem().vb
        if widget.sceneBoundingRect().contains(pos):
            mouse_point = vb.mapSceneToView(pos)
            x_val = mouse_point.x()
            y_val = mouse_point.y()
            widget._hover_label.setText(f"x={x_val:.2g}  y={y_val:.2g}")
            widget._hover_label.setPos(mouse_point)
            widget._hover_label.show()
        else:
            widget._hover_label.hide()

    def _on_selection_changed(self):
        """Update selection count display."""
        count = self.state.selection.selection_count
        if count > 0:
            self._selection_label.setText(f"🔘 {count:,} selected")
            self._selection_label.show()
        else:
            self._selection_label.hide()

    def _on_x_bins_changed(self, value: int):
        self._x_bins = value
        self.x_hist_widget.set_bins(value)
        self._update_x_histogram()

    def _on_y_bins_changed(self, value: int):
        self._y_bins = value
        self.y_hist_widget.set_bins(value)
        self._update_y_histogram()

    def _update_x_histogram(self):
        self.x_hist_widget.clear()
        if self._x_data is not None and len(self._x_data) > 0:
            try:
                clean_x = self._x_data[~np.isnan(self._x_data)]
                if len(clean_x) > 0:
                    hist, bins = np.histogram(clean_x, bins=self._x_bins)
                    self.x_hist_widget.plot(
                        bins,
                        hist,
                        stepMode="center",
                        fillLevel=0,
                        brush=(100, 100, 200, 100),
                    )
            except:
                pass

    def _update_y_histogram(self):
        self.y_hist_widget.clear()
        if self._y_data is not None and len(self._y_data) > 0:
            try:
                clean_y = self._y_data[~np.isnan(self._y_data)]
                if len(clean_y) > 0:
                    hist, bins = np.histogram(clean_y, bins=self._y_bins)
                    # Horizontal histogram style
                    bin_centers = (bins[:-1] + bins[1:]) / 2
                    self.y_hist_widget.clear()
                    bar_height = (bins[1] - bins[0]) * 0.8 if len(bins) > 1 else 0.8
                    bar_item = pg.BarGraphItem(
                        x0=np.zeros(len(hist)),
                        y=bin_centers,
                        width=hist,
                        height=bar_height,
                        brush=(100, 200, 100, 100),
                        pen=pg.mkPen((100, 200, 100, 255), width=1),
                    )
                    self.y_hist_widget.addItem(bar_item)
            except:
                pass

    def _render_pie(self, labels: list, values: list, colors: list):
        """Render pie chart in the mini widget"""
        self.pie_widget.clear()
        if not labels or not values:
            return
        try:
            total = float(sum(values))
            if total <= 0:
                return

            self.pie_widget.setAspectLocked(True)
            self.pie_widget.hideAxis("bottom")
            self.pie_widget.hideAxis("left")

            pie_rect = QRectF(-1.0, -1.0, 2.0, 2.0)
            start_angle = 90.0
            for value, color in zip(values, colors):
                if value <= 0:
                    continue
                span_angle = -(float(value) / total) * 360.0

                path = QPainterPath()
                path.moveTo(0.0, 0.0)
                path.arcTo(pie_rect, start_angle, span_angle)
                path.closeSubpath()

                wedge = QGraphicsPathItem(path)
                wedge.setBrush(pg.mkBrush(color))
                wedge.setPen(pg.mkPen(color="w", width=1))
                wedge.setZValue(10)
                self.pie_widget.addItem(wedge)

                start_angle += span_angle
        except Exception:
            logger.warning("stat_panel.render_pie.error", exc_info=True)
            # Fallback: bar chart
            x = np.arange(len(labels))
            bars = pg.BarGraphItem(
                x=x, height=values, width=0.6, brushes=[pg.mkBrush(c) for c in colors]
            )
            self.pie_widget.addItem(bars)
            # Set X-axis labels to group names
            self.pie_widget.showAxis("bottom")
            ax = self.pie_widget.getAxis("bottom")
            ticks = [(i, str(lbl)) for i, lbl in enumerate(labels)]
            ax.setTicks([ticks])

    def _update_pie_chart(self):
        """Update the pie chart"""
        self.pie_widget.clear()
        if self._group_data is None or len(self._group_data) == 0:
            # If no group data, show Y value distribution by quartiles
            if self._y_data is not None and len(self._y_data) > 0:
                try:
                    clean_y = self._y_data[~np.isnan(self._y_data)]
                    if len(clean_y) > 0:
                        q1 = np.percentile(clean_y, 25)
                        q2 = np.percentile(clean_y, 50)
                        q3 = np.percentile(clean_y, 75)

                        # Count values in each quartile
                        c1 = np.sum(clean_y <= q1)
                        c2 = np.sum((clean_y > q1) & (clean_y <= q2))
                        c3 = np.sum((clean_y > q2) & (clean_y <= q3))
                        c4 = np.sum(clean_y > q3)

                        labels = ["Q1", "Q2", "Q3", "Q4"]
                        values = [c1, c2, c3, c4]
                        colors = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444"]

                        # Mini pie chart
                        self._render_pie(labels, values, colors)

                        # Store for expansion
                        self.pie_widget.set_pie_data(
                            labels, values, "Y Value Distribution by Quartile", colors
                        )
                except:
                    pass
            return

        try:
            labels = list(self._group_data.keys())[:10]  # Limit to 10 categories
            values = [self._group_data[k] for k in labels]

            colors = [
                "#1f77b4",
                "#ff7f0e",
                "#2ca02c",
                "#d62728",
                "#9467bd",
                "#8c564b",
                "#e377c2",
                "#7f7f7f",
                "#bcbd22",
                "#17becf",
            ]

            # Mini pie chart representation
            self._render_pie(
                labels, values, [colors[i % len(colors)] for i in range(len(labels))]
            )

            # Store for expansion
            self.pie_widget.set_pie_data(
                labels, values, "Y Groupby Aggregation", colors
            )
        except:
            pass

    def _update_percentile_chart(self):
        """Update the percentile line chart"""
        self.percentile_widget.clear()
        if self._y_data is None or len(self._y_data) == 0:
            return

        try:
            clean_y = self._y_data[~np.isnan(self._y_data)]
            if len(clean_y) == 0:
                return

            # Detailed percentiles
            percentiles = np.array(
                [
                    0,
                    1,
                    2,
                    3,
                    4,
                    5,
                    10,
                    25,
                    50,
                    75,
                    90,
                    95,
                    97,
                    99,
                    99.7,
                    99.9,
                    99.99,
                    100,
                ]
            )
            values = np.percentile(clean_y, percentiles)

            # Line plot with markers
            pen = pg.mkPen(color=(148, 103, 189), width=2)  # Purple
            self.percentile_widget.plot(
                percentiles,
                values,
                pen=pen,
                symbol="o",
                symbolSize=5,
                symbolBrush=pg.mkBrush(148, 103, 189),
                symbolPen=pg.mkPen("w", width=0.5),
            )

            # Store for expansion
            self.percentile_widget.set_percentile_data(
                clean_y, "Y Values Percentile Distribution", (148, 103, 189)
            )
        except:
            pass

    def update_histograms(
        self,
        x_data: Optional[np.ndarray],
        y_data: Optional[np.ndarray],
        group_data: Optional[Dict[str, float]] = None,
    ):
        """Update all charts with new data"""
        self._x_data = x_data
        self._y_data = y_data
        self._group_data = group_data

        # Store data for double-click expansion
        # X Distribution: vertical histogram (default)
        if x_data is not None:
            self.x_hist_widget.set_data(
                x_data,
                "X-Axis Distribution",
                (100, 100, 200, 150),
                bins=self._x_bins,
                horizontal=False,
            )
        # Y Distribution: horizontal histogram
        if y_data is not None:
            self.y_hist_widget.set_data(
                y_data,
                "Y-Axis Distribution",
                (100, 200, 100, 150),
                bins=self._y_bins,
                horizontal=True,
            )

        # Update all charts
        self._update_x_histogram()
        self._update_y_histogram()
        self._update_pie_chart()
        self._update_percentile_chart()

    def set_group_data(self, group_data: Dict[str, float]):
        """Set groupby aggregation data for pie chart"""
        self._group_data = group_data
        self._update_pie_chart()

    def _on_stats_col_changed(self, col_name: str):
        """P1-5: Switch displayed stats when user selects a different Y column."""
        if not col_name:
            return
        self._current_stats_col = col_name
        stats = self._all_y_stats.get(col_name, {})
        percentiles = self._all_y_percentiles.get(col_name)
        self.update_stats(stats, percentiles)

    def update_multi_y_stats(
        self,
        stats_by_col: Dict[str, Dict[str, Any]],
        percentiles_by_col: Dict[str, Dict[str, float]] = None,
        group_counts: Dict[str, int] = None,
        group_sums: Dict[str, float] = None,
    ):
        """P1-5: Update stats for all value columns. Shows combo if 2+ columns."""
        self._all_y_stats = stats_by_col or {}
        self._all_y_percentiles = percentiles_by_col or {}

        col_names = list(self._all_y_stats.keys())
        if len(col_names) >= 2:
            self._stats_col_combo.blockSignals(True)
            self._stats_col_combo.clear()
            self._stats_col_combo.addItems(col_names)
            # Preserve current selection if still valid
            if self._current_stats_col in col_names:
                self._stats_col_combo.setCurrentText(self._current_stats_col)
            else:
                self._current_stats_col = col_names[0]
            self._stats_col_combo.blockSignals(False)
            self._stats_col_combo.show()
        else:
            self._stats_col_combo.hide()
            self._current_stats_col = col_names[0] if col_names else None

        # Show stats for current column
        if self._current_stats_col and self._current_stats_col in self._all_y_stats:
            stats = self._all_y_stats[self._current_stats_col]
            pcts = self._all_y_percentiles.get(self._current_stats_col)
            self.update_stats(stats, pcts, group_counts, group_sums)

    def update_stats(
        self,
        stats: Dict[str, Any],
        percentiles: Dict[str, float] = None,
        group_counts: Dict[str, int] = None,
        group_sums: Dict[str, float] = None,
    ):
        if stats is None:
            self.stats_label.setText("Load data to see statistics")
            return
        if not stats:
            # stats is empty dict {} — data is loaded but no columns selected
            self.stats_label.setText("Select data columns to view statistics")
            return

        lines = []
        # Format stats in a more compact 2-column layout
        items = list(stats.items())
        for i in range(0, len(items), 2):
            left = items[i]
            right = items[i + 1] if i + 1 < len(items) else None

            left_str = (
                f"{left[0]}: {left[1]:.2f}"
                if isinstance(left[1], float)
                else f"{left[0]}: {left[1]}"
            )

            if right:
                right_str = (
                    f"{right[0]}: {right[1]:.2f}"
                    if isinstance(right[1], float)
                    else f"{right[0]}: {right[1]}"
                )
                lines.append(f"{left_str:<20} {right_str}")
            else:
                lines.append(left_str)

        # Percentiles
        if percentiles:
            lines.append("\nPercentiles")
            for k, v in percentiles.items():
                lines.append(f"  {k}: {v:.4f}")

        # Group stats
        if group_counts or group_sums:
            lines.append("\nGroupBy Stats")
            if group_counts:
                for k, v in group_counts.items():
                    lines.append(f"  {k} count: {v}")
            if group_sums:
                for k, v in group_sums.items():
                    lines.append(f"  {k} sum: {v:.4f}")

        self.stats_label.setText("\n".join(lines))

    def apply_theme(self, is_light: bool):
        """Apply theme colors to mini-graphs"""
        bg_color = "#F8FAFC" if is_light else "#2B3440"
        if hasattr(self, "_mini_plot_widgets"):
            for widget in self._mini_plot_widgets:
                widget.setBackground(bg_color)


# ==================== Main Graph ====================
