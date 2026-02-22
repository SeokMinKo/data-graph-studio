# Phase 2 GOAT Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve code quality by reaching 80%+ docstring coverage, reducing max nesting depth from 19 to ≤5 in the worst offender, and adding Fail Fast input validation at core API boundaries.

**Architecture:** Three independent improvements: (1) docstring sweep targeting the two highest-debt files; (2) structural refactor of `filtering.py:to_expression()` using a dispatch-table pattern; (3) targeted Fail Fast guards at 4 public API entry points.

**Tech Stack:** Python 3.11+, pytest, ast (for coverage measurement)

**Branch:** `goat-code-audit`

**Baseline:**
- Docstring coverage: 71.3% (563/790 public functions)
- Target: 80% = 632/790 (need 69 more)
- Worst nesting: `filtering.py:to_expression()` depth=19
- Test count: 1,915 passing

---

## Task 1: Docstrings for `core/data_engine.py` (69 missing → reaches 80% overall)

**Files:**
- Modify: `data_graph_studio/core/data_engine.py`
- Test: verify with inline AST script

**Step 1: Measure current state**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python3 -c "
import ast
tree = ast.parse(open('data_graph_studio/core/data_engine.py').read())
missing = []
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name.startswith('_'): continue
        has_doc = (isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant))
        if not has_doc:
            missing.append((node.name, node.lineno))
print(f'Missing: {len(missing)}')
for n, l in missing:
    print(f'  line {l}: {n}()')
"
```

**Step 2: Read `data_graph_studio/core/data_engine.py` in full**

Read the file before adding docstrings. Understand what each public function does.

**Step 3: Add docstrings to every undocumented public function**

For each undocumented function, add a docstring following this format:
```python
def function_name(self, param: type) -> return_type:
    """
    One-sentence summary of what this does.

    Args:
        param: What this parameter represents and any constraints.

    Returns:
        What is returned and its shape/type.

    Raises:
        ExceptionType: When this exception is raised.
    """
```

Rules:
- One sentence summary on the first line
- `Args:` section if the function takes non-self parameters
- `Returns:` section if it returns something non-trivial
- `Raises:` section if it raises exceptions
- Property methods (@property): one-liner is fine — `"""Current DataFrame or None."""`
- Skip `Args:` for obvious single-parameter functions

**Step 4: Verify coverage improved**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python3 -c "
import ast, os
results = []
for root, dirs, files in os.walk('data_graph_studio/core'):
    for f in files:
        if not f.endswith('.py'): continue
        path = os.path.join(root, f)
        try:
            tree = ast.parse(open(path).read())
        except:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith('_'): continue
                has_doc = (isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant))
                results.append(has_doc)
total = len(results)
covered = sum(results)
print(f'Core coverage: {covered}/{total} = {covered/total*100:.1f}%')
"
```
Expected: ≥80%

**Step 5: Run full test suite**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/ -x -q 2>&1 | tail -3
```
Expected: 1915 passed, 4 skipped

**Step 6: Commit**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/core/data_engine.py && git commit -m "docs: add docstrings to data_engine.py public API (coverage +~9%)"
```

---

## Task 2: Docstrings for `core/state.py` top 20 public methods

**Files:**
- Modify: `data_graph_studio/core/state.py`

**Step 1: Find undocumented public methods**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python3 -c "
import ast
tree = ast.parse(open('data_graph_studio/core/state.py').read())
missing = []
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name.startswith('_'): continue
        has_doc = (isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant))
        if not has_doc:
            missing.append((node.name, node.lineno))
print(f'Missing: {len(missing)}')
for n, l in missing[:25]:
    print(f'  line {l}: {n}()')
"
```

**Step 2: Read `data_graph_studio/core/state.py`**

Focus on the undocumented public methods. Read them to understand their behavior.

**Step 3: Add docstrings to all undocumented public methods**

Same format as Task 1. For state methods, pay attention to:
- What state changes the method causes
- What events/signals are emitted
- Any invariants that must hold after the call

Example for state-mutation methods:
```python
def select(self, rows: List[int], add: bool = False) -> None:
    """
    Update the row selection set.

    Args:
        rows: Row indices to select. Must be non-negative.
        add: If True, add to existing selection. If False, replace it.

    Emits:
        selection_changed signal.
    """
```

**Step 4: Verify and test**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/ -x -q 2>&1 | tail -3
```

