# Stability Review: Data Graph Studio

## Summary

The codebase demonstrates solid foundational architecture with significant strengths in error handling, resource management, and thread safety. However, several latent stability risks have been identified:

- Silent failure risks in streaming/filtering operations (warning-level logging only)
- Potential race conditions between UI and worker threads during rapid state transitions
- Incomplete null safety in a few critical paths
- Resource cleanup gaps in edge cases
- Known technical debt in v0.16+ features

**Overall Risk Assessment: MEDIUM** — Suitable for production with documented known limitations; regression testing strongly recommended for comparison/filter features.

---

## Known Unfixed Bugs (from CHANGELOG/REVIEW_LOG/PRD)

| Issue | Location | Severity | Source | Status |
|-------|----------|----------|--------|--------|
| Y-axis 3+ columns handling undefined | graph_panel.py | HIGH | v0.16 REVIEW_LOG | ACKNOWLEDGED — fallback behavior intentionally undefined |
| Filter edge case: 0 rows → no "empty state" UI | Filter PR | MEDIUM | v0.16 REVIEW_LOG | FIXED in Round 2 — spec'd "No data matches filters" |
| Draw mode move — Esc behavior unclear | v0.16 | MEDIUM | v0.16 REVIEW_LOG | FIXED in Round 2 — Esc → original position + Undo |
| Heatmap 3-column selection UI unspecified | v0.16 | MEDIUM | v0.16 REVIEW_LOG | FIXED in Round 2 — explicit X/Y/Value mapping |
| Box Plot/Violin data mapping ambiguous | v0.16 | MEDIUM | v0.16 REVIEW_LOG | FIXED in Round 2 — spec'd as Group x Value scatter |
| Zone drag-to-drop removal undocumented | Data Tab PRD | LOW | PRD_data_tab_redesign | ACKNOWLEDGED — Ctrl+drag removed implicitly |

---

## Silent Failures (Error Swallowing)

### 1. ETL Parser Fallback — No User Notification (`data_graph_studio/core/file_loader.py:415`)
```python
logger.warning(f"etl-parser failed: {e}")
# Falls back to text parsing without user notification
```
**Impact**: User loads ETL file as unstructured text; data may be silently corrupted.
**Severity**: HIGH for ETL users.
**Fix**: Add toast: "ETL file conversion failed; loading as text. Data may be incomplete."

### 2. Parquet Conversion Failure — Silent Memory Impact (`data_graph_studio/core/file_loader.py:560`)
```python
logger.warning(f"Failed to convert to parquet: {e}")
# Continues with original large CSV — memory optimization bypassed
```
**Impact**: Large files consume peak memory without user awareness.
**Fix**: Toast for files >100MB: "Memory optimization failed; standard load active (may use more RAM)."

### 3. File Watcher Read Error — Stale Data (`data_graph_studio/core/file_watcher.py`)
```python
logger.warning(f"FileWatcher: cannot read {file_path} for row count: {e}")
# Continues with stale row count
```
**Impact**: User sees data as "unchanged" when file read failed; streaming chart doesn't update.

### 4. Dataset Removal Callback Errors (`data_graph_studio/core/dataset_manager.py:240`)
```python
logger.warning(f"dataset_removing callback error: {e}")
# Callback chain continues; potential state inconsistency
```
**Impact**: UI may not refresh properly if disconnect fails.

---

## Null Safety Issues

### 1. Engine State Access After Load (`data_graph_studio/ui/controllers/file_loading_controller.py:476-510`)
```python
w.state.set_data_loaded(True, w.engine.row_count)
# w.engine.df could be None if load failed with success=True signal
```
Pattern: Some accesses check `if df is not None`, others assume loaded state. Inconsistent guarding.

### 2. Profile Access Without State Check (`file_loading_controller.py:505-506`)
```python
if w.engine.profile:
    w._update_summary_from_profile()
```
Guard is present but profile can be None for non-CSV formats. Low risk — guard is correct.

