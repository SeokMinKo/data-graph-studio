# GOAT Round 5: 9+ Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Push GOAT code audit score from 6.8/10 to 9.0+/10.

**Architecture:** Five parallel tracks targeting the highest-impact score gaps: UI monolith decomposition (Function Design + Conventions), observability wiring (Observability), typed raise coverage (Error Strategy), and test improvements (Test Coverage). Tracks 3–5 are fast; Tracks 1–2 are the heavy lifts.

**Tech Stack:** Python 3.11+, PySide6, polars, pytest, hypothesis

---

## Score Targets

| Category | Before | Target | Weight | Lift |
|---|---|---|---|---|
| Architecture | 7.0 | 8.5 | 20% | +0.30 |
| Function Design | 6.5 | 9.0 | 15% | +0.375 |
| Error Strategy | 5.0 | 8.5 | 15% | +0.525 |
| Test Coverage | 7.0 | 8.5 | 20% | +0.30 |
| Conventions | 6.0 | 9.0 | 15% | +0.45 |
| Observability | 5.0 | 8.0 | 10% | +0.30 |
| Domain Modeling | 6.0 | 7.5 | 5% | +0.075 |
| **Total** | **6.8** | **9.1** | | **+2.325** |

---

## Track 1: main_window.py Mixin Surgery

**Why:** 2060 lines, 246 methods — single biggest violation of Function Design and Conventions. Auditor gave 6.5/10 and 6.0/10 partly because of this file alone.

**Strategy:** Extract 4 mixin files. Each mixin is a `Protocol` that `MainWindow` composes. The main file becomes a 150-line facade.

### Task 1.1: Extract `_main_window_ipc_mixin.py`

**Files:**
- Create: `data_graph_studio/ui/_main_window_ipc_mixin.py`
- Modify: `data_graph_studio/ui/main_window.py`

**Step 1: Identify IPC methods**

These are all methods matching `_ipc_*` (lines 639–722 in main_window.py). Count them:

```bash
grep -n "def _ipc_" data_graph_studio/ui/main_window.py
```

Expected: ~30 methods. All delegate to `*a, **kw` — they're stubs that forward to a controller.

**Step 2: Create the IPC mixin file**

Create `data_graph_studio/ui/_main_window_ipc_mixin.py`:

```python
"""IPC handler stubs for MainWindow.

All methods here are wired in _setup_ipc_server() and forward
to the appropriate controllers. No logic lives here.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class _MainWindowIpcMixin:
    """Mixin providing IPC command handler stubs for MainWindow."""
```

Then move ALL `_ipc_*` methods verbatim from `main_window.py` into this class.

**Step 3: Update MainWindow to inherit the mixin**

In `main_window.py`, change:
```python
class MainWindow(QMainWindow):
```
to:
```python
from data_graph_studio.ui._main_window_ipc_mixin import _MainWindowIpcMixin

class MainWindow(_MainWindowIpcMixin, QMainWindow):
```

Remove the moved methods from `main_window.py`.

