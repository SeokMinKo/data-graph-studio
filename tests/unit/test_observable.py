from data_graph_studio.core.observable import Observable


def test_subscribe_and_emit():
    obs = Observable()
    received = []
    obs.subscribe("data_changed", lambda v: received.append(v))
    obs.emit("data_changed", 42)
    assert received == [42]


def test_unsubscribe():
    obs = Observable()
    received = []

    def handler(v):
        received.append(v)

    obs.subscribe("data_changed", handler)
    obs.unsubscribe("data_changed", handler)
    obs.emit("data_changed", 99)
    assert received == []


def test_multiple_subscribers():
    obs = Observable()
    a, b = [], []
    obs.subscribe("ev", lambda v: a.append(v))
    obs.subscribe("ev", lambda v: b.append(v))
    obs.emit("ev", "hello")
    assert a == ["hello"]
    assert b == ["hello"]


def test_emit_unknown_event_does_not_raise():
    obs = Observable()
    obs.emit("nonexistent_event")  # must not raise


def test_duplicate_subscribe_is_noop():
    obs = Observable()
    received = []
    def handler(v):
        return received.append(v)
    obs.subscribe("ev", handler)
    obs.subscribe("ev", handler)  # duplicate
    obs.emit("ev", 1)
    assert received == [1]  # called only once
