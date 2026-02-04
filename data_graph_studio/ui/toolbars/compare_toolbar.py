"""
CompareToolbar — Dedicated toolbar for profile comparison mode.

Provides (two-row layout):
  Row 1: Grid layout selector (Row | Column | 2×2) + Exit Compare button
  Row 2: Sync checkboxes (X-axis | Y-axis | Zoom | Selection)

Signals:
  - grid_layout_changed(str)  — "row", "column", or "grid"
  - sync_changed(str, bool)   — ("x"|"y"|"zoom"|"selection", checked)
  - exit_requested()
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import (
    QToolBar, QToolButton, QPushButton, QWidget, QLabel,
    QSizePolicy, QHBoxLayout, QVBoxLayout, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QActionGroup


class CompareToolbar(QToolBar):
    """Toolbar for compare side-by-side mode controls (two-row layout)."""

    grid_layout_changed = Signal(str)   # "row" | "column" | "grid"
    sync_changed = Signal(str, bool)    # key, checked
    exit_requested = Signal()

    # Default sync states
    _DEFAULT_SYNC = {
        "x": True,
        "y": False,
        "zoom": False,
        "selection": True,
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Compare Toolbar", parent)
        self.setObjectName("compareToolbar")
        self.setMovable(False)
        self.setIconSize(QSize(16, 16))

        self._grid_actions: Dict[str, QAction] = {}
        self._sync_buttons: Dict[str, QCheckBox] = {}
        self._current_grid = "row"

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Use a custom widget with two-row layout inside the toolbar
        container = QWidget()
        container.setObjectName("compareToolbarContainer")
        two_row_layout = QVBoxLayout(container)
        two_row_layout.setContentsMargins(4, 2, 4, 2)
        two_row_layout.setSpacing(2)

        # === Row 1: Layout options + Exit button ===
        row1 = QWidget()
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(4)

        grid_label = QLabel("Layout:")
        grid_label.setObjectName("toolbarLabel")
        row1_layout.addWidget(grid_label)

        grid_group = QActionGroup(self)
        grid_group.setExclusive(True)

        grid_options = [
            ("row", "☰ Row", "Horizontal side-by-side layout"),
            ("column", "☷ Column", "Vertical stacked layout"),
            ("grid", "⊞ 2×2", "2×2 grid layout"),
        ]

        for key, text, tooltip in grid_options:
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setMinimumWidth(60)
            btn.setStyleSheet(
                "QToolButton { padding: 2px 8px; border: 1px solid #555; "
                "border-radius: 3px; }"
                "QToolButton:checked { background-color: #2980b9; color: white; "
                "border-color: #2980b9; }"
            )
            action = QAction(text, self)
            action.setToolTip(tooltip)
            action.setCheckable(True)
            action.setData(key)
            grid_group.addAction(action)
            btn.setDefaultAction(action)
            row1_layout.addWidget(btn)
            self._grid_actions[key] = action

        # Default: row
        self._grid_actions["row"].setChecked(True)
        grid_group.triggered.connect(self._on_grid_action_triggered)

        row1_layout.addStretch()

        # Exit button
        exit_btn = QPushButton("✕ Exit Compare")
        exit_btn.setToolTip("Exit comparison mode (Esc)")
        exit_btn.setFixedHeight(24)
        exit_btn.setStyleSheet(
            "QPushButton { color: white; background: #c0392b; border: none; "
            "border-radius: 3px; padding: 2px 10px; font-weight: bold; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        exit_btn.clicked.connect(self.exit_requested.emit)
        row1_layout.addWidget(exit_btn)

        two_row_layout.addWidget(row1)

        # === Row 2: Sync checkboxes ===
        row2 = QWidget()
        row2_layout = QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(8)

        sync_label = QLabel("Sync:")
        sync_label.setObjectName("toolbarLabel")
        row2_layout.addWidget(sync_label)

        sync_options = [
            ("x", "X-axis", "Synchronize X-axis panning"),
            ("y", "Y-axis", "Synchronize Y-axis panning"),
            ("zoom", "Zoom", "Synchronize zoom level"),
            ("selection", "Selection", "Synchronize data selection"),
        ]

        for key, text, tooltip in sync_options:
            cb = QCheckBox(text)
            cb.setChecked(self._DEFAULT_SYNC.get(key, False))
            cb.setToolTip(tooltip)
            cb.toggled.connect(lambda checked, k=key: self._on_sync_toggled(k, checked))
            row2_layout.addWidget(cb)
            self._sync_buttons[key] = cb

        row2_layout.addStretch()

        two_row_layout.addWidget(row2)

        self.addWidget(container)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_grid_action_triggered(self, action: QAction) -> None:
        key = action.data()
        if key and key != self._current_grid:
            self._current_grid = key
            self.grid_layout_changed.emit(key)

    def _on_sync_toggled(self, key: str, checked: bool) -> None:
        self.sync_changed.emit(key, checked)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_sync_state(self, key: str, checked: bool) -> None:
        """Programmatically set a sync toggle state."""
        btn = self._sync_buttons.get(key)
        if btn is not None:
            btn.setChecked(checked)

    def set_grid_layout(self, layout: str) -> None:
        """Programmatically select a grid layout."""
        action = self._grid_actions.get(layout)
        if action is not None:
            action.setChecked(True)
            self._current_grid = layout

    def sync_state(self) -> Dict[str, bool]:
        """Return current sync toggle states."""
        return {key: btn.isChecked() for key, btn in self._sync_buttons.items()}

    def grid_layout(self) -> str:
        """Return current grid layout key."""
        return self._current_grid

    def reset_to_defaults(self) -> None:
        """Reset all controls to default states."""
        self.set_grid_layout("row")
        for key, default in self._DEFAULT_SYNC.items():
            self.set_sync_state(key, default)
