"""Tests for IPCController main-thread dispatcher.

The IPC server runs handlers in a background asyncio thread.
Qt UI calls must happen on the main thread.
_main_thread(fn) dispatches fn to main thread and returns result.
"""
import concurrent.futures
import queue
import threading
import pytest
from unittest.mock import MagicMock

from data_graph_studio.ui.controllers.ipc_controller import IPCController


def _make_controller():
    ctrl = IPCController.__new__(IPCController)
    ctrl._w = MagicMock()
    ctrl._work_queue = queue.SimpleQueue()
    return ctrl


def test_main_thread_calls_fn_directly_when_on_main_thread():
    ctrl = _make_controller()
    result = ctrl._main_thread(lambda: 42)
    assert result == 42


def test_main_thread_propagates_exception_when_on_main_thread():
    ctrl = _make_controller()

    def _raise():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        ctrl._main_thread(_raise)


def test_pump_work_queue_executes_fn_and_sets_future():
    ctrl = _make_controller()
    fut = concurrent.futures.Future()
    ctrl._work_queue.put((lambda: "hello", fut))
    ctrl._pump_work_queue()
    assert fut.result(timeout=1) == "hello"


def test_pump_work_queue_sets_exception_on_failure():
    ctrl = _make_controller()
    fut = concurrent.futures.Future()

    def bad():
        raise RuntimeError("oops")

    ctrl._work_queue.put((bad, fut))
    ctrl._pump_work_queue()
    with pytest.raises(RuntimeError, match="oops"):
        fut.result(timeout=1)  # noqa: F821 - pytest imported above


def test_pump_work_queue_is_noop_when_queue_empty():
    ctrl = _make_controller()
    ctrl._pump_work_queue()  # no exception


def test_main_thread_from_background_thread_dispatches_via_queue():
    ctrl = _make_controller()
    results = []

    def background():
        r = ctrl._main_thread(lambda: "from_bg")
        results.append(r)

    t = threading.Thread(target=background, daemon=True)
    t.start()

    # Simulate Qt main thread pump
    import time
    time.sleep(0.02)
    ctrl._pump_work_queue()
    t.join(timeout=2)
    assert results == ["from_bg"]
