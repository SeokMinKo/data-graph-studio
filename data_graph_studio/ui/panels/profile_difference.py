"""
ProfileDifferenceRenderer — Difference analysis renderer for profile comparison.

Shows A, B, and A-B diff with stats (Mean Diff, Max Diff, RMSE).
Requires exactly 2 profiles with the same X column.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

import numpy as np

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
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

        self._is_light: bool = False  # Default: dark (midnight) theme
        self._diff_mode: str = "absolute"  # "absolute" or "percent"
        self._profile_a_id: Optional[str] = None
        self._profile_b_id: Optional[str] = None
        self._profile_ids: List[str] = []  # multi-profile support
        self._plot_widget = None
        self._header: Optional[QFrame] = None
        self._header_title: Optional[QLabel] = None
        self._x_col_label: Optional[QLabel] = None
        self._subtitle_label: Optional[QLabel] = None
        self._stats_label: Optional[QLabel] = None
        self._stats_frame: Optional[QFrame] = None
        self._abs_btn: Optional[QPushButton] = None
        self._pct_btn: Optional[QPushButton] = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def can_difference(profiles: List["GraphSetting"]) -> bool:
        """Check if 2+ profiles with same non-None x_column.

        Returns False when X columns differ, triggering the X-axis
        mismatch warning in the comparison controller.
        """
        if len(profiles) < 2:
            return False
        x_cols = {p.x_column for p in profiles}
        return len(x_cols) == 1 and None not in x_cols

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
        rmse = float(np.sqrt(np.nanmean(diff**2)))

        return {
            "diff_series": diff,
            "mean_diff": mean_diff,
            "max_diff": max_diff,
            "rmse": rmse,
        }

    @staticmethod
    def compute_pct_diff(df, y_col_a: str, y_col_b: str) -> Dict:
        """Compute percentage diff stats: (A - B) / B * 100.

        Returns dict with keys: diff_series, mean_diff, max_diff, rmse.
        B==0 positions are set to NaN.
        """
        a = np.asarray(df[y_col_a], dtype=np.float64)
        b = np.asarray(df[y_col_b], dtype=np.float64)

        with np.errstate(divide="ignore", invalid="ignore"):
            pct = np.where(b != 0, (a - b) / b * 100.0, np.nan)

        if len(pct) == 0:
            return {
                "diff_series": pct,
                "mean_diff": 0.0,
                "max_diff": 0.0,
                "rmse": 0.0,
            }

        abs_pct = np.abs(pct)
        mean_diff = float(np.nanmean(abs_pct))
        max_diff = float(np.nanmax(abs_pct)) if not np.all(np.isnan(abs_pct)) else 0.0
        rmse = float(np.sqrt(np.nanmean(pct**2))) if not np.all(np.isnan(pct)) else 0.0

        return {
            "diff_series": pct,
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
        self._header = QFrame()
        self._header.setFixedHeight(52)
        header_layout = QVBoxLayout(self._header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(2)

        # Top row: title + x_col + exit
        top_row = QHBoxLayout()
        self._header_title = QLabel("Profile Comparison (Difference)")
        top_row.addWidget(self._header_title)

        self._x_col_label = QLabel("")
        top_row.addWidget(self._x_col_label)
        top_row.addStretch()

        # Absolute / Percent toggle buttons
        self._abs_btn = QPushButton("Absolute")
        self._abs_btn.setFixedWidth(70)
        self._abs_btn.setCheckable(True)
        self._abs_btn.setChecked(True)
        self._abs_btn.clicked.connect(lambda: self._set_diff_mode("absolute"))
        top_row.addWidget(self._abs_btn)

        self._pct_btn = QPushButton("Percent")
        self._pct_btn.setFixedWidth(70)
        self._pct_btn.setCheckable(True)
        self._pct_btn.setChecked(False)
        self._pct_btn.clicked.connect(lambda: self._set_diff_mode("percent"))
        top_row.addWidget(self._pct_btn)

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
        header_layout.addWidget(self._subtitle_label)

        layout.addWidget(self._header)

        # Plot area
        try:
            import pyqtgraph as pg

            self._plot_widget = pg.PlotWidget()
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
        self._stats_frame = QFrame()
        stats_layout = QHBoxLayout(self._stats_frame)
        stats_layout.setContentsMargins(8, 4, 8, 4)
        self._stats_label = QLabel("Mean Diff: — | Max Diff: — | RMSE: —")
        self._stats_label.setStyleSheet("font-size: 12px;")
        stats_layout.addWidget(self._stats_label)
        stats_layout.addStretch()
        layout.addWidget(self._stats_frame)

        # Esc shortcut
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self.exit_requested.emit)

        # Apply initial theme
        self.apply_theme(self._is_light)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, is_light: bool) -> None:
        """Apply light/dark theme colors."""
        self._is_light = is_light

        # Header
        header_bg = "#E5E7EB" if is_light else "#1E293B"
        header_fg = "#111827" if is_light else "#FFFFFF"
        header_fg_muted = "rgba(0,0,0,0.6)" if is_light else "rgba(255,255,255,0.8)"
        header_fg_subtle = "rgba(0,0,0,0.5)" if is_light else "rgba(255,255,255,0.7)"

        if self._header:
            self._header.setStyleSheet(
                f"background-color: {header_bg}; border-radius: 4px;"
            )
        if self._header_title:
            self._header_title.setStyleSheet(f"color: {header_fg}; font-weight: bold;")
        if self._x_col_label:
            self._x_col_label.setStyleSheet(f"color: {header_fg_muted};")
        if self._subtitle_label:
            self._subtitle_label.setStyleSheet(
                f"color: {header_fg_subtle}; font-size: 11px;"
            )

        # Plot background
        plot_bg = "#FFFFFF" if is_light else "#1E293B"
        if self._plot_widget:
            self._plot_widget.setBackground(plot_bg)

        # Stats bar
        stats_bg = "#F3F4F6" if is_light else "#334155"
        stats_fg = "#111827" if is_light else "#E2E8F0"
        if self._stats_frame:
            self._stats_frame.setStyleSheet(
                f"background-color: {stats_bg}; border-radius: 4px; padding: 4px;"
            )
        if self._stats_label:
            self._stats_label.setStyleSheet(f"font-size: 12px; color: {stats_fg};")

        # Toggle buttons
        btn_style = (
            "QPushButton { color: %(fg)s; background: transparent; border: 1px solid %(border)s; "
            "border-radius: 3px; padding: 2px 6px; font-size: 10px; }"
            "QPushButton:checked { background: %(accent)s; color: white; border-color: %(accent)s; }"
        ) % {
            "fg": header_fg,
            "border": header_fg_muted,
            "accent": "#3B82F6",
        }
        if self._abs_btn:
            self._abs_btn.setStyleSheet(btn_style)
        if self._pct_btn:
            self._pct_btn.setStyleSheet(btn_style)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _set_diff_mode(self, mode: str) -> None:
        """Switch between absolute and percent diff mode."""
        self._diff_mode = mode
        if self._abs_btn and self._pct_btn:
            self._abs_btn.setChecked(mode == "absolute")
            self._pct_btn.setChecked(mode == "percent")
        self._render()

    def set_profiles(self, *args) -> None:
        """Set profiles to compare.

        Accepts either:
          - set_profiles(profile_a_id, profile_b_id)  (legacy 2-arg)
          - set_profiles([id1, id2, ...])              (multi-profile list)
        """
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            ids = list(args[0])
        elif len(args) == 2 and isinstance(args[0], str):
            ids = [args[0], args[1]]
        else:
            ids = list(args)

        self._profile_ids = ids
        # Backward compat
        self._profile_a_id = ids[0] if len(ids) >= 1 else None
        self._profile_b_id = ids[1] if len(ids) >= 2 else None
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

        if len(self._profile_ids) < 2:
            return

        # Resolve all profiles
        profiles = []
        for pid in self._profile_ids:
            gs = self.store.get(pid)
            if gs is not None:
                profiles.append((pid, gs))

        if len(profiles) < 2:
            return

        # Baseline is first profile
        _, gs_baseline = profiles[0]
        x_col = gs_baseline.x_column
        if self._x_col_label is not None:
            self._x_col_label.setText(f"X: {x_col}" if x_col else "")

        # Y column helper
        def _y_col(gs):
            vc = list(gs.value_columns)
            if not vc:
                return ""
            first = vc[0]
            return (
                first.get("name", "")
                if isinstance(first, dict)
                else getattr(first, "name", "")
            )

        y_col_baseline = _y_col(gs_baseline)

        if self._subtitle_label is not None:
            others = ", ".join(f"{gs.name}({_y_col(gs)})" for _, gs in profiles[1:])
            self._subtitle_label.setText(
                f"Baseline: {gs_baseline.name}({y_col_baseline}) vs {others}"
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
                x_data = (
                    x_series.to_numpy()
                    if hasattr(x_series, "to_numpy")
                    else np.arange(len(df))
                )
            else:
                x_data = np.arange(len(df))
        except Exception:
            x_data = np.arange(len(df))

        from .profile_overlay import ProfileOverlayRenderer

        x_data = ProfileOverlayRenderer._coerce_x_to_numeric(x_data, len(df))

        # Baseline Y data
        try:
            y_baseline = (
                df[y_col_baseline].to_numpy()
                if y_col_baseline and y_col_baseline in df
                else None
            )
        except Exception:
            y_baseline = None

        if y_baseline is None:
            return

        import pyqtgraph as pg
        import pandas as pd

        # Style helper
        def _style(gs, fallback_color, fallback_width=2):
            cs = dict(gs.chart_settings) if gs.chart_settings else {}
            color = cs.get("color", fallback_color)
            width = cs.get("line_width", fallback_width)
            vc = list(gs.value_columns)
            if vc:
                first = vc[0]
                vc_color = (
                    first.get("color", None)
                    if isinstance(first, dict)
                    else getattr(first, "color", None)
                )
                if vc_color:
                    color = vc_color
            return color, int(width)

        DIFF_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

        # Downsample settings from baseline
        cs_base = dict(gs_baseline.chart_settings) if gs_baseline.chart_settings else {}
        show_all = cs_base.get("show_all_data", False)
        mp = cs_base.get("max_points", MAX_POINTS)

        # Plot baseline
        color_base, width_base = _style(gs_baseline, DIFF_COLORS[0])
        x_plot = x_data
        y_base_plot = y_baseline
        if not show_all and len(x_plot) > mp:
            step = len(x_plot) // mp
            x_plot = x_plot[::step]
            y_base_plot = y_base_plot[::step]

        self._plot_widget.plot(
            x_plot,
            y_base_plot,
            pen=pg.mkPen(color_base, width=width_base),
            name=f"Baseline: {y_col_baseline}",
        )

        # For each other profile, compute and plot diff
        all_stats = []

        for pair_idx, (pid, gs_other) in enumerate(profiles[1:], start=1):
            y_col_other = _y_col(gs_other)
            try:
                y_other = (
                    df[y_col_other].to_numpy()
                    if y_col_other and y_col_other in df
                    else None
                )
            except Exception:
                y_other = None

            if y_other is None:
                continue

            # Compute diff
            temp_df = pd.DataFrame({"y_a": y_baseline, "y_b": y_other})
            if self._diff_mode == "percent":
                result = self.compute_pct_diff(temp_df, "y_a", "y_b")
            else:
                result = self.compute_diff(temp_df, "y_a", "y_b")
            diff = result["diff_series"]

            # Downsample
            x_d = x_data
            y_o = y_other
            d = diff
            if not show_all and len(x_d) > mp:
                step = len(x_d) // mp
                x_d = x_d[::step]
                y_o = y_o[::step]
                d = d[::step]

            pair_color = DIFF_COLORS[pair_idx % len(DIFF_COLORS)]
            color_other, width_other = _style(gs_other, pair_color)

            # Plot other series
            self._plot_widget.plot(
                x_d,
                y_o,
                pen=pg.mkPen(color_other, width=width_other),
                name=f"{gs_other.name}: {y_col_other}",
            )

            # Diff shaded area
            zeros = np.zeros_like(d)
            diff_pen_color = pg.mkColor(pair_color)
            diff_pen_color.setAlpha(180)
            fill = pg.FillBetweenItem(
                pg.PlotCurveItem(x_d, d, pen=pg.mkPen(diff_pen_color, width=1)),
                pg.PlotCurveItem(x_d, zeros, pen=pg.mkPen(None)),
                brush=pg.mkBrush(
                    diff_pen_color.red(),
                    diff_pen_color.green(),
                    diff_pen_color.blue(),
                    40,
                ),
            )
            self._plot_widget.addItem(fill)

            if self._diff_mode == "percent":
                all_stats.append(
                    f"[{gs_other.name}] Mean: {result['mean_diff']:.2f}% | "
                    f"Max: {result['max_diff']:.2f}% | RMSE: {result['rmse']:.2f}%"
                )
            else:
                all_stats.append(
                    f"[{gs_other.name}] Mean: {result['mean_diff']:.4f} | "
                    f"Max: {result['max_diff']:.4f} | RMSE: {result['rmse']:.4f}"
                )

        # Stats bar
        if self._stats_label is not None:
            if all_stats:
                self._stats_label.setText("  ·  ".join(all_stats))
            else:
                self._stats_label.setText("Mean Diff: — | Max Diff: — | RMSE: —")
