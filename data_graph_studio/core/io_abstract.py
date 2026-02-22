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
        """파일 읽기. 존재하지 않으면 FileNotFoundError."""
        ...

    @abstractmethod
    def write_file(self, path: str, data: bytes) -> None:
        """파일 쓰기. 부모 디렉토리가 없으면 생성."""
        ...

    @abstractmethod
    def stat(self, path: str) -> os.stat_result:
        """파일 stat. 존재하지 않으면 FileNotFoundError."""
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """파일/디렉토리 존재 여부."""
        ...


class ITimerFactory(ABC):
    """타이머 추상화 — FileWatcher, 테스트에서 Mock 가능"""

    @abstractmethod
    def create_timer(self, interval_ms: int, callback: Callable) -> Any:
        """주기적 타이머 생성. 반환값은 구현에 따라 다름."""
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
        if self._running:
            return
        self._running = True
        self._schedule()

    def stop(self) -> None:
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
        """Create a recurring timer handle. Call .start() to begin firing."""
        return _ThreadingTimerHandle(interval_ms / 1000.0, callback)


class RealFileSystem(IFileSystem):
    """실제 OS 파일 시스템 구현"""

    def read_file(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    def write_file(self, path: str, data: bytes) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def stat(self, path: str) -> os.stat_result:
        return os.stat(path)

    def exists(self, path: str) -> bool:
        return os.path.exists(path)


def atomic_write(path: str, data: bytes) -> None:
    """
    원자적 파일 저장 — PRD Section 10.3

    temp 파일에 쓰고 → fsync → rename.
    POSIX에서 rename은 원자적이므로 중간 상태 없음.
    실패 시 temp 파일 정리.
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
    except Exception:
        # 실패 시 임시 파일 정리
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise
