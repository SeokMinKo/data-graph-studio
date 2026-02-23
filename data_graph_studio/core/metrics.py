"""Lightweight in-process metrics for observability."""
import time
import threading
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TimerSample:
    """A single duration measurement."""
    name: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """
    Thread-safe in-process metrics collector.

    Tracks counters and timers. Logs a summary periodically.

    Usage:
        metrics = get_metrics()
        metrics.increment("file.loaded")
        with metrics.timer("query.duration"):
            run_query()
    """

    def __init__(self):
        """Initialise an empty, thread-safe metrics collector.

        Output: None
        Invariants: all counters start at 0; all timer sample lists start empty
        """
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._timers: Dict[str, List[float]] = defaultdict(list)

    def increment(self, name: str, count: int = 1) -> None:
        """Increment a named counter by count.

        Input: name — str, counter key
               count — int, amount to add (default 1)
        Output: None
        Invariants: counter for name is created at 0 if not previously seen
        """
        with self._lock:
            self._counters[name] += count

    def record_duration(self, name: str, duration_ms: float) -> None:
        """Record a duration sample for the named timer.

        Input: name — str, timer key
               duration_ms — float, elapsed time in milliseconds
        Output: None
        Invariants: at most 100 samples are kept per timer; oldest samples are discarded when the cap is exceeded
        """
        with self._lock:
            self._timers[name].append(duration_ms)
            # keep last 100 samples per timer
            if len(self._timers[name]) > 100:
                self._timers[name] = self._timers[name][-100:]

    def timer(self, name: str) -> "TimerContext":
        """Return a context manager that records elapsed time for a named timer.

        Input: name — str, timer key to record under
        Output: TimerContext — context manager; call via `with metrics.timer("name"):`
        """
        return TimerContext(self, name)

    def timed_operation(self, name: str) -> "TimedOperationContext":
        """Return a context manager that times a block, counts calls, and tracks errors.

        On enter: increments {name}.count.
        On exit: records elapsed duration via record_duration.
        On exception: increments {name}.error; exception is never suppressed.

        Input: name — str, base key; sub-keys {name}.count and {name}.error are auto-managed
        Output: TimedOperationContext — context manager; call via `with metrics.timed_operation("name"):`
        """
        return TimedOperationContext(self, name)

    def snapshot(self) -> Dict:
        """Return a thread-safe snapshot of all current counters and timer statistics.

        Output: Dict — {"counters": {name: int}, "timers": {name: {"count", "mean_ms", "min_ms", "max_ms"}}}
        Invariants: timers with no samples are omitted from the output
        """
        with self._lock:
            result = {"counters": dict(self._counters), "timers": {}}
            for name, samples in self._timers.items():
                if samples:
                    result["timers"][name] = {
                        "count": len(samples),
                        "mean_ms": sum(samples) / len(samples),
                        "min_ms": min(samples),
                        "max_ms": max(samples),
                    }
            return result

    def log_summary(self) -> None:
        """Log the current metrics snapshot as a structured INFO log entry.

        Output: None
        Invariants: calls snapshot() once; emits a single log record at INFO level
        """
        snap = self.snapshot()
        logger.info("metrics.summary", extra={
            "counters": snap["counters"],
            "timers": snap["timers"],
        })

    def reset(self) -> None:
        """Clear all counters and timer samples.

        Output: None
        Invariants: all counter and timer dicts are empty after return; thread-safe
        """
        with self._lock:
            self._counters.clear()
            self._timers.clear()


class TimerContext:
    """Context manager for timing code blocks."""

    def __init__(self, collector: MetricsCollector, name: str):
        """Initialise the timer context.

        Input: collector — MetricsCollector, collector to record the duration into
               name — str, timer key passed to record_duration
        Output: None
        """
        self._collector = collector
        self._name = name
        self._start: Optional[float] = None

    def __enter__(self) -> "TimerContext":
        """Record the start timestamp and return self.

        Output: TimerContext — self, for use in with-statement target
        """
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        """Compute elapsed time and record it via the collector.

        Output: None
        Invariants: duration is only recorded if __enter__ was called; returns None (does not suppress exceptions)
        """
        if self._start is not None:
            elapsed_ms = (time.perf_counter() - self._start) * 1000
            self._collector.record_duration(self._name, elapsed_ms)


class TimedOperationContext:
    """Context manager that times a block, counts calls, and tracks errors.

    - Increments ``{name}.count`` on entry.
    - Records duration in milliseconds on exit.
    - Increments ``{name}.error`` if an exception propagates.
    - Never suppresses exceptions.
    """

    def __init__(self, collector: MetricsCollector, name: str):
        """Initialise the timed operation context.

        Input: collector — MetricsCollector, collector to record counters and duration into
               name — str, base key; {name}.count and {name}.error sub-keys are auto-managed
        Output: None
        """
        self._collector = collector
        self._name = name
        self._start: Optional[float] = None

    def __enter__(self) -> "TimedOperationContext":
        """Increment the call counter and start the timer.

        Output: TimedOperationContext — self, for use in with-statement target
        """
        self._collector.increment(f"{self._name}.count")
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Record elapsed duration and increment error counter if an exception occurred.

        Input: exc_type — type or None, exception type if raised in the block
               exc_val — BaseException or None, exception instance
               exc_tb — traceback or None
        Output: bool — always False (exceptions are never suppressed)
        """
        if self._start is not None:
            elapsed_ms = (time.perf_counter() - self._start) * 1000
            self._collector.record_duration(self._name, elapsed_ms)
        if exc_type is not None:
            self._collector.increment(f"{self._name}.error")
        return False


# Global singleton
_metrics: Optional[MetricsCollector] = None
_metrics_lock = threading.Lock()


def get_metrics() -> MetricsCollector:
    """Return the process-wide MetricsCollector singleton, creating it on first call.

    Output: MetricsCollector — the global singleton instance
    Invariants: same instance is returned on every subsequent call; creation is thread-safe
    """
    global _metrics
    if _metrics is None:
        with _metrics_lock:
            if _metrics is None:
                _metrics = MetricsCollector()
    return _metrics
