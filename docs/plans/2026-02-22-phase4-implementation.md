# Phase 4: GOAT Code 9.0+ Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Remove all Qt imports from the core layer and fix remaining code quality violations to raise GOAT Code score from 7.55 → 9.0+

**Architecture:** Each Qt-dependent core file is either migrated to Observable (state.py) or moved to the UI layer (clipboard_manager.py, shortcut_controller.py) or refactored to use stdlib (profile_store.py, ipc_server.py). export_controller.py gets an IExportRenderer ABC so Qt rendering stays in UI.

**Tech Stack:** Python 3.11+, PySide6, Polars, asyncio, threading, hypothesis

**Test baseline:** 1997 passed, 4 skipped — must not regress.

**Branch:** Create `goat-phase4` from master before starting.

---

## Task 1: Migrate state.py AppState → Observable

**Goal:** Remove `QObject` and `Signal` from `data_graph_studio/core/state.py`. This is the highest-impact change (+2.5 on architecture score).

**Pattern:** Identical to Phase 3 (marking.py, comparison_manager.py, etc.). Read `data_graph_studio/core/marking.py` and `data_graph_studio/ui/adapters/marking_adapter.py` as reference.

**Files:**
- Modify: `data_graph_studio/core/state.py`
- Create: `data_graph_studio/ui/adapters/app_state_adapter.py`
- Create: `tests/unit/test_app_state_observable.py`

**27 signals to migrate:**
```
data_loaded, data_cleared,
group_zone_changed, value_zone_changed, hover_zone_changed,
filter_changed, sort_changed,
selection_changed, limit_to_marking_changed(bool),
chart_settings_changed, tool_mode_changed, grid_view_changed,
summary_updated(dict),
profile_loaded(object), profile_cleared, profile_saved,
setting_activated(str), setting_added(str), setting_removed(str),
floating_window_opened(str), floating_window_closed(str),
dataset_added(str), dataset_removed(str), dataset_activated(str), dataset_updated(str),
comparison_mode_changed(str), comparison_settings_changed
```

**Step 1: Write the failing test**

```python
# tests/unit/test_app_state_observable.py
import pytest
from data_graph_studio.core.state import AppState

def test_app_state_is_not_qobject():
    """AppState must not inherit from QObject."""
    try:
        from PySide6.QtCore import QObject
        state = AppState()
        assert not isinstance(state, QObject), "AppState must not be a QObject"
    except ImportError:
        pass  # Qt not available - Observable only

def test_data_loaded_event():
    received = []
    state = AppState()
    state.subscribe("data_loaded", lambda: received.append(True))
    state.data_loaded_signal()  # or however emit is triggered
    assert len(received) == 1

def test_summary_updated_event():
    received = []
    state = AppState()
    state.subscribe("summary_updated", lambda d: received.append(d))
    state.emit("summary_updated", {"rows": 100})
    assert received == [{"rows": 100}]

def test_dataset_added_event():
    received = []
    state = AppState()
    state.subscribe("dataset_added", lambda id_: received.append(id_))
    state.emit("dataset_added", "ds_001")
    assert received == ["ds_001"]
```

