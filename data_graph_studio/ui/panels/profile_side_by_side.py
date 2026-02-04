"""
ProfileSideBySideLayout — Side-by-side layout for comparing profiles
within the same dataset.

Uses MiniGraphWidget with graph_setting parameter and ViewSyncManager
for pan/zoom/selection synchronization.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSplitter, QCheckBox, QPushButton, QGridLayout,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QShortcut, QKeySequence

from .side_by_side_layout import MiniGraphWidget
from ...core.view_sync import ViewSyncManager

if TYPE_CHECKING:
    from ...core.data_engine import DataEngine
    from ...core.state import AppState
    from ...core.profile_store import ProfileStore


class ProfileSideBySideLayout(QWidget):
    """Side-by-side layout for comparing profiles within the same dataset."""

    profile_activated = Signal(str)  # profile_id
    exit_requested = Signal()  # FR-9

    MAX_PANELS = 4

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

        self._panels: Dict[str, MiniGraphWidget] = {}
        self._profile_ids: List[str] = []

        # ViewSyncManager with defaults: X=on, Y=off, Selection=on
        self._view_sync_manager = ViewSyncManager(parent=self)
        self._view_sync_manager.sync_x = True
        self._view_sync_manager.sync_y = False
        self._view_sync_manager.sync_selection = True

        # Grid layout mode: "row" | "column" | "grid"
        self._current_grid_layout: str = "row"

        # Splitter / grid references
        self._splitter: Optional[QSplitter] = None
        self._grid_container: Optional[QWidget] = None
        self._content_layout: Optional[QVBoxLayout] = None
        self._header_labels: Dict[str, QLabel] = {}

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header: "Profile Comparison (Side-by-Side) [✕ Exit]"
        header = QFrame()
        header.setStyleSheet("background-color: #2c3e50; border-radius: 4px;")
        header.setFixedHeight(36)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("Profile Comparison (Side-by-Side)")
        title.setStyleSheet("color: white; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        exit_btn = QPushButton("✕ Exit")
        exit_btn.setFixedWidth(60)
        exit_btn.setStyleSheet(
            "QPushButton { color: white; background: #c0392b; border: none; "
            "border-radius: 3px; padding: 2px 6px; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        exit_btn.setToolTip("Exit side-by-side comparison view")
        exit_btn.clicked.connect(self.exit_requested.emit)
        header_layout.addWidget(exit_btn)

        layout.addWidget(header)

        # NOTE: Sync controls moved to CompareToolbar.
        # No inline sync checkboxes here.

        # Content area — will hold splitter or grid
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._content_layout, 1)

        # Esc shortcut (FR-9)
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self.exit_requested.emit)

    # ------------------------------------------------------------------
    # Toolbar integration — sync & grid layout
    # ------------------------------------------------------------------

    def set_sync_option(self, key: str, enabled: bool) -> None:
        """Set a sync option from the CompareToolbar.

        Keys: "x", "y", "selection".
        X sync controls X-axis panning and zoom synchronization.
        Y sync controls Y-axis panning and zoom synchronization.
        """
        if key == "x":
            self._view_sync_manager.sync_x = enabled
        elif key == "y":
            self._view_sync_manager.sync_y = enabled
        elif key == "selection":
            self._view_sync_manager.sync_selection = enabled

    def get_sync_options(self) -> dict:
        """Return current sync option states."""
        return {
            "x": self._view_sync_manager.sync_x,
            "y": self._view_sync_manager.sync_y,
            "selection": self._view_sync_manager.sync_selection,
        }

    def set_grid_layout(self, layout: str) -> None:
        """Switch panel arrangement: 'row', 'column', or 'grid'."""
        if not self._panels:
            return
        self._current_grid_layout = layout
        self._rearrange_panels()

    def reset_all_views(self) -> None:
        """Reset all panel views to auto-range."""
        self._view_sync_manager.reset_all_views()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_profiles(self, profile_ids: List[str]) -> None:
        """Set which profiles to compare (creates panels)."""
        self._profile_ids = list(profile_ids[: self.MAX_PANELS])
        self._rebuild_panels()

    def refresh(self) -> None:
        """Refresh all panels."""
        for panel in self._panels.values():
            try:
                panel.refresh()
            except Exception:
                pass

    def on_profile_deleted(self, profile_id: str) -> None:
        """FR-10: remove panel, exit if <2 remain."""
        if profile_id not in self._panels:
            return

        # Unregister from sync manager
        self._view_sync_manager.unregister_panel(profile_id)

        # Remove widget
        panel = self._panels.pop(profile_id)
        panel.setParent(None)
        panel.deleteLater()

        # Remove from id list
        if profile_id in self._profile_ids:
            self._profile_ids.remove(profile_id)

        # Remove header label
        self._header_labels.pop(profile_id, None)

        # If <2 remain, exit comparison
        if len(self._panels) < 2:
            self.exit_requested.emit()

    def on_profile_renamed(self, profile_id: str, new_name: str) -> None:
        """FR-10: update header label for renamed profile."""
        label = self._header_labels.get(profile_id)
        if label is not None:
            label.setText(new_name)

    # ------------------------------------------------------------------
    # Internal panel management
    # ------------------------------------------------------------------

    def _rebuild_panels(self) -> None:
        """Clear and recreate all panels."""
        # Clear existing
        self._view_sync_manager.clear()
        for panel in self._panels.values():
            panel.setParent(None)
            panel.deleteLater()
        self._panels.clear()
        self._header_labels.clear()

        # Remove old content widget
        self._clear_content_widgets()

        if not self._profile_ids:
            return

        # Create panels
        for pid in self._profile_ids:
            gs = self.store.get(pid)
            if gs is None:
                continue

            panel = MiniGraphWidget(
                self.dataset_id, self.engine, self.state,
                graph_setting=gs,
            )
            panel.activated.connect(lambda did, _pid=pid: self.profile_activated.emit(_pid))
            panel.view_range_changed.connect(
                lambda src_id, xr, yr, _pid=pid: self._view_sync_manager.on_source_range_changed(_pid, xr, yr)
            )
            # Route selection_changed through ViewSyncManager
            panel.selection_changed.connect(
                lambda src_id, region, _pid=pid: self._view_sync_manager.on_source_selection_changed(_pid, region)
            )
            self._panels[pid] = panel
            self._view_sync_manager.register_panel(pid, panel)

        # Arrange panels according to current grid layout
        self._rearrange_panels()

    def _clear_content_widgets(self) -> None:
        """Remove old splitter / grid container from content layout."""
        if self._splitter is not None:
            self._splitter.setParent(None)
            self._splitter.deleteLater()
            self._splitter = None
        if self._grid_container is not None:
            self._grid_container.setParent(None)
            self._grid_container.deleteLater()
            self._grid_container = None

    def _rearrange_panels(self) -> None:
        """Rearrange existing panels according to self._current_grid_layout.

        Supports: "row" (horizontal splitter), "column" (vertical splitter),
        "grid" (2×2 QGridLayout).
        """
        if not self._panels:
            return

        # Detach panels from any current container (without deleting them)
        for panel in self._panels.values():
            panel.setParent(None)

        # Remove old container
        self._clear_content_widgets()

        panel_list = [self._panels[pid] for pid in self._profile_ids if pid in self._panels]

        if self._current_grid_layout == "grid":
            # 2×2 QGridLayout
            self._grid_container = QWidget()
            grid = QGridLayout(self._grid_container)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(2)
            for i, panel in enumerate(panel_list):
                row = i // 2
                col = i % 2
                grid.addWidget(panel, row, col)
            self._content_layout.addWidget(self._grid_container, 1)

        elif self._current_grid_layout == "column":
            # Vertical splitter
            self._splitter = QSplitter(Qt.Vertical)
            for panel in panel_list:
                self._splitter.addWidget(panel)
            if self._splitter.count() > 0:
                h = max(self.height(), 600)
                sizes = [h // self._splitter.count()] * self._splitter.count()
                self._splitter.setSizes(sizes)
            self._content_layout.addWidget(self._splitter, 1)

        else:
            # Default: "row" — horizontal splitter
            self._splitter = QSplitter(Qt.Horizontal)
            for panel in panel_list:
                self._splitter.addWidget(panel)
            if self._splitter.count() > 0:
                w = max(self.width(), 800)
                sizes = [w // self._splitter.count()] * self._splitter.count()
                self._splitter.setSizes(sizes)
            self._content_layout.addWidget(self._splitter, 1)
