"""StreamingController must be testable without a Qt application instance."""

from unittest.mock import MagicMock

import pytest

from data_graph_studio.core.io_abstract import IFileSystem, ITimerFactory
from data_graph_studio.core.streaming_controller import StreamingController


# ── Stubs ──────────────────────────────────────────────────────────────────


class _StubFS(IFileSystem):
    def read_file(self, path):
        return b"col1,col2\n1,2\n3,4\n"

    def write_file(self, path, data):
        pass

    def stat(self, path):
        import os
        return os.stat_result((0, 0, 0, 0, 0, 0, 100, 0, 1000.0, 0))

    def exists(self, path):
        return True


class _StubTimerFactory(ITimerFactory):
    def create_timer(self, interval_ms, callback):
        timer = MagicMock()
        timer.start = MagicMock()
        timer.stop = MagicMock()
        return timer


@pytest.fixture
def stub_fs():
    return _StubFS()


@pytest.fixture
def stub_timer():
    return _StubTimerFactory()


@pytest.fixture
def ctrl(stub_fs, stub_timer):
    return StreamingController(fs=stub_fs, timer_factory=stub_timer)


# ── Tests ──────────────────────────────────────────────────────────────────


def test_streaming_controller_no_qt_required(stub_fs, stub_timer):
    """StreamingController can be instantiated without QApplication."""
    c = StreamingController(fs=stub_fs, timer_factory=stub_timer)
    assert c is not None
    assert c.state == "off"


def test_streaming_state_changed_event_fires(ctrl):
    """streaming_state_changed event fires on state transitions."""
    states = []
    ctrl.subscribe("streaming_state_changed", lambda s: states.append(s))

    ctrl.start("/tmp/data.csv")
    assert "live" in states

    ctrl.pause()
    assert "paused" in states

    ctrl.resume()
    assert states.count("live") == 2

    ctrl.stop()
    assert "off" in states


def test_subscribe_unsubscribe(ctrl):
    """subscribe/unsubscribe work correctly on StreamingController."""
    received = []

    def handler(s):
        received.append(s)

    ctrl.subscribe("streaming_state_changed", handler)
    ctrl.start("/tmp/data.csv")
    assert received == ["live"]

    ctrl.unsubscribe("streaming_state_changed", handler)
    ctrl.stop()
    # handler should not fire for "off"
    assert received == ["live"]


def test_initial_state_is_off(ctrl):
    assert ctrl.state == "off"


def test_poll_interval_and_follow_tail(ctrl):
    ctrl.set_poll_interval(5000)
    assert ctrl.poll_interval_ms == 5000

    ctrl.set_follow_tail(True)
    assert ctrl.follow_tail is True


def test_start_returns_true_on_success(ctrl):
    ok = ctrl.start("/tmp/data.csv")
    assert ok is True


def test_start_nonexistent_file_returns_false(stub_timer):
    """Start returns False when file does not exist."""

    class _NoFS(IFileSystem):
        def read_file(self, path):
            return b""

        def write_file(self, path, data):
            pass

        def stat(self, path):
            raise FileNotFoundError(path)

        def exists(self, path):
            return False

    ctrl = StreamingController(fs=_NoFS(), timer_factory=stub_timer)
    result = ctrl.start("/nonexistent.csv")
    assert result is False
    assert ctrl.state == "off"


def test_shutdown_stops_streaming(ctrl):
    ctrl.start("/tmp/data.csv")
    ctrl.shutdown()
    assert ctrl.state == "off"
