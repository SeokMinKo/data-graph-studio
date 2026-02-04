# PRD: Compare Toolbar + Profile Settings in Side-by-Side View

**Version:** 1.0  
**Date:** 2025-07-10  
**Status:** Draft  
**Author:** DGS Dev Team  

---

## 1. Problem Statement

The current Compare Side-by-Side feature has three critical issues:

1. **Sync options are not toggleable**: The `ProfileSideBySideLayout` has sync checkboxes embedded in its header, but there's no way to toggle them from a dedicated, discoverable toolbar. Users expect toolbar-level controls.

2. **Profile graph settings are ignored**: When comparing profiles, `MiniGraphWidget._plot_data()` ignores `effective_chart_type`, `effective_group_columns`, `effective_hover_columns`, and renders only a simple line chart with the first value column. Profiles configured with scatter plots, grouped colors, or multiple value columns lose their visual identity.

3. **No dedicated Compare toolbar**: There is no centralized control surface for comparison-mode operations (grid layout switching, sync toggles, exit). Controls are scattered between inline checkboxes and context menus.

---

## 2. Goals

| # | Goal | Metric |
|---|------|--------|
| G1 | Provide a dedicated Compare Toolbar visible only during comparison mode | Toolbar auto-shows on compare start, auto-hides on compare end |
| G2 | Support grid layout options (Row, Column, 2×2) | User can switch layout via toolbar buttons |
| G3 | Sync toggles (X, Y, Zoom, Selection) accessible from toolbar | All 4 toggles are checkable buttons on toolbar |
| G4 | MiniGraphWidget respects all profile graph settings | chart_type, group_by, hover, all value_columns rendered |
| G5 | Toolbar integrable with View menu for show/hide | "Compare Toolbar" toggle action in View menu |
| G6 | No regression in existing dataset comparison (SideBySideLayout) | Existing dataset comparison still works |

---

## 3. Non-Goals

- Overlay/Difference mode toolbar (future scope)
- Custom color palette editor for compare mode
- Drag-and-drop reordering of panels in grid
- Toolbar docking customization (movable toolbar positions)

---

## 4. Detailed Design

### 4.1 Compare Toolbar (`ui/toolbars/compare_toolbar.py`)

A new `QToolBar` subclass:

```
[Row|Column|2×2]  |  [X Sync][Y Sync][Zoom Sync][Selection Sync]  |  [Exit Compare]
```

**Components:**
- **Grid Layout Button Group**: 3 exclusive `QToolButton`s (Row, Column, Grid) with `QButtonGroup`. Default: Row.
- **Sync Toggle Buttons**: 4 checkable `QPushButton`s. Default state: X=ON, Y=OFF, Zoom=OFF, Selection=ON.
- **Exit Compare Button**: Non-checkable `QPushButton` with red styling.

**Signals:**
- `grid_layout_changed(str)` — emits "row", "column", or "grid"
- `sync_changed(str, bool)` — emits ("x"|"y"|"zoom"|"selection", checked)
- `exit_requested()` — emits when exit button clicked

**Public API:**
- `set_sync_state(key: str, checked: bool)` — programmatic sync state update
- `set_grid_layout(layout: str)` — programmatic layout selection
- `sync_state() -> dict` — returns current sync toggle states

### 4.2 MiniGraphWidget Improvements (`ui/panels/side_by_side_layout.py`)

`_plot_data()` refactored to honor full `graph_setting`:

| Feature | Current | Target |
|---------|---------|--------|
| chart_type | Always line | line, scatter, bar |
| value_columns | First only | All value columns rendered |
| group_by | Ignored | Group-by with per-group color using `COLOR_PALETTE` |
| hover_columns | Ignored | Stored for future tooltip support |
| color per value_column | Dataset color only | Per-column color from value_column dict |

**Implementation:**
- Extract `_resolve_plot_params()` to compute chart type, columns, colors
- Loop over all effective value columns
- For scatter: use `ScatterPlotItem` instead of `plot()`
- For bar: use `BarGraphItem`
- For group_by: split dataframe by group column, plot each group with distinct color
- Sampling logic preserved (max 1000 points per series)

### 4.3 ProfileSideBySideLayout Improvements (`ui/panels/profile_side_by_side.py`)

**Changes:**
1. **Remove** internal sync checkbox bar (`syncOptionsFrame`), header "Reset All" button
2. **Add** grid layout support:
   - `set_grid_layout(layout: str)`:
     - `"row"` → `QSplitter(Qt.Horizontal)` (current default)
     - `"column"` → `QSplitter(Qt.Vertical)`
     - `"grid"` → `QGridLayout` in 2×2 arrangement
3. **Add** public methods for toolbar integration:
   - `set_sync_option(key: str, enabled: bool)` — delegates to `ViewSyncManager`
   - `get_sync_options() -> dict` — returns current sync states
4. **Keep** Esc shortcut and exit button in header

### 4.4 MainWindow Wiring (`ui/main_window.py`)

