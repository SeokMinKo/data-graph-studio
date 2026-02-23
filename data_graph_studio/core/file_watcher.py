"""
FileWatcher — PRD Section 3.2, 6.2, 10.2

Polled file watcher for live data streaming.
Supports reload mode (full file change detection) and tail mode (append-only).

Signals:
    file_changed(str)       — file_path (reload mode: content changed)
    file_deleted(str)       — file_path (file deleted/inaccessible)
    rows_appended(str, int) — file_path, new_row_count (tail mode: new rows)

Safety:
    - FR-2.8: Triple anti-loop defense (debounce + self-change + mtime/size)
    - Section 10.2: Max 10 watched files, 2GB+ tail-only, error backoff
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from data_graph_studio.core.io_abstract import IFileSystem, ITimerFactory
from data_graph_studio.core.observable import Observable
from data_graph_studio.core.constants import (
    MIN_POLL_INTERVAL_MS,
    MAX_POLL_INTERVAL_MS,
    DEFAULT_POLL_INTERVAL_MS,
    DEBOUNCE_MS,
    MAX_WATCHED_FILES,
    LARGE_FILE_THRESHOLD,
    MAX_BACKOFF_MS,
)

logger = logging.getLogger(__name__)


def _clamp_interval(ms: int) -> int:
    """Clamp polling interval to valid range [500, 60000] ms."""
    return max(MIN_POLL_INTERVAL_MS, min(MAX_POLL_INTERVAL_MS, ms))


# ─── Per-file watch state ──────────────────────────────────────────

@dataclass
class _WatchEntry:
    """Internal per-file watch state."""
    path: str
    mode: str                      # "reload" | "tail"
    last_mtime: float = 0.0
    last_size: int = 0
    last_row_count: int = 0        # For tail mode: row count at last check
    last_header: str = ""          # For tail mode: CSV header line for schema check
    self_modifying: bool = False   # FR-2.8: self-change flag
    backoff_multiplier: int = 1    # Error backoff multiplier
    registered_at: float = field(default_factory=time.time)


class FileWatcher(Observable):
    """
    Polled file watcher with DI support.

    Usage:
        fs = RealFileSystem()
        timer_factory = ThreadingTimerFactory()
        watcher = FileWatcher(fs=fs, timer_factory=timer_factory)
        watcher.watch("/path/to/file.csv", mode="tail")
        watcher.subscribe("file_changed", on_changed)
        watcher.subscribe("rows_appended", on_appended)

    Events:
        file_changed(file_path: str)           — reload mode: content changed
        file_deleted(file_path: str)           — file deleted/inaccessible
        rows_appended(file_path: str, int)     — tail mode: new rows appended
    """

    def __init__(
        self,
        fs: IFileSystem,
        timer_factory: ITimerFactory,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> None:
        """Initialise FileWatcher with injected filesystem and timer factory.

        Input: fs — IFileSystem, abstraction for stat/read operations;
               timer_factory — ITimerFactory, creates poll and debounce timers;
               poll_interval_ms — int, desired poll interval clamped to [500, 60000]
        Output: None
        Invariants: no timer is started until the first file is watched
        """
        super().__init__()

        self._fs = fs
        self._timer_factory = timer_factory
        self._poll_interval_ms = _clamp_interval(poll_interval_ms)

        # Ordered dict to track registration order (for eviction)
        self._entries: OrderedDict[str, _WatchEntry] = OrderedDict()

        # Timer
        self._timer: Any = None

        # Debounce state (per-file)
        self._debounce_pending: Dict[str, str] = {}  # path → event_type
        self._debounce_data: Dict[str, int] = {}      # path → new_row_count (for tail)
        self._debounce_timer: Any = None

    # ── Properties ────────────────────────────────────────────

    @property
    def poll_interval_ms(self) -> int:
        """Return the current polling interval in milliseconds.

        Output: int — value in range [MIN_POLL_INTERVAL_MS, MAX_POLL_INTERVAL_MS]
        """
        return self._poll_interval_ms

    @property
    def watched_count(self) -> int:
        """Return the number of files currently being watched.

        Output: int — zero or more, capped at MAX_WATCHED_FILES
        """
        return len(self._entries)

    # ── Public API ────────────────────────────────────────────

    def set_interval(self, ms: int) -> None:
        """Set the polling interval, clamping to [500, 60000] ms.

        Input: ms — int, desired polling interval in milliseconds
        Output: None
        Invariants: restarts the timer immediately if it is already running
        """
        self._poll_interval_ms = _clamp_interval(ms)
        # Restart timer if running
        if self._timer is not None:
            self._stop_timer()
            self._start_timer()

    def watch(self, file_path: str, mode: str = "reload") -> bool:
        """Register a file for polling and start the timer if not already running.

        Input: file_path — str, absolute path to the file to watch;
               mode — str, 'reload' (any content change) or 'tail' (append-only)
        Output: bool — True if watch registered, False if file not found or stat fails
        Invariants: files >= 2 GB are silently promoted to tail mode (Section 10.2);
                    oldest entry evicted when MAX_WATCHED_FILES is reached;
                    initial mtime/size captured as baseline to prevent false positives
        """
        # Check file exists
        if not self._fs.exists(file_path):
            logger.warning("file_watcher.not_found", extra={"path": file_path})
            return False

        # Get initial stat
        try:
            st = self._fs.stat(file_path)
        except (FileNotFoundError, PermissionError) as e:
            logger.warning("file_watcher.stat_failed", extra={"path": file_path, "error": e})
            return False

        # Section 10.2: 2GB+ → tail only
        if st.st_size > LARGE_FILE_THRESHOLD and mode == "reload":
            logger.info("file_watcher.large_file_tail_mode", extra={"path": file_path})
            mode = "tail"

        # Section 10.2: Max watched files → evict oldest
        if file_path not in self._entries and len(self._entries) >= MAX_WATCHED_FILES:
            # Evict oldest (first item in OrderedDict)
            oldest_path = next(iter(self._entries))
            logger.info("file_watcher.evicting_oldest", extra={"path": oldest_path})
            self._entries.pop(oldest_path)

        # Count rows for tail mode
        row_count = 0
        header = ""
        if mode == "tail":
            try:
                data = self._fs.read_file(file_path)
                lines = data.decode("utf-8", errors="replace").splitlines()
                if lines:
                    header = lines[0]
                    row_count = len(lines) - 1  # subtract header
            except (OSError, PermissionError) as e:
                logger.warning("file_watcher.read_row_count_failed", extra={"path": file_path, "error": e})

        # Create entry
        entry = _WatchEntry(
            path=file_path,
            mode=mode,
            last_mtime=st.st_mtime,
            last_size=st.st_size,
            last_row_count=row_count,
            last_header=header,
        )
        self._entries[file_path] = entry

        # Start timer if not running
        if self._timer is None:
            self._start_timer()

        return True

    def unwatch(self, file_path: str) -> None:
        """Stop watching a file and cancel any pending debounce event for it.

        Input: file_path — str, path previously registered with watch()
        Output: None
        Invariants: no-op if file_path was not being watched; poll timer is stopped
                    when no files remain
        """
        self._entries.pop(file_path, None)
        self._debounce_pending.pop(file_path, None)
        self._debounce_data.pop(file_path, None)

        # Stop timer if no files left
        if not self._entries:
            self._stop_timer()

    def is_watching(self, file_path: str) -> bool:
        """Return True if file_path is currently registered for polling.

        Input: file_path — str
        Output: bool — True if actively watched, False otherwise
        """
        return file_path in self._entries

    def get_watch_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Return a snapshot of the watch state for a registered file.

        Input: file_path — str
        Output: Dict[str, Any] — keys: path, mode, last_mtime, last_size,
                last_row_count, backoff_multiplier, effective_interval_ms;
                or None if file_path is not being watched
        """
        entry = self._entries.get(file_path)
        if entry is None:
            return None
        return {
            "path": entry.path,
            "mode": entry.mode,
            "last_mtime": entry.last_mtime,
            "last_size": entry.last_size,
            "last_row_count": entry.last_row_count,
            "backoff_multiplier": entry.backoff_multiplier,
            "effective_interval_ms": min(
                self._poll_interval_ms * entry.backoff_multiplier,
                MAX_BACKOFF_MS,
            ),
        }

    def begin_self_modify(self, file_path: str) -> None:
        """Mark a file as being written by this application to suppress change events.

        Input: file_path — str, path registered with watch()
        Output: None
        Invariants: no-op if file_path is not being watched; call end_self_modify()
                    after the write completes (FR-2.8 anti-loop)
        """
        entry = self._entries.get(file_path)
        if entry:
            entry.self_modifying = True

    def end_self_modify(self, file_path: str) -> None:
        """Clear self-modify flag and update baseline stat to suppress spurious reload.

        Input: file_path — str, path previously passed to begin_self_modify()
        Output: None
        Invariants: no-op if file_path is not watched; stat failure (FileNotFoundError,
                    PermissionError) is silently swallowed; FR-2.8 anti-loop guarantee
        """
        entry = self._entries.get(file_path)
        if entry:
            entry.self_modifying = False
            # Update baseline to current state
            try:
                st = self._fs.stat(file_path)
                entry.last_mtime = st.st_mtime
                entry.last_size = st.st_size
            except (FileNotFoundError, PermissionError):
                pass

    def flush_debounce(self) -> None:
        """Emit all pending debounced events immediately, bypassing the debounce timer.

        Output: None — emits file_changed, rows_appended, or file_deleted for each
                pending path via Observable.emit
        Invariants: clears pending and data dicts before emitting; safe to call
                    concurrently with shutdown; used by tests and shutdown
        """
        if not self._debounce_pending:
            return

        pending = dict(self._debounce_pending)
        data = dict(self._debounce_data)
        self._debounce_pending.clear()
        self._debounce_data.clear()

        for path, event_type in pending.items():
            if event_type == "changed":
                self.emit("file_changed", path)
            elif event_type == "appended":
                count = data.get(path, 0)
                self.emit("rows_appended", path, count)
            elif event_type == "deleted":
                self.emit("file_deleted", path)

    def shutdown(self) -> None:
        """Flush pending events, stop the poll timer, and clear all watch state (PRD 10.6).

        Output: None
        Invariants: flushes debounce queue before stopping; all internal collections cleared;
                    safe to call more than once
        """
        self.flush_debounce()
        self._stop_timer()
        self._entries.clear()
        self._debounce_pending.clear()
        self._debounce_data.clear()

    # ── Backoff (Section 10.2) ────────────────────────────────

    def _apply_backoff(self, file_path: str) -> None:
        """Double the error backoff multiplier for a file, capped at MAX_BACKOFF_MS effective.

        Input: file_path — str, registered watch path
        Output: None
        Invariants: no-op if file_path is not watched; effective interval never exceeds MAX_BACKOFF_MS
        """
        entry = self._entries.get(file_path)
        if entry:
            entry.backoff_multiplier = min(
                entry.backoff_multiplier * 2,
                MAX_BACKOFF_MS // max(self._poll_interval_ms, 1),
            )
            # Ensure effective interval doesn't exceed MAX_BACKOFF_MS
            effective = self._poll_interval_ms * entry.backoff_multiplier
            if effective > MAX_BACKOFF_MS:
                entry.backoff_multiplier = MAX_BACKOFF_MS // max(self._poll_interval_ms, 1)

    def _reset_backoff(self, file_path: str) -> None:
        """Reset the backoff multiplier to 1 after a successful poll for a file.

        Input: file_path — str, registered watch path
        Output: None
        Invariants: no-op if file_path is not watched
        """
        entry = self._entries.get(file_path)
        if entry:
            entry.backoff_multiplier = 1

    # ── Timer Management ──────────────────────────────────────

    def _start_timer(self) -> None:
        """Create and start the poll timer if one is not already running.

        Output: None
        Invariants: no-op if timer already running; timer fires _on_poll at poll_interval_ms
        """
        if self._timer is not None:
            return
        self._timer = self._timer_factory.create_timer(
            self._poll_interval_ms, self._on_poll
        )
        if callable(getattr(self._timer, "start", None)):
            self._timer.start()

    def _stop_timer(self) -> None:
        """Stop and discard the poll timer.

        Output: None
        Invariants: no-op if timer is not running; self._timer set to None
        """
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    # ── Polling ───────────────────────────────────────────────

    def _on_poll(self) -> None:
        """Poll all watched files for changes on each timer tick.

        Output: None — delegates to _check_file for each registered path
        Invariants: snapshot of keys taken before iteration to allow safe mutation;
                    entries removed inside _check_file are skipped via None guard
        """
        # Copy keys to allow mutation during iteration
        paths = list(self._entries.keys())
        for path in paths:
            entry = self._entries.get(path)
            if entry is None:
                continue
            self._check_file(entry)

    def _check_file(self, entry_or_path: "_WatchEntry | str") -> None:
        """Stat a single watched file and schedule a debounce event if it changed.

        Input: entry_or_path — _WatchEntry or str path; str is resolved to its _WatchEntry
        Output: None — may call _schedule_debounce or _handle_tail/_handle_reload;
                removes entry and schedules 'deleted' if file is inaccessible
        Invariants: self-modifying files are skipped (FR-2.8); backoff reset on success
        """
        if isinstance(entry_or_path, str):
            entry = self._entries.get(entry_or_path)
            if entry is None:
                return
        else:
            entry = entry_or_path
        path = entry.path

        # FR-2.8: Skip if self-modifying
        if entry.self_modifying:
            return

        # Try to stat the file
        try:
            st = self._fs.stat(path)
        except (FileNotFoundError, PermissionError):
            # FR-2.7 / ERR-2.1 / ERR-2.2: File deleted or inaccessible
            self._schedule_debounce(path, "deleted")
            # Remove from watched list
            self._entries.pop(path, None)
            return

        # FR-2.8: mtime + size comparison
        mtime_changed = st.st_mtime != entry.last_mtime
        size_changed = st.st_size != entry.last_size

        if not mtime_changed and not size_changed:
            return  # No change

        # File has changed
        if entry.mode == "tail":
            self._handle_tail(entry, st)
        else:
            self._handle_reload(entry, st)

        # Reset backoff on successful detection
        self._reset_backoff(path)

    def _handle_reload(self, entry: _WatchEntry, st: Any) -> None:
        """Update baseline stat and schedule a 'changed' debounce event (reload mode).

        Input: entry — _WatchEntry, the watch record for the file;
               st — stat_result, current filesystem stat
        Output: None
        Invariants: entry.last_mtime and last_size updated to st values before scheduling
        """
        entry.last_mtime = st.st_mtime
        entry.last_size = st.st_size
        self._schedule_debounce(entry.path, "changed")

    def _handle_tail(self, entry: _WatchEntry, st: Any) -> None:
        """Detect new rows appended to a file and schedule a debounce event (tail mode).

        Input: entry — _WatchEntry, the watch record for the file;
               st — stat_result, current filesystem stat
        Output: None — schedules 'appended' event with new row count, or 'changed'
                if the CSV header changed, or 'deleted' if the file vanished
        Raises: nothing — read errors apply backoff; permission errors emit 'deleted'
        Invariants: uses seek-based read when size grew and header is known (performance);
                    falls back to full IFileSystem.read_file if seek fails (ERR-2.3)
        """
        path = entry.path
        current_size = st.st_size

        try:
            # Seek-based: only read new bytes appended since last check
            if current_size > entry.last_size and entry.last_header:
                try:
                    with open(path, 'rb') as f:
                        f.seek(entry.last_size)
                        new_data = f.read()
                    new_lines = new_data.decode("utf-8", errors="replace").splitlines()
                    new_lines = [line for line in new_lines if line.strip()]
                    new_rows = len(new_lines)

                    if new_rows > 0:
                        entry.last_mtime = st.st_mtime
                        entry.last_size = current_size
                        entry.last_row_count += new_rows
                        self._debounce_data[path] = new_rows
                        self._schedule_debounce(path, "appended")
                    else:
                        entry.last_mtime = st.st_mtime
                        entry.last_size = current_size
                    return
                except (OSError, IOError):
                    pass  # Fall through to full read via IFileSystem

            # Full read via IFileSystem abstraction
            data = self._fs.read_file(path)
            lines = data.decode("utf-8", errors="replace").splitlines()
        except (FileNotFoundError, PermissionError):
            self._schedule_debounce(path, "deleted")
            self._entries.pop(path, None)
            return
        except (OSError, PermissionError) as e:
            logger.warning("file_watcher.read_error", extra={"path": path, "error": e})
            self._apply_backoff(path)
            return

        if not lines:
            return

        current_header = lines[0]
        current_row_count = len(lines) - 1  # subtract header

        # ERR-2.3: Schema (column count) changed → fallback to reload
        if current_header != entry.last_header:
            entry.last_mtime = st.st_mtime
            entry.last_size = st.st_size
            entry.last_row_count = current_row_count
            entry.last_header = current_header
            self._schedule_debounce(path, "changed")
            return

        new_rows = current_row_count - entry.last_row_count
        if new_rows > 0:
            entry.last_mtime = st.st_mtime
            entry.last_size = st.st_size
            entry.last_row_count = current_row_count
            self._debounce_data[path] = new_rows
            self._schedule_debounce(path, "appended")
        else:
            entry.last_mtime = st.st_mtime
            entry.last_size = st.st_size
            entry.last_row_count = current_row_count

    # ── Debounce ──────────────────────────────────────────────

    def _schedule_debounce(self, path: str, event_type: str) -> None:
        """Record a pending event and arm the debounce timer if not already armed.

        Input: path — str, watched file path; event_type — str, 'changed' | 'appended' | 'deleted'
        Output: None
        Invariants: last event wins per path within the debounce window;
                    if timer has no start() (e.g. NullTimer in tests), flushes synchronously
        """
        self._debounce_pending[path] = event_type

        # Schedule debounce flush via timer.
        # If the timer has no start() method (e.g. NullTimer in unit tests),
        # flush immediately so the event is not silently dropped.
        if self._debounce_timer is None:
            self._debounce_timer = self._timer_factory.create_timer(
                DEBOUNCE_MS, self._on_debounce_timeout
            )
            if callable(getattr(self._debounce_timer, "start", None)):
                self._debounce_timer.start()
            else:
                # No async timer available — flush synchronously
                self._debounce_timer = None
                self.flush_debounce()

    def _on_debounce_timeout(self) -> None:
        """Handle debounce timer expiry by stopping the timer and flushing pending events.

        Output: None — delegates to flush_debounce(); clears self._debounce_timer
        """
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer = None
        self.flush_debounce()
