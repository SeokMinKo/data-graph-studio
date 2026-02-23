# UI Large File Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split theme.py (2,259 lines) and table_panel.py (2,803 lines) into smaller focused modules to improve GOAT Coding Conventions score.

**Architecture:** theme.py gets its 1,733-line stylesheet function split into 3 pure-data modules (base/light/dark CSS). table_panel.py gets 4 independent behavior groups extracted as mixins (search, focus, window, column ops). Public APIs are unchanged throughout.

**Tech Stack:** PySide6, Python mixins, pytest

---

## Pre-flight

Before starting, verify baseline:

```bash
cd /Users/lov2fn/Projects/data-graph-studio
source .venv/bin/activate
pytest tests/unit/ -q 2>&1 | tail -3
```

Expected: `1099 passed`

---

## Part 1: theme.py Split

### Task 1: Behavior-preservation test for generate_stylesheet

**Files:**
- Create: `tests/unit/test_theme_stylesheet_preservation.py`

**Step 1: Read theme.py to understand the API**

```bash
head -60 data_graph_studio/ui/theme.py
grep -n "def generate_stylesheet\|class.*Palette\|is_dark" data_graph_studio/ui/theme.py | head -20
```

**Step 2: Write the failing test**

```python
# tests/unit/test_theme_stylesheet_preservation.py
"""Regression: generate_stylesheet output must be byte-identical before/after refactor."""
import pytest
from unittest.mock import MagicMock


def _make_palette(is_dark: bool):
    """Build the minimal palette object generate_stylesheet() expects."""
    from data_graph_studio.ui.theme import ColorPalette
    return ColorPalette(is_dark=is_dark)


def test_light_stylesheet_is_nonempty():
    from data_graph_studio.ui.theme import generate_stylesheet
    palette = _make_palette(is_dark=False)
    css = generate_stylesheet(palette)
    assert isinstance(css, str)
    assert len(css) > 1000, "Light stylesheet suspiciously short"
    assert "QWidget" in css or "QMainWindow" in css


def test_dark_stylesheet_is_nonempty():
    from data_graph_studio.ui.theme import generate_stylesheet
    palette = _make_palette(is_dark=True)
    css = generate_stylesheet(palette)
    assert isinstance(css, str)
    assert len(css) > 1000, "Dark stylesheet suspiciously short"


def test_light_and_dark_are_different():
    from data_graph_studio.ui.theme import generate_stylesheet
    light = generate_stylesheet(_make_palette(False))
    dark = generate_stylesheet(_make_palette(True))
    assert light != dark
```

**Step 3: Run test to verify it passes against current code**

```bash
pytest tests/unit/test_theme_stylesheet_preservation.py -v
```

Expected: all 3 PASS (these are behavior tests, not regressions yet — they document what we must preserve)

**Step 4: Commit**

```bash
git add tests/unit/test_theme_stylesheet_preservation.py
git commit -m "test: add stylesheet preservation tests before theme.py split"
```

---

### Task 2: Extract base stylesheet

**Files:**
- Create: `data_graph_studio/ui/_theme_base_stylesheet.py`
- Modify: `data_graph_studio/ui/theme.py`

**Step 1: Read generate_stylesheet to identify base CSS sections**

```bash
grep -n "def generate_stylesheet" data_graph_studio/ui/theme.py
wc -l data_graph_studio/ui/theme.py
```

Then read the full generate_stylesheet body and identify which CSS sections are shared by both light and dark themes (scrollbars, tooltips, common widget styles, etc.).

**Step 2: Create `_theme_base_stylesheet.py`**

```python
# data_graph_studio/ui/_theme_base_stylesheet.py
"""Base (shared) stylesheet fragments — applies to both light and dark themes."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .theme import ColorPalette


def base_stylesheet(palette: "ColorPalette") -> str:
    """Return CSS that applies to both light and dark themes.

    Returns:
        CSS string for shared widget styles.
    """
    return f"""
    /* [paste the shared CSS sections here] */
    """
```

**Step 3: Update generate_stylesheet in theme.py to use base_stylesheet**

In `theme.py`, find `generate_stylesheet` and replace the shared sections with:

```python
def generate_stylesheet(palette: ColorPalette) -> str:
    from ._theme_base_stylesheet import base_stylesheet
    # ... (keep the mode-specific CSS inline for now, will extract in Tasks 3 & 4)
    return base_stylesheet(palette) + "... remaining CSS ..."
```

