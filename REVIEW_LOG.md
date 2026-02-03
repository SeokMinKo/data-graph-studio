# PRD Review Log: Zone을 Chart Options로 이전 + UI 개선

**Date**: 2025-07-14  
**PRD Version**: 1.0  
**Reviewers**: 6 strict reviewers  
**Passing Criteria**: 4/6 AGREE

---

## 1. 🧠 Behavior Reviewer

**Status**: ❌ **REJECT**

### Issues

1. **FR-4 Group By: Single ComboBox cannot replicate current multi-group capability**  
   - Current `GroupZone` (`table_panel.py` line 401–473) supports **multiple** group columns with drag-reorder (`allow_reorder=True`). The PRD specifies a single `QComboBox` with `(None)` option for Group By.  
   - The existing `state.py` (`add_group_column`, line 527) allows multiple group columns; `reorder_group_columns` (line 539) supports re-ordering. A single combo box reduces this to exactly one group column—this is a **functional regression**.  
   - **Fix**: Either use a multi-select combo or a checkbox list (like Y-Axis) to maintain multi-group. Or explicitly document this as a scope reduction and update `state.group_columns` API accordingly.

2. **FR-3 Y-Axis Formula input missing from Data tab spec**  
   - Current `ValueChipWidget` (`table_panel.py` lines 252–296) has an inline formula `QLineEdit` per value column (`formula_edit` at line 279). The PRD Data tab layout shows only `☑ col1 [SUM ▼]` — no formula field.  
   - Section 5 mentions "Formula 입력 (인라인, 접어두기 가능)" but the mockup doesn't show it, and Section 6 `DataTab` class spec has no formula-related method.  
   - **Fix**: Add formula field to mockup and `DataTab` spec. Define the collapsible behavior.

3. **FR-8 Table header right-click → Data tab reflection is underspecified**  
   - PRD says "기능 유지" for context menu items like "Add to Y-Axis", "Set as X", etc. Currently these call `_on_column_action` (`table_panel.py` line 1757) which directly mutates `state`. This still works, but the PRD doesn't specify whether the Data tab should **visually scroll to** or **highlight** the newly-added item after a right-click action. Without this, users won't get feedback that their action worked (since the Data tab may be on a different GraphOptionsPanel tab).  
   - **Fix**: Specify that after a table header action, the Data tab auto-switches or flashes a confirmation.

4. **Edge case: Switching between no data and data loaded**  
   - `DataTab.set_columns()` is defined, but there's no spec for what happens when data is cleared or a new dataset is loaded. Should the Data tab clear all checkboxes? Should previously-checked columns persist if column names match?  
   - **Fix**: Define behavior for dataset switching and data clearing explicitly.

5. **Edge case: Column name collision with "(Index)" and "(None)"**  
   - If actual data has a column literally named "(Index)" or "(None)", the combo boxes will be ambiguous.  
   - **Fix**: Use a sentinel value internally (e.g., `None` in Python) rather than relying on display text for logic.

6. **Missing: Drag & drop removal from spec**  
   - The PRD says "드래그 앤 드롭 지원 (제외)" but the current `DataTableView.eventFilter` (`table_panel.py` line 632) supports Ctrl+drag from table headers to zones. If zones are removed, this Ctrl+drag breaks silently. The PRD doesn't address this removal.  
   - **Fix**: Explicitly state that Ctrl+drag from table headers is removed or repurposed.

---

## 2. 🏗️ Structure Reviewer

**Status**: ✅ **AGREE** (with recommendations)

### Confirmations
- Moving zone logic from `TablePanel` to a `DataTab` widget inside `GraphOptionsPanel` is architecturally sound. It reduces coupling between `TablePanel` and `AppState` zone signals.
- The `DataTab` class spec correctly takes `AppState` as dependency and exposes `set_columns()` — clean interface.
- State interface (`state.py`) remains unchanged (FR-10), which minimizes risk.

### Recommendations (non-blocking)

1. **File placement for `DataTab`**  
   - PRD doesn't specify where `DataTab` lives. Recommend `data_graph_studio/ui/panels/data_tab.py` as a new file rather than embedding it inside `graph_panel.py` (which is already 3708 lines).

2. **Dead code in `table_panel.py`**  
   - The PRD says "Zone 관련 기존 클래스 파일 삭제 (사용하지 않지만 코드는 유지)". This means `XAxisZone`, `GroupZone`, `ValueZone`, `HoverZone`, `ChipWidget`, `ValueChipWidget`, `ChipListWidget`, `DragHandleLabel`, and all helper functions (`_parse_drag_payload`, `_build_drag_payload`, `_remove_from_source`) — roughly **450+ lines** — stay as dead code. This is acceptable for now but should be flagged for cleanup.

3. **`GraphOptionsPanel` tab index management**  
   - Currently `GraphOptionsPanel._setup_ui()` (`graph_panel.py` line 64) creates 4 tabs: Chart, Legend, Axes, Style. Adding "Data" as the first tab (FR-1) means all existing tab indices shift by +1. Any code referencing `self.tabs.setCurrentIndex(0)` etc. will break.  
   - **Recommendation**: Use named tab references, not indices.

4. **Signal wiring migration**  
   - `TablePanel._connect_signals()` (line 1560) connects `state.group_zone_changed`, `state.value_zone_changed`, `state.hover_zone_changed`. After zones move to `DataTab`, these connections in `TablePanel` should be reviewed — some (`_on_group_zone_changed` triggering table model refresh) are still needed.

---

## 3. 🎨 UI Reviewer

**Status**: ❌ **REJECT**

### Issues

1. **NFR-1 Panel width (200–280px) is too narrow for Y-Axis checkbox + aggregation combo + formula**  
   - Current `ValueChipWidget` (`table_panel.py` line 252) uses a 180px zone width and already has "깨짐" issues per the PRD's own problem statement. The Data tab at 200–280px must fit: checkbox (20px) + column name (~80px) + aggregation combo (70px) + formula input (?). That's ~170px minimum, leaving only 30–110px margin. With scrollbar (17px), it's even tighter.  
   - The PRD mockup shows `☑ Temperature  [SUM ▼]` on one line — that's ~200px minimum width. Adding formula (even collapsible) will break layout on the narrower end.  
   - **Fix**: Either increase minimum width to 260px or use a two-row layout per Y-axis item (name+checkbox on row 1, agg+formula on row 2).

2. **Hover Columns layout is vague**  
   - Mockup shows `☑ col1  ☑ col2` in a horizontal flow layout. But `QCheckBox` widgets in a `QVBoxLayout` are vertical by default. Using `QGridLayout` or `QFlowLayout` for hover items isn't specified. With 20+ columns, a simple horizontal layout won't fit.  
   - **Fix**: Specify grid layout (2 columns) or scrollable vertical checkbox list for Hover.

3. **No keyboard accessibility mentioned**  
   - Current zones support drag-and-drop which, while not keyboard-friendly, at least has the right-click menu as an alternative. The new combo boxes and checkboxes are inherently more keyboard-accessible, which is good. However, there's no spec for:
     - Tab order between sections (X → Y → Group → Hover)
     - Keyboard shortcut for "Select All" in Y-Axis/Hover  
   - **Recommendation**: Add tab order spec and keyboard shortcuts for [+All] buttons.

4. **[+All] button behavior undefined**  
   - The mockup shows `[+All]` next to "Y-Axis (Values)" and "Hover Columns". Does this:
     - Check all items? Or toggle all?
     - For Y-Axis, does "+All" add all numeric columns? What about non-numeric?
   - **Fix**: Define +All behavior explicitly.

5. **Separator style not specified**  
   - The mockup uses `───────────────` between sections. Is this a `QFrame` with `HLine` shape? What's the color/thickness in dark vs light theme?  
   - **Minor fix**: Specify separator widget type and theme colors.

