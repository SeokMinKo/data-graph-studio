# UI Large File Split — Design Document

**Date:** 2026-02-23
**Goal:** Reduce oversized UI files to improve GOAT Coding Conventions score (6.5 → ~8.0)
**Approach:** Option B — theme.py + table_panel.py submodule extraction

---

## Motivation

Three files dominate the Coding Conventions violation list:

| File | Current | Target |
|------|---------|--------|
| `theme.py` | 2,259 lines | ~350 lines |
| `table_panel.py` | 2,803 lines | ~1,700 lines |
| `main_window.py` | 2,070 lines | unchanged (already well-split via controllers) |

The `main_window.py` is left out — it already uses 13 extracted controllers; remaining lines are mostly 3-line delegation stubs which are architectural best practice, not violations.

---

## Part 1: theme.py Split

### Problem

`generate_stylesheet()` is a single 1,733-line function that concatenates CSS strings for both light and dark themes. It is pure data — no logic, no conditionals on state — making it safe to extract.

### Design

```
data_graph_studio/ui/
  theme.py                      # ~350 lines — Theme class, ColorPalette, ThemeManager
  _theme_base_stylesheet.py     # ~300 lines — shared widget CSS (scrollbars, tooltips, etc.)
  _theme_light_stylesheet.py    # ~600 lines — light mode CSS
  _theme_dark_stylesheet.py     # ~600 lines — dark mode CSS
```

`generate_stylesheet(palette)` in `theme.py` becomes:
```python
def generate_stylesheet(palette: ColorPalette) -> str:
    from ._theme_base_stylesheet import base_stylesheet
    from ._theme_light_stylesheet import light_stylesheet
    from ._theme_dark_stylesheet import dark_stylesheet
    if palette.is_dark:
        return base_stylesheet(palette) + dark_stylesheet(palette)
    return base_stylesheet(palette) + light_stylesheet(palette)
```

**Public API:** unchanged. All callers of `generate_stylesheet()` continue to work.
**Risk:** Very low — CSS is pure data, no cross-file state.

---

## Part 2: table_panel.py Mixin Extraction

### Problem

`TablePanel` mixes 4 independent concerns in one file:
1. Search/filter logic
2. Focus row navigation
3. Windowed (paginated) loading
4. Column operations (type convert, freeze, visibility)

### Design

```
data_graph_studio/ui/panels/
  table_panel.py                 # ~1,700 lines — main class + DataTableView
  _table_search_mixin.py         # ~100 lines — search/filter methods
  _table_focus_mixin.py          # ~120 lines — focus navigation methods
  _table_window_mixin.py         # ~60 lines  — windowed loading methods
  _table_column_mixin.py         # ~90 lines  — column operation methods
```

`TablePanel` inherits all 4 mixins:
```python
class TablePanel(
    _TableSearchMixin,
    _TableFocusMixin,
    _TableWindowMixin,
    _TableColumnMixin,
    QWidget,
):
    ...
```

Each mixin file:
- Has `from __future__ import annotations` + TYPE_CHECKING guard for `TablePanel` type hints
- Contains only the methods for its concern
- Accesses `self.*` attributes defined in `TablePanel.__init__` (standard mixin pattern)

**Public API:** unchanged. Method names, signals, and `TablePanel` interface are identical.
**Risk:** Medium — mixin `self.*` access requires care; test suite validates behavior.

---

## Invariants

- All existing tests pass after each extraction
- `TablePanel` public interface (method names, signals, `__init__` signature) is unchanged
- `theme.generate_stylesheet()` returns byte-identical output before/after split
- No circular imports

---

## Implementation Order

1. theme.py split (lowest risk — start here)
2. table_panel search mixin (most isolated)
3. table_panel focus mixin
4. table_panel window mixin
5. table_panel column mixin

Each step: extract → run tests → commit.

---

## Expected Outcome

| Metric | Before | After |
|--------|--------|-------|
| theme.py lines | 2,259 | ~350 |
| table_panel.py lines | 2,803 | ~1,700 |
| Files >500 lines (UI) | 8 | 6 |
| GOAT Coding Conventions | 6.5 | ~8.0 |
| GOAT Overall | ~8.25 | ~8.5 |
