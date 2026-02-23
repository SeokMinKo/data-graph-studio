"""DGS application exception hierarchy.

All application-defined exceptions inherit from DGSError.
This allows callers to catch DGSError for any app-level failure
or a specific subclass for targeted handling.

Error strategy: Exception-based (see GOAT code standard).
"""
from __future__ import annotations
from typing import Any


class DGSError(Exception):
    """Base exception for all data-graph-studio errors.

    Attributes:
        operation: Human-readable description of what was being attempted.
        context: Optional dict with extra diagnostic info (file, column, etc.)
    """
    def __init__(self, message: str, operation: str = "", context: dict[str, Any] | None = None) -> None:
        self.operation = operation
        self.context = context or {}
        super().__init__(message)

    def __str__(self) -> str:
        base = super().__str__()
        if self.operation:
            return f"[{self.operation}] {base}"
        return base


class DataLoadError(DGSError):
    """File loading or parsing failed."""


class QueryError(DGSError):
    """Data query, filter, or aggregation failed."""


class ExportError(DGSError):
    """Data or chart export failed."""


class ValidationError(DGSError):
    """Input validation failed at system boundary."""


class DatasetError(DGSError):
    """Dataset management operation failed (add, remove, activate)."""


class ConfigError(DGSError):
    """Configuration load or parse failed."""
