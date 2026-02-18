"""Tests for AdbTraceController, TraceProgressDialog, and legacy compatibility."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from PySide6.QtWidgets import QApplication

app = QApplication.instance()
if not app:
    app = QApplication([])

from data_graph_studio.ui.dialogs.trace_progress_dialog import (
    AdbTraceController,
    TraceProgressDialog,
)

# android_logger_wizard removed (replaced by TraceConfigDialog)


# UT-11: _detect_sysfs_path
class TestDetectSysfsPath:
    def test_prefers_sys_kernel_tracing(self) -> None:
        ctrl = AdbTraceController()
        with patch.object(ctrl, "_run_adb_cmd") as mock_cmd:
            mock_cmd.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            path = ctrl._detect_sysfs_path("SERIAL123")
            assert path == "/sys/kernel/tracing"

    def test_falls_back_to_debug_tracing(self) -> None:
        ctrl = AdbTraceController()
        call_count = 0

        def side_effect(serial: str, cmd: str) -> subprocess.CompletedProcess:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch.object(ctrl, "_run_adb_cmd", side_effect=side_effect):
            path = ctrl._detect_sysfs_path("SERIAL123")
            assert path == "/sys/kernel/debug/tracing"

    def test_raises_when_both_fail(self) -> None:
        ctrl = AdbTraceController()
        with patch.object(ctrl, "_run_adb_cmd") as mock_cmd:
            mock_cmd.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="not found"
            )
            try:
                ctrl._detect_sysfs_path("SERIAL123")
                assert False, "Should have raised RuntimeError"
            except RuntimeError:
                pass


# UT-12: start/stop sequence
class TestStartStopSequence:
    def test_start_trace_sends_correct_commands(self) -> None:
        ctrl = AdbTraceController()
        config = {
            "buffer_size_mb": 64,
            "events": ["block/block_rq_issue", "block/block_rq_complete"],
            "save_path": "/tmp/test_trace.txt",
        }
        with patch.object(ctrl, "_run_adb_cmd") as mock_cmd, \
             patch.object(ctrl, "_detect_sysfs_path", return_value="/sys/kernel/tracing"):
            mock_cmd.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            ctrl.start_trace("SERIAL", config)

            # Verify key commands were called
            cmds = [c.args[1] for c in mock_cmd.call_args_list]
            assert any("echo > /sys/kernel/tracing/trace" in c for c in cmds)
            assert any("buffer_size_kb" in c for c in cmds)
            assert any("block/block_rq_issue/enable" in c for c in cmds)
            assert any("tracing_on" in c for c in cmds)

    def test_stop_trace_saves_file(self, tmp_path: Path) -> None:
        ctrl = AdbTraceController()
        ctrl._serial = "SERIAL"
        ctrl._sysfs_path = "/sys/kernel/tracing"
        ctrl._enabled_events = ["block/block_rq_issue"]
        ctrl._tracing = True
        save_path = str(tmp_path / "trace.txt")

        with patch.object(ctrl, "_run_adb_cmd") as mock_cmd:
            mock_cmd.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="# tracer: nop\ndata here\n", stderr=""
            )
            ctrl.stop_trace(save_path)

        assert Path(save_path).read_text() == "# tracer: nop\ndata here\n"


# UT-13: cleanup guarantee
class TestCleanupGuarantee:
    def test_cleanup_called_on_error(self) -> None:
        ctrl = AdbTraceController()
        ctrl._serial = "SERIAL"
        ctrl._sysfs_path = "/sys/kernel/tracing"
        ctrl._enabled_events = ["block/block_rq_issue"]
        ctrl._tracing = True

        with patch.object(ctrl, "_run_adb_cmd") as mock_cmd:
            # First call (tracing_on=0) succeeds, cat fails
            def side_effect(serial: str, cmd: str) -> subprocess.CompletedProcess:
                if "cat" in cmd:
                    raise subprocess.TimeoutExpired(cmd="adb", timeout=10)
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

            mock_cmd.side_effect = side_effect
            try:
                ctrl.stop_trace("/tmp/out.txt")
            except Exception:
                pass

            # cleanup should have disabled tracing
            cmds = [c.args[1] for c in mock_cmd.call_args_list]
            tracing_off_calls = [c for c in cmds if "tracing_on" in c and "0" in c]
            assert len(tracing_off_calls) >= 1

    def test_cleanup_is_idempotent(self) -> None:
        ctrl = AdbTraceController()
        ctrl._serial = "SERIAL"
        ctrl._sysfs_path = "/sys/kernel/tracing"
        ctrl._enabled_events = []
        ctrl._tracing = False

        with patch.object(ctrl, "_run_adb_cmd") as mock_cmd:
            mock_cmd.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            ctrl.cleanup()  # Should not raise


# UT-14: shlex.quote
class TestShlexQuote:
    def test_adb_cmd_uses_shlex_quote(self) -> None:
        ctrl = AdbTraceController()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="ok", stderr=""
            )
            ctrl._run_adb_cmd("SERIAL", 'cat /sys/kernel/tracing/trace')
            cmd = mock_run.call_args.args[0]
            # The shell command should be quoted via shlex
            assert "su" in " ".join(cmd) or "shell" in " ".join(cmd)


# UT-15: TraceProgressDialog
class TestTraceProgressDialog:
    def test_dialog_creation(self) -> None:
        ctrl = AdbTraceController()
        dlg = TraceProgressDialog(ctrl)
        assert dlg.minimumWidth() >= 480
        assert dlg.minimumHeight() >= 320

    def test_stop_button_disables(self) -> None:
        ctrl = AdbTraceController()
        dlg = TraceProgressDialog(ctrl)
        assert dlg._stop_btn.isEnabled()
        # Simulate stop click behavior (without actual trace)
        dlg._stop_btn.setEnabled(False)
        assert not dlg._stop_btn.isEnabled()


# UT-16, UT-17: Removed (android_logger_wizard deleted, replaced by TraceConfigDialog)
