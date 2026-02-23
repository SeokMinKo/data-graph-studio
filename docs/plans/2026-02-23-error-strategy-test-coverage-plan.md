# Error Strategy & Test Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Raise GOAT Error Strategy score to 8.5+ and Test Coverage to 8.0+ by adopting typed raises in core, logging UI bare excepts, and adding tests for 10 untested modules.

**Architecture:** Three independent tracks executed in parallel — Track A adds typed raise callsites at real error boundaries; Track B mechanically adds exc_info=True to UI bare excepts; Track C writes normal/boundary/error tests for untested core modules.

**Tech Stack:** Python 3.11, PySide6, Polars, Pytest, Hypothesis

---

## Track A — Typed raise adoption in core

### Task A1: Add typed raises to file_loader.py

**Files:**
- Modify: `data_graph_studio/core/file_loader.py`

**Context:**
```bash
grep -n "except\|return False\|return None" data_graph_studio/core/file_loader.py | head -30
```

**Step 1: Read the file's error paths**

Find every location where load fails silently (returns False/None without raising).
Key targets:
- Unsupported file format detection
- Encoding detection failure
- CSV/parquet parse failure

**Step 2: Add typed raises**

```python
# Before (swallow pattern):
except Exception as e:
    logger.error("load.failed", exc_info=True)
    return False

# After (raise at boundary):
except Exception as e:
    raise DataLoadError(
        f"Failed to load {path.suffix} file",
        operation="load_file",
        context={"file": str(path), "suffix": path.suffix}
    ) from e
```

Import at top of file:
```python
from .exceptions import DataLoadError
```

**Step 3: Run tests**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/test_file_loader.py -q
```
Expected: same count, 0 failures

**Step 4: Commit**
```bash
git add data_graph_studio/core/file_loader.py
git commit -m "feat: raise DataLoadError at file loading boundaries"
```

---

### Task A2: Add typed raises to filtering.py

**Files:**
- Modify: `data_graph_studio/core/filtering.py`

**Step 1: Identify error paths**
```bash
grep -n "except\|return\b" data_graph_studio/core/filtering.py | head -20
```

**Step 2: Add QueryError at invalid filter spec**

```python
from .exceptions import QueryError

# In _apply_single_filter or equivalent:
except Exception as e:
    raise QueryError(
        "Filter execution failed",
        operation="_apply_single_filter",
        context={"column": col, "operator": op, "value": str(val)}
    ) from e
```

**Step 3: Run tests**
```bash
pytest tests/unit/test_filtering.py tests/unit/test_boundary_cases.py -q
```
Expected: all pass

**Step 4: Commit**
```bash
git add data_graph_studio/core/filtering.py
git commit -m "feat: raise QueryError at filter execution boundaries"
```

---

### Task A3: Add typed raises to data_engine.py

**Files:**
- Modify: `data_graph_studio/core/data_engine.py`

**Step 1: Find dataset-not-found and invalid-column paths**
```bash
grep -n "return None\|return False\|except Exception" data_graph_studio/core/data_engine.py | head -20
```

**Step 2: Add DatasetError / QueryError**

```python
from .exceptions import DatasetError, QueryError

# Dataset not found:
def get_dataset(self, dataset_id: str):
    ds = self._datasets.get(dataset_id)
    if ds is None:
        raise DatasetError(
            f"Dataset not found: {dataset_id}",
            operation="get_dataset",
            context={"dataset_id": dataset_id}
        )
    return ds
```

**Step 3: Run tests**
```bash
pytest tests/unit/test_data_engine.py tests/unit/test_data_engine_errors.py -q
```

**Step 4: Commit**
```bash
git add data_graph_studio/core/data_engine.py
git commit -m "feat: raise DatasetError/QueryError at data engine boundaries"
```

---

## Track B — UI bare except logging

### Task B1: Add exc_info=True to all UI bare excepts

**Files:**
- Modify: All `data_graph_studio/ui/**/*.py` files with bare `except Exception:`

**Step 1: Get the full list**
```bash
grep -rn "except Exception\b" data_graph_studio/ui/ --include="*.py" | grep -v __pycache__ | wc -l
```

**Step 2: Apply pattern mechanically**

For every bare `except Exception:` or `except Exception as e:` in UI:

```python
# If file has no logger, add at module top:
import logging
logger = logging.getLogger(__name__)

# Pattern for Qt signal handlers (never propagate):
except Exception:
    logger.exception("panel_name.handler_name.error")

# Pattern for non-fatal UI operations:
except Exception:
    logger.warning("operation_name.failed", exc_info=True)
