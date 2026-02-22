from pathlib import Path
from unittest.mock import MagicMock, patch
from data_graph_studio.core.capture_protocol import CaptureRequest, ICaptureService
from data_graph_studio.ui.capture_service import CaptureService


def test_capture_service_implements_interface():
    assert issubclass(CaptureService, ICaptureService)


def test_list_panels_returns_registered():
    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 800
    mock_widget.height.return_value = 600
    svc.register_panel("graph_panel", mock_widget)
    assert "graph_panel" in svc.list_panels()


def test_capture_unknown_target_returns_error():
    svc = CaptureService()
    req = CaptureRequest(target="nonexistent_panel", output_dir=Path("/tmp"))
    results = svc.capture(req)
    assert len(results) == 1
    assert results[0].error is not None


def test_capture_service_generates_summary():
    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 800
    mock_widget.height.return_value = 600
    svc.register_panel("stat_panel", mock_widget)

    with patch.object(svc, "_grab_widget", return_value=Path("/tmp/stat_panel.png")):
        req = CaptureRequest(target="stat_panel", output_dir=Path("/tmp"))
        results = svc.capture(req)

    assert len(results) == 1
    assert "stat_panel" in results[0].summary
    assert results[0].error is None
