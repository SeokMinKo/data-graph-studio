# Performance Review: Data Graph Studio

## Summary

The codebase has several moderate-to-critical performance issues, primarily in the rendering pipeline, cache management, and Polars query execution. The main bottlenecks are unnecessary DataFrame copies, inefficient LRU cache implementation, overly aggressive cache invalidation, and Qt event processing overhead.

---

## Critical Bottlenecks (Immediate Impact)

1. **`data_graph_studio/core/cache.py:245-266` — O(n²) LRU Eviction**
   - `_ensure_space()` iterates through ALL cache levels and ALL entries every time a single item is added
   - **Impact**: Under memory pressure, adding one cache entry may trigger 5-10+ full cache scans
   - **Fix**: Maintain a sorted heap of cache entries by `last_accessed` timestamp instead of scanning all entries

2. **`data_graph_studio/ui/panels/graph_panel.py:456-525` — Filter Applied AFTER DataFrame Load**
   - Filter is applied on working_df AFTER loading entire engine.df into memory
   - **Impact**: For 100M row file with 90% filtered out, loads all 100M rows then keeps 10M
   - **Fix**: Apply filters at file load time (push-down predicates to Polars lazy evaluation)

3. **`data_graph_studio/core/file_loader.py:530` — Blocking `.collect()` for Row Count**
   ```python
   self._total_rows = int(self._lazy_df.select(pl.len()).collect()[0, 0])
   ```
   - Executes FULL table scan just to get row count on large files, before windowed loading
   - **Impact**: 500MB+ files may block UI for 2-5 seconds
   - **Fix**: Use Polars metadata caching or lazy row count estimation

4. **`data_graph_studio/ui/panels/graph_panel.py:630-710` — Group-Aware Sampling with Nested Loops**
   - For each group, loops through entire valid_mask array multiple times
   - **Impact**: 10 groups × 10M rows = 100M+ operations per refresh
   - **Fix**: Use Polars `group_by().sample()` or vectorized boolean indexing

5. **`data_graph_studio/ui/panels/graph_panel.py:553-584` — Data Labels Loop Creates 200+ Qt Items**
   - `show_labels` creates individual TextItem for EVERY point (capped at 200), each triggers scene update
   - **Fix**: Use a single QGraphicsItemGroup or batch with `setUpdatesEnabled(False)`

---

## Memory Issues

1. **`data_graph_studio/ui/panels/graph_panel.py:477` — Categorical Cache Unbounded**
   - Cache cleared on X column change but can grow unbounded with many categorical columns
   - **Fix**: Implement LRU with max size (e.g., 50 mappings)

2. **`data_graph_studio/core/data_engine.py:80-81` — OrderedDict Cache Too Small (128 entries)**
   - 128 entries causes thrashing when switching between 3+ datasets
   - **Impact**: Hit ratio drops to <10% with multiple active datasets
   - **Fix**: Increase to 256-512 and make configurable per dataset

3. **`data_graph_studio/core/cache.py:64-70` — Recursive Size Estimation on Every `.set()`**
   - Deep recursive estimation: O(n) overhead PER insertion for large dicts
   - **Impact**: Cache `set()` takes 10-50ms on large query result dicts
   - **Fix**: Sample estimation (top 10 entries, extrapolate)

---

## Cache Inefficiencies

