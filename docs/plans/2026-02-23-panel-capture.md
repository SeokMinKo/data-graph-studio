# Panel Capture Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add CLI-accessible panel screenshot capture for AI-driven UI/UX debugging — allows AI agents to verify DGS renders correctly after refactoring.

**Architecture:** Extend existing asyncio IPC server with a `capture` command. `capture_protocol.py` in core defines ABC + value objects (no Qt). `capture_service.py` in ui holds the Qt `QWidget.grab()` implementation. CLI tool `dgs_capture.py` connects via IPC or launches DGS in headless capture mode.

**Tech Stack:** PySide6 (`QWidget.grab`, `QOffscreenSurface`), asyncio IPC (existing), Python 3.11+, pytest

---

## Task 1: capture_protocol.py — Value Objects + ABC

**Files:**
- Create: `data_graph_studio/core/capture_protocol.py`
- Create: `tests/unit/test_capture_protocol.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_capture_protocol.py
from pathlib import Path
from data_graph_studio.core.capture_protocol import CaptureRequest, CaptureResult, ICaptureService

def test_capture_request_defaults():
    req = CaptureRequest(target="all", output_dir=Path("/tmp"))
    assert req.format == "png"
    assert req.target == "all"

def test_capture_request_specific_panel():
    req = CaptureRequest(target="graph_panel", output_dir=Path("/tmp/caps"))
    assert req.target == "graph_panel"

def test_capture_result_has_error_field():
    result = CaptureResult(
        name="graph_panel",
        file=Path("/tmp/graph_panel.png"),
        state={"visible": True},
        summary="graph_panel: ok"
    )
    assert result.error is None

def test_capture_result_with_error():
    result = CaptureResult(
        name="graph_panel",
        file=Path("/tmp/graph_panel.png"),
        state={},
        summary="",
        error="panel not found"
    )
    assert result.error == "panel not found"

def test_icapture_service_is_abstract():
    import inspect
    assert inspect.isabstract(ICaptureService)
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/lov2fn/Projects/data-graph-studio
source .venv/bin/activate
pytest tests/unit/test_capture_protocol.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# data_graph_studio/core/capture_protocol.py
"""
Capture Protocol — value objects and ABC for panel screenshot capture.

No Qt dependencies. Used by both core (IPC handler) and ui (CaptureService).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    Invariants: target must be in VALID_TARGETS or "all"/"window"
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
        """
        Capture one or more panels.

        Inputs: CaptureRequest with target + output_dir
        Outputs: List of CaptureResult (one per panel captured)
        Raises: ValueError if target is invalid
        """
        ...

    @abstractmethod
    def list_panels(self) -> List[str]:
        """Return list of currently registered panel names."""
        ...
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_capture_protocol.py -v
```
Expected: 5 PASS

**Step 5: Commit**

```bash
git add data_graph_studio/core/capture_protocol.py tests/unit/test_capture_protocol.py
git commit -m "feat: add CaptureRequest/CaptureResult value objects and ICaptureService ABC"
```

---

## Task 2: capture_service.py — Qt Implementation

**Files:**
- Create: `data_graph_studio/ui/capture_service.py`
- Create: `tests/unit/test_capture_service.py`

**Step 1: Write the failing tests (using mock — no real Qt needed)**

