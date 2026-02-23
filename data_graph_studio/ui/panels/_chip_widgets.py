"""Chip widgets and drag-and-drop helpers for zone panels."""

import logging
from typing import Optional, Dict, Any
import json


from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QAbstractItemView, QListWidget, QListWidgetItem,
    QPushButton, QComboBox, QLineEdit, QApplication,
)
from PySide6.QtCore import Qt, Signal, QMimeData, QByteArray, QSize
from PySide6.QtGui import QDrag, QDropEvent, QDragEnterEvent

from ...core.state import AppState, AggregationType, ValueColumn


logger = logging.getLogger(__name__)

# ==================== Drag helpers ====================

def _parse_drag_payload(mime_data: QMimeData) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"zone": None, "name": None, "index": None}
    if mime_data.hasFormat("application/x-dgs-zone"):
        try:
            raw = bytes(mime_data.data("application/x-dgs-zone")).decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                payload.update(data)
        except Exception:
            logger.warning("chip_widgets.parse_drag_payload.error", exc_info=True)
    if not payload.get("name") and mime_data.hasText():
        payload["name"] = mime_data.text()
    return payload


def _build_drag_payload(zone: str, name: str, index: Optional[int] = None) -> QByteArray:
    data: Dict[str, Any] = {"zone": zone, "name": name}
    if index is not None:
        data["index"] = index
    return QByteArray(json.dumps(data).encode("utf-8"))


def _remove_from_source(state: AppState, payload: Dict[str, Any], target_zone: str):
    source = payload.get("zone")
    if not source or source == target_zone:
        return
    name = payload.get("name")
    index = payload.get("index")
    if source == "x":
        if state.x_column == name:
            state.set_x_column(None)
    elif source == "group":
        if name:
            state.remove_group_column(name)
    elif source == "hover":
        if name:
            state.remove_hover_column(name)
    elif source == "value":
        if index is not None:
            state.remove_value_column(index)


# ==================== Chip widgets ====================

class DragHandleLabel(QLabel):
    def __init__(self, zone_id: str, name: str, index: Optional[int] = None):
        super().__init__("⋮⋮")
        self.zone_id = zone_id
        self.name = name
        self.index = index
        self._start_pos = None
        self.setObjectName("dragHandle")
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._start_pos is not None:
            if (event.pos() - self._start_pos).manhattanLength() >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self.name)
                mime.setData("application/x-dgs-zone", _build_drag_payload(self.zone_id, self.name, self.index))
                drag.setMimeData(mime)
                drag.exec(Qt.MoveAction)
        super().mouseMoveEvent(event)


class ChipWidget(QFrame):
    remove_clicked = Signal()

    def __init__(self, text: str, accent: str, text_color: str = "#1E293B", zone_id: Optional[str] = None, index: Optional[int] = None):
        super().__init__()
        self._zone_id = zone_id
        self._name = text
        self._index = index
        self._start_pos = None
        self.setObjectName("chipWidget")
        self.setFixedHeight(28)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        if zone_id:
            layout.addWidget(DragHandleLabel(zone_id, text, index))

        label = QLabel(text)
        label.setObjectName("chipLabel")
        label.setToolTip(text)
        layout.addWidget(label, 1)

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setObjectName("chipRemoveBtn")
        remove_btn.clicked.connect(self.remove_clicked.emit)
        layout.addWidget(remove_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._start_pos is not None and self._zone_id:
            if (event.pos() - self._start_pos).manhattanLength() >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self._name)
                mime.setData("application/x-dgs-zone", _build_drag_payload(self._zone_id, self._name, self._index))
                drag.setMimeData(mime)
                drag.exec(Qt.MoveAction)
        super().mouseMoveEvent(event)