6. **Data tab scroll behavior**  
   - With 200 columns, the Y-Axis checkbox list could be 4000px tall. Is the entire Data tab in a `QScrollArea`? Or just the Y-Axis section? The mockup doesn't show scroll indicators.  
   - **Fix**: Specify scroll areas. Recommend per-section scroll with max heights.

---

## 4. 🔍 Overall Reviewer

**Status**: ✅ **AGREE** (with notes)

### Confirmations
- Clear problem statement and motivation (zones eating 640px of table width).
- Scope is well-defined (inclusion/exclusion lists are explicit).
- State interface stability (FR-10) reduces integration risk.
- Test scenarios (UT-1 through PT-2) cover the critical paths.
- Success criteria are measurable.

### Notes (non-blocking)

1. **Missing migration/rollback plan**  
   - No mention of feature flag or gradual rollout. If the new Data tab has issues, there's no way to revert to zones without code changes. Consider a feature toggle.

2. **Missing: Profile save/load compatibility**  
   - Section 9 mentions "프로파일 저장/로드 정상 동작" as a success criterion, but the PRD doesn't specify how `apply_graph_setting` (`state.py` line 732) interacts with the new Data tab. The current `_sync_from_state` method mentioned in Section 6 needs to handle profile application correctly.  
   - **Recommendation**: Add an integration test for profile load → Data tab sync.

3. **Missing: Wizard integration**  
   - `NewProjectWizard` currently may set initial X/Y columns. PRD doesn't mention wizard → Data tab flow.  
   - **Low risk**: Wizard presumably mutates `state`, which will trigger `_sync_from_state`.

4. **Test gap: No test for 100+ column performance (NFR-2)**  
   - PT-1 tests 200 columns < 100ms, but there's no UT for the rendering path specifically. UT-2 tests `set_columns()` but doesn't measure timing.

5. **Section 10 "미해결 질문 - 없음" is overconfident**  
   - Given the issues raised by other reviewers (multi-group regression, formula UI, +All behavior), there are clearly open questions.

---

## 5. ⚡ Algorithm Reviewer

**Status**: ✅ **AGREE**

### Confirmations
- Data flow is straightforward: `engine.columns` → `DataTab.set_columns()` → populate combo boxes and checkbox lists. No complex algorithm needed.
- Aggregation combo per Y-axis item is O(1) lookup in `AggregationType` enum.
- `_sync_from_state` is a simple state-to-UI mapping — no algorithmic concern.

### Notes

1. **Column filtering (numeric vs non-numeric) for Y-Axis**  
   - PRD says "숫자형 컬럼만 Y-Axis에 표시". This requires `DataTab.set_columns(columns, numeric_columns)` with two lists. The filtering is O(n) where n = number of columns — trivial.  
   - **However**: Determining numeric columns requires `engine.df.dtypes` inspection. If the engine exposes this (it does via `engine.columns` and `engine.df`), this is fine. But the PRD should clarify who is responsible for computing `numeric_columns` — the caller of `set_columns()` or the `DataTab` itself.

2. **Checkbox state management for Y-Axis**  
   - With 200 columns and checkboxes, toggling one checkbox triggers `state.add_value_column()` → `value_zone_changed` signal → graph refresh. This is O(1) for state mutation, but graph refresh cost depends on the graph renderer.  
   - PRD correctly specifies `blockSignals` usage to prevent cascade (Section 7). Good.

3. **Data tab sync complexity**  
   - `_sync_from_state` must iterate all columns to set checkbox states. With 200 columns, this is O(n) but with Qt widget operations (setChecked), each one triggers layout recalculation unless batched.  
   - **Recommendation**: Use `setUpdatesEnabled(False)` during bulk sync, then re-enable.

---

## 6. 🔧 Performance & Memory Reviewer

**Status**: ✅ **AGREE** (with warnings)

### Confirmations
- Memory target < 1MB for the Data tab widget is reasonable. 200 `QCheckBox` widgets ≈ ~400KB including Qt overhead.
- Performance target (< 100ms for 200 columns) is achievable with standard Qt widgets.
- `blockSignals` requirement prevents signal storms during bulk operations.

### Warnings (non-blocking)

