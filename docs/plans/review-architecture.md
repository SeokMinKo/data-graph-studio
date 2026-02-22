# Architecture Review: Data Graph Studio

## Summary

The Data Graph Studio codebase exhibits significant god object antipatterns, with three critical bottlenecks: **AppState** (1,640 lines, 121 methods, 27 signals) managing global application state without clear responsibility boundaries; **MainWindow** (2,023 lines, 249 methods) orchestrating 15+ controllers despite already extracting some concerns; and **TablePanel** (2,893 lines, 179 methods) handling table rendering, data operations, and multiple UI concerns simultaneously. High coupling between UI layers and core state, combined with 110+ Qt signals in AppState creating complex state synchronization chains, creates a brittle architecture where changes ripple unpredictably across the system.

---

## Critical Issues (must fix)

### 1. AppState as a God Object (`data_graph_studio/core/state.py:312-1640`)
- **Problem**: Single class manages 17 distinct concerns: multi-dataset tracking, comparison settings, selection state, filter/sort logic, profile lifecycle, undo/redo, theme, and layout ratios.
- **Signals**: 27 signals (lines 320-356) emit frequently with batching logic (lines 436-452), creating complex event chains that are hard to debug.
- **Methods**: 121 public methods performing mutations directly on internal state (`self._dataset_states`, `self._filters`, etc.) without encapsulation.
- **Impact**: Any change to AppState cascades to 50+ files importing it; signal handlers in MainWindow, GraphPanel, TablePanel all depend on precise signal ordering.
- **Example**: `add_dataset()` (lines 506-546) manages 10+ internal state mutations + 2 signal emissions.

### 2. MainWindow as Coordinator Hub (`data_graph_studio/ui/main_window.py:93-2023`)
- **Problem**: Despite extracting 15 controllers, MainWindow still has 249 methods and holds 30+ instance attributes (lines 120-200).
- 51 imports (most directly from core)
- `__init__` spans 123 lines initializing 25+ sub-components
- `_setup_main_layout()` spans 113 lines with deeply nested widget construction
- Direct encapsulation break: `self.engine._current_file_path = file_path` (line 1835)
- **Impact**: Any controller change requires MainWindow review; controllers tightly coupled to MainWindow's public interface.

### 3. Circular/Bidirectional Dependencies: Core ↔ UI
- `data_graph_studio/core/profile_comparison_controller.py` lines 47-48 imports from UI: `from ..ui.panels.profile_overlay import ProfileOverlayRenderer`
- AppState holds QObject signals, making it inherently UI-aware despite being in `core/`
- **Impact**: Core layer is contaminated with UI concerns; cannot test core logic without Qt imports.

---

## High Issues (should fix)

### 4. TablePanel Overloaded (`data_graph_studio/ui/panels/table_panel.py:1-2892`)
- 2,893 lines, 179 methods, 16 classes
- 142 signal connections creating tight coupling to AppState internals
- Handles: table rendering, drag/drop, conditional formatting, grouped data model, selection sync, filtering UI

### 5. GraphPanel Complex Signal Chains (`data_graph_studio/ui/panels/graph_panel.py:39-2381`)
- 57 methods managing graph rendering, sampling, filtering, windowing, minimap sync
- 18 signal connections (lines 180-208) create ordering dependencies
- Guard flag `_minimap_syncing` needed — indicates race condition workaround
- Dynamic signal connections in loops (lines 1134-1182) create memory leaks; no disconnection logic

### 6. State Mutation Without API Contracts
- AppState fields exposed as public/semi-public properties return mutable dicts/objects
- Callers can mutate returned objects directly: `state.active_dataset_state.filters.append(...)`
- No undo/redo tracking on indirect mutations

---

## Medium / Low Issues

### 7. Extracted Controllers Still Tightly Coupled to MainWindow
- Controllers accept `MainWindow` instance and access its public attributes directly
- Cannot reuse controllers in alternative UI frameworks

### 8. Mixed Data Transformation & Rendering Logic in GraphPanel
- Data sampling, filtering, aggregation, and UI rendering all in same class
- Hard to test rendering without actual data

---

## PRD-refactor-god-objects.md Implementation Status

### Completed ✓
- GraphOptionsPanel, StatPanel, MainGraph extracted as separate files
- 15 controllers extracted from MainWindow

### Still Pending ✗
- **Phase 1 (MainWindow)**: Controllers extracted but MainWindow still 2,023 lines (target was ~800)
  - Controllers are thin delegators, not actual responsibility owners
  - MainWindow still contains `_setup_main_layout()`, `_connect_signals()`, `keyPressEvent()` — all large methods
- **Phase 2 (GraphPanel completion)**: Still 2,381 lines, sub-components not independently usable
- **Tests**: No new unit tests added for extracted controllers

---

## Import/Coupling Analysis

| File | Lines | Classes | Methods | Imports | Signals | Coupling |
|------|-------|---------|---------|---------|---------|----------|
| `core/state.py` | 1,640 | 17 | 121 | 9 | 27 | **CRITICAL** |
| `ui/main_window.py` | 2,023 | 3 | 249 | 51 | 0 | **CRITICAL** |
| `ui/panels/table_panel.py` | 2,893 | 16 | 179 | 11 | 142 | **HIGH** |
| `ui/panels/graph_panel.py` | 2,381 | 1 | 57 | 20 | 18 | **HIGH** |

**Notable circular dependencies:**
1. AppState (core) ← imports → 50+ UI files (asymmetric, acceptable)
2. `core/profile_comparison_controller.py` → `ui/panels/profile_overlay.py` — **latent cycle**

---

## Recommended Refactoring Order

### Phase 1: Break AppState God Object (2-3 weeks) — Highest ROI
1. **Extract ComparisonManager** (lines 416-663) → `core/comparison_manager.py`
2. **Extract SelectionManager** (selection-related methods) → `core/selection_manager.py`
3. **Extract ChartStateManager** (column/filter/sort/chart state) → `core/chart_state_manager.py`
4. Reduce AppState to 400-500 lines

### Phase 2: Untangle MainWindow (2 weeks)
1. Extract `LayoutManager` → `_setup_main_layout()` + panel management
2. Extract `ControllerFactory` → consolidate controller initialization
3. Extract `KeyPressHandler` → 67-line `keyPressEvent()`
4. Make controllers take explicit dependencies (not MainWindow)

### Phase 3: Decompose TablePanel (2 weeks)
1. Extract `TableModel` hierarchy → separate file
2. Extract `SelectionSyncManager`
3. Extract `ConditionalFormattingEngine`
4. Target: ~1,500 lines

### Phase 4: Simplify GraphPanel (1 week)
1. Extract `SamplingPipeline` → data transformation separate from rendering
2. Reduce signal connections via explicit handler pattern
3. Target: ~1,500 lines

---

## Conclusion

The PRD-refactor plan is sound but incompletely executed — controllers were extracted but MainWindow grew to absorb their wiring logic instead. AppState remains a monolith despite being the system's core dependency.

**Immediate priorities:**
1. Complete Phase 2 of PRD (reduce GraphPanel to <1,500 lines with truly independent sub-components)
2. Extract ComparisonManager + SelectionManager (smaller wins, unblock other work)
3. Add coupling metrics to CI/CD (fail builds if files exceed 1,500 lines or import counts exceed 25)

The architecture can be salvaged with 4-6 weeks of focused refactoring, but without structural changes, maintenance velocity will continue declining.
