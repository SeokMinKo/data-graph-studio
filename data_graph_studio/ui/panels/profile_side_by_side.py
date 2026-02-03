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

        # Sync bar: [☑X축 ☐Y축 ☑Selection] [Reset All]
        sync_frame = QFrame()
        sync_frame.setObjectName("syncOptionsFrame")
        sync_layout = QHBoxLayout(sync_frame)
        sync_layout.setContentsMargins(8, 4, 8, 4)

        sync_layout.addWidget(QLabel("Sync:"))

        self._sync_x_cb = QCheckBox("X축")
        self._sync_x_cb.setChecked(True)
        self._sync_x_cb.setToolTip("Synchronize X-axis panning across panels")
        self._sync_x_cb.stateChanged.connect(self._on_sync_x_changed)
        sync_layout.addWidget(self._sync_x_cb)

        self._sync_y_cb = QCheckBox("Y축")
        self._sync_y_cb.setChecked(False)
        self._sync_y_cb.setToolTip("Synchronize Y-axis zoom across panels")
        self._sync_y_cb.stateChanged.connect(self._on_sync_y_changed)
        sync_layout.addWidget(self._sync_y_cb)

        self._sync_sel_cb = QCheckBox("Selection")
        self._sync_sel_cb.setChecked(True)
        self._sync_sel_cb.setToolTip("Synchronize data selection across panels")
        self._sync_sel_cb.stateChanged.connect(self._on_sync_sel_changed)
        sync_layout.addWidget(self._sync_sel_cb)

        sync_layout.addStretch()

        reset_btn = QPushButton("Reset All")
        reset_btn.setFixedWidth(80)
        reset_btn.setToolTip("Reset view to fit all data")
        reset_btn.clicked.connect(self._on_reset_all)
        sync_layout.addWidget(reset_btn)

        layout.addWidget(sync_frame)

        # Content area — will hold splitter or grid
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._content_layout, 1)

        # Esc shortcut (FR-9)
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self.exit_requested.emit)

    # ------------------------------------------------------------------
    # Sync checkbox handlers
    # ------------------------------------------------------------------

    def _on_sync_x_changed(self, checkbox_state):
        checked = checkbox_state == Qt.Checked.value if isinstance(checkbox_state, int) else checkbox_state == Qt.Checked
        self._view_sync_manager.sync_x = checked

    def _on_sync_y_changed(self, checkbox_state):
        checked = checkbox_state == Qt.Checked.value if isinstance(checkbox_state, int) else checkbox_state == Qt.Checked
        self._view_sync_manager.sync_y = checked

    def _on_sync_sel_changed(self, checkbox_state):
        checked = checkbox_state == Qt.Checked.value if isinstance(checkbox_state, int) else checkbox_state == Qt.Checked
        self._view_sync_manager.sync_selection = checked

    def _on_reset_all(self):
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
        if self._splitter is not None:
            self._splitter.setParent(None)
            self._splitter.deleteLater()
            self._splitter = None
        if self._grid_container is not None:
            self._grid_container.setParent(None)
            self._grid_container.deleteLater()
            self._grid_container = None

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
            self._panels[pid] = panel
            self._view_sync_manager.register_panel(pid, panel)

        # Layout: splitter (horizontal) by default
        self._splitter = QSplitter(Qt.Horizontal)
        for pid in self._profile_ids:
            panel = self._panels.get(pid)
            if panel is not None:
                self._splitter.addWidget(panel)

        # Equal sizes
        if self._splitter.count() > 0:
            w = max(self.width(), 800)
            sizes = [w // self._splitter.count()] * self._splitter.count()
            self._splitter.setSizes(sizes)

        self._content_layout.addWidget(self._splitter, 1)