1. **Widget creation/destruction on dataset switch**  
   - When `set_columns()` is called with a new column list, existing checkbox widgets must be destroyed and recreated. With 200 columns:
     - Destruction: 200 `QCheckBox` + 200 optional `QComboBox` = 400 widget deletions
     - Creation: 400 new widgets
   - This should be < 100ms per the PRD target, but **only if done correctly**:
     - Use `QWidget.deleteLater()` instead of immediate deletion (avoid double-free with signal connections)
     - Consider widget pooling or `setVisible(False)` for reuse instead of recreation  
   - **Risk**: If `set_columns()` is called frequently (e.g., rapid dataset switching), GC pressure could cause frame drops.

2. **No explicit cleanup in `DataTab` destructor**  
   - The PRD's `DataTab` class spec doesn't mention cleanup. If `DataTab` connects to `state` signals in `__init__`, those connections must be disconnected when `DataTab` is destroyed, or the `state` object will hold references preventing GC.  
   - **Fix**: Add `def cleanup(self)` or override `closeEvent` to disconnect signals.

3. **Memory leak risk from checkbox signal connections**  
   - Each Y-axis checkbox will have a `stateChanged` connection. When `set_columns()` recreates checkboxes, old connections must be cleaned. Using `deleteLater()` on the parent widget should handle this, but lambda closures capturing `column_name` strings could delay GC if references are held.  
   - **Mitigation**: Use `functools.partial` instead of lambdas, or explicitly disconnect before deletion.

4. **Splitter resize reflow**  
   - Removing 4 zone widgets from `TablePanel.splitter` changes the splitter from 3 segments (left_panel | table | right_panel, sizes [280, 500, 360] at `table_panel.py` line 1555) to just the table. The current `splitter.setSizes()` and `setStretchFactor()` calls must be completely rewritten. If left unchanged, the splitter will allocate space for ghost segments.  
   - **Fix**: PRD should specify the simplified splitter setup (single widget, no splitter needed).

5. **200-column checkbox scroll performance**  
   - A `QScrollArea` with 200+ checkboxes should use lazy loading or a virtual list for smooth scrolling. Standard `QVBoxLayout` with 200 `QCheckBox` widgets will work but may stutter on first render.  
   - **Acceptable**: For 200 columns, standard layout is fine. For 500+, virtual scrolling would be needed.

---

## Summary

| # | Reviewer | Status | Critical Issues |
|---|----------|--------|----------------|
| 1 | 🧠 Behavior | ❌ REJECT | Multi-group regression, formula UI missing, edge cases |
| 2 | 🏗️ Structure | ✅ AGREE | File placement and tab index recommendations |
| 3 | 🎨 UI | ❌ REJECT | Width too narrow, scroll/layout unspecified, +All undefined |
| 4 | 🔍 Overall | ✅ AGREE | Migration plan and wizard integration notes |
| 5 | ⚡ Algorithm | ✅ AGREE | numeric_columns responsibility needs clarification |
| 6 | 🔧 Performance | ✅ AGREE | Widget cleanup and signal disconnection warnings |

**Result: 4/6 AGREE → ✅ PASS** (barely)

### Required Fixes Before Implementation

The following MUST be addressed before development starts:

1. **🔴 CRITICAL**: Group By must support multiple columns (not single ComboBox) — this is a functional regression that breaks existing workflows.
2. **🔴 CRITICAL**: Y-Axis formula input must be included in the Data tab spec and mockup.
3. **🟡 HIGH**: Define [+All] button behavior for Y-Axis and Hover.
4. **🟡 HIGH**: Specify scroll area strategy for the Data tab (per-section vs. whole tab).
5. **🟡 HIGH**: Minimum panel width should be 260px, not 200px, to fit Y-axis row content.
6. **🟠 MEDIUM**: Define behavior for dataset switch / data clear in Data tab.
7. **🟠 MEDIUM**: Address Ctrl+drag removal from table headers.
8. **🟠 MEDIUM**: Specify DataTab cleanup/signal disconnection strategy.