**Step 4: Run existing tests**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/ -q --tb=short 2>&1 | tail -10
```

Expected: `1469 passed` (IPC methods are stub-only, no logic to break)

**Step 5: Verify file sizes**

```bash
wc -l data_graph_studio/ui/main_window.py data_graph_studio/ui/_main_window_ipc_mixin.py
```

Expected: main_window.py ≤ 1750, mixin ≤ 400.

**Step 6: Commit**

```bash
git add data_graph_studio/ui/main_window.py data_graph_studio/ui/_main_window_ipc_mixin.py
git commit -m "refactor: extract IPC handler stubs into _main_window_ipc_mixin"
```

---

### Task 1.2: Extract `_main_window_actions_mixin.py`

**Files:**
- Create: `data_graph_studio/ui/_main_window_actions_mixin.py`
- Modify: `data_graph_studio/ui/main_window.py`

**Step 1: Identify action handlers**

Action handlers = all `_on_*` methods (lines ~462–2060 in main_window.py). These are Qt slot callbacks. They are the largest group.

```bash
grep -n "def _on_\|def _copy_\|def _paste_\|def _update_recent" data_graph_studio/ui/main_window.py | wc -l
```

**Step 2: Create the actions mixin**

Create `data_graph_studio/ui/_main_window_actions_mixin.py`:

```python
"""Action handler slots for MainWindow.

Qt signal callbacks (menu actions, toolbar buttons, keyboard shortcuts).
These methods respond to user actions and delegate to controllers.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    pass


class _MainWindowActionsMixin:
    """Mixin providing Qt action slot handlers for MainWindow."""
```

Move ALL `_on_*` methods, `_copy_*`, `_paste_*`, `_update_recent_files_menu`,
`_get_recent_files`, `_add_to_recent_files`, `_open_recent_file`, `_clear_recent_files`
verbatim into this class.

**Step 3: Update inheritance**

```python
from data_graph_studio.ui._main_window_ipc_mixin import _MainWindowIpcMixin
from data_graph_studio.ui._main_window_actions_mixin import _MainWindowActionsMixin

class MainWindow(_MainWindowIpcMixin, _MainWindowActionsMixin, QMainWindow):
```

**Step 4: Run tests and verify**

```bash
pytest tests/unit/ -q --tb=short 2>&1 | tail -10
wc -l data_graph_studio/ui/main_window.py data_graph_studio/ui/_main_window_actions_mixin.py
```

Expected: 1469 passed. `main_window.py` ≤ 800 lines.

**Step 5: Commit**

```bash
git add data_graph_studio/ui/main_window.py data_graph_studio/ui/_main_window_actions_mixin.py
git commit -m "refactor: extract action slot handlers into _main_window_actions_mixin"
```

---

### Task 1.3: Extract `_main_window_events_mixin.py`

**Files:**
- Create: `data_graph_studio/ui/_main_window_events_mixin.py`
- Modify: `data_graph_studio/ui/main_window.py`

**Step 1: Identify Qt event overrides**

These are Qt event method overrides:
```bash
grep -n "def closeEvent\|def dragEnterEvent\|def dragLeaveEvent\|def dropEvent\|def keyPressEvent\|def _handle_dropped" data_graph_studio/ui/main_window.py
```

**Step 2: Create events mixin**

```python
"""Qt event overrides for MainWindow.

Handles OS-level events: window close, drag-and-drop, keyboard.
"""
from __future__ import annotations


class _MainWindowEventsMixin:
    """Mixin providing Qt event handler overrides for MainWindow."""
```

Move: `closeEvent`, `dragEnterEvent`, `dragLeaveEvent`, `dropEvent`,
`keyPressEvent`, `_handle_dropped_files`, `_is_text_input_focused`.

**Step 3: Update inheritance and run tests**

```python
class MainWindow(_MainWindowIpcMixin, _MainWindowActionsMixin, _MainWindowEventsMixin, QMainWindow):
```

```bash
pytest tests/unit/ -q 2>&1 | tail -5
wc -l data_graph_studio/ui/main_window.py
```

Expected: 1469 passed, `main_window.py` ≤ 600 lines.

**Step 4: Commit**

```bash
git add data_graph_studio/ui/main_window.py data_graph_studio/ui/_main_window_events_mixin.py
git commit -m "refactor: extract Qt event overrides into _main_window_events_mixin"
```

---

### Task 1.4: Extract `_main_window_layout_mixin.py`

**Files:**
- Create: `data_graph_studio/ui/_main_window_layout_mixin.py`
- Modify: `data_graph_studio/ui/main_window.py`

**Step 1: Identify layout/setup methods**

```bash
grep -n "def _setup_\|def _reset_layout\|def _redistribute\|def _get_panel_key\|def _toggle_panel\|def _format_tooltip\|def _wire_shortcut\|def _show_shortcuts\|def _show_edit_shortcuts\|def _on_shortcut_customized\|def _run_capture" data_graph_studio/ui/main_window.py
```

**Step 2: Create layout mixin**

```python
"""Layout setup and panel management for MainWindow.

Handles window construction, toolbar setup, panel layout, and
shortcut configuration. Called once during __init__.
"""
from __future__ import annotations


class _MainWindowLayoutMixin:
    """Mixin providing layout setup and panel management for MainWindow."""
```

Move all `_setup_*` methods, `_reset_layout`, `_redistribute_panel_sizes`,
`_get_panel_key`, `_toggle_panel_visibility`, `_format_tooltip`,
`_wire_shortcut_callbacks`, `_show_shortcuts_dialog`, `_show_edit_shortcuts_dialog`,
`_on_shortcut_customized`, `_run_capture_and_exit`.

**Step 3: Run tests and verify**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
wc -l data_graph_studio/ui/main_window.py
```

Expected: 1469 passed, `main_window.py` ≤ 350 lines.

**Step 4: Commit**

```bash
git add data_graph_studio/ui/main_window.py data_graph_studio/ui/_main_window_layout_mixin.py
git commit -m "refactor: extract layout/setup into _main_window_layout_mixin"
```

---

## Track 2: main_graph.py Mixin Surgery

**Why:** 2082 lines, 67 methods. Natural responsibility boundaries exist (selection, drawing, tooltip, reference lines, trendlines, plot).

**Target:** Each split file ≤ 350 lines. `main_graph.py` facade ≤ 200 lines.

### Task 2.1: Extract `_graph_selection_mixin.py`

**Files:**
- Create: `data_graph_studio/ui/panels/_graph_selection_mixin.py`
- Modify: `data_graph_studio/ui/panels/main_graph.py`

**Step 1: Identify selection methods**

```bash
grep -n "def highlight_selection\|def mousePressEvent\|def mouseMoveEvent\|def mouseReleaseEvent\|def _finish_rect\|def _finish_lasso\|def _point_in_polygon\|def _cleanup_selection\|def _cleanup_lasso" data_graph_studio/ui/panels/main_graph.py
```

**Step 2: Create selection mixin**

```python
"""Rectangular and lasso selection handling for MainGraph.

