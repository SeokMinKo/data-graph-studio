# Review Log: Compare Toolbar + Profile Settings in Side-by-Side View

**PRD Version:** 1.0  
**Review Date:** 2025-07-10  
**Verdict:** ✅ **APPROVED** (8/8 AGREE)

---

## 🧠 Behavior Reviewer

**Verdict: AGREE ✅**

### Checklist
1. ✅ Toolbar auto-shows on compare start — covered in §4.4 step 5
2. ✅ Toolbar auto-hides on compare end — covered in §4.4 step 6
3. ✅ Grid layout default is "Row" (backward compatible) — §4.1
4. ✅ Sync defaults match current behavior (X=ON, Y=OFF, Selection=ON) — §4.1
5. ✅ Exit button on toolbar triggers `stop_comparison()` — §4.1 signals
6. ✅ Esc shortcut preserved in ProfileSideBySideLayout — §4.3
7. ✅ Profile deletion during compare auto-exits if <2 panels — §7 edge cases
8. ✅ Compare mode change (side-by-side → overlay) hides toolbar — §7
9. ✅ Each panel renders its own chart_type independently — §7
10. ✅ Sync state persists across grid layout changes — §5.3

**Comment:** Behavior is well-specified. The edge case table covers the important scenarios. The "force-show toolbar" when compare starts even if user had hidden it via View menu is the right UX choice.

---

## 🏗️ Structure Reviewer

**Verdict: AGREE ✅**

### Checklist
1. ✅ New file `ui/toolbars/compare_toolbar.py` — clean separation from existing toolbars
2. ✅ No modification to `SideBySideLayout` (dataset comparison) — isolation preserved
3. ✅ `ViewSyncManager` API unchanged — additive `sync_zoom` only
4. ✅ Signal-based communication (toolbar → layout → sync manager) — loose coupling
5. ✅ `MiniGraphWidget` changes scoped to `_plot_data()` — minimal blast radius
6. ✅ MainWindow wiring follows existing pattern (`_on_profile_comparison_started/ended`)
7. ✅ `__init__.py` for `ui/toolbars/` package needed — noted for implementation
8. ✅ No circular imports — toolbar has no dependency on core modules
9. ✅ Frozen `GraphSetting` dataclass not modified — read-only usage in MiniGraphWidget
10. ✅ Grid layout abstraction in ProfileSideBySideLayout — `set_grid_layout(str)` is clean API

**Comment:** The structure is clean. One suggestion: consider extracting the plot rendering logic from `MiniGraphWidget._plot_data()` into a helper module if it grows beyond ~100 lines. Not blocking.

---

## 🎨 UI Reviewer

**Verdict: AGREE ✅**

### Checklist
1. ✅ Toolbar uses standard QToolBar — native look and feel
2. ✅ Grid buttons are exclusive (QButtonGroup) — no ambiguous state
3. ✅ Sync buttons are checkable with toggle appearance — discoverable
4. ✅ Exit button has distinct red styling — visually clear "danger zone"
5. ✅ Icon size 16×16 matches main toolbar — visual consistency
6. ✅ Grid layout transitions are live (no reload) — smooth UX
7. ✅ 2×2 grid handles 3 panels gracefully (one empty cell) — §5.2
8. ✅ Toolbar position is `Qt.TopToolBarArea` — standard location
9. ✅ View menu toggle for toolbar — power user control
10. ✅ Per-column colors and per-group colors in MiniGraphWidget — visual differentiation

**Comment:** The toolbar design is standard and discoverable. The grid layout options (Row/Column/2×2) cover the common use cases well. Good that each profile retains its own chart type rendering.

---

## 🔍 Overall Reviewer

**Verdict: AGREE ✅**

### Checklist
1. ✅ All 3 original problems addressed (sync toggle, profile settings, toolbar)
2. ✅ Non-goals are reasonable and clearly scoped
3. ✅ Data flow diagram is clear and complete
4. ✅ Edge cases are comprehensive (7 cases documented)
5. ✅ Testing strategy covers unit + integration levels
6. ✅ Migration path is clean (no breaking changes to dataset comparison)
7. ✅ Effort estimate is realistic (~4 hours)
8. ✅ Implementation is phased (A→E) with clear dependencies
9. ✅ No open questions remaining
10. ✅ PRD is self-contained — no external dependencies or approvals needed

**Comment:** Well-structured PRD. The scope is tight and achievable. All three user complaints are directly addressed.

---

## ⚡ Algorithm Reviewer