**Step 5: Commit**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/core/state.py && git commit -m "docs: add docstrings to state.py public methods (coverage +~7%)"
```

---

## Task 3: Refactor `filtering.py:to_expression()` — depth=19 → dispatch table

**Files:**
- Modify: `data_graph_studio/core/filtering.py`
- Test: `tests/unit/test_filtering_refactor.py`

**Context:** `to_expression()` at line 72 has depth=19 — a giant if/elif chain with 30+ branches. The fix is a dispatch table that maps filter types to handler functions.

**Step 1: Read `data_graph_studio/core/filtering.py` lines 72-250**

Understand the full if/elif chain. Note:
- What types/conditions are dispatched on?
- What does each branch return?
- Any shared logic between branches?

**Step 2: Write tests that capture current behavior**

```python
# tests/unit/test_filtering_refactor.py
"""Tests to verify to_expression() behavior is preserved after refactor."""
from data_graph_studio.core.filtering import FilterManager, FilterCondition

def test_equality_filter():
    """Basic equality condition produces correct expression."""
    fm = FilterManager()
    # Use actual FilterCondition/filter API to create an equality condition
    # and verify to_expression() returns the expected Polars expression
    # NOTE: Read the file first to understand the API, then write real tests
    pass  # Replace with real test after reading the file
```

**IMPORTANT:** Read the file first, then write meaningful tests. Do NOT write placeholder tests.

**Step 3: Run tests — verify they pass (baseline)**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_filtering_refactor.py -v
```

**Step 4: Refactor to dispatch table**

The pattern to apply:

```python
# BEFORE (if/elif chain):
def to_expression(self, col, condition):
    if condition.type == "equals":
        return col == condition.value
    elif condition.type == "not_equals":
        return col != condition.value
    elif condition.type == "greater_than":
        return col > condition.value
    # ... 27 more branches

# AFTER (dispatch table):
_FILTER_DISPATCH = {
    "equals": lambda col, cond: col == cond.value,
    "not_equals": lambda col, cond: col != cond.value,
    "greater_than": lambda col, cond: col > cond.value,
    # ... all branches as lambdas or named functions
}

def to_expression(self, col, condition):
    """
    Convert a filter condition to a Polars expression.

    Args:
        col: Polars column expression.
        condition: FilterCondition with type and value fields.

    Returns:
        Polars boolean expression.

    Raises:
        ValueError: If condition.type is not recognized.
    """
    handler = _FILTER_DISPATCH.get(condition.type)
    if handler is None:
        raise ValueError(f"Unknown filter type: {condition.type!r}")
    return handler(col, condition)
```

For complex branches (multi-line logic), extract named functions instead of lambdas:
```python
def _filter_contains(col, cond):
    """Handle 'contains' filter with case sensitivity."""
    if cond.case_sensitive:
        return col.str.contains(cond.value)
    return col.str.contains(cond.value, literal=True)

_FILTER_DISPATCH = {
    "contains": _filter_contains,
    ...
}
```

**Step 5: Run tests — verify all still pass**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_filtering_refactor.py tests/test_filtering.py -v
```

**Step 6: Verify nesting depth reduced**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python3 -c "
import ast

def max_nesting(node, depth=0):
    children = list(ast.iter_child_nodes(node))
    if not children: return depth
    control = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)
    max_d = depth
    for child in children:
        new_d = depth + (1 if isinstance(child, control) else 0)
        max_d = max(max_d, max_nesting(child, new_d))
    return max_d

tree = ast.parse(open('data_graph_studio/core/filtering.py').read())
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef,)) and node.name == 'to_expression':
        print(f'to_expression() nesting depth: {max_nesting(node)}')
"
```
Expected: ≤ 3

**Step 7: Run full test suite**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/ -x -q 2>&1 | tail -3
```

**Step 8: Commit**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/core/filtering.py tests/unit/test_filtering_refactor.py && git commit -m "refactor: replace to_expression() depth-19 if/elif chain with dispatch table"
```

---

## Task 4: Fail Fast validation at core API boundaries

**Files:**
- Modify: `data_graph_studio/core/data_engine.py`
- Modify: `data_graph_studio/core/file_loader.py`
- Modify: `data_graph_studio/core/state.py`
- Test: `tests/unit/test_fail_fast.py`