Manages mouse-driven data point selection including rect select,
lasso select, point-in-polygon testing, and selection cleanup.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    pass


class _GraphSelectionMixin:
    """Mixin providing data point selection logic for MainGraph."""
```

Move: `highlight_selection`, `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent`,
`_finish_rect_selection`, `_finish_lasso_selection`, `_point_in_polygon`,
`_cleanup_selection`, `_cleanup_lasso`.

**Step 3: Update MainGraph inheritance**

```python
from data_graph_studio.ui.panels._graph_selection_mixin import _GraphSelectionMixin

class MainGraph(_GraphSelectionMixin, pg.PlotWidget):
```

**Step 4: Run tests**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
```

**Step 5: Commit**

```bash
git add data_graph_studio/ui/panels/main_graph.py data_graph_studio/ui/panels/_graph_selection_mixin.py
git commit -m "refactor: extract selection logic into _graph_selection_mixin"
```

---

### Task 2.2: Extract `_graph_drawing_mixin.py`

**Files:**
- Create: `data_graph_studio/ui/panels/_graph_drawing_mixin.py`
- Modify: `data_graph_studio/ui/panels/main_graph.py`

Move: `set_drawing_manager`, `get_drawing_manager`, `set_drawing_style`,
`_update_drawing_preview`, `_finish_drawing`, `_handle_text_draw`, `_cleanup_drawing`.

**Step 1: Create drawing mixin**

```python
"""Free-form drawing tools (line, rect, text) for MainGraph."""
from __future__ import annotations


class _GraphDrawingMixin:
    """Mixin providing drawing tool management for MainGraph."""
```

**Step 2: Update inheritance, run tests, commit**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
git add data_graph_studio/ui/panels/main_graph.py data_graph_studio/ui/panels/_graph_drawing_mixin.py
git commit -m "refactor: extract drawing tools into _graph_drawing_mixin"
```

---

### Task 2.3: Extract `_graph_tooltip_mixin.py`

**Files:**
- Create: `data_graph_studio/ui/panels/_graph_tooltip_mixin.py`
- Modify: `data_graph_studio/ui/panels/main_graph.py`

Move: `_on_mouse_moved`, `_show_tooltip`, `_hide_tooltip`, `_format_value`,
`set_hover_data`, `_find_nearest_data_point`, `_prompt_add_annotation`.

```python
"""Mouse hover tooltip and nearest-point detection for MainGraph."""
from __future__ import annotations


class _GraphTooltipMixin:
    """Mixin providing hover tooltip behavior for MainGraph."""
```

**Run tests, commit:**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
git add data_graph_studio/ui/panels/main_graph.py data_graph_studio/ui/panels/_graph_tooltip_mixin.py
git commit -m "refactor: extract tooltip/hover logic into _graph_tooltip_mixin"
```

---

### Task 2.4: Extract `_graph_reference_mixin.py`

**Files:**
- Create: `data_graph_studio/ui/panels/_graph_reference_mixin.py`
- Modify: `data_graph_studio/ui/panels/main_graph.py`

Move: `add_reference_line`, `add_reference_band`, `clear_reference_lines`,
`_add_mean_line`, `_add_median_line`, `_add_custom_line`, `_add_sigma_band`,
`add_trendline`, `clear_trendlines`, `_add_trendline_degree`,
`_add_exponential_trendline`.

```python
"""Reference lines, bands, and trendline overlays for MainGraph."""
from __future__ import annotations


class _GraphReferenceMixin:
    """Mixin providing reference line and trendline overlays for MainGraph."""
```

