# Code Review: Data Graph Studio

**Reviewer**: Claude (AI)
**Date**: 2026-02-27
**Scope**: Full codebase review (architecture, security, correctness, maintainability)

---

## 1. Project Overview

Data Graph Studio is a PySide6-based desktop application for big data visualization. It uses Polars as its data engine, supports multiple chart types (pyqtgraph/plotly), multi-dataset comparison, profile management, streaming/live data, IPC control, and an optional REST API. The codebase is well-structured with clear separation of concerns.

**Tech Stack**: Python 3.9+, PySide6, Polars, DuckDB, pyqtgraph, plotly, numpy, scipy

---

## 2. Architecture (Good)

### Strengths
- **Facade Pattern** (`DataEngine`): Clean delegation to `FileLoader`, `DataQuery`, `DataExporter`, `DatasetManager`, `ComparisonEngine` — good decomposition of a 680-line facade.
- **Controller Extraction**: `MainWindow` is decomposed into ~15 UI controllers (`FileLoadingController`, `DatasetController`, `ProfileUIController`, etc.), keeping each controller focused.
- **Stateless Query Layer** (`DataQuery`): All methods take `DataFrame` as input — easy to test, no hidden state.
- **Plugin-style Chart System**: Each chart type (`bubble.py`, `candlestick.py`, `violin_plot.py`, etc.) is a separate module.
- **LTTB Sampling**: Proper implementation of Largest Triangle Three Buckets for large dataset visualization.
- **Undo/Redo**: Lightweight command-pattern `UndoStack` with categorized action types.

### Concerns
- **DataEngine facade is overly verbose**: ~180 lines of pure delegation boilerplate (e.g., `def filter(self, column, operator, value): return self._query.filter(self.df, column, operator, value)`). Consider using `__getattr__` delegation or generating wrappers to reduce maintenance burden.
- **Duplicated constants**: `DEFAULT_CHUNK_SIZE`, `LARGE_FILE_THRESHOLD`, `MAX_RETRIES` etc. are defined in both `DataEngine` and `FileLoader`. Only `FileLoader`'s are actually used.

---

## 3. Security Issues

### 3.1 CRITICAL: IPC `exec` Command — Remote Code Execution

**File**: `dgs_client.py:106-110`

```python
elif cmd == 'exec':
    result = send_command('execute', code=sys.argv[2])
```

The client sends arbitrary Python code via the `execute` IPC command. If a corresponding server-side handler evaluates this with `eval()`/`exec()`, this is a **remote code execution** vulnerability. Even though IPC is local-only (Unix Domain Socket), any local process or user could execute arbitrary code in the context of the application.

**Recommendation**: Remove the `exec`/`execute` command entirely, or restrict it to a safe whitelist of operations. If dynamic evaluation is required, sandbox it heavily.

### 3.2 HIGH: Filtering — Regex Injection

**File**: `data_graph_studio/core/filtering.py:146`

```python
elif self.operator == FilterOperator.MATCHES_REGEX:
    return col.cast(pl.Utf8).str.contains(str(self.value))
```

User-supplied regex is passed directly to `str.contains()` without validation. A malicious or accidental [ReDoS](https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS) pattern (e.g., `(a+)+$`) could cause catastrophic backtracking and freeze the application.

**Recommendation**: Wrap regex compilation in a `try/except re.error`, set a timeout, or use `literal=True` where regex isn't explicitly needed.

### 3.3 MEDIUM: API Server — No Upload Size Limit

**File**: `data_graph_studio/api_server.py:91-174, 205-245`

The REST API accepts file uploads with no size limit. An attacker could upload a massive file and exhaust server memory.

**Recommendation**: Add `UploadFile` size limits or configure FastAPI/Starlette middleware to limit request body size.

### 3.4 MEDIUM: API Server — No Authentication

**File**: `data_graph_studio/api_server.py`

