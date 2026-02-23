"""Zone widgets - X-Axis, Group, Value, and Hover drop zones."""

from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QFrame, QPushButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDropEvent, QDragEnterEvent

from ...core.state import AppState, AggregationType, ValueColumn
from ..adapters.app_state_adapter import AppStateAdapter
from ._chip_widgets import (
    ChipWidget, ValueChipWidget, ChipListWidget,
    _parse_drag_payload, _remove_from_source,
)


# ==================== X-Axis Zone ====================

class XAxisZone(QFrame):
    """X-Axis Zone - X축 컬럼 선택"""

    x_changed = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._state_adapter = AppStateAdapter(state, parent=self)
        self.setObjectName("XAxisZone")
        self.setMinimumWidth(140)
        self.setMaximumWidth(180)
        self.setAcceptDrops(True)

        self._setup_ui()
        self._connect_signals()
        self._apply_style()

    def _apply_style(self):
        # Styles handled by global theme stylesheet
        pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header (no float button for internal sections)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon = QLabel("📐")
        icon.setObjectName("zoneIcon")
        header_layout.addWidget(icon)

        header = QLabel("X-Axis")
        header.setObjectName("zoneHeader")
        header.setProperty("zone", "x")
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Help text
        help_label = QLabel("Drag column for X-axis\n(empty = use index)")
        help_label.setObjectName("zoneHelp")
        help_label.setProperty("zone", "x")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # Chip drop area
        self.x_column_frame = QFrame()
        self.x_column_frame.setObjectName("dropZone")
        self.x_column_frame.setProperty("zone", "x")
        x_layout = QVBoxLayout(self.x_column_frame)
        x_layout.setContentsMargins(4, 4, 4, 4)
        x_layout.setSpacing(2)

        self.placeholder_label = QLabel("(Index)")
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setObjectName("placeholder")
        x_layout.addWidget(self.placeholder_label)

        self.list_widget = ChipListWidget(zone_id="x", accept_drop=True, single_item=True)
        self.list_widget.setObjectName("chipList")
        self.list_widget.item_dropped.connect(self._on_chip_dropped)
        x_layout.addWidget(self.list_widget)

        layout.addWidget(self.x_column_frame)

        # Clear button
        clear_btn = QPushButton("✕ Use Index")
        clear_btn.setObjectName("zoneClearBtn")
        clear_btn.setProperty("zone", "x")
        clear_btn.setToolTip("Clear X-axis column and use row index")
        clear_btn.clicked.connect(self._clear_x_column)
        layout.addWidget(clear_btn)

        layout.addStretch()

    def _connect_signals(self):
        # Listen for x_column changes from state (via adapter)
        self._state_adapter.chart_settings_changed.connect(self._sync_from_state)

    def _on_chip_dropped(self, column_name: str, payload: Dict[str, Any]):
        self._set_x_column(column_name)
        _remove_from_source(self.state, payload, "x")

    def _set_x_column(self, column_name: str):
        """Set X column"""
        self.state.set_x_column(column_name)
        self._update_display(column_name)

    def _clear_x_column(self):
        """Clear X column (use index)"""
        self.state.set_x_column(None)
        self._update_display(None)

    def _update_display(self, column_name: Optional[str]):
        """Update the display"""
        self.list_widget.clear_chips()
        if column_name:
            chip = ChipWidget(column_name, accent="#10B981", text_color="#047857", zone_id="x")
            chip.remove_clicked.connect(self._clear_x_column)
            self.list_widget.add_chip(column_name, chip)
            self.placeholder_label.hide()
            self.list_widget.show()
            self.x_column_frame.setProperty("state", "filled")
        else:
            self.placeholder_label.setText("(Index)")
            self.placeholder_label.show()
            self.list_widget.hide()
            self.x_column_frame.setProperty("state", "empty")
        self.x_column_frame.style().unpolish(self.x_column_frame)
        self.x_column_frame.style().polish(self.x_column_frame)

    def _sync_from_state(self):
        """Sync from state"""
        self._update_display(self.state.x_column)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-dgs-zone"):
            event.acceptProposedAction()
            self.x_column_frame.setProperty("state", "dragover")
            self.x_column_frame.style().unpolish(self.x_column_frame)
            self.x_column_frame.style().polish(self.x_column_frame)

    def dragLeaveEvent(self, event):
        self._update_display(self.state.x_column)

    def dropEvent(self, event: QDropEvent):
        payload = _parse_drag_payload(event.mimeData())
        if payload.get("name"):
            self._on_chip_dropped(payload["name"], payload)
            event.acceptProposedAction()