**Run tests, commit:**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
wc -l data_graph_studio/ui/panels/main_graph.py
git add data_graph_studio/ui/panels/main_graph.py data_graph_studio/ui/panels/_graph_reference_mixin.py
git commit -m "refactor: extract reference lines and trendlines into _graph_reference_mixin"
```

Expected: `main_graph.py` ≤ 500 lines by now.

---

### Task 2.5: Extract `_graph_plot_mixin.py`

**Files:**
- Create: `data_graph_studio/ui/panels/_graph_plot_mixin.py`
- Modify: `data_graph_studio/ui/panels/main_graph.py`

Move: `plot_data`, `_plot_series`, `plot_multi_series`, `clear_plot`,
`_update_legend_settings`, `contextMenuEvent`, `_export_plot_image`,
`_export_plot_data_csv`, `_copy_plot_image`, `push_view_range`,
`undo_view_range`, `redo_view_range`.

```python
"""Core plot rendering and context menu for MainGraph."""
from __future__ import annotations


class _GraphPlotMixin:
    """Mixin providing plot rendering, export, and view management for MainGraph."""
```

**Run tests, verify final sizes, commit:**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
wc -l data_graph_studio/ui/panels/main_graph.py data_graph_studio/ui/panels/_graph_*.py
git add data_graph_studio/ui/panels/main_graph.py data_graph_studio/ui/panels/_graph_plot_mixin.py
git commit -m "refactor: extract plot rendering into _graph_plot_mixin — main_graph.py ≤300 lines"
```

---

## Track 3: Observability Wiring

**Why:** `MetricsCollector` exists with timer infrastructure but only used for `.increment()` counters. No operation timing for the critical path. Auditor gave 5.0/10.

**Strategy:** Add a `timed_operation` context manager factory to `metrics.py`, then wire into 5 key core operations.

### Task 3.1: Add `timed_operation` to `metrics.py`

**Files:**
- Modify: `data_graph_studio/core/metrics.py`

**Step 1: Write test first**

In `tests/unit/test_metrics.py` (create if not exists):

```python
def test_timed_operation_records_duration():
    from data_graph_studio.core.metrics import MetricsCollector
    m = MetricsCollector()
    with m.timed_operation("test.op"):
        pass
    snap = m.snapshot()
    assert "test.op" in snap["timers"]
    assert snap["timers"]["test.op"]["count"] == 1

def test_timed_operation_increments_counter():
    from data_graph_studio.core.metrics import MetricsCollector
    m = MetricsCollector()
    with m.timed_operation("test.op"):
        pass
    snap = m.snapshot()
    assert snap["counters"].get("test.op.count", 0) == 1

def test_timed_operation_records_error():
    from data_graph_studio.core.metrics import MetricsCollector
    m = MetricsCollector()
    try:
        with m.timed_operation("test.op"):
            raise ValueError("boom")
    except ValueError:
        pass
    snap = m.snapshot()
    assert snap["counters"].get("test.op.error", 0) == 1
```

Run to verify fail:
```bash
pytest tests/unit/test_metrics.py -v 2>&1 | tail -15
```

**Step 2: Implement `timed_operation` in `metrics.py`**

Add to `MetricsCollector`:

```python
def timed_operation(self, name: str) -> "TimedOperationContext":
    """Context manager that times a block and counts calls and errors.

    Usage:
        with metrics.timed_operation("query.execute"):
            run_query()
    Records:
        - {name} timer duration
        - {name}.count counter
        - {name}.error counter on exception
    """
    return TimedOperationContext(self, name)
```

Add new class:

```python
class TimedOperationContext:
    """Context manager for timing + counting + error tracking."""

    def __init__(self, collector: MetricsCollector, name: str):
        self._collector = collector
        self._name = name
        self._start: Optional[float] = None

    def __enter__(self) -> "TimedOperationContext":
        self._start = time.perf_counter()
        self._collector.increment(f"{self._name}.count")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._start is not None:
            elapsed_ms = (time.perf_counter() - self._start) * 1000
            self._collector.record_duration(self._name, elapsed_ms)
        if exc_type is not None:
            self._collector.increment(f"{self._name}.error")
        return False  # never suppress exceptions
```

**Step 3: Run tests**

```bash
pytest tests/unit/test_metrics.py -v 2>&1 | tail -15
```

Expected: all pass.

**Step 4: Commit**

```bash
git add data_graph_studio/core/metrics.py tests/unit/test_metrics.py
git commit -m "feat: add timed_operation context manager to MetricsCollector"
```

---

### Task 3.2: Wire metrics into 5 core operations

**Files:**
- Modify: `data_graph_studio/core/filtering.py`
- Modify: `data_graph_studio/core/data_engine.py`
- Modify: `data_graph_studio/core/file_loader.py`
- Modify: `data_graph_studio/core/comparison_engine.py`
- Modify: `data_graph_studio/core/statistics.py`