The REST API server has no authentication mechanism. While it binds to `127.0.0.1` by default (good), any local process can access it.

**Recommendation**: Add at minimum a bearer token or API key for production use.

### 3.5 MEDIUM: API Server — In-Memory Data Store Without Eviction

**File**: `data_graph_studio/api_server.py:63`

```python
_data_store: dict = {}
```

Uploaded data is stored in a global dict with no size limit or TTL eviction. This is a memory leak vector.

**Recommendation**: Add a maximum entry count, TTL-based eviction, or LRU cache.

### 3.6 LOW: IPC Client Protocol Mismatch

**File**: `dgs_client.py:41-66`

The standalone `dgs_client.py` uses raw TCP sockets (`socket.AF_INET`) while the server (`ipc_server.py`) uses `QLocalServer` (Unix Domain Socket). These are **incompatible protocols**. The client will always get `ConnectionRefusedError`.

**Recommendation**: Update `dgs_client.py` to use Unix Domain Sockets (matching the server) or provide a separate TCP-based client. Currently this file is effectively dead code.

---

## 4. Bugs & Correctness

### 4.1 `_get_all_filters` — Infinite Recursion Possible

**File**: `data_graph_studio/core/filtering.py:466-478`

```python
def _get_all_filters(self, scheme: FilteringScheme) -> List[Filter]:
    if scheme.inherit_from and scheme.inherit_from in self._schemes:
        parent = self._schemes[scheme.inherit_from]
        filters.extend(self._get_all_filters(parent))
```

If scheme A inherits from B and B inherits from A (circular inheritance), this will recurse infinitely and crash.

**Recommendation**: Track visited schemes in a `set` parameter:

```python
def _get_all_filters(self, scheme, visited=None):
    visited = visited or set()
    if scheme.name in visited:
        return []
    visited.add(scheme.name)
    ...
```

### 4.2 `ExpressionEngine.IF` — O(n) Python Loop

**File**: `data_graph_studio/core/expression_engine.py:569-581`

```python
if func_name == 'IF':
    result = []
    for i in range(len(condition)):
        if condition[i]:
            result.append(then_value[i] ...)
```

This iterates row-by-row in pure Python. For a 1M-row DataFrame, this will be extremely slow.

**Recommendation**: Use `pl.when(condition).then(then_value).otherwise(else_value)` for vectorized execution.

### 4.3 `ExpressionEngine` — Missing Return for Binary Ops

**File**: `data_graph_studio/core/expression_engine.py:380-396`

The `binary` case has no explicit `return` at the end — if `op` is `^`, the function returns `left.pow(right)` correctly, but there's no `else` clause or final `return`. If an unsupported operator sneaks through, it silently falls through to the `comparison` block.

**Recommendation**: Add a `raise ExpressionError(f"Unknown operator: {op}")` at the end of the binary block.

### 4.4 `DataSampler.random_sample` — Global Random State Mutation

**File**: `data_graph_studio/graph/sampling.py:181`

```python
np.random.seed(seed)
```

This mutates global NumPy random state, which can cause non-determinism in other parts of the application running concurrently.

**Recommendation**: Use `np.random.default_rng(seed)` for isolated random state:

```python
rng = np.random.default_rng(seed)
indices = np.sort(rng.choice(n, n_samples, replace=False))
```

### 4.5 `dgs_client.py` — Token Not Sent

**File**: `dgs_client.py:49`

```python
data = json.dumps({'command': command, 'args': args}, ensure_ascii=False)
```

The client never includes the `token` field in its requests, but the server requires it for authentication. All requests will be rejected with "Authentication failed".

**Recommendation**: Read the token from the port file and include it in the payload.

---

## 5. Performance

### 5.1 DataEngine Cache — Hash Collision Risk

**File**: `data_graph_studio/core/data_engine.py:138-141`

```python
def _cache_key(self, operation: str, *args) -> str:
    return f"{dataset_id}:{operation}:{hash(args)}"
```