```

**Rules:**
- Qt signal handlers → `logger.exception(...)` (never re-raise, Qt crashes)
- File operations in UI → `logger.warning(..., exc_info=True)`
- Init/setup failures → `logger.error(..., exc_info=True)`
- NO logic changes
- NO typed raises in UI layer

**Step 3: Run full test suite**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/ -q 2>&1 | tail -5
```
Expected: 1220+ passed, 0 failures

**Step 4: Verify count dropped**
```bash
grep -rn "except Exception\b" data_graph_studio/ui/ --include="*.py" | grep -v __pycache__ | grep -v "exc_info\|logger" | wc -l
```
Expected: ≤20 (only truly silent defensive catches remain)

**Step 5: Commit**
```bash
git add data_graph_studio/ui/
git commit -m "fix: add exc_info logging to UI bare except handlers"
```

---

## Track C — Tests for untested core modules

### Task C1: Tests for comparison_algorithms.py

**Files:**
- Create: `tests/unit/test_comparison_algorithms.py`

**Step 1: Read the module**
```bash
grep -n "def " data_graph_studio/core/comparison_algorithms.py
head -100 data_graph_studio/core/comparison_algorithms.py
```

**Step 2: Write tests** — min 7 tests:
- 3 normal cases (happy path with known outputs)
- 2 boundary cases (empty input, single element)
- 2 error cases (invalid input types, mismatched lengths)

**Step 3: Run**
```bash
pytest tests/unit/test_comparison_algorithms.py -v
```

**Step 4: Commit**
```bash
git add tests/unit/test_comparison_algorithms.py
git commit -m "test: add tests for comparison_algorithms"
```

---

### Task C2: Tests for data_exporter.py

**Files:**
- Create: `tests/unit/test_data_exporter_core.py`

**Step 1: Read the module**
```bash
grep -n "def " data_graph_studio/core/data_exporter.py
```

**Step 2: Write tests** — test each export format:
- CSV export produces valid CSV
- Excel export produces valid file bytes
- JSON export produces valid JSON
- Export with 0 rows (boundary)
- Export with special chars / Unicode (boundary)
- Export to non-existent path raises ExportError (error case)

**Step 3: Run and commit**

---

### Task C3: Tests for etl_helpers.py

**Files:**
- Create: `tests/unit/test_etl_helpers.py`

**Step 1: Read the module**
```bash
grep -n "def " data_graph_studio/core/etl_helpers.py
head -80 data_graph_studio/core/etl_helpers.py
```

**Step 2: Write tests** — ETL parsing utils:
- Timestamp parsing (normal: ISO, boundary: epoch 0, error: garbage string)
- Numeric coercion (normal: "1.5", boundary: "0", error: "abc")
- Binary read helpers if present

**Step 3: Run and commit**

---

### Task C4: Tests for data_query_helpers.py + comparison_report.py

**Files:**
- Create: `tests/unit/test_data_query_helpers.py`
- Create: `tests/unit/test_comparison_report.py`

Write 7 tests per file following the same pattern.

**Commit both:**
```bash
git add tests/unit/test_data_query_helpers.py tests/unit/test_comparison_report.py
git commit -m "test: add tests for data_query_helpers and comparison_report"
```

---

### Task C5: Tests for remaining 5 modules

**Files:**
- Create: `tests/unit/test_expressions_ast_evaluator.py`
- Create: `tests/unit/test_data_engine_mixins.py` (covers analysis_mixin + dataset_mixin)
- Create: `tests/unit/test_chart_report_types.py`

Write min 5 tests per file. Focus on:
- Type contracts (inputs/outputs match declared types)
- Error propagation (exceptions raised correctly)
- Boundary values (empty, single, large)

**Commit:**
```bash
git add tests/unit/test_expressions_ast_evaluator.py tests/unit/test_data_engine_mixins.py tests/unit/test_chart_report_types.py
git commit -m "test: add tests for remaining untested core modules"
```

---

## Final Verification

### Task Final: Full suite + GOAT check

**Step 1: Run full test suite**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/ -q 2>&1 | tail -5
```
Expected: 1270+ passed, 0 failures

**Step 2: Verify typed raises exist**
```bash
grep -rn "raise DataLoadError\|raise QueryError\|raise DatasetError" data_graph_studio/core/ --include="*.py" | grep -v __pycache__
```
Expected: ≥10 results

**Step 3: Verify UI logging improved**
```bash
grep -rn "except Exception\b" data_graph_studio/ui/ --include="*.py" | grep -v __pycache__ | grep -v "exc_info\|logger" | wc -l
```
Expected: ≤20

**Step 4: Push**
```bash
git push origin HEAD
```
