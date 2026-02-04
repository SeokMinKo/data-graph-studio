"""
Data Tab - X/Y/Group/Hover configuration for Chart Options panel.

Search + ListBox UI pattern for Y-Axis, Group By, Hover, and Filter sections.
"""

from __future__ import annotations

import functools
from typing import Optional, List, Dict, Set, Any, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QCheckBox, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QCompleter,
)
from PySide6.QtCore import Qt, Signal, Slot, QStringListModel, QSortFilterProxyModel

from ...core.state import AppState, AggregationType, ValueColumn, GroupColumn

if TYPE_CHECKING:
    from ...core.data_engine import DataEngine


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INDEX_SENTINEL = "(Index)"
_AGG_ITEMS: List[tuple[str, AggregationType]] = [
    ("SUM", AggregationType.SUM),
    ("MEAN", AggregationType.MEAN),
    ("MEDIAN", AggregationType.MEDIAN),
    ("MIN", AggregationType.MIN),
    ("MAX", AggregationType.MAX),
    ("COUNT", AggregationType.COUNT),
    ("STD", AggregationType.STD),
    ("VAR", AggregationType.VAR),
    ("FIRST", AggregationType.FIRST),
    ("LAST", AggregationType.LAST),
]

_YAXIS_MAX_HEIGHT = 150
_GROUP_MAX_HEIGHT = 100
_HOVER_MAX_HEIGHT = 100
_FILTER_MAX_HEIGHT = 150


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_separator() -> QFrame:
    """Create a horizontal line separator."""
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setObjectName("dataTabSeparator")
    line.setFixedHeight(2)
    return line