**Step 4: Run preservation tests**

```bash
pytest tests/unit/test_theme_stylesheet_preservation.py -v
```

Expected: all PASS (output must still be identical)

**Step 5: Run full suite**

```bash
pytest tests/unit/ -q 2>&1 | tail -3
```

Expected: 1100 passed (or same count, no failures)

**Step 6: Commit**

```bash
git add data_graph_studio/ui/_theme_base_stylesheet.py data_graph_studio/ui/theme.py
git commit -m "refactor: extract base_stylesheet from theme.py"
```

---

### Task 3: Extract light stylesheet

**Files:**
- Create: `data_graph_studio/ui/_theme_light_stylesheet.py`
- Modify: `data_graph_studio/ui/theme.py`

**Step 1: Create `_theme_light_stylesheet.py`**

```python
# data_graph_studio/ui/_theme_light_stylesheet.py
"""Light mode stylesheet — extracted from theme.generate_stylesheet."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .theme import ColorPalette


def light_stylesheet(palette: "ColorPalette") -> str:
    """Return light mode CSS.

    Returns:
        Light theme CSS string.
    """
    return f"""
    /* [paste light-mode CSS sections here] */
    """
```

**Step 2: Update generate_stylesheet**

```python
def generate_stylesheet(palette: ColorPalette) -> str:
    from ._theme_base_stylesheet import base_stylesheet
    from ._theme_light_stylesheet import light_stylesheet
    if not palette.is_dark:
        return base_stylesheet(palette) + light_stylesheet(palette)
    # dark CSS still inline for now
    return base_stylesheet(palette) + "... dark CSS ..."
```

**Step 3: Run tests**

```bash
pytest tests/unit/test_theme_stylesheet_preservation.py tests/unit/ -q 2>&1 | tail -3
```

Expected: all pass

**Step 4: Commit**

```bash
git add data_graph_studio/ui/_theme_light_stylesheet.py data_graph_studio/ui/theme.py
git commit -m "refactor: extract light_stylesheet from theme.py"
```

---

### Task 4: Extract dark stylesheet

**Files:**
- Create: `data_graph_studio/ui/_theme_dark_stylesheet.py`
- Modify: `data_graph_studio/ui/theme.py`

Same pattern as Task 3, but for dark mode. After this task:

`generate_stylesheet` becomes:
```python
def generate_stylesheet(palette: ColorPalette) -> str:
    """Generate the full Qt stylesheet for the given color palette.

    Args:
        palette: ColorPalette with is_dark flag and color values.

    Returns:
        Complete QSS stylesheet string.
    """
    from ._theme_base_stylesheet import base_stylesheet
    from ._theme_light_stylesheet import light_stylesheet
    from ._theme_dark_stylesheet import dark_stylesheet
    mode_css = dark_stylesheet(palette) if palette.is_dark else light_stylesheet(palette)
    return base_stylesheet(palette) + mode_css
```

Run tests, check `wc -l data_graph_studio/ui/theme.py` — should be ~350 lines.

**Commit:**
```bash
git add data_graph_studio/ui/_theme_dark_stylesheet.py data_graph_studio/ui/theme.py
git commit -m "refactor: extract dark_stylesheet from theme.py — theme.py now ~350 lines"
```

---

## Part 2: table_panel.py Mixin Extraction

### Pre-task: read table_panel.py structure

```bash
grep -n "def \|class " data_graph_studio/ui/panels/table_panel.py | head -80
wc -l data_graph_studio/ui/panels/table_panel.py
```

Understand which class(es) exist and how methods are organized.

---

### Task 5: Extract _TableSearchMixin

**Files:**
- Create: `data_graph_studio/ui/panels/_table_search_mixin.py`
- Modify: `data_graph_studio/ui/panels/table_panel.py`

**Step 1: Identify search methods**

```bash
grep -n "search\|filter\|_apply_filter\|_execute_search\|_clear_search\|_on_search" \
  data_graph_studio/ui/panels/table_panel.py
```

**Step 2: Create the mixin**

