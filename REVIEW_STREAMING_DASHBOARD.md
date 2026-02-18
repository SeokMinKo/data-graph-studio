# Code Review: Streaming + Dashboard (commit 9522bea)

**Date**: 2026-02-19  
**Reviewer**: Claude (automated)  
**Scope**: 9 files, +627 / -284 lines

---

## Summary

Good commit that fixes several real bugs (self→self.w, speed cumulative error, CSS accumulation) and adds meaningful features (seek-based tail, sliding window, drag-and-drop, stats overlay). However, there are several issues worth addressing.

---

## Issues

### P0 — Must Fix

#### 1. `append_rows()` reads entire file, defeating its purpose
**File**: `data_engine.py:286-297`  
```python
full_df = pl.read_csv(file_path)  # reads ENTIRE file
new_rows = full_df.tail(new_row_count)
```
The method is called "incremental append" but reads the full CSV every time. For a 10M-row streaming file, this negates the seek-based optimization in `file_watcher.py`.

**Fix**: Use `pl.read_csv()` with `skip_rows` or parse only the new bytes (passed from the watcher). Alternatively, pass the raw new lines from the seek-based read directly.

#### 2. Sliding window applied to display but not to engine DataFrame — memory leak
**File**: `streaming_ui_controller.py:207-209`
```python
df = self.w.engine.df
if df is not None and self._streaming_window_size is not None:
    df = df.tail(self._streaming_window_size)
```
The engine DataFrame grows unbounded. Only the *display* is windowed. For long-running streams, memory will grow indefinitely.

**Fix**: Also truncate the engine's DataFrame: `self.w.engine.update_dataframe(df)` after windowing. Or add `engine.trim(max_rows)`.

#### 3. `_activate_dashboard_mode` indentation error
**File**: `view_actions_controller.py:402`
```python
            QMessageBox.warning(
            self.w, "Dashboard Mode",   # ← wrong indentation (not inside parens properly)
                "Cannot activate..."
```
This may work syntactically but is misleading. Same issue at line 579 (`QInputDialog.getText`).

**Fix**: Align arguments properly inside the parentheses.

---

### P1 — Should Fix

#### 4. `_on_dashboard_grid_size_changed` discards existing cell assignments
**File**: `view_actions_controller.py:497-501`
```python
ctrl.create_layout(before.name if before else "Dashboard", rows, cols)
```
`create_layout` creates a brand-new empty layout, losing all existing cell profile assignments.

**Fix**: Use `ctrl.resize_layout(rows, cols)` or migrate cells after creating new layout.

#### 5. `_on_dashboard_name_changed` mutates layout directly — no undo, no persistence
**File**: `view_actions_controller.py:505-507`
```python
layout.name = new_name  # direct mutation, no undo push, no save
```

**Fix**: Use controller method with undo support similar to `unassign_profile`.

#### 6. `_on_dashboard_cell_swap` doesn't push undo
**File**: `view_actions_controller.py:479-492`  
Swap modifies layout but doesn't record undo state, inconsistent with unassign which does.

**Fix**: Add `_push_undo` before the swap.

#### 7. Seek-based tail doesn't handle partial lines
**File**: `file_watcher.py:378-389`
```python
f.seek(entry.last_size)
new_data = f.read()
new_lines = new_data.decode("utf-8", errors="replace").splitlines()
```
If the writer is mid-line when we read, we'll count an incomplete line as a full row. Next read will also include the remainder, causing a duplicate partial row.

**Fix**: Check if `new_data` starts mid-line (doesn't start at a newline boundary after seek). Drop the first partial line and adjust `entry.last_size` to the end of the last complete line.

#### 8. `_find_dashboard_panel` has dead code path
**File**: `dashboard_panel.py:75-82`
```python
if w is None:           # w is always None here after while loop
    w = self.parent()   # re-starts from parent
```
The second loop after `w is None` resets `w` to `self.parent()` but then looks for `_DashboardTab` which wouldn't contain `DashboardPanel` reference in current code structure.

**Fix**: Simplify — just walk parents once looking for either type.

#### 9. Stats overlay QTimer not parented — potential leak
**File**: `streaming_ui_controller.py:249`
```python
self._stats_timer = QTimer()  # no parent
```

**Fix**: `QTimer(self.w)` to ensure cleanup on window destruction.

#### 10. `follow_tail` attribute access without check
**File**: `streaming_ui_controller.py:217`
```python
if self.w._streaming_controller.follow_tail:
```
`follow_tail` is not defined in the `StreamingController` diff. If it doesn't exist, this raises `AttributeError`.

**Fix**: Use `getattr(self.w._streaming_controller, 'follow_tail', False)`.

---

### P2 — Nice to Have

#### 11. Speed change: `max(500, ...)` is arbitrary magic number
**File**: `streaming_ui_controller.py:60`  
Should be a named constant (e.g., `MIN_POLL_INTERVAL_MS = 500`).

#### 12. Window size parsing is fragile
**File**: `streaming_ui_controller.py:68-74`  
`"1.5k"` → `int("1.5000")` → ValueError. Only integer `k` values work.

**Fix**: Parse float first, then multiply: `int(float(text.replace("k","")) * 1000)`.

#### 13. `DashboardItemWidget` removed from `dashboard.py` but may be referenced elsewhere
The legacy `DashboardItemWidget` class was deleted. Ensure no imports reference it.

#### 14. No tests for new features
No test files were added/modified in this commit. The new features (append_rows, sliding window, drag-drop, grid resize, cell swap, stats overlay) have zero test coverage.

**Fix**: Add unit tests, especially for `append_rows`, seek-based tail partial line handling, and cell swap logic.

---

## Positive Highlights

- ✅ `self` → `self.w` fixes prevent runtime crashes across 15+ call sites
- ✅ Speed calculation now uses base interval — eliminates cumulative drift
- ✅ `set_focus_cell` CSS fix (property-based) prevents style string explosion
- ✅ Undo for `unassign_profile` maintains consistency
- ✅ Seek-based tail is a good performance optimization direction
- ✅ Stats overlay provides useful real-time feedback
- ✅ `dashboard.py` cleanup (legacy re-export) is well-structured

---

## Test Results

⚠️ Tests could not be executed — `pytest` hangs (likely Qt event loop blocking without `QApplication` fixture or `--forked` mode).

**Recommendation**: Fix test infrastructure to run headlessly (`QT_QPA_PLATFORM=offscreen` or pytest-qt fixture).
