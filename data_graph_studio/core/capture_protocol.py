"""
Capture Protocol — value objects and ABC for panel screenshot capture.

No Qt dependencies. Used by both core (IPC handler) and ui (CaptureService).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


VALID_TARGETS = {
    "all", "window",
    "graph_panel", "table_panel", "filter_panel", "stat_panel",
    "details_panel", "summary_panel", "history_panel",
    "dashboard_panel", "comparison_stats_panel",
}


@dataclass
class CaptureRequest:
    """
    Spec for a capture operation.

    Inputs: target (panel name or "all"/"window"), output_dir, format
    """
    target: str
    output_dir: Path
    format: str = "png"


@dataclass
class CaptureResult:
    """
    Result of a single panel capture.

    error is None on success; set to a string on failure.
    """
    name: str
    file: Path
    state: Dict[str, Any]
    summary: str
    error: Optional[str] = None


class ICaptureService(ABC):
    """Abstract interface for panel capture implementations."""

    @abstractmethod
    def capture(self, request: CaptureRequest) -> List[CaptureResult]:
        """Capture one or more panels according to the request spec.

        Input: request — CaptureRequest with target panel name (or "all"/"window"),
               output_dir, and format.
        Output: List[CaptureResult] — one entry per panel captured; CaptureResult.error
                is None on success or a description string on failure.
        Raises: ValueError — if request.target is not in VALID_TARGETS.
        """
        ...

    @abstractmethod
    def list_panels(self) -> List[str]:
        """Return the list of currently registered panel names available for capture.

        Output: List[str] — panel name strings; subset of VALID_TARGETS.
        Invariants: does not modify service state.
        """
        ...
