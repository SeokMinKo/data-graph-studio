"""
ToolbarCustomizeDialog - Configure toolbar group visibility and order.

┌──────────────────────────────────────────────┐
│ Customize Toolbars                      [x]  │
│──────────────────────────────────────────────│
│  Toolbar / Group             Visible         │
│  ▼ Main Toolbar                              │
│    ☑ File                    [▲] [▼]         │
│    ☑ Navigation              [▲] [▼]         │
│    ☑ Drawing                 [▲] [▼]         │
│    ☑ Chart Types             [▲] [▼]         │
│  ▼ Secondary Toolbar                         │
│    ☑ Streaming               [▲] [▼]         │
│    ☑ View Controls           [▲] [▼]         │
│    ☑ Quick Actions           [▲] [▼]         │
│──────────────────────────────────────────────│
│  [Reset Defaults]           [Cancel] [Apply] │
└──────────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import Optional, Dict, TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QHeaderView,
    QLabel,
    QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

if TYPE_CHECKING:
    from ..toolbars.toolbar_manager import ToolbarManager


class ToolbarCustomizeDialog(QDialog):
    """Dialog for customizing toolbar group visibility and order."""

    def __init__(
        self,
        manager: ToolbarManager,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._manager = manager
        self._result: Dict = {"groups": {}}
        self._group_items: Dict[str, QTreeWidgetItem] = {}
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        self.setWindowTitle("Customize Toolbars")
        self.setObjectName("toolbarCustomizeDialog")
        self.setMinimumSize(500, 400)
        self.resize(550, 500)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("Customize Toolbars")
        header_font = QFont()
        header_font.setPointSize(14)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        info = QLabel(
            "Toggle group visibility with checkboxes. "
            "Use the arrow buttons to reorder groups within a toolbar."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Group", ""])
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(20)
        self._tree.setColumnCount(2)
        header_view = self._tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.Fixed)
        header_view.resizeSection(1, 80)
        layout.addWidget(self._tree)

        # Button layout
        btn_layout = QHBoxLayout()

        reset_btn = QPushButton("Reset Defaults")
        reset_btn.clicked.connect(self._on_reset)
        btn_layout.addWidget(reset_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _populate(self):
        """Populate tree from manager's toolbar registry."""
        self._tree.clear()
        self._group_items.clear()

        for toolbar_id, info in self._manager._toolbars.items():
            # Create toolbar category node
            toolbar_item = QTreeWidgetItem(self._tree)
            toolbar_item.setText(0, info.display_name)
            toolbar_item.setFlags(toolbar_item.flags() & ~Qt.ItemIsUserCheckable)
            font = toolbar_item.font(0)
            font.setBold(True)
            toolbar_item.setFont(0, font)
            toolbar_item.setExpanded(True)

            # Sort groups by current order
            sorted_groups = sorted(info.groups, key=lambda g: g.order)

            for group in sorted_groups:
                group_item = QTreeWidgetItem(toolbar_item)
                group_item.setText(0, group.label)
                group_item.setCheckState(
                    0, Qt.Checked if group.visible else Qt.Unchecked
                )
                group_item.setData(0, Qt.UserRole, group.id)
                group_item.setData(0, Qt.UserRole + 1, toolbar_id)
                self._group_items[group.id] = group_item

                # Reorder buttons widget
                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(2, 0, 2, 0)
                btn_layout.setSpacing(2)

                up_btn = QPushButton("▲")
                up_btn.setFixedSize(28, 22)
                up_btn.setToolTip("Move Up")
                up_btn.clicked.connect(
                    lambda checked, gid=group.id: self._move_group(gid, -1)
                )
                btn_layout.addWidget(up_btn)

                down_btn = QPushButton("▼")
                down_btn.setFixedSize(28, 22)
                down_btn.setToolTip("Move Down")
                down_btn.clicked.connect(
                    lambda checked, gid=group.id: self._move_group(gid, 1)
                )
                btn_layout.addWidget(down_btn)

                self._tree.setItemWidget(group_item, 1, btn_widget)

    def _move_group(self, group_id: str, direction: int):
        """Move a group up (-1) or down (+1) within its toolbar."""
        item = self._group_items.get(group_id)
        if item is None:
            return

        parent = item.parent()
        if parent is None:
            return

        index = parent.indexOfChild(item)
        new_index = index + direction

        if new_index < 0 or new_index >= parent.childCount():
            return

        # Swap in tree
        parent.takeChild(index)
        parent.insertChild(new_index, item)

        # Re-add widget (takeChild destroys it)
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(2, 0, 2, 0)
        btn_layout.setSpacing(2)

        up_btn = QPushButton("▲")
        up_btn.setFixedSize(28, 22)
        up_btn.setToolTip("Move Up")
        up_btn.clicked.connect(lambda checked, gid=group_id: self._move_group(gid, -1))
        btn_layout.addWidget(up_btn)

        down_btn = QPushButton("▼")
        down_btn.setFixedSize(28, 22)
        down_btn.setToolTip("Move Down")
        down_btn.clicked.connect(lambda checked, gid=group_id: self._move_group(gid, 1))
        btn_layout.addWidget(down_btn)

        self._tree.setItemWidget(item, 1, btn_widget)

        # Keep item selected
        self._tree.setCurrentItem(item)

    def _on_reset(self):
        """Reset to default visibility and order."""
        self._manager.reset_to_defaults()
        self._populate()

    def _on_apply(self):
        """Build result dict and accept dialog."""
        result = {"groups": {}}

        # Walk the tree to capture current order and visibility
        for i in range(self._tree.topLevelItemCount()):
            toolbar_item = self._tree.topLevelItem(i)
            for j in range(toolbar_item.childCount()):
                group_item = toolbar_item.child(j)
                group_id = group_item.data(0, Qt.UserRole)
                visible = group_item.checkState(0) == Qt.Checked
                result["groups"][group_id] = {
                    "visible": visible,
                    "order": j,
                }

        self._result = result
        self.accept()

    def get_result(self) -> dict:
        """Return customization result dict."""
        return self._result
