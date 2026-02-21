"""
Dashboard Panel — PRD v2 Feature 1 (§5.1 / §9.1)

QGridLayout-based dashboard with mini graph cells,
header bar (mode label, preset dropdown, settings gear, close button),
empty-cell placeholders, focus highlighting, drag-and-drop reordering,
custom grid size, dashboard name editing, and multi-dashboard tabs.
"""

from __future__ import annotations

from typing import Dict, Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QComboBox, QScrollArea, QToolButton, QDialog, QSpinBox, QDialogButtonBox, QFormLayout,
    QLineEdit,
)
from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QDrag

from ...core.dashboard_layout import (
    DashboardLayout,
    LAYOUT_PRESETS,
    MIN_CELL_WIDTH,
    MIN_CELL_HEIGHT,
)

if TYPE_CHECKING:
    from ...core.dashboard_controller import DashboardController


# ---------------------------------------------------------------------------
# Drag & Drop mixin
# ---------------------------------------------------------------------------

_MIME_TYPE = "application/x-dgs-dashboard-cell"


class _DragDropCellMixin:
    """Mixin adding drag-and-drop support to dashboard cell widgets."""

    _row: int
    _col: int

    def _init_drag_drop(self):
        self.setAcceptDrops(True)

    def mouseMoveEvent(self, event):  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(_MIME_TYPE, f"{self._row},{self._col}".encode())
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasFormat(_MIME_TYPE):
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        if event.mimeData().hasFormat(_MIME_TYPE):
            src = event.mimeData().data(_MIME_TYPE).data().decode()
            src_row, src_col = (int(x) for x in src.split(","))
            # Find the parent DashboardPanel and request swap
            panel = self._find_dashboard_panel()
            if panel:
                panel.cell_swap_requested.emit(src_row, src_col, self._row, self._col)
            event.acceptProposedAction()

    def _find_dashboard_panel(self) -> Optional[DashboardPanel]:
        w = self.parent()  # type: ignore[attr-defined]
        while w is not None:
            if isinstance(w, DashboardPanel):
                return w
            w = w.parent()
        # Check tab widget parents
        if w is None:
            w = self.parent()  # type: ignore[attr-defined]
            while w is not None:
                if isinstance(w, _DashboardTab):
                    return w._panel_ref
                w = w.parent()
        return None


# ---------------------------------------------------------------------------
# Empty Cell Placeholder
# ---------------------------------------------------------------------------

