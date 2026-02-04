"""Tests for the Command Palette dialog."""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMainWindow, QMenuBar, QMenu
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt

from data_graph_studio.ui.dialogs.command_palette_dialog import (
    CommandPaletteDialog,
    CommandEntry,
)


@pytest.fixture(scope="module")
def qapp():
    """Ensure a QApplication exists."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def main_window(qapp):
    """Create a minimal main window with menus for testing."""
    win = QMainWindow()
    menubar = win.menuBar()

    # File menu
    file_menu = menubar.addMenu("&File")
    open_action = QAction("&Open Data...", win)
    open_action.setShortcut("Ctrl+O")
    file_menu.addAction(open_action)

    save_action = QAction("&Save", win)
    save_action.setShortcut("Ctrl+S")
    file_menu.addAction(save_action)

    exit_action = QAction("E&xit", win)
    exit_action.setShortcut("Ctrl+Q")
    file_menu.addAction(exit_action)

    # View menu with submenu
    view_menu = menubar.addMenu("&View")
    theme_menu = view_menu.addMenu("&Theme")
    light_action = QAction("Light", win)
    theme_menu.addAction(light_action)
    dark_action = QAction("Dark", win)
    theme_menu.addAction(dark_action)

    # Graph menu
    graph_menu = menubar.addMenu("&Graph")
    chart_menu = graph_menu.addMenu("Chart &Type")
    line_action = QAction("Line", win)
    chart_menu.addAction(line_action)
    bar_action = QAction("Bar", win)
    chart_menu.addAction(bar_action)

    return win


@pytest.fixture
def palette(main_window):
    """Create a CommandPaletteDialog attached to the test main window."""
    return CommandPaletteDialog(main_window)


class TestCommandPaletteIndexing:
    """Test that the palette indexes menu actions correctly."""

    def test_entries_populated(self, palette):
        """All leaf menu actions should be indexed."""
        assert len(palette._entries) > 0

    def test_file_menu_indexed(self, palette):
        """File menu actions should appear in entries."""
        labels = [e.label for e in palette._entries]
        assert any("Open Data" in l for l in labels)
        assert any("Save" in l for l in labels)
        assert any("xit" in l for l in labels)

    def test_submenu_actions_indexed(self, palette):
        """Submenu actions (e.g., Theme > Light) should be indexed with prefix."""
        labels = [e.label for e in palette._entries]
        assert any("Theme" in l and "Light" in l for l in labels)
        assert any("Theme" in l and "Dark" in l for l in labels)

    def test_shortcuts_captured(self, palette):
        """Shortcuts should be captured from QAction."""
        open_entries = [e for e in palette._entries if "Open Data" in e.label]
        assert len(open_entries) == 1
        assert "Ctrl+O" in open_entries[0].shortcut or "O" in open_entries[0].shortcut

    def test_separators_excluded(self, palette):
        """Separator actions should not appear in entries."""
        for entry in palette._entries:
            assert entry.label.strip() != ""

    def test_nested_chart_type(self, palette):
        """Nested menu items like Graph > Chart Type > Line should be indexed."""
        labels = [e.label for e in palette._entries]
        assert any("Chart Type" in l and "Line" in l for l in labels)
        assert any("Chart Type" in l and "Bar" in l for l in labels)


class TestCommandPaletteFiltering:
    """Test real-time filtering."""

    def test_empty_query_shows_all(self, palette):
        """Empty query should show all entries."""
        palette._filter_entries("")
        assert len(palette._filtered) == len(palette._entries)

    def test_case_insensitive_filter(self, palette):
        """Filtering should be case-insensitive."""
        palette._filter_entries("open")
        assert any("Open Data" in e.label for e in palette._filtered)

        palette._filter_entries("OPEN")
        assert any("Open Data" in e.label for e in palette._filtered)

    def test_partial_match(self, palette):
        """Partial text should match."""
        palette._filter_entries("sav")
        assert any("Save" in e.label for e in palette._filtered)

    def test_multi_word_search(self, palette):
        """Multiple words should all match (AND logic)."""
        palette._filter_entries("chart line")
        assert any("Line" in e.label and "Chart" in e.label for e in palette._filtered)

    def test_no_match_returns_empty(self, palette):
        """Non-matching query should return empty list."""
        palette._filter_entries("xyznonexistent123")
        assert len(palette._filtered) == 0

    def test_shortcut_in_search(self, palette):
        """Searching by shortcut text should match."""
        palette._filter_entries("Ctrl+O")
        assert any("Open Data" in e.label for e in palette._filtered)

    def test_filter_updates_list_widget(self, palette):
        """Filtering should update the QListWidget."""
        palette._filter_entries("save")
        assert palette._result_list.count() == len(palette._filtered)


class TestCommandPaletteExecution:
    """Test action execution."""

    def test_item_activation_triggers_action(self, palette):
        """Double-clicking or pressing Enter on an item should trigger its QAction."""
        # Find the "Save" entry
        palette._filter_entries("Save")
        assert palette._result_list.count() > 0

        item = palette._result_list.item(0)
        entry = item.data(Qt.UserRole)
        assert entry is not None

        # Mock the action trigger
        entry.action.trigger = MagicMock()

        # Simulate activation (accept() will close, so we mock it)
        with patch.object(palette, 'accept'):
            palette._on_item_activated(item)

        entry.action.trigger.assert_called_once()


class TestCommandPaletteKeyboard:
    """Test keyboard navigation."""

    def test_escape_rejects(self, palette, qapp):
        """Pressing Escape should close the dialog."""
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        with patch.object(palette, 'reject') as mock_reject:
            event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
            palette.keyPressEvent(event)
            mock_reject.assert_called_once()

    def test_arrow_down_moves_selection(self, palette):
        """Down arrow should move selection down."""
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        palette._filter_entries("")
        if palette._result_list.count() < 2:
            pytest.skip("Need at least 2 items")

        palette._result_list.setCurrentRow(0)
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier)
        palette.keyPressEvent(event)
        assert palette._result_list.currentRow() == 1

    def test_arrow_up_moves_selection(self, palette):
        """Up arrow should move selection up."""
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        palette._filter_entries("")
        if palette._result_list.count() < 2:
            pytest.skip("Need at least 2 items")

        palette._result_list.setCurrentRow(1)
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier)
        palette.keyPressEvent(event)
        assert palette._result_list.currentRow() == 0

    def test_enter_activates_current(self, palette):
        """Enter should activate the current item."""
        palette._filter_entries("")
        if palette._result_list.count() == 0:
            pytest.skip("Need at least 1 item")

        palette._result_list.setCurrentRow(0)
        item = palette._result_list.currentItem()
        entry = item.data(Qt.UserRole)
        entry.action.trigger = MagicMock()

        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        with patch.object(palette, 'accept'):
            event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
            palette.keyPressEvent(event)

        entry.action.trigger.assert_called_once()