---

## Race Conditions

### 1. Data Loader Thread Signal Leakage — MEDIUM probability
**Scenario**:
1. User starts loading file A → `_loader_thread` created
2. User cancels immediately, opens file B
3. Old thread's `finished_loading.emit(success)` arrives after new dataset is active
4. `_on_loading_finished` updates engine state for file A while file B is active

**File**: `data_graph_studio/ui/controllers/file_loading_controller.py:417-420`
**Mitigation**: `_cleanup_loader_thread()` calls `wait(2000)` but doesn't disconnect signals.
**Fix**: `w._loader_thread.finished_loading.disconnect()` in `_cleanup_loader_thread()` (10 min).

### 2. Streaming State Transition During File Update
**Scenario**: File updated while streaming is paused → FileWatcher emits signal → stale DataFrame accessed.
**Mitigation**: FileWatcher has internal guards; low practical risk.

### 3. Multi-File Load Progress Dialog Race
**Scenario**: Main window closed while modal progress dialog is active → background thread continues.
**Mitigation**: Qt modal prevents main window interaction; thread cleanup in destructor handles. Low risk.

---

## Unvalidated Inputs

### 1. Formula Parser — No Range Validation
**Issue**: `1/0`, `LOG(-1)`, deeply nested expressions without explicit validation.
**Fix**: Wrap evaluation in try-except; return None for invalid inputs; toast: "Formula error: {msg}"
**Effort**: 30 min

### 2. Custom Axis Format Strings
**Issue**: User-entered format like `##.##.##` applied directly to axis labels.
**Risk**: Low — worst case is incorrect label display, not code execution (Qt context, not eval).

### 3. File Paths With Special Characters
**Issue**: Paths with Unicode or UNC path syntax.
**Mitigation**: Polars/pathlib handle these; low risk in practice.

---

## Resource Leaks

### 1. QThread Orphan After Timeout (`file_loading_controller.py:394-397`)
```python
w._loader_thread.terminate()
w._loader_thread.wait(1000)
# If wait times out again: OS thread orphaned, reference set to None
```
**Risk**: Very low — rare timeout scenario on slow systems.
**Fix**: Track thread state separately; consider QThreadPool.

### 2. DataFrame Memory Management
**Pattern**: Large DataFrames stored in multiple places (engine.df, lazy_df, dataset cache).
**Mitigation**: `gc.collect()` called after loading; lazy evaluation for 100MB+ files; LRU cache with maxsize=128. Adequate.

### 3. File Watcher Timer
**Pattern**: If streaming controller destroyed mid-polling, timer continues briefly.
**Mitigation**: `FileWatcher.stop()` calls `self._timer.stop()` explicitly. Safe.

---

## Priority Fix List

### Critical (Before Next Release)

1. **ETL parse failure user feedback** — `file_loader.py:415` — Add toast notification (5 min)
2. **Large file memory warning** — `file_loader.py:560` — Add toast for >100MB failures (5 min)
3. **Thread signal leakage** — `file_loading_controller.py:417-420` — Disconnect signals in cleanup (10 min)

### High (Next Sprint)

4. **Y-axis 3+ columns warning** — `graph_panel.py` — Toast when 3rd column added (15 min)
5. **Filter empty state** — `graph_panel.py` — "No data matches filters" overlay (20 min)
6. **Formula parser error handling** — `expressions.py` — try-except + toast (30 min)

### Medium (Backlog)

7. **File watcher error recovery** — `file_watcher.py:82` — Retry with backoff (45 min)
8. **QThread orphan prevention** — `file_loading_controller.py:394-397` — QThreadPool migration (60 min)

---

## Conclusion

The codebase is production-ready with documented limitations. Most risks are logged, low-probability, and cause graceful degradation rather than crashes. Critical tier fixes are all <15 min each — high value, low effort. Schedule for next sprint.
