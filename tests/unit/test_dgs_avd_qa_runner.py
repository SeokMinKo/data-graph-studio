# tests/unit/test_dgs_avd_qa_runner.py
"""Unit tests for dgs_avd_qa_runner."""
from unittest.mock import patch, MagicMock
import pytest


def test_ipc_send_returns_status_ok():
    """_ipc_send() returns parsed JSON response dict."""
    import json
    from data_graph_studio.tools.dgs_avd_qa_runner import _ipc_send

    # Server appends \n to response
    fake_response = json.dumps({"status": "ok"}).encode() + b"\n"
    mock_sock = MagicMock()
    mock_sock.recv.return_value = fake_response

    with patch("data_graph_studio.tools.dgs_avd_qa_runner.read_port_file", return_value=None), \
         patch("socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__ = lambda s: mock_sock
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        result = _ipc_send({"cmd": "ping"})

    assert result["status"] == "ok"


def test_verify_block_layer_columns_passes_for_valid_df():
    """_verify_block_layer_columns() passes when required columns are present."""
    from data_graph_studio.tools.dgs_avd_qa_runner import _verify_block_layer_columns
    import polars as pl

    df = pl.DataFrame({
        "d2c_ms": [1.0, 2.0],
        "queue_depth": [1, 2],
        "iops": [100.0, 200.0],
        "cmd": ["R", "W"],
        "size_kb": [4.0, 8.0],
    })

    result = _verify_block_layer_columns(df)
    assert result["pass"] is True


def test_verify_block_layer_columns_fails_for_raw_event_df():
    """_verify_block_layer_columns() fails when only raw event columns present."""
    from data_graph_studio.tools.dgs_avd_qa_runner import _verify_block_layer_columns
    import polars as pl

    df = pl.DataFrame({
        "timestamp": [1000.0],
        "event": ["block_rq_issue"],
        "details": ["8,0 R 4096 () 1000 + 8 [kworker]"],
    })

    result = _verify_block_layer_columns(df)
    assert result["pass"] is False
    assert "d2c_ms" in result["missing"]


def test_build_report_contains_all_sections():
    """_build_report() produces markdown with required sections."""
    from data_graph_studio.tools.dgs_avd_qa_runner import _build_report

    scenarios = [
        {"name": "trace_capture", "status": "PASS", "notes": ""},
        {"name": "parse_ftrace", "status": "PASS", "notes": "100 rows"},
        {"name": "block_layer_columns", "status": "PASS", "notes": ""},
        {"name": "screenshot", "status": "PASS", "notes": "3 captures"},
    ]

    report = _build_report(scenarios, device="emulator-5554")

    assert "emulator-5554" in report
    assert "PASS" in report
    assert "trace_capture" in report
    assert "block_layer_columns" in report