**Context:** Four public functions accept user input without validation:
1. `data_engine.py:drop_column(col_name)` — no empty string guard, no reserved name check
2. `file_loader.py:add_precision_column(column)` — accepts any string, no existence check
3. `state.py:select(rows)` — accepts negative indices
4. `state.py:deselect(rows)` — same issue

**Step 1: Write failing tests**

```python
# tests/unit/test_fail_fast.py
"""Fail Fast: core API must reject invalid input at the boundary."""
import pytest

def test_drop_column_rejects_empty_string():
    """drop_column() must raise ValueError for empty column name."""
    from data_graph_studio.core.data_engine import DataEngine
    engine = DataEngine()
    import polars as pl
    engine.update_dataframe(pl.DataFrame({"a": [1, 2, 3]}))
    with pytest.raises(ValueError, match="column name"):
        engine.drop_column("")

def test_drop_column_rejects_none():
    """drop_column() must raise TypeError for None."""
    from data_graph_studio.core.data_engine import DataEngine
    engine = DataEngine()
    import polars as pl
    engine.update_dataframe(pl.DataFrame({"a": [1]}))
    with pytest.raises((ValueError, TypeError)):
        engine.drop_column(None)

def test_add_precision_column_rejects_empty_string():
    """add_precision_column() must raise ValueError for empty string."""
    from data_graph_studio.core.file_loader import FileLoader
    loader = FileLoader()
    with pytest.raises(ValueError, match="column"):
        loader.add_precision_column("")

def test_select_rejects_negative_indices():
    """select() must raise ValueError for negative row indices."""
    from data_graph_studio.core.state import AppState
    state = AppState.__new__(AppState)
    state.selected_rows = set()
    with pytest.raises(ValueError, match="row index"):
        state.select([-1, 0, 1])
```

**Step 2: Run — verify FAIL**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_fail_fast.py -v
```
Expected: All 4 FAIL (no validation exists yet)

**NOTE:** If instantiation fails (e.g. DataEngine requires arguments), read the file to understand the constructor, then adjust the test setup.

**Step 3: Read the target functions**

Read these sections:
- `data_graph_studio/core/data_engine.py` — `drop_column()` method
- `data_graph_studio/core/file_loader.py` — `add_precision_column()` method
- `data_graph_studio/core/state.py` — `select()` and `deselect()` methods

**Step 4: Add Fail Fast guards**

**`data_engine.py:drop_column()`:**
```python
def drop_column(self, col_name: str) -> None:
    """Remove a column from the active DataFrame."""
    if not isinstance(col_name, str) or not col_name.strip():
        raise ValueError(f"column name must be a non-empty string, got {col_name!r}")
    if self.df is None or col_name not in self.df.columns:
        return
    # ... rest of existing logic
```

**`file_loader.py:add_precision_column()`:**
```python
def add_precision_column(self, column: str) -> None:
    """Register a column for high-precision handling."""
    if not isinstance(column, str) or not column.strip():
        raise ValueError(f"column must be a non-empty string, got {column!r}")
    self._precision_columns.add(column)
```

**`state.py:select()`:**
```python
def select(self, rows: List[int], add: bool = False) -> None:
    """Update row selection. Rows must be non-negative integers."""
    invalid = [r for r in rows if not isinstance(r, int) or r < 0]
    if invalid:
        raise ValueError(f"row index must be a non-negative integer, got: {invalid[:3]}")
    if not add:
        self.selected_rows.clear()
    self.selected_rows.update(rows)
```

**Step 5: Run tests — verify they pass**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_fail_fast.py -v
```
Expected: 4/4 PASS

**Step 6: Run full test suite**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/ -x -q 2>&1 | tail -3
```
Expected: All passing (no regressions from stricter validation)

**Step 7: Commit**

```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/core/data_engine.py \
        data_graph_studio/core/file_loader.py \
        data_graph_studio/core/state.py \
        tests/unit/test_fail_fast.py && git commit -m "feat: add Fail Fast input validation at core API boundaries"
```

---

## Phase 2 Completion Checklist

- [ ] `data_engine.py` fully documented
- [ ] `state.py` top public methods documented
- [ ] Core docstring coverage ≥ 80%
- [ ] `to_expression()` nesting depth ≤ 3 (was 19)
- [ ] `drop_column()` rejects empty/None column names
- [ ] `add_precision_column()` rejects empty strings
- [ ] `select()` rejects negative indices
- [ ] All 1915+ tests passing
- [ ] 4 commits on `goat-code-audit` branch
