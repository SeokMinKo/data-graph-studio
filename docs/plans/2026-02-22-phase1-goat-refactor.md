# Phase 1 GOAT Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Resolve the 4 critical Phase 1 issues from the GOAT Code audit — Config Module, logging cleanup, Qt signal decoupling, and GraphPanel god object split.

**Architecture:** Introduce `core/constants.py` as central config hub; replace print() with structured logging; extract a pure Python `Observable` event system to make core classes Qt-independent; split `GraphPanel` into focused renderer classes.

**Tech Stack:** Python 3.11+, PySide6, Polars, pytest, standard `logging`

**Branch:** `goat-code-audit`

---

## Task 1: Create `core/constants.py` — Central Config Hub

**Files:**
- Create: `data_graph_studio/core/constants.py`
- Modify: `data_graph_studio/core/file_watcher.py`
- Modify: `data_graph_studio/core/annotation.py`
- Modify: `data_graph_studio/core/ipc_server.py`
- Modify: `data_graph_studio/core/undo_manager.py`
- Modify: `data_graph_studio/core/state.py`
- Test: `tests/unit/test_constants.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_constants.py
from data_graph_studio.core import constants

def test_file_watcher_constants_exist():
    assert constants.MIN_POLL_INTERVAL_MS == 500
    assert constants.MAX_POLL_INTERVAL_MS == 60000
    assert constants.DEFAULT_POLL_INTERVAL_MS == 1000
    assert constants.DEBOUNCE_MS == 300
    assert constants.MAX_WATCHED_FILES == 10
    assert constants.LARGE_FILE_THRESHOLD == 2097152000
    assert constants.MAX_BACKOFF_MS == 30000

def test_ipc_constants_exist():
    assert constants.IPC_DEFAULT_PORT == 52849
    assert constants.IPC_MAX_PORT_ATTEMPTS == 100

def test_undo_constants_exist():
    assert constants.UNDO_MAX_DEPTH == 50

def test_annotation_constants_exist():
    assert constants.MAX_ANNOTATION_TEXT_LENGTH == 200

def test_diff_color_constants_exist():
    assert constants.DIFF_POSITIVE_COLOR == "#2ca02c"
    assert constants.DIFF_NEGATIVE_COLOR == "#d62728"
    assert constants.DIFF_NEUTRAL_COLOR == "#7f7f7f"
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/lov2fn/Projects/data-graph-studio
pytest tests/unit/test_constants.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'data_graph_studio.core.constants'`

**Step 3: Create `core/constants.py`**

```python
# data_graph_studio/core/constants.py
"""
Central constants for Data Graph Studio.
All magic numbers and configurable defaults live here.
Import from this module — do not define constants elsewhere in core/.
"""

# --- File Watcher ---
MIN_POLL_INTERVAL_MS: int = 500
MAX_POLL_INTERVAL_MS: int = 60_000
DEFAULT_POLL_INTERVAL_MS: int = 1_000
DEBOUNCE_MS: int = 300
MAX_WATCHED_FILES: int = 10
LARGE_FILE_THRESHOLD: int = 2_097_152_000  # 2 GB
MAX_BACKOFF_MS: int = 30_000

# --- IPC Server ---
IPC_DEFAULT_PORT: int = 52_849
IPC_MAX_PORT_ATTEMPTS: int = 100

# --- Undo / History ---
UNDO_MAX_DEPTH: int = 50

# --- Annotations ---
MAX_ANNOTATION_TEXT_LENGTH: int = 200

# --- Diff Colors ---
DIFF_POSITIVE_COLOR: str = "#2ca02c"
DIFF_NEGATIVE_COLOR: str = "#d62728"
DIFF_NEUTRAL_COLOR: str = "#7f7f7f"
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_constants.py -v
```
Expected: PASS (5 tests)

**Step 5: Update `core/file_watcher.py` — replace local constants with imports**

