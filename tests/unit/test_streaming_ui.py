"""
Tests for streaming UI integration:
- StreamingDialog
- MainWindow streaming toolbar & menu actions
- StreamingController signal wiring
"""

import pytest
from unittest.mock import MagicMock


from data_graph_studio.ui.dialogs.streaming_dialog import StreamingDialog
from data_graph_studio.core.streaming_controller import StreamingController
from data_graph_studio.core.io_abstract import IFileSystem, ITimerFactory


# ── Fixtures ──────────────────────────────────────────────


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


# ── StreamingDialog tests ─────────────────────────────────


class TestStreamingDialog:
    def test_default_values(self, qtbot):
        dlg = StreamingDialog()
        qtbot.addWidget(dlg)
        assert dlg.file_path is None
        assert dlg.interval_ms == 1000
        assert dlg.mode == "tail"

    def test_initial_values(self, qtbot):
        dlg = StreamingDialog(
            initial_path="/tmp/data.csv",
            initial_interval_ms=2000,
            initial_mode="reload",
        )
        qtbot.addWidget(dlg)
        assert dlg._file_edit.text() == "/tmp/data.csv"
        assert dlg._interval_spin.value() == 2000
        assert dlg._mode_combo.currentData() == "reload"

    def test_accept_sets_properties(self, qtbot):
        dlg = StreamingDialog()
        qtbot.addWidget(dlg)
        dlg._file_edit.setText("/tmp/test.csv")
        dlg._interval_spin.setValue(3000)
        dlg._mode_combo.setCurrentIndex(1)  # reload
        dlg._on_accept()
        assert dlg.file_path == "/tmp/test.csv"
        assert dlg.interval_ms == 3000
        assert dlg.mode == "reload"

    def test_empty_path_does_not_accept(self, qtbot):
        dlg = StreamingDialog()
        qtbot.addWidget(dlg)
        dlg._file_edit.setText("")
        dlg._on_accept()
        # file_path should remain None (dialog not accepted)
        assert dlg.file_path is None


# ── StreamingController integration tests ─────────────────


class TestStreamingControllerSignals:
    def test_state_transitions(self, stub_fs, stub_timer):
        ctrl = StreamingController(fs=stub_fs, timer_factory=stub_timer)
        states = []
        ctrl.streaming_state_changed.connect(lambda s: states.append(s))

        assert ctrl.state == "off"

        ctrl.start("/tmp/data.csv", mode="tail")
        assert ctrl.state == "live"
        assert states[-1] == "live"

        ctrl.pause()
        assert ctrl.state == "paused"
        assert states[-1] == "paused"

        ctrl.resume()
        assert ctrl.state == "live"
        assert states[-1] == "live"

        ctrl.stop()
        assert ctrl.state == "off"
        assert states[-1] == "off"

    def test_start_failure(self, stub_timer):
        fs = MagicMock(spec=IFileSystem)
        fs.exists.return_value = False
        ctrl = StreamingController(fs=fs, timer_factory=stub_timer)
        result = ctrl.start("/nonexistent.csv")
        assert result is False
        assert ctrl.state == "off"

    def test_set_poll_interval(self, stub_fs, stub_timer):
        ctrl = StreamingController(fs=stub_fs, timer_factory=stub_timer)
        ctrl.set_poll_interval(5000)
        assert ctrl.poll_interval_ms == 5000

    def test_set_follow_tail(self, stub_fs, stub_timer):
        ctrl = StreamingController(fs=stub_fs, timer_factory=stub_timer)
        ctrl.set_follow_tail(True)
        assert ctrl.follow_tail is True

    def test_shutdown(self, stub_fs, stub_timer):
        ctrl = StreamingController(fs=stub_fs, timer_factory=stub_timer)
        ctrl.start("/tmp/data.csv")
        ctrl.shutdown()
        assert ctrl.state == "off"