**Pattern to apply in each file:**

Find the public entry point and wrap with `timed_operation`:

```python
# Before:
def apply_filters(self, df: pl.DataFrame, filters: List) -> pl.DataFrame:
    ...
    get_metrics().increment("filter.applied")
    ...

# After:
def apply_filters(self, df: pl.DataFrame, filters: List) -> pl.DataFrame:
    with get_metrics().timed_operation("filter.apply"):
        ...
    # remove old increment — timed_operation handles it
```

**Specific changes:**

1. `filtering.py` — `FilteringScheme.apply_filters` (line ~382): wrap body with `timed_operation("filter.apply")`
2. `data_engine.py` — `load_file` (line ~320): wrap body with `timed_operation("engine.load_file")`
3. `data_engine.py` — `collect_lazy` (line ~309): wrap body with `timed_operation("engine.collect_lazy")`
4. `comparison_engine.py` — `calculate_difference` (line ~36): wrap with `timed_operation("comparison.calculate_difference")`
5. `statistics.py` — `calculate` (line ~56): wrap with `timed_operation("statistics.calculate")`

Note: `file_loader_formats.py` already wraps with `get_metrics().timer("file.load_duration")` — replace with `timed_operation` so errors are tracked too.

**Step 1: Apply changes**

For each file, import `get_metrics` if not already imported (all 5 already have it), then wrap:

```python
# filtering.py: FilteringScheme.apply_filters
def apply_filters(self, df: pl.DataFrame, filters: List[Filter]) -> pl.DataFrame:
    with get_metrics().timed_operation("filter.apply"):
        return self._apply_filters_impl(df, filters)

def _apply_filters_impl(self, df: pl.DataFrame, filters: List[Filter]) -> pl.DataFrame:
    # ... existing body here
```

Or simpler — just wrap the existing body directly in a `with` block without extracting:
```python
def apply_filters(self, ...):
    with get_metrics().timed_operation("filter.apply"):
        # existing code (indented one more level)
        ...
```

**Step 2: Run tests**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
```

Expected: 1469+ passed.

**Step 3: Commit**

```bash
git add data_graph_studio/core/filtering.py data_graph_studio/core/data_engine.py \
        data_graph_studio/core/file_loader.py data_graph_studio/core/comparison_engine.py \
        data_graph_studio/core/statistics.py data_graph_studio/core/file_loader_formats.py
git commit -m "feat: wire timed_operation into 5 core operations (filter, load, compare, stats)"
```

---

## Track 4: Typed Raise Coverage

**Why:** Only 7 typed raises in all of core. 31 generic `ValueError/RuntimeError` raises remain. Auditor gave Error Strategy 5.0/10.

**Strategy:** Convert error-boundary raises to typed exceptions. Leave validation raises (`ValueError` for bad params) as-is OR convert to `ValidationError`.

### Task 4.1: Convert error-boundary raises in ETL/file loading

**Files:**
- Modify: `data_graph_studio/core/file_loader_formats.py`
- Modify: `data_graph_studio/core/file_loader_formats_csv.py`
- Modify: `data_graph_studio/core/etl_helpers.py`

**Step 1: Write test first**

In `tests/unit/test_file_loader_formats.py` (create if not exists):

```python
def test_unsupported_file_type_raises_data_load_error(tmp_path):
    from data_graph_studio.core.exceptions import DataLoadError
    from data_graph_studio.core.file_loader_formats import load_file_by_type
    with pytest.raises(DataLoadError, match="Unsupported file type"):
        load_file_by_type(tmp_path / "test.xyz", "xyz")
```

In `tests/unit/test_etl_helpers.py` (already exists — add):

```python
def test_etl_read_failure_raises_data_load_error():
    from data_graph_studio.core.exceptions import DataLoadError
    from data_graph_studio.core.etl_helpers import read_etl_binary
    with pytest.raises(DataLoadError):
        read_etl_binary(b"garbage_data_not_etl")
