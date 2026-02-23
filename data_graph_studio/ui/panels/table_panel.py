"""
Table Panel - 테이블 뷰 + X Zone + Group Zone + Value Zone
"""

from typing import Optional, List
import logging
import polars as pl

logger = logging.getLogger(__name__)

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QTableView, QLineEdit, QComboBox, QPushButton,
    QApplication,
)
from PySide6.QtCore import QTimer
from PySide6.QtCore import (
    Qt, Signal, QItemSelection, QItemSelectionModel,
)
from PySide6.QtGui import QDropEvent, QDragEnterEvent

from ...core.state import AppState, AggregationType
from ...core.data_engine import DataEngine
from ..adapters.app_state_adapter import AppStateAdapter
from .grouped_table_model import GroupedTableModel
from .conditional_formatting import ConditionalFormatDialog
from ._table_search_mixin import _TableSearchMixin
from ._table_focus_mixin import _TableFocusMixin
from ._table_window_mixin import _TableWindowMixin
from ._table_column_mixin import _TableColumnMixin
from ._polars_table_model import PolarsTableModel
from ._chip_widgets import (
    DragHandleLabel, ChipWidget, ValueChipWidget, ChipListWidget,
    _parse_drag_payload, _build_drag_payload, _remove_from_source,
)
from ._zone_widgets import XAxisZone, GroupZone, ValueZone, HoverZone
from ._data_table_view import DataTableView
from ._table_bars import FilterBar, HiddenColumnsBar
from ._pivot_table_dialog import PivotTableDialog


# ==================== Table Panel ====================