# ==================== Group Zone ====================

class GroupZone(QFrame):
    """Group Zone - Minimal drag & drop zone"""

    group_changed = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._state_adapter = AppStateAdapter(state, parent=self)
        self.setObjectName("GroupZone")
        self.setMinimumWidth(130)
        self.setMaximumWidth(170)
        self.setAcceptDrops(True)

        self._setup_ui()
        self._connect_signals()
        self._apply_style()

    def _apply_style(self):
        # Styles handled by global theme stylesheet
        pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header (no float button for internal sections)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon = QLabel("📁")
        icon.setObjectName("zoneIcon")
        header_layout.addWidget(icon)

        header = QLabel("Group By")
        header.setObjectName("zoneHeader")
        header.setProperty("zone", "group")
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Help text
        help_label = QLabel("Drag columns to group")
        help_label.setObjectName("zoneHelp")
        help_label.setProperty("zone", "group")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # List widget
        self.list_widget = ChipListWidget(zone_id="group", accept_drop=True, allow_reorder=True)
        self.list_widget.setMaximumHeight(130)
        self.list_widget.setObjectName("chipList")
        self.list_widget.item_dropped.connect(self._on_column_dropped)
        self.list_widget.order_changed.connect(self._on_order_changed)
        layout.addWidget(self.list_widget, 1)

        # Clear button
        remove_btn = QPushButton("✕ Clear")
        remove_btn.setObjectName("dangerButton")
        remove_btn.setToolTip("Clear all group-by columns")
        remove_btn.clicked.connect(self.state.clear_group_zone)
        layout.addWidget(remove_btn)

    def _connect_signals(self):
        self._state_adapter.group_zone_changed.connect(self._sync_from_state)

    def _on_column_dropped(self, column_name: str, payload: Dict[str, Any]):
        self.state.add_group_column(column_name)
        _remove_from_source(self.state, payload, "group")

    def _on_order_changed(self, new_order: List[str]):
        self.state.reorder_group_columns(new_order)

    def _sync_from_state(self):
        self.list_widget.clear_chips()
        for idx, group_col in enumerate(self.state.group_columns):
            chip = ChipWidget(group_col.name, accent="#CBD5F5", text_color="#1E293B", zone_id="group", index=idx)
            chip.remove_clicked.connect(lambda checked=False, name=group_col.name: self.state.remove_group_column(name))
            self.list_widget.add_chip(group_col.name, chip)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-dgs-zone"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        payload = _parse_drag_payload(event.mimeData())
        if payload.get("name"):
            self._on_column_dropped(payload["name"], payload)
            event.acceptProposedAction()


# ==================== Value Zone ====================

