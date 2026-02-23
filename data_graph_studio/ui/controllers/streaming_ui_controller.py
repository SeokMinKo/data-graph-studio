"""StreamingUIController - extracted from MainWindow."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QMessageBox, QLabel
from PySide6.QtCore import Slot, QTimer

from ..dialogs.streaming_dialog import StreamingDialog

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..main_window import MainWindow

class StreamingUIController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window
        self._base_poll_interval_ms: int | None = None
        self._streaming_start_time: float | None = None
        self._streaming_total_rows: int = 0
        self._streaming_window_size: int | None = None  # None = All
        # Stats overlay
        self._stats_label: QLabel | None = None
        self._stats_timer: QTimer | None = None

    def _on_streaming_play(self, checked: bool = False):
        """Start/resume streaming — Play 연속 클릭 방어 (FR-B2.6)."""
        if self.w._streaming_controller.state == "live":
            return  # already playing
        if not self.w.state.is_data_loaded:
            self.w.statusbar.showMessage("⚠ No data loaded — cannot start streaming", 4000)
            self.w._streaming_play_action.setChecked(False)
            return
        if self.w._streaming_controller.state == "paused":
            self.w._streaming_controller.resume()
        else:
            self.w._on_start_streaming_dialog()


    def _on_streaming_pause(self):
        """Pause/resume streaming playback (unified — replaces _on_pause_streaming)."""
        if self.w._streaming_controller.state == "live":
            self.w._streaming_controller.pause()
        elif self.w._streaming_controller.state == "paused":
            self.w._streaming_controller.resume()


    def _on_streaming_stop(self):
        """Stop streaming — current data is kept (FR-B2.7). Unified stop method."""
        self.w._streaming_controller.stop()


    def _on_streaming_speed_changed(self, text: str):
        """Change streaming speed (base interval based, no cumulative error)."""
        try:
            if self._base_poll_interval_ms is None:
                self._base_poll_interval_ms = self.w._streaming_controller.poll_interval_ms
            speed = float(text.replace('x', ''))
            self.w._streaming_controller.set_poll_interval(
                max(500, int(self._base_poll_interval_ms / speed))
            )
        except (ValueError, ZeroDivisionError):
            pass


    def _on_streaming_window_changed(self, text: str):
        """Change streaming window size for sliding window display."""
        text = text.strip()
        if text.lower() == "all" or not text:
            self._streaming_window_size = None
        else:
            try:
                self._streaming_window_size = int(
                    text.replace(",", "").replace("k", "000").replace("K", "000")
                )
            except ValueError:
                self._streaming_window_size = None


    def _on_start_streaming_dialog(self):
        """Open the streaming configuration dialog and start streaming (FR-B2.1)."""
        if not self.w.state.is_data_loaded:
            self.w.statusbar.showMessage("⚠ No data loaded — load data first", 4000)
            return
        initial_path = self.w._streaming_controller.current_path or ""
        dlg = StreamingDialog(
            self.w,
            initial_path=initial_path,
            initial_interval_ms=self.w._streaming_controller.poll_interval_ms,
            initial_mode="tail",
        )
        if dlg.exec() != QDialog.Accepted:
            return

        file_path = dlg.file_path
        if not file_path:
            return

        # Store base interval and reset stats
        self._base_poll_interval_ms = dlg.interval_ms
        self._streaming_start_time = time.time()
        self._streaming_total_rows = 0

        # Configure and start
        self.w._streaming_controller.set_poll_interval(dlg.interval_ms)
        ok = self.w._streaming_controller.start(file_path, mode=dlg.mode)
        if not ok:
            QMessageBox.warning(
                self.w, "Streaming Error",
                f"Could not start streaming for:\n{file_path}\n\n"
                "The file may not exist or is not accessible.",
            )

    # Aliases for backward compatibility (unified pause/stop — bug #3)
    _on_pause_streaming = _on_streaming_pause
    _on_stop_streaming = _on_streaming_stop

    @Slot(str)
    def _on_streaming_state_changed(self, new_state: str):
        """Handle streaming state transitions — update toolbar and status bar (FR-B2.4)."""
        is_active = new_state in ("live", "paused")

        # Toolbar buttons
        self.w._streaming_play_action.setEnabled(new_state != "live")
        self.w._streaming_play_action.setChecked(new_state == "live")
        self.w._streaming_pause_action.setEnabled(is_active)
        self.w._streaming_stop_action.setEnabled(is_active)

        # Pause button label
        if new_state == "paused":
            self.w._streaming_pause_action.setText("▶")
            self.w._streaming_pause_action.setToolTip("Resume Streaming")
        else:
            self.w._streaming_pause_action.setText("⏸")
            self.w._streaming_pause_action.setToolTip("Pause Streaming")

        # Menu actions
        self.w._start_streaming_action.setEnabled(new_state == "off")
        self.w._stop_streaming_action.setEnabled(is_active)

        # Show/hide streaming toolbar controls + stats overlay
        if is_active:
            self.w._toolbar_ctrl._show_streaming_controls()
            self._start_stats_overlay()
        else:
            self.w._toolbar_ctrl._hide_streaming_controls()
            self._stop_stats_overlay()

        # Status bar (FR-B2.4)
        if new_state == "live":
            self.w.statusbar.showMessage("Streaming: 🟢 active", 3000)
            if self._streaming_start_time is None:
                self._streaming_start_time = time.time()
        elif new_state == "paused":
            self.w.statusbar.showMessage("Streaming: ⏸ paused", 3000)
        elif new_state == "off":
            self.w.statusbar.showMessage("Streaming stopped", 3000)
            self._streaming_start_time = None
            self._streaming_total_rows = 0

    @Slot(str, int)
    def _on_streaming_data_updated(self, file_path: str, new_row_count: int):
        """Handle incoming streaming data — incremental append when possible."""
        try:
            # Track stats
            self._streaming_total_rows += max(0, new_row_count)

            if not self.w.engine.is_loaded:
                # First load via engine
                dataset_id = self.w.engine.load_dataset(file_path)
                if dataset_id:
                    dataset = self.w.engine.get_dataset(dataset_id)
                    if dataset:
                        memory_bytes = (
                            dataset.df.estimated_size()
                            if dataset and dataset.df is not None
                            else 0
                        )
                        self.w.state.add_dataset(
                            dataset_id=dataset_id,
                            name=dataset.name if dataset.name else Path(file_path).stem,
                            file_path=file_path,
                            row_count=self.w.engine.row_count,
                            column_count=self.w.engine.column_count,
                            memory_bytes=memory_bytes,
                        )
                    self.w._on_dataset_activated(dataset_id)
                return

            # Try incremental append
            if hasattr(self.w.engine, 'append_rows') and new_row_count > 0:
                try:
                    self.w.engine.append_rows(file_path, new_row_count)
                except Exception:
                    logger.warning("streaming_ui_controller.append_rows_failed.fallback_to_reload", exc_info=True)
                    self.w.engine.load_file(file_path, optimize_memory=True)
            else:
                self.w.engine.load_file(file_path, optimize_memory=True)

            # Apply sliding window if set
            df = self.w.engine.df
            if df is not None and self._streaming_window_size is not None:
                df = df.tail(self._streaming_window_size)

            if df is not None:
                self.w.state.set_data_loaded(True, len(df))
                self.w.table_panel.set_data(df)
                self.w.graph_panel.refresh()

                # Follow tail: auto-scroll table
                if self.w._streaming_controller.follow_tail:
                    if hasattr(self.w.table_panel, 'table_view'):
                        self.w.table_panel.table_view.scrollToBottom()

                self._update_streaming_status(new_row_count)

        except Exception as e:
            logger.error("streaming_ui_controller.data_update_error", extra={"error": e}, exc_info=True)
            self.w.statusbar.showMessage(f"Streaming error: {e}", 5000)

    @Slot(str)
    def _on_streaming_file_deleted(self, file_path: str):
        """Handle file deletion during streaming — notify user."""
        self.w.statusbar.showMessage(
            f"⚠ Streaming file deleted: {Path(file_path).name} — streaming stopped", 5000
        )

    def _update_streaming_status(self, new_row_count: int):
        """Update statusbar with streaming row counter and throughput."""
        elapsed = time.time() - self._streaming_start_time if self._streaming_start_time else 0
        rate = self._streaming_total_rows / elapsed if elapsed > 0 else 0
        total = f"{self._streaming_total_rows:,}"
        msg = f"Streaming: {total} rows ({rate:.0f} rows/s)"
        if new_row_count > 0:
            msg += f"  |  +{new_row_count}"
        self.w.statusbar.showMessage(msg, 3000)

    # -- Stats overlay --

    def _start_stats_overlay(self):
        """Show a persistent streaming stats label."""
        if self._stats_label is None:
            self._stats_label = QLabel("")
            self._stats_label.setStyleSheet(
                "QLabel { background: rgba(0,0,0,0.6); color: #0f0; "
                "padding: 4px 8px; border-radius: 4px; font-size: 11px; }"
            )
            self.w.statusbar.addPermanentWidget(self._stats_label)
        self._stats_label.show()
        if self._stats_timer is None:
            self._stats_timer = QTimer()
            self._stats_timer.timeout.connect(self._refresh_stats_overlay)
        self._stats_timer.start(1000)

    def _stop_stats_overlay(self):
        """Hide the streaming stats overlay."""
        if self._stats_timer:
            self._stats_timer.stop()
        if self._stats_label:
            self._stats_label.hide()

    def _refresh_stats_overlay(self):
        """Update the stats overlay label."""
        if self._stats_label is None or self._streaming_start_time is None:
            return
        elapsed = time.time() - self._streaming_start_time
        mins, secs = divmod(int(elapsed), 60)
        rate = self._streaming_total_rows / elapsed if elapsed > 0 else 0
        self._stats_label.setText(
            f"⏱ {mins:02d}:{secs:02d}  |  "
            f"📊 {self._streaming_total_rows:,} rows  |  "
            f"⚡ {rate:.0f} rows/s"
        )


