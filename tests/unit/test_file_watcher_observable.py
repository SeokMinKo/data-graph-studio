"""FileWatcher uses Observable pattern, not Qt signals."""
from data_graph_studio.core.file_watcher import FileWatcher
from data_graph_studio.core.observable import Observable


def test_file_watcher_is_observable():
    assert issubclass(FileWatcher, Observable)


def test_file_watcher_is_not_qobject():
    try:
        from PySide6.QtCore import QObject
        assert not issubclass(FileWatcher, QObject)
    except ImportError:
        pass


def test_file_changed_event_fires(tmp_path):
    """file_changed event fires when file modification is detected."""
    from data_graph_studio.core.io_abstract import ITimerFactory, RealFileSystem

    class NullTimerFactory(ITimerFactory):
        """Timer factory that never fires (for unit tests that call _check_file manually)."""
        def create_timer(self, interval_ms, callback):
            class NullTimer:
                def stop(self): pass
                def cancel(self): pass
            return NullTimer()

    test_file = tmp_path / "test.csv"
    test_file.write_bytes(b"a,b\n1,2\n")

    received = []
    watcher = FileWatcher(fs=RealFileSystem(), timer_factory=NullTimerFactory())
    watcher.subscribe("file_changed", received.append)
    watcher.watch(str(test_file))

    # Simulate file modification and trigger check
    import time; time.sleep(0.01)  # ensure mtime advances
    test_file.write_bytes(b"a,b\n1,2\n3,4\n")
    watcher._check_file(str(test_file))
    assert str(test_file) in received
