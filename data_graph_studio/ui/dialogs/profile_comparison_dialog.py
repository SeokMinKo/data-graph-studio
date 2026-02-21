"""ProfileComparisonDialog — lets the user select profiles and comparison mode."""

from __future__ import annotations

from typing import List, TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QComboBox, QDialogButtonBox,
    QGroupBox, QAbstractItemView,
)
from PySide6.QtCore import Qt

from ...core.state import ComparisonMode
from ..panels.profile_overlay import ProfileOverlayRenderer
from ..panels.profile_difference import ProfileDifferenceRenderer

if TYPE_CHECKING:
    from ...core.profile import GraphSetting


class ProfileComparisonDialog(QDialog):
    """Dialog to select profiles and comparison mode."""

    def __init__(
        self,
        profiles: List["GraphSetting"],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Profile Comparison")
        self.setMinimumSize(400, 350)

        self._profiles = profiles
        self._selected_ids: List[str] = []
        self._selected_mode: ComparisonMode = ComparisonMode.SIDE_BY_SIDE

        self._setup_ui()
        self._update_mode_availability()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Profile list with checkboxes
        grp = QGroupBox("Select Profiles (2 or more)")
        grp_layout = QVBoxLayout(grp)

        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        for gs in self._profiles:
            item = QListWidgetItem(f"{gs.name}  (X: {gs.x_column or '—'})")
            item.setData(Qt.UserRole, gs.id)
            item.setCheckState(Qt.Unchecked)
            self._list_widget.addItem(item)
        self._list_widget.itemChanged.connect(self._on_item_changed)
        grp_layout.addWidget(self._list_widget)
        layout.addWidget(grp)

        # Mode selector
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Comparison Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.setToolTip("Select how profiles are visually compared")
        self._mode_combo.addItem("Side-by-Side", ComparisonMode.SIDE_BY_SIDE)
        self._mode_combo.addItem("Overlay", ComparisonMode.OVERLAY)
        self._mode_combo.addItem("Difference", ComparisonMode.DIFFERENCE)
        mode_layout.addWidget(self._mode_combo)
        layout.addLayout(mode_layout)

        # Hint label
        self._hint_label = QLabel("")
        self._hint_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._hint_label)

        # Buttons
        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._ok_btn = bbox.button(QDialogButtonBox.Ok)
        self._ok_btn.setText("Compare")
        self._ok_btn.setToolTip("Start profile comparison")
        self._ok_btn.setEnabled(False)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    # ------------------------------------------------------------------
    # Logic
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QListWidgetItem):
        self._update_mode_availability()

    def _checked_profiles(self) -> List["GraphSetting"]:
        checked = []
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item.checkState() == Qt.Checked:
                pid = item.data(Qt.UserRole)
                for gs in self._profiles:
                    if gs.id == pid:
                        checked.append(gs)
                        break
        return checked

    def _update_mode_availability(self):
        checked = self._checked_profiles()
        n = len(checked)

        can_overlay = ProfileOverlayRenderer.can_overlay(checked) if n >= 2 else False
        can_diff = ProfileDifferenceRenderer.can_difference(checked) if n >= 2 else False

        # Side-by-Side: always available when n>=2
        # Overlay: only when same X
        # Difference: only when n==2 and same X
        model = self._mode_combo.model()
        # Item 0 = Side-by-Side
        model.item(0).setEnabled(n >= 2)
        # Item 1 = Overlay
        model.item(1).setEnabled(can_overlay)
        # Item 2 = Difference
        model.item(2).setEnabled(can_diff)

        self._ok_btn.setEnabled(n >= 2)

        # Hints
        if n < 2:
            self._hint_label.setText("Select 2 or more profiles to compare")
        elif not can_overlay:
            self._hint_label.setText("Overlay requires all profiles to share the same X column")
        elif not can_diff and n != 2:
            self._hint_label.setText("Difference requires exactly 2 profiles")
        else:
            self._hint_label.setText("")

    # ------------------------------------------------------------------
    # Result accessors
    # ------------------------------------------------------------------

    @property
    def selected_profile_ids(self) -> List[str]:
        return [gs.id for gs in self._checked_profiles()]

    @property
    def selected_mode(self) -> ComparisonMode:
        return self._mode_combo.currentData()