```python
# tests/unit/test_capture_service.py
from pathlib import Path
from unittest.mock import MagicMock, patch
from data_graph_studio.core.capture_protocol import CaptureRequest, ICaptureService
from data_graph_studio.ui.capture_service import CaptureService


def test_capture_service_implements_interface():
    assert issubclass(CaptureService, ICaptureService)


def test_list_panels_returns_registered():
    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 800
    mock_widget.height.return_value = 600
    svc.register_panel("graph_panel", mock_widget)
    assert "graph_panel" in svc.list_panels()


def test_capture_unknown_target_returns_error():
    svc = CaptureService()
    req = CaptureRequest(target="nonexistent_panel", output_dir=Path("/tmp"))
    results = svc.capture(req)
    assert len(results) == 1
    assert results[0].error is not None


def test_capture_service_generates_summary():
    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 800
    mock_widget.height.return_value = 600
    svc.register_panel("stat_panel", mock_widget)

    with patch.object(svc, "_grab_widget", return_value=Path("/tmp/stat_panel.png")):
        req = CaptureRequest(target="stat_panel", output_dir=Path("/tmp"))
        results = svc.capture(req)

    assert len(results) == 1
    assert "stat_panel" in results[0].summary
    assert results[0].error is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_capture_service.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# data_graph_studio/ui/capture_service.py
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
        logger.debug("capture_service.panel_registered", extra={"name": name})

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
            targets = list(self._panels.keys()) + ["window"]
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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
            logger.warning("capture_service.capture_failed", extra={"name": name, "error": str(exc)})
            return CaptureResult(name=name, file=file_path, state={}, summary="", error=str(exc))

    def _grab_widget(self, widget: Any, file_path: Path) -> Path:
        """Use QWidget.grab() to capture widget to file."""
        from PySide6.QtWidgets import QApplication
        pixmap = widget.grab()
        pixmap.save(str(file_path))
        return file_path

    def _collect_state(self, name: str, widget: Any) -> Dict[str, Any]:
        """Collect basic widget state for the JSON output."""
        if widget is None:
            return {}
        return {
            "visible": widget.isVisible() if hasattr(widget, "isVisible") else True,
            "size": [widget.width(), widget.height()] if hasattr(widget, "width") else [0, 0],
        }

    def _build_summary(self, name: str, state: Dict[str, Any]) -> str:
        """Build human-readable summary string for AI consumption."""
        visible = state.get("visible", True)
        size = state.get("size", [0, 0])
        return f"{name}: {'visible' if visible else 'hidden'}, size={size[0]}x{size[1]}"
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_capture_service.py -v
```
Expected: 4 PASS

**Step 5: Commit**

```bash
git add data_graph_studio/ui/capture_service.py tests/unit/test_capture_service.py
git commit -m "feat: add CaptureService Qt implementation with QWidget.grab()"
```

---

## Task 3: Wire CaptureService into IPC Server + MainWindow

**Files:**
- Modify: `data_graph_studio/ui/main_window.py` (find `_setup_ipc_server` ~line 623)
- Create: `tests/unit/test_capture_ipc_handler.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_capture_ipc_handler.py
from pathlib import Path
from unittest.mock import MagicMock, patch
from data_graph_studio.core.capture_protocol import CaptureRequest, CaptureResult
from data_graph_studio.ui.capture_service import CaptureService


def test_capture_handler_calls_service():
    """Simulate what main_window wires: IPC command → CaptureService.capture()"""
    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 640
    mock_widget.height.return_value = 480
    svc.register_panel("filter_panel", mock_widget)

    with patch.object(svc, "_grab_widget", return_value=Path("/tmp/filter_panel.png")):
        req = CaptureRequest(target="filter_panel", output_dir=Path("/tmp"))
        results = svc.capture(req)

    assert len(results) == 1
    assert results[0].name == "filter_panel"
    assert results[0].error is None


def test_capture_handler_returns_json_serializable():
    """Result can be serialised to JSON for IPC response."""
    import json
    from dataclasses import asdict
    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 800
    mock_widget.height.return_value = 600
    svc.register_panel("table_panel", mock_widget)

    with patch.object(svc, "_grab_widget", return_value=Path("/tmp/table_panel.png")):
        results = svc.capture(CaptureRequest(target="table_panel", output_dir=Path("/tmp")))

    result_dict = asdict(results[0])
    result_dict["file"] = str(result_dict["file"])  # Path → str for JSON
    json.dumps(result_dict)  # must not raise
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_capture_ipc_handler.py -v
```
Expected: FAIL

**Step 3: Add capture handler registration to MainWindow**

In `data_graph_studio/ui/main_window.py`, find `_setup_ipc_server` (~line 623) and add:

```python
def _setup_ipc_server(self):
    # ... existing code ...

    # Add after existing handler registrations:
    from data_graph_studio.ui.capture_service import CaptureService
    from data_graph_studio.core.capture_protocol import CaptureRequest
    import dataclasses, json
    from pathlib import Path

    self._capture_service = CaptureService()
    # Register known panels — add more as needed
    self._capture_service.register_panel("graph_panel", self._graph_panel if hasattr(self, '_graph_panel') else None)
    self._capture_service.register_panel("table_panel", self._table_panel if hasattr(self, '_table_panel') else None)
    self._capture_service.register_panel("filter_panel", self._filter_panel if hasattr(self, '_filter_panel') else None)

    def _handle_capture(target="all", output_dir="/tmp/dgs_captures", format="png"):
        req = CaptureRequest(target=target, output_dir=Path(output_dir), format=format)
        results = self._capture_service.capture(req)
        # Convert to JSON-safe dicts
        serialised = []
        for r in results:
            d = dataclasses.asdict(r)
            d["file"] = str(d["file"])
            serialised.append(d)
        return {"status": "ok", "captures": serialised}

    self._ipc_server.register_handler("capture", _handle_capture)
```

Note: The panel widget attribute names (`_graph_panel`, `_table_panel`, etc.) — check the actual names in `MainWindow.__init__` and adjust.

**Step 4: Run tests**

```bash
pytest tests/unit/test_capture_ipc_handler.py -v
```
Expected: 2 PASS

**Step 5: Commit**

```bash
git add data_graph_studio/ui/main_window.py tests/unit/test_capture_ipc_handler.py
git commit -m "feat: wire CaptureService into IPC server capture handler"
```

---

## Task 4: CLI Tool — dgs_capture.py

**Files:**
- Create: `data_graph_studio/tools/__init__.py` (empty)
- Create: `data_graph_studio/tools/dgs_capture.py`
- Create: `tests/unit/test_dgs_capture_cli.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_dgs_capture_cli.py
from unittest.mock import MagicMock, patch
import json
from pathlib import Path


def test_cli_connect_mode_sends_ipc_command():
    """--connect mode: sends capture IPC command to running DGS."""
    mock_response = {
        "status": "ok",
        "captures": [
            {"name": "graph_panel", "file": "/tmp/graph_panel.png",
             "state": {"visible": True}, "summary": "graph_panel: ok", "error": None}
        ]
    }
    with patch("data_graph_studio.tools.dgs_capture.IPCClient") as MockClient:
        instance = MockClient.return_value
        instance.connect.return_value = True
        instance.send_command.return_value = mock_response

        from data_graph_studio.tools.dgs_capture import run_connect_mode
        result = run_connect_mode(target="graph_panel", output_dir=Path("/tmp"))

    instance.send_command.assert_called_once_with(
        "capture", target="graph_panel", output_dir="/tmp", format="png"
    )
    assert result["status"] == "ok"


def test_cli_connect_mode_fails_gracefully_when_no_dgs():
    """--connect mode: returns error dict when DGS not running."""
    with patch("data_graph_studio.tools.dgs_capture.IPCClient") as MockClient:
        instance = MockClient.return_value
        instance.connect.return_value = False  # DGS not running

        from data_graph_studio.tools.dgs_capture import run_connect_mode
        result = run_connect_mode(target="all", output_dir=Path("/tmp"))

    assert result["status"] == "error"
    assert "not running" in result["message"]
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_dgs_capture_cli.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write CLI tool**

```python
# data_graph_studio/tools/__init__.py
# (empty)

