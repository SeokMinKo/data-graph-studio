# Test Quality Review: Data Graph Studio

## Summary

- **1,753 test functions** across **85 test files** with **3,418 total assertions**
- **Core module coverage: 67%** (28/42 modules have tests)
- **UI module coverage: 9.4%** (8 test files for 85 UI source files)
- **Overall health: Fair (5.5/10)** — solid foundation, critical gaps in UI and edge cases

---

## Coverage Gaps (Untested Modules)

### 14 Core Modules With Zero Tests

| Module | Risk | Missing Tests |
|--------|------|---------------|
| `formula_parser.py` | **CRITICAL** — security-sensitive | Injection attacks, eval/exec/import blocking |
| `expression_engine.py` | **HIGH** | NaN/Inf in SIN, COS, TAN, LOG, SQRT |
| `clipboard_manager.py` | **HIGH** | Malformed HTML, mismatched columns |
| `ipc_server.py` | **HIGH** | Concurrency, malformed messages |
| `comparison_report.py` | MEDIUM | Report generation edge cases |
| `dashboard_controller.py` | MEDIUM | Dashboard state management |
| `annotation_controller.py` | MEDIUM | Annotation CRUD |
| `column_dependency_graph.py` | MEDIUM | Circular deps, missing cols |
| `etl_helpers.py` | MEDIUM | Parser edge cases |
| `io_abstract.py` | LOW | Abstract interface contract |
| `transform_chain.py` | MEDIUM | Chain ordering, failure propagation |
| `updater.py` | LOW | Version comparison, network failure |
| `shortcut_controller.py` | LOW | Conflict detection |
| `view_sync.py` | MEDIUM | Sync under concurrent updates |

### UI Layer Crisis (9.4% coverage)

- 85 UI source files, only 8 test files
- Main window, dialogs, panels, wizards: effectively untested
- Only 3 basic Qt smoke tests
- Theme system barely tested

---

## Missing Edge Cases

### Data Shape Edge Cases
- **Empty DataFrame (0 rows, 0 columns)**: Only 18 tests check this; many code paths untested with empty input
- **Single row/column DataFrames**: Sampling, statistics, grouping all untested at boundary
- **All-duplicate values**: Group operations untested

### Data Quality Edge Cases
- **NaN/Inf values**: No pipeline tests for stats, filtering, chart rendering with NaN/Inf
- **Mixed types in column**: String column containing numbers/dates untested
- **Extremely large values**: Overflow in statistics calculations

### Unicode & Encoding
- Zero tests for Chinese/Korean/emoji column names
- No UTF-8 BOM handling tests
- No tests for surrogate characters in data

### File Corruption
- No tests for truncated CSV files
- No tests for invalid UTF-8 in file content
- No tests for schema mismatches (saved profile with different columns)
- No tests for partial parquet files

### Concurrency
- No concurrent file loading tests
- No cancel-during-load tests
- No streaming + filter interaction tests

### Performance Boundaries
- No tests with 10M+ rows
- No memory efficiency tests
- No sampling accuracy tests at boundary sizes

---

## Test Quality Issues

### Weak Assertions (Average 1.95 per test, target: 3+)

| Category | Count | Example |
|----------|-------|---------|
| Tests with 0-1 assertions | 40+ | `test_ui_imports.py` (0 asserts — just imports), `test_ui_qt_smoke.py` (1 assert per test) |
| "Doesn't crash" tests | 15+ | Calling function, asserting no exception, not checking result |
| Missing negative cases | Many | Testing happy path only, no invalid input tests |

### Excessive Mocking (37 instances)

Mocking hides real integration bugs:
- `test_export_controller.py` — mocks PDF generation completely
- `test_data_engine.py` — some tests mock the DataEngine they're supposed to test
- Many UI tests mock `AppState` so heavily they don't test real behavior

### Test Isolation Issues

- Session-scoped `QApplication` — shared across all Qt tests; ordering dependency risk
- Module-level functions in some test files modify global state without cleanup
- Tests relying on fixture execution order

### Slow Tests

- 2 tests with `time.sleep()` calls: 20ms + 150ms delays
- Several integration tests that do full file load (>1s each)
- No test timeout enforcement

### Duplicate Test Coverage (3 major areas)

1. **Expression evaluation**: Tested in `test_expressions.py`, `test_calculated_fields.py`, AND `test_formula_categorical.py` — overlapping logic
2. **File loading**: `test_file_loader.py` + `test_file_formats.py` + `test_integration.py` — same paths
3. **Filtering logic**: `test_filtering.py` + `test_data_query.py` + `test_data_engine.py` — partial overlap

---

## Test Organization Problems

- Test file naming inconsistent: `test_ui_qt_*` vs `test_ui_*` vs `test_*_panel`
- No test categories/marks for slow vs fast, unit vs integration
- `tests/unit/` directory exists but mostly empty — unclear boundary
- `conftest.py` large (check for god object patterns in test fixtures)

---

## Recommended New Tests (Priority Order)

### P0 — Critical (Add This Sprint)

1. **Formula parser security** — eval/exec/import injection blocking
   ```python
   def test_formula_parser_blocks_exec():
       with pytest.raises(SecurityError):
           FormulaParser.parse("exec('import os')")
   ```

2. **Expression engine NaN/Inf** — math function edge cases
   ```python
   def test_expression_engine_log_negative():
       result = ExpressionEngine.evaluate("LOG(-1)", df)
       assert result.is_nan().all()  # Not exception
   ```

3. **Empty DataFrame through full pipeline**
   ```python
   def test_data_engine_empty_df():
       engine = DataEngine()
       engine.load_from_df(pl.DataFrame())
       assert engine.row_count == 0
       assert engine.get_statistics() == {}
   ```

4. **File corruption handling**
   ```python
   def test_file_loader_truncated_csv(tmp_path):
       f = tmp_path / "bad.csv"
       f.write_bytes(b"col1,col2\n1,2\n3")  # truncated row
       result = FileLoader().load_file(str(f))
       assert result.success or result.error_message  # Not exception
   ```

### P1 — High (Next Sprint)

5. **NaN/Inf in statistics pipeline**
6. **Unicode column names end-to-end**
7. **Cancel file loading mid-stream**
8. **Concurrent dataset operations (threading)**

### P2 — Medium (Backlog)

9. **10M row performance benchmarks** (pytest-benchmark)
10. **Theme consistency tests** — ensure all widgets use theme tokens
11. **UI component snapshot tests** — catch regressions

---

## Overall Health Score

| Dimension | Score | Notes |
|-----------|-------|-------|
| Coverage breadth | 6/10 | 67% core, 9% UI |
| Assertion quality | 5/10 | 1.95 avg, too many smoke tests |
| Edge case coverage | 4/10 | Major gaps in NaN, Unicode, concurrency |
| Test isolation | 7/10 | Good fixtures, some ordering deps |
| Organization | 5/10 | Inconsistent naming, duplicate coverage |
| **Overall** | **5.5/10** | Fair |

**Strengths**: Large test count, good core business logic coverage, conftest fixtures reusable
**Weaknesses**: UI nearly untested, security-sensitive paths untested, no performance tests

**Effort to reach "Good" (7/10)**: ~200-300 new tests, 2-3 weeks
