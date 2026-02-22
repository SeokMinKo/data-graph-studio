"""Qt signal adapter for FileWatcher + QTimerFactory for Qt environments."""
from PySide6.QtCore import QObject, Signal, QTimer
from data_graph_studio.core.file_watcher import FileWatcher
from data_graph_studio.core.io_abstract import ITimerFactory


class _QtTimerHandle:
    """Wraps QTimer to expose start()/stop() interface expected by FileWatcher."""

    def __init__(self, interval_ms: int, callback) -> None:
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(callback)

    def start(self) -> None:
        """Start the underlying QTimer."""
        self._timer.start()

    def stop(self) -> None:
        """Stop the underlying QTimer."""
        self._timer.stop()


class QTimerFactory(ITimerFactory):
    """Qt-based timer factory. Use in Qt applications for event-loop integration."""

    def create_timer(self, interval_ms: int, callback) -> _QtTimerHandle:
        """Create a QTimer-backed handle that fires callback every interval_ms."""
        return _QtTimerHandle(interval_ms, callback)


class FileWatcherAdapter(QObject):
    """Wraps FileWatcher and re-emits Observable events as Qt Signals."""
    file_changed = Signal(str)
    file_deleted = Signal(str)
    rows_appended = Signal(str, int)

    def __init__(self, watcher: FileWatcher, parent=None):
        super().__init__(parent)
        self._watcher = watcher
        watcher.subscribe("file_changed", self.file_changed.emit)
        watcher.subscribe("file_deleted", self.file_deleted.emit)
        watcher.subscribe("rows_appended", self.rows_appended.emit)

    @property
    def watcher(self) -> FileWatcher:
        """Return the underlying FileWatcher instance."""
        return self._watcher
