"""FilterBar and HiddenColumnsBar - status bars for the table panel."""

from typing import List

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QFrame, QPushButton,
)
from PySide6.QtCore import Signal

from ...core.state import AppState
from ..adapters.app_state_adapter import AppStateAdapter


# ==================== Filter Bar ====================

class FilterBar(QFrame):
    """활성 필터 표시 바"""

    filter_removed = Signal(int)  # filter index
    clear_all = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._state_adapter = AppStateAdapter(state, parent=self)
        self.setObjectName("FilterBar")
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(8, 4, 8, 4)
        self.main_layout.setSpacing(6)

        # Filter icon
        icon = QLabel("🔍")
        icon.setObjectName("cardIcon")
        self.main_layout.addWidget(icon)

        # Filters container
        self.filters_layout = QHBoxLayout()
        self.filters_layout.setSpacing(4)
        self.main_layout.addLayout(self.filters_layout)

        self.main_layout.addStretch()

        # Clear all button
        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("warningButton")
        clear_btn.setToolTip("Remove all active filters")
        clear_btn.clicked.connect(self.clear_all.emit)
        self.main_layout.addWidget(clear_btn)

        self.setVisible(False)  # Hidden by default

    def _connect_signals(self):
        self._state_adapter.filter_changed.connect(self._update_filters)

    def _update_filters(self):
        """Update filter display"""
        # Clear existing
        while self.filters_layout.count():
            item = self.filters_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filters = self.state.filters

        if not filters:
            self.setVisible(False)
            return

        self.setVisible(True)

        for i, f in enumerate(filters):
            chip = self._create_filter_chip(f, i)
            self.filters_layout.addWidget(chip)

    def _create_filter_chip(self, filter_cond, index: int) -> QWidget:
        """Create a filter chip widget"""
        chip = QFrame()
        chip.setObjectName("chipWidget")

        layout = QHBoxLayout(chip)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        # Operator display
        op_map = {
            'eq': '=', 'ne': '≠', 'gt': '>', 'lt': '<',
            'ge': '≥', 'le': '≤', 'contains': '∋'
        }
        op = op_map.get(filter_cond.operator, filter_cond.operator)

        # Display value (truncate if too long)
        val_str = str(filter_cond.value)
        if len(val_str) > 15:
            val_str = val_str[:15] + "..."

        label = QLabel(f"{filter_cond.column} {op} \"{val_str}\"")
        label.setObjectName("chipLabel")
        layout.addWidget(label)

        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setObjectName("chipRemoveBtn")
        remove_btn.clicked.connect(lambda: self.filter_removed.emit(index))
        layout.addWidget(remove_btn)

        return chip


# ==================== Hidden Columns Bar ====================

class HiddenColumnsBar(QFrame):
    """숨겨진 컬럼 표시 바"""

    show_column = Signal(str)  # column name
    show_all = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("HiddenColumnsBar")
        self._setup_ui()

    def _setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(8, 4, 8, 4)
        self.main_layout.setSpacing(6)

        # Icon
        icon = QLabel("👁")
        icon.setObjectName("cardIcon")
        self.main_layout.addWidget(icon)

        label = QLabel("Hidden columns:")
        label.setObjectName("profileLabel")
        self.main_layout.addWidget(label)

        # Columns container
        self.columns_layout = QHBoxLayout()
        self.columns_layout.setSpacing(4)
        self.main_layout.addLayout(self.columns_layout)

        self.main_layout.addStretch()

        # Show all button
        show_all_btn = QPushButton("Show All")
        show_all_btn.setObjectName("smallButton")
        show_all_btn.setToolTip("Show all hidden columns")
        show_all_btn.clicked.connect(self.show_all.emit)
        self.main_layout.addWidget(show_all_btn)

        self.setVisible(False)

    def update_hidden_columns(self, hidden_columns: List[str]):
        """Update hidden columns display"""
        # Clear existing
        while self.columns_layout.count():
            item = self.columns_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not hidden_columns:
            self.setVisible(False)
            return

        self.setVisible(True)

        for col in hidden_columns[:5]:  # Show max 5
            chip = self._create_column_chip(col)
            self.columns_layout.addWidget(chip)

        if len(hidden_columns) > 5:
            more = QLabel(f"+{len(hidden_columns) - 5} more")
            more.setObjectName("hintLabel")
            self.columns_layout.addWidget(more)

    def _create_column_chip(self, column: str) -> QWidget:
        chip = QFrame()
        chip.setObjectName("chipWidget")

        layout = QHBoxLayout(chip)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(2)

        label = QLabel(column[:12] + "..." if len(column) > 12 else column)
        label.setObjectName("chipLabel")
        label.setToolTip(column)
        layout.addWidget(label)

        show_btn = QPushButton("👁")
        show_btn.setFixedSize(16, 16)
        show_btn.setObjectName("chipRemoveBtn")
        show_btn.setToolTip(f"Show {column}")
        show_btn.clicked.connect(lambda: self.show_column.emit(column))
        layout.addWidget(show_btn)

        return chip
