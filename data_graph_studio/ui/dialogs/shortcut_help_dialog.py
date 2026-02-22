"""
ShortcutHelpDialog — FR-7.2: 단축키 도움말 다이얼로그

모든 단축키를 카테고리별로 그룹핑하여 표시.
Cmd+/ 또는 메뉴에서 호출.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton, QHeaderView, QWidget
)
from PySide6.QtGui import QKeySequence, QFont

from ..controllers.shortcut_controller import ShortcutController


class ShortcutHelpDialog(QDialog):
    """
    단축키 도움말 다이얼로그

    PRD §5.6 레이아웃:
    ┌──────────────────────────────────┐
    │ Keyboard Shortcuts          [✕]  │
    │──────────────────────────────────│
    │  Category / Action    Shortcut   │
    │  ─────────────────────────────── │
    │  ▼ File                          │
    │    Open File          Cmd+O      │
    │    Save Profile       Cmd+S      │
    │  ▼ Edit                          │
    │    Undo               Cmd+Z      │
    │    Redo               Cmd+Shift+Z│
    │  ...                             │
    │──────────────────────────────────│
    │                         [Close]  │
    └──────────────────────────────────┘
    """

    def __init__(
        self,
        controller: ShortcutController,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self._controller = controller
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(500, 450)
        self.resize(550, 550)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("Keyboard Shortcuts")
        header_font = QFont()
        header_font.setPointSize(14)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Action", "Shortcut"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(20)

        header_view = self._tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)

        self._populate_tree()
        layout.addWidget(self._tree)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setToolTip("Close shortcut help dialog")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _populate_tree(self):
        """카테고리별로 단축키를 트리에 추가"""
        self._tree.clear()

        categories = self._controller.get_shortcuts_by_category()

        for category_name, shortcuts in categories.items():
            # 카테고리 노드
            category_item = QTreeWidgetItem(self._tree, [category_name, ""])
            category_font = QFont()
            category_font.setBold(True)
            category_item.setFont(0, category_font)
            category_item.setExpanded(True)

            for shortcut in shortcuts:
                keys_str = (
                    shortcut.keys.toString()
                    if isinstance(shortcut.keys, QKeySequence)
                    else str(shortcut.keys)
                )
                # macOS에서 Ctrl → Cmd 표시
                display_keys = keys_str.replace("Ctrl+", "⌘").replace(
                    "Shift+", "⇧"
                ).replace("Alt+", "⌥").replace("Meta+", "⌘")

                item = QTreeWidgetItem(
                    category_item,
                    [shortcut.name, display_keys]
                )
                if shortcut.description:
                    item.setToolTip(0, shortcut.description)