**Verdict: AGREE ✅**

### Checklist
1. ✅ Group-by splitting uses standard pandas groupby — O(n) per render
2. ✅ Sampling preserved at 1000 points — prevents rendering lag
3. ✅ Color palette cycling for >20 groups is correct approach
4. ✅ ViewSyncManager throttle (50ms leading edge) unchanged — proven mechanism
5. ✅ Grid layout reparenting is O(k) where k ≤ 4 panels — trivial
6. ✅ No new data structures or complex algorithms needed
7. ✅ `sync_zoom` aliasing to sync_x + sync_y is correct MVP approach
8. ✅ Per-panel independent rendering avoids cross-panel data dependencies
9. ✅ WeakValueDictionary in ViewSyncManager prevents memory leaks — preserved
10. ✅ Signal-slot mechanism for toolbar events — Qt's native efficient dispatch

**Comment:** No algorithmic concerns. The 1000-point sampling per series is the right trade-off for mini graphs. Group-by rendering is straightforward.

---

## 🔧 Performance Reviewer

**Verdict: AGREE ✅**

### Checklist
1. ✅ Sampling at 1000 points per series prevents pyqtgraph slowdown
2. ✅ Grid layout switch reparents widgets — no data reload needed
3. ✅ ViewSyncManager 50ms throttle prevents cascade updates
4. ✅ MAX_PANELS = 4 caps the number of simultaneous renders
5. ✅ `_is_syncing` flag prevents infinite sync loops — preserved
6. ✅ No additional timers or polling introduced
7. ✅ Toolbar signals are on-demand (not polling) — zero idle cost
8. ✅ Group-by rendering: max groups rendered is bounded by data cardinality
9. ✅ ScatterPlotItem/BarGraphItem are standard pyqtgraph optimized items
10. ✅ No file I/O or network calls in the rendering path

**Comment:** Performance characteristics are maintained or improved. The multi-column rendering adds more draw calls per panel but is bounded by MAX_PANELS × num_value_columns, which is manageable.

---

## 🛡️ Security Reviewer

**Verdict: AGREE ✅**

### Checklist
1. ✅ No user input executed as code — all toolbar inputs are enum/bool values
2. ✅ No file system access in toolbar or rendering code
3. ✅ No network access introduced
4. ✅ GraphSetting is frozen dataclass — immutable, safe to share
5. ✅ No new IPC handlers exposed (existing ones preserved)
6. ✅ No serialization/deserialization of untrusted data in new code
7. ✅ Toolbar signals carry only simple types (str, bool) — no injection risk
8. ✅ pandas operations use column names from trusted GraphSetting — no SQL injection analog
9. ✅ pyqtgraph rendering is sandboxed to widget — no external side effects
10. ✅ No elevation of privileges or capability expansion

**Comment:** No security concerns. The new code is purely UI/rendering with no trust boundary crossings.

---

## 🧪 Testability Reviewer

**Verdict: AGREE ✅**

### Checklist
1. ✅ CompareToolbar is a standalone QToolBar — can be instantiated in isolation
2. ✅ All toolbar state changes emit signals — testable via `QSignalSpy` or manual connect
3. ✅ `set_sync_state`/`sync_state` provide round-trip testability
4. ✅ `set_grid_layout` is a simple string-based API — easy to parameterize tests
5. ✅ MiniGraphWidget can be tested with mock DataEngine and GraphSetting
6. ✅ Grid layout switching testable by checking `QSplitter.orientation()` or `QGridLayout` child count
7. ✅ ViewSyncManager existing test patterns can be reused
8. ✅ ProfileSideBySideLayout public API (`set_grid_layout`, `set_sync_option`) is test-friendly
9. ✅ No global state mutation — all state is instance-level
10. ✅ Existing `test_profile_comparison_controller.py` provides a test template

**Comment:** The design is highly testable. The signal-based architecture and clean public APIs make unit testing straightforward. Integration tests can use `QTest` for toolbar interaction.

---

## Summary

| Reviewer | Verdict |
|----------|---------|
| 🧠 Behavior | ✅ AGREE |
| 🏗️ Structure | ✅ AGREE |
| 🎨 UI | ✅ AGREE |
| 🔍 Overall | ✅ AGREE |
| ⚡ Algorithm | ✅ AGREE |
| 🔧 Performance | ✅ AGREE |
| 🛡️ Security | ✅ AGREE |
| 🧪 Testability | ✅ AGREE |

**Result: 8/8 AGREE — PRD APPROVED. Proceed to implementation.**