class ValueZone(QFrame):
    """Value Zone - Y-axis values"""

    value_changed = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._state_adapter = AppStateAdapter(state, parent=self)
        self.setObjectName("ValueZone")
        self.setMinimumWidth(160)
        self.setAcceptDrops(True)

        self._setup_ui()
        self._connect_signals()
        self._apply_style()

    def _apply_style(self):
        # Styles handled by global theme stylesheet
        pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header (no float button for internal sections)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon = QLabel("📊")
        icon.setObjectName("zoneIcon")
        header_layout.addWidget(icon)

        header = QLabel("Y-Axis Values")
        header.setObjectName("zoneHeader")
        header.setProperty("zone", "value")
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Help text
        help_label = QLabel("Drag numeric columns for Y values")
        help_label.setObjectName("zoneHelp")
        help_label.setProperty("zone", "value")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # Chip list
        self.list_widget = ChipListWidget(zone_id="value", accept_drop=True)
        self.list_widget.setObjectName("chipList")
        self.list_widget.item_dropped.connect(self._on_column_dropped)
        layout.addWidget(self.list_widget, 1)

    def _connect_signals(self):
        self._state_adapter.value_zone_changed.connect(self._sync_from_state)

    def _add_value_chip(self, value_col: ValueColumn, index: int):
        """Add value chip"""
        chip = ValueChipWidget(
            value_col,
            index,
            on_agg_changed=self._on_agg_changed,
            on_formula_changed=self._on_formula_changed
        )
        chip.remove_clicked.connect(lambda checked=False, i=index: self._remove_value(i))
        self.list_widget.add_chip(value_col.name, chip)

    def _on_agg_changed(self, index: int, agg: AggregationType):
        self.state.update_value_column(index, aggregation=agg)

    def _on_formula_changed(self, index: int, formula: str):
        """Formula 변경 핸들러"""
        self.state.update_value_column(index, formula=formula.strip())

    def _remove_value(self, index: int):
        self.state.remove_value_column(index)

    def _on_column_dropped(self, column_name: str, payload: Dict[str, Any]):
        self.state.add_value_column(column_name)
        _remove_from_source(self.state, payload, "value")

    def _sync_from_state(self):
        self.list_widget.clear_chips()
        for i, value_col in enumerate(self.state.value_columns):
            self._add_value_chip(value_col, i)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-dgs-zone"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        payload = _parse_drag_payload(event.mimeData())
        if payload.get("name"):
            self._on_column_dropped(payload["name"], payload)
            event.acceptProposedAction()


# ==================== Hover Zone ====================

class HoverZone(QFrame):
    """Hover Zone - Columns to display on data hover"""

    hover_changed = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._state_adapter = AppStateAdapter(state, parent=self)
        self.setObjectName("HoverZone")
        self.setMinimumWidth(150)
        self.setAcceptDrops(True)

        self._setup_ui()
        self._connect_signals()
        self._apply_style()

    def _apply_style(self):
        # Styles handled by global theme stylesheet
        pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header (no float button)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon = QLabel("💬")
        icon.setObjectName("zoneIcon")
        header_layout.addWidget(icon)

        header = QLabel("Hover Data")
        header.setObjectName("zoneHeader")
        header.setProperty("zone", "hover")
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Help text
        help_label = QLabel("Drag columns to show\non hover tooltip")
        help_label.setObjectName("zoneHelp")
        help_label.setProperty("zone", "hover")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # List widget for hover columns
        self.list_widget = ChipListWidget(zone_id="hover", accept_drop=True)
        self.list_widget.setMaximumHeight(120)
        self.list_widget.setObjectName("chipList")
        self.list_widget.item_dropped.connect(self._on_column_dropped)
        layout.addWidget(self.list_widget, 1)

        # Clear button
        clear_btn = QPushButton("✕ Clear")
        clear_btn.setObjectName("warningButton")
        clear_btn.setToolTip("Clear all hover columns")
        clear_btn.clicked.connect(self._clear_all)
        layout.addWidget(clear_btn)

    def _connect_signals(self):
        self._state_adapter.hover_zone_changed.connect(self._sync_from_state)

    def _on_column_dropped(self, column_name: str, payload: Dict[str, Any]):
        self.state.add_hover_column(column_name)
        _remove_from_source(self.state, payload, "hover")

    def _clear_all(self):
        self.state.clear_hover_columns()

    def _sync_from_state(self):
        self.list_widget.clear_chips()
        for idx, col in enumerate(self.state.hover_columns):
            chip = ChipWidget(col, accent="#FACC15", text_color="#713F12", zone_id="hover", index=idx)
            chip.remove_clicked.connect(lambda checked=False, name=col: self.state.remove_hover_column(name))
            self.list_widget.add_chip(col, chip)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-dgs-zone"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        payload = _parse_drag_payload(event.mimeData())
        if payload.get("name"):
            self._on_column_dropped(payload["name"], payload)
            event.acceptProposedAction()