class _EmptyCellWidget(_DragDropCellMixin, QFrame):
    """Placeholder for an empty dashboard cell (FR-1.7)."""

    clicked = Signal(int, int)  # row, col

    def __init__(self, row: int, col: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = row
        self._col = col
        self._init_drag_drop()
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(MIN_CELL_WIDTH, MIN_CELL_HEIGHT)
        self.setToolTip("Click to add a chart to this cell")
        self.setStyleSheet(
            "QFrame { border: 2px dashed #888; border-radius: 6px; background: transparent; }"
            "QFrame[focused=\"true\"] { border: 2px solid #3b82f6; }"
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

class _SpinnerCellWidget(_DragDropCellMixin, QFrame):
    """Temporary spinner shown while chart renders."""

    def __init__(self, row: int = 0, col: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = row
        self._col = col
        self._init_drag_drop()
        self.setMinimumSize(MIN_CELL_WIDTH, MIN_CELL_HEIGHT)
        self.setStyleSheet(
            "QFrame { border: 1px solid #ccc; border-radius: 4px; }"
            "QFrame[focused=\"true\"] { border: 2px solid #3b82f6; }"
        )
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinner = QLabel("⏳ Loading…")
        spinner.setStyleSheet("font-size: 14px; color: #666;")
        spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(spinner)


# ---------------------------------------------------------------------------
# Grid Size Dialog
# ---------------------------------------------------------------------------

class _GridSizeDialog(QDialog):
    """Dialog for custom grid size input."""

    def __init__(self, current_rows: int = 2, current_cols: int = 2,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Custom Grid Size")
        form = QFormLayout(self)
        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, 10)
        self._rows_spin.setValue(current_rows)
        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(1, 10)
        self._cols_spin.setValue(current_cols)
        form.addRow("Rows:", self._rows_spin)
        form.addRow("Columns:", self._cols_spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @property
    def rows(self) -> int:
        return self._rows_spin.value()

    @property
    def cols(self) -> int:
        return self._cols_spin.value()


# ---------------------------------------------------------------------------
# Cell Edit Dialog
# ---------------------------------------------------------------------------

class _CellEditDialog(QDialog):
    """Simple dialog to edit cell properties (chart type, profile, span)."""

    def __init__(self, row: int, col: int, profiles: list[str] | None = None,
                 current_profile: str = "", row_span: int = 1, col_span: int = 1,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Cell ({row}, {col})")
        form = QFormLayout(self)

        self._profile_combo = QComboBox()
        self._profile_combo.addItem("(none)", "")
        for p in (profiles or []):
            self._profile_combo.addItem(p, p)
        idx = self._profile_combo.findData(current_profile)
        if idx >= 0:
            self._profile_combo.setCurrentIndex(idx)
        form.addRow("Profile:", self._profile_combo)

        self._row_span = QSpinBox()
        self._row_span.setRange(1, 5)
        self._row_span.setValue(row_span)
        form.addRow("Row span:", self._row_span)

        self._col_span = QSpinBox()
        self._col_span.setRange(1, 5)
        self._col_span.setValue(col_span)
        form.addRow("Col span:", self._col_span)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @property
    def profile_id(self) -> str:
        return self._profile_combo.currentData() or ""

    @property
    def row_span(self) -> int:
        return self._row_span.value()

    @property
    def col_span(self) -> int:
        return self._col_span.value()


# ---------------------------------------------------------------------------
# Editable Dashboard Name Label
# ---------------------------------------------------------------------------

class _EditableLabel(QLabel):
    """QLabel that turns into QLineEdit on double-click."""

    name_changed = Signal(str)

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet("font-weight: bold;")
        self._editing = False

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self._start_edit()

    def _start_edit(self):
        if self._editing:
            return
        self._editing = True
        parent_layout = self.parent().layout() if self.parent() else None
        if parent_layout is None:
            self._editing = False
            return

        edit = QLineEdit(self.text(), self.parent())
        edit.setStyleSheet("font-weight: bold;")
        edit.selectAll()

        idx = parent_layout.indexOf(self)
        if idx < 0:
            self._editing = False
            return

        self.hide()
        parent_layout.insertWidget(idx, edit)
        edit.setFocus()

        def _finish():
            new_text = edit.text().strip() or self.text()
            self.setText(new_text)
            parent_layout.removeWidget(edit)
            edit.deleteLater()
            self.show()
            self._editing = False
            self.name_changed.emit(new_text)

        edit.editingFinished.connect(_finish)


# ---------------------------------------------------------------------------
# Dashboard Tab (internal — wraps a single grid for multi-tab)
# ---------------------------------------------------------------------------

class _DashboardTab(QWidget):
    """Single tab holding a scrollable grid."""

    def __init__(self, panel_ref: DashboardPanel, parent: QWidget | None = None):
        super().__init__(parent)
        self._panel_ref = panel_ref
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setSpacing(6)
        self._scroll.setWidget(self._grid_container)
        root.addWidget(self._scroll, stretch=1)


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
    cell_swap_requested : (src_row, src_col, dst_row, dst_col)
    cell_edit_requested : (row, col) emitted when a cell edit is requested.
    grid_size_changed : (rows, cols) emitted on custom grid size.
    name_changed : new dashboard name string.
    """

    exit_requested = Signal()
    cell_clicked = Signal(int, int)
    preset_changed = Signal(str)
    cell_swap_requested = Signal(int, int, int, int)
    cell_edit_requested = Signal(int, int)
    grid_size_changed = Signal(int, int)
    name_changed = Signal(str)

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

        self._name_label = _EditableLabel("Dashboard Mode")
        self._name_label.name_changed.connect(self.name_changed.emit)
        hl.addWidget(self._name_label)

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
        gear.setToolTip("Dashboard settings — custom grid size")
        gear.clicked.connect(self._on_gear_clicked)
        hl.addWidget(gear)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setToolTip("Exit dashboard (Esc)")
        close_btn.clicked.connect(self.exit_requested.emit)
        hl.addWidget(close_btn)

        return header

    def _on_gear_clicked(self) -> None:
        """Open custom grid size dialog (gear button)."""
        layout = self._controller.current_layout if self._controller else None
        rows = layout.rows if layout else 2
        cols = layout.cols if layout else 2
        dlg = _GridSizeDialog(rows, cols, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.grid_size_changed.emit(dlg.rows, dlg.cols)

    # -- grid population ----------------------------------------------------

    def populate(self, layout: DashboardLayout) -> None:
        """Clear and rebuild the grid from a DashboardLayout."""
        self._clear_grid()

        # Update name label
        if layout.name:
            self._name_label.setText(layout.name)

        # Ensure minimum size (FR-1.9)
        min_w, min_h = layout.minimum_window_size()
        self._grid_container.setMinimumSize(min_w, min_h)

        # Track which positions are occupied by spanned cells
        occupied: set[tuple[int, int]] = set()
        for cell in layout.cells:
            for dr in range(cell.row_span):
                for dc in range(cell.col_span):
                    occupied.add((cell.row + dr, cell.col + dc))

            widget = _SpinnerCellWidget(cell.row, cell.col)
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

    def replace_spinner(self, row: int, col: int, widget: QWidget,
                        row_span: int = 1, col_span: int = 1) -> None:
        """Replace a spinner cell with the real chart widget (FR-1.10).

        Preserves span information so merged cells render correctly.
        """
        key = f"{row},{col}"
        old = self._cell_widgets.get(key)
        if old is not None:
            # Try to recover span from the existing grid item
            item = self._grid.itemAtPosition(row, col)
            if item and row_span == 1 and col_span == 1:
                for r in range(self._grid.rowCount()):
                    for c in range(self._grid.columnCount()):
                        gi = self._grid.itemAtPosition(r, c)
                        if gi and gi.widget() is old and (r != row or c != col):
                            row_span = max(row_span, r - row + 1)
                            col_span = max(col_span, c - col + 1)
            self._grid.removeWidget(old)
            old.deleteLater()
        self._grid.addWidget(widget, row, col, row_span, col_span)
        self._cell_widgets[key] = widget

    def set_focus_cell(self, row: int, col: int) -> None:
        """Highlight the focused cell with a blue border (§8.1).

        Uses QSS dynamic property to avoid CSS string accumulation.
        """
        # Remove old focus
        if self._focused_cell is not None:
            old_key = f"{self._focused_cell[0]},{self._focused_cell[1]}"
            old_w = self._cell_widgets.get(old_key)
            if old_w is not None:
                old_w.setProperty("focused", False)
                old_w.style().polish(old_w)

        key = f"{row},{col}"
        w = self._cell_widgets.get(key)
        if w is not None:
            w.setProperty("focused", True)
            w.style().polish(w)
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
            c += 1
            if c >= cols:
                c = 0
                r += 1
            if r >= rows:
                r = 0
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.cell_clicked.emit(r, c)
            return
        else:
            super().keyPressEvent(event)
            return

        self.set_focus_cell(r, c)
