# Phase 3b: Observability — Core Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured logging to 14 key core files that currently have no logging, and replace silent `print()` error swallowing in UI files with proper `logger.error()` calls.

**Architecture:** Each file gets `logger = logging.getLogger(__name__)`. Key operation boundaries (function entry/exit for slow operations, error paths, state changes) get `logger.debug/info/warning/error` calls. Uses existing `StructuredFormatter` from Phase 1 (`core/logging_utils.py`).

**Tech Stack:** Python `logging` module, existing `core/logging_utils.py`, existing `__main__.py` log setup.

---

## Logging Convention

All new log calls must use keyword arguments for structured output (matching existing pattern):
```python
import logging
logger = logging.getLogger(__name__)

# At operation boundaries:
logger.debug("filtering.apply_filters started", extra={"scheme": scheme_name, "row_count": len(df)})
logger.warning("filtering.apply_filters failed", extra={"error": str(e), "scheme": scheme_name})
logger.error("cache.get miss", extra={"key": key})
```

Do NOT use `f"string {var}"` format strings in log messages — put variables in `extra={}` for structured parsing.

---

## Task 1: Add loggers to computation-heavy core files

**Files to modify:**
- `data_graph_studio/core/expression_engine.py` — 734 lines, evaluates user expressions
- `data_graph_studio/core/formula_parser.py` — 705 lines, parses/evaluates formulas
- `data_graph_studio/core/filtering.py` — 523 lines (has dispatch table from Phase 2)
- `data_graph_studio/core/cache.py` — 290 lines

**Step 1: Write test that logger exists**

Create `tests/unit/test_observability_loggers.py`:
```python
"""Key core modules must have loggers configured."""
import logging


def test_expression_engine_has_logger():
    import data_graph_studio.core.expression_engine as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_formula_parser_has_logger():
    import data_graph_studio.core.formula_parser as m
    assert hasattr(m, 'logger')


def test_filtering_has_logger():
    import data_graph_studio.core.filtering as m
    assert hasattr(m, 'logger')


def test_cache_has_logger():
    import data_graph_studio.core.cache as m
    assert hasattr(m, 'logger')


def test_comparison_manager_has_logger():
    import data_graph_studio.core.comparison_manager as m
    assert hasattr(m, 'logger')


def test_marking_has_logger():
    import data_graph_studio.core.marking as m
    assert hasattr(m, 'logger')


def test_annotation_controller_has_logger():
    import data_graph_studio.core.annotation_controller as m
    assert hasattr(m, 'logger')


def test_dashboard_controller_has_logger():
    import data_graph_studio.core.dashboard_controller as m
    assert hasattr(m, 'logger')


def test_profile_store_has_logger():
    import data_graph_studio.core.profile_store as m
    assert hasattr(m, 'logger')


def test_project_has_logger():
    import data_graph_studio.core.project as m
    assert hasattr(m, 'logger')


def test_undo_manager_has_logger():
    import data_graph_studio.core.undo_manager as m
    assert hasattr(m, 'logger')


def test_statistics_has_logger():
    import data_graph_studio.core.statistics as m
    assert hasattr(m, 'logger')
```

**Step 2: Run to confirm FAIL**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_observability_loggers.py -v 2>&1 | tail -20
```

**Step 3: Add loggers to expression_engine.py**

At the top of the file, after existing imports:
```python
import logging
logger = logging.getLogger(__name__)
```

Then add log calls at key boundaries. Read the file first to identify:
- Entry points of `evaluate()` / `_evaluate_ast()` — add `logger.debug`
- Exception handlers — add `logger.warning` or `logger.error`
- Example:
```python
def evaluate(self, expr: str, context: dict) -> Any:
    logger.debug("expression_engine.evaluate", extra={"expr": expr[:80]})
    try:
        result = self._evaluate_ast(...)
        return result
    except ExpressionError as e:
        logger.warning("expression_engine.evaluate failed", extra={"expr": expr[:80], "error": str(e)})
        raise