Find lines 33–39 in `file_watcher.py`:
```python
# BEFORE
MIN_POLL_INTERVAL_MS = 500
MAX_POLL_INTERVAL_MS = 60000
DEFAULT_POLL_INTERVAL_MS = 1000
DEBOUNCE_MS = 300
MAX_WATCHED_FILES = 10
LARGE_FILE_THRESHOLD = 2097152000
MAX_BACKOFF_MS = 30000
```
Replace with:
```python
# AFTER
from data_graph_studio.core.constants import (
    MIN_POLL_INTERVAL_MS,
    MAX_POLL_INTERVAL_MS,
    DEFAULT_POLL_INTERVAL_MS,
    DEBOUNCE_MS,
    MAX_WATCHED_FILES,
    LARGE_FILE_THRESHOLD,
    MAX_BACKOFF_MS,
)
```

**Step 6: Update `core/annotation.py`, `core/ipc_server.py`, `core/undo_manager.py`, `core/state.py`**

Apply same pattern — replace local definitions with imports from `constants`.

For `state.py` lines 43–45:
```python
# BEFORE
DIFF_POSITIVE_COLOR = "#2ca02c"
DIFF_NEGATIVE_COLOR = "#d62728"
DIFF_NEUTRAL_COLOR = "#7f7f7f"
```
```python
# AFTER
from data_graph_studio.core.constants import (
    DIFF_POSITIVE_COLOR,
    DIFF_NEGATIVE_COLOR,
    DIFF_NEUTRAL_COLOR,
)
```

**Step 7: Run full test suite to verify no regressions**

```bash
pytest tests/ -x -q
```
Expected: All previously passing tests still pass.

**Step 8: Commit**

```bash
git add data_graph_studio/core/constants.py \
        data_graph_studio/core/file_watcher.py \
        data_graph_studio/core/annotation.py \
        data_graph_studio/core/ipc_server.py \
        data_graph_studio/core/undo_manager.py \
        data_graph_studio/core/state.py \
        tests/unit/test_constants.py
git commit -m "refactor: centralize magic numbers into core/constants.py"
```

---

## Task 2: Fix `print()` Calls in `clipboard_manager.py`

**Files:**
- Modify: `data_graph_studio/core/clipboard_manager.py`

**Step 1: Locate the print() calls**

```bash
grep -n "print(" data_graph_studio/core/clipboard_manager.py
```
Expected: lines 142 and 199.

**Step 2: Replace print() with logger.error()**

```python
# BEFORE (line 142)
print(f"HTML parse error: {e}")

# AFTER
logger.error("clipboard HTML parse error", extra={"error": str(e)})
```

```python
# BEFORE (line 199)
print(f"Text parse error: {e}")

# AFTER
logger.error("clipboard text parse error", extra={"error": str(e)})
```

Confirm `logger = logging.getLogger(__name__)` exists at module level (add if missing).

**Step 3: Run tests**

```bash
pytest tests/ -x -q
```
Expected: All passing.

**Step 4: Commit**

```bash
git add data_graph_studio/core/clipboard_manager.py
git commit -m "fix: replace print() with structured logger in clipboard_manager"
```

---

## Task 3: Upgrade Logging to Structured Format

**Files:**
- Modify: `data_graph_studio/__main__.py`
- Create: `data_graph_studio/core/logging_utils.py`
- Test: `tests/unit/test_logging_utils.py`

**Goal:** All log output uses `key=value` structured format so log lines are machine-parseable.

**Step 1: Write failing test**

```python
# tests/unit/test_logging_utils.py
import logging
import json
from data_graph_studio.core.logging_utils import StructuredFormatter

def test_structured_formatter_outputs_key_value():
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="", lineno=0,
        msg="data loaded", args=(),
        exc_info=None
    )
    record.__dict__["file"] = "test.csv"
    record.__dict__["rows"] = 1000
    output = formatter.format(record)
    assert "level=INFO" in output
    assert "msg=data loaded" in output

def test_structured_formatter_includes_extra_fields():
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test", level=logging.ERROR,
        pathname="", lineno=0,
        msg="parse error", args=(),
        exc_info=None
    )
    record.__dict__["error"] = "unexpected EOF"
    output = formatter.format(record)
    assert "error=unexpected EOF" in output
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_logging_utils.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create `core/logging_utils.py`**

```python
# data_graph_studio/core/logging_utils.py
"""Structured logging formatter and helpers."""

import logging
import time
from typing import Any

_RESERVED_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "message",
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
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_logging_utils.py -v
```
Expected: PASS

**Step 5: Update `__main__.py` to use StructuredFormatter**

In `setup_logging()`:
```python
# BEFORE
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[...]
)
```

```python
# AFTER
from data_graph_studio.core.logging_utils import StructuredFormatter

