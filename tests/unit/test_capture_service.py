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


def test_state_includes_data_loaded():
    """If widget has a data_loaded property, include it in state."""
    from data_graph_studio.ui.capture_service import CaptureService
    from data_graph_studio.core.capture_protocol import CaptureRequest
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 800
    mock_widget.height.return_value = 600
    mock_widget.data_loaded = True
    svc.register_panel("graph_panel", mock_widget)

    with patch.object(svc, "_grab_widget", return_value=Path("/tmp/graph.png")):
        results = svc.capture(CaptureRequest(target="graph_panel", output_dir=Path("/tmp")))

    assert results[0].state.get("data_loaded") is True


def test_capture_all_skips_window_when_not_registered(tmp_path):
    """target='all' should not crash when no window widget is registered."""
    svc = CaptureService()
    mock_widget = MagicMock()
    svc.register_panel("graph_panel", mock_widget)

    with patch.object(svc, "_grab_widget", return_value=tmp_path / "graph.png"):
        results = svc.capture(CaptureRequest(target="all", output_dir=tmp_path))

    names = [r.name for r in results]
    assert "graph_panel" in names
    assert "window" not in names  # window not registered → should not appear


def test_capture_filenames_are_unique_for_rapid_captures(tmp_path):
    """Rapid successive captures must produce unique filenames."""
    svc = CaptureService()
    mock_widget = MagicMock()
    svc.register_panel("graph_panel", mock_widget)

    paths_seen = set()

    def fake_grab(widget, file_path):
        paths_seen.add(str(file_path))
        return file_path

    with patch.object(svc, "_grab_widget", side_effect=fake_grab):
        req = CaptureRequest(target="graph_panel", output_dir=tmp_path)
        svc.capture(req)
        svc.capture(req)
        svc.capture(req)

    assert len(paths_seen) == 3, f"Expected 3 unique paths, got {len(paths_seen)}: {paths_seen}"