```

**Step 4: Add loggers to formula_parser.py**

Same pattern. Key locations:
- `parse()` entry point
- `_eval_prepared()` (117-line function — add warning on exception)
- Any `except` block that currently silently fails

**Step 5: Add logger to filtering.py**

Add `import logging` / `logger = logging.getLogger(__name__)` near top.
Add to `_filter_contains`, `_filter_not_contains` and the `apply_filters()` catch block:
```python
# In apply_filters() exception handler:
except Exception as e:
    logger.warning("filtering.apply_filters skipped", extra={"filter": cond.column, "error": str(e)})
```

**Step 6: Add logger to cache.py**

Add logger. Add at cache miss/eviction paths:
```python
logger.debug("cache.miss", extra={"key": key})
logger.debug("cache.evicted", extra={"evicted_count": n})
```

**Step 7: Run tests**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_observability_loggers.py::test_expression_engine_has_logger tests/unit/test_observability_loggers.py::test_formula_parser_has_logger tests/unit/test_observability_loggers.py::test_filtering_has_logger tests/unit/test_observability_loggers.py::test_cache_has_logger -v
```
Expected: 4/4 PASS

**Step 8: Full suite**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/ -x -q 2>&1 | tail -5
```

**Step 9: Commit**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/core/expression_engine.py data_graph_studio/core/formula_parser.py data_graph_studio/core/filtering.py data_graph_studio/core/cache.py tests/unit/test_observability_loggers.py && git commit -m "feat: add structured logging to expression_engine, formula_parser, filtering, cache"
```

---

## Task 2: Add loggers to controller/manager core files

**Files to modify:**
- `data_graph_studio/core/comparison_manager.py` — 449 lines
- `data_graph_studio/core/marking.py` — 447 lines
- `data_graph_studio/core/annotation_controller.py` — 336 lines
- `data_graph_studio/core/dashboard_controller.py` — 292 lines

**Step 1: Run failing tests**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_observability_loggers.py::test_comparison_manager_has_logger tests/unit/test_observability_loggers.py::test_marking_has_logger tests/unit/test_observability_loggers.py::test_annotation_controller_has_logger tests/unit/test_observability_loggers.py::test_dashboard_controller_has_logger -v 2>&1 | tail -10
```

**Step 2: Add loggers to each file**

For each file, add at top:
```python
import logging
logger = logging.getLogger(__name__)
```

Key log points by file:
- `comparison_manager.py`: `load_dataset()`, `remove_dataset()` entry points
- `marking.py`: `update_marking()` when indices change, `create_marking()`, `remove_marking()`
- `annotation_controller.py`: `add_annotation()`, `delete_annotation()`, error paths
- `dashboard_controller.py`: `save_dashboard()`, `load_dashboard()`, error paths

**Step 3: Run targeted tests + full suite, commit**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/core/comparison_manager.py data_graph_studio/core/marking.py data_graph_studio/core/annotation_controller.py data_graph_studio/core/dashboard_controller.py && git commit -m "feat: add structured logging to comparison_manager, marking, annotation_controller, dashboard_controller"
```

---

## Task 3: Add loggers to storage/persistence core files

**Files to modify:**
- `data_graph_studio/core/profile_store.py` — 111 lines
- `data_graph_studio/core/project.py` — (check line count first)
- `data_graph_studio/core/undo_manager.py`
- `data_graph_studio/core/statistics.py`

**Step 1: Run failing tests**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_observability_loggers.py::test_profile_store_has_logger tests/unit/test_observability_loggers.py::test_project_has_logger tests/unit/test_observability_loggers.py::test_undo_manager_has_logger tests/unit/test_observability_loggers.py::test_statistics_has_logger -v 2>&1 | tail -10
```

**Step 2: Add loggers + key log calls**

- `profile_store.py`: log profile load/save operations, async failures
- `project.py`: log project open/save/close, errors
- `undo_manager.py`: log push/undo/redo operations, stack overflow
- `statistics.py`: log calculation entry/exit (debug level), errors

**Step 3: Run full suite, commit**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/core/profile_store.py data_graph_studio/core/project.py data_graph_studio/core/undo_manager.py data_graph_studio/core/statistics.py && git commit -m "feat: add structured logging to profile_store, project, undo_manager, statistics"
```

