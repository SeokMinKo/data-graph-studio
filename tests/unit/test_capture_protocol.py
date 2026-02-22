from pathlib import Path
from data_graph_studio.core.capture_protocol import CaptureRequest, CaptureResult, ICaptureService

def test_capture_request_defaults():
    req = CaptureRequest(target="all", output_dir=Path("/tmp"))
    assert req.format == "png"
    assert req.target == "all"

def test_capture_request_specific_panel():
    req = CaptureRequest(target="graph_panel", output_dir=Path("/tmp/caps"))
    assert req.target == "graph_panel"

def test_capture_result_has_error_field():
    result = CaptureResult(
        name="graph_panel",
        file=Path("/tmp/graph_panel.png"),
        state={"visible": True},
        summary="graph_panel: ok"
    )
    assert result.error is None

def test_capture_result_with_error():
    result = CaptureResult(
        name="graph_panel",
        file=Path("/tmp/graph_panel.png"),
        state={},
        summary="",
        error="panel not found"
    )
    assert result.error == "panel not found"

def test_icapture_service_is_abstract():
    import inspect
    assert inspect.isabstract(ICaptureService)
