"""Search and filter behavior for TablePanel."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass  # avoid circular imports

import polars as pl

logger = logging.getLogger(__name__)


class _TableSearchMixin:
    """Mixin: search bar and filter application for TablePanel.

    Requires self to be a TablePanel instance with:
      self.engine             - DataEngine
      self.state              - AppState
      self.search_input       - QLineEdit
      self.search_clear_btn   - QPushButton
      self.search_result_label - QLabel
      self._search_debounce_timer - QTimer
      self._pending_search_text   - str
      self._update_table_model()  - method
    """

    def _on_search_text_changed(self, text: str):
        """Handle search text change with debouncing"""
        self._pending_search_text = text

        # Show/hide clear button
        if text:
            self.search_clear_btn.show()
        else:
            self.search_clear_btn.hide()
            self.search_result_label.setText("")

        # Start debounce timer
        self._search_debounce_timer.start()

    def _execute_search(self):
        """Execute search after debounce delay"""
        text = self._pending_search_text

        if not self.engine.is_loaded:
            return

        if not text:
            self._update_table_model(self.engine.df)
            self.search_result_label.setText("")
            return

        result = self.engine.search(text)

        # Update result count
        if result is not None:
            count = len(result)
            if count == 0:
                self.search_result_label.setText("No results")
                self.search_result_label.setProperty("state", "notfound")
            else:
                self.search_result_label.setText(f"{count:,} results")
                self.search_result_label.setProperty("state", "found")
            self.search_result_label.style().unpolish(self.search_result_label)
            self.search_result_label.style().polish(self.search_result_label)

        self._update_table_model(result)

    def _clear_search(self):
        """Clear search input and restore full data"""
        self.search_input.clear()
        self.search_clear_btn.hide()
        self.search_result_label.setText("")
        self._search_debounce_timer.stop()
        if self.engine.is_loaded:
            self._update_table_model(self.engine.df)

    def _on_search(self, text: str):
        """Legacy search handler (kept for compatibility)"""
        self._on_search_text_changed(text)

    def _on_filter_removed(self, index: int):
        """Handle filter removal"""
        self.state.remove_filter(index)

    def _on_clear_filters(self):
        """Handle clear all filters"""
        self.state.clear_filters()

    def _on_filter_changed(self):
        """Handle filter state change"""
        if self.engine.is_loaded:
            self._apply_filters_and_update()

    def _apply_filters_and_update(self):
        """Apply filters to data and update table"""
        df = self.engine.df
        if df is None:
            return

        # Apply all enabled filters sequentially
        filtered_df = df
        for f in self.state.filters:
            if not f.enabled:
                continue
            try:
                col = pl.col(f.column)

                if f.operator == 'eq':
                    filtered_df = filtered_df.filter(col == f.value)
                elif f.operator == 'ne':
                    filtered_df = filtered_df.filter(col != f.value)
                elif f.operator == 'gt':
                    filtered_df = filtered_df.filter(col > f.value)
                elif f.operator == 'lt':
                    filtered_df = filtered_df.filter(col < f.value)
                elif f.operator == 'ge':
                    filtered_df = filtered_df.filter(col >= f.value)
                elif f.operator == 'le':
                    filtered_df = filtered_df.filter(col <= f.value)
                elif f.operator == 'contains':
                    filtered_df = filtered_df.filter(col.str.contains(str(f.value)))
            except Exception as e:
                # UX 10: Show filter error to user instead of print
                logger.warning("table_search_mixin.apply_filters.filter_error", exc_info=True)
                main_window = self.window()
                if main_window and hasattr(main_window, 'statusBar'):
                    main_window.statusBar().showMessage(
                        f"Filter error on '{f.column}': {e}", 5000
                    )
                continue

        # Update visible rows count in state
        self.state.set_visible_rows(len(filtered_df))
        self._update_table_model(filtered_df)
