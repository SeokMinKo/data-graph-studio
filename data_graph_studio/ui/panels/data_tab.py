"""
Data Tab - X/Y/Group/Hover configuration for Chart Options panel.

Replaces the drag-and-drop Zone widgets with combo-box / checkbox UI
inside the GraphOptionsPanel "Data" tab.
"""

from __future__ import annotations

import functools
from typing import Optional, List, Dict, Set, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QCheckBox, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QToolButton,
)
from PySide6.QtCore import Qt, Signal, Slot

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
# Per-item widgets used inside the Y-Axis section
# ---------------------------------------------------------------------------

class _YAxisItemWidget(QWidget):
    """Single Y-Axis column entry with checkbox and formula toggle."""

    checked_changed = Signal(str, bool)       # column_name, checked
    agg_changed = Signal(str, object)         # column_name, AggregationType
    formula_changed = Signal(str, str)         # column_name, formula_text

    def __init__(self, column_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.column_name = column_name
        self._setup_ui()

    # -- UI ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(2)

        # Row 1 – checkbox + formula toggle
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self.checkbox = QCheckBox(self.column_name)
        self.checkbox.stateChanged.connect(self._on_check_state)
        row1.addWidget(self.checkbox, 1)

        self.formula_toggle = QToolButton()
        self.formula_toggle.setText("▶ f(y)")
        self.formula_toggle.setCheckable(True)
        self.formula_toggle.setChecked(False)
        self.formula_toggle.setMinimumHeight(20)
        self.formula_toggle.setToolTip("Toggle formula editor for this column")
        self.formula_toggle.clicked.connect(self._on_formula_toggled)
        self.formula_toggle.setVisible(False)
        row1.addWidget(self.formula_toggle)

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

        # detail_widget kept as alias for compat (visibility toggling)
        self.detail_widget = self.formula_toggle

    # -- Slots ---------------------------------------------------------------

    def _on_check_state(self, state: int) -> None:
        checked = state == Qt.Checked.value if hasattr(Qt.Checked, 'value') else state == int(Qt.Checked)
        self.formula_toggle.setVisible(checked)
        if not checked:
            self.formula_widget.setVisible(False)
            self.formula_toggle.setChecked(False)
            self.formula_toggle.setText("▶ f(y)")
        self.checked_changed.emit(self.column_name, checked)

    def _on_formula_toggled(self, checked: bool) -> None:
        self.formula_widget.setVisible(checked)
        self.formula_toggle.setText("▼ f(y)" if checked else "▶ f(y)")

    def _on_formula_finished(self) -> None:
        self.formula_changed.emit(self.column_name, self.formula_edit.text().strip())

    # -- Public helpers ------------------------------------------------------

    def set_checked(self, checked: bool) -> None:
        self.checkbox.setChecked(checked)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def set_aggregation(self, agg: AggregationType) -> None:
        """Kept for compat — aggregation now managed in Group By section."""
        pass

    def set_formula(self, formula: str) -> None:
        self.formula_edit.setText(formula)
        if formula:
            self.formula_toggle.setChecked(True)
            self.formula_widget.setVisible(True)
            self.formula_toggle.setText("▼ f(y)")

    def block_signals(self, block: bool) -> None:
        """Block / unblock all child signals."""
        self.checkbox.blockSignals(block)
        self.formula_edit.blockSignals(block)


# ---------------------------------------------------------------------------
# DataTab
# ---------------------------------------------------------------------------

class DataTab(QWidget):
    """Chart Options → Data tab.

    Provides combo-box / checkbox UI for X-Axis, Y-Axis (Values),
    Group By, Hover column configuration, and **Filter** (Item 15).

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

        # Widget references for fast lookup
        self._y_items: Dict[str, _YAxisItemWidget] = {}
        self._group_checks: Dict[str, QCheckBox] = {}
        self._hover_checks: Dict[str, QCheckBox] = {}

        # Filter state
        self._filter_engine: "DataEngine | None" = None
        self._filter_checks: Dict[str, QCheckBox] = {}  # value → checkbox

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

        # --- X-Axis ---------------------------------------------------------
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

        # --- Y-Axis (Values) ------------------------------------------------
        y_row, self._y_badge = _make_section_header(
            "Y-Axis (Values)",
            on_none=self._select_none_y,
        )
        self._main_layout.addLayout(y_row)

        self._y_search = QLineEdit()
        self._y_search.setPlaceholderText("🔍 Search columns...")
        self._y_search.setFixedHeight(28)
        self._y_search.setClearButtonEnabled(True)
        self._y_search.textChanged.connect(self._filter_y_items)
        self._main_layout.addWidget(self._y_search)

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

        self._main_layout.addWidget(_make_separator())

        # --- Group By -------------------------------------------------------
        g_row, self._group_badge = _make_section_header(
            "Group By",
            on_none=self._select_none_group,
        )
        self._main_layout.addLayout(g_row)

        self._group_search = QLineEdit()
        self._group_search.setPlaceholderText("🔍 Search columns...")
        self._group_search.setFixedHeight(28)
        self._group_search.setClearButtonEnabled(True)
        self._group_search.textChanged.connect(self._filter_group_items)
        self._main_layout.addWidget(self._group_search)

        self._group_scroll = QScrollArea()
        self._group_scroll.setWidgetResizable(True)
        self._group_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._group_scroll.setMaximumHeight(_GROUP_MAX_HEIGHT)
        self._group_scroll.setFrameShape(QFrame.NoFrame)

        self._group_container = QWidget()
        self._group_layout = QVBoxLayout(self._group_container)
        self._group_layout.setContentsMargins(0, 0, 0, 0)
        self._group_layout.setSpacing(2)
        self._group_layout.addStretch()
        self._group_scroll.setWidget(self._group_container)
        self._main_layout.addWidget(self._group_scroll)

        # Aggregation type for grouped data – level 1
        agg_row = QHBoxLayout()
        agg_row.setSpacing(4)
        agg_label = QLabel("Agg 1:")
        agg_label.setStyleSheet("font-size: 11px;")
        agg_row.addWidget(agg_label)

        self._agg_combo = QComboBox()
        self._agg_combo.setMinimumHeight(24)
        self._agg_combo.setToolTip("Primary aggregation function for grouped data")
        for label, agg in _AGG_ITEMS:
            self._agg_combo.addItem(label, agg)
        self._agg_combo.currentIndexChanged.connect(self._on_global_agg_changed)
        agg_row.addWidget(self._agg_combo, 1)
        self._main_layout.addLayout(agg_row)

        # Aggregation type – level 2
        agg_row2 = QHBoxLayout()
        agg_row2.setSpacing(4)
        agg_label2 = QLabel("Agg 2:")
        agg_label2.setStyleSheet("font-size: 11px;")
        agg_row2.addWidget(agg_label2)

        self._agg_combo_2 = QComboBox()
        self._agg_combo_2.setMinimumHeight(24)
        self._agg_combo_2.setToolTip("Secondary aggregation function for grouped data")
        for label, agg in _AGG_ITEMS:
            self._agg_combo_2.addItem(label, agg)
        # Default Agg 2 to MEAN
        mean_idx = next((i for i, (l, a) in enumerate(_AGG_ITEMS) if a == AggregationType.MEAN), 1)
        self._agg_combo_2.setCurrentIndex(mean_idx)
        self._secondary_agg: AggregationType = AggregationType.MEAN
        self._agg_combo_2.currentIndexChanged.connect(self._on_global_agg2_changed)
        agg_row2.addWidget(self._agg_combo_2, 1)
        self._main_layout.addLayout(agg_row2)

        self._main_layout.addWidget(_make_separator())

        # --- Hover Columns --------------------------------------------------
        h_row, self._hover_badge = _make_section_header(
            "Hover Columns",
            on_none=self._select_none_hover,
        )
        self._main_layout.addLayout(h_row)

        self._hover_search = QLineEdit()
        self._hover_search.setPlaceholderText("🔍 Search columns...")
        self._hover_search.setFixedHeight(28)
        self._hover_search.setClearButtonEnabled(True)
        self._hover_search.textChanged.connect(self._filter_hover_items)
        self._main_layout.addWidget(self._hover_search)

        self._hover_scroll = QScrollArea()
        self._hover_scroll.setWidgetResizable(True)
        self._hover_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._hover_scroll.setMaximumHeight(_HOVER_MAX_HEIGHT)
        self._hover_scroll.setFrameShape(QFrame.NoFrame)

        self._hover_container = QWidget()
        self._hover_layout = QVBoxLayout(self._hover_container)
        self._hover_layout.setContentsMargins(0, 0, 0, 0)
        self._hover_layout.setSpacing(2)
        self._hover_layout.addStretch()
        self._hover_scroll.setWidget(self._hover_container)
        self._main_layout.addWidget(self._hover_scroll)

        self._main_layout.addWidget(_make_separator())

        # --- Filter (Item 15) ------------------------------------------------
        f_row, self._filter_badge = _make_section_header(
            "Filter",
            on_none=self._clear_filter,
        )
        self._main_layout.addLayout(f_row)

        # Column selector
        self._filter_col_combo = QComboBox()
        self._filter_col_combo.setToolTip("Select column to filter on")
        self._filter_col_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._filter_col_combo.currentIndexChanged.connect(self._on_filter_column_changed)
        self._main_layout.addWidget(self._filter_col_combo)

        # Select All / Deselect All buttons
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

        # Values list (checkboxes)
        self._filter_scroll = QScrollArea()
        self._filter_scroll.setWidgetResizable(True)
        self._filter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._filter_scroll.setMaximumHeight(_FILTER_MAX_HEIGHT)
        self._filter_scroll.setFrameShape(QFrame.NoFrame)

        self._filter_container = QWidget()
        self._filter_layout = QVBoxLayout(self._filter_container)
        self._filter_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_layout.setSpacing(2)
        self._filter_layout.addStretch()
        self._filter_scroll.setWidget(self._filter_container)
        self._main_layout.addWidget(self._filter_scroll)

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
        try:
            self._state.chart_settings_changed.disconnect(self._on_state_x_changed)
        except RuntimeError:
            pass
        try:
            self._state.value_zone_changed.disconnect(self._on_state_value_changed)
        except RuntimeError:
            pass
        try:
            self._state.group_zone_changed.disconnect(self._on_state_group_changed)
        except RuntimeError:
            pass
        try:
            self._state.hover_zone_changed.disconnect(self._on_state_hover_changed)
        except RuntimeError:
            pass
        try:
            self._state.data_cleared.disconnect(self.clear)
        except RuntimeError:
            pass

    # ======================================================================
    # Public API
    # ======================================================================

    def set_columns(self, columns: List[str], engine: "DataEngine") -> None:
        """Populate all sections from a newly-loaded dataset.

        Parameters
        ----------
        columns : list[str]
            Column names from the dataset.
        engine : DataEngine
            Used to determine numeric columns via ``engine.df.dtypes``.
        """
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
            self._rebuild_y_list()
            self._rebuild_group_list()
            self._rebuild_hover_list()
            self._rebuild_filter_combo()

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
            self._clear_group_checks()
            self._clear_hover_checks()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    def sync_from_state(self) -> None:
        """Re-sync the entire UI from the current AppState.

        Useful when a profile is applied or state is changed externally.
        """
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

    def _rebuild_y_list(self) -> None:
        self._clear_y_items()
        for col in self._all_columns:
            if col not in self._numeric_columns:
                continue
            item = _YAxisItemWidget(col)
            item.checked_changed.connect(functools.partial(self._on_y_checked, col))
            item.checked_changed.connect(functools.partial(self._on_y_check_sort, col))
            item.agg_changed.connect(functools.partial(self._on_y_agg_changed, col))
            item.formula_changed.connect(functools.partial(self._on_y_formula_changed, col))
            self._y_items[col] = item
            # Insert before the trailing stretch
            self._y_layout.insertWidget(self._y_layout.count() - 1, item)

    def _rebuild_group_list(self) -> None:
        self._clear_group_checks()
        for col in self._all_columns:
            cb = QCheckBox(col)
            cb.stateChanged.connect(functools.partial(self._on_group_checked, col))
            cb.stateChanged.connect(functools.partial(self._on_group_check_sort, col))
            self._group_checks[col] = cb
            self._group_layout.insertWidget(self._group_layout.count() - 1, cb)

    def _rebuild_hover_list(self) -> None:
        self._clear_hover_checks()
        for col in self._all_columns:
            cb = QCheckBox(col)
            cb.stateChanged.connect(functools.partial(self._on_hover_checked, col))
            cb.stateChanged.connect(functools.partial(self._on_hover_check_sort, col))
            self._hover_checks[col] = cb
            self._hover_layout.insertWidget(self._hover_layout.count() - 1, cb)

    def _rebuild_filter_combo(self) -> None:
        """Rebuild the filter column combo box."""
        self._filter_col_combo.blockSignals(True)
        self._filter_col_combo.clear()
        self._filter_col_combo.addItem("(None)")
        for col in self._all_columns:
            self._filter_col_combo.addItem(col)
        self._filter_col_combo.blockSignals(False)
        self._clear_filter_checks()
        self._update_filter_badge()

    # -- Clear helpers -------------------------------------------------------

    def _clear_y_items(self) -> None:
        for item in self._y_items.values():
            item.setParent(None)
            item.deleteLater()
        self._y_items.clear()

    def _clear_group_checks(self) -> None:
        for cb in self._group_checks.values():
            cb.setParent(None)
            cb.deleteLater()
        self._group_checks.clear()

    def _clear_hover_checks(self) -> None:
        for cb in self._hover_checks.values():
            cb.setParent(None)
            cb.deleteLater()
        self._hover_checks.clear()

    # ======================================================================
    # Internal – state → UI sync
    # ======================================================================

    def _sync_from_state_internal(self) -> None:
        """Sync all sections from current AppState (no guard flags set here)."""
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

        # Y-Axis
        value_names: Dict[str, ValueColumn] = {}
        for vc in self._state.value_columns:
            value_names[vc.name] = vc

        for col, item in self._y_items.items():
            item.block_signals(True)
            if col in value_names:
                vc = value_names[col]
                item.set_checked(True)
                item.set_aggregation(vc.aggregation)
                item.set_formula(vc.formula)
            else:
                item.set_checked(False)
            item.block_signals(False)
            # Manually sync visibility after blockSignals
            item.detail_widget.setVisible(item.is_checked())
            if not item.is_checked():
                item.formula_widget.setVisible(False)
                item.formula_toggle.setChecked(False)
                item.formula_toggle.setText("▶ f(y)")

        # Group By
        group_names = {gc.name for gc in self._state.group_columns}
        for col, cb in self._group_checks.items():
            cb.blockSignals(True)
            cb.setChecked(col in group_names)
            cb.blockSignals(False)

        # Hover
        hover_set = set(self._state.hover_columns)
        for col, cb in self._hover_checks.items():
            cb.blockSignals(True)
            cb.setChecked(col in hover_set)
            cb.blockSignals(False)

        self._update_badges()

    # ======================================================================
    # Badge helpers
    # ======================================================================

    def _update_badges(self) -> None:
        """Update the None/count badge text for Y-Axis, Group By, Hover."""
        # Y-Axis
        n_y = len([w for w in self._y_items.values() if w.is_checked()])
        if self._y_badge:
            self._y_badge.setText(f"{n_y}개" if n_y > 0 else "None")
            self._y_badge.setMaximumWidth(42 if n_y == 0 else 48)
        # Group
        n_g = len([cb for cb in self._group_checks.values() if cb.isChecked()])
        if self._group_badge:
            self._group_badge.setText(f"{n_g}개" if n_g > 0 else "None")
            self._group_badge.setMaximumWidth(42 if n_g == 0 else 48)
        # Hover
        n_h = len([cb for cb in self._hover_checks.values() if cb.isChecked()])
        if self._hover_badge:
            self._hover_badge.setText(f"{n_h}개" if n_h > 0 else "None")
            self._hover_badge.setMaximumWidth(42 if n_h == 0 else 48)

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
            value_names: Dict[str, ValueColumn] = {}
            for vc in self._state.value_columns:
                value_names[vc.name] = vc

            for col, item in self._y_items.items():
                item.block_signals(True)
                if col in value_names:
                    vc = value_names[col]
                    item.set_checked(True)
                    item.set_aggregation(vc.aggregation)
                    item.set_formula(vc.formula)
                else:
                    item.set_checked(False)
                item.block_signals(False)
                item.detail_widget.setVisible(item.is_checked())
                if not item.is_checked():
                    item.formula_widget.setVisible(False)
                    item.formula_toggle.setChecked(False)
                    item.formula_toggle.setText("▶ f(y)")
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
            group_names = {gc.name for gc in self._state.group_columns}
            for col, cb in self._group_checks.items():
                cb.blockSignals(True)
                cb.setChecked(col in group_names)
                cb.blockSignals(False)
            self._update_badges()
        finally:
            self._syncing = False

    @Slot()
    def _on_state_hover_changed(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            hover_set = set(self._state.hover_columns)
            for col, cb in self._hover_checks.items():
                cb.blockSignals(True)
                cb.setChecked(col in hover_set)
                cb.blockSignals(False)
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

    def _on_y_checked(self, column_name: str, _col_from_signal: str, checked: bool) -> None:
        """Handle Y-axis checkbox toggle.

        Using functools.partial, the first arg is the partial-bound column_name,
        followed by the signal's own (column_name, checked) args.
        """
        if self._syncing:
            return
        self._syncing = True
        try:
            if checked:
                # Only add if not already present
                if not any(vc.name == column_name for vc in self._state.value_columns):
                    self._state.add_value_column(column_name)
            else:
                # Find and remove by name
                for i, vc in enumerate(self._state.value_columns):
                    if vc.name == column_name:
                        self._state.remove_value_column(i)
                        break
        finally:
            self._syncing = False

    @Slot(int)
    def _on_global_agg_changed(self, _index: int) -> None:
        """Group By 섹션의 전역 Aggregation 변경 → 모든 value column에 적용"""
        if self._syncing:
            return
        agg = self._agg_combo.currentData()
        if agg is None:
            return
        self._syncing = True
        try:
            for i, vc in enumerate(self._state.value_columns):
                self._state.update_value_column(i, aggregation=agg)
        finally:
            self._syncing = False

    @Slot(int)
    def _on_global_agg2_changed(self, _index: int) -> None:
        """Secondary aggregation level – stored locally for now."""
        if self._syncing:
            return
        agg = self._agg_combo_2.currentData()
        if agg is not None:
            self._secondary_agg = agg

    def _on_y_agg_changed(self, column_name: str, _col_from_signal: str, agg: AggregationType) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            for i, vc in enumerate(self._state.value_columns):
                if vc.name == column_name:
                    self._state.update_value_column(i, aggregation=agg)
                    break
        finally:
            self._syncing = False

    def _on_y_formula_changed(self, column_name: str, _col_from_signal: str, formula: str) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            for i, vc in enumerate(self._state.value_columns):
                if vc.name == column_name:
                    self._state.update_value_column(i, formula=formula)
                    break
        finally:
            self._syncing = False

    # -- Group By ------------------------------------------------------------

    def _on_group_checked(self, column_name: str, state: int) -> None:
        """Handle Group By checkbox toggle."""
        if self._syncing:
            return
        self._syncing = True
        try:
            checked = state == Qt.Checked.value if hasattr(Qt.Checked, 'value') else state == int(Qt.Checked)
            if checked:
                self._state.add_group_column(column_name)
            else:
                self._state.remove_group_column(column_name)
        finally:
            self._syncing = False

    # -- Hover ---------------------------------------------------------------

    def _on_hover_checked(self, column_name: str, state: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            checked = state == Qt.Checked.value if hasattr(Qt.Checked, 'value') else state == int(Qt.Checked)
            if checked:
                self._state.add_hover_column(column_name)
            else:
                self._state.remove_hover_column(column_name)
        finally:
            self._syncing = False

    # ======================================================================
    # Bulk actions – [All] / [None]
    # ======================================================================

    @Slot()
    def _select_none_y(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            for col, item in self._y_items.items():
                item.block_signals(True)
                item.set_checked(False)
                item.block_signals(False)
                item.detail_widget.setVisible(False)
                item.formula_widget.setVisible(False)
                item.formula_toggle.setChecked(False)
                item.formula_toggle.setText("▶ f(y)")
            self._state.clear_value_zone()
            self._update_badges()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    def _select_none_group(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            for cb in self._group_checks.values():
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
            self._state.clear_group_zone()
            self._update_badges()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    def _select_none_hover(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            for cb in self._hover_checks.values():
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
            self._state.clear_hover_columns()
            self._update_badges()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    # ==================================================================
    # Filter section (Item 15)
    # ==================================================================

    def _on_filter_column_changed(self, index: int) -> None:
        """Load unique values when filter column changes."""
        self._clear_filter_checks()
        col = self._filter_col_combo.currentText()
        if not col or col == "(None)" or self._filter_engine is None:
            self._update_filter_badge()
            return

        try:
            df = self._filter_engine.df
            if df is None or col not in df.columns:
                return
            # Get unique values (limit to 500)
            unique_vals = df[col].drop_nulls().unique().sort().to_list()[:500]
        except Exception:
            unique_vals = []

        for val in unique_vals:
            label = str(val) if val is not None else "(null)"
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_filter_value_toggled)
            self._filter_checks[label] = cb
            self._filter_layout.insertWidget(self._filter_layout.count() - 1, cb)

        self._update_filter_badge()

    def _on_filter_value_toggled(self, _state: int) -> None:
        """Emit filter_changed with current filter selections."""
        if self._syncing:
            return
        self._emit_filter_signal()

    def _emit_filter_signal(self) -> None:
        col = self._filter_col_combo.currentText()
        if not col or col == "(None)":
            self.filter_changed.emit({})
            return
        selected = [label for label, cb in self._filter_checks.items() if cb.isChecked()]
        if len(selected) == len(self._filter_checks):
            # All selected → no filter
            self.filter_changed.emit({})
        else:
            self.filter_changed.emit({col: selected})
        self._update_filter_badge()

    def _filter_select_all(self) -> None:
        for cb in self._filter_checks.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self._emit_filter_signal()

    def _filter_deselect_all(self) -> None:
        for cb in self._filter_checks.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._emit_filter_signal()

    def _clear_filter(self) -> None:
        """Reset filter column selection and clear all checks."""
        self._clear_filter_checks()
        self._filter_col_combo.blockSignals(True)
        if self._filter_col_combo.count() > 0:
            self._filter_col_combo.setCurrentIndex(0)
        self._filter_col_combo.blockSignals(False)
        self.filter_changed.emit({})
        self._update_filter_badge()

    def _clear_filter_checks(self) -> None:
        for cb in self._filter_checks.values():
            cb.setParent(None)
            cb.deleteLater()
        self._filter_checks.clear()

    def _update_filter_badge(self) -> None:
        n_checked = sum(1 for cb in self._filter_checks.values() if cb.isChecked())
        total = len(self._filter_checks)
        if self._filter_badge:
            if total == 0:
                self._filter_badge.setText("None")
            elif n_checked == total:
                self._filter_badge.setText("All")
            else:
                self._filter_badge.setText(f"{n_checked}/{total}")

    def get_filter_selections(self) -> Dict[str, list]:
        """Return current filter as {column: [selected_values]}.

        Returns empty dict when no filter is active.
        """
        col = self._filter_col_combo.currentText()
        if not col or col == "(None)" or not self._filter_checks:
            return {}
        selected = [label for label, cb in self._filter_checks.items() if cb.isChecked()]
        if len(selected) == len(self._filter_checks):
            return {}
        return {col: selected}

    # ==================================================================
    # Column search / filter
    # ==================================================================

    # ==================================================================
    # Sort checked items to top
    # ==================================================================

    def _sort_checked_to_top(self, layout: 'QVBoxLayout', items_dict: dict, key_fn=None) -> None:
        """Move checked items to the top of *layout*.

        Works for both _YAxisItemWidget (uses .is_checked()) and QCheckBox
        (uses .isChecked()).  The trailing stretch item is preserved at the end.

        Parameters
        ----------
        layout : QVBoxLayout
            The layout containing the items and a trailing stretch.
        items_dict : dict
            Mapping of column_name → widget.
        key_fn : callable, optional
            Function ``widget → bool`` returning checked state.
            Defaults to ``widget.isChecked()`` / ``widget.is_checked()``.
        """
        if not items_dict:
            return

        def _is_checked(w):
            if key_fn is not None:
                return key_fn(w)
            if hasattr(w, 'is_checked'):
                return w.is_checked()
            if hasattr(w, 'isChecked'):
                return w.isChecked()
            return False

        # Collect widgets in desired order: checked first, then unchecked
        checked = []
        unchecked = []
        for col in self._all_columns:
            w = items_dict.get(col)
            if w is None:
                continue
            if _is_checked(w):
                checked.append(w)
            else:
                unchecked.append(w)

        ordered = checked + unchecked

        # Remove all widgets from layout (except trailing stretch)
        for w in ordered:
            layout.removeWidget(w)

        # Re-insert in order before the stretch
        for i, w in enumerate(ordered):
            layout.insertWidget(i, w)

    def _on_y_check_sort(self, _col: str, _checked: bool) -> None:
        """Re-sort Y-axis list after check state change."""
        if self._syncing:
            return
        self._sort_checked_to_top(self._y_layout, self._y_items)

    def _on_group_check_sort(self, _col: str, _state: int) -> None:
        """Re-sort Group By list after check state change."""
        if self._syncing:
            return
        self._sort_checked_to_top(self._group_layout, self._group_checks)

    def _on_hover_check_sort(self, _col: str, _state: int) -> None:
        """Re-sort Hover list after check state change."""
        if self._syncing:
            return
        self._sort_checked_to_top(self._hover_layout, self._hover_checks)

    @Slot(str)
    def _filter_y_items(self, text: str) -> None:
        """Y-Axis 체크박스 목록 필터링"""
        query = text.strip().lower()
        for col, item in self._y_items.items():
            item.setVisible(query == "" or query in col.lower())

    @Slot(str)
    def _filter_group_items(self, text: str) -> None:
        """Group By 체크박스 목록 필터링"""
        query = text.strip().lower()
        for col, cb in self._group_checks.items():
            cb.setVisible(query == "" or query in col.lower())

    @Slot(str)
    def _filter_hover_items(self, text: str) -> None:
        """Hover 체크박스 목록 필터링"""
        query = text.strip().lower()
        for col, cb in self._hover_checks.items():
            cb.setVisible(query == "" or query in col.lower())
