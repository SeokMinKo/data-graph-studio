"""Focus row navigation behavior for TablePanel."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass  # avoid circular imports

from PySide6.QtWidgets import QAbstractItemView


class _TableFocusMixin:
    """Mixin: focus row navigation for TablePanel.

    Requires self to be a TablePanel instance with:
      self.engine              - DataEngine
      self.state               - AppState
      self.table_view          - QTableView
      self.focus_prev_btn      - QPushButton
      self.focus_next_btn      - QPushButton
      self.focus_label         - QLabel
      self._focus_enabled      - bool
      self._focus_sorted_rows  - List[int]
      self._focus_current_idx  - int
    """

    def _on_focus_toggled(self, checked: bool):
        """Toggle focus mode."""
        self._focus_enabled = checked
        if checked:
            self._update_focus_from_selection()
        else:
            self._clear_focus()

    def _update_focus_from_selection(self):
        """Update focus state from current selection."""
        if not self._focus_enabled or not self.engine.is_loaded:
            self._clear_focus()
            return

        selected = self.state.selection.selected_rows
        if not selected:
            self._clear_focus()
            return

        max_row = len(self.engine.df) if self.engine.df is not None else 0
        valid = sorted(r for r in selected if 0 <= r < max_row)
        if not valid:
            self._clear_focus()
            return

        self._focus_sorted_rows = valid
        self._focus_current_idx = 0

        # Highlight rows in model
        model = self.table_view.model()
        if hasattr(model, 'set_focused_rows'):
            model.set_focused_rows(set(valid))

        self._update_focus_nav()
        self._scroll_to_focus_current()

    def _clear_focus(self):
        """Clear all focus state."""
        self._focus_sorted_rows = []
        self._focus_current_idx = 0
        self.focus_prev_btn.setEnabled(False)
        self.focus_next_btn.setEnabled(False)
        self.focus_label.setText("")

        model = self.table_view.model()
        if hasattr(model, 'set_focused_rows'):
            model.set_focused_rows(set())

    def _update_focus_nav(self):
        """Update back/next buttons and label."""
        count = len(self._focus_sorted_rows)
        if count == 0:
            self.focus_prev_btn.setEnabled(False)
            self.focus_next_btn.setEnabled(False)
            self.focus_label.setText("")
            return

        idx = self._focus_current_idx
        self.focus_prev_btn.setEnabled(idx > 0)
        self.focus_next_btn.setEnabled(idx < count - 1)
        self.focus_label.setText(f"{idx + 1}/{count}")

    def _scroll_to_focus_current(self):
        """Scroll table to the current focus row."""
        if not self._focus_sorted_rows:
            return
        row = self._focus_sorted_rows[self._focus_current_idx]
        model = self.table_view.model()
        if model and row < model.rowCount():
            index = model.index(row, 0)
            self.table_view.scrollTo(index, QAbstractItemView.PositionAtCenter)

    def _on_focus_prev(self):
        if self._focus_current_idx > 0:
            self._focus_current_idx -= 1
            self._update_focus_nav()
            self._scroll_to_focus_current()

    def _on_focus_next(self):
        if self._focus_current_idx < len(self._focus_sorted_rows) - 1:
            self._focus_current_idx += 1
            self._update_focus_nav()
            self._scroll_to_focus_current()
