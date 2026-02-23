"""
Pure Python observable/event system for core layer.
No Qt dependency. Core classes use this for event notification.
Qt UI wires up via adapter classes in ui/adapters/ that translate
Observable events to PySide6 Signals.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Observable:
    """
    Lightweight event emitter.

    Usage:
        class MyManager(Observable):
            def do_thing(self):
                self.emit("thing_done", result)

        manager = MyManager()
        manager.subscribe("thing_done", my_handler)
    """

    def __init__(self) -> None:
        """Initialize the Observable with an empty listener registry.

        Output: None
        Invariants: self._listeners is always a defaultdict(list)
        """
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable) -> None:
        """Register handler for event. Noop if already registered.

        Input: event — str, event name to listen for
               handler — Callable, function to invoke when the event fires
        Output: None
        Invariants: a given handler is registered at most once per event
        """
        if handler not in self._listeners[event]:
            self._listeners[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable) -> None:
        """Remove handler. Noop if not registered.

        Input: event — str, event name the handler was registered under
               handler — Callable, the handler to remove
        Output: None
        """
        try:
            self._listeners[event].remove(handler)
        except ValueError:
            pass

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Fire all handlers for event. Errors in handlers are logged, not raised.

        Input: event — str, event name to dispatch
               *args — positional arguments forwarded to each handler
               **kwargs — keyword arguments forwarded to each handler
        Output: None
        Invariants: handler exceptions are caught and logged; they never propagate to callers
        """
        for handler in list(self._listeners.get(event, [])):
            try:
                handler(*args, **kwargs)
            except Exception as exc:
                logger.error(
                    "observable handler error",
                    extra={
                        "event": event,
                        "handler": handler.__qualname__,
                        "error": str(exc),
                    },
                    exc_info=True,
                )