1. **Create** `CompareToolbar` instance in `__init__`, store as `self._compare_toolbar`
2. **Add** toolbar via `self.addToolBar(Qt.TopToolBarArea, self._compare_toolbar)`
3. **Initially hide** the toolbar: `self._compare_toolbar.hide()`
4. **View menu**: Add "Compare Toolbar" checkable action that toggles visibility
5. **On comparison started** (`_on_profile_comparison_started`):
   - Show toolbar
   - Connect `grid_layout_changed` → `ProfileSideBySideLayout.set_grid_layout`
   - Connect `sync_changed` → `ProfileSideBySideLayout.set_sync_option`
   - Connect `exit_requested` → `profile_comparison_controller.stop_comparison`
6. **On comparison ended** (`_on_profile_comparison_ended`):
   - Hide toolbar
   - Disconnect signals

### 4.5 ViewSyncManager Adaptation

Add `sync_zoom` property (currently the zoom sync is partially controlled by `sync_y`). The new behavior:
- `sync_x`: Synchronize X-axis panning
- `sync_y`: Synchronize Y-axis panning
- `sync_zoom`: Synchronize zoom level (both axes proportionally) — maps internally to triggering `set_view_range` with both ranges when zoom changes
- `sync_selection`: Synchronize data selection

For MVP, `sync_zoom` can alias to setting both `sync_x` and `sync_y` simultaneously. This avoids breaking the existing `ViewSyncManager` interface.

---

## 5. UI/UX Specifications

### 5.1 Toolbar Appearance
- Standard `QToolBar` with `setMovable(False)`
- Icon size: 16×16 (consistent with main toolbar)
- Grid buttons: text-only with highlight on active (`QToolButton` with `setCheckable(True)`)
- Sync buttons: text with check indicator (toggled appearance)
- Exit button: red background, white text (same style as current header exit button)

### 5.2 Grid Layout Behavior
- **Row** (default): Panels side-by-side horizontally (current behavior)
- **Column**: Panels stacked vertically
- **Grid (2×2)**: 2 columns × N rows layout via `QGridLayout`
  - 2 panels: 1×2 row
  - 3 panels: 2×2 with one empty cell
  - 4 panels: 2×2 full

### 5.3 Transition
- Layout change is live — panels reparented without data reload
- Sync state persists across layout changes

---

## 6. Data Flow

```
CompareToolbar
    ├── grid_layout_changed("row"|"column"|"grid")
    │       └── ProfileSideBySideLayout.set_grid_layout()
    │               └── Rearranges panels (QSplitter / QGridLayout)
    ├── sync_changed("x"|"y"|"zoom"|"selection", bool)
    │       └── ProfileSideBySideLayout.set_sync_option()
    │               └── ViewSyncManager.sync_x / sync_y / sync_selection
    └── exit_requested()
            └── ProfileComparisonController.stop_comparison()
                    └── MainWindow._on_profile_comparison_ended()
                            └── Hide toolbar, restore graph panel
```

---

## 7. Edge Cases

| Case | Handling |
|------|----------|
| Compare with 1 panel (after delete) | Auto-exit comparison |
| Grid layout with 3 panels | 2×2 with one cell empty |
| Profile has no value columns | Show empty plot with header only |
| Profile has >5 value columns | Render all (no artificial limit) |
| group_by column has >20 unique values | Render all, cycle color palette |
| Toolbar hidden via View menu, compare starts | Force-show toolbar |
| Compare mode changes (side-by-side → overlay) | Hide toolbar (toolbar is side-by-side only) |
| Mixed chart types across profiles | Each panel renders its own chart type |

---

## 8. Testing Strategy

### 8.1 Unit Tests
- **CompareToolbar signals**: Verify `grid_layout_changed`, `sync_changed`, `exit_requested` emit correctly
- **CompareToolbar state**: Verify `set_sync_state`, `set_grid_layout`, `sync_state` round-trip
- **MiniGraphWidget chart types**: Verify scatter, bar, line rendering paths
- **MiniGraphWidget multi-column**: Verify all value columns plotted
- **MiniGraphWidget group_by**: Verify group splitting and color assignment
- **Grid layout switching**: Verify panel reparenting without data loss

### 8.2 Integration Tests
- Compare 2 profiles → toolbar appears, exit → toolbar hides
- Change grid layout during comparison → panels rearrange
- Toggle sync during comparison → sync behavior changes

---

## 9. Migration & Backward Compatibility

- `ProfileSideBySideLayout` internal sync checkboxes removed — sync now controlled exclusively via toolbar
- `SideBySideLayout` (dataset comparison) is **not** modified — retains its own sync checkboxes
- `ViewSyncManager` API unchanged — new `sync_zoom` is additive
- No database/state schema changes

---

## 10. Implementation Plan

| Phase | Component | Effort |
|-------|-----------|--------|
| A | `CompareToolbar` (new file) | Small |
| B | `MiniGraphWidget._plot_data()` refactor | Medium |
| C | `ProfileSideBySideLayout` grid + toolbar integration | Medium |
| D | `MainWindow` wiring | Small |
| E | Tests | Small |

**Total estimated effort:** ~4 hours

---

## 11. Open Questions

None — all requirements are well-defined from user feedback and code analysis.