def setup_logging():
    log_dir = os.path.join(os.path.expanduser("~"), '.data_graph_studio', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'app_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

    formatter = StructuredFormatter()
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    return logging.getLogger('DataGraphStudio')
```

**Step 6: Run full test suite**

```bash
pytest tests/ -x -q
```

**Step 7: Commit**

```bash
git add data_graph_studio/core/logging_utils.py \
        data_graph_studio/__main__.py \
        tests/unit/test_logging_utils.py
git commit -m "feat: add StructuredFormatter for machine-parseable key=value logs"
```

---

## Task 4: Qt Signal Adapter — Decouple `core/` from PySide6

**Goal:** Make core classes testable without Qt. Core classes emit events via a pure Python `Observable`. Qt signal forwarding lives in a thin adapter layer only.

**Files:**
- Create: `data_graph_studio/core/observable.py`
- Modify: `data_graph_studio/core/filtering.py` (pilot — simplest, 3 signals)
- Modify: `data_graph_studio/core/streaming_controller.py` (pilot — 3 signals)
- Create: `data_graph_studio/ui/adapters/filtering_adapter.py`
- Test: `tests/unit/test_observable.py`
- Test: `tests/unit/test_filtering_no_qt.py`

**Note:** `state.py` (30+ signals) is NOT in this task — do it last, after the pattern is proven on smaller classes.

**Step 1: Write failing tests for Observable**

```python
# tests/unit/test_observable.py
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
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_observable.py -v
```
Expected: FAIL

**Step 3: Create `core/observable.py`**

```python
# data_graph_studio/core/observable.py
"""
Pure Python observable/event system for core layer.
No Qt dependency. Core classes use this for event notification.
Qt UI wires up via adapter classes that translate Observable events to Qt Signals.
"""

from __future__ import annotations
from collections import defaultdict
from typing import Any, Callable


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
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event: str, handler: Callable) -> None:
        """Register handler for event. Noop if already registered."""
        if handler not in self._listeners[event]:
            self._listeners[event].append(handler)

    def unsubscribe(self, event: str, handler: Callable) -> None:
        """Remove handler. Noop if not registered."""
        try:
            self._listeners[event].remove(handler)
        except ValueError:
            pass

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Fire all handlers for event. Errors in handlers are logged, not raised."""
        import logging
        logger = logging.getLogger(__name__)
        for handler in list(self._listeners.get(event, [])):
            try:
                handler(*args, **kwargs)
            except Exception as exc:
                logger.error(
                    "observable handler error",
                    extra={"event": event, "handler": handler.__qualname__, "error": str(exc)},
                )
```

**Step 4: Run test to verify Observable passes**

```bash
pytest tests/unit/test_observable.py -v
```
Expected: PASS (4 tests)

**Step 5: Write failing test for FilterManager without Qt**

```python
# tests/unit/test_filtering_no_qt.py
"""FilterManager must be testable without a Qt application instance."""
import pytest
from data_graph_studio.core.filtering import FilterManager

def test_filter_manager_no_qt_required():
    """FilterManager can be instantiated without QApplication."""
    fm = FilterManager()
    assert fm is not None

def test_filter_changed_event_fires():
    """filter_changed event fires when filter is applied."""
    fm = FilterManager()
    received = []
    fm.subscribe("filter_changed", lambda scheme: received.append(scheme))
    fm.create_scheme("test_scheme")
    fm.set_active_scheme("test_scheme")
    assert "test_scheme" in received
```

**Step 6: Run test to verify it fails** (FilterManager currently requires Qt)

```bash
pytest tests/unit/test_filtering_no_qt.py -v
```
Expected: FAIL — `RuntimeError: QApplication not found` or similar

**Step 7: Refactor `core/filtering.py` — replace `QObject` with `Observable`**

Locate the `FilterManager(QObject)` class definition (~line 220):

```python
# BEFORE
from PySide6.QtCore import QObject, Signal

class FilterManager(QObject):
    filter_changed = Signal(str)
    scheme_created = Signal(str)
    scheme_removed = Signal(str)

    def __init__(self):
        super().__init__()
```

```python
# AFTER
from data_graph_studio.core.observable import Observable

class FilterManager(Observable):
    """
    Manages filter schemes.
    Events: filter_changed(scheme_name), scheme_created(name), scheme_removed(name)
    """

    def __init__(self):
        super().__init__()
```

Replace all `self.filter_changed.emit(x)` → `self.emit("filter_changed", x)` throughout the file.
Replace all `self.scheme_created.emit(x)` → `self.emit("scheme_created", x)`
Replace all `self.scheme_removed.emit(x)` → `self.emit("scheme_removed", x)`

**Step 8: Create Qt adapter for FilterManager**

```python
# data_graph_studio/ui/adapters/filtering_adapter.py
"""
Qt signal adapter for FilterManager.
Translates Observable events → PySide6 Signals.
"""
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.filtering import FilterManager


class FilterManagerAdapter(QObject):
    """
    Wraps FilterManager and re-emits its Observable events as Qt Signals.
    Used by UI components that need Qt signal connections.
    """
    filter_changed = Signal(str)
    scheme_created = Signal(str)
    scheme_removed = Signal(str)

    def __init__(self, manager: FilterManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        manager.subscribe("filter_changed", self.filter_changed.emit)
        manager.subscribe("scheme_created", self.scheme_created.emit)
        manager.subscribe("scheme_removed", self.scheme_removed.emit)

    @property
    def manager(self) -> FilterManager:
        return self._manager
```

**Step 9: Update UI code that uses FilterManager signals**

Search for all `.connect()` calls on `filter_manager` signals in UI:
```bash
grep -rn "filter_manager\." data_graph_studio/ui/ | grep "\.connect\|filter_changed\|scheme_created\|scheme_removed"
```
For each connection found, update to use `FilterManagerAdapter` instead of `FilterManager` directly.

**Step 10: Run failing tests to verify they now pass**

```bash
pytest tests/unit/test_filtering_no_qt.py tests/unit/test_observable.py -v
```
Expected: PASS

**Step 11: Run full test suite**

```bash
pytest tests/ -x -q
```
Expected: All previously passing tests still pass.

**Step 12: Commit**

```bash
git add data_graph_studio/core/observable.py \
        data_graph_studio/core/filtering.py \
        data_graph_studio/ui/adapters/filtering_adapter.py \
        tests/unit/test_observable.py \
        tests/unit/test_filtering_no_qt.py
git commit -m "refactor: decouple FilterManager from Qt using Observable pattern"
```

**Step 13: Repeat for `streaming_controller.py`**

Apply same pattern:
- `StreamingController(QObject)` → `StreamingController(Observable)`
- Signals: `streaming_state_changed`, `data_updated`, `file_deleted`
- Create: `data_graph_studio/ui/adapters/streaming_adapter.py`
- Test: `tests/unit/test_streaming_no_qt.py`

Commit after each class: `"refactor: decouple StreamingController from Qt"`

---

## Task 5: Split `GraphPanel` God Object

**Goal:** Break 2,489-line `GraphPanel` into focused classes. Keep `GraphPanel` as coordinator only.

**Target structure:**
```
ui/panels/graph_panel/
├── __init__.py          # re-exports GraphPanel for backward compat
├── graph_panel.py       # coordinator (~300 lines)
├── renderers/
│   ├── combo_renderer.py    # _refresh_combo_chart + _render_combo_series*
│   ├── statistical_renderer.py  # _refresh_statistical_chart + box/violin/heatmap
│   └── grid_renderer.py    # _refresh_grid_view + _plot_grid_series + _clear_grid_cells
├── refresh_scheduler.py  # _schedule_refresh, _schedule_style_refresh, _do_refresh (dispatcher)
└── drawing_tools.py     # all 10 drawing-related methods
```

**Step 1: Create directory structure**

```bash
mkdir -p data_graph_studio/ui/panels/graph_panel/renderers
touch data_graph_studio/ui/panels/graph_panel/__init__.py
touch data_graph_studio/ui/panels/graph_panel/renderers/__init__.py
```

**Step 2: Write test for backward compatibility**

```python
# tests/unit/test_graph_panel_import.py
def test_graph_panel_importable_from_original_path():
    """Backward compat: original import path must still work."""
    from data_graph_studio.ui.panels.graph_panel import GraphPanel
    assert GraphPanel is not None
```

**Step 3: Extract `combo_renderer.py`**

Move these methods into a `ComboChartRenderer` class:
- `_render_combo_series` (line 1073)
- `_render_combo_series_vb` (line 1100)
- `_refresh_combo_chart` (line 1124, 217 lines)
- `_refresh_overlay_comparison` (line 1719)

```python
# data_graph_studio/ui/panels/graph_panel/renderers/combo_renderer.py
"""Handles combo chart rendering for GraphPanel."""

class ComboChartRenderer:
    """
    Renders combo (multi-series) charts.

    Inputs: plot_widget, state, chart_settings
    Outputs: rendered chart, no return value
    Raises: nothing — errors are caught and logged
    """

    def __init__(self, plot_widget, state):
        self._plot = plot_widget
        self._state = state

    def refresh(self, data, settings):
        """Render combo chart with given data and settings."""
        # ... extracted logic from _refresh_combo_chart
```

**Step 4: Extract `statistical_renderer.py`**

Move:
- `_refresh_statistical_chart` (line 1341)
- `_render_box_plot` (line 1416, 98 lines)
- `_render_violin_plot` (line 1514, 111 lines)
- `_render_heatmap` (line 1625, 94 lines)

**Step 5: Extract `grid_renderer.py`**

Move:
- `_refresh_grid_view` (line 2240, 179 lines)
- `_plot_grid_series` (line 2419)
- `_clear_grid_cells` (line 2446)
- `_sync_grid_axes` (line 2458)

**Step 6: Extract `drawing_tools.py`**

Move all 10 drawing methods (lines 2192–2234) into `DrawingToolsController`.

**Step 7: Update `GraphPanel` to delegate to extracted classes**

```python
# graph_panel.py (after extraction — ~300 lines)
class GraphPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self._combo_renderer = ComboChartRenderer(self._plot_widget, state)
        self._stats_renderer = StatisticalChartRenderer(self._plot_widget, state)
        self._grid_renderer = GridChartRenderer(self._grid_layout, state)
        self._drawing_tools = DrawingToolsController(self._plot_widget)
        self._setup_ui()
        self._connect_signals()

    def _do_refresh(self, chart_type):
        """Dispatch to appropriate renderer based on chart type."""
        if chart_type in COMBO_CHART_TYPES:
            self._combo_renderer.refresh(...)
        elif chart_type in STATISTICAL_CHART_TYPES:
            self._stats_renderer.refresh(...)
        elif chart_type == ChartType.GRID:
            self._grid_renderer.refresh(...)
```

**Step 8: Update `__init__.py` for backward compat**

```python
# data_graph_studio/ui/panels/graph_panel/__init__.py
from data_graph_studio.ui.panels.graph_panel.graph_panel import GraphPanel
__all__ = ["GraphPanel"]
```

**Step 9: Run full test suite after each renderer extraction**

```bash
pytest tests/ -x -q
```
Expected: All passing after each step.

**Step 10: Commit after each renderer**

```bash
git commit -m "refactor: extract ComboChartRenderer from GraphPanel"
git commit -m "refactor: extract StatisticalChartRenderer from GraphPanel"
git commit -m "refactor: extract GridChartRenderer from GraphPanel"
git commit -m "refactor: extract DrawingToolsController from GraphPanel"
git commit -m "refactor: GraphPanel reduced to coordinator (~300 lines)"
```

---

## Phase 1 Completion Checklist

- [ ] `core/constants.py` created, all magic numbers centralized
- [ ] `print()` calls removed from `clipboard_manager.py`
- [ ] Structured logging formatter deployed
- [ ] `FilterManager` and `StreamingController` decoupled from Qt
- [ ] `Observable` base class tested and documented
- [ ] `GraphPanel` split into 5 focused classes, each <300 lines
- [ ] All tests passing
- [ ] No new Qt imports added to `core/`

---

## Phase 1b: Remaining Qt Decoupling (After Phase 1 Complete)

The following core classes still need Qt extraction (apply same Observable pattern):
- `core/marking.py` (MarkingManager)
- `core/view_sync.py` (ViewSyncController)
- `core/ipc_server.py` (IpcServer)
- `core/state.py` (AppState — most complex, 30+ signals, do last)

Plan these separately after Phase 1 is proven.