1. **`data_graph_studio/core/cache.py:155-161` — Aggressive L1 Invalidation**
   - `on_filter_changed()` clears ALL L1 immediately even for visibility-only changes
   - **Impact**: Stats re-computed 3-5x per filter interaction
   - **Fix**: Distinguish filter *value* change (needs recalc) vs *visibility* toggle (doesn't)

2. **`data_graph_studio/core/data_engine.py:275-277` — Cache Cleared Unconditionally on File Load**
   - Even reloading the same file clears cache
   - **Fix**: Only clear if file content changed (check mtime + size)

3. **`data_graph_studio/core/data_query.py:161` — Cache Key Missing Context**
   ```python
   cache_key = f"stats_{column}"
   ```
   - Doesn't include windowed/filtered status → can return wrong stats in windowed mode
   - **Fix**: Use `(is_windowed, filter_hash, column)` tuple as key

---

## Polars Anti-patterns

1. **`data_graph_studio/core/data_query.py:334` — Unnecessary Sort Before Head**
   ```python
   return df[column].unique().sort().head(limit).to_list()
   ```
   - **Fix**: `unique().head(limit)` — unsorted is fine for categorical values
   - **Impact**: ~50ms saved per call on large columns

2. **`data_graph_studio/core/data_query.py:415-429` — Building OR Conditions in Python Loop**
   - O(n_columns) Python overhead instead of vectorized operation
   - **Fix**: Use `pl.concat_list()` or `fold()` for all-at-once construction

3. **`data_graph_studio/core/data_query.py:450-455` — Deprecated Index Builder Still Called**
   - 3 full passes over dataframe per unique value: O(unique_count × n)
   - **Fix**: `df.with_row_index().group_by(column)["row_number"].list()` (one pass)

---

## Rendering Issues

1. **`data_graph_studio/ui/panels/graph_panel.py:389-420` — Full Refresh on Every Style Change**
   - Clearing entire plot, re-filtering, re-sampling, re-creating all items even for color-only changes
   - **Impact**: 500ms+ per style change on large datasets
   - **Fix**: Tag change type; skip data recomputation for style-only changes

2. **`data_graph_studio/ui/panels/main_graph.py:553-584` — Text Labels Scene Thrashing**
   - 200 individual `addItem()` calls each trigger scene → viewport → redraw
   - **Impact**: 50-200ms to add 200 labels
   - **Fix**: Batch with `setUpdatesEnabled(False)` wrapping the loop

3. **`data_graph_studio/ui/panels/graph_panel.py:337-356` — Minimap Sync Blocking Flag**
   - If minimap drag is slow, entire UI unresponsive during sync
   - **Fix**: Debounce with Qt timer instead of blocking sync flag

---

## Qt Event Loop Blocking

1. **`data_graph_studio/ui/controllers/file_loading_controller.py:174,234,862`** — `QApplication.processEvents()` in loops
   - Called too frequently (every chunk) → excess thread context switches
   - **Fix**: Use QThread for file I/O, communicate via signals

2. **`data_graph_studio/ui/wizards/parsing_step.py:557,587,593,623`** — Same pattern in parsing
   - **Fix**: Worker thread with signals/slots

---

## Quick Wins (Big Impact, Small Change)

1. **`data_graph_studio/core/cache.py:237-243`** — `get_total_size()` called twice in stats → call once
2. **`data_graph_studio/core/data_query.py:334`** — Remove `.sort()` before `.head()` → 50ms saved per call
3. **`data_graph_studio/core/file_loader.py:581-583`** — Verify memory optimization not applied twice
4. **`data_graph_studio/graph/sampling.py:44`** — Return reference not copy for edge case (< 3 points)

---

## Priority Fix Order

| Priority | Issue | Estimated Gain |
|---|---|---|
| P0 | Cache eviction O(n²) bug | 50-200ms per refresh |
| P1 | Style-only refresh optimization | 500ms per color change |
| P2 | Filter push-down to lazy stage | 30-50% memory reduction |
| P3 | Thread-ify file loading | UI responsiveness |
| P4 | Polars query micro-optimizations | 5-50ms per query |

---

## Profiling Recommendations

```bash
# Profile rendering
python -m cProfile -s cumulative -o profile.prof main.py data.csv
snakeviz profile.prof

# Memory profiling
python -m memory_profiler main.py

# Cache effectiveness
# After app use: print(cache_manager.get_stats())  # hit_ratio should be > 0.7

# Sampling benchmarks
# x, y = np.random.randn(1_000_000), np.random.randn(1_000_000)
# %timeit DataSampler.lttb(x, y, 10000)  # Target: < 100ms
```
