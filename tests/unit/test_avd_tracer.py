# tests/unit/test_avd_tracer.py
"""Unit tests for avd_tracer — adb-based ftrace capture utility."""
from unittest.mock import patch, MagicMock, call
import subprocess
import pytest


def test_list_devices_returns_emulator_serials():
    """list_devices() parses adb devices output and returns serial strings."""
    from data_graph_studio.tools.avd_tracer import list_devices

    mock_output = "List of devices attached\nemulator-5554\tdevice\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout=mock_output, stderr=""
        )
        devices = list_devices()

    assert "emulator-5554" in devices


def test_list_devices_returns_empty_when_no_devices():
    """list_devices() returns [] when no devices are connected."""
    from data_graph_studio.tools.avd_tracer import list_devices

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="List of devices attached\n", stderr=""
        )
        devices = list_devices()

    assert devices == []


def test_run_io_workload_issues_adb_dd_command():
    """run_io_workload() runs dd on the device via adb shell."""
    from data_graph_studio.tools.avd_tracer import run_io_workload

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_io_workload("emulator-5554", block_count=64)

    args = mock_run.call_args[0][0]
    assert "adb" in args
    assert "-s" in args
    assert "emulator-5554" in args
    assert "dd" in " ".join(args)


def test_pull_trace_calls_adb_pull(tmp_path):
    """pull_trace() calls 'adb pull' to retrieve the trace file."""
    from data_graph_studio.tools.avd_tracer import pull_trace

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        out = pull_trace("emulator-5554", str(tmp_path / "trace.txt"))

    assert mock_run.called
    args = mock_run.call_args[0][0]
    assert "adb" in args
    assert "pull" in args


def test_capture_block_trace_full_flow(tmp_path):
    """capture_block_trace() orchestrates the full capture pipeline."""
    from data_graph_studio.tools.avd_tracer import capture_block_trace

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        out_path = capture_block_trace(
            "emulator-5554",
            output_path=str(tmp_path / "trace.txt"),
            duration_sec=0,
            block_count=64,
        )

    # adb must have been called multiple times (setup + workload + pull)
    assert mock_run.call_count >= 3
    assert out_path == str(tmp_path / "trace.txt")
