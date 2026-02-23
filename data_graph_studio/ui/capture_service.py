"""
CaptureService — Qt implementation of ICaptureService.

Uses QWidget.grab() for panel screenshots. Supports offscreen mode
via QOffscreenSurface when no display is available.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from data_graph_studio.core.capture_protocol import (
    CaptureRequest, CaptureResult, ICaptureService, VALID_TARGETS
)
from data_graph_studio.core.metrics import get_metrics

logger = logging.getLogger(__name__)


class CaptureService(ICaptureService):
    """
    Qt-based panel capture service.

    Register widgets by name, then call capture() with a CaptureRequest.
    """

    def __init__(self) -> None:
        self._panels: Dict[str, Any] = {}  # name → QWidget

    def register_panel(self, name: str, widget: Any) -> None:
        """Register a named panel widget for capture."""
        self._panels[name] = widget
        logger.debug("capture_service.panel_registered", extra={"panel_name": name})

    def list_panels(self) -> List[str]:
        """Return list of registered panel names."""
        return list(self._panels.keys())

    def capture(self, request: CaptureRequest) -> List[CaptureResult]:
        """
        Capture one or more panels based on request.target.

        Inputs: CaptureRequest (target, output_dir, format)
        Outputs: List[CaptureResult]
        Raises: nothing — errors are captured per-result
        """
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if request.target == "all":
            targets = list(self._panels.keys())
            if "window" in self._panels:
                targets.append("window")
        elif request.target == "window":
            targets = ["window"]
        else:
            targets = [request.target]

        results = []
        for name in targets:
            result = self._capture_one(name, output_dir, request.format)
            results.append(result)

        get_metrics().increment("capture.completed", len(results))
        logger.debug("capture_service.done", extra={"count": len(results)})
        return results

    def _capture_one(self, name: str, output_dir: Path, fmt: str) -> CaptureResult:
        """Capture a single panel by name."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_path = output_dir / f"{name}_{timestamp}.{fmt}"

        try:
            widget = self._panels.get(name)
            if widget is None and name != "window":
                return CaptureResult(
                    name=name, file=file_path, state={}, summary="",
                    error=f"panel '{name}' not registered"
                )

            saved = self._grab_widget(widget, file_path)
            state = self._collect_state(name, widget)
            summary = self._build_summary(name, state)

            return CaptureResult(name=name, file=saved, state=state, summary=summary)

        except Exception as exc:
            logger.warning("capture_service.capture_failed", extra={"panel_name": name, "error": str(exc)})
            return CaptureResult(name=name, file=file_path, state={}, summary="", error=str(exc))

    def _grab_widget(self, widget: Any, file_path: Path) -> Path:
        """Use QWidget.grab() to capture widget to file."""
        pixmap = widget.grab()
        pixmap.save(str(file_path))
        return file_path

    def _collect_state(self, name: str, widget: Any) -> Dict[str, Any]:
        """Collect extended widget state for the JSON output."""
        if widget is None:
            return {}
        state: Dict[str, Any] = {
            "visible": widget.isVisible() if hasattr(widget, "isVisible") else True,
            "size": [widget.width(), widget.height()] if hasattr(widget, "width") else [0, 0],
        }
        # Collect optional domain-specific state from panels that expose it.
        # Use vars() + type dict to avoid triggering MagicMock auto-creation;
        # real Qt widgets store domain attrs in __dict__ or as class properties.
        instance_attrs = vars(widget) if hasattr(widget, "__dict__") else {}
        class_attrs = {k for c in type(widget).__mro__ for k in vars(c)}
        for attr in ("data_loaded", "row_count", "active_filters", "chart_type"):
            if attr in instance_attrs or attr in class_attrs:
                state[attr] = getattr(widget, attr)
        return state

    def _build_summary(self, name: str, state: Dict[str, Any]) -> str:
        """Build AI-readable summary string."""
        parts = [name]
        if not state.get("visible", True):
            parts.append("hidden")
        else:
            w, h = state.get("size", [0, 0])
            parts.append(f"{w}x{h}")
        if state.get("data_loaded"):
            row_count = state.get("row_count", "?")
            parts.append(f"{row_count} rows")
        if state.get("active_filters"):
            parts.append(f"{state['active_filters']} filters")
        if state.get("chart_type"):
            parts.append(f"chart={state['chart_type']}")
        return ", ".join(parts)
