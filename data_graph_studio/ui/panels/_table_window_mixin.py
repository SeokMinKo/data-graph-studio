"""Windowed (paginated) row loading behavior for TablePanel."""
from __future__ import annotations


class _TableWindowMixin:
    """Mixin: windowed/paginated data loading for TablePanel.

    Requires self to be a TablePanel instance with:
      self.engine              - DataEngine (is_loaded, is_windowed, window_size,
                                 window_start, total_rows, set_window, df)
      self.state               - AppState (clear_selection, set_visible_rows)
      self.window_widget       - QWidget (visibility toggle)
      self.window_slider       - QSlider
      self.window_size_combo   - QComboBox
      self.window_label        - QLabel
      self.window_prev_btn     - QPushButton
      self.window_next_btn     - QPushButton
      self._window_debounce    - QTimer
      self.window_changed      - Signal()
      self.set_data()          - method
    """

    def _update_window_controls(self):
        if not self.engine.is_loaded or not self.engine.is_windowed:
            self.window_widget.setVisible(False)
            return

        total_rows = self.engine.total_rows
        window_size = self.engine.window_size
        max_start = max(0, total_rows - window_size)

        self.window_widget.setVisible(True)
        self.window_slider.blockSignals(True)
        self.window_slider.setMinimum(0)
        self.window_slider.setMaximum(max_start)
        self.window_slider.setValue(min(self.engine.window_start, max_start))
        self.window_slider.blockSignals(False)

        size_label = f"{int(window_size/1000)}k"
        if size_label in [self.window_size_combo.itemText(i) for i in range(self.window_size_combo.count())]:
            self.window_size_combo.blockSignals(True)
            self.window_size_combo.setCurrentText(size_label)
            self.window_size_combo.blockSignals(False)

        self._set_window_label(self.engine.window_start, window_size, total_rows)

    def _set_window_label(self, start: int, size: int, total: int):
        end = min(start + size, total) if total else start + size
        self.window_label.setText(f"{start + 1:,}–{end:,} / {total:,}")

    def _apply_window(self, start: int):
        if not self.engine.is_windowed:
            return

        total_rows = self.engine.total_rows
        window_size = self.engine.window_size
        max_start = max(0, total_rows - window_size)
        start = max(0, min(start, max_start))

        if self.engine.set_window(start, window_size):
            self.state.clear_selection()
            self.state.set_visible_rows(len(self.engine.df))
            self.set_data(self.engine.df)
            self.window_changed.emit()

    def _on_window_prev(self):
        self._apply_window(self.engine.window_start - self.engine.window_size)

    def _on_window_next(self):
        self._apply_window(self.engine.window_start + self.engine.window_size)

    def _on_window_slider_changed(self, value: int):
        if not self.engine.is_windowed:
            return
        self._set_window_label(value, self.engine.window_size, self.engine.total_rows)
        self._window_debounce.start()

    def _on_window_slider_released(self):
        self._window_debounce.stop()
        self._apply_window(self.window_slider.value())

    def _apply_window_debounced(self):
        self._apply_window(self.window_slider.value())

    def _on_window_size_changed(self, text: str):
        if not self.engine.is_windowed:
            return
        size = int(text.replace("k", "")) * 1000
        current_start = self.engine.window_start
        self.engine.set_window(current_start, size)
        self._update_window_controls()
        self.state.clear_selection()
        self.state.set_visible_rows(len(self.engine.df))
        self.set_data(self.engine.df)
        self.window_changed.emit()
