"""
I/O Abstraction Layer — PRD Section 9.4

Provides:
- IFileSystem ABC — file system abstraction for DI
- ITimerFactory ABC — timer abstraction for DI
- RealFileSystem — production file system implementation
- atomic_write — safe temp→rename file writing (PRD Section 10.3)
"""

from __future__ import annotations

import os
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable


class IFileSystem(ABC):
    """파일 시스템 추상화 — FileWatcher, DataEngine 등에서 사용"""

    @abstractmethod
    def read_file(self, path: str) -> bytes:
        """Read and return the raw bytes of the file at path.

        Input: path — str, file path to read.
        Output: bytes — full file contents.
        Raises: FileNotFoundError — if path does not exist.
        """
        ...

    @abstractmethod
    def write_file(self, path: str, data: bytes) -> None:
        """Write bytes to path, creating parent directories as needed.

        Input: path — str, destination file path; data — bytes to write.
        Output: None
        Raises: OSError — on permission errors or disk-full conditions.
        """
        ...

    @abstractmethod
    def stat(self, path: str) -> os.stat_result:
        """Return the stat result for path.

        Input: path — str, file or directory path.
        Output: os.stat_result — metadata including size and modification time.
        Raises: FileNotFoundError — if path does not exist.
        """
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Return True if path exists on the filesystem, False otherwise.

        Input: path — str, file or directory path to check.
        Output: bool — True if the path exists.
        """
        ...


class ITimerFactory(ABC):
    """타이머 추상화 — FileWatcher, 테스트에서 Mock 가능"""

    @abstractmethod
    def create_timer(self, interval_ms: int, callback: Callable) -> Any:
        """Create a recurring timer that fires callback every interval_ms milliseconds.

        Input: interval_ms — int, polling period in milliseconds (> 0);
               callback — Callable[[], None], invoked on each tick.
        Output: timer handle — implementation-specific object with start()/stop() interface.
        """
        ...


class _ThreadingTimerHandle:
    """
    Recurring timer handle with start()/stop() interface.
    Wraps threading.Timer to produce Qt-compatible start/stop semantics.
    """

    def __init__(self, interval_s: float, callback: Callable) -> None:
        self._interval_s = interval_s
        self._callback = callback
        self._current: threading.Timer | None = None
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the recurring timer."""
        if self._running:
            return
        self._running = True
        self._schedule()

    def stop(self) -> None:
        """Stop the recurring timer and cancel any pending callback."""
        with self._lock:
            self._running = False
            if self._current is not None:
                self._current.cancel()
                self._current = None

    def _schedule(self) -> None:
        t = threading.Timer(self._interval_s, self._fire)
        t.daemon = True
        with self._lock:
            self._current = t
        t.start()

    def _fire(self) -> None:
        with self._lock:
            if not self._running:
                return
        self._callback()
        with self._lock:
            if self._running:
                self._schedule()


class ThreadingTimerFactory(ITimerFactory):
    """
    Production timer using threading.Timer — no Qt dependency.

    Creates recurring timers that expose start()/stop() interface,
    matching the contract expected by FileWatcher.
    All timers are daemon threads so they don't block process exit.
    """

    def create_timer(self, interval_ms: int, callback: Callable) -> _ThreadingTimerHandle:
        """Create a daemon-threaded recurring timer handle.

        Input: interval_ms — int, firing period in milliseconds (> 0);
               callback — Callable[[], None], invoked on each interval tick.
        Output: _ThreadingTimerHandle — call .start() to begin firing, .stop() to cancel.
        Invariants: returned timer is not yet running; start() must be called explicitly.
        """
        return _ThreadingTimerHandle(interval_ms / 1000.0, callback)


class RealFileSystem(IFileSystem):
    """실제 OS 파일 시스템 구현"""

    def read_file(self, path: str) -> bytes:
        """Read and return the raw bytes of the file at path.

        Input: path — str, file path to read.
        Output: bytes — full file contents.
        Raises: FileNotFoundError — if path does not exist; OSError on permission errors.
        """
        with open(path, "rb") as f:
            return f.read()

    def write_file(self, path: str, data: bytes) -> None:
        """Write bytes to path, creating parent directories as needed.

        Input: path — str, destination file path; data — bytes to write.
        Output: None
        Raises: OSError — on permission errors or disk-full conditions.
        Invariants: parent directories are created with exist_ok=True before writing.
        """
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def stat(self, path: str) -> os.stat_result:
        """Return os.stat_result for the file at path.

        Input: path — str, file or directory path.
        Output: os.stat_result — metadata including size and modification time.
        Raises: FileNotFoundError — if path does not exist.
        """
        return os.stat(path)

    def exists(self, path: str) -> bool:
        """Return True if the path exists on the filesystem.

        Input: path — str, file or directory path to check.
        Output: bool — True if the path exists, False otherwise.
        """
        return os.path.exists(path)


class IExportRenderer(ABC):
    """Abstract interface for chart-to-image rendering.

    Implementations provide Qt, headless, or test rendering backends.
    """

    @abstractmethod
    def render_to_png(self, widget, width: int, height: int, dpi: int = 96) -> bytes:
        """Render a Qt widget/scene to PNG bytes.

        Args:
            widget: The Qt widget or scene to render.
            width: Output width in pixels.
            height: Output height in pixels.
            dpi: Dots per inch for the output.

        Returns:
            PNG image as bytes.
        """

    @abstractmethod
    def render_to_svg(self, widget, width: int, height: int) -> bytes:
        """Render a Qt widget/scene to SVG bytes.

        Args:
            widget: The Qt widget or scene to render.
            width: Output width in pixels.
            height: Output height in pixels.

        Returns:
            SVG XML as bytes.
        """

    @abstractmethod
    def render_to_pdf(self, widget, width: int, height: int, options=None) -> bytes:
        """Render a Qt widget/scene to PDF bytes.

        Args:
            widget: The Qt widget or scene to render.
            width: Output width in pixels.
            height: Output height in pixels.
            options: ExportOptions instance (dpi, page_size, include_stats, stats_data).

        Returns:
            PDF document as bytes.
        """


def atomic_write(path: str, data: bytes) -> None:
    """Write data to path atomically using write-fsync-rename (PRD Section 10.3).

    Input: path — str, destination file path; data — bytes to persist.
    Output: None
    Raises: OSError, IOError, PermissionError — on write or rename failure; the
            temporary file is cleaned up before re-raising.
    Invariants: on success, path contains exactly data; no partial writes are visible;
                parent directories are created as needed.
    """
    tmp_path = path + ".tmp"
    try:
        # 부모 디렉토리 보장
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        os.rename(tmp_path, path)
    except (OSError, IOError, PermissionError):
        # 실패 시 임시 파일 정리
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise
