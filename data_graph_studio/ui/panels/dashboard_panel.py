"""
Dashboard Panel — PRD v2 Feature 1 (§5.1 / §9.1)

QGridLayout-based dashboard with mini graph cells,
header bar (mode label, preset dropdown, settings gear, close button),
empty-cell placeholders, and focus highlighting.
"""

from __future__ import annotations

from typing import Dict, Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QComboBox, QScrollArea, QSizePolicy,
    QToolButton,
)
from PySide6.QtCore import Qt, Signal, QTimer

from ...core.dashboard_layout import (
    DashboardLayout,
    DashboardCell,
    LAYOUT_PRESETS,
    MIN_CELL_WIDTH,
    MIN_CELL_HEIGHT,
)

if TYPE_CHECKING:
    from ...core.dashboard_controller import DashboardController
    from ...core.state import AppState
    from ...core.data_engine import DataEngine


# ---------------------------------------------------------------------------
# Empty Cell Placeholder
# ---------------------------------------------------------------------------

class _EmptyCellWidget(QFrame):
    """Placeholder for an empty dashboard cell (FR-1.7)."""

    clicked = Signal(int, int)  # row, col

    def __init__(self, row: int, col: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = row
        self._col = col
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(MIN_CELL_WIDTH, MIN_CELL_HEIGHT)
        self.setToolTip("Click to add a chart to this cell")
        self.setStyleSheet(
            "QFrame { border: 2px dashed #888; border-radius: 6px; background: transparent; }"
        )
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus = QLabel("+")
        plus.setStyleSheet("font-size: 32px; color: #888;")
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(plus)
        hint = QLabel("Click to add chart")
        hint.setStyleSheet("font-size: 11px; color: #888;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

    def mousePressEvent(self, event):  # noqa: N802
        self.clicked.emit(self._row, self._col)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Loading Spinner Cell (FR-1.10)
# ---------------------------------------------------------------------------

class _SpinnerCellWidget(QFrame):
    """Temporary spinner shown while chart renders."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(MIN_CELL_WIDTH, MIN_CELL_HEIGHT)
        self.setStyleSheet("QFrame { border: 1px solid #ccc; border-radius: 4px; }")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinner = QLabel("⏳ Loading…")
        spinner.setStyleSheet("font-size: 14px; color: #666;")
        spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(spinner)


# ---------------------------------------------------------------------------
# Dashboard Panel
# ---------------------------------------------------------------------------

class DashboardPanel(QWidget):
    """
    Top-level dashboard panel containing the header bar and grid of cells.

    Signals
    -------
    exit_requested : emitted when user clicks Exit or presses Esc.
    cell_clicked : (row, col) emitted when an empty cell is clicked.
    preset_changed : preset name string emitted on dropdown change.
    """

    exit_requested = Signal()
    cell_clicked = Signal(int, int)
    preset_changed = Signal(str)

    def __init__(
        self,
        controller: DashboardController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._cell_widgets: Dict[str, QWidget] = {}  # "r,c" → widget
        self._focused_cell: tuple[int, int] | None = None

        self._build_ui()

    # -- UI -----------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        root.addWidget(self._build_header())

        # Scrollable grid area (NFR-1.5)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setSpacing(6)
        self._scroll.setWidget(self._grid_container)
        root.addWidget(self._scroll, stretch=1)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet("QFrame { border-bottom: 1px solid #ddd; }")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 2, 8, 2)

        label = QLabel("Dashboard Mode")
        label.setStyleSheet("font-weight: bold;")
        hl.addWidget(label)

        hl.addSpacing(12)

        hl.addWidget(QLabel("Layout:"))
        self._preset_combo = QComboBox()
        self._preset_combo.setToolTip("Select dashboard grid layout preset")
        self._preset_combo.addItems(list(LAYOUT_PRESETS.keys()))
        self._preset_combo.currentTextChanged.connect(self.preset_changed.emit)
        hl.addWidget(self._preset_combo)

        hl.addStretch()

        gear = QToolButton()
        gear.setText("⚙")
        gear.setToolTip("Dashboard settings")
        hl.addWidget(gear)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setToolTip("Exit dashboard (Esc)")
        close_btn.clicked.connect(self.exit_requested.emit)
        hl.addWidget(close_btn)

        return header

    # -- grid population ----------------------------------------------------

    def populate(self, layout: DashboardLayout) -> None:
        """Clear and rebuild the grid from a DashboardLayout."""
        self._clear_grid()

        # Ensure minimum size (FR-1.9)
        min_w, min_h = layout.minimum_window_size()
        self._grid_container.setMinimumSize(min_w, min_h)

        # Track which positions are occupied by spanned cells
        occupied: set[tuple[int, int]] = set()
        for cell in layout.cells:
            for dr in range(cell.row_span):
                for dc in range(cell.col_span):
                    occupied.add((cell.row + dr, cell.col + dc))

            widget = _SpinnerCellWidget()
            widget.setMinimumSize(MIN_CELL_WIDTH * cell.col_span, MIN_CELL_HEIGHT * cell.row_span)
            self._grid.addWidget(widget, cell.row, cell.col, cell.row_span, cell.col_span)
            self._cell_widgets[f"{cell.row},{cell.col}"] = widget

        # Fill remaining positions with empty-cell placeholders
        for r in range(layout.rows):
            for c in range(layout.cols):
                if (r, c) not in occupied:
                    empty = _EmptyCellWidget(r, c)
                    empty.clicked.connect(self.cell_clicked.emit)
                    self._grid.addWidget(empty, r, c)
                    self._cell_widgets[f"{r},{c}"] = empty

    def replace_spinner(self, row: int, col: int, widget: QWidget) -> None:
        """Replace a spinner cell with the real chart widget (FR-1.10)."""
        key = f"{row},{col}"
        old = self._cell_widgets.get(key)
        if old is not None:
            self._grid.removeWidget(old)
            old.deleteLater()
        self._grid.addWidget(widget, row, col)
        self._cell_widgets[key] = widget

    def set_focus_cell(self, row: int, col: int) -> None:
        """Highlight the focused cell with a blue border (§8.1)."""
        # Remove old focus
        if self._focused_cell is not None:
            old_key = f"{self._focused_cell[0]},{self._focused_cell[1]}"
            old_w = self._cell_widgets.get(old_key)
            if old_w is not None:
                old_w.setStyleSheet(old_w.styleSheet().replace("border: 2px solid #3b82f6;", ""))

        key = f"{row},{col}"
        w = self._cell_widgets.get(key)
        if w is not None:
            w.setStyleSheet(w.styleSheet() + " border: 2px solid #3b82f6;")
        self._focused_cell = (row, col)

    # -- cleanup (§10.1, §10.6) -------------------------------------------

    def cleanup(self) -> None:
        """Disconnect signals and schedule widget deletion."""
        self._clear_grid()

    def _clear_grid(self) -> None:
        for w in self._cell_widgets.values():
            self._grid.removeWidget(w)
            w.deleteLater()
        self._cell_widgets.clear()

    # -- keyboard (FR-B1.2) ------------------------------------------------

    def keyPressEvent(self, event):  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.exit_requested.emit()
            return

        layout = self._controller.current_layout if self._controller else None
        if layout is None:
            super().keyPressEvent(event)
            return

        rows, cols = layout.rows, layout.cols
        if rows == 0 or cols == 0:
            super().keyPressEvent(event)
            return

        r, c = self._focused_cell if self._focused_cell else (0, 0)

        if key == Qt.Key.Key_Up:
            r = max(0, r - 1)
        elif key == Qt.Key.Key_Down:
            r = min(rows - 1, r + 1)
        elif key == Qt.Key.Key_Left:
            c = max(0, c - 1)
        elif key == Qt.Key.Key_Right:
            c = min(cols - 1, c + 1)
        elif key == Qt.Key.Key_Tab:
            # Tab: advance to next cell (left-to-right, top-to-bottom)
            c += 1
            if c >= cols:
                c = 0
                r += 1
            if r >= rows:
                r = 0
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Enter: trigger cell click (assign profile)
            self.cell_clicked.emit(r, c)
            return
        else:
            super().keyPressEvent(event)
            return

        self.set_focus_cell(r, c)
