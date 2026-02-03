"""
ProfileOverlayRenderer — Overlay renderer for profile comparison.

Multiple Y series on one chart for profiles sharing the same X column.
Supports dual-axis, mixed chart_type handling, downsampling, and interactive legend.
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShortcut, QKeySequence

if TYPE_CHECKING:
    from ...core.data_engine import DataEngine
    from ...core.state import AppState
    from ...core.profile_store import ProfileStore
    from ...core.profile import GraphSetting


# Distinct color palette for overlay series
OVERLAY_COLORS = [
    "#1f77b4",  # blue
    "#ff7f0e",  # orange
    "#2ca02c",  # green
    "#d62728",  # red
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#17becf",  # cyan
]

MAX_POINTS_PER_SERIES = 5000


class ProfileOverlayRenderer(QWidget):
    """Overlay renderer — multiple Y series on one chart for same X column."""

    exit_requested = Signal()

    def __init__(
        self,
        dataset_id: str,
        engine: "DataEngine",
        state: "AppState",
        store: "ProfileStore",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.dataset_id = dataset_id
        self.engine = engine
        self.state = state
        self.store = store

        self._profile_ids: List[str] = []
        self._plot_widget = None
        self._warning_label: Optional[QLabel] = None
        self._x_col_label: Optional[QLabel] = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def can_overlay(profiles: List["GraphSetting"]) -> bool:
        """Check if all profiles share the same x_column (UT-6).

        Returns True only when there is at least one profile and every profile
        has the same non-None x_column.
        """
        if not profiles:
            return False
        x_cols = {p.x_column for p in profiles}
        return len(x_cols) == 1 and None not in x_cols

    @staticmethod
    def needs_dual_axis(max_a: float, max_b: float) -> bool:
        """UT-9: Determine if dual Y axes are needed.

        Returns True when the ratio of the two maxima exceeds 10 (strict >).
        Zero values are treated as "no range" and return False.
        """
        if max_a == 0.0 or max_b == 0.0:
            return False
        ratio = max(abs(max_a), abs(max_b)) / min(abs(max_a), abs(max_b))
        return ratio > 10

    @staticmethod
    def has_mixed_chart_types(profiles: List["GraphSetting"]) -> bool:
        """UT-10: Check if profiles use different chart_type values."""
        if len(profiles) <= 1:
            return False
        types = {(p.chart_type or "line") for p in profiles}
        return len(types) > 1

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QFrame()
        header.setStyleSheet("background-color: #34495e; border-radius: 4px;")
        header.setFixedHeight(36)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("Profile Comparison (Overlay)")
        title.setStyleSheet("color: white; font-weight: bold;")
        header_layout.addWidget(title)

        self._x_col_label = QLabel("")
        self._x_col_label.setStyleSheet("color: rgba(255,255,255,0.8);")
        header_layout.addWidget(self._x_col_label)

        header_layout.addStretch()

        exit_btn = QPushButton("✕ Exit")
        exit_btn.setFixedWidth(60)
        exit_btn.setStyleSheet(
            "QPushButton { color: white; background: #c0392b; border: none; "
            "border-radius: 3px; padding: 2px 6px; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        exit_btn.setToolTip("Exit overlay comparison view")
        exit_btn.clicked.connect(self.exit_requested.emit)
        header_layout.addWidget(exit_btn)

        layout.addWidget(header)

        # Warning label (hidden by default)
        self._warning_label = QLabel("")
        self._warning_label.setStyleSheet("color: #e67e22; font-size: 11px; padding: 2px 8px;")
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

        # Plot area
        try:
            import pyqtgraph as pg

            self._plot_widget = pg.PlotWidget()
            self._plot_widget.setBackground("w")
            self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self._plot_widget.addLegend(offset=(10, 10))
            self._plot_widget.setMinimumHeight(200)
            layout.addWidget(self._plot_widget, 1)
        except ImportError:
            placeholder = QLabel("pyqtgraph not available")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setMinimumHeight(200)
            layout.addWidget(placeholder, 1)

        # Esc shortcut
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self.exit_requested.emit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_profiles(self, profile_ids: List[str]) -> None:
        """Set which profiles to overlay."""
        self._profile_ids = list(profile_ids)
        self._render()

    def refresh(self) -> None:
        """Re-render current profiles."""
        self._render()

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        if self._plot_widget is None:
            return

        import numpy as np

        self._plot_widget.clear()

        # Resolve profiles
        profiles: List["GraphSetting"] = []
        for pid in self._profile_ids:
            gs = self.store.get(pid)
            if gs is not None:
                profiles.append(gs)

        if not profiles:
            return

        # Determine shared X column
        x_col = profiles[0].x_column
        if self._x_col_label is not None:
            self._x_col_label.setText(f"X: {x_col}" if x_col else "")

        # Mixed chart_type warning (FR-11)
        if self.has_mixed_chart_types(profiles):
            if self._warning_label is not None:
                self._warning_label.setText("⚠ Mixed chart types → rendered as line")
                self._warning_label.setVisible(True)
        else:
            if self._warning_label is not None:
                self._warning_label.setVisible(False)

        # Get dataset
        dataset = self.engine.get_dataset(self.dataset_id)
        if dataset is None or dataset.df is None:
            return

        df = dataset.df

        # X data
        try:
            if x_col and hasattr(df, "__contains__") and x_col in df:
                x_series = df[x_col]
                x_data = x_series.to_numpy() if hasattr(x_series, "to_numpy") else np.arange(len(df))
            else:
                x_data = np.arange(len(df))
        except Exception:
            x_data = np.arange(len(df))

        # Collect Y max values per series (for dual-axis detection)
        import pyqtgraph as pg

        series_data = []
        for i, gs in enumerate(profiles):
            vc = list(gs.value_columns)
            if not vc:
                continue
            first_vc = vc[0]
            y_col = first_vc.get("name", "") if isinstance(first_vc, dict) else getattr(first_vc, "name", "")
            if not y_col:
                continue
            try:
                if hasattr(df, "__contains__") and y_col in df:
                    y_series = df[y_col]
                    y_data = y_series.to_numpy() if hasattr(y_series, "to_numpy") else None
                else:
                    y_data = None
            except Exception:
                y_data = None
            if y_data is None:
                continue

            color = OVERLAY_COLORS[i % len(OVERLAY_COLORS)]
            series_data.append({
                "profile": gs,
                "y_col": y_col,
                "y_data": y_data,
                "color": color,
                "y_max": float(np.nanmax(np.abs(y_data))) if len(y_data) > 0 else 0.0,
            })

        if not series_data:
            return

        # Dual-axis detection (only when exactly 2 series)
        use_dual = False
        if len(series_data) == 2:
            use_dual = self.needs_dual_axis(series_data[0]["y_max"], series_data[1]["y_max"])

        # Plot each series
        for idx, sd in enumerate(series_data):
            x_plot = x_data
            y_plot = sd["y_data"]

            # Downsample if needed
            if len(x_plot) > MAX_POINTS_PER_SERIES:
                step = len(x_plot) // MAX_POINTS_PER_SERIES
                x_plot = x_plot[::step]
                y_plot = y_plot[::step]

            pen = pg.mkPen(sd["color"], width=2)
            label = f"{sd['profile'].name} ({sd['y_col']})"

            if use_dual and idx == 1:
                # Second series on right Y axis
                p2 = pg.ViewBox()
                self._plot_widget.scene().addItem(p2)
                self._plot_widget.getAxis("right").linkToView(p2)
                self._plot_widget.getAxis("right").setLabel(sd["y_col"])
                p2.setXLink(self._plot_widget)
                curve = pg.PlotCurveItem(x_plot, y_plot, pen=pen, name=label)
                p2.addItem(curve)
            else:
                self._plot_widget.plot(x_plot, y_plot, pen=pen, name=label)
