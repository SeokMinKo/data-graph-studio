"""Tests for the redesigned DataTab (Search + ListBox pattern)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt

from data_graph_studio.ui.panels.data_tab import (
    _SearchableColumnPicker,
    _ColumnListBox,
    _ListBoxItem,
    _YAxisListItem,
    _is_numeric_dtype,
    DataTab,
)


# ---------------------------------------------------------------------------
# _is_numeric_dtype
# ---------------------------------------------------------------------------

class TestIsNumericDtype:
    def test_int_types(self):
        assert _is_numeric_dtype("Int64")
        assert _is_numeric_dtype("int32")
        assert _is_numeric_dtype("UInt8")

    def test_float_types(self):
        assert _is_numeric_dtype("Float64")
        assert _is_numeric_dtype("f32")

    def test_non_numeric(self):
        assert not _is_numeric_dtype("Utf8")
        assert not _is_numeric_dtype("Boolean")
        assert not _is_numeric_dtype("Date")
        assert not _is_numeric_dtype("String")


# ---------------------------------------------------------------------------
# _SearchableColumnPicker
# ---------------------------------------------------------------------------

class TestSearchableColumnPicker:
    def test_set_items(self, qtbot):
        picker = _SearchableColumnPicker()
        qtbot.addWidget(picker)
        picker.set_items(["alpha", "beta", "gamma"])
        assert picker._combo.count() == 3

    def test_set_excluded(self, qtbot):
        picker = _SearchableColumnPicker()
        qtbot.addWidget(picker)
        picker.set_items(["alpha", "beta", "gamma"])
        picker.set_excluded({"beta"})
        assert picker._combo.count() == 2
        texts = [picker._combo.itemText(i) for i in range(picker._combo.count())]
        assert "beta" not in texts

    def test_signal_on_activate(self, qtbot):
        picker = _SearchableColumnPicker()
        qtbot.addWidget(picker)
        picker.set_items(["alpha", "beta"])
        with qtbot.waitSignal(picker.column_selected, timeout=1000) as blocker:
            picker._on_activated(0)
        assert blocker.args == ["alpha"]


# ---------------------------------------------------------------------------
# _ColumnListBox
# ---------------------------------------------------------------------------

class TestColumnListBox:
    def test_add_and_items(self, qtbot):
        lb = _ColumnListBox()
        qtbot.addWidget(lb)
        lb.add_item("col_a")
        lb.add_item("col_b")
        assert lb.items() == ["col_a", "col_b"]
        assert lb.count() == 2

    def test_add_duplicate(self, qtbot):
        lb = _ColumnListBox()
        qtbot.addWidget(lb)
        lb.add_item("col_a")
        lb.add_item("col_a")
        assert lb.count() == 1

    def test_remove(self, qtbot):
        lb = _ColumnListBox()
        qtbot.addWidget(lb)
        lb.add_item("col_a")
        lb.add_item("col_b")
        lb.remove_item("col_a")
        assert lb.items() == ["col_b"]

    def test_clear_all(self, qtbot):
        lb = _ColumnListBox()
        qtbot.addWidget(lb)
        lb.add_item("a")
        lb.add_item("b")
        lb.add_item("c")
        lb.clear_all()
        assert lb.count() == 0

    def test_contains(self, qtbot):
        lb = _ColumnListBox()
        qtbot.addWidget(lb)
        lb.add_item("x")
        assert lb.contains("x")
        assert not lb.contains("y")

    def test_item_removed_signal(self, qtbot):
        lb = _ColumnListBox()
        qtbot.addWidget(lb)
        lb.add_item("col_a")
        with qtbot.waitSignal(lb.item_removed, timeout=1000) as blocker:
            lb.remove_item("col_a")
        assert blocker.args == ["col_a"]


# ---------------------------------------------------------------------------
# _YAxisListItem
# ---------------------------------------------------------------------------

class TestYAxisListItem:
    def test_creation(self, qtbot):
        item = _YAxisListItem("price")
        qtbot.addWidget(item)
        assert item.column_name == "price"

    def test_formula_toggle(self, qtbot):
        item = _YAxisListItem("price")
        qtbot.addWidget(item)
        item.show()
        assert not item.formula_widget.isVisible()
        item.formula_toggle.click()
        assert item.formula_widget.isVisible()
        item.formula_toggle.click()
        assert not item.formula_widget.isVisible()

    def test_set_formula(self, qtbot):
        item = _YAxisListItem("price")
        qtbot.addWidget(item)
        item.show()
        item.set_formula("y*2")
        assert item.formula_edit.text() == "y*2"
        assert item.formula_widget.isVisible()

    def test_remove_signal(self, qtbot):
        item = _YAxisListItem("price")
        qtbot.addWidget(item)
        with qtbot.waitSignal(item.remove_clicked, timeout=1000) as blocker:
            item._remove_btn.click()
        assert blocker.args == ["price"]

    def test_formula_changed_signal(self, qtbot):
        item = _YAxisListItem("price")
        qtbot.addWidget(item)
        item.formula_toggle.click()
        item.formula_edit.setText("LOG(y)")
        with qtbot.waitSignal(item.formula_changed, timeout=1000) as blocker:
            item.formula_edit.editingFinished.emit()
        assert blocker.args == ["price", "LOG(y)"]


# ---------------------------------------------------------------------------
# DataTab (integration-level, mocked state)
# ---------------------------------------------------------------------------

class TestDataTab:
    @pytest.fixture
    def mock_state(self):
        state = MagicMock()
        state.x_column = None
        state.value_columns = []
        state.group_columns = []
        state.hover_columns = []
        # Make signals connectable
        state.chart_settings_changed = MagicMock()
        state.chart_settings_changed.connect = MagicMock()
        state.chart_settings_changed.disconnect = MagicMock()
        state.value_zone_changed = MagicMock()
        state.value_zone_changed.connect = MagicMock()
        state.value_zone_changed.disconnect = MagicMock()
        state.group_zone_changed = MagicMock()
        state.group_zone_changed.connect = MagicMock()
        state.group_zone_changed.disconnect = MagicMock()
        state.hover_zone_changed = MagicMock()
        state.hover_zone_changed.connect = MagicMock()
        state.hover_zone_changed.disconnect = MagicMock()
        state.data_cleared = MagicMock()
        state.data_cleared.connect = MagicMock()
        state.data_cleared.disconnect = MagicMock()
        return state

    @pytest.fixture
    def mock_engine(self):
        engine = MagicMock()
        engine.df = MagicMock()
        engine.df.columns = ["id", "price", "volume", "category"]
        # Simulate dtypes
        class FakeDtype:
            def __init__(self, s): self._s = s
            def __str__(self): return self._s
        engine.df.dtypes = [FakeDtype("Int64"), FakeDtype("Float64"), FakeDtype("Float64"), FakeDtype("Utf8")]
        return engine

    def test_creation(self, qtbot, mock_state):
        tab = DataTab(mock_state)
        qtbot.addWidget(tab)
        assert tab is not None

    def test_set_columns(self, qtbot, mock_state, mock_engine):
        tab = DataTab(mock_state)
        qtbot.addWidget(tab)
        tab.set_columns(["id", "price", "volume", "category"], mock_engine)

        # X-Axis should have all columns + (Index)
        assert tab._x_combo.count() == 5  # (Index) + 4 columns

        # Y-Axis picker should only show numeric columns
        numeric_items = []
        for i in range(tab._y_picker._combo.count()):
            numeric_items.append(tab._y_picker._combo.itemText(i))
        # id, price, volume are numeric (Int64, Float64, Float64)
        assert "category" not in numeric_items
        assert "price" in numeric_items

    def test_clear(self, qtbot, mock_state, mock_engine):
        tab = DataTab(mock_state)
        qtbot.addWidget(tab)
        tab.set_columns(["id", "price", "volume", "category"], mock_engine)
        tab.clear()
        assert tab._x_combo.count() == 0

    def test_no_agg_combo(self, qtbot, mock_state):
        """Verify Agg 1/Agg 2 combos are removed."""
        tab = DataTab(mock_state)
        qtbot.addWidget(tab)
        assert not hasattr(tab, '_agg_combo')
        assert not hasattr(tab, '_agg_combo_2')
        assert not hasattr(tab, '_secondary_agg')

    def test_section_order(self, qtbot, mock_state):
        """Verify section order: Filter → Group By → X-Axis → Y-Axis → Hover."""
        tab = DataTab(mock_state)
        qtbot.addWidget(tab)
        # Collect all section header labels
        headers = []
        layout = tab._main_layout
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w and isinstance(w, type(tab._x_combo).__mro__[0].__mro__[0]):  # QLabel check
                pass
            # Check layout items for section headers
            sub = item.layout()
            if sub is not None:
                for j in range(sub.count()):
                    sub_item = sub.itemAt(j)
                    if sub_item and sub_item.widget():
                        from PySide6.QtWidgets import QLabel
                        ww = sub_item.widget()
                        if isinstance(ww, QLabel) and ww.objectName() == "sectionHeader":
                            headers.append(ww.text())
            if w is not None:
                from PySide6.QtWidgets import QLabel
                if isinstance(w, QLabel) and w.objectName() == "sectionHeader":
                    headers.append(w.text())

        assert headers == ["Filter", "Group By", "X-Axis", "Y-Axis (Values)", "Hover Columns"]

    def test_filter_changed_signal_interface(self, qtbot, mock_state):
        """Verify filter_changed signal exists and emits dict."""
        tab = DataTab(mock_state)
        qtbot.addWidget(tab)
        received = []
        tab.filter_changed.connect(lambda d: received.append(d))
        tab._clear_filter()
        assert received == [{}]

    def test_get_filter_selections_empty(self, qtbot, mock_state):
        tab = DataTab(mock_state)
        qtbot.addWidget(tab)
        assert tab.get_filter_selections() == {}
