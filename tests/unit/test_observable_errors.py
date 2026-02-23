"""
Error-path tests for the Observable event system.

Tests verify:
- Handler that raises: other handlers still run
- Emitting an event with no listeners: no crash
- Subscribe then unsubscribe: handler not called after unsubscribe
- Duplicate subscribe is a no-op
- Unsubscribing a handler that was never subscribed: no crash
"""

import logging
import pytest

from data_graph_studio.core.observable import Observable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Counter:
    """Simple callable that tracks call count and args."""
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    @property
    def count(self):
        return len(self.calls)


class _ConcreteObservable(Observable):
    """Minimal concrete subclass for testing."""
    pass


# ---------------------------------------------------------------------------
# Handler that raises — other handlers must still run
# ---------------------------------------------------------------------------

class TestHandlerExceptionIsolation:
    def test_second_handler_runs_when_first_raises(self):
        """If handler A raises, handler B registered for the same event still fires."""
        obs = _ConcreteObservable()
        counter = _Counter()

        def bad_handler(*args, **kwargs):
            raise ValueError("boom")

        obs.subscribe("test_event", bad_handler)
        obs.subscribe("test_event", counter)

        # Must not propagate the exception
        obs.emit("test_event", 42)

        assert counter.count == 1
        assert counter.calls[0][0] == (42,)

    def test_first_handler_runs_when_second_raises(self):
        """Handler registered before a raising handler still fires."""
        obs = _ConcreteObservable()
        counter = _Counter()

        def bad_handler(*args, **kwargs):
            raise RuntimeError("internal error")

        obs.subscribe("evt", counter)
        obs.subscribe("evt", bad_handler)

        obs.emit("evt", "payload")

        assert counter.count == 1

    def test_all_other_handlers_run_when_one_raises(self):
        """With N handlers where the middle one raises, the rest all still fire."""
        obs = _ConcreteObservable()
        counters = [_Counter() for _ in range(4)]

        def bad_handler(*args, **kwargs):
            raise Exception("middle failure")

        obs.subscribe("multi", counters[0])
        obs.subscribe("multi", counters[1])
        obs.subscribe("multi", bad_handler)
        obs.subscribe("multi", counters[2])
        obs.subscribe("multi", counters[3])

        obs.emit("multi")

        for i, c in enumerate(counters):
            assert c.count == 1, f"counter[{i}] was not called"

    def test_exception_in_handler_is_logged_not_raised(self, caplog):
        """A handler exception is logged at ERROR level and not re-raised."""
        obs = _ConcreteObservable()

        def exploding_handler(*args, **kwargs):
            raise TypeError("type mismatch")

        obs.subscribe("logged_evt", exploding_handler)

        with caplog.at_level(logging.ERROR):
            obs.emit("logged_evt")

        # emit() should not raise
        # Log record should contain something about the error
        error_msgs = [r.message for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_msgs) >= 1

    def test_emit_returns_none_even_when_handler_raises(self):
        """emit() always returns None regardless of handler errors."""
        obs = _ConcreteObservable()

        def raiser(*a, **kw):
            raise ValueError("whoops")

        obs.subscribe("e", raiser)
        result = obs.emit("e")
        assert result is None


# ---------------------------------------------------------------------------
# Emitting event with no listeners
# ---------------------------------------------------------------------------

