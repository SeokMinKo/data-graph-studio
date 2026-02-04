"""
CommandPaletteDialog — VS Code-style Command Palette for feature search

Indexes all menu actions, chart types, panel toggles, and shortcuts.
Opened via Ctrl+Shift+P or F1.
"""

from typing import Optional, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QWidget, QLabel, QHBoxLayout,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QFont


class CommandEntry:
    """A single command palette entry."""
    __slots__ = ('label', 'shortcut', 'action')

    def __init__(self, label: str, shortcut: str, action: QAction):
        self.label = label        # Display text, e.g. "File > Open Data..."
        self.shortcut = shortcut  # Human-readable shortcut, e.g. "Ctrl+O"
        self.action = action      # The QAction to trigger


class CommandPaletteDialog(QDialog):
    """
    Command Palette — search and execute any feature.

    ┌──────────────────────────────────┐
    │  🔍  Type to search...           │
    ├──────────────────────────────────┤
    │  File > Open Data...    Ctrl+O   │
    │  File > Save Data       Ctrl+S   │
    │  View > Theme > Dark             │
    │  Graph > Chart Type > Line       │
    │  ...                             │
    └──────────────────────────────────┘
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._entries: List[CommandEntry] = []
        self._filtered: List[CommandEntry] = []
        self._setup_ui()
        self._build_index()
        self._filter_entries("")

    # ── UI Setup ──────────────────────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle("Command Palette")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setMinimumWidth(560)
        self.setMaximumWidth(700)
        self.setMinimumHeight(100)
        self.resize(620, 420)

        # Position at top-center of parent
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + 80
            self.move(x, y)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("  🔍  Type to search features...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setStyleSheet("""
            QLineEdit {
                font-size: 15px;
                padding: 10px 12px;
                border: none;
                border-bottom: 1px solid #3A3F4B;
                background: #1E222A;
                color: #E0E0E0;
            }
            QLineEdit:focus {
                border-bottom: 2px solid #4FC3F7;
            }
        """)
        self._search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_input)

        # Results list
        self._result_list = QListWidget()
        self._result_list.setStyleSheet("""
            QListWidget {
                border: none;
                background: #1E222A;
                color: #E0E0E0;
                font-size: 13px;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 14px;
                border: none;
            }
            QListWidget::item:selected {
                background: #2D3340;
                color: #FFFFFF;
            }
            QListWidget::item:hover {
                background: #262B36;
            }
        """)
        self._result_list.itemActivated.connect(self._on_item_activated)
        self._result_list.itemDoubleClicked.connect(self._on_item_activated)
        layout.addWidget(self._result_list)

        # Dialog styling
        self.setStyleSheet("""
            QDialog {
                background: #1E222A;
                border: 1px solid #3A3F4B;
                border-radius: 8px;
            }
        """)

        # Focus search on open
        self._search_input.setFocus()

    # ── Index Building ────────────────────────────────────────────

    def _build_index(self):
        """Walk all menu actions from the parent main window and index them."""
        self._entries.clear()
        main_window = self.parent()
        if main_window is None:
            return

        menubar = main_window.menuBar()
        if menubar is None:
            return

        # Walk all menus recursively
        for menu_action in menubar.actions():
            menu = menu_action.menu()
            if menu is None:
                continue
            menu_title = menu_action.text().replace("&", "")
            self._walk_menu(menu, prefix=menu_title)

    def _walk_menu(self, menu, prefix: str = ""):
        """Recursively walk a QMenu and collect all actions."""
        for action in menu.actions():
            if action.isSeparator():
                continue

            submenu = action.menu()
            if submenu is not None:
                sub_title = action.text().replace("&", "")
                self._walk_menu(submenu, prefix=f"{prefix} > {sub_title}")
                continue

            # It's a leaf action
            text = action.text().replace("&", "").strip()
            if not text:
                continue

            shortcut = action.shortcut().toString() if action.shortcut() else ""
            label = f"{prefix} > {text}" if prefix else text
            self._entries.append(CommandEntry(label=label, shortcut=shortcut, action=action))

    # ── Filtering ─────────────────────────────────────────────────

    def _on_search_changed(self, text: str):
        self._filter_entries(text)

    def _filter_entries(self, query: str):
        """Filter entries by query (case-insensitive contains match)."""
        query_lower = query.lower().strip()

        if not query_lower:
            self._filtered = list(self._entries)
        else:
            # Split query into tokens for multi-word matching
            tokens = query_lower.split()
            self._filtered = [
                entry for entry in self._entries
                if all(token in entry.label.lower() or token in entry.shortcut.lower()
                       for token in tokens)
            ]

        self._update_list()

    def _update_list(self):
        """Rebuild the list widget from filtered entries."""
        self._result_list.clear()

        for entry in self._filtered:
            item = QListWidgetItem()

            # Build display text with shortcut hint
            display = entry.label
            if entry.shortcut:
                display = f"{entry.label}"

            item.setText(display)
            item.setData(Qt.UserRole, entry)

            # Show shortcut as tooltip
            if entry.shortcut:
                item.setToolTip(f"Shortcut: {entry.shortcut}")

            self._result_list.addItem(item)

        # Custom paint: add shortcut text to the right side
        for i in range(self._result_list.count()):
            item = self._result_list.item(i)
            entry = item.data(Qt.UserRole)
            if entry and entry.shortcut:
                # Use display with padded shortcut
                item.setText(f"{entry.label}    [{entry.shortcut}]")

        # Select first item
        if self._result_list.count() > 0:
            self._result_list.setCurrentRow(0)

        # Adjust height dynamically
        item_count = min(self._result_list.count(), 12)
        list_height = max(item_count * 30, 60)
        self._result_list.setFixedHeight(list_height)
        self.adjustSize()

    # ── Execution ─────────────────────────────────────────────────

    def _on_item_activated(self, item: QListWidgetItem):
        """Trigger the action associated with the selected item."""
        entry = item.data(Qt.UserRole)
        if entry and entry.action:
            self.accept()
            entry.action.trigger()

    # ── Keyboard Navigation ───────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_Escape:
            self.reject()
            return

        if key in (Qt.Key_Return, Qt.Key_Enter):
            current = self._result_list.currentItem()
            if current:
                self._on_item_activated(current)
            return

        if key == Qt.Key_Down:
            row = self._result_list.currentRow()
            if row < self._result_list.count() - 1:
                self._result_list.setCurrentRow(row + 1)
            return

        if key == Qt.Key_Up:
            row = self._result_list.currentRow()
            if row > 0:
                self._result_list.setCurrentRow(row - 1)
            return

        super().keyPressEvent(event)
