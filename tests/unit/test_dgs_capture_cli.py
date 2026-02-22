from unittest.mock import MagicMock, patch
import json
from pathlib import Path


def test_cli_connect_mode_sends_ipc_command():
    """--connect mode: sends capture IPC command to running DGS."""
    mock_response = {
        "status": "ok",
        "captures": [
            {"name": "graph_panel", "file": "/tmp/graph_panel.png",
             "state": {"visible": True}, "summary": "graph_panel: ok", "error": None}
        ]
    }
    with patch("data_graph_studio.tools.dgs_capture.IPCClient") as MockClient:
        instance = MockClient.return_value
        instance.connect.return_value = True
        instance.send_command.return_value = mock_response

        from data_graph_studio.tools.dgs_capture import run_connect_mode
        result = run_connect_mode(target="graph_panel", output_dir=Path("/tmp"))

    instance.send_command.assert_called_once_with(
        "capture", target="graph_panel", output_dir="/tmp", format="png"
    )
    assert result["status"] == "ok"


def test_cli_connect_mode_fails_gracefully_when_no_dgs():
    """--connect mode: returns error dict when DGS not running."""
    with patch("data_graph_studio.tools.dgs_capture.IPCClient") as MockClient:
        instance = MockClient.return_value
        instance.connect.return_value = False  # DGS not running

        from data_graph_studio.tools.dgs_capture import run_connect_mode
        result = run_connect_mode(target="all", output_dir=Path("/tmp"))

    assert result["status"] == "error"
    assert "not running" in result["message"]
