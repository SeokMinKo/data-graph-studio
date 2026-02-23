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
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = defaultdict(int)
        self._timers: Dict[str, List[float]] = defaultdict(list)

    def increment(self, name: str, count: int = 1) -> None:
        """Increment a named counter."""
        with self._lock:
            self._counters[name] += count

    def record_duration(self, name: str, duration_ms: float) -> None:
        """Record a duration in milliseconds."""
        with self._lock:
            self._timers[name].append(duration_ms)
            # keep last 100 samples per timer
            if len(self._timers[name]) > 100:
                self._timers[name] = self._timers[name][-100:]

    def timer(self, name: str) -> "TimerContext":
        """Context manager to time a block."""
        return TimerContext(self, name)

    def timed_operation(self, name: str) -> "TimedOperationContext":
        """Context manager that times a block, increments a call counter, and tracks errors.

        On enter: increments ``{name}.count``.
        On exit: records elapsed duration via ``record_duration``.
        On exception: increments ``{name}.error`` (exception is never suppressed).
        """
        return TimedOperationContext(self, name)

    def snapshot(self) -> Dict:
        """Return a snapshot of current metrics."""
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
        """Log a metrics summary via structured logging."""
        snap = self.snapshot()
        logger.info("metrics.summary", extra={
            "counters": snap["counters"],
            "timers": snap["timers"],
        })

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._counters.clear()
            self._timers.clear()


class TimerContext:
    """Context manager for timing code blocks."""

    def __init__(self, collector: MetricsCollector, name: str):
        self._collector = collector
        self._name = name
        self._start: Optional[float] = None

    def __enter__(self) -> "TimerContext":
        """Start timing."""
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        """Record elapsed time."""
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
        self._collector = collector
        self._name = name
        self._start: Optional[float] = None

    def __enter__(self) -> "TimedOperationContext":
        self._collector.increment(f"{self._name}.count")
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
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
    """Get the global MetricsCollector instance (singleton)."""
    global _metrics
    if _metrics is None:
        with _metrics_lock:
            if _metrics is None:
                _metrics = MetricsCollector()
    return _metrics
