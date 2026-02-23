"""
Data Tab - X/Y/Group/Hover configuration for Chart Options panel.

Search + ListBox UI pattern for Y-Axis, Group By, Hover, and Filter sections.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Set, TYPE_CHECKING


from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QPushButton,
    QScrollArea, QSizePolicy, QCompleter,
)
from PySide6.QtCore import Qt, Signal, Slot, QStringListModel

from ...core.state import AppState
from ..adapters.app_state_adapter import AppStateAdapter
from ._data_tab_widgets import (  # noqa: F401  (re-exported for tests and backward compat)
    _INDEX_SENTINEL,
    _AGG_ITEMS,
    _YAXIS_MAX_HEIGHT,
    _GROUP_MAX_HEIGHT,
    _HOVER_MAX_HEIGHT,
    _FILTER_MAX_HEIGHT,
    _make_separator,
    _make_section_header,
    _is_numeric_dtype,
    _SearchableColumnPicker,
    _ListBoxItem,
    _ColumnListBox,
    _YAxisListItem,
    _YAxisItemWidget,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ...core.data_engine import DataEngine

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
        self._state_adapter = AppStateAdapter(state, parent=self)

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

        # Column selector (searchable combo)
        self._filter_col_combo = QComboBox()
        self._filter_col_combo.setEditable(True)
        self._filter_col_combo.setInsertPolicy(QComboBox.NoInsert)
        self._filter_col_combo.setToolTip("Select column to filter on (type to search)")
        self._filter_col_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._filter_col_combo.setMinimumHeight(28)
        if self._filter_col_combo.lineEdit():
            self._filter_col_combo.lineEdit().setPlaceholderText("🔍 Search columns...")
        # Contains-match completer
        self._filter_col_completer = QCompleter()
        self._filter_col_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._filter_col_completer.setFilterMode(Qt.MatchContains)
        self._filter_col_completer.setCompletionMode(QCompleter.PopupCompletion)
        self._filter_col_model = QStringListModel()
        self._filter_col_completer.setModel(self._filter_col_model)
        self._filter_col_combo.setCompleter(self._filter_col_completer)
        self._filter_col_combo.currentIndexChanged.connect(self._on_filter_column_changed)
        self._filter_col_completer.activated.connect(self._on_filter_col_completer_activated)
        self._main_layout.addWidget(self._filter_col_combo)

        # Value selector (searchable combo)
        self._filter_val_combo = QComboBox()
        self._filter_val_combo.setEditable(True)
        self._filter_val_combo.setInsertPolicy(QComboBox.NoInsert)
        self._filter_val_combo.setToolTip("Select value to add as filter (type to search)")
        self._filter_val_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._filter_val_combo.setMinimumHeight(28)
        if self._filter_val_combo.lineEdit():
            self._filter_val_combo.lineEdit().setPlaceholderText("🔍 Search values...")
        # Contains-match completer
        self._filter_val_completer = QCompleter()
        self._filter_val_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._filter_val_completer.setFilterMode(Qt.MatchContains)
        self._filter_val_completer.setCompletionMode(QCompleter.PopupCompletion)
        self._filter_val_model = QStringListModel()
        self._filter_val_completer.setModel(self._filter_val_model)
        self._filter_val_combo.setCompleter(self._filter_val_completer)
        self._filter_val_combo.activated.connect(self._on_filter_value_selected)
        self._filter_val_completer.activated.connect(self._on_filter_val_completer_activated)
        self._main_layout.addWidget(self._filter_val_combo)

        # [All] [None] buttons
        filter_btn_row = QHBoxLayout()
        filter_btn_row.setSpacing(4)
        self._filter_select_all_btn = QPushButton("All")
        self._filter_select_all_btn.setObjectName("smallButton")
        self._filter_select_all_btn.setFixedHeight(20)
        self._filter_select_all_btn.setToolTip("Select all values for the current filter column")
        self._filter_select_all_btn.clicked.connect(self._filter_select_all)
        filter_btn_row.addWidget(self._filter_select_all_btn)
        self._filter_deselect_all_btn = QPushButton("None")
        self._filter_deselect_all_btn.setObjectName("smallButton")
        self._filter_deselect_all_btn.setFixedHeight(20)
        self._filter_deselect_all_btn.setToolTip("Deselect all values for the current filter column")
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
        self._group_picker.setToolTip("Type to search for columns to group by. Press Enter to add.")
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
        self._y_picker.setToolTip("Type to search for numeric columns for Y-axis. Press Enter to add.")
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
        self._hover_picker.setToolTip("Type to search for columns to show on hover. Press Enter to add.")
        self._hover_picker.column_selected.connect(self._on_hover_column_selected)
        self._main_layout.addWidget(self._hover_picker)

        self._hover_listbox = _ColumnListBox(max_height=_HOVER_MAX_HEIGHT)
        self._hover_listbox.item_removed.connect(self._on_hover_item_removed)
        self._main_layout.addWidget(self._hover_listbox)

        # Bottom stretch
        self._main_layout.addStretch()

        # ------------------------------------------------------------------
        # Explicit tab order (top → bottom through the panel)
        # Filter section
        QWidget.setTabOrder(self._filter_col_combo, self._filter_val_combo)
        QWidget.setTabOrder(self._filter_val_combo, self._filter_select_all_btn)
        QWidget.setTabOrder(self._filter_select_all_btn, self._filter_deselect_all_btn)
        # Group By section
        QWidget.setTabOrder(self._filter_deselect_all_btn, self._group_picker._combo)
        # X-Axis
        QWidget.setTabOrder(self._group_picker._combo, self._x_combo)
        # Y-Axis
        QWidget.setTabOrder(self._x_combo, self._y_picker._combo)
        # Hover
        QWidget.setTabOrder(self._y_picker._combo, self._hover_picker._combo)
        # ------------------------------------------------------------------

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ======================================================================
    # State signal connections
    # ======================================================================

    def _connect_state_signals(self) -> None:
        self._state_adapter.chart_settings_changed.connect(self._on_state_x_changed)
        self._state_adapter.value_zone_changed.connect(self._on_state_value_changed)
        self._state_adapter.group_zone_changed.connect(self._on_state_group_changed)
        self._state_adapter.hover_zone_changed.connect(self._on_state_hover_changed)
        self._state_adapter.data_cleared.connect(self.clear)

    def _disconnect_state_signals(self) -> None:
        for sig, slot in [
            (self._state_adapter.chart_settings_changed, self._on_state_x_changed),
            (self._state_adapter.value_zone_changed, self._on_state_value_changed),
            (self._state_adapter.group_zone_changed, self._on_state_group_changed),
            (self._state_adapter.hover_zone_changed, self._on_state_hover_changed),
            (self._state_adapter.data_cleared, self.clear),
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
        # Update completer model
        self._filter_col_model.setStringList(list(self._all_columns))

        self._filter_val_combo.blockSignals(True)
        self._filter_val_combo.clear()
        self._filter_val_combo.blockSignals(False)
        self._filter_val_model.setStringList([])
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
            logger.warning("data_tab.load_filter_unique_vals.error", exc_info=True)
            unique_vals = []

        self._filter_unique_vals = unique_vals

        # Exclude already-selected values for this column
        already_selected = set(self._filter_data.get(col, []))
        visible_vals = [val for val in unique_vals if val not in already_selected]
        self._filter_val_combo.blockSignals(True)
        for val in visible_vals:
            self._filter_val_combo.addItem(val)
        self._filter_val_combo.setCurrentIndex(-1)
        if self._filter_val_combo.lineEdit():
            self._filter_val_combo.lineEdit().clear()
        self._filter_val_combo.blockSignals(False)
        # Update completer model
        self._filter_val_model.setStringList(visible_vals)

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

    def _on_filter_col_completer_activated(self, text: str) -> None:
        """Handle filter column selection via completer (typed search)."""
        idx = self._filter_col_combo.findText(text)
        if idx >= 0:
            self._filter_col_combo.setCurrentIndex(idx)
            # currentIndexChanged will fire and call _on_filter_column_changed

    def _on_filter_val_completer_activated(self, text: str) -> None:
        """Handle filter value selection via completer (typed search)."""
        col = self._filter_col_combo.currentText()
        if not text or not col:
            return
        # Reuse the same logic as _on_filter_value_selected
        if col not in self._filter_data:
            self._filter_data[col] = []
        if text not in self._filter_data[col]:
            self._filter_data[col].append(text)
            display = f"{col} = {text}"
            self._filter_listbox.add_item(display)
            idx = self._filter_val_combo.findText(text)
            if idx >= 0:
                self._filter_val_combo.removeItem(idx)
            # Update completer model
            current_vals = self._filter_val_model.stringList()
            if text in current_vals:
                current_vals.remove(text)
                self._filter_val_model.setStringList(current_vals)
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
