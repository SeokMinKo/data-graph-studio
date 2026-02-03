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

_YAXIS_MAX_HEIGHT = 200
_GROUP_MAX_HEIGHT = 120
_HOVER_MAX_HEIGHT = 120


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
    on_all: object = None,
    on_none: object = None,
) -> QHBoxLayout:
    """Return an HBoxLayout with *title* label and [All] / [None] buttons."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)

    label = QLabel(title)
    label.setObjectName("sectionHeader")
    row.addWidget(label)
    row.addStretch()

    if on_all is not None:
        btn_all = QPushButton("All")
        btn_all.setObjectName("smallButton")
        btn_all.setFixedHeight(20)
        btn_all.setMaximumWidth(36)
        btn_all.clicked.connect(on_all)
        row.addWidget(btn_all)

    if on_none is not None:
        btn_none = QPushButton("None")
        btn_none.setObjectName("smallButton")
        btn_none.setFixedHeight(20)
        btn_none.setMaximumWidth(42)
        btn_none.clicked.connect(on_none)
        row.addWidget(btn_none)

    return row


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
    """Single Y-Axis column entry with checkbox, agg combo, formula toggle."""

    checked_changed = Signal(str, bool)       # column_name, checked
    agg_changed = Signal(str, object)          # column_name, AggregationType
    formula_changed = Signal(str, str)         # column_name, formula_text

    def __init__(self, column_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.column_name = column_name
        self._setup_ui()

    # -- UI ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Row 1 – checkbox
        self.checkbox = QCheckBox(self.column_name)
        self.checkbox.stateChanged.connect(self._on_check_state)
        layout.addWidget(self.checkbox)

        # Row 2 – agg combo + formula toggle (hidden by default)
        self.detail_widget = QWidget()
        detail_layout = QHBoxLayout(self.detail_widget)
        detail_layout.setContentsMargins(20, 0, 0, 0)  # indent under checkbox
        detail_layout.setSpacing(4)

        self.agg_combo = QComboBox()
        self.agg_combo.setFixedHeight(22)
        self.agg_combo.setMinimumWidth(60)
        self.agg_combo.setMaximumWidth(80)
        for label, agg in _AGG_ITEMS:
            self.agg_combo.addItem(label, agg)
        self.agg_combo.currentIndexChanged.connect(self._on_agg_changed)
        detail_layout.addWidget(self.agg_combo)

        self.formula_toggle = QToolButton()
        self.formula_toggle.setText("▶ f(y)")
        self.formula_toggle.setCheckable(True)
        self.formula_toggle.setChecked(False)
        self.formula_toggle.setFixedHeight(22)
        self.formula_toggle.clicked.connect(self._on_formula_toggled)
        detail_layout.addWidget(self.formula_toggle)

        detail_layout.addStretch()
        layout.addWidget(self.detail_widget)
        self.detail_widget.setVisible(False)

        # Row 3 – formula input (hidden by default)
        self.formula_widget = QWidget()
        formula_layout = QHBoxLayout(self.formula_widget)
        formula_layout.setContentsMargins(20, 0, 0, 0)
        formula_layout.setSpacing(4)

        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText("f(y)=...  e.g. y*2, LOG(y)")
        self.formula_edit.setFixedHeight(22)
        self.formula_edit.editingFinished.connect(self._on_formula_finished)
        formula_layout.addWidget(self.formula_edit)
        layout.addWidget(self.formula_widget)
        self.formula_widget.setVisible(False)

    # -- Slots ---------------------------------------------------------------

    def _on_check_state(self, state: int) -> None:
        checked = state == Qt.Checked.value if hasattr(Qt.Checked, 'value') else state == int(Qt.Checked)
        self.detail_widget.setVisible(checked)
        if not checked:
            self.formula_widget.setVisible(False)
            self.formula_toggle.setChecked(False)
            self.formula_toggle.setText("▶ f(y)")
        self.checked_changed.emit(self.column_name, checked)

    def _on_agg_changed(self, _index: int) -> None:
        agg = self.agg_combo.currentData()
        if agg is not None:
            self.agg_changed.emit(self.column_name, agg)

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
        for i in range(self.agg_combo.count()):
            if self.agg_combo.itemData(i) is agg:
                self.agg_combo.setCurrentIndex(i)
                return

    def set_formula(self, formula: str) -> None:
        self.formula_edit.setText(formula)
        if formula:
            self.formula_toggle.setChecked(True)
            self.formula_widget.setVisible(True)
            self.formula_toggle.setText("▼ f(y)")

    def block_signals(self, block: bool) -> None:
        """Block / unblock all child signals."""
        self.checkbox.blockSignals(block)
        self.agg_combo.blockSignals(block)
        self.formula_edit.blockSignals(block)


# ---------------------------------------------------------------------------
# DataTab
# ---------------------------------------------------------------------------

class DataTab(QWidget):
    """Chart Options → Data tab.

    Provides combo-box / checkbox UI for X-Axis, Y-Axis (Values),
    Group By, and Hover column configuration.

    Parameters
    ----------
    state : AppState
        The shared application state singleton.
    """

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
        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(6, 6, 6, 6)
        self._main_layout.setSpacing(8)

        # --- X-Axis ---------------------------------------------------------
        x_header = QLabel("X-Axis")
        x_header.setObjectName("sectionHeader")
        self._main_layout.addWidget(x_header)

        self._x_combo = QComboBox()
        self._x_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._x_combo.currentIndexChanged.connect(self._on_x_combo_changed)
        self._main_layout.addWidget(self._x_combo)

        self._main_layout.addWidget(_make_separator())

        # --- Y-Axis (Values) ------------------------------------------------
        self._main_layout.addLayout(
            _make_section_header(
                "Y-Axis (Values)",
                on_all=self._select_all_y,
                on_none=self._select_none_y,
            )
        )

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
        self._main_layout.addLayout(
            _make_section_header(
                "Group By",
                on_all=self._select_all_group,
                on_none=self._select_none_group,
            )
        )

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

        self._main_layout.addWidget(_make_separator())

        # --- Hover Columns --------------------------------------------------
        self._main_layout.addLayout(
            _make_section_header(
                "Hover Columns",
                on_all=self._select_all_hover,
                on_none=self._select_none_hover,
            )
        )

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

            # Determine numeric columns
            if engine.df is not None:
                for col, dtype in zip(engine.df.columns, engine.df.dtypes):
                    if _is_numeric_dtype(str(dtype)):
                        self._numeric_columns.add(col)

            self._rebuild_x_combo()
            self._rebuild_y_list()
            self._rebuild_group_list()
            self._rebuild_hover_list()

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
            self._group_checks[col] = cb
            self._group_layout.insertWidget(self._group_layout.count() - 1, cb)

    def _rebuild_hover_list(self) -> None:
        self._clear_hover_checks()
        for col in self._all_columns:
            cb = QCheckBox(col)
            cb.stateChanged.connect(functools.partial(self._on_hover_checked, col))
            self._hover_checks[col] = cb
            self._hover_layout.insertWidget(self._hover_layout.count() - 1, cb)

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
    def _select_all_y(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            self._state.begin_batch_update()
            for col, item in self._y_items.items():
                if not item.is_checked():
                    item.block_signals(True)
                    item.set_checked(True)
                    item.block_signals(False)
                    item.detail_widget.setVisible(True)
                    if not any(vc.name == col for vc in self._state.value_columns):
                        self._state.add_value_column(col)
            self._state.end_batch_update()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

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
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    @Slot()
    def _select_all_group(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            self._state.begin_batch_update()
            for col, cb in self._group_checks.items():
                if not cb.isChecked():
                    cb.blockSignals(True)
                    cb.setChecked(True)
                    cb.blockSignals(False)
                    if not any(gc.name == col for gc in self._state.group_columns):
                        self._state.add_group_column(col)
            self._state.end_batch_update()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    @Slot()
    def _select_none_group(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            for cb in self._group_checks.values():
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
            self._state.clear_group_zone()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    @Slot()
    def _select_all_hover(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            self._state.begin_batch_update()
            for col, cb in self._hover_checks.items():
                if not cb.isChecked():
                    cb.blockSignals(True)
                    cb.setChecked(True)
                    cb.blockSignals(False)
                    if col not in self._state.hover_columns:
                        self._state.add_hover_column(col)
            self._state.end_batch_update()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False

    @Slot()
    def _select_none_hover(self) -> None:
        self._syncing = True
        self.setUpdatesEnabled(False)
        try:
            for cb in self._hover_checks.values():
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
            self._state.clear_hover_columns()
        finally:
            self.setUpdatesEnabled(True)
            self._syncing = False
