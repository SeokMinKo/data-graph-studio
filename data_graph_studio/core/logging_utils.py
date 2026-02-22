"""Structured logging formatter and helpers."""

import logging
import time

_RESERVED_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "message",
    "taskName",
})


class StructuredFormatter(logging.Formatter):
    """
    Formats log records as key=value pairs for machine-parseable output.

    Output format:
        ts=<iso> level=<LEVEL> logger=<name> msg=<message> [key=value ...]
    """

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created))
        parts = [
            f"ts={ts}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"msg={record.message}",
        ]
        for key, val in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                parts.append(f"{key}={val}")
        if record.exc_info:
            parts.append(f"exc={self.formatException(record.exc_info)}")
        return " ".join(parts)