```

Run to verify fail:
```bash
pytest tests/unit/test_file_loader_formats.py tests/unit/test_etl_helpers.py -v -k "raises_data_load" 2>&1 | tail -15
```

**Step 2: Apply conversions**

`file_loader_formats.py` line ~271:
```python
# Before:
raise ValueError(f"Unsupported file type: {file_type}")
# After:
from .exceptions import DataLoadError
raise DataLoadError(
    f"Unsupported file type: {file_type}",
    operation="load_file_by_type",
    context={"file_type": file_type},
)
```

`file_loader_formats_csv.py` lines 195, 197, 199:
```python
# All three ValueError("ETL ...") → DataLoadError("ETL ...")
```

`etl_helpers.py` lines 197, 200, 207, 211:
```python
# raise ValueError(f"ETL 파일 읽기 실패: {e}") →
raise DataLoadError(
    "ETL 파일 읽기 실패",
    operation="read_etl_binary",
    context={"error": str(e)},
) from e
```

**Step 3: Run tests**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add data_graph_studio/core/file_loader_formats.py \
        data_graph_studio/core/file_loader_formats_csv.py \
        data_graph_studio/core/etl_helpers.py \
        tests/unit/test_file_loader_formats.py \
        tests/unit/test_etl_helpers.py
git commit -m "feat: convert ETL/file-loading ValueError to DataLoadError"
```

---

### Task 4.2: Convert dataset/query/export raises

**Files:**
- Modify: `data_graph_studio/core/dataset_manager.py`
- Modify: `data_graph_studio/core/data_query.py`
- Modify: `data_graph_studio/core/export_workers.py`
- Modify: `data_graph_studio/core/data_exporter.py`
- Modify: `data_graph_studio/core/report.py`

**Step 1: Write tests**

```python
# test_dataset_manager.py — add:
def test_failed_load_raises_dataset_error(tmp_path):
    from data_graph_studio.core.exceptions import DatasetError
    from data_graph_studio.core.dataset_manager import DatasetManager
    manager = DatasetManager()
    with pytest.raises(DatasetError, match="Failed to load"):
        manager._load_path(tmp_path / "nonexistent.csv")

# test_data_exporter_core.py — add:
def test_export_without_dataframe_raises_export_error(tmp_path):
    from data_graph_studio.core.exceptions import ExportError
    from data_graph_studio.core.data_exporter import DataExporter
    e = DataExporter(df=None)
    with pytest.raises(ExportError, match="No DataFrame"):
        e.to_csv(tmp_path / "out.csv")
```

**Step 2: Apply conversions**

`dataset_manager.py` line ~430:
```python
# raise RuntimeError(f"Failed to load {p}") →
from .exceptions import DatasetError
raise DatasetError(
    f"Failed to load {p}",
    operation="_load_path",
    context={"path": str(p)},
)
```

`data_query.py` line ~52:
```python
# raise ValueError(f"Unknown operator: {operator}") →
from .exceptions import QueryError
raise QueryError(
    f"Unknown operator: {operator}",
    operation="apply_operator",
    context={"operator": operator},
)
```

`export_workers.py` line ~131:
```python
# raise ValueError(f"Unknown export task: {self.task}") →
from .exceptions import ExportError
raise ExportError(
    f"Unknown export task: {self.task}",
    operation="ExportWorker.run",
    context={"task": str(self.task)},
)
```

`data_exporter.py` lines 35, 58, 81 — all "No DataFrame to export":
```python
from .exceptions import ExportError
raise ExportError(
    "No DataFrame to export",
    operation=<method_name>,
    context={},
)
```

`report.py` line ~185:
```python
# raise ValueError(f"Unsupported format: {options.format}") →
from .exceptions import ExportError
raise ExportError(
    f"Unsupported format: {options.format}",
    operation="generate_report",
    context={"format": str(options.format)},
)
```

**Step 3: Run tests**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
```

**Step 4: Commit**

```bash
git add data_graph_studio/core/dataset_manager.py data_graph_studio/core/data_query.py \
        data_graph_studio/core/export_workers.py data_graph_studio/core/data_exporter.py \
        data_graph_studio/core/report.py
git commit -m "feat: convert dataset/query/export ValueError to typed exceptions"
```

---

### Task 4.3: Convert validation raises to `ValidationError`

**Files:**
- Modify: `data_graph_studio/core/filtering.py`
- Modify: `data_graph_studio/core/marking.py`
- Modify: `data_graph_studio/core/annotation.py`
- Modify: `data_graph_studio/core/state_types.py`
- Modify: `data_graph_studio/core/data_engine.py`

**Step 1: Identify validation raises (input contract enforcement)**

```
filtering.py:220   raise ValueError("Scheme already exists")
filtering.py:240   raise ValueError("Cannot remove Page scheme")
marking.py:185     raise ValueError("Marking already exists")
marking.py:211     raise ValueError("Cannot remove Main marking")
annotation.py:52   raise ValueError("x/y must be numbers")
state_types.py:201 raise ValueError("row index must be non-negative")
state_types.py:215 raise ValueError("row index must be non-negative")
data_engine.py:149 raise ValueError("column name must be non-empty string")
```

**Step 2: Write test first (filtering.py example)**

In `tests/unit/test_filtering.py` — add:
```python
def test_duplicate_scheme_raises_validation_error():
    from data_graph_studio.core.exceptions import ValidationError
    from data_graph_studio.core.filtering import FilteringState
    state = FilteringState()
    state.add_scheme("test_scheme")
    with pytest.raises(ValidationError, match="already exists"):
        state.add_scheme("test_scheme")
