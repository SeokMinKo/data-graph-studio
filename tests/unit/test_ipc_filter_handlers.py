import os
import tempfile
from unittest.mock import MagicMock

from data_graph_studio.ui.controllers.ipc_controller import IPCController


def _make_controller():
    """Build IPCController with a mock MainWindow."""
    w = MagicMock()
    w.state.add_filter = MagicMock()
    w.state.clear_filters = MagicMock()
    ctrl = IPCController.__new__(IPCController)
    ctrl._w = w
    return ctrl


def test_ipc_apply_filter_calls_state():
    ctrl = _make_controller()
    result = ctrl._ipc_apply_filter(column="region", op="eq", value="Asia")
    ctrl._w.state.add_filter.assert_called_once_with("region", "eq", "Asia")
    assert result["status"] == "ok"


def test_ipc_clear_filters_calls_state():
    ctrl = _make_controller()
    result = ctrl._ipc_clear_filters()
    ctrl._w.state.clear_filters.assert_called_once()
    assert result["status"] == "ok"


def test_ipc_apply_filter_returns_error_on_exception():
    ctrl = _make_controller()
    ctrl._w.state.add_filter.side_effect = ValueError("bad column")
    result = ctrl._ipc_apply_filter(column="nope", op="eq", value="x")
    assert result["status"] == "error"
    assert "bad column" in result["message"]


def test_ipc_load_file_returns_status_ok_on_success():
    ctrl = _make_controller()
    ctrl._w.engine.load_dataset.return_value = "dataset-abc"
    ctrl._w.engine.get_dataset.return_value = MagicMock(
        name="sales", row_count=10, column_count=3, memory_bytes=1024
    )

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"a,b,c\n1,2,3\n")
        path = f.name

    try:
        result = ctrl._ipc_load_file(path)
    finally:
        os.unlink(path)

    assert result["status"] == "ok"
    assert result["dataset_id"] == "dataset-abc"


def test_ipc_load_file_returns_status_error_when_engine_fails():
    ctrl = _make_controller()
    ctrl._w.engine.load_dataset.return_value = None

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"a,b\n1,2\n")
        path = f.name

    try:
        result = ctrl._ipc_load_file(path)
    finally:
        os.unlink(path)

    assert result["status"] == "error"
