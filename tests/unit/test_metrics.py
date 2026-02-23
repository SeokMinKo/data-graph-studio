from data_graph_studio.core.metrics import MetricsCollector
import threading

def test_counter_increment():
    m = MetricsCollector()
    m.increment("test.event")
    m.increment("test.event")
    assert m.snapshot()["counters"]["test.event"] == 2

def test_timer_records_duration():
    import time
    m = MetricsCollector()
    with m.timer("test.op"):
        time.sleep(0.01)
    snap = m.snapshot()
    assert "test.op" in snap["timers"]
    assert snap["timers"]["test.op"]["mean_ms"] >= 5

def test_thread_safety():
    m = MetricsCollector()
    threads = [threading.Thread(target=lambda: m.increment("x", 1)) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert m.snapshot()["counters"]["x"] == 100

def test_snapshot_is_independent():
    m = MetricsCollector()
    m.increment("a")
    snap1 = m.snapshot()
    m.increment("a")
    snap2 = m.snapshot()
    assert snap1["counters"]["a"] == 1
    assert snap2["counters"]["a"] == 2


def test_timed_operation_records_duration():
    m = MetricsCollector()
    with m.timed_operation("test.op"):
        pass
    snap = m.snapshot()
    assert "test.op" in snap["timers"]
    assert snap["timers"]["test.op"]["count"] == 1


def test_timed_operation_increments_counter():
    m = MetricsCollector()
    with m.timed_operation("test.op"):
        pass
    snap = m.snapshot()
    assert snap["counters"].get("test.op.count", 0) == 1


def test_timed_operation_records_error():
    m = MetricsCollector()
    try:
        with m.timed_operation("test.op"):
            raise ValueError("boom")
    except ValueError:
        pass
    snap = m.snapshot()
    assert snap["counters"].get("test.op.error", 0) == 1


def test_timed_operation_does_not_suppress_exceptions():
    import pytest
    m = MetricsCollector()
    with pytest.raises(RuntimeError, match="should propagate"):
        with m.timed_operation("test.op"):
            raise RuntimeError("should propagate")


def test_timed_operation_still_records_duration_on_error():
    m = MetricsCollector()
    try:
        with m.timed_operation("test.op"):
            raise ValueError("boom")
    except ValueError:
        pass
    snap = m.snapshot()
    assert "test.op" in snap["timers"]
    assert snap["timers"]["test.op"]["count"] == 1


def test_timed_operation_multiple_calls_accumulate():
    m = MetricsCollector()
    for _ in range(3):
        with m.timed_operation("test.op"):
            pass
    snap = m.snapshot()
    assert snap["timers"]["test.op"]["count"] == 3
    assert snap["counters"]["test.op.count"] == 3