```

**Step 3: Convert to ValidationError**

```python
# filtering.py line 220:
from .exceptions import ValidationError
raise ValidationError(
    f"Scheme '{name}' already exists",
    operation="add_scheme",
    context={"name": name},
)

# Similar pattern for all 8 raises above
```

**Step 4: Run tests**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
```

Expected: 1469+ passed (existing tests must still pass — ValidationError is subclass of DGSError but not ValueError, check if any tests catch ValueError).

If existing tests catch `ValueError`:
```bash
grep -rn "pytest.raises(ValueError)" tests/ | head -10
```

Update those tests to catch `ValidationError` instead.

**Step 5: Commit**

```bash
git add data_graph_studio/core/filtering.py data_graph_studio/core/marking.py \
        data_graph_studio/core/annotation.py data_graph_studio/core/state_types.py \
        data_graph_studio/core/data_engine.py
git commit -m "feat: convert validation ValueError to ValidationError in core"
```

---

## Track 5: Test Coverage + NaN Bug

**Why:** Auditor flagged NaN bug as unresolved and integration test gap. Test Coverage at 7.0/10.

### Task 5.1: Fix Polars NaN filter bug

**File:**
- Modify: `data_graph_studio/core/filtering.py`

**Background:** `NaN > 0.0 = True` in Polars (IEEE 754 total ordering). Numeric range filters (`gt`, `lt`, `ge`, `le`) silently include NaN rows. Documented in `test_boundary_cases.py::test_gt_filter_nan_polars_behavior`.

**Step 1: Verify the existing failing test**

```bash
pytest tests/unit/test_boundary_cases.py::test_gt_filter_nan_polars_behavior -v 2>&1
```

Read the test to understand the exact behavior being documented.

**Step 2: Write the fix test (desired behavior)**

In `tests/unit/test_boundary_cases.py` — add next to existing test:

```python
def test_gt_filter_excludes_nan_rows():
    """After fix: NaN rows must NOT appear in gt/lt/ge/le filter results."""
    import polars as pl
    from data_graph_studio.core.filtering import Filter, FilterOperator, FilteringScheme
    df = pl.DataFrame({"val": [1.0, float("nan"), 5.0, 10.0]})
    f = Filter(column="val", operator=FilterOperator.GT, value=0.0)
    scheme = FilteringScheme(name="test")
    result = scheme.apply_filters(df, [f])
    # NaN should be excluded
    assert result["val"].is_nan().sum() == 0
    assert len(result) == 2  # only 5.0 and 10.0
```

Run to verify fail:
```bash
pytest tests/unit/test_boundary_cases.py::test_gt_filter_excludes_nan_rows -v 2>&1 | tail -10
```

**Step 3: Find where gt/lt/ge/le are applied in filtering.py**

```bash
grep -n "gt\|lt\|ge\|le\|>.*value\|<.*value" data_graph_studio/core/filtering.py | head -20
```

**Step 4: Apply NaN exclusion**

In `_apply_single_filter` or the operator dispatch, add NaN exclusion for numeric comparison operators:

```python
# After applying the comparison, chain .filter(~pl.col(col).is_nan())
# Only for: GT, LT, GE, LE operators on numeric columns

if f.operator in (FilterOperator.GT, FilterOperator.LT, FilterOperator.GE, FilterOperator.LE):
    if data[f.column].dtype in NUMERIC_DTYPES:
        result = result.filter(~pl.col(f.column).is_nan())
```

**Step 5: Run the fix test**

```bash
pytest tests/unit/test_boundary_cases.py::test_gt_filter_excludes_nan_rows -v 2>&1 | tail -10
```

Expected: PASS.

