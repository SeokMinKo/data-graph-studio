"""Unit tests for the parse_ftrace IPC command."""
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest


def _make_controller(tmp_path):
    """Build a minimal IPCController with a fake MainWindow."""
    from data_graph_studio.ui.controllers.ipc_controller import IPCController

    w = MagicMock()
    w.engine.load_dataset_from_dataframe.return_value = "ds-abc"
    w.engine.profile = None

    ctrl = IPCController.__new__(IPCController)
    ctrl._w = w
    ctrl._work_queue = __import__("queue").SimpleQueue()
    return ctrl, w


def test_parse_ftrace_returns_status_ok_with_existing_file(tmp_path):
    """parse_ftrace IPC command returns {status: ok} for a valid file path."""
    trace_file = tmp_path / "trace.txt"
    trace_file.write_text("# ftrace data\n")

    ctrl, w = _make_controller(tmp_path)

    with patch.object(w, "_parse_ftrace_async") as mock_parse:
        result = ctrl._ipc_parse_ftrace(str(trace_file))

    assert result["status"] == "ok"
    mock_parse.assert_called_once_with(str(trace_file), "blocklayer")


def test_parse_ftrace_accepts_custom_converter(tmp_path):
    """parse_ftrace IPC command passes converter argument through."""
    trace_file = tmp_path / "trace.txt"
    trace_file.write_text("# ftrace data\n")

    ctrl, w = _make_controller(tmp_path)

    with patch.object(w, "_parse_ftrace_async") as mock_parse:
        result = ctrl._ipc_parse_ftrace(str(trace_file), converter="raw")

    assert result["status"] == "ok"
    mock_parse.assert_called_once_with(str(trace_file), "raw")


def test_parse_ftrace_returns_error_for_missing_file(tmp_path):
    """parse_ftrace IPC command returns {status: error} if file doesn't exist."""
    ctrl, w = _make_controller(tmp_path)

    result = ctrl._ipc_parse_ftrace("/nonexistent/path/trace.txt")

    assert result["status"] == "error"
    assert "not found" in result["message"].lower()