**Step 2: Run to verify it fails**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/test_app_state_observable.py -v 2>&1 | tail -15
```

Expected: `test_app_state_is_not_qobject` FAILS because AppState is currently a QObject.

**Step 3: Migrate state.py**

In `data_graph_studio/core/state.py`:

1. Remove: `from PySide6.QtCore import QObject, Signal`
2. Add: `from .observable import Observable`
3. Change: `class AppState(QObject):` → `class AppState(Observable):`
4. Remove all 27 `signal_name = Signal(...)` declarations
5. Replace every `self.signal_name.emit(arg)` call with `self.emit("signal_name", arg)` or `self.emit("signal_name")` for no-arg signals

   Search for `.emit(` inside AppState and convert:
   ```python
   # Before
   self.data_loaded.emit()
   self.summary_updated.emit(stats_dict)
   self.dataset_added.emit(dataset_id)

   # After
   self.emit("data_loaded")
   self.emit("summary_updated", stats_dict)
   self.emit("dataset_added", dataset_id)
   ```

6. Remove `super().__init__()` QObject call → `super().__init__()` is still needed for Observable

**Step 4: Create AppStateAdapter**

```python
# data_graph_studio/ui/adapters/app_state_adapter.py
"""Qt bridge for AppState Observable events."""
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.state import AppState


class AppStateAdapter(QObject):
    """Bridges AppState Observable events to Qt Signals for UI consumption."""

    data_loaded = Signal()
    data_cleared = Signal()
    group_zone_changed = Signal()
    value_zone_changed = Signal()
    hover_zone_changed = Signal()
    filter_changed = Signal()
    sort_changed = Signal()
    selection_changed = Signal()
    limit_to_marking_changed = Signal(bool)
    chart_settings_changed = Signal()
    tool_mode_changed = Signal()
    grid_view_changed = Signal()
    summary_updated = Signal(dict)
    profile_loaded = Signal(object)
    profile_cleared = Signal()
    profile_saved = Signal()
    setting_activated = Signal(str)
    setting_added = Signal(str)
    setting_removed = Signal(str)
    floating_window_opened = Signal(str)
    floating_window_closed = Signal(str)
    dataset_added = Signal(str)
    dataset_removed = Signal(str)
    dataset_activated = Signal(str)
    dataset_updated = Signal(str)
    comparison_mode_changed = Signal(str)
    comparison_settings_changed = Signal()

    def __init__(self, state: AppState, parent: QObject = None):
        super().__init__(parent)
        self._state = state
        # Wire all Observable events to Qt Signals
        state.subscribe("data_loaded", self.data_loaded.emit)
        state.subscribe("data_cleared", self.data_cleared.emit)
        state.subscribe("group_zone_changed", self.group_zone_changed.emit)
        state.subscribe("value_zone_changed", self.value_zone_changed.emit)
        state.subscribe("hover_zone_changed", self.hover_zone_changed.emit)
        state.subscribe("filter_changed", self.filter_changed.emit)
        state.subscribe("sort_changed", self.sort_changed.emit)
        state.subscribe("selection_changed", self.selection_changed.emit)
        state.subscribe("limit_to_marking_changed", self.limit_to_marking_changed.emit)
        state.subscribe("chart_settings_changed", self.chart_settings_changed.emit)
        state.subscribe("tool_mode_changed", self.tool_mode_changed.emit)
        state.subscribe("grid_view_changed", self.grid_view_changed.emit)
        state.subscribe("summary_updated", self.summary_updated.emit)
        state.subscribe("profile_loaded", self.profile_loaded.emit)
        state.subscribe("profile_cleared", self.profile_cleared.emit)
        state.subscribe("profile_saved", self.profile_saved.emit)
        state.subscribe("setting_activated", self.setting_activated.emit)
        state.subscribe("setting_added", self.setting_added.emit)
        state.subscribe("setting_removed", self.setting_removed.emit)
        state.subscribe("floating_window_opened", self.floating_window_opened.emit)
        state.subscribe("floating_window_closed", self.floating_window_closed.emit)
        state.subscribe("dataset_added", self.dataset_added.emit)
        state.subscribe("dataset_removed", self.dataset_removed.emit)
        state.subscribe("dataset_activated", self.dataset_activated.emit)
        state.subscribe("dataset_updated", self.dataset_updated.emit)
        state.subscribe("comparison_mode_changed", self.comparison_mode_changed.emit)
        state.subscribe("comparison_settings_changed", self.comparison_settings_changed.emit)
```

**Step 5: Update UI files to use AppStateAdapter**

In `data_graph_studio/ui/main_window.py`:
1. After creating `self.state = AppState()`, add: `self._state_adapter = AppStateAdapter(self.state, parent=self)`
2. Replace all `self.state.signal_name.connect(...)` with `self._state_adapter.signal_name.connect(...)`

Grep for all `.connect(` calls on state in the UI:
```bash
grep -rn "state\.\w*\.connect\|self\.state\.\w*\.connect" data_graph_studio/ui/ --include="*.py"
```

Replace pattern: `state.data_loaded.connect(fn)` → `self._state_adapter.data_loaded.connect(fn)`

**Step 6: Run tests**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

Expected: 2001 passed (4 new tests added), 4 skipped.

**Step 7: Commit**

```bash
git add data_graph_studio/core/state.py data_graph_studio/ui/adapters/app_state_adapter.py tests/unit/test_app_state_observable.py
git commit -m "refactor: decouple AppState from Qt using Observable pattern"
```

---

## Task 2: Move clipboard_manager.py to UI layer

**Goal:** `ClipboardManager` uses Qt clipboard/image APIs — it's UI infrastructure, not core logic.

**Files:**
- Move: `data_graph_studio/core/clipboard_manager.py` → `data_graph_studio/ui/clipboard_manager.py`
- Modify: `data_graph_studio/ui/main_window.py` (update import)
- Modify: `data_graph_studio/ui/controllers/data_ops_controller.py` (update import)
- Modify: `data_graph_studio/ui/controllers/file_loading_controller.py` (update import)

**Step 1: Move the file**

```bash
mv data_graph_studio/core/clipboard_manager.py data_graph_studio/ui/clipboard_manager.py
```

**Step 2: Update imports in 3 UI files**

Change `from ..core.clipboard_manager import` → `from ..clipboard_manager import` (or `from ...ui.clipboard_manager import` depending on relative path depth).

Exact replacements:
- `data_graph_studio/ui/main_window.py` line: `from ..core.clipboard_manager import ClipboardManager, DragDropHandler` → `from .clipboard_manager import ClipboardManager, DragDropHandler`
- `data_graph_studio/ui/controllers/data_ops_controller.py`: `from ...core.clipboard_manager import ClipboardManager` → `from ...ui.clipboard_manager import ClipboardManager`
- `data_graph_studio/ui/controllers/file_loading_controller.py`: `from ...core.clipboard_manager import ClipboardManager` → `from ...ui.clipboard_manager import ClipboardManager`

**Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move ClipboardManager from core to UI layer"
```

---

## Task 3: Move shortcut_controller.py to UI layer

**Goal:** `ShortcutController` is UI behavior (keyboard shortcuts). Already imports from `..ui.shortcuts`.

**Files:**
- Move: `data_graph_studio/core/shortcut_controller.py` → `data_graph_studio/ui/controllers/shortcut_controller.py`
- Modify imports in: `ui/main_window.py`, `ui/dialogs/shortcut_help_dialog.py`, `ui/dialogs/shortcut_edit_dialog.py`

**Step 1: Move file**

```bash
mv data_graph_studio/core/shortcut_controller.py data_graph_studio/ui/controllers/shortcut_controller.py
```

**Step 2: Fix internal import in the moved file**

The moved file currently has: `from ..ui.shortcuts import ShortcutManager, Shortcut, ShortcutCategory`

After moving to `ui/controllers/`, change to: `from ..shortcuts import ShortcutManager, Shortcut, ShortcutCategory`

**Step 3: Update caller imports**

- `ui/main_window.py`: `from ..core.shortcut_controller import ShortcutController` → `from .controllers.shortcut_controller import ShortcutController`
- `ui/dialogs/shortcut_help_dialog.py`: `from ...core.shortcut_controller import ShortcutController` → `from ..controllers.shortcut_controller import ShortcutController`
- `ui/dialogs/shortcut_edit_dialog.py`: same as above

**Step 4: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: move ShortcutController from core to UI layer"
```

---

## Task 4: Remove QtConcurrent from profile_store.py

**Goal:** Replace `qt_run`/`QFuture` with stdlib `concurrent.futures.Future`.

**Files:**
- Modify: `data_graph_studio/core/profile_store.py`

**Step 1: Read the current async methods**

Look at lines 79–110 of `profile_store.py`. The `export_async` and `import_async` methods try `qt_run` first, then fall back to `ThreadPoolExecutor`.

**Step 2: Simplify — remove Qt path entirely**

Replace the try/except block at top with just:
```python
from concurrent.futures import Future, ThreadPoolExecutor
```

Change `import_async` return type annotation from `"QFuture"` to `Future`.

The methods should only use `ThreadPoolExecutor`:
```python
def export_async(self, path: str, settings: "GraphSetting") -> Future:
    """Export settings asynchronously. Returns Future."""
    def _export():
        self.export(path, settings)
    executor = ThreadPoolExecutor(max_workers=1)
    return executor.submit(_export)

def import_async(self, path: str) -> Future:
    """Import settings asynchronously. Returns Future."""
    def _import():
        return self.import_settings(path)
    executor = ThreadPoolExecutor(max_workers=1)
    return executor.submit(_import)
```

**Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add data_graph_studio/core/profile_store.py
git commit -m "refactor: replace QtConcurrent with ThreadPoolExecutor in profile_store"
```

---

## Task 5: Replace QTcpServer in ipc_server.py with asyncio

**Goal:** Remove PySide6 network dependency from core. Use stdlib asyncio TCP server.

**Files:**
- Modify: `data_graph_studio/core/ipc_server.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_ipc_server_no_qt.py
def test_ipc_server_has_no_qt_import():
    """IpcServer must not import from PySide6."""
    import ast, pathlib
    src = pathlib.Path("data_graph_studio/core/ipc_server.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "PySide6" not in node.module, f"Found Qt import: {node.module}"
```

**Step 2: Rewrite ipc_server.py with asyncio**

Key API to preserve:
- `IpcServer(port: int, message_handler: Callable)` constructor
- `start()` / `stop()` methods
- Port file writing (`~/.dgs/ipc_port`)
- Dynamic port selection (try DEFAULT_PORT, increment on failure)

New implementation skeleton:
```python
import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Callable, Optional

from data_graph_studio.core.constants import (
    IPC_DEFAULT_PORT as DEFAULT_PORT,
    IPC_MAX_PORT_ATTEMPTS as MAX_PORT_ATTEMPTS,
)

logger = logging.getLogger(__name__)
_PORT_FILE = Path.home() / ".dgs" / "ipc_port"


class IpcServer:
    """Asyncio-based IPC server (replaces QTcpServer)."""

    def __init__(self, message_handler: Callable[[dict], None]):
        self._handler = message_handler
        self._server: Optional[asyncio.Server] = None
        self._port: Optional[int] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> int:
        """Start server in background thread. Returns bound port."""
        self._loop = asyncio.new_event_loop()
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(timeout=5.0)
        return self._port

    def stop(self) -> None:
        if self._loop and self._server:
            self._loop.call_soon_threadsafe(self._server.close)

    def _run_loop(self, ready: threading.Event) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._start_server(ready))
        self._loop.run_forever()

    async def _start_server(self, ready: threading.Event) -> None:
        for attempt in range(MAX_PORT_ATTEMPTS):
            port = DEFAULT_PORT + attempt
            try:
                self._server = await asyncio.start_server(
                    self._handle_client, "127.0.0.1", port
                )
                self._port = port
                self._write_port_file(port)
                ready.set()
                return
            except OSError:
                continue
        ready.set()  # signal even on failure

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await asyncio.wait_for(reader.read(4096), timeout=10.0)
            msg = json.loads(data.decode())
            self._handler(msg)
        except Exception as e:
            logger.warning("ipc_server.handle_client_error", extra={"error": str(e)})
        finally:
            writer.close()

    def _write_port_file(self, port: int) -> None:
        _PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PORT_FILE.write_text(f"{os.getpid()}:{port}")
```

**Step 3: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add data_graph_studio/core/ipc_server.py tests/unit/test_ipc_server_no_qt.py
git commit -m "refactor: replace QTcpServer with asyncio in ipc_server"
```

---

## Task 6: Extract IExportRenderer from export_controller.py

**Goal:** `ExportController` orchestrates export but uses QPainter directly. Extract an `IExportRenderer` ABC so core stays Qt-free. Move Qt rendering to `ui/renderers/`.

**Files:**
- Modify: `data_graph_studio/core/export_controller.py` (keep ExportFormat, ExportOptions; add IExportRenderer ABC; remove QPainter/QThread)
- Create: `data_graph_studio/ui/renderers/qt_export_renderer.py`
- Modify: `data_graph_studio/ui/main_window.py` (inject QtExportRenderer)

**Step 1: Add IExportRenderer ABC to io_abstract.py**

```python
# Add to data_graph_studio/core/io_abstract.py
from abc import ABC, abstractmethod
from typing import Any

class IExportRenderer(ABC):
    """Abstract interface for chart-to-image rendering."""

    @abstractmethod
    def render_png(self, scene: Any, width: int, height: int, dpi: int) -> bytes:
        """Render scene to PNG bytes."""

    @abstractmethod
    def render_svg(self, scene: Any, width: int, height: int) -> bytes:
        """Render scene to SVG bytes."""

    @abstractmethod
    def render_pdf(self, scene: Any, width: int, height: int) -> bytes:
        """Render scene to PDF bytes."""
```

**Step 2: Update ExportController to accept renderer via DI**

In `export_controller.py`:
- Remove: `from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt`
- Remove: `from PySide6.QtGui import QImage, QPainter, QColor`
- Remove: `from PySide6.QtSvg import QSvgGenerator`
- Add: `from .io_abstract import IExportRenderer`
- Change `class ExportController(QObject)` → `class ExportController(Observable)`
- Change `class ExportWorker(QThread)` → run in `threading.Thread`
- `ExportController.__init__` gains `renderer: IExportRenderer` parameter

**Step 3: Create QtExportRenderer**

```python
# data_graph_studio/ui/renderers/qt_export_renderer.py
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtSvg import QSvgGenerator
from data_graph_studio.core.io_abstract import IExportRenderer

class QtExportRenderer(IExportRenderer):
    """Qt implementation of IExportRenderer using QPainter."""

    def render_png(self, scene, width, height, dpi) -> bytes:
        # Move existing QPainter PNG logic here
        ...

    def render_svg(self, scene, width, height) -> bytes:
        # Move existing QSvgGenerator logic here
        ...

    def render_pdf(self, scene, width, height) -> bytes:
        # Move existing QPdfWriter logic here
        ...
```

**Step 4: Update main_window.py**

```python
from data_graph_studio.ui.renderers.qt_export_renderer import QtExportRenderer
# ...
self.export_controller = ExportController(renderer=QtExportRenderer())
```

**Step 5: Run tests**

```bash
source .venv/bin/activate && pytest tests/ -x -q 2>&1 | tail -5
```

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: extract IExportRenderer ABC and move Qt rendering to UI layer"
```

---

## Task 7: Split large functions (>100 lines)

**Goal:** All functions ≤50 lines (GOAT standard). Target the 2 largest violators.

### 7a: comparison_report.py `_generate_html_report` (277 lines)

**Files:**
- Modify: `data_graph_studio/core/comparison_report.py` (or wherever it lives — check first)

```bash
grep -rn "_generate_html_report\|def _generate_html" data_graph_studio/ --include="*.py"
```

Extract HTML sections into private helpers:
- `_render_header_section(...)` → `<head>` + CSS
- `_render_summary_section(...)` → stats table
- `_render_diff_section(...)` → diff visualization
- `_render_footer_section(...)` → closing tags

Each helper ≤50 lines.

### 7b: expression_engine.py `_evaluate_function` (217 lines)

```bash
grep -n "def _evaluate_function" data_graph_studio/core/expression_engine.py
```

Replace the long if/elif chain with a dispatch dict:
```python
_FUNCTION_DISPATCH = {
    "abs": _eval_abs,
    "round": _eval_round,
    "sum": _eval_sum,
    # ... etc
}

def _evaluate_function(self, name: str, args: list) -> Any:
    handler = _FUNCTION_DISPATCH.get(name)
    if handler is None:
        raise ValueError(f"Unknown function: {name}")
    return handler(self, args)
```

**Step for each:** Run tests after each refactor. Commit separately.

```bash
git commit -m "refactor: split _generate_html_report into section helpers"
git commit -m "refactor: replace _evaluate_function if/elif chain with dispatch table"
```

---

## Task 8: Docstrings to 85%+ coverage

**Goal:** Raise docstring coverage from 76% → 85%+.

**Step 1: Find missing docstrings**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate
python -c "
import ast, pathlib
missing = []
for f in pathlib.Path('data_graph_studio').rglob('*.py'):
    tree = ast.parse(f.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (node.name.startswith('_') or ast.get_docstring(node)):
                missing.append(f'{f}:{node.lineno} {node.name}')
print('\n'.join(missing[:50]))
print(f'Total: {len(missing)}')
"
```

**Step 2: Add docstrings to public functions**

Focus on: core/, ui/controllers/ — the highest-value areas.

Format: one-line summary, Args, Returns sections.

**Step 3: Commit**

```bash
git add -A
git commit -m "docs: add missing docstrings to reach 85%+ coverage"
```

---

## Task 9: External call timeouts

**Goal:** All external calls (network, subprocess, async) have explicit timeout.

**Step 1: Audit**

```bash
grep -rn "subprocess\.\|asyncio\.\|urllib\.\|requests\.\|socket\." data_graph_studio/core/ --include="*.py" | grep -v "#" | grep -v "timeout"
```

**Step 2: Add timeouts**

For each call missing a timeout:
- `subprocess.run(...)` → add `timeout=30`
- `asyncio.wait_for(...)` → already pattern, ensure timeout value
- `socket.connect(...)` → add `settimeout(10.0)`

**Step 3: Commit**

```bash
git add -A
git commit -m "fix: add explicit timeouts to all external calls in core layer"
```

---

## Final Verification

After all tasks complete:

```bash
# Run full test suite
source .venv/bin/activate && pytest tests/ -q 2>&1 | tail -5

# Verify no Qt in core (except adapters)
grep -rn "from PySide6\|import PySide6" data_graph_studio/core/ --include="*.py" | grep -v "adapters"
# Should return: ZERO results

# Check git log
git log --oneline master..HEAD | head -20
```

Expected test count: 2001+ passed, 4 skipped.
Expected Qt violations in core: 0.