class TestEmitNoListeners:
    def test_emit_unknown_event_does_not_crash(self):
        """Emitting an event that nobody subscribed to doesn't raise."""
        obs = _ConcreteObservable()
        try:
            obs.emit("ghost_event", 1, 2, key="value")
        except Exception as exc:
            pytest.fail(f"emit with no listeners raised: {exc}")

    def test_emit_after_all_unsubscribed_does_not_crash(self):
        """Emitting an event after all handlers are removed doesn't raise."""
        obs = _ConcreteObservable()
        counter = _Counter()
        obs.subscribe("evt", counter)
        obs.unsubscribe("evt", counter)

        try:
            obs.emit("evt", "data")
        except Exception as exc:
            pytest.fail(f"emit after unsubscribe raised: {exc}")

    def test_emit_with_no_listeners_returns_none(self):
        """emit() returns None when there are no listeners."""
        obs = _ConcreteObservable()
        result = obs.emit("nothing_here")
        assert result is None

    def test_emit_multiple_event_types_no_cross_contamination(self):
        """Emitting event A does not trigger handlers registered on event B."""
        obs = _ConcreteObservable()
        counter_b = _Counter()
        obs.subscribe("event_b", counter_b)

        obs.emit("event_a", "payload")  # no listeners for event_a
        assert counter_b.count == 0


# ---------------------------------------------------------------------------
# Subscribe then unsubscribe
# ---------------------------------------------------------------------------

class TestSubscribeUnsubscribe:
    def test_handler_not_called_after_unsubscribe(self):
        """A handler is not invoked after it has been unsubscribed."""
        obs = _ConcreteObservable()
        counter = _Counter()

        obs.subscribe("click", counter)
        obs.emit("click")
        assert counter.count == 1

        obs.unsubscribe("click", counter)
        obs.emit("click")
        assert counter.count == 1  # still 1, not 2

    def test_unsubscribe_nonregistered_handler_does_not_raise(self):
        """Unsubscribing a handler that was never registered is a no-op."""
        obs = _ConcreteObservable()
        counter = _Counter()

        try:
            obs.unsubscribe("nonexistent_event", counter)
        except Exception as exc:
            pytest.fail(f"unsubscribe raised: {exc}")

    def test_unsubscribe_only_removes_target_handler(self):
        """Unsubscribing handler A leaves handler B active."""
        obs = _ConcreteObservable()
        a = _Counter()
        b = _Counter()

        obs.subscribe("data", a)
        obs.subscribe("data", b)
        obs.unsubscribe("data", a)
        obs.emit("data", "payload")

        assert a.count == 0
        assert b.count == 1

    def test_subscribe_same_handler_twice_is_noop(self):
        """Subscribing the same handler twice results in it being called once."""
        obs = _ConcreteObservable()
        counter = _Counter()

        obs.subscribe("tick", counter)
        obs.subscribe("tick", counter)  # duplicate
        obs.emit("tick")

        assert counter.count == 1

    def test_resubscribe_after_unsubscribe_works(self):
        """A handler can be re-subscribed after being unsubscribed."""
        obs = _ConcreteObservable()
        counter = _Counter()

        obs.subscribe("ping", counter)
        obs.emit("ping")
        assert counter.count == 1

        obs.unsubscribe("ping", counter)
        obs.emit("ping")
        assert counter.count == 1  # not called while unsubscribed

        obs.subscribe("ping", counter)
        obs.emit("ping")
        assert counter.count == 2  # called again after re-subscribe


# ---------------------------------------------------------------------------
# Multiple independent events
# ---------------------------------------------------------------------------

class TestMultipleEvents:
    def test_handlers_isolated_by_event_name(self):
        """Handlers for different events don't interfere with each other."""
        obs = _ConcreteObservable()
        ca = _Counter()
        cb = _Counter()

        obs.subscribe("event_a", ca)
        obs.subscribe("event_b", cb)

        obs.emit("event_a")
        assert ca.count == 1
        assert cb.count == 0

        obs.emit("event_b")
        assert ca.count == 1
        assert cb.count == 1

    def test_emit_passes_args_to_handler(self):
        """emit passes positional and keyword args to the handler."""
        obs = _ConcreteObservable()
        received = []

        def handler(*args, **kwargs):
            received.append((args, kwargs))

        obs.subscribe("data", handler)
        obs.emit("data", 1, 2, key="val")

        assert len(received) == 1
        assert received[0] == ((1, 2), {"key": "val"})