# data_graph_studio/tools/dgs_capture.py
"""
dgs_capture — CLI tool for AI-driven panel screenshot capture.

Usage:
    # Connect to running DGS
    python -m data_graph_studio.tools.dgs_capture --connect --target all

    # Specific panel
    python -m data_graph_studio.tools.dgs_capture --connect --target graph_panel

    # Headless (launch + capture + exit)
    python -m data_graph_studio.tools.dgs_capture --headless --target all
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any

from data_graph_studio.core.ipc_server import IPCClient

logger = logging.getLogger(__name__)


def run_connect_mode(target: str, output_dir: Path, fmt: str = "png") -> Dict[str, Any]:
    """
    Connect to a running DGS instance via IPC and send a capture command.

    Inputs: target (panel name or "all"), output_dir, fmt
    Outputs: dict with "status" and "captures"
    Raises: nothing — errors returned in dict
    """
    client = IPCClient()
    if not client.connect():
        return {"status": "error", "message": "DGS not running — start DGS first"}

    try:
        response = client.send_command(
            "capture",
            target=target,
            output_dir=str(output_dir),
            format=fmt
        )
        return response
    except Exception as exc:
        logger.warning("dgs_capture.ipc_error", extra={"error": str(exc)})
        return {"status": "error", "message": str(exc)}
    finally:
        client.disconnect()


def run_headless_mode(target: str, output_dir: Path, data_path: str = None) -> Dict[str, Any]:
    """
    Launch DGS in offscreen mode, capture panels, then exit.

    Inputs: target, output_dir, optional data_path to load
    Outputs: dict with "status" and "captures"
    """
    import subprocess
    import tempfile
    import time

    args = [
        sys.executable, "-m", "data_graph_studio",
        "--capture-mode",
        "--capture-target", target,
        "--capture-output", str(output_dir),
    ]
    if data_path:
        args += ["--data", data_path]

    result_file = output_dir / "_capture_result.json"
    args += ["--capture-result-file", str(result_file)]

    output_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(args, timeout=30, capture_output=True, text=True)

    if result_file.exists():
        return json.loads(result_file.read_text())
    return {"status": "error", "message": proc.stderr or "headless capture failed"}


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="DGS Panel Capture Tool (AI use)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--connect", action="store_true", help="Connect to running DGS")
    mode.add_argument("--headless", action="store_true", help="Launch DGS headless")

    parser.add_argument("--target", default="all",
                        help="Panel name, 'all', or 'window' (default: all)")
    parser.add_argument("--output-dir", default="/tmp/dgs_captures", type=Path)
    parser.add_argument("--data", help="Data file to load (headless mode only)")
    parser.add_argument("--format", default="png", dest="fmt")

    args = parser.parse_args()

    if args.connect:
        result = run_connect_mode(args.target, args.output_dir, args.fmt)
    else:
        result = run_headless_mode(args.target, args.output_dir, args.data)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_dgs_capture_cli.py -v
```
Expected: 2 PASS

**Step 5: Commit**

```bash
git add data_graph_studio/tools/ tests/unit/test_dgs_capture_cli.py
git commit -m "feat: add dgs_capture CLI tool for IPC + headless capture modes"
```

---

## Task 5: Headless Mode in MainWindow

**Files:**
- Modify: `data_graph_studio/ui/main_window.py` (find `__init__` ~line 121)
- Modify: `data_graph_studio/__main__.py` (or app entry point — check how DGS is launched)

**Step 1: Find the app entry point**

```bash
cat data_graph_studio/__main__.py
# or
grep -r "QApplication\|app.exec" data_graph_studio/ --include="*.py" -l | head -5
```

**Step 2: Add --capture-mode argument parsing**

In the main entry point (wherever `QApplication` is created), add:

```python
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--capture-mode", action="store_true")
parser.add_argument("--capture-target", default="all")
parser.add_argument("--capture-output", default="/tmp/dgs_captures")
parser.add_argument("--capture-result-file", default=None)
parser.add_argument("--data", default=None)
args, _ = parser.parse_known_args()

if args.capture_mode:
    # Use offscreen platform if no display
    import os
    if not os.environ.get("DISPLAY") and sys.platform != "darwin":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
```

**Step 3: Auto-capture and exit in MainWindow**

Add to `MainWindow.__init__` after full setup:

```python
import os
if "--capture-mode" in sys.argv:
    QTimer.singleShot(2000, self._run_capture_and_exit)  # 2s for UI to settle

def _run_capture_and_exit(self):
    """Used by headless capture mode: capture all panels then exit."""
    import argparse, json, dataclasses
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-target", default="all")
    parser.add_argument("--capture-output", default="/tmp/dgs_captures")
    parser.add_argument("--capture-result-file", default=None)
    args, _ = parser.parse_known_args()

    from data_graph_studio.core.capture_protocol import CaptureRequest
    req = CaptureRequest(target=args.capture_target, output_dir=Path(args.capture_output))
    results = self._capture_service.capture(req)

    output = {
        "status": "ok",
        "captures": [{**dataclasses.asdict(r), "file": str(r.file)} for r in results]
    }

    if args.capture_result_file:
        Path(args.capture_result_file).write_text(json.dumps(output, indent=2))

    QApplication.quit()
```

**Step 4: Manual smoke test**

```bash
# Start DGS normally in one terminal
python -m data_graph_studio &

# In another terminal, connect and capture
python -m data_graph_studio.tools.dgs_capture --connect --target all --output-dir /tmp/dgs_test
ls /tmp/dgs_test/
```

Expected: PNG files + any JSON

**Step 5: Commit**

```bash
git add data_graph_studio/ui/main_window.py data_graph_studio/__main__.py
git commit -m "feat: add --capture-mode headless support to MainWindow"
```

---

## Task 6: State JSON + Summary Enhancement

**Files:**
- Modify: `data_graph_studio/ui/capture_service.py`
- Modify: `tests/unit/test_capture_service.py` (add tests)

**Step 1: Add richer state collection tests**

```python
# Add to tests/unit/test_capture_service.py

def test_state_includes_data_loaded():
    """If widget has a data_loaded property, include it in state."""
    from data_graph_studio.ui.capture_service import CaptureService
    from pathlib import Path

    svc = CaptureService()
    mock_widget = MagicMock()
    mock_widget.isVisible.return_value = True
    mock_widget.width.return_value = 800
    mock_widget.height.return_value = 600
    mock_widget.data_loaded = True
    svc.register_panel("graph_panel", mock_widget)

    with patch.object(svc, "_grab_widget", return_value=Path("/tmp/graph.png")):
        results = svc.capture(CaptureRequest(target="graph_panel", output_dir=Path("/tmp")))

    assert results[0].state.get("data_loaded") is True
```

**Step 2: Enhance `_collect_state` in capture_service.py**

```python
def _collect_state(self, name: str, widget: Any) -> Dict[str, Any]:
    """Collect extended widget state for JSON output."""
    if widget is None:
        return {}
    state: Dict[str, Any] = {
        "visible": widget.isVisible() if hasattr(widget, "isVisible") else True,
        "size": [widget.width(), widget.height()] if hasattr(widget, "width") else [0, 0],
    }
    # Collect optional domain-specific state
    for attr in ("data_loaded", "row_count", "active_filters", "chart_type"):
        if hasattr(widget, attr):
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
```

**Step 3: Run all capture tests**

```bash
pytest tests/unit/test_capture_protocol.py tests/unit/test_capture_service.py tests/unit/test_capture_ipc_handler.py tests/unit/test_dgs_capture_cli.py -v
```
Expected: All PASS

**Step 4: Run full test suite**

```bash
source .venv/bin/activate
pytest tests/ -q --tb=short 2>&1 | tail -5
```
Expected: 2038+ passed

**Step 5: Commit**

```bash
git add data_graph_studio/ui/capture_service.py tests/unit/test_capture_service.py
git commit -m "feat: enhance CaptureService state collection and summary generation"
```

---

## Final: Merge + Verification

```bash
# From feature branch
git checkout master
git merge panel-capture --no-ff -m "feat: add AI-driven panel capture system via IPC + headless mode"
git push origin master
```

**Smoke test (if DGS is running):**
```bash
python -m data_graph_studio.tools.dgs_capture --connect --target all
# Should output JSON with capture results and PNG file paths
```
