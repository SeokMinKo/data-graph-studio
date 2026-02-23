# Error Strategy & Test Coverage Improvement Design
Date: 2026-02-23

## Context

GOAT scores after previous round:
- Error Strategy: 7.6/10 (typed raise: 0 actual usages despite hierarchy existing)
- Test Coverage: 7.1/10 (10 untested core modules, no integration coverage)
- Coding Conventions: 7.8/10 (UI 220 bare excepts unlogged)

## Three Independent Tracks

### Track A — Typed raise adoption (Error Strategy)

**Problem:** `core/exceptions.py` defines DataLoadError, QueryError etc but zero `raise` callsites exist.
**Goal:** Add `raise DGSError-subclass(...)` at real error boundaries in core.

Target files (outermost validation layer = highest value):
- `file_loader.py` — failed load, unsupported format, encoding failure
- `filtering.py` — invalid filter spec, polars execution error
- `data_engine.py` — dataset not found, invalid column, cast failure
- `data_query.py` — streaming fallback should raise QueryError on all-paths failure

Pattern:
```python
except Exception as e:
    raise DataLoadError("CSV load failed", operation="load_csv",
                        context={"file": str(path), "encoding": enc}) from e
```

**Constraint:** Do NOT add raises where the current code intentionally swallows (fallback chains).

---

### Track B — UI bare except logging (Observability)

**Problem:** 220 bare `except Exception:` in `ui/` have zero logging context.
**Goal:** Add `logger.exception(...)` or `logger.error(..., exc_info=True)` to all.

Rules:
- Qt signal handlers → `exc_info=True` only (never propagate)
- Non-fatal UI events → `logger.warning(..., exc_info=True)`
- Fatal UI init → `logger.exception(...)`
- No logic changes, no typed raises in UI

---

### Track C — Untested core module tests

**Problem:** 10 core modules have 0 direct test files.
**Target modules (priority order):**
1. `comparison_algorithms.py` — statistical comparison logic
2. `data_exporter.py` — CSV/Excel/JSON export
3. `etl_helpers.py` — ETL parsing utils
4. `data_query_helpers.py` — query construction helpers
5. `comparison_report.py` — report generation
6. `comparison_report_types.py` — data types
7. `data_engine_analysis_mixin.py` — analysis methods
8. `data_engine_dataset_mixin.py` — dataset management
9. `chart_report_types.py` — chart types
10. `expressions_ast_evaluator.py` — expression eval

**Per module:** Normal (3), boundary (2), error (2) = min 7 tests each → ~70 new tests

---

## Execution Strategy

All 3 tracks are fully independent → parallel agent dispatch.

| Track | Agent | Files touched |
|-------|-------|--------------|
| A | Agent-A | core/file_loader.py, core/filtering.py, core/data_engine.py, core/data_query.py |
| B | Agent-B | ui/**/*.py (logging only, no logic) |
| C | Agent-C | tests/unit/test_comparison_algorithms.py + 4 more new test files |

## Success Criteria

- Track A: `grep "raise DataLoadError\|raise QueryError" core/` → ≥10 results
- Track B: UI bare except count drops from 220 → ≤20
- Track C: 5+ new test files, ≥50 new tests, 0 failures
- Full suite: 1220+ passing, 0 failures
