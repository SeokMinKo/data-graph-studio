"""
ProfileDifferenceRenderer — Difference analysis renderer for profile comparison.

Shows A, B, and A-B diff with stats (Mean Diff, Max Diff, RMSE).
Requires exactly 2 profiles with the same X column.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, TYPE_CHECKING

import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShortcut, QKeySequence

if TYPE_CHECKING:
    from ...core.data_engine import DataEngine
    from ...core.state import AppState
    from ...core.profile_store import ProfileStore
    from ...core.profile import GraphSetting

MAX_POINTS = 5000


class ProfileDifferenceRenderer(QWidget):
    """Difference analysis — shows A, B, and A-B diff."""

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

        self._profile_a_id: Optional[str] = None
        self._profile_b_id: Optional[str] = None
        self._plot_widget = None
        self._x_col_label: Optional[QLabel] = None
        self._subtitle_label: Optional[QLabel] = None
        self._stats_label: Optional[QLabel] = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def can_difference(profiles: List["GraphSetting"]) -> bool:
        """Check if exactly 2 profiles with same non-None x_column.

        Returns False when X columns differ, triggering the X-axis
        mismatch warning in the comparison controller.
        """
        if len(profiles) != 2:
            return False
        return (
            profiles[0].x_column == profiles[1].x_column
            and profiles[0].x_column is not None
        )

    @staticmethod
    def compute_diff(df, y_col_a: str, y_col_b: str) -> Dict:
        """Compute diff stats (UT-7).

        Args:
            df: DataFrame (pandas-like) with y_col_a and y_col_b.
            y_col_a: column name for series A.
            y_col_b: column name for series B.

        Returns:
            dict with keys: diff_series, mean_diff, max_diff, rmse.
            diff = df[y_col_a] - df[y_col_b].
            mean_diff and max_diff use absolute values.
        """
        a = np.asarray(df[y_col_a], dtype=np.float64)
        b = np.asarray(df[y_col_b], dtype=np.float64)
        diff = a - b

        if len(diff) == 0:
            return {
                "diff_series": diff,
                "mean_diff": 0.0,
                "max_diff": 0.0,
                "rmse": 0.0,
            }

        abs_diff = np.abs(diff)
        mean_diff = float(np.nanmean(abs_diff))
        max_diff = float(np.nanmax(abs_diff))
        rmse = float(np.sqrt(np.nanmean(diff ** 2)))

        return {
            "diff_series": diff,
            "mean_diff": mean_diff,
            "max_diff": max_diff,
            "rmse": rmse,
        }

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QFrame()
        header.setStyleSheet("background-color: #2c3e50; border-radius: 4px;")
        header.setFixedHeight(52)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(2)

        # Top row: title + x_col + exit
        top_row = QHBoxLayout()
        title = QLabel("Profile Comparison (Difference)")
        title.setStyleSheet("color: white; font-weight: bold;")
        top_row.addWidget(title)

        self._x_col_label = QLabel("")
        self._x_col_label.setStyleSheet("color: rgba(255,255,255,0.8);")
        top_row.addWidget(self._x_col_label)
        top_row.addStretch()

        exit_btn = QPushButton("✕ Exit")
        exit_btn.setFixedWidth(60)
        exit_btn.setStyleSheet(
            "QPushButton { color: white; background: #c0392b; border: none; "
            "border-radius: 3px; padding: 2px 6px; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        exit_btn.setToolTip("Exit difference analysis view")
        exit_btn.clicked.connect(self.exit_requested.emit)
        top_row.addWidget(exit_btn)
        header_layout.addLayout(top_row)

        # Subtitle row
        self._subtitle_label = QLabel("")
        self._subtitle_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px;")
        header_layout.addWidget(self._subtitle_label)

        layout.addWidget(header)

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

        # Stats bar
        stats_frame = QFrame()
        stats_frame.setStyleSheet(
            "background-color: #ecf0f1; border-radius: 4px; padding: 4px;"
        )
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(8, 4, 8, 4)
        self._stats_label = QLabel("Mean Diff: — | Max Diff: — | RMSE: —")
        self._stats_label.setStyleSheet("font-size: 12px;")
        stats_layout.addWidget(self._stats_label)
        stats_layout.addStretch()
        layout.addWidget(stats_frame)

        # Esc shortcut
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self.exit_requested.emit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_profiles(self, profile_a_id: str, profile_b_id: str) -> None:
        """Set the two profiles to compare."""
        self._profile_a_id = profile_a_id
        self._profile_b_id = profile_b_id
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

        self._plot_widget.clear()

        if self._profile_a_id is None or self._profile_b_id is None:
            return

        gs_a = self.store.get(self._profile_a_id)
        gs_b = self.store.get(self._profile_b_id)
        if gs_a is None or gs_b is None:
            return

        x_col = gs_a.x_column
        if self._x_col_label is not None:
            self._x_col_label.setText(f"X: {x_col}" if x_col else "")

        # Extract Y column names
        vc_a = list(gs_a.value_columns)
        vc_b = list(gs_b.value_columns)
        y_col_a = ""
        y_col_b = ""
        if vc_a:
            first = vc_a[0]
            y_col_a = first.get("name", "") if isinstance(first, dict) else getattr(first, "name", "")
        if vc_b:
            first = vc_b[0]
            y_col_b = first.get("name", "") if isinstance(first, dict) else getattr(first, "name", "")

        if self._subtitle_label is not None:
            self._subtitle_label.setText(
                f"Profile A: {y_col_a} vs Profile B: {y_col_b}"
            )

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

        # Y data
        try:
            y_a = df[y_col_a].to_numpy() if y_col_a and y_col_a in df else None
            y_b = df[y_col_b].to_numpy() if y_col_b and y_col_b in df else None
        except Exception:
            y_a = y_b = None

        if y_a is None or y_b is None:
            return

        # Compute diff using pandas-like interface for numpy arrays
        import pandas as pd
        temp_df = pd.DataFrame({"y_a": y_a, "y_b": y_b})
        result = self.compute_diff(temp_df, "y_a", "y_b")

        diff = result["diff_series"]

        # Downsample if needed
        if len(x_data) > MAX_POINTS:
            step = len(x_data) // MAX_POINTS
            x_data = x_data[::step]
            y_a = y_a[::step]
            y_b = y_b[::step]
            diff = diff[::step]

        # Plot
        import pyqtgraph as pg

        # Read styles from profile chart_settings (Item 12)
        def _style(gs, fallback_color, fallback_width=2):
            cs = dict(gs.chart_settings) if gs.chart_settings else {}
            color = cs.get("color", fallback_color)
            width = cs.get("line_width", fallback_width)
            vc = list(gs.value_columns)
            if vc:
                first = vc[0]
                vc_color = first.get("color", None) if isinstance(first, dict) else getattr(first, "color", None)
                if vc_color:
                    color = vc_color
            return color, int(width)

        color_a, width_a = _style(gs_a, "#1f77b4")
        color_b, width_b = _style(gs_b, "#ff7f0e")

        # Series A
        self._plot_widget.plot(
            x_data, y_a,
            pen=pg.mkPen(color_a, width=width_a),
            name=f"A: {y_col_a}",
        )

        # Series B
        self._plot_widget.plot(
            x_data, y_b,
            pen=pg.mkPen(color_b, width=width_b),
            name=f"B: {y_col_b}",
        )

        # Diff shaded area (gray fill)
        zeros = np.zeros_like(diff)
        fill_above = pg.FillBetweenItem(
            pg.PlotCurveItem(x_data, diff, pen=pg.mkPen("#7f7f7f", width=1)),
            pg.PlotCurveItem(x_data, zeros, pen=pg.mkPen(None)),
            brush=pg.mkBrush(127, 127, 127, 60),
        )
        self._plot_widget.addItem(fill_above)

        # Stats bar
        if self._stats_label is not None:
            self._stats_label.setText(
                f"Mean Diff: {result['mean_diff']:.4f}  |  "
                f"Max Diff: {result['max_diff']:.4f}  |  "
                f"RMSE: {result['rmse']:.4f}"
            )