```python
# data_graph_studio/ui/panels/_table_search_mixin.py
"""Search and filter behavior for TablePanel."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass  # avoid circular imports


class _TableSearchMixin:
    """Mixin: search bar and filter application for TablePanel.

    Requires self to be a TablePanel instance with:
      - self._search_bar (QLineEdit)
      - self._table_view (DataTableView)
      - self._proxy_model or equivalent filter model
    """

    def _on_search_text_changed(self, text: str) -> None:
        """Handle search text input change."""
        # paste method body here

    def _execute_search(self, text: str) -> None:
        """Apply current search text to table filter."""
        # paste method body here

    def _clear_search(self) -> None:
        """Clear search bar and reset table filter."""
        # paste method body here

    def _apply_filters_and_update(self) -> None:
        """Reapply all active filters and refresh the table view."""
        # paste method body here
```

**Step 3: Remove methods from table_panel.py and add mixin to class**

In `table_panel.py`:
```python
from ._table_search_mixin import _TableSearchMixin

class TablePanel(_TableSearchMixin, QWidget):  # add mixin to inheritance
    ...
    # remove the 4 search methods (now in mixin)
```

**Step 4: Run full test suite**

```bash
pytest tests/unit/ -q 2>&1 | tail -3
```

Expected: same count, no failures

**Step 5: Commit**

```bash
git add data_graph_studio/ui/panels/_table_search_mixin.py \
        data_graph_studio/ui/panels/table_panel.py
git commit -m "refactor: extract _TableSearchMixin from table_panel.py"
```

---

### Task 6: Extract _TableFocusMixin

**Files:**
- Create: `data_graph_studio/ui/panels/_table_focus_mixin.py`
- Modify: `data_graph_studio/ui/panels/table_panel.py`

Same pattern as Task 5. Target methods:
```bash
grep -n "focus\|_on_focus\|_update_focus\|_clear_focus" \
  data_graph_studio/ui/panels/table_panel.py
```

Mixin docstring:
```
Requires self to be a TablePanel with:
  - self._focus_highlight (any highlight tracking object)
  - self._table_view (DataTableView)
```

Run tests, commit:
```bash
git commit -m "refactor: extract _TableFocusMixin from table_panel.py"
```

---

### Task 7: Extract _TableWindowMixin

**Files:**
- Create: `data_graph_studio/ui/panels/_table_window_mixin.py`
- Modify: `data_graph_studio/ui/panels/table_panel.py`

Target methods (windowed/paginated loading):
```bash
grep -n "window\|_apply_window\|_update_window\|slider\|chunk" \
  data_graph_studio/ui/panels/table_panel.py
```

Run tests, commit:
```bash
git commit -m "refactor: extract _TableWindowMixin from table_panel.py"
```

---

### Task 8: Extract _TableColumnMixin

**Files:**
- Create: `data_graph_studio/ui/panels/_table_column_mixin.py`
- Modify: `data_graph_studio/ui/panels/table_panel.py`

Target methods:
```bash
grep -n "column\|freeze\|convert\|visibility\|conditional_format" \
  data_graph_studio/ui/panels/table_panel.py
```

Run tests, commit:
```bash
git commit -m "refactor: extract _TableColumnMixin from table_panel.py"
```

---

### Task 9: Final size verification and cleanup

**Step 1: Verify file sizes**

```bash
wc -l data_graph_studio/ui/theme.py \
       data_graph_studio/ui/panels/table_panel.py \
       data_graph_studio/ui/_theme_base_stylesheet.py \
       data_graph_studio/ui/_theme_light_stylesheet.py \
       data_graph_studio/ui/_theme_dark_stylesheet.py \
       data_graph_studio/ui/panels/_table_search_mixin.py \
       data_graph_studio/ui/panels/_table_focus_mixin.py \
       data_graph_studio/ui/panels/_table_window_mixin.py \
       data_graph_studio/ui/panels/_table_column_mixin.py
```

**Step 2: Run full suite one final time**

```bash
pytest tests/unit/ -q 2>&1 | tail -5
```

Expected: same count, 0 failures

**Step 3: Final commit**

```bash
git add -u
git commit -m "refactor: complete UI large file split — theme + table_panel mixins"
```

---

## Expected Outcome

| File | Before | After |
|------|--------|-------|
| `theme.py` | 2,259 | ~350 |
| `table_panel.py` | 2,803 | ~1,700 |
| New files created | 0 | 7 |
| Tests | 1099 | 1100 (+ preservation test) |
| GOAT Coding Conventions | 6.5 | ~8.0 |