---

## Task 4: Replace print() error swallowing in UI files

**Files to modify:**
- `data_graph_studio/ui/panels/table_panel.py` (lines 421, 461)
- `data_graph_studio/ui/panels/grouped_table_model.py` (line 628)
- `data_graph_studio/ui/panels/main_graph.py` (line 264)
- `data_graph_studio/ui/panels/graph_panel/graph_panel.py` (line 1076)
- `data_graph_studio/ui/panels/graph_widgets.py` (lines 127, 182, 232)
- `data_graph_studio/ui/drawing.py` (line 1157)

**Note:** `cli.py` print() calls are intentional (CLI output to stdout) — do NOT change those.
`api.py:297` and `api_server.py:365` are user-facing messages — leave as-is or convert to warnings.

**Step 1: Write test (structural)**

```python
def test_no_silent_print_errors_in_ui_panels():
    """UI panels must not use print() for error handling."""
    import ast, pathlib
    target_files = [
        "data_graph_studio/ui/panels/table_panel.py",
        "data_graph_studio/ui/panels/graph_panel/graph_panel.py",
        "data_graph_studio/ui/panels/graph_widgets.py",
    ]
    root = pathlib.Path("/Users/lov2fn/Projects/data-graph-studio")
    for rel_path in target_files:
        src = (root / rel_path).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Name) and
                    node.func.id == "print"):
                # Check if it's inside an except block
                # (simple check: line context)
                lines = src.splitlines()
                line = lines[node.lineno - 1].strip()
                assert "print" not in line, f"print() found in {rel_path}:{node.lineno}: {line}"
```

Note: this test is tricky to write perfectly. Instead, just manually verify the changes are correct after implementing.

**Step 2: Add loggers to affected UI files**

For each file, at the top add:
```python
import logging
logger = logging.getLogger(__name__)
```

**Step 3: Replace each print() with logger.error()**

Examples:
```python
# table_panel.py:421
# BEFORE:
except Exception as e:
    print(f"Sort error: {e}")
# AFTER:
except Exception as e:
    logger.error("table_panel.sort_error", extra={"error": str(e)})

# graph_widgets.py:127
# BEFORE:
except Exception as e:
    print(f"Error plotting histogram: {e}")
# AFTER:
except Exception as e:
    logger.error("graph_widgets.histogram_error", extra={"error": str(e)})
```

**Step 4: Full suite + commit**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/ui/panels/table_panel.py data_graph_studio/ui/panels/grouped_table_model.py data_graph_studio/ui/panels/main_graph.py data_graph_studio/ui/panels/graph_panel/graph_panel.py data_graph_studio/ui/panels/graph_widgets.py data_graph_studio/ui/drawing.py && git commit -m "fix: replace print() error handlers with structured logger.error() in UI panels"
```

---

## Phase 3b Completion Checklist

- [ ] 12 core files have `logger = logging.getLogger(__name__)`
- [ ] Key operation boundaries have debug/warning/error log calls
- [ ] 8 UI print() error handlers replaced with logger.error()
- [ ] All tests pass (baseline: 1960)
- [ ] `test_observability_loggers.py` with 12 tests all green
- [ ] 4 commits on goat-code-audit branch

**Files NOT needing loggers (intentionally skipped):**
- `core/__init__.py`, `core/constants.py`, `core/types.py` — no logic
- `core/expressions.py`, `core/parsing.py`, `core/parsing_utils.py` — check if trivial
- `cli.py` — print() is intentional CLI output