Python's `hash()` can produce collisions (especially for tuples of similar values). This could cause incorrect cached results to be returned.

**Recommendation**: Use a more robust hash like `hashlib.md5(repr(args).encode()).hexdigest()` or simply use `repr(args)` directly.

### 5.2 Memory Optimization — Aggressive Float32 Downcast

**File**: `data_graph_studio/core/file_loader.py:812`

```python
if not should_keep:
    cast_exprs.append(pl.col(col).cast(pl.Float32))
```

In `PrecisionMode.AUTO`, all Float64 columns are downcast to Float32 unless the column name matches precision-sensitive patterns. This can cause data loss for scientific/financial data where column names don't follow the predefined patterns.

**Recommendation**: Consider checking actual value ranges before downcasting, or make AUTO mode more conservative (keep Float64 by default).

### 5.3 `_load_text` — Entire File Loaded Into Memory

**File**: `data_graph_studio/core/file_loader.py:628-700`

The text file loader reads all lines into a list, then creates another list of split rows, then constructs a DataFrame. For a 1M-line file, this triples memory usage.

**Recommendation**: For large text files, consider streaming the parse or converting to CSV first (as already done for large CSVs → Parquet).

---

## 6. Code Quality

### 6.1 Inconsistent Error Handling Pattern

Many methods use broad `except Exception: pass` or `except Exception: continue` which silently swallows errors:

- `data_query.py:68-71` — filter fallback
- `filtering.py:458-462` — filter apply
- `data_engine.py:597-599` — cast_column

While defensive, this makes debugging very difficult.

**Recommendation**: At minimum, log the exception at `DEBUG` or `WARNING` level before suppressing.

### 6.2 DataEngine Dead Property Comments

**File**: `data_graph_studio/core/data_engine.py:506, 670`

Two sections both have `# -- clear ----------------------------------------------------------------` comment headers. The first one at line 506 actually contains `recommend_chart_type`, not a clear method.

### 6.3 Unused Import

**File**: `data_graph_studio/core/file_loader.py:26`

`numpy` is imported at the top level but never directly used in the module (only used via Polars).

### 6.4 Version Hardcoded in Multiple Places

- `main.py:132` — `"0.1.0"`
- `api_server.py:34-35` — `"1.0.0"` (different from main!)
- `setup.py` uses `setuptools_scm` for versioning

**Recommendation**: Consolidate version into a single source of truth (e.g., `_build_version.py` or `importlib.metadata`).

---

## 7. Testing

The project has a solid test suite with ~95 test files covering:
- Unit tests for core engine, filtering, expressions, profiles
- Qt smoke tests (`test_ui_qt_smoke.py`)
- Integration tests (`test_integration_comprehensive.py`)
- Security tests (`test_ipc_security.py`, `test_updater_validation.py`)

**Positive**: The presence of `test_ipc_security.py` and `test_updater_validation.py` shows security-conscious development.

---

## 8. Summary

| Category | Rating | Notes |
|----------|--------|-------|
| Architecture | Good | Clean Facade + Controller pattern, good separation |
| Security | Needs Work | IPC exec command, regex injection, API limits |
| Correctness | Good | Few bugs, mostly edge cases |
| Performance | Good | LTTB sampling, lazy evaluation, memory optimization |
| Testing | Good | Comprehensive coverage including security tests |
| Code Quality | Good | Well-organized, Korean+English comments, minor issues |

### Priority Fixes
1. **P0**: Remove or sandbox `exec`/`execute` IPC command
2. **P0**: Add ReDoS protection to regex filter
3. **P1**: Fix IPC client/server protocol mismatch (`dgs_client.py`)
4. **P1**: Vectorize `IF` function in ExpressionEngine
5. **P1**: Add circular inheritance guard in FilteringManager
6. **P2**: Add upload size limits to API server
7. **P2**: Fix cache key hash collision risk
8. **P2**: Use isolated random state in sampling
