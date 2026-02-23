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
from typing import Optional

from data_graph_studio.core.file_watcher import FileWatcher
from data_graph_studio.core.io_abstract import IFileSystem, ITimerFactory
from data_graph_studio.core.observable import Observable
from data_graph_studio.core.constants import DEFAULT_POLL_INTERVAL_MS

logger = logging.getLogger(__name__)


class StreamingController(Observable):
    """
    Streaming controller — manages FileWatcher and streaming state.

    Events emitted:
        streaming_state_changed(new_state: str)  — "off" | "live" | "paused"
        data_updated(file_path: str, new_row_count: int)
        file_deleted(file_path: str)             — notifies listeners before stop

    Usage:
        ctrl = StreamingController(fs=real_fs, timer_factory=qt_timer_factory)
        ctrl.subscribe("streaming_state_changed", on_state_changed)
        ctrl.start("/path/to/file.csv", mode="tail")
        ctrl.pause()
        ctrl.resume()
        ctrl.stop()
    """

    def __init__(
        self,
        fs: IFileSystem,
        timer_factory: ITimerFactory,
    ):
        """Initialize the StreamingController in 'off' state with no active watcher.

        Input: fs — IFileSystem, filesystem abstraction for file existence and size checks
               timer_factory — ITimerFactory, factory used to create polling timers
        Output: None
        Invariants: state is 'off'; _watcher and _current_path are None; follow_tail is False
        """
        super().__init__()

        self._fs = fs
        self._timer_factory = timer_factory
        self._state: str = "off"  # "off" | "live" | "paused"
        self._watcher: Optional[FileWatcher] = None
        self._current_path: Optional[str] = None
        self._current_mode: str = "tail"
        self._poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS
        self._follow_tail: bool = False

    # ── Properties ────────────────────────────────────────────

    @property
    def state(self) -> str:
        """Return the current streaming state string ('off', 'live', or 'paused').

        Output: str — one of 'off', 'live', or 'paused'
        """
        return self._state

    @property
    def poll_interval_ms(self) -> int:
        """Return the file polling interval in milliseconds.

        Output: int — polling period; matches the interval passed to the FileWatcher
        """
        return self._poll_interval_ms

    @property
    def follow_tail(self) -> bool:
        """Return True when the controller is set to follow the file tail.

        Output: bool — True when auto-scroll to file end is enabled
        """
        return self._follow_tail

    @property
    def current_path(self) -> Optional[str]:
        """Return the file path currently being streamed, or None.

        Output: Optional[str] — absolute file path, or None when state is 'off'
        """
        return self._current_path

    # ── Public API ────────────────────────────────────────────

    def start(self, file_path: str, mode: str = "tail") -> bool:
        """Start streaming for a file, stopping any existing watcher first.

        Input: file_path — str, readable file path to monitor;
               mode — str, "tail" (append-only) or "reload" (full change detection).
        Output: bool — True if the watcher was created and started successfully; False if
                FileWatcher.watch() returned False.
        Invariants: state transitions to "live" on True; watcher is cleaned up on False.
        """
        if self._state == "live":
            self.stop()

        self._watcher = FileWatcher(
            fs=self._fs,
            timer_factory=self._timer_factory,
            poll_interval_ms=self._poll_interval_ms,
        )

        # Subscribe to Observable events
        self._watcher.subscribe("file_changed", self._on_file_changed)
        self._watcher.subscribe("file_deleted", self._on_file_deleted)
        self._watcher.subscribe("rows_appended", self._on_rows_appended)

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
        """Stop streaming and release the FileWatcher immediately (ERR-2.4).

        Output: None
        Invariants: state transitions to "off"; _watcher is None; _current_path is None.
        """
        if self._watcher:
            self._watcher.shutdown()
            self._watcher = None
        self._current_path = None
        self._set_state("off")

    def pause(self) -> None:
        """Pause streaming — keep the watcher alive but suppress data_updated events.

        Output: None
        Invariants: state transitions to "paused" only when currently "live"; no-op otherwise.
        """
        if self._state == "live":
            self._set_state("paused")

    def resume(self) -> None:
        """Resume streaming from a paused state, allowing data_updated events to flow again.

        Output: None
        Invariants: state transitions to "live" only when currently "paused"; no-op otherwise.
        """
        if self._state == "paused":
            self._set_state("live")

    def set_poll_interval(self, ms: int) -> None:
        """Set the file polling interval in milliseconds.

        Input: ms — int, polling period in milliseconds (> 0).
        Output: None
        Invariants: if a watcher is active it is updated immediately; takes effect on
                    the next poll cycle.
        """
        self._poll_interval_ms = ms
        if self._watcher:
            self._watcher.set_interval(ms)

    def set_follow_tail(self, enabled: bool) -> None:
        """Enable or disable follow-tail mode (auto-scroll to the end of the file).

        Input: enabled — bool; True to enable auto-scroll, False to disable.
        Output: None
        Invariants: self.follow_tail == enabled after this call.
        """
        self._follow_tail = enabled

    def shutdown(self) -> None:
        """Perform a full shutdown per PRD Section 10.6 step 1, delegating to stop().

        Output: None
        Invariants: equivalent to calling stop(); state is "off" after this call.
        """
        self.stop()

    # ── Internal ──────────────────────────────────────────────

    def _set_state(self, new_state: str) -> None:
        if self._state != new_state:
            self._state = new_state
            self.emit("streaming_state_changed", new_state)

    def _on_file_changed(self, path: str) -> None:
        """Handle file_changed from FileWatcher."""
        if self._state != "live":
            return
        self.emit("data_updated", path, 0)

    def _on_file_deleted(self, path: str) -> None:
        """Handle file_deleted — ERR-2.1. Notify UI before stopping."""
        logger.warning("streaming_controller.file_deleted", extra={"path": path})
        self.emit("file_deleted", path)
        self.stop()

    def _on_rows_appended(self, path: str, count: int) -> None:
        """Handle rows_appended from FileWatcher."""
        if self._state != "live":
            return
        self.emit("data_updated", path, count)
