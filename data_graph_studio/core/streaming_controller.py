"""
StreamingController — PRD Section 9.2

Manages FileWatcher lifecycle and streaming state.
Bridges FileWatcher signals with DataEngine data synchronization.

States: off → live → paused → off

Signals:
    streaming_state_changed(str)  — "off" | "live" | "paused"
    data_updated(str, int)        — file_path, new_row_count
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from data_graph_studio.core.file_watcher import FileWatcher
from data_graph_studio.core.io_abstract import IFileSystem, ITimerFactory

logger = logging.getLogger(__name__)


class StreamingController(QObject):
    """
    Streaming controller — manages FileWatcher and streaming state.

    Usage:
        ctrl = StreamingController(fs=real_fs, timer_factory=qt_timer_factory)
        ctrl.streaming_state_changed.connect(on_state_changed)
        ctrl.start("/path/to/file.csv", mode="tail")
        ctrl.pause()
        ctrl.resume()
        ctrl.stop()
    """

    # ── Signals ───────────────────────────────────────────────
    streaming_state_changed = Signal(str)  # "off" | "live" | "paused"
    data_updated = Signal(str, int)        # file_path, new_row_count

    def __init__(
        self,
        fs: IFileSystem,
        timer_factory: ITimerFactory,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)

        self._fs = fs
        self._timer_factory = timer_factory
        self._state: str = "off"  # "off" | "live" | "paused"
        self._watcher: Optional[FileWatcher] = None
        self._current_path: Optional[str] = None
        self._current_mode: str = "tail"
        self._poll_interval_ms: int = 1000
        self._follow_tail: bool = False

    # ── Properties ────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    @property
    def poll_interval_ms(self) -> int:
        return self._poll_interval_ms

    @property
    def follow_tail(self) -> bool:
        return self._follow_tail

    @property
    def current_path(self) -> Optional[str]:
        return self._current_path

    # ── Public API ────────────────────────────────────────────

    def start(self, file_path: str, mode: str = "tail") -> bool:
        """
        Start streaming for a file.

        Args:
            file_path: Path to the file to stream
            mode: "tail" (append-only) or "reload" (full change)

        Returns:
            True if started successfully.
        """
        if self._state == "live":
            self.stop()

        self._watcher = FileWatcher(
            fs=self._fs,
            timer_factory=self._timer_factory,
            poll_interval_ms=self._poll_interval_ms,
        )

        # Connect signals
        self._watcher.file_changed.connect(self._on_file_changed)
        self._watcher.file_deleted.connect(self._on_file_deleted)
        self._watcher.rows_appended.connect(self._on_rows_appended)

        result = self._watcher.watch(file_path, mode=mode)
        if not result:
            self._watcher.shutdown()
            self._watcher = None
            return False

        self._current_path = file_path
        self._current_mode = mode
        self._set_state("live")
        return True

    def stop(self) -> None:
        """Stop streaming. ERR-2.4: FileWatcher 즉시 해제."""
        if self._watcher:
            self._watcher.shutdown()
            self._watcher = None
        self._current_path = None
        self._set_state("off")

    def pause(self) -> None:
        """Pause streaming (keep watcher but don't emit events)."""
        if self._state == "live":
            self._set_state("paused")

    def resume(self) -> None:
        """Resume streaming from paused state."""
        if self._state == "paused":
            self._set_state("live")

    def set_poll_interval(self, ms: int) -> None:
        """Set polling interval."""
        self._poll_interval_ms = ms
        if self._watcher:
            self._watcher.set_interval(ms)

    def set_follow_tail(self, enabled: bool) -> None:
        """Enable/disable follow tail (auto-scroll to end)."""
        self._follow_tail = enabled

    def shutdown(self) -> None:
        """Full shutdown — PRD Section 10.6 step 1."""
        self.stop()

    # ── Internal ──────────────────────────────────────────────

    def _set_state(self, new_state: str) -> None:
        if self._state != new_state:
            self._state = new_state
            self.streaming_state_changed.emit(new_state)

    def _on_file_changed(self, path: str) -> None:
        """Handle file_changed from FileWatcher."""
        if self._state != "live":
            return
        self.data_updated.emit(path, 0)

    def _on_file_deleted(self, path: str) -> None:
        """Handle file_deleted — ERR-2.1."""
        logger.warning(f"Streaming: file deleted: {path}")
        self.stop()

    def _on_rows_appended(self, path: str, count: int) -> None:
        """Handle rows_appended from FileWatcher."""
        if self._state != "live":
            return
        self.data_updated.emit(path, count)