class TablePanel(_TableColumnMixin, _TableWindowMixin, _TableFocusMixin, _TableSearchMixin, QWidget):
    """
    Table Panel - Data table with full width (zones removed to Data tab in Chart Options).

    구조:
    ┌─────────────────────────────────────────────────────────┐
    │                      Data Table                         │
    │                  (전체 너비 활용)                          │
    └─────────────────────────────────────────────────────────┘
    """

    file_dropped = Signal(str)
    window_changed = Signal()

    def __init__(self, state: AppState, engine: DataEngine, graph_panel=None):
        super().__init__()
        self.state = state
        self._state_adapter = AppStateAdapter(state, parent=self)
        self.engine = engine
        self.graph_panel = graph_panel

        self.setAcceptDrops(True)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Table area (full width - zones removed to Data tab)
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(4, 4, 4, 4)
        table_layout.setSpacing(4)

        # Filter bar (above search)
        self.filter_bar = FilterBar(self.state)
        self.filter_bar.filter_removed.connect(self._on_filter_removed)
        self.filter_bar.clear_all.connect(self._on_clear_filters)
        table_layout.addWidget(self.filter_bar)

        # Hidden columns bar
        self.hidden_bar = HiddenColumnsBar(self.state)
        self.hidden_bar.show_column.connect(self._on_show_column)
        self.hidden_bar.show_all.connect(self._on_show_all_columns)
        table_layout.addWidget(self.hidden_bar)

        # Search bar with debouncing, clear button, and result count
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 6)
        search_layout.setSpacing(8)

        # Search input container (for clear button overlay)
        search_container = QFrame()
        search_container_layout = QHBoxLayout(search_container)
        search_container_layout.setContentsMargins(0, 0, 0, 0)
        search_container_layout.setSpacing(0)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search data...")
        self.search_input.setObjectName("searchInput")
        search_container_layout.addWidget(self.search_input)

        # Clear button (inside search input)
        self.search_clear_btn = QPushButton("×")
        self.search_clear_btn.setFixedSize(20, 20)
        self.search_clear_btn.setObjectName("searchClearBtn")
        self.search_clear_btn.setToolTip("Clear search")
        self.search_clear_btn.clicked.connect(self._clear_search)
        self.search_clear_btn.hide()  # Hidden when empty
        search_container_layout.addWidget(self.search_clear_btn)

        search_layout.addWidget(search_container, 1)

        # Search result count label
        self.search_result_label = QLabel("")
        self.search_result_label.setObjectName("searchResultLabel")
        self.search_result_label.setMinimumWidth(80)
        search_layout.addWidget(self.search_result_label)

        table_layout.addLayout(search_layout)

        # Search debounce timer (300ms)
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(300)
        self._search_debounce_timer.timeout.connect(self._execute_search)
        self._pending_search_text = ""

        # Connect search input to debounced search
        self.search_input.textChanged.connect(self._on_search_text_changed)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.expand_btn = QPushButton("▼ Expand")
        self.expand_btn.setObjectName("smallButton")
        self.expand_btn.setToolTip("Expand all groups")
        self.expand_btn.clicked.connect(self._expand_all)
        toolbar.addWidget(self.expand_btn)

        self.collapse_btn = QPushButton("▶ Collapse")
        self.collapse_btn.setObjectName("smallButton")
        self.collapse_btn.setToolTip("Collapse all groups")
        self.collapse_btn.clicked.connect(self._collapse_all)
        toolbar.addWidget(self.collapse_btn)

        # Table view mode
        toolbar.addWidget(QLabel("Table:"))
        self.table_view_mode_combo = QComboBox()
        self.table_view_mode_combo.setMinimumWidth(120)
        self.table_view_mode_combo.setMaximumWidth(180)
        self.table_view_mode_combo.addItem("Grouped", "grouped")
        self.table_view_mode_combo.addItem("Rows (pre-group)", "pre_group")
        self.table_view_mode_combo.addItem("Source Raw", "source_raw")
        self.table_view_mode_combo.setToolTip(
            "Choose how the table is displayed when Group By is configured.\n"
            "- Grouped: hierarchical grouped table (current behavior)\n"
            "- Rows (pre-group): show row-level data before grouping\n"
            "- Source Raw: show the dataset as-loaded (ignore table filters/marking)"
        )
        self.table_view_mode_combo.currentIndexChanged.connect(self._on_table_view_mode_changed)
        toolbar.addWidget(self.table_view_mode_combo)

        # Limit to Marking toggle button
        self.limit_marking_btn = QPushButton("🔗 Limit to Marking")
        self.limit_marking_btn.setCheckable(True)
        self.limit_marking_btn.setChecked(False)
        self.limit_marking_btn.setObjectName("limitMarkingBtn")
        self.limit_marking_btn.setToolTip("Show only marked/selected rows in table")
        self.limit_marking_btn.clicked.connect(self._on_limit_marking_toggled)
        toolbar.addWidget(self.limit_marking_btn)

        # Focus navigation
        self.focus_btn = QPushButton("🔍 Focus")
        self.focus_btn.setCheckable(True)
        self.focus_btn.setChecked(False)
        self.focus_btn.setObjectName("focusBtn")
        self.focus_btn.setToolTip("Auto-scroll to selected rows and highlight them")
        self.focus_btn.clicked.connect(self._on_focus_toggled)
        toolbar.addWidget(self.focus_btn)

        self.focus_prev_btn = QPushButton("<")
        self.focus_prev_btn.setFixedWidth(30)
        self.focus_prev_btn.setToolTip("Previous selected row")
        self.focus_prev_btn.setEnabled(False)
        self.focus_prev_btn.clicked.connect(self._on_focus_prev)
        toolbar.addWidget(self.focus_prev_btn)

        self.focus_label = QLabel("")
        self.focus_label.setFixedWidth(50)
        self.focus_label.setAlignment(Qt.AlignCenter)
        self.focus_label.setStyleSheet("font-size: 10px;")
        toolbar.addWidget(self.focus_label)

        self.focus_next_btn = QPushButton(">")
        self.focus_next_btn.setFixedWidth(30)
        self.focus_next_btn.setToolTip("Next selected row")
        self.focus_next_btn.setEnabled(False)
        self.focus_next_btn.clicked.connect(self._on_focus_next)
        toolbar.addWidget(self.focus_next_btn)

        # Focus internal state
        self._focus_enabled = False
        self._focus_sorted_rows: List[int] = []
        self._focus_current_idx = 0

        # GroupBy comboboxes (최대 2개)
        toolbar.addWidget(QLabel("Group:"))

        self.group_combo1 = QComboBox()
        self.group_combo1.setMinimumWidth(100)
        self.group_combo1.setMaximumWidth(160)
        self.group_combo1.setToolTip("Group By column 1")
        self.group_combo1.currentTextChanged.connect(self._on_group_combo_changed)
        toolbar.addWidget(self.group_combo1)

        self.group_combo2 = QComboBox()
        self.group_combo2.setMinimumWidth(100)
        self.group_combo2.setMaximumWidth(160)
        self.group_combo2.setToolTip("Group By column 2")
        self.group_combo2.currentTextChanged.connect(self._on_group_combo_changed)
        toolbar.addWidget(self.group_combo2)

        # Aggregation combobox
        toolbar.addWidget(QLabel("Agg:"))

        self.agg_combo = QComboBox()
        self.agg_combo.setMinimumWidth(80)
        self.agg_combo.setMaximumWidth(120)
        self.agg_combo.setToolTip("Aggregation function")
        from ...core.state import AggregationType
        for agg in AggregationType:
            self.agg_combo.addItem(agg.value.capitalize(), agg.value)
        self.agg_combo.setCurrentText("Sum")
        self.agg_combo.currentTextChanged.connect(self._on_agg_combo_changed)
        toolbar.addWidget(self.agg_combo)

        # Window controls (for large datasets)
        self.window_widget = QWidget()
        window_layout = QHBoxLayout(self.window_widget)
        window_layout.setContentsMargins(8, 0, 8, 0)
        window_layout.setSpacing(6)

        from PySide6.QtWidgets import QSlider
        self.window_prev_btn = QPushButton("◀")
        self.window_prev_btn.setFixedWidth(24)
        self.window_prev_btn.setToolTip("Previous window")
        self.window_prev_btn.clicked.connect(self._on_window_prev)
        window_layout.addWidget(self.window_prev_btn)

        self.window_slider = QSlider(Qt.Horizontal)
        self.window_slider.setFixedWidth(160)
        self.window_slider.setMinimum(0)
        self.window_slider.setMaximum(0)
        self.window_slider.setSingleStep(1000)
        self.window_slider.setPageStep(10000)
        self.window_slider.valueChanged.connect(self._on_window_slider_changed)
        self.window_slider.sliderReleased.connect(self._on_window_slider_released)
        window_layout.addWidget(self.window_slider)

        self.window_size_combo = QComboBox()
        self.window_size_combo.addItems(["50k", "100k", "200k", "500k"])
        self.window_size_combo.setCurrentText("200k")
        self.window_size_combo.setToolTip("Window size")
        self.window_size_combo.currentTextChanged.connect(self._on_window_size_changed)
        window_layout.addWidget(self.window_size_combo)

        self.window_next_btn = QPushButton("▶")
        self.window_next_btn.setFixedWidth(24)
        self.window_next_btn.setToolTip("Next window")
        self.window_next_btn.clicked.connect(self._on_window_next)
        window_layout.addWidget(self.window_next_btn)

        self.window_label = QLabel("")
        self.window_label.setObjectName("windowLabel")
        window_layout.addWidget(self.window_label)

        self._window_debounce = QTimer(self)
        self._window_debounce.setSingleShot(True)
        self._window_debounce.setInterval(250)
        self._window_debounce.timeout.connect(self._apply_window_debounced)

        self.window_widget.setVisible(False)
        toolbar.addWidget(self.window_widget)

        # F2: Edit mode toggle
        self.edit_toggle_btn = QPushButton("✏️ Edit")
        self.edit_toggle_btn.setCheckable(True)
        self.edit_toggle_btn.setChecked(False)
        self.edit_toggle_btn.setObjectName("smallButton")
        self.edit_toggle_btn.setToolTip("Toggle inline cell editing")
        self.edit_toggle_btn.clicked.connect(self._on_edit_toggle)
        toolbar.addWidget(self.edit_toggle_btn)

        toolbar.addStretch()

        self.group_info_label = QLabel("")
        self.group_info_label.setObjectName("groupInfoLabel")
        toolbar.addWidget(self.group_info_label)

        table_layout.addLayout(toolbar)

        # F7: Frozen columns container
        self._frozen_columns: List[str] = []
        self._frozen_view: Optional[QTableView] = None

        # Table view
        self.table_view = DataTableView()
        self.table_model = PolarsTableModel()
        self.grouped_model = None
        self.table_view.setModel(self.table_model)
        self.table_view.clicked.connect(self._on_table_clicked)

        table_layout.addWidget(self.table_view)

        layout.addWidget(table_container)

    def _connect_signals(self):
        self.table_view.rows_selected.connect(self._on_rows_selected)
        self.table_view.exclude_value.connect(self._on_exclude_value)
        self.table_view.hide_column.connect(self._on_hide_column)
        self.table_view.exclude_column.connect(self._on_exclude_column)
        self.table_view.column_dragged.connect(self._on_column_action)
        self.table_view.column_order_changed.connect(self._on_column_order_changed)
        self.table_view.column_type_convert.connect(self._on_column_type_convert)
        self.table_view.conditional_format_requested.connect(self._on_conditional_format_requested)
        self.table_view.column_freeze.connect(self._on_freeze_column)
        self.table_view.column_unfreeze.connect(self._on_unfreeze_column)
        self._state_adapter.selection_changed.connect(self._on_state_selection_changed)
        self._state_adapter.group_zone_changed.connect(self._on_group_zone_changed)
        self._state_adapter.value_zone_changed.connect(self._on_value_zone_changed)
        self._state_adapter.filter_changed.connect(self._on_filter_changed)
        self._state_adapter.limit_to_marking_changed.connect(self._on_limit_to_marking_changed)
        self._state_adapter.selection_changed.connect(self._on_selection_for_limit_marking)

    def set_data(self, df: Optional[pl.DataFrame]):
        # 기존 캐시 클리어
        self.table_model._column_cache.clear()
        if self.grouped_model:
            self.grouped_model._row_cache = []
        self._update_table_model(df)
        self._update_window_controls()
        self._populate_group_combos()
        self._sync_group_combos_from_state()
        # Enable/disable search bar based on data availability
        has_data = df is not None and len(df) > 0
        self.search_input.setEnabled(has_data)
        if not has_data:
            self.search_input.setPlaceholderText("No data loaded")
            self.search_input.clear()
        else:
            self.search_input.setPlaceholderText("🔍 Search in table... (Ctrl+F)")

    def _update_table_model(self, df: Optional[pl.DataFrame] = None):
        if df is None:
            df = self.engine.df if self.engine.is_loaded else None

        if df is None:
            self.table_model.set_dataframe(None)
            self.group_info_label.setText("")
            return

        # Apply column order + hidden columns
        order = self.state.get_column_order() or []
        if order:
            ordered_cols = [c for c in order if c in df.columns]
            # Append any new columns not in order
            ordered_cols += [c for c in df.columns if c not in ordered_cols]
            df = df.select(ordered_cols)

        hidden_cols = self.state.hidden_columns
        if hidden_cols:
            visible_cols = [col for col in df.columns if col not in hidden_cols]
            if visible_cols:
                df = df.select(visible_cols)

        # Table view mode
        view_mode = None
        try:
            view_mode = self.table_view_mode_combo.currentData()
        except Exception:
            logger.warning("table_panel.update_table.view_mode.error", exc_info=True)
            view_mode = None

        # "Source Raw" means: ignore table-level filters/marking/search and show engine.df as-is.
        if view_mode == "source_raw":
            df = self.engine.df if self.engine.is_loaded else df

        show_grouped = bool(self.state.group_columns) and view_mode != "pre_group" and view_mode != "source_raw"

        if show_grouped:
            if self.grouped_model is None:
                self.grouped_model = GroupedTableModel()

            group_cols = [g.name for g in self.state.group_columns]
            value_cols = [v.name for v in self.state.value_columns]
            agg_map = {v.name: v.aggregation.value for v in self.state.value_columns}

            self.grouped_model.set_data(
                df,
                group_columns=group_cols,
                value_columns=value_cols,
                aggregations=agg_map
            )

            self.table_view.setModel(self.grouped_model)

            group_names = " → ".join(group_cols)
            self.group_info_label.setText(f"Grouped: {group_names}")
            self.group_info_label.setProperty("state", "grouped")
            self.group_info_label.style().unpolish(self.group_info_label)
            self.group_info_label.style().polish(self.group_info_label)

            # Grouped-only controls
            try:
                self.expand_btn.setEnabled(True)
                self.collapse_btn.setEnabled(True)
            except Exception:
                logger.warning("table_panel.update_table.expand_btn.error", exc_info=True)
        else:
            # Row-level table view
            self.table_model.set_dataframe(df)
            self.table_view.setModel(self.table_model)

            # Disable grouped-only controls
            try:
                self.expand_btn.setEnabled(False)
                self.collapse_btn.setEnabled(False)
            except Exception:
                logger.warning("table_panel.update_table.collapse_btn.error", exc_info=True)

            # 데이터가 잘렸는지 표시
            actual_rows = self.table_model.get_actual_row_count()
            displayed_rows = self.table_model.rowCount()
            if actual_rows > displayed_rows:
                self.group_info_label.setText(f"Showing {displayed_rows:,} of {actual_rows:,} rows")
                self.group_info_label.setProperty("state", "warning")
                self.group_info_label.style().unpolish(self.group_info_label)
                self.group_info_label.style().polish(self.group_info_label)
            else:
                self.group_info_label.setText("")
                self.group_info_label.setProperty("state", "")
                self.group_info_label.style().unpolish(self.group_info_label)
                self.group_info_label.style().polish(self.group_info_label)

        header = self.table_view.horizontalHeader()
        for i in range(min(10, self.table_view.model().columnCount())):
            header.resizeSection(i, 120)

    def clear(self):
        self.table_model.set_dataframe(None)
        if self.grouped_model:
            self.grouped_model.set_data(None)
        self.group_info_label.setText("")

    def _on_rows_selected(self, rows: List[int]):
        if self.grouped_model and self.state.group_columns:
            actual_rows = []
            for row in rows:
                data = self.grouped_model.data(
                    self.grouped_model.index(row, 0),
                    Qt.UserRole
                )
                if data:
                    node, row_idx = data
                    if row_idx is not None:
                        actual_rows.append(row_idx)
            self.state.select_rows(actual_rows)
        else:
            self.state.select_rows(rows)

    def _on_state_selection_changed(self):
        """Sync table selection with state selection"""
        selected_rows = self.state.selection.selected_rows

        if not selected_rows:
            # Clear selection
            self.table_view.clearSelection()
            return

        model = self.table_view.model()
        if model is None:
            return

        row_count = model.rowCount()
        col_count = model.columnCount()

        if row_count == 0 or col_count == 0:
            return

        # Block signals to prevent feedback loop
        self.table_view.blockSignals(True)

        try:
            # Clear and rebuild selection
            self.table_view.clearSelection()

            # Use QItemSelection for batch selection (more efficient)
            selection = QItemSelection()

            for row in selected_rows:
                if 0 <= row < row_count:
                    # Create selection range for entire row
                    top_left = model.index(row, 0)
                    bottom_right = model.index(row, col_count - 1)
                    selection.select(top_left, bottom_right)

            # Apply selection
            selection_model = self.table_view.selectionModel()
            if selection_model:
                selection_model.select(selection, QItemSelectionModel.Select)

            # Scroll to first selected row
            first_row = min(selected_rows)
            if 0 <= first_row < row_count:
                self.table_view.scrollTo(model.index(first_row, 0))

        finally:
            self.table_view.blockSignals(False)

    def _on_group_zone_changed(self):
        self._sync_group_combos_from_state()
        if self.engine.is_loaded:
            self._update_table_model(self.engine.df)

    def _on_value_zone_changed(self):
        if self.engine.is_loaded and self.state.group_columns:
            self._update_table_model(self.engine.df)

    # ── GroupBy / Aggregation Combos ──────────────────────────

    def _populate_group_combos(self):
        """컬럼 목록으로 GroupBy 콤보박스 채우기"""
        columns = self.engine.columns if self.engine.is_loaded else []
        for combo in (self.group_combo1, self.group_combo2):
            combo.blockSignals(True)
            prev = combo.currentText()
            combo.clear()
            combo.addItem("(None)")
            for col in columns:
                combo.addItem(col)
            # 이전 선택 복원
            idx = combo.findText(prev)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def _sync_group_combos_from_state(self):
        """AppState의 group_columns를 콤보박스에 반영"""
        groups = self.state.group_columns
        for i, combo in enumerate((self.group_combo1, self.group_combo2)):
            combo.blockSignals(True)
            if i < len(groups):
                idx = combo.findText(groups[i].name)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                combo.setCurrentIndex(0)  # (None)
            combo.blockSignals(False)

    def _on_group_combo_changed(self):
        """콤보박스에서 GroupBy 변경 시 AppState 업데이트

        Uses blockSignals to prevent redundant intermediate table rebuilds
        when clear_group_zone + add_group_column each emit group_zone_changed.
        """
        g1 = self.group_combo1.currentText()
        g2 = self.group_combo2.currentText()

        was_blocked = self.state.signalsBlocked()
        self.state.blockSignals(True)
        try:
            self.state.clear_group_zone()
            if g1 and g1 != "(None)":
                self.state.add_group_column(g1)
            if g2 and g2 != "(None)" and g2 != g1:
                self.state.add_group_column(g2)
        finally:
            self.state.blockSignals(was_blocked)
        # Emit once after batch update
        self.state.group_zone_changed.emit()

    def _on_agg_combo_changed(self):
        """Aggregation 변경 시 현재 value_columns의 aggregation 업데이트"""
        from ...core.state import AggregationType
        agg_text = self.agg_combo.currentData()
        if not agg_text:
            return
        try:
            agg = AggregationType(agg_text)
        except ValueError:
            return
        # 모든 value_columns의 aggregation 업데이트 (index로 전달)
        for i in range(len(self.state.value_columns)):
            self.state.update_value_column(i, aggregation=agg)

    def _on_table_clicked(self, index):
        if index.column() == 0 and self.grouped_model and self.state.group_columns:
            is_header = self.grouped_model.data(index, Qt.UserRole + 1)
            if is_header:
                self.grouped_model.toggle_expand(index.row())

    def _expand_all(self):
        if self.grouped_model and self.state.group_columns:
            self.grouped_model.expand_all()

    def _collapse_all(self):
        if self.grouped_model and self.state.group_columns:
            self.grouped_model.collapse_all()

    def get_group_data(self) -> List:
        if self.grouped_model and self.state.group_columns:
            return self.grouped_model.get_group_data()
        return []

    # ==================== Table View Mode ====================

    def _on_table_view_mode_changed(self):
        """Handle table view mode changes."""
        if not self.engine.is_loaded:
            return

        mode = None
        try:
            mode = self.table_view_mode_combo.currentData()
        except Exception:
            logger.warning("table_panel.on_view_mode_changed.error", exc_info=True)
            mode = None

        # Grouped mode only makes sense when Group By is configured.
        if mode == "grouped" and not self.state.group_columns:
            # Auto-fallback to row view when no group columns.
            idx = self.table_view_mode_combo.findData("pre_group")
            if idx >= 0:
                self.table_view_mode_combo.blockSignals(True)
                self.table_view_mode_combo.setCurrentIndex(idx)
                self.table_view_mode_combo.blockSignals(False)

        # Re-apply current table pipeline
        if mode == "source_raw":
            self._update_table_model(self.engine.df)
            return

        if self.state.limit_to_marking:
            self._apply_limit_to_marking()
        else:
            self._apply_filters_and_update()

    # ==================== Limit to Marking ====================

    def _on_limit_marking_toggled(self, checked: bool):
        """Handle limit to marking button toggle"""
        self.state.set_limit_to_marking(checked)

    def _on_limit_to_marking_changed(self, enabled: bool):
        """Handle limit to marking state change"""
        self.limit_marking_btn.setChecked(enabled)
        self._apply_limit_to_marking()

    def _on_selection_for_limit_marking(self):
        """Update table when selection changes and limit to marking is enabled"""
        if self.state.limit_to_marking:
            self._apply_limit_to_marking()
        if self._focus_enabled:
            self._update_focus_from_selection()

    def _apply_limit_to_marking(self):
        """Apply limit to marking filter to table"""
        if not self.engine.is_loaded:
            return

        df = self.engine.df
        if df is None:
            return

        if self.state.limit_to_marking and self.state.selection.has_selection:
            # Filter to only selected rows
            selected_rows = list(self.state.selection.selected_rows)

            # Ensure indices are within bounds
            max_idx = len(df)
            valid_indices = [i for i in selected_rows if 0 <= i < max_idx]

            if valid_indices:
                # Bug 2: O(n) with polars is_in instead of O(n×m) list comprehension
                valid_series = pl.Series("valid", valid_indices)
                idx_series = pl.Series("idx", list(range(len(df))))
                mask = idx_series.is_in(valid_series)
                filtered_df = df.filter(mask)

                # UX 9: Use setProperty instead of inline style
                self.group_info_label.setText(f"Showing {len(valid_indices)} marked rows")
                self.group_info_label.setProperty("state", "marking")
                self.group_info_label.style().unpolish(self.group_info_label)
                self.group_info_label.style().polish(self.group_info_label)

                self._update_table_model(filtered_df)
            else:
                # No valid selection, show empty or all
                self._update_table_model(df)
        else:
            # Show all data
            self._apply_filters_and_update()

    # ==================== F2: Edit Mode ====================

    def _on_edit_toggle(self, checked: bool):
        self.table_model.set_editable(checked)

    # ==================== Drag & Drop ====================

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path:
                    self.file_dropped.emit(file_path)
                    break
            event.acceptProposedAction()
