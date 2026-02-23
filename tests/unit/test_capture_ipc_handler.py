from pathlib import Path
from unittest.mock import MagicMock, patch
from data_graph_studio.core.capture_protocol import CaptureRequest
from data_graph_studio.ui.capture_service import CaptureService


def test_capture_handler_calls_service():
    """Simulate what main_window wires: IPC command → CaptureService.capture()"""
    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 640
    mock_widget.height.return_value = 480
    svc.register_panel("filter_panel", mock_widget)

    with patch.object(svc, "_grab_widget", return_value=Path("/tmp/filter_panel.png")):
        req = CaptureRequest(target="filter_panel", output_dir=Path("/tmp"))
        results = svc.capture(req)

    assert len(results) == 1
    assert results[0].name == "filter_panel"
    assert results[0].error is None


def test_capture_handler_returns_json_serializable():
    """Result can be serialised to JSON for IPC response."""
    import json
    from dataclasses import asdict
    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 800
    mock_widget.height.return_value = 600
    svc.register_panel("table_panel", mock_widget)

    with patch.object(svc, "_grab_widget", return_value=Path("/tmp/table_panel.png")):
        results = svc.capture(CaptureRequest(target="table_panel", output_dir=Path("/tmp")))

    result_dict = asdict(results[0])
    result_dict["file"] = str(result_dict["file"])  # Path → str for JSON
    json.dumps(result_dict)  # must not raise
