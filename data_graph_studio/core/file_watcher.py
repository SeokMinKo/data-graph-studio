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

from PySide6.QtCore import QObject, Signal

from data_graph_studio.core.io_abstract import IFileSystem, ITimerFactory

logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────

MIN_POLL_INTERVAL_MS = 500      # 0.5 seconds
MAX_POLL_INTERVAL_MS = 60000    # 60 seconds
DEFAULT_POLL_INTERVAL_MS = 1000 # 1 second
DEBOUNCE_MS = 300               # 300ms debounce
MAX_WATCHED_FILES = 10          # Section 10.2
LARGE_FILE_THRESHOLD = 2 * 1024 * 1024 * 1024  # 2GB
MAX_BACKOFF_MS = 30000          # 30 seconds max backoff


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


class FileWatcher(QObject):
    """
    Polled file watcher with DI support.

    Usage:
        fs = RealFileSystem()
        timer_factory = QTimerFactory()
        watcher = FileWatcher(fs=fs, timer_factory=timer_factory)
        watcher.watch("/path/to/file.csv", mode="tail")
        watcher.file_changed.connect(on_changed)
        watcher.rows_appended.connect(on_appended)
    """

    # ── Signals ───────────────────────────────────────────────
    file_changed = Signal(str)       # file_path
    file_deleted = Signal(str)       # file_path
    rows_appended = Signal(str, int) # file_path, new_row_count

    def __init__(
        self,
        fs: IFileSystem,
        timer_factory: ITimerFactory,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)

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
        return self._poll_interval_ms

    @property
    def watched_count(self) -> int:
        return len(self._entries)

    # ── Public API ────────────────────────────────────────────

    def set_interval(self, ms: int) -> None:
        """Set polling interval. Clamped to [500, 60000] ms."""
        self._poll_interval_ms = _clamp_interval(ms)
        # Restart timer if running
        if self._timer is not None:
            self._stop_timer()
            self._start_timer()

    def watch(self, file_path: str, mode: str = "reload") -> bool:
        """
        Start watching a file.

        Args:
            file_path: Path to the file
            mode: "reload" (full change) or "tail" (append-only)

        Returns:
            True if watch started successfully, False otherwise.
        """
        # Check file exists
        if not self._fs.exists(file_path):
            logger.warning(f"FileWatcher: file not found: {file_path}")
            return False

        # Get initial stat
        try:
            st = self._fs.stat(file_path)
        except (FileNotFoundError, PermissionError) as e:
            logger.warning(f"FileWatcher: cannot stat {file_path}: {e}")
            return False

        # Section 10.2: 2GB+ → tail only
        if st.st_size > LARGE_FILE_THRESHOLD and mode == "reload":
            logger.info(f"FileWatcher: {file_path} > 2GB, forcing tail mode")
            mode = "tail"

        # Section 10.2: Max watched files → evict oldest
        if file_path not in self._entries and len(self._entries) >= MAX_WATCHED_FILES:
            # Evict oldest (first item in OrderedDict)
            oldest_path = next(iter(self._entries))
            logger.info(f"FileWatcher: max files reached, evicting {oldest_path}")
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
            except Exception as e:
                logger.warning(f"FileWatcher: cannot read {file_path} for row count: {e}")

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
        """Stop watching a file."""
        self._entries.pop(file_path, None)
        self._debounce_pending.pop(file_path, None)
        self._debounce_data.pop(file_path, None)

        # Stop timer if no files left
        if not self._entries:
            self._stop_timer()

    def is_watching(self, file_path: str) -> bool:
        """Check if a file is being watched."""
        return file_path in self._entries

    def get_watch_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get watch info for a file."""
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
        """Mark file as being modified by this app (prevents infinite loop)."""
        entry = self._entries.get(file_path)
        if entry:
            entry.self_modifying = True

    def end_self_modify(self, file_path: str) -> None:
        """
        End self-modify mode.
        Updates last_mtime/size to current state so the self-write
        isn't detected as an external change.
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
        """
        Flush pending debounce events immediately.
        Used in tests and during shutdown.
        """
        if not self._debounce_pending:
            return

        pending = dict(self._debounce_pending)
        data = dict(self._debounce_data)
        self._debounce_pending.clear()
        self._debounce_data.clear()

        for path, event_type in pending.items():
            if event_type == "changed":
                self.file_changed.emit(path)
            elif event_type == "appended":
                count = data.get(path, 0)
                self.rows_appended.emit(path, count)
            elif event_type == "deleted":
                self.file_deleted.emit(path)

    def shutdown(self) -> None:
        """Stop all watchers and clean up. PRD Section 10.6."""
        self.flush_debounce()
        self._stop_timer()
        self._entries.clear()
        self._debounce_pending.clear()
        self._debounce_data.clear()

    # ── Backoff (Section 10.2) ────────────────────────────────

    def _apply_backoff(self, file_path: str) -> None:
        """Double the backoff multiplier for a file (max 30s effective)."""
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
        """Reset backoff to normal after a successful poll."""
        entry = self._entries.get(file_path)
        if entry:
            entry.backoff_multiplier = 1

    # ── Timer Management ──────────────────────────────────────

    def _start_timer(self) -> None:
        if self._timer is not None:
            return
        self._timer = self._timer_factory.create_timer(
            self._poll_interval_ms, self._on_poll
        )
        self._timer.start()

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    # ── Polling ───────────────────────────────────────────────

    def _on_poll(self) -> None:
        """Called by timer on each poll interval."""
        # Copy keys to allow mutation during iteration
        paths = list(self._entries.keys())
        for path in paths:
            entry = self._entries.get(path)
            if entry is None:
                continue
            self._check_file(entry)

    def _check_file(self, entry: _WatchEntry) -> None:
        """Check a single file for changes."""
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
        """Handle change in reload mode → emit file_changed."""
        entry.last_mtime = st.st_mtime
        entry.last_size = st.st_size
        self._schedule_debounce(entry.path, "changed")

    def _handle_tail(self, entry: _WatchEntry, st: Any) -> None:
        """
        Handle change in tail mode.
        Uses seek-based reading for performance — only reads new bytes.
        Falls back to full read if file was truncated or on first read without header.
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
        except Exception as e:
            logger.warning(f"FileWatcher: error reading {path}: {e}")
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
        """
        Schedule a debounced event.
        Multiple events within debounce window are merged
        (last event wins for same path).
        """
        self._debounce_pending[path] = event_type

        # In production, use a QTimer for debounce.
        # For testability with MockTimerFactory, we use a simple flag approach.
        # The debounce timer fires after DEBOUNCE_MS and calls flush_debounce.
        if self._debounce_timer is None:
            self._debounce_timer = self._timer_factory.create_timer(
                DEBOUNCE_MS, self._on_debounce_timeout
            )
            self._debounce_timer.start()

    def _on_debounce_timeout(self) -> None:
        """Debounce timer expired → emit pending events."""
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer = None
        self.flush_debounce()
