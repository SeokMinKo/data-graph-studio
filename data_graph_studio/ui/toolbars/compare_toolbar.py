"""
CompareToolbar — Dedicated toolbar for profile comparison mode.

Provides:
  - Grid layout selector: Row | Column | 2×2
  - Sync toggle buttons: X | Y | Zoom | Selection
  - Exit Compare button

Signals:
  - grid_layout_changed(str)  — "row", "column", or "grid"
  - sync_changed(str, bool)   — ("x"|"y"|"zoom"|"selection", checked)
  - exit_requested()
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import (
    QToolBar, QToolButton, QPushButton, QWidget, QLabel,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QActionGroup


class CompareToolbar(QToolBar):
    """Toolbar for compare side-by-side mode controls."""

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
        self._sync_buttons: Dict[str, QPushButton] = {}
        self._current_grid = "row"

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # --- Grid Layout section ---
        grid_label = QLabel("  Layout: ")
        grid_label.setObjectName("toolbarLabel")
        self.addWidget(grid_label)

        grid_group = QActionGroup(self)
        grid_group.setExclusive(True)

        grid_options = [
            ("row", "☰ Row", "Horizontal side-by-side layout"),
            ("column", "☷ Column", "Vertical stacked layout"),
            ("grid", "⊞ 2×2", "2×2 grid layout"),
        ]

        for key, text, tooltip in grid_options:
            action = QAction(text, self)
            action.setToolTip(tooltip)
            action.setCheckable(True)
            action.setData(key)
            grid_group.addAction(action)
            self.addAction(action)
            self._grid_actions[key] = action

        # Default: row
        self._grid_actions["row"].setChecked(True)
        grid_group.triggered.connect(self._on_grid_action_triggered)

        self.addSeparator()

        # --- Sync section ---
        sync_label = QLabel("  Sync: ")
        sync_label.setObjectName("toolbarLabel")
        self.addWidget(sync_label)

        sync_options = [
            ("x", "X", "Synchronize X-axis panning"),
            ("y", "Y", "Synchronize Y-axis panning"),
            ("zoom", "Zoom", "Synchronize zoom level"),
            ("selection", "Sel", "Synchronize data selection"),
        ]

        for key, text, tooltip in sync_options:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(self._DEFAULT_SYNC.get(key, False))
            btn.setToolTip(tooltip)
            btn.setFixedHeight(24)
            btn.setMinimumWidth(36)
            btn.setStyleSheet(
                "QPushButton { padding: 2px 6px; border: 1px solid #555; "
                "border-radius: 3px; }"
                "QPushButton:checked { background-color: #2980b9; color: white; "
                "border-color: #2980b9; }"
            )
            btn.toggled.connect(lambda checked, k=key: self._on_sync_toggled(k, checked))
            self.addWidget(btn)
            self._sync_buttons[key] = btn

        self.addSeparator()

        # --- Spacer ---
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(spacer)

        # --- Exit button ---
        exit_btn = QPushButton("✕ Exit Compare")
        exit_btn.setToolTip("Exit comparison mode (Esc)")
        exit_btn.setFixedHeight(26)
        exit_btn.setStyleSheet(
            "QPushButton { color: white; background: #c0392b; border: none; "
            "border-radius: 3px; padding: 2px 10px; font-weight: bold; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        exit_btn.clicked.connect(self.exit_requested.emit)
        self.addWidget(exit_btn)

        # Trailing space
        trail = QLabel("  ")
        self.addWidget(trail)

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