def _make_section_header(
    title: str,
    on_none: object = None,
) -> tuple:
    """Return (QHBoxLayout, btn_none | None) with *title* label and [None] button."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)

    label = QLabel(title)
    label.setObjectName("sectionHeader")
    row.addWidget(label)
    row.addStretch()

    btn_none = None
    if on_none is not None:
        btn_none = QPushButton("None")
        btn_none.setObjectName("smallButton")
        btn_none.setFixedHeight(20)
        btn_none.setMaximumWidth(42)
        btn_none.setToolTip("Deselect all items in this section")
        btn_none.clicked.connect(on_none)
        row.addWidget(btn_none)

    return row, btn_none


def _is_numeric_dtype(dtype_str: str) -> bool:
    """Return *True* if *dtype_str* (Polars string repr) is numeric."""
    dtype_lower = dtype_str.lower()
    numeric_keywords = (
        "int", "float", "decimal", "uint",
        "i8", "i16", "i32", "i64",
        "u8", "u16", "u32", "u64",
        "f32", "f64",
    )
    return any(kw in dtype_lower for kw in numeric_keywords)


# ---------------------------------------------------------------------------
# Reusable widgets: _SearchableColumnPicker and _ColumnListBox
# ---------------------------------------------------------------------------

class _SearchableColumnPicker(QWidget):
    """Editable QComboBox that acts as a searchable column picker.

    When the user selects a column (Enter or click), ``column_selected``
    is emitted and the text is cleared.
    """

    column_selected = Signal(str)

    def __init__(self, placeholder: str = "🔍 Search columns...", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.NoInsert)
        self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._combo.setMinimumHeight(28)
        if self._combo.lineEdit():
            self._combo.lineEdit().setPlaceholderText(placeholder)
        self._combo.activated.connect(self._on_activated)
        layout.addWidget(self._combo)

        self._all_items: List[str] = []
        self._excluded: Set[str] = set()

    def set_items(self, items: List[str]) -> None:
        """Set the full list of available items."""
        self._all_items = list(items)
        self._refresh_combo()

    def set_excluded(self, excluded: Set[str]) -> None:
        """Set items that should be excluded (already selected)."""
        self._excluded = set(excluded)
        self._refresh_combo()

    def _refresh_combo(self) -> None:
        self._combo.blockSignals(True)
        self._combo.clear()
        for item in self._all_items:
            if item not in self._excluded:
                self._combo.addItem(item)
        self._combo.setCurrentIndex(-1)
        if self._combo.lineEdit():
            self._combo.lineEdit().clear()
        self._combo.blockSignals(False)

    def _on_activated(self, index: int) -> None:
        text = self._combo.itemText(index)
        if text and text not in self._excluded:
            self.column_selected.emit(text)
            # Clear text after selection
            self._combo.setCurrentIndex(-1)
            if self._combo.lineEdit():
                self._combo.lineEdit().clear()

    def clear_text(self) -> None:
        self._combo.setCurrentIndex(-1)
        if self._combo.lineEdit():
            self._combo.lineEdit().clear()


class _ListBoxItem(QWidget):
    """Single item in a _ColumnListBox with a label and [×] remove button."""

    remove_clicked = Signal(str)

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.item_text = text
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(4)

        self._label = QLabel(text)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._label, 1)

        self._remove_btn = QPushButton("×")
        self._remove_btn.setObjectName("smallButton")
        self._remove_btn.setFixedSize(20, 20)
        self._remove_btn.setToolTip("Remove this item")
        self._remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.item_text))
        layout.addWidget(self._remove_btn)

    def label_text(self) -> str:
        return self.item_text


class _ColumnListBox(QWidget):
    """Scrollable list of items with [×] remove buttons.

    Signals
    -------
    item_added : str
    item_removed : str
    """

    item_added = Signal(str)
    item_removed = Signal(str)

    def __init__(self, max_height: int = 100, parent: QWidget | None = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setMaximumHeight(max_height)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        self._items: Dict[str, _ListBoxItem] = {}

    def add_item(self, text: str) -> None:
        """Add an item to the list. No-op if already present."""
        if text in self._items:
            return
        item_w = _ListBoxItem(text)
        item_w.remove_clicked.connect(self._on_remove)
        self._items[text] = item_w
        self._layout.insertWidget(self._layout.count() - 1, item_w)
        self.item_added.emit(text)

    def remove_item(self, text: str) -> None:
        """Remove an item by text."""
        item_w = self._items.pop(text, None)
        if item_w is not None:
            item_w.setParent(None)
            item_w.deleteLater()
            self.item_removed.emit(text)

    def clear_all(self) -> None:
        """Remove all items."""
        for text in list(self._items.keys()):
            self.remove_item(text)

    def items(self) -> List[str]:
        """Return list of current item texts, in insertion order."""
        return list(self._items.keys())

    def count(self) -> int:
        return len(self._items)

    def contains(self, text: str) -> bool:
        return text in self._items

    def _on_remove(self, text: str) -> None:
        self.remove_item(text)


# ---------------------------------------------------------------------------
# Per-item widgets used inside the Y-Axis section (ListBox version)
# ---------------------------------------------------------------------------

class _YAxisListItem(QWidget):
    """Single Y-Axis column entry in the list with formula toggle and [×] button."""

    remove_clicked = Signal(str)
    formula_changed = Signal(str, str)  # column_name, formula_text

    def __init__(self, column_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.column_name = column_name
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(2)

        # Row 1 – column name + formula toggle + remove button
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self._label = QLabel(self.column_name)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row1.addWidget(self._label, 1)

        self.formula_toggle = QToolButton()
        self.formula_toggle.setText("▶ f(y)")
        self.formula_toggle.setCheckable(True)
        self.formula_toggle.setChecked(False)
        self.formula_toggle.setMinimumHeight(20)
        self.formula_toggle.setToolTip("Toggle formula editor for this column")
        self.formula_toggle.clicked.connect(self._on_formula_toggled)
        row1.addWidget(self.formula_toggle)

        self._remove_btn = QPushButton("×")
        self._remove_btn.setObjectName("smallButton")
        self._remove_btn.setFixedSize(20, 20)
        self._remove_btn.setToolTip("Remove this column")
        self._remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.column_name))
        row1.addWidget(self._remove_btn)

        layout.addLayout(row1)

        # Row 2 – formula input (hidden by default)
        self.formula_widget = QWidget()
        formula_layout = QHBoxLayout(self.formula_widget)
        formula_layout.setContentsMargins(20, 0, 0, 0)
        formula_layout.setSpacing(4)

        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText("f(y)=...  e.g. y*2, LOG(y)")
        self.formula_edit.setMinimumHeight(24)
        self.formula_edit.editingFinished.connect(self._on_formula_finished)
        formula_layout.addWidget(self.formula_edit)
        layout.addWidget(self.formula_widget)
        self.formula_widget.setVisible(False)

    def _on_formula_toggled(self, checked: bool) -> None:
        self.formula_widget.setVisible(checked)
        self.formula_toggle.setText("▼ f(y)" if checked else "▶ f(y)")

    def _on_formula_finished(self) -> None:
        self.formula_changed.emit(self.column_name, self.formula_edit.text().strip())

    def set_formula(self, formula: str) -> None:
        self.formula_edit.setText(formula)
        if formula:
            self.formula_toggle.setChecked(True)
            self.formula_widget.setVisible(True)
            self.formula_toggle.setText("▼ f(y)")

    def get_formula(self) -> str:
        return self.formula_edit.text().strip()


# ---------------------------------------------------------------------------
# Kept for backward compatibility — old _YAxisItemWidget is no longer used
# by the new UI but some test code may reference the class.
# ---------------------------------------------------------------------------

_YAxisItemWidget = _YAxisListItem  # alias


# ---------------------------------------------------------------------------
# DataTab
# ---------------------------------------------------------------------------

class DataTab(QWidget):
    """Chart Options → Data tab.

    Provides Search + ListBox UI for X-Axis, Y-Axis (Values),
    Group By, Hover column configuration, and Filter.

    Section order (top → bottom):
    1. Filter
    2. Group By
    3. X-Axis
    4. Y-Axis (Values)
    5. Hover

    Parameters
    ----------
    state : AppState
        The shared application state singleton.
    """

    # Emitted when the user changes filter selections.
    # Dict[str, List[Any]]: mapping of column name → selected values.
    filter_changed = Signal(dict)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self._state = state

        # Column metadata (populated by set_columns)
        self._all_columns: List[str] = []
        self._numeric_columns: Set[str] = set()

        # Filter state
        self._filter_engine: "DataEngine | None" = None
        self._filter_data: Dict[str, List[str]] = {}  # column → [selected values]

        # Guard flag for bulk updates
        self._syncing = False

        self._setup_ui()
        self._connect_state_signals()

    # ======================================================================
    # UI Setup
    # ======================================================================

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Wrap everything in a top-level QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(6, 6, 6, 6)
        self._main_layout.setSpacing(8)

        # =================================================================
        # 1. Filter
        # =================================================================
        f_row, self._filter_badge = _make_section_header(
            "Filter",
            on_none=self._clear_filter,
        )
        self._main_layout.addLayout(f_row)

        # Column selector
        self._filter_col_combo = QComboBox()
        self._filter_col_combo.setEditable(True)
        self._filter_col_combo.setInsertPolicy(QComboBox.NoInsert)
        self._filter_col_combo.setToolTip("Select column to filter on")
        self._filter_col_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._filter_col_combo.setMinimumHeight(28)
        if self._filter_col_combo.lineEdit():
            self._filter_col_combo.lineEdit().setPlaceholderText("🔍 Search columns...")
        self._filter_col_combo.currentIndexChanged.connect(self._on_filter_column_changed)
        self._main_layout.addWidget(self._filter_col_combo)

        # Value selector
        self._filter_val_combo = QComboBox()
        self._filter_val_combo.setEditable(True)
        self._filter_val_combo.setInsertPolicy(QComboBox.NoInsert)
        self._filter_val_combo.setToolTip("Select value to add as filter")
        self._filter_val_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._filter_val_combo.setMinimumHeight(28)
        if self._filter_val_combo.lineEdit():
            self._filter_val_combo.lineEdit().setPlaceholderText("🔍 Search values...")
        self._filter_val_combo.activated.connect(self._on_filter_value_selected)
        self._main_layout.addWidget(self._filter_val_combo)

        # [All] [None] buttons
        filter_btn_row = QHBoxLayout()
        filter_btn_row.setSpacing(4)
        self._filter_select_all_btn = QPushButton("All")
        self._filter_select_all_btn.setObjectName("smallButton")
        self._filter_select_all_btn.setFixedHeight(20)
        self._filter_select_all_btn.clicked.connect(self._filter_select_all)
        filter_btn_row.addWidget(self._filter_select_all_btn)
        self._filter_deselect_all_btn = QPushButton("None")
        self._filter_deselect_all_btn.setObjectName("smallButton")
        self._filter_deselect_all_btn.setFixedHeight(20)
        self._filter_deselect_all_btn.clicked.connect(self._filter_deselect_all)
        filter_btn_row.addWidget(self._filter_deselect_all_btn)
        filter_btn_row.addStretch()
        self._main_layout.addLayout(filter_btn_row)

        # Filter ListBox
        self._filter_listbox = _ColumnListBox(max_height=_FILTER_MAX_HEIGHT)
        self._filter_listbox.item_removed.connect(self._on_filter_item_removed)
        self._main_layout.addWidget(self._filter_listbox)

        # Keep unique values for the currently selected filter column
        self._filter_unique_vals: List[str] = []

        self._main_layout.addWidget(_make_separator())

        # =================================================================
        # 2. Group By
        # =================================================================
        g_row, self._group_badge = _make_section_header(
            "Group By",
            on_none=self._select_none_group,
        )
        self._main_layout.addLayout(g_row)

        self._group_picker = _SearchableColumnPicker("🔍 Search columns...")
        self._group_picker.column_selected.connect(self._on_group_column_selected)
        self._main_layout.addWidget(self._group_picker)

        self._group_listbox = _ColumnListBox(max_height=_GROUP_MAX_HEIGHT)
        self._group_listbox.item_removed.connect(self._on_group_item_removed)
        self._main_layout.addWidget(self._group_listbox)

        self._main_layout.addWidget(_make_separator())

        # =================================================================
        # 3. X-Axis
        # =================================================================
        x_header = QLabel("X-Axis")
        x_header.setObjectName("sectionHeader")
        self._main_layout.addWidget(x_header)

        self._x_combo = QComboBox()
        self._x_combo.setEditable(True)
        self._x_combo.setInsertPolicy(QComboBox.NoInsert)
        self._x_combo.setToolTip("Select column for X-axis (or use index)")
        self._x_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if self._x_combo.lineEdit():
            self._x_combo.lineEdit().setPlaceholderText("🔍 Search column...")
        self._x_combo.currentIndexChanged.connect(self._on_x_combo_changed)
        self._main_layout.addWidget(self._x_combo)

        self._main_layout.addWidget(_make_separator())

        # =================================================================
        # 4. Y-Axis (Values) — Search + ListBox with f(y) support
        # =================================================================
        y_row, self._y_badge = _make_section_header(
            "Y-Axis (Values)",
            on_none=self._select_none_y,
        )
        self._main_layout.addLayout(y_row)

        self._y_picker = _SearchableColumnPicker("🔍 Search numeric columns...")
        self._y_picker.column_selected.connect(self._on_y_column_selected)
        self._main_layout.addWidget(self._y_picker)

        # Y-Axis ListBox (custom, with _YAxisListItem widgets)
        self._y_scroll = QScrollArea()
        self._y_scroll.setWidgetResizable(True)
        self._y_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._y_scroll.setMaximumHeight(_YAXIS_MAX_HEIGHT)
        self._y_scroll.setFrameShape(QFrame.NoFrame)

        self._y_container = QWidget()
        self._y_layout = QVBoxLayout(self._y_container)
        self._y_layout.setContentsMargins(0, 0, 0, 0)
        self._y_layout.setSpacing(2)
        self._y_layout.addStretch()
        self._y_scroll.setWidget(self._y_container)
        self._main_layout.addWidget(self._y_scroll)

        self._y_items: Dict[str, _YAxisListItem] = {}

        self._main_layout.addWidget(_make_separator())

        # =================================================================
        # 5. Hover
        # =================================================================
        h_row, self._hover_badge = _make_section_header(
            "Hover Columns",
            on_none=self._select_none_hover,
        )
        self._main_layout.addLayout(h_row)

        self._hover_picker = _SearchableColumnPicker("🔍 Search columns...")
        self._hover_picker.column_selected.connect(self._on_hover_column_selected)
        self._main_layout.addWidget(self._hover_picker)

        self._hover_listbox = _ColumnListBox(max_height=_HOVER_MAX_HEIGHT)
        self._hover_listbox.item_removed.connect(self._on_hover_item_removed)
        self._main_layout.addWidget(self._hover_listbox)

        # Bottom stretch
        self._main_layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ======================================================================
    # State signal connections
    # ======================================================================

    def _connect_state_signals(self) -> None:
        self._state.chart_settings_changed.connect(self._on_state_x_changed)
        self._state.value_zone_changed.connect(self._on_state_value_changed)
        self._state.group_zone_changed.connect(self._on_state_group_changed)
        self._state.hover_zone_changed.connect(self._on_state_hover_changed)
        self._state.data_cleared.connect(self.clear)

    def _disconnect_state_signals(self) -> None:
        for sig, slot in [
            (self._state.chart_settings_changed, self._on_state_x_changed),
            (self._state.value_zone_changed, self._on_state_value_changed),
            (self._state.group_zone_changed, self._on_state_group_changed),
            (self._state.hover_zone_changed, self._on_state_hover_changed),
            (self._state.data_cleared, self.clear),
        ]:
            try:
                sig.disconnect(slot)
            except RuntimeError:
                pass

    # ======================================================================
    # Public API
    # ======================================================================

    def set_columns(self, columns: List[str], engine: "DataEngine") -> None:
        """Populate all sections from a newly-loaded dataset."""
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            self._all_columns = list(columns)
            self._numeric_columns = set()
            self._filter_engine = engine

            # Determine numeric columns
            if engine.df is not None:
                for col, dtype in zip(engine.df.columns, engine.df.dtypes):
                    if _is_numeric_dtype(str(dtype)):
                        self._numeric_columns.add(col)

            self._rebuild_x_combo()
            self._rebuild_pickers()
            self._rebuild_filter_combo()

            # Clear listboxes before sync
            self._clear_y_items()
            self._group_listbox.clear_all()
            self._hover_listbox.clear_all()

            # Sync current state into the new widgets
            self._sync_from_state_internal()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    def clear(self) -> None:
        """Clear all widgets (data unloaded)."""
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            self._all_columns = []
            self._numeric_columns = set()

            self._x_combo.blockSignals(True)
            self._x_combo.clear()
            self._x_combo.blockSignals(False)

            self._clear_y_items()
            self._group_listbox.clear_all()
            self._hover_listbox.clear_all()
            self._clear_filter_state()

            self._y_picker.set_items([])
            self._group_picker.set_items([])
            self._hover_picker.set_items([])
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    def sync_from_state(self) -> None:
        """Re-sync the entire UI from the current AppState."""
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            self._sync_from_state_internal()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    def cleanup(self) -> None:
        """Disconnect all signals.  Call before widget destruction."""
        self._disconnect_state_signals()

    # ======================================================================
    # Internal – widget builders
    # ======================================================================

    def _rebuild_x_combo(self) -> None:
        self._x_combo.blockSignals(True)
        self._x_combo.clear()
        self._x_combo.addItem(_INDEX_SENTINEL, None)
        for col in self._all_columns:
            self._x_combo.addItem(col, col)
        self._x_combo.blockSignals(False)

    def _rebuild_pickers(self) -> None:
        """Rebuild the column pickers for Y-Axis, Group By, Hover."""
        numeric_cols = [c for c in self._all_columns if c in self._numeric_columns]
        self._y_picker.set_items(numeric_cols)
        self._group_picker.set_items(list(self._all_columns))
        self._hover_picker.set_items(list(self._all_columns))

    def _rebuild_filter_combo(self) -> None:
        """Rebuild the filter column combo box."""
        self._filter_col_combo.blockSignals(True)
        self._filter_col_combo.clear()
        for col in self._all_columns:
            self._filter_col_combo.addItem(col)
        self._filter_col_combo.setCurrentIndex(-1)
        if self._filter_col_combo.lineEdit():
            self._filter_col_combo.lineEdit().clear()
        self._filter_col_combo.blockSignals(False)

        self._filter_val_combo.blockSignals(True)
        self._filter_val_combo.clear()
        self._filter_val_combo.blockSignals(False)
        self._filter_unique_vals = []
        self._update_filter_badge()

    # -- Y-Axis item management ---------------------------------------------

    def _add_y_item(self, col: str, formula: str = "") -> None:
        """Add a Y-Axis item widget."""
        if col in self._y_items:
            return
        item = _YAxisListItem(col)
        item.remove_clicked.connect(self._on_y_item_removed)
        item.formula_changed.connect(self._on_y_formula_changed)
        if formula:
            item.set_formula(formula)
        self._y_items[col] = item
        self._y_layout.insertWidget(self._y_layout.count() - 1, item)
        self._update_y_picker_excluded()

    def _remove_y_item(self, col: str) -> None:
        """Remove a Y-Axis item widget."""
        item = self._y_items.pop(col, None)
        if item is not None:
            item.setParent(None)
            item.deleteLater()
            self._update_y_picker_excluded()

    def _clear_y_items(self) -> None:
        for item in self._y_items.values():
            item.setParent(None)
            item.deleteLater()
        self._y_items.clear()
        self._update_y_picker_excluded()

    def _update_y_picker_excluded(self) -> None:
        self._y_picker.set_excluded(set(self._y_items.keys()))

    def _update_group_picker_excluded(self) -> None:
        self._group_picker.set_excluded(set(self._group_listbox.items()))

    def _update_hover_picker_excluded(self) -> None:
        self._hover_picker.set_excluded(set(self._hover_listbox.items()))

    # -- Clear filter state --------------------------------------------------

    def _clear_filter_state(self) -> None:
        self._filter_listbox.clear_all()
        self._filter_data.clear()
        self._filter_unique_vals = []
        self._filter_col_combo.blockSignals(True)
        self._filter_col_combo.setCurrentIndex(-1)
        if self._filter_col_combo.lineEdit():
            self._filter_col_combo.lineEdit().clear()
        self._filter_col_combo.blockSignals(False)
        self._filter_val_combo.blockSignals(True)
        self._filter_val_combo.clear()
        self._filter_val_combo.blockSignals(False)

    # ======================================================================
    # Internal – state → UI sync
    # ======================================================================

    def _sync_from_state_internal(self) -> None:
        """Sync all sections from current AppState."""
        # X-Axis
        self._x_combo.blockSignals(True)
        x_col = self._state.x_column
        if x_col is None:
            self._x_combo.setCurrentIndex(0)  # (Index)
        else:
            idx = self._x_combo.findData(x_col)
            if idx >= 0:
                self._x_combo.setCurrentIndex(idx)
            else:
                self._x_combo.setCurrentIndex(0)
        self._x_combo.blockSignals(False)

        # Y-Axis — rebuild list from state
        self._clear_y_items()
        for vc in self._state.value_columns:
            self._add_y_item(vc.name, vc.formula)

        # Group By — rebuild list from state
        self._group_listbox.blockSignals(True)
        self._group_listbox.clear_all()
        for gc in self._state.group_columns:
            self._group_listbox.add_item(gc.name)
        self._group_listbox.blockSignals(False)
        self._update_group_picker_excluded()

        # Hover — rebuild list from state
        self._hover_listbox.blockSignals(True)
        self._hover_listbox.clear_all()
        for hc in self._state.hover_columns:
            self._hover_listbox.add_item(hc)
        self._hover_listbox.blockSignals(False)
        self._update_hover_picker_excluded()

        self._update_badges()

    # ======================================================================
    # Badge helpers
    # ======================================================================

    def _update_badges(self) -> None:
        """Update the None/count badge text for all sections."""
        n_y = len(self._y_items)
        if self._y_badge:
            self._y_badge.setText(f"{n_y}개" if n_y > 0 else "None")
            self._y_badge.setMaximumWidth(42 if n_y == 0 else 48)

        n_g = self._group_listbox.count()
        if self._group_badge:
            self._group_badge.setText(f"{n_g}개" if n_g > 0 else "None")
            self._group_badge.setMaximumWidth(42 if n_g == 0 else 48)

        n_h = self._hover_listbox.count()
        if self._hover_badge:
            self._hover_badge.setText(f"{n_h}개" if n_h > 0 else "None")
            self._hover_badge.setMaximumWidth(42 if n_h == 0 else 48)

        self._update_filter_badge()

    # ======================================================================
    # Slots – state signals → UI refresh
    # ======================================================================

    @Slot()
    def _on_state_x_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._x_combo.blockSignals(True)
            x_col = self._state.x_column
            if x_col is None:
                self._x_combo.setCurrentIndex(0)
            else:
                idx = self._x_combo.findData(x_col)
                if idx >= 0:
                    self._x_combo.setCurrentIndex(idx)
            self._x_combo.blockSignals(False)
        finally:
            self._syncing = False

    @Slot()
    def _on_state_value_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            # Rebuild Y-Axis items from state
            state_cols = {vc.name: vc for vc in self._state.value_columns}

            # Remove items not in state
            for col in list(self._y_items.keys()):
                if col not in state_cols:
                    self._remove_y_item(col)

            # Add/update items from state
            for vc in self._state.value_columns:
                if vc.name not in self._y_items:
                    self._add_y_item(vc.name, vc.formula)
                else:
                    item = self._y_items[vc.name]
                    if item.get_formula() != vc.formula:
                        item.set_formula(vc.formula)

            self._update_badges()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    @Slot()
    def _on_state_group_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            group_names = [gc.name for gc in self._state.group_columns]
            current = set(self._group_listbox.items())
            target = set(group_names)

            self._group_listbox.blockSignals(True)
            # Remove items not in state
            for col in current - target:
                self._group_listbox.remove_item(col)
            # Add items from state
            for col in group_names:
                if col not in current:
                    self._group_listbox.add_item(col)
            self._group_listbox.blockSignals(False)

            self._update_group_picker_excluded()
            self._update_badges()
        finally:
            self._syncing = False

    @Slot()
    def _on_state_hover_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            hover_names = list(self._state.hover_columns)
            current = set(self._hover_listbox.items())
            target = set(hover_names)

            self._hover_listbox.blockSignals(True)
            for col in current - target:
                self._hover_listbox.remove_item(col)
            for col in hover_names:
                if col not in current:
                    self._hover_listbox.add_item(col)
            self._hover_listbox.blockSignals(False)

            self._update_hover_picker_excluded()
            self._update_badges()
        finally:
            self._syncing = False

    # ======================================================================
    # Slots – UI interactions → state mutations
    # ======================================================================

    @Slot(int)
    def _on_x_combo_changed(self, index: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            data = self._x_combo.itemData(index)
            self._state.set_x_column(data)  # None for (Index)
        finally:
            self._syncing = False

    # -- Y-Axis --------------------------------------------------------------

    def _on_y_column_selected(self, col: str) -> None:
        """User picked a column from Y-Axis picker."""
        if self._syncing:
            return
        self._syncing = True
        try:
            if not any(vc.name == col for vc in self._state.value_columns):
                self._state.add_value_column(col)
            # State signal will update UI
        finally:
            self._syncing = False
        # Force UI update since we set _syncing
        self._add_y_item(col)
        self._update_badges()

    def _on_y_item_removed(self, col: str) -> None:
        """User clicked [×] on a Y-Axis item."""
        if self._syncing:
            return
        self._syncing = True
        try:
            for i, vc in enumerate(self._state.value_columns):
                if vc.name == col:
                    self._state.remove_value_column(i)
                    break
        finally:
            self._syncing = False
        self._remove_y_item(col)
        self._update_badges()

    def _on_y_formula_changed(self, col: str, formula: str) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            for i, vc in enumerate(self._state.value_columns):
                if vc.name == col:
                    self._state.update_value_column(i, formula=formula)
                    break
        finally:
            self._syncing = False

    # -- Group By ------------------------------------------------------------

    def _on_group_column_selected(self, col: str) -> None:
        """User picked a column from Group By picker."""
        if self._syncing:
            return
        self._syncing = True
        try:
            self._state.add_group_column(col)
        finally:
            self._syncing = False
        self._group_listbox.blockSignals(True)
        self._group_listbox.add_item(col)
        self._group_listbox.blockSignals(False)
        self._update_group_picker_excluded()
        self._update_badges()

    def _on_group_item_removed(self, col: str) -> None:
        """User clicked [×] on a Group By item."""
        if self._syncing:
            return
        self._syncing = True
        try:
            self._state.remove_group_column(col)
        finally:
            self._syncing = False
        self._update_group_picker_excluded()
        self._update_badges()

    # -- Hover ---------------------------------------------------------------

    def _on_hover_column_selected(self, col: str) -> None:
        """User picked a column from Hover picker."""
        if self._syncing:
            return
        self._syncing = True
        try:
            self._state.add_hover_column(col)
        finally:
            self._syncing = False
        self._hover_listbox.blockSignals(True)
        self._hover_listbox.add_item(col)
        self._hover_listbox.blockSignals(False)
        self._update_hover_picker_excluded()
        self._update_badges()

    def _on_hover_item_removed(self, col: str) -> None:
        """User clicked [×] on a Hover item."""
        if self._syncing:
            return
        self._syncing = True
        try:
            self._state.remove_hover_column(col)
        finally:
            self._syncing = False
        self._update_hover_picker_excluded()
        self._update_badges()

    # ======================================================================
    # Bulk actions – [None]
    # ======================================================================

    @Slot()
    def _select_none_y(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            self._clear_y_items()
            self._state.clear_value_zone()
            self._update_badges()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    def _select_none_group(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            self._group_listbox.blockSignals(True)
            self._group_listbox.clear_all()
            self._group_listbox.blockSignals(False)
            self._update_group_picker_excluded()
            self._state.clear_group_zone()
            self._update_badges()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    def _select_none_hover(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            self._hover_listbox.blockSignals(True)
            self._hover_listbox.clear_all()
            self._hover_listbox.blockSignals(False)
            self._update_hover_picker_excluded()
            self._state.clear_hover_columns()
            self._update_badges()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    # ==================================================================
    # Filter section
    # ==================================================================

    def _on_filter_column_changed(self, index: int) -> None:
        """Load unique values when filter column changes."""
        self._filter_val_combo.blockSignals(True)
        self._filter_val_combo.clear()
        self._filter_val_combo.blockSignals(False)
        self._filter_unique_vals = []

        col = self._filter_col_combo.currentText()
        if not col or self._filter_engine is None:
            return

        try:
            df = self._filter_engine.df
            if df is None or col not in df.columns:
                return
            unique_vals = [str(v) for v in df[col].drop_nulls().unique().sort().to_list()[:500]]
        except Exception:
            unique_vals = []

        self._filter_unique_vals = unique_vals

        # Exclude already-selected values for this column
        already_selected = set(self._filter_data.get(col, []))
        self._filter_val_combo.blockSignals(True)
        for val in unique_vals:
            if val not in already_selected:
                self._filter_val_combo.addItem(val)
        self._filter_val_combo.setCurrentIndex(-1)
        if self._filter_val_combo.lineEdit():
            self._filter_val_combo.lineEdit().clear()
        self._filter_val_combo.blockSignals(False)

    def _on_filter_value_selected(self, index: int) -> None:
        """User selected a value from the filter value combo."""
        val = self._filter_val_combo.itemText(index)
        col = self._filter_col_combo.currentText()
        if not val or not col:
            return

        # Add to filter data
        if col not in self._filter_data:
            self._filter_data[col] = []
        if val not in self._filter_data[col]:
            self._filter_data[col].append(val)

        # Add to listbox
        display = f"{col} = {val}"
        self._filter_listbox.add_item(display)

        # Remove from value combo (already selected)
        idx = self._filter_val_combo.findText(val)
        if idx >= 0:
            self._filter_val_combo.removeItem(idx)
        self._filter_val_combo.setCurrentIndex(-1)
        if self._filter_val_combo.lineEdit():
            self._filter_val_combo.lineEdit().clear()

        self._emit_filter_signal()
        self._update_filter_badge()

    def _on_filter_item_removed(self, display_text: str) -> None:
        """User clicked [×] on a filter item."""
        # Parse "column = value"
        parts = display_text.split(" = ", 1)
        if len(parts) != 2:
            return
        col, val = parts[0], parts[1]

        if col in self._filter_data:
            if val in self._filter_data[col]:
                self._filter_data[col].remove(val)
            if not self._filter_data[col]:
                del self._filter_data[col]

        # Re-add to value combo if this column is currently selected
        if self._filter_col_combo.currentText() == col:
            self._filter_val_combo.addItem(val)

        self._emit_filter_signal()
        self._update_filter_badge()

    def _filter_select_all(self) -> None:
        """Add all values for the currently selected filter column."""
        col = self._filter_col_combo.currentText()
        if not col or not self._filter_unique_vals:
            return

        if col not in self._filter_data:
            self._filter_data[col] = []

        for val in self._filter_unique_vals:
            if val not in self._filter_data[col]:
                self._filter_data[col].append(val)
                display = f"{col} = {val}"
                self._filter_listbox.add_item(display)

        # Clear value combo (all selected)
        self._filter_val_combo.blockSignals(True)
        self._filter_val_combo.clear()
        self._filter_val_combo.setCurrentIndex(-1)
        if self._filter_val_combo.lineEdit():
            self._filter_val_combo.lineEdit().clear()
        self._filter_val_combo.blockSignals(False)

        self._emit_filter_signal()
        self._update_filter_badge()

    def _filter_deselect_all(self) -> None:
        """Remove all filter values for the currently selected column."""
        col = self._filter_col_combo.currentText()
        if not col:
            return

        # Remove items for this column from listbox
        to_remove = [item for item in self._filter_listbox.items() if item.startswith(f"{col} = ")]
        for item in to_remove:
            self._filter_listbox.remove_item(item)

        if col in self._filter_data:
            del self._filter_data[col]

        # Repopulate value combo
        self._filter_val_combo.blockSignals(True)
        self._filter_val_combo.clear()
        for val in self._filter_unique_vals:
            self._filter_val_combo.addItem(val)
        self._filter_val_combo.setCurrentIndex(-1)
        if self._filter_val_combo.lineEdit():
            self._filter_val_combo.lineEdit().clear()
        self._filter_val_combo.blockSignals(False)

        self._emit_filter_signal()
        self._update_filter_badge()

    def _clear_filter(self) -> None:
        """Reset all filters."""
        self._filter_listbox.clear_all()
        self._filter_data.clear()
        self._filter_col_combo.blockSignals(True)
        self._filter_col_combo.setCurrentIndex(-1)
        if self._filter_col_combo.lineEdit():
            self._filter_col_combo.lineEdit().clear()
        self._filter_col_combo.blockSignals(False)
        self._filter_val_combo.blockSignals(True)
        self._filter_val_combo.clear()
        self._filter_val_combo.blockSignals(False)
        self._filter_unique_vals = []
        self.filter_changed.emit({})
        self._update_filter_badge()

    def _emit_filter_signal(self) -> None:
        self.filter_changed.emit(dict(self._filter_data))

    def _update_filter_badge(self) -> None:
        total_items = self._filter_listbox.count()
        if self._filter_badge:
            if total_items == 0:
                self._filter_badge.setText("None")
            else:
                self._filter_badge.setText(f"{total_items}개")

    def get_filter_selections(self) -> Dict[str, list]:
        """Return current filter as {column: [selected_values]}.

        Returns empty dict when no filter is active.
        """
        return dict(self._filter_data)
