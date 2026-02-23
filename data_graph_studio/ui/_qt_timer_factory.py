"""
Qt timer implementations for ITimerFactory.
"""

from PySide6.QtCore import QTimer

from ..core.io_abstract import ITimerFactory


class _QtTimerWrapper:
    """Wraps QTimer to match the start/stop interface expected by FileWatcher."""
    def __init__(self, interval_ms: int, callback):
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(callback)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()


class _QtTimerFactory(ITimerFactory):
    """Production timer factory using PySide6 QTimer."""
    def create_timer(self, interval_ms: int, callback):
        return _QtTimerWrapper(interval_ms, callback)