**Step 6: Run full suite**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
```

**Step 7: Commit**

```bash
git add data_graph_studio/core/filtering.py tests/unit/test_boundary_cases.py
git commit -m "fix: exclude NaN rows from numeric range filters (gt/lt/ge/le)"
```

---

### Task 5.2: Add integration test for core→data load→filter pipeline

**File:**
- Create: `tests/unit/test_integration_core_pipeline.py`

**Why:** Auditor specifically flagged no integration tests between layers.

**Step 1: Create integration test file**

```python
"""Integration tests: core pipeline from file load to filtered output.

Tests the complete data path: DataEngine.load_file → state → FilteringScheme.apply_filters.
No UI, no Qt — pure core layer integration.
"""
import pytest
import polars as pl
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from data_graph_studio.core.filtering import Filter, FilterOperator, FilteringScheme
from data_graph_studio.core.data_engine import DataEngine
from data_graph_studio.core.app_state import AppState


@pytest.fixture
def sample_csv(tmp_path):
    """CSV with numeric and string columns."""
    p = tmp_path / "sample.csv"
    p.write_text("name,score,active\nalice,80,true\nbob,45,false\ncarol,90,true\n")
    return p


class TestCoreLoadFilter:
    def test_load_then_filter_returns_correct_rows(self, sample_csv):
        """Full pipeline: load CSV → filter by score → correct result."""
        state = AppState()
        engine = DataEngine(state)
        assert engine.load_file(str(sample_csv))

        df = engine.get_current_dataframe()
        assert df is not None

        scheme = FilteringScheme(name="test")
        f = Filter(column="score", operator=FilterOperator.GT, value=50.0)
        result = scheme.apply_filters(df, [f])

        assert len(result) == 2
        assert set(result["name"].to_list()) == {"alice", "carol"}

    def test_load_nonexistent_raises_data_load_error(self, tmp_path):
        from data_graph_studio.core.exceptions import DataLoadError
        state = AppState()
        engine = DataEngine(state)
        with pytest.raises(DataLoadError):
            engine.load_file(str(tmp_path / "ghost.csv"))

    def test_filter_nan_excluded_from_range(self, tmp_path):
        """NaN values must not appear in range filter results."""
        p = tmp_path / "nan_test.csv"
        p.write_text("val\n1.0\n\n5.0\n10.0\n")  # empty row → NaN
        state = AppState()
        engine = DataEngine(state)
        engine.load_file(str(p))
        df = engine.get_current_dataframe()

        scheme = FilteringScheme(name="test")
        f = Filter(column="val", operator=FilterOperator.GT, value=0.0)
        result = scheme.apply_filters(df, [f])
        assert result["val"].is_nan().sum() == 0
```

**Step 2: Run tests**

```bash
pytest tests/unit/test_integration_core_pipeline.py -v 2>&1 | tail -20
```

Fix any import paths that don't match the actual API. Consult `data_graph_studio/core/data_engine.py` for the correct method names.

**Step 3: Commit**

```bash
git add tests/unit/test_integration_core_pipeline.py
git commit -m "test: add core pipeline integration tests (load→filter, NaN, DataLoadError)"
```

---

## Final: GOAT Audit + Verify

### Task 6.1: Final verification

**Step 1: Full test suite**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/ -q 2>&1 | tail -5
```

Expected: ≥ 1485 passing (1469 + ~16 new tests across tracks 4-5).

**Step 2: Verify no files exceed 500 lines**

```bash
find data_graph_studio/ -name "*.py" | xargs wc -l | awk '$1 > 500 {print}' | sort -rn | grep -v "__pycache__\|total" | head -20
```

Expected: ≤ 5 files over 500 lines (down from 42).

**Step 3: Verify typed raises**

```bash
grep -rn "raise DataLoadError\|raise QueryError\|raise DatasetError\|raise ExportError\|raise ValidationError" data_graph_studio/core/ --include="*.py" | grep -v __pycache__ | wc -l
```

Expected: ≥ 30 (up from 7).

**Step 4: Verify observability wired**

```bash
grep -rn "timed_operation" data_graph_studio/core/ --include="*.py" | grep -v __pycache__
```

Expected: ≥ 5 files.

**Step 5: Push**

```bash
git push origin HEAD
```

**Step 6: Re-run GOAT audit**

Use `/goat-code` skill → score should be ≥ 9.0.

---

## Effort Summary

| Track | Tasks | Estimated Lines Changed | Expected Score Lift |
|---|---|---|---|
| 1. main_window.py split | 4 tasks | ~2060 moved | Function +2.5, Conventions +3.0 |
| 2. main_graph.py split | 5 tasks | ~2082 moved | Function +2.5, Conventions +3.0 |
| 3. Observability | 2 tasks | ~60 | Observability +3.0 |
| 4. Typed raises | 3 tasks | ~80 | Error Strategy +3.5 |
| 5. Tests + NaN fix | 2 tasks | ~100 | Tests +1.5, Architecture +1.5 |

**Total estimated time:** 1 full day of focused work.