class ValueChipWidget(QFrame):
    remove_clicked = Signal()

    def __init__(self, value_col: ValueColumn, index: int, on_agg_changed, on_formula_changed):
        super().__init__()
        self._zone_id = "value"
        self._name = value_col.name
        self._index = index
        self._start_pos = None
        self.setObjectName("valueChipWidget")
        self.setMinimumHeight(28)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(2)

        # Row 1: drag handle + name + remove button
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        row1.addWidget(DragHandleLabel("value", value_col.name, index))

        name_label = QLabel(f"● {value_col.name}")
        name_label.setObjectName("valueNameLabel")
        name_label.setToolTip(value_col.name)
        row1.addWidget(name_label, 1)

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setObjectName("chipRemoveBtn")
        remove_btn.clicked.connect(self.remove_clicked.emit)
        row1.addWidget(remove_btn)
        main_layout.addLayout(row1)

        # Row 2: agg combo + formula
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        agg_combo = QComboBox()
        agg_combo.setMinimumWidth(55)
        agg_combo.setMaximumWidth(70)
        agg_combo.setFixedHeight(20)
        for agg in AggregationType:
            agg_combo.addItem(agg.value.upper(), agg)
        agg_combo.setCurrentText(value_col.aggregation.value.upper())
        agg_combo.currentIndexChanged.connect(
            lambda idx, combo=agg_combo: on_agg_changed(index, combo.currentData())
        )
        row2.addWidget(agg_combo)

        formula_edit = QLineEdit()
        formula_edit.setPlaceholderText("f(y)=...")
        formula_edit.setText(value_col.formula or "")
        formula_edit.setFixedHeight(20)
        formula_edit.setToolTip(
            "Y값에 적용할 수식을 입력하세요.\n"
            "예시: y*2, y+100, LOG(y), SQRT(y), ABS(y)"
        )
        formula_edit.editingFinished.connect(
            lambda edit=formula_edit: on_formula_changed(index, edit.text())
        )
        row2.addWidget(formula_edit, 1)
        main_layout.addLayout(row2)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._start_pos is not None:
            if (event.pos() - self._start_pos).manhattanLength() >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self._name)
                mime.setData("application/x-dgs-zone", _build_drag_payload(self._zone_id, self._name, self._index))
                drag.setMimeData(mime)
                drag.exec(Qt.MoveAction)
        super().mouseMoveEvent(event)


class ChipListWidget(QListWidget):
    """Chip/tag style list with drag/drop between zones."""

    item_dropped = Signal(str, dict)
    order_changed = Signal(list)

    def __init__(self, zone_id: str, accept_drop: bool = True, single_item: bool = False, allow_reorder: bool = False):
        super().__init__()
        self.zone_id = zone_id
        self.single_item = single_item
        self.allow_reorder = allow_reorder
        self.setDragEnabled(True)
        self.setAcceptDrops(accept_drop)
        self.setDropIndicatorShown(True)
        self.setSpacing(2)
        self.setDragDropMode(QAbstractItemView.DragDrop if accept_drop else QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.MoveAction if allow_reorder else Qt.CopyAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-dgs-zone"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole) or item.text()
        payload = _build_drag_payload(self.zone_id, name, index=self.row(item))
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(name)
        mime.setData("application/x-dgs-zone", payload)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def dropEvent(self, event: QDropEvent):
        payload = _parse_drag_payload(event.mimeData())
        name = payload.get("name")
        if not name:
            super().dropEvent(event)
            return

        if payload.get("zone") == self.zone_id:
            if self.allow_reorder:
                super().dropEvent(event)
                self.order_changed.emit([self.item(i).data(Qt.UserRole) or self.item(i).text() for i in range(self.count())])
            event.acceptProposedAction()
            return

        self.item_dropped.emit(name, payload)
        event.acceptProposedAction()

    def add_chip(self, name: str, widget: QWidget):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, name)
        # Ensure proper size hint from the widget
        widget.adjustSize()
        h = max(widget.sizeHint().height(), widget.minimumHeight(), 28)
        item.setSizeHint(QSize(self.viewport().width(), h + 4))
        self.addItem(item)
        self.setItemWidget(item, widget)

    def clear_chips(self):
        self.clear()
