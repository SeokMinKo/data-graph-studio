"""
Table Panel - 테이블 뷰 + X Zone + Group Zone + Value Zone
"""

from typing import Optional, List, Dict, Any
import json
import polars as pl

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QTableView, QHeaderView, QAbstractItemView, QMenu,
    QLineEdit, QComboBox, QPushButton,
    QSplitter, QSizePolicy, QApplication, QListWidget,
    QListWidgetItem, QGroupBox, QSlider
)
from PySide6.QtCore import QTimer
from PySide6.QtCore import (
    Qt, Signal, Slot, QAbstractTableModel, QModelIndex,
    QMimeData, QByteArray, QItemSelection, QItemSelectionModel, QEvent
)
from PySide6.QtGui import QDrag, QAction, QDropEvent, QDragEnterEvent

from ...core.state import AppState, AggregationType, GroupColumn, ValueColumn
from ...core.data_engine import DataEngine
from .grouped_table_model import GroupedTableModel
from ..floatable import FloatButton, FloatWindow


class PolarsTableModel(QAbstractTableModel):
    """Polars DataFrame을 위한 Qt 테이블 모델 (최적화 버전)

    성능 최적화:
    - 컬럼 기반 캐싱 (Polars는 컬럼 지향이므로)
    - 직접 인덱스 접근으로 iter_rows() 회피
    - 필요한 데이터만 로드
    - 정렬 인덱스 기반 접근 (메모리 효율)
    """

    # 테이블에 표시할 최대 행 수 (성능 보장)
    MAX_DISPLAY_ROWS = 100_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: Optional[pl.DataFrame] = None
        self._original_df: Optional[pl.DataFrame] = None  # 정렬 전 원본
        self._visible_columns: List[str] = []
        self._row_count = 0
        self._actual_row_count = 0  # 실제 데이터 행 수
        # 컬럼 기반 캐시: column_index -> list of values
        self._column_cache: Dict[int, list] = {}
        self._cache_valid = False
        # 정렬 상태
        self._sort_column: Optional[int] = None
        self._sort_order: Optional[Qt.SortOrder] = None
        self._sort_indices: Optional[pl.Series] = None  # 원본 인덱스 매핑

    def set_dataframe(self, df: Optional[pl.DataFrame]):
        self.beginResetModel()
        self._df = df
        self._original_df = df  # 원본 저장
        self._column_cache.clear()
        self._cache_valid = False
        # 정렬 상태 초기화
        self._sort_column = None
        self._sort_order = None
        self._sort_indices = None
        if df is not None:
            self._visible_columns = df.columns
            self._actual_row_count = len(df)
            # 성능을 위해 최대 행 수 제한
            self._row_count = min(len(df), self.MAX_DISPLAY_ROWS)
        else:
            self._visible_columns = []
            self._row_count = 0
            self._actual_row_count = 0
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return self._row_count

    def columnCount(self, parent=QModelIndex()):
        return len(self._visible_columns)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or self._df is None:
            return None

        if role == Qt.DisplayRole or role == Qt.EditRole:
            row = index.row()
            col = index.column()

            if row >= self._row_count or col >= len(self._visible_columns):
                return None

            # 컬럼 캐시에서 데이터 가져오기
            if col not in self._column_cache:
                self._cache_column(col)

            if col in self._column_cache:
                cache = self._column_cache[col]
                if row < len(cache):
                    value = cache[row]
                    if value is None:
                        return ""
                    return str(value)

        return None

    def _cache_column(self, col: int):
        """컬럼 데이터를 캐시에 로드 (한 번만 변환)"""
        if self._df is None or col >= len(self._visible_columns):
            return

        col_name = self._visible_columns[col]
        try:
            # 표시할 행 수만큼만 가져옴
            if self._row_count < self._actual_row_count:
                col_data = self._df[col_name].head(self._row_count).to_list()
            else:
                col_data = self._df[col_name].to_list()
            self._column_cache[col] = col_data
        except Exception:
            self._column_cache[col] = []

        # 캐시 크기 제한 (메모리 관리)
        MAX_CACHED_COLUMNS = 50
        if len(self._column_cache) > MAX_CACHED_COLUMNS:
            # 가장 오래된 컬럼 제거 (LRU 간소화)
            oldest = min(self._column_cache.keys())
            del self._column_cache[oldest]

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                if 0 <= section < len(self._visible_columns):
                    col_name = self._visible_columns[section]
                    # 정렬 아이콘 추가
                    if self._sort_column == section:
                        if self._sort_order == Qt.AscendingOrder:
                            return f"{col_name} ▲"
                        else:
                            return f"{col_name} ▼"
                    return col_name
            else:
                return str(section + 1)
        return None

    def get_column_name(self, index: int) -> Optional[str]:
        if 0 <= index < len(self._visible_columns):
            return self._visible_columns[index]
        return None

    def get_actual_row_count(self) -> int:
        """실제 데이터 행 수 (표시 제한과 무관)"""
        return self._actual_row_count

    # ==================== 정렬 기능 ====================

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder):
        """컬럼 기준 정렬

        Args:
            column: 정렬할 컬럼 인덱스
            order: Qt.AscendingOrder 또는 Qt.DescendingOrder
        """
        if self._original_df is None:
            return

        if column < 0 or column >= len(self._visible_columns):
            return

        col_name = self._visible_columns[column]

        self.beginResetModel()
        try:
            # 원본 데이터에 row_index 추가
            df_with_idx = self._original_df.with_row_index("__original_idx__")

            # 정렬 수행
            descending = (order == Qt.DescendingOrder)
            sorted_df = df_with_idx.sort(
                col_name,
                descending=descending,
                nulls_last=True
            )

            # 원본 인덱스 저장 (Int32로 메모리 효율화)
            self._sort_indices = sorted_df["__original_idx__"].cast(pl.Int32)

            # 정렬된 DataFrame 저장 (인덱스 컬럼 제거)
            self._df = sorted_df.drop("__original_idx__")

            # 캐시 무효화
            self._column_cache.clear()

            # 정렬 상태 저장
            self._sort_column = column
            self._sort_order = order

        except Exception as e:
            # 정렬 실패 시 원본 유지
            print(f"Sort error: {e}")
            self._df = self._original_df
            self._sort_column = None
            self._sort_order = None
            self._sort_indices = None

        self.endResetModel()

    def clear_sort(self):
        """정렬 초기화 (원본 순서로 복원)"""
        if self._original_df is None:
            return

        self.beginResetModel()
        self._df = self._original_df
        self._column_cache.clear()
        self._sort_column = None
        self._sort_order = None
        self._sort_indices = None
        self.endResetModel()

    def get_sort_column(self) -> Optional[int]:
        """현재 정렬된 컬럼 인덱스 반환"""
        return self._sort_column

    def get_sort_order(self) -> Optional[Qt.SortOrder]:
        """현재 정렬 순서 반환"""
        return self._sort_order

    def get_original_row_index(self, sorted_row: int) -> Optional[int]:
        """정렬된 행 인덱스에서 원본 행 인덱스 반환

        Args:
            sorted_row: 정렬된 테이블에서의 행 인덱스

        Returns:
            원본 DataFrame에서의 행 인덱스
        """
        if self._sort_indices is None:
            return sorted_row  # 정렬 안 된 경우 그대로 반환

        if 0 <= sorted_row < len(self._sort_indices):
            return int(self._sort_indices[sorted_row])

        return None

    def get_sorted_row_index(self, original_row: int) -> Optional[int]:
        """원본 행 인덱스에서 정렬된 행 인덱스 반환

        Args:
            original_row: 원본 DataFrame에서의 행 인덱스

        Returns:
            정렬된 테이블에서의 행 인덱스
        """
        if self._sort_indices is None:
            return original_row

        # 역 매핑 (선형 검색, 필요시 최적화 가능)
        try:
            indices_list = self._sort_indices.to_list()
            return indices_list.index(original_row)
        except ValueError:
            return None


def _parse_drag_payload(mime_data: QMimeData) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"zone": None, "name": None, "index": None}
    if mime_data.hasFormat("application/x-dgs-zone"):
        try:
            raw = bytes(mime_data.data("application/x-dgs-zone")).decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                payload.update(data)
        except Exception:
            pass
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


class DragHandleLabel(QLabel):
    def __init__(self, zone_id: str, name: str, index: Optional[int] = None):
        super().__init__("⋮⋮")
        self.zone_id = zone_id
        self.name = name
        self.index = index
        self._start_pos = None
        self.setStyleSheet("font-size: 10px; color: #94A3B8; background: transparent;")
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
        self.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid {accent}80;
                border-radius: 10px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        if zone_id:
            layout.addWidget(DragHandleLabel(zone_id, text, index))

        label = QLabel(text)
        label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {text_color}; background: transparent;")
        label.setToolTip(text)
        layout.addWidget(label, 1)

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94A3B8;
                border: none;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #FEE2E2;
                color: #EF4444;
                border-radius: 8px;
            }
        """)
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
        accent = value_col.color
        self.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid {accent}40;
                border-radius: 10px;
            }}
            QFrame:hover {{
                border-color: {accent}80;
                background: {accent}08;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        layout.addWidget(DragHandleLabel("value", value_col.name, index))

        name_label = QLabel(f"● {value_col.name}")
        name_label.setStyleSheet("font-weight: 600; font-size: 11px; color: #E6E9EF; background: transparent;")
        name_label.setToolTip(value_col.name)
        layout.addWidget(name_label)

        agg_combo = QComboBox()
        agg_combo.setStyleSheet(f"""
            QComboBox {{
                background: {accent}15;
                border: 1px solid {accent}30;
                border-radius: 5px;
                padding: 3px 6px;
                color: {accent};
                font-weight: 600;
                font-size: 10px;
                min-width: 70px;
            }}
            QComboBox:hover {{
                border-color: {accent};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 16px;
            }}
        """)
        for agg in AggregationType:
            agg_combo.addItem(agg.value.upper(), agg)
        agg_combo.setCurrentText(value_col.aggregation.value.upper())
        agg_combo.currentIndexChanged.connect(
            lambda idx, combo=agg_combo: on_agg_changed(index, combo.currentData())
        )
        layout.addWidget(agg_combo)

        formula_edit = QLineEdit()
        formula_edit.setPlaceholderText("f(y) = ...")
        formula_edit.setText(value_col.formula or "")
        formula_edit.setStyleSheet(f"""
            QLineEdit {{
                background: #F9FAFB;
                border: 1px solid {accent}30;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 10px;
                color: #E6E9EF;
                min-width: 80px;
            }}
            QLineEdit:focus {{
                border-color: {accent};
                background: white;
            }}
        """)
        formula_edit.setToolTip(
            "Y값에 적용할 수식을 입력하세요.\n"
            "예시: y*2, y+100, LOG(y), SQRT(y), ABS(y)"
        )
        formula_edit.editingFinished.connect(
            lambda edit=formula_edit: on_formula_changed(index, edit.text())
        )
        layout.addWidget(formula_edit, 1)

        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94A3B8;
                border: none;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #FEE2E2;
                color: #EF4444;
                border-radius: 8px;
            }
        """)
        remove_btn.clicked.connect(self.remove_clicked.emit)
        layout.addWidget(remove_btn)

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
        item.setSizeHint(widget.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, widget)

    def clear_chips(self):
        self.clear()


# ==================== X-Axis Zone ====================

class XAxisZone(QFrame):
    """X-Axis Zone - X축 컬럼 선택"""
    
    x_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("XAxisZone")
        self.setFixedWidth(150)
        self.setAcceptDrops(True)
        
        self._setup_ui()
        self._connect_signals()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #XAxisZone {
                background: #F0FDF4;
                border: none;
                border-radius: 8px;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header (no float button for internal sections)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon = QLabel("📐")
        icon.setStyleSheet("font-size: 16px; background: transparent;")
        header_layout.addWidget(icon)

        header = QLabel("X-Axis")
        header.setStyleSheet("""
            font-weight: 600;
            font-size: 13px;
            color: #047857;
            background: transparent;
        """)
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Help text
        help_label = QLabel("Drag column for X-axis\n(empty = use index)")
        help_label.setStyleSheet("""
            color: #059669;
            font-size: 10px;
            background: transparent;
        """)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # Chip drop area
        self.x_column_frame = QFrame()
        self.x_column_frame.setStyleSheet("""
            QFrame {
                background: white;
                border: 2px dashed #6EE7B7;
                border-radius: 8px;
                min-height: 50px;
            }
        """)
        x_layout = QVBoxLayout(self.x_column_frame)
        x_layout.setContentsMargins(6, 6, 6, 6)
        x_layout.setSpacing(4)

        self.placeholder_label = QLabel("(Index)")
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet("""
            color: #94A3B8;
            font-size: 12px;
            font-style: italic;
            background: transparent;
        """)
        x_layout.addWidget(self.placeholder_label)

        self.list_widget = ChipListWidget(zone_id="x", accept_drop=True, single_item=True)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
        """)
        self.list_widget.item_dropped.connect(self._on_chip_dropped)
        x_layout.addWidget(self.list_widget)

        layout.addWidget(self.x_column_frame)

        # Clear button
        clear_btn = QPushButton("✕ Use Index")
        clear_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #059669;
                border: 1px solid #6EE7B7;
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 500;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #D1FAE5;
                border-color: #059669;
            }
        """)
        clear_btn.clicked.connect(self._clear_x_column)
        layout.addWidget(clear_btn)

        layout.addStretch()
    
    def _connect_signals(self):
        # Listen for x_column changes from state
        self.state.chart_settings_changed.connect(self._sync_from_state)
    
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
            self.x_column_frame.setStyleSheet("""
                QFrame {
                    background: #ECFDF5;
                    border: 2px solid #10B981;
                    border-radius: 8px;
                    min-height: 50px;
                }
            """)
        else:
            self.placeholder_label.setText("(Index)")
            self.placeholder_label.show()
            self.list_widget.hide()
            self.x_column_frame.setStyleSheet("""
                QFrame {
                    background: white;
                    border: 2px dashed #6EE7B7;
                    border-radius: 8px;
                    min-height: 50px;
                }
            """)
    
    def _sync_from_state(self):
        """Sync from state"""
        self._update_display(self.state.x_column)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-dgs-zone"):
            event.acceptProposedAction()
            self.x_column_frame.setStyleSheet("""
                QFrame {
                    background: #D1FAE5;
                    border: 2px solid #10B981;
                    border-radius: 8px;
                    min-height: 50px;
                }
            """)
    
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
        self.setObjectName("GroupZone")
        self.setFixedWidth(140)
        self.setAcceptDrops(True)
        
        self._setup_ui()
        self._connect_signals()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #GroupZone {
                background: #F8FAFC;
                border: none;
                border-radius: 8px;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header (no float button for internal sections)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon = QLabel("📁")
        icon.setStyleSheet("font-size: 16px; background: transparent;")
        header_layout.addWidget(icon)

        header = QLabel("Group By")
        header.setStyleSheet("""
            font-weight: 600;
            font-size: 13px;
            color: #E6E9EF;
            background: transparent;
        """)
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Help text
        help_label = QLabel("Drag columns to group")
        help_label.setStyleSheet("""
            color: #64748B;
            font-size: 10px;
            background: transparent;
        """)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # List widget
        self.list_widget = ChipListWidget(zone_id="group", accept_drop=True, allow_reorder=True)
        self.list_widget.setMaximumHeight(130)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
        """)
        self.list_widget.item_dropped.connect(self._on_column_dropped)
        self.list_widget.order_changed.connect(self._on_order_changed)
        layout.addWidget(self.list_widget, 1)

        # Clear button
        remove_btn = QPushButton("✕ Clear")
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #EF4444;
                border: 1px solid #FCA5A5;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 500;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #FEF2F2;
                border-color: #EF4444;
            }
        """)
        remove_btn.clicked.connect(self.state.clear_group_zone)
        layout.addWidget(remove_btn)
    
    def _connect_signals(self):
        self.state.group_zone_changed.connect(self._sync_from_state)
    
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
        self.setObjectName("ValueZone")
        self.setMinimumWidth(160)
        self.setAcceptDrops(True)
        
        self._setup_ui()
        self._connect_signals()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #ValueZone {
                background: #FAF5FF;
                border: none;
                border-radius: 8px;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header (no float button for internal sections)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon = QLabel("📊")
        icon.setStyleSheet("font-size: 16px; background: transparent;")
        header_layout.addWidget(icon)

        header = QLabel("Y-Axis Values")
        header.setStyleSheet("""
            font-weight: 600;
            font-size: 13px;
            color: #581C87;
            background: transparent;
        """)
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Help text
        help_label = QLabel("Drag numeric columns for Y values")
        help_label.setStyleSheet("""
            color: #9333EA;
            font-size: 10px;
            background: transparent;
        """)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Chip list
        self.list_widget = ChipListWidget(zone_id="value", accept_drop=True)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
        """)
        self.list_widget.item_dropped.connect(self._on_column_dropped)
        layout.addWidget(self.list_widget, 1)
    
    def _connect_signals(self):
        self.state.value_zone_changed.connect(self._sync_from_state)
    
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
        self.setObjectName("HoverZone")
        self.setMinimumWidth(150)
        self.setAcceptDrops(True)

        self._setup_ui()
        self._connect_signals()
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            #HoverZone {
                background: #FEFCE8;
                border: none;
                border-radius: 8px;
            }
        """)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header (no float button)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon = QLabel("💬")
        icon.setStyleSheet("font-size: 16px; background: transparent;")
        header_layout.addWidget(icon)

        header = QLabel("Hover Data")
        header.setStyleSheet("""
            font-weight: 600;
            font-size: 13px;
            color: #854D0E;
            background: transparent;
        """)
        header_layout.addWidget(header)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Help text
        help_label = QLabel("Drag columns to show\non hover tooltip")
        help_label.setStyleSheet("""
            color: #A16207;
            font-size: 10px;
            background: transparent;
        """)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # List widget for hover columns
        self.list_widget = ChipListWidget(zone_id="hover", accept_drop=True)
        self.list_widget.setMaximumHeight(120)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
        """)
        self.list_widget.item_dropped.connect(self._on_column_dropped)
        layout.addWidget(self.list_widget, 1)

        # Clear button
        clear_btn = QPushButton("✕ Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #CA8A04;
                border: 1px solid #FACC15;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 500;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #FEF9C3;
                border-color: #EAB308;
            }
        """)
        clear_btn.clicked.connect(self._clear_all)
        layout.addWidget(clear_btn)

    def _connect_signals(self):
        self.state.hover_zone_changed.connect(self._sync_from_state)

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


# ==================== Data Table View ====================

class DataTableView(QTableView):
    """데이터 테이블 뷰 - Minimal Design"""
    
    column_dragged = Signal(str)
    column_action = Signal(str)
    rows_selected = Signal(list)
    exclude_value = Signal(str, object)  # column, value
    hide_column = Signal(str)  # column name
    exclude_column = Signal(str)  # column name (drop from data)
    column_order_changed = Signal(list)
    
    def __init__(self):
        super().__init__()
        
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setDragEnabled(True)
        
        # Compact, clean style
        self.setStyleSheet("""
            QTableView {
                background: #323D4A;
                alternate-background-color: #2B3440;
                selection-background-color: #3A4E63;
                selection-color: #E6E9EF;
                gridline-color: #3E4A59;
                border: none;
                border-radius: 8px;
                color: #E6E9EF;
            }
            QTableView::item {
                padding: 4px 8px;
                color: #E6E9EF;
            }
            QTableView::item:selected {
                background: #3A4E63;
                color: #E6E9EF;
            }
            QTableView::item:hover {
                background: #384554;
            }
            QHeaderView::section {
                background: #2B3440;
                border: none;
                border-bottom: 1px solid #3E4A59;
                padding: 6px 8px;
                font-weight: 600;
                font-size: 11px;
                color: #E6E9EF;
            }
            QHeaderView::section:hover {
                background: #3A4654;
                color: #F2F4F8;
            }
        """)
        
        # Context menu for cells
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_cell_menu)
        
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._show_header_menu)
        self.horizontalHeader().sectionPressed.connect(self._on_header_pressed)
        self.horizontalHeader().sectionMoved.connect(self._on_header_moved)
        self.horizontalHeader().installEventFilter(self)
        self._header_drag_start = None
        self._header_drag_col = None
        
        self.selectionModel_connected = False
    
    def setModel(self, model):
        super().setModel(model)
        if model and not self.selectionModel_connected:
            self.selectionModel().selectionChanged.connect(self._on_selection_changed)
            self.selectionModel_connected = True
    
    def _on_header_pressed(self, logical_index: int):
        # Store for potential drag-to-zone (reorder still handled by header)
        model = self.model()
        if model:
            self._header_drag_col = model.get_column_name(logical_index)

    def _on_header_moved(self, logical_index: int, old_visual_index: int, new_visual_index: int):
        model = self.model()
        header = self.horizontalHeader()
        if not model or not header:
            return
        order = []
        for visual in range(header.count()):
            logical = header.logicalIndex(visual)
            name = model.get_column_name(logical)
            if name:
                order.append(name)
        if order:
            self.column_order_changed.emit(order)

    def eventFilter(self, obj, event):
        if obj is self.horizontalHeader():
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._header_drag_start = event.pos()
            elif event.type() == QEvent.MouseMove and (event.buttons() & Qt.LeftButton):
                if self._header_drag_start is not None and self._header_drag_col:
                    distance = (event.pos() - self._header_drag_start).manhattanLength()
                    # Start drag if moved enough distance - both inside or outside header area
                    if distance >= QApplication.startDragDistance() * 2:
                        drag = QDrag(self)
                        mime = QMimeData()
                        mime.setText(self._header_drag_col)
                        mime.setData("application/x-dgs-zone", _build_drag_payload("table", self._header_drag_col, None))
                        drag.setMimeData(mime)
                        drag.exec(Qt.CopyAction)
                        self._header_drag_start = None
                        self._header_drag_col = None
                        return True
            elif event.type() == QEvent.MouseButtonRelease:
                self._header_drag_start = None
        return super().eventFilter(obj, event)
    
    def _on_selection_changed(self, selected, deselected):
        indexes = self.selectionModel().selectedRows()
        rows = [idx.row() for idx in indexes]
        self.rows_selected.emit(rows)
    
    def _show_header_menu(self, pos):
        logical_index = self.horizontalHeader().logicalIndexAt(pos)
        model = self.model()
        if not model:
            return
        
        column_name = model.get_column_name(logical_index)
        if not column_name:
            return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1E293B;
                color: #E2E8F0;
                border: 1px solid #3E4A59;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 16px;
                border-radius: 4px;
                color: #E2E8F0;
            }
            QMenu::item:selected {
                background: #334155;
                color: #E2E8F0;
            }
            QMenu::separator {
                height: 1px;
                background: #3E4A59;
                margin: 4px 8px;
            }
        """)
        
        sort_asc = QAction("↑ Sort Ascending", self)
        sort_asc.triggered.connect(lambda: self.sortByColumn(logical_index, Qt.AscendingOrder))
        menu.addAction(sort_asc)
        
        sort_desc = QAction("↓ Sort Descending", self)
        sort_desc.triggered.connect(lambda: self.sortByColumn(logical_index, Qt.DescendingOrder))
        menu.addAction(sort_desc)
        
        menu.addSeparator()
        
        exclude_col = QAction("🚫 Exclude Column", self)
        exclude_col.triggered.connect(lambda: self.exclude_column.emit(column_name))
        menu.addAction(exclude_col)

        menu.addSeparator()

        # Set as submenu
        set_as_menu = menu.addMenu("📌 Set as...")
        
        set_x = QAction("📐 X-Axis", self)
        set_x.triggered.connect(lambda: self.column_dragged.emit(f"X:{column_name}"))
        set_as_menu.addAction(set_x)

        set_y = QAction("📊 Y-Axis Value", self)
        set_y.triggered.connect(lambda: self.column_dragged.emit(f"V:{column_name}"))
        set_as_menu.addAction(set_y)

        set_g = QAction("📁 Group By", self)
        set_g.triggered.connect(lambda: self.column_dragged.emit(f"G:{column_name}"))
        set_as_menu.addAction(set_g)

        set_h = QAction("💬 Hover Data", self)
        set_h.triggered.connect(lambda: self.column_dragged.emit(f"H:{column_name}"))
        set_as_menu.addAction(set_h)
        
        menu.exec(self.horizontalHeader().mapToGlobal(pos))
    
    def _show_cell_menu(self, pos):
        """셀 우클릭 메뉴"""
        index = self.indexAt(pos)
        if not index.isValid():
            return
        
        model = self.model()
        if not model:
            return
        
        column_name = model.get_column_name(index.column())
        cell_value = model.data(index, Qt.DisplayRole)
        
        if not column_name:
            return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1E293B;
                color: #E2E8F0;
                border: 1px solid #3E4A59;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 16px;
                border-radius: 4px;
                color: #E2E8F0;
            }
            QMenu::item:selected {
                background: #334155;
                color: #E2E8F0;
            }
            QMenu::separator {
                height: 1px;
                background: #3E4A59;
                margin: 4px 8px;
            }
        """)
        
        # Filter options
        if cell_value:
            display_val = str(cell_value)[:20] + "..." if len(str(cell_value)) > 20 else str(cell_value)
            
            filter_eq = QAction(f"🔍 Filter: {column_name} = \"{display_val}\"", self)
            filter_eq.triggered.connect(lambda: self.exclude_value.emit(column_name, ("eq", cell_value)))
            menu.addAction(filter_eq)
            
            filter_ne = QAction(f"🚫 Exclude: {column_name} ≠ \"{display_val}\"", self)
            filter_ne.triggered.connect(lambda: self.exclude_value.emit(column_name, ("ne", cell_value)))
            menu.addAction(filter_ne)
            
            menu.addSeparator()
        
        # Copy
        copy_action = QAction("📋 Copy", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(str(cell_value) if cell_value else ""))
        menu.addAction(copy_action)
        
        menu.exec(self.viewport().mapToGlobal(pos))


# ==================== Filter Bar ====================

class FilterBar(QFrame):
    """활성 필터 표시 바"""
    
    filter_removed = Signal(int)  # filter index
    clear_all = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("FilterBar")
        self._setup_ui()
        self._apply_style()
        self._connect_signals()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #FilterBar {
                background: #FEF3C7;
                border: none;
                border-radius: 6px;
                padding: 2px;
            }
        """)
    
    def _setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(8, 4, 8, 4)
        self.main_layout.setSpacing(6)
        
        # Filter icon
        icon = QLabel("🔍")
        icon.setStyleSheet("font-size: 14px; background: transparent;")
        self.main_layout.addWidget(icon)
        
        # Filters container
        self.filters_layout = QHBoxLayout()
        self.filters_layout.setSpacing(4)
        self.main_layout.addLayout(self.filters_layout)
        
        self.main_layout.addStretch()
        
        # Clear all button
        clear_btn = QPushButton("Clear All")
        clear_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #B45309;
                border: 1px solid #F59E0B;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #FDE68A;
            }
        """)
        clear_btn.clicked.connect(self.clear_all.emit)
        self.main_layout.addWidget(clear_btn)
        
        self.setVisible(False)  # Hidden by default
    
    def _connect_signals(self):
        self.state.filter_changed.connect(self._update_filters)
    
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
        chip.setStyleSheet(f"""
            QFrame {{
                background: {'#FEF3C7' if filter_cond.enabled else '#3A4654'};
                border: 1px solid {'#F59E0B' if filter_cond.enabled else '#D1D5DB'};
                border-radius: 12px;
                padding: 2px;
            }}
        """)
        
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
        label.setStyleSheet(f"""
            font-size: 11px;
            color: {'#92400E' if filter_cond.enabled else '#C2C8D1'};
            background: transparent;
        """)
        layout.addWidget(label)
        
        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #9CA3AF;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #EF4444;
            }
        """)
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
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #HiddenColumnsBar {
                background: #1E3A5F;
                border: none;
                border-radius: 6px;
                padding: 2px;
            }
        """)
    
    def _setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(8, 4, 8, 4)
        self.main_layout.setSpacing(6)
        
        # Icon
        icon = QLabel("👁")
        icon.setStyleSheet("font-size: 14px; background: transparent;")
        self.main_layout.addWidget(icon)
        
        label = QLabel("Hidden columns:")
        label.setStyleSheet("font-size: 11px; color: #A5B4FC; background: transparent;")
        self.main_layout.addWidget(label)
        
        # Columns container
        self.columns_layout = QHBoxLayout()
        self.columns_layout.setSpacing(4)
        self.main_layout.addLayout(self.columns_layout)
        
        self.main_layout.addStretch()
        
        # Show all button
        show_all_btn = QPushButton("Show All")
        show_all_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #4338CA;
                border: 1px solid #59B8E3;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #E0E7FF;
            }
        """)
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
            more.setStyleSheet("font-size: 10px; color: #C2C8D1; background: transparent;")
            self.columns_layout.addWidget(more)
    
    def _create_column_chip(self, column: str) -> QWidget:
        chip = QFrame()
        chip.setStyleSheet("""
            QFrame {
                background: #2D3748;
                border: 1px solid #4A5568;
                border-radius: 10px;
            }
        """)
        
        layout = QHBoxLayout(chip)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(2)
        
        label = QLabel(column[:12] + "..." if len(column) > 12 else column)
        label.setStyleSheet("font-size: 10px; color: #A5B4FC; background: transparent;")
        label.setToolTip(column)
        layout.addWidget(label)
        
        show_btn = QPushButton("👁")
        show_btn.setFixedSize(16, 16)
        show_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #E0E7FF;
            }
        """)
        show_btn.setToolTip(f"Show {column}")
        show_btn.clicked.connect(lambda: self.show_column.emit(column))
        layout.addWidget(show_btn)
        
        return chip


# ==================== Table Panel ====================

class TablePanel(QWidget):
    """
    Table Panel

    구조:
    ┌──────────┬──────────┬─────────────────────┬────────────┬──────────┐
    │  X Zone  │  Group   │     Data Table      │   Values   │  Hover   │
    │ (150px)  │  Zone    │                     │   Zone     │  Zone    │
    │          │ (150px)  │                     │  (180px)   │ (150px)  │
    └──────────┴──────────┴─────────────────────┴────────────┴──────────┘
    """

    file_dropped = Signal(str)
    window_changed = Signal()

    def __init__(self, state: AppState, engine: DataEngine, graph_panel=None):
        super().__init__()
        self.state = state
        self.engine = engine
        self.graph_panel = graph_panel

        self.setAcceptDrops(True)

        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setStyleSheet("QSplitter::handle { background: #3E4A59; }")

        # Left panel: X Zone + Group Zone
        self.left_panel = QWidget()
        left_layout = QHBoxLayout(self.left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        # X Zone
        self.x_zone = XAxisZone(self.state)
        left_layout.addWidget(self.x_zone)

        # Group Zone
        self.group_zone = GroupZone(self.state)
        left_layout.addWidget(self.group_zone)

        self.splitter.addWidget(self.left_panel)
        
        # Table area (center)
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
        search_container.setStyleSheet("QFrame { background: transparent; border: none; }")
        search_container_layout = QHBoxLayout(search_container)
        search_container_layout.setContentsMargins(0, 0, 0, 0)
        search_container_layout.setSpacing(0)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search data...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 8px 14px;
                padding-right: 30px;
                font-size: 12px;
                color: #334155;
            }
            QLineEdit:focus {
                border: 2px solid #59B8E3;
                background: #FAFAFF;
            }
        """)
        search_container_layout.addWidget(self.search_input)
        
        # Clear button (inside search input)
        self.search_clear_btn = QPushButton("×")
        self.search_clear_btn.setFixedSize(20, 20)
        self.search_clear_btn.setStyleSheet("""
            QPushButton {
                background: #E2E8F0;
                color: #64748B;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #CBD5E1;
                color: #334155;
            }
        """)
        self.search_clear_btn.setToolTip("Clear search")
        self.search_clear_btn.clicked.connect(self._clear_search)
        self.search_clear_btn.hide()  # Hidden when empty
        search_container_layout.addWidget(self.search_clear_btn)
        
        search_layout.addWidget(search_container, 1)
        
        # Search result count label
        self.search_result_label = QLabel("")
        self.search_result_label.setStyleSheet("""
            QLabel {
                color: #64748B;
                font-size: 11px;
                padding: 0 8px;
                background: transparent;
            }
        """)
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
        
        expand_btn = QPushButton("▼ Expand")
        expand_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #59B8E3;
                border: 1px solid #59B8E3;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 500;
            }
            QPushButton:hover { background: #3A4654; }
        """)
        expand_btn.clicked.connect(self._expand_all)
        toolbar.addWidget(expand_btn)
        
        collapse_btn = QPushButton("▶ Collapse")
        collapse_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #59B8E3;
                border: 1px solid #59B8E3;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 500;
            }
            QPushButton:hover { background: #3A4654; }
        """)
        collapse_btn.clicked.connect(self._collapse_all)
        toolbar.addWidget(collapse_btn)
        
        # Limit to Marking toggle button
        self.limit_marking_btn = QPushButton("🔗 Limit to Marking")
        self.limit_marking_btn.setCheckable(True)
        self.limit_marking_btn.setChecked(False)
        self.limit_marking_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #C2C8D1;
                border: 1px solid #D1D5DB;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #FEF3C7;
                border-color: #F59E0B;
                color: #92400E;
            }
            QPushButton:checked {
                background: #FEF3C7;
                border-color: #F59E0B;
                color: #92400E;
                font-weight: 600;
            }
        """)
        self.limit_marking_btn.setToolTip("Show only marked/selected rows in table")
        self.limit_marking_btn.clicked.connect(self._on_limit_marking_toggled)
        toolbar.addWidget(self.limit_marking_btn)

        # Window controls (for large datasets)
        self.window_widget = QWidget()
        window_layout = QHBoxLayout(self.window_widget)
        window_layout.setContentsMargins(8, 0, 8, 0)
        window_layout.setSpacing(6)

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
        self.window_label.setStyleSheet("color: #C2C8D1; font-size: 10px;")
        window_layout.addWidget(self.window_label)

        self._window_debounce = QTimer(self)
        self._window_debounce.setSingleShot(True)
        self._window_debounce.setInterval(250)
        self._window_debounce.timeout.connect(self._apply_window_debounced)

        self.window_widget.setVisible(False)
        toolbar.addWidget(self.window_widget)
        
        toolbar.addStretch()
        
        self.group_info_label = QLabel("")
        self.group_info_label.setStyleSheet("color: #C2C8D1; font-size: 10px;")
        toolbar.addWidget(self.group_info_label)
        
        table_layout.addLayout(toolbar)
        
        # Table view
        self.table_view = DataTableView()
        self.table_model = PolarsTableModel()
        self.grouped_model = None
        self.table_view.setModel(self.table_model)
        self.table_view.clicked.connect(self._on_table_clicked)
        
        table_layout.addWidget(self.table_view)

        self.splitter.addWidget(table_container)

        # Right panel: Value Zone + Hover Zone
        self.right_panel = QWidget()
        right_layout = QHBoxLayout(self.right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(6)

        # Value Zone
        self.value_zone = ValueZone(self.state)
        right_layout.addWidget(self.value_zone)

        # Hover Zone
        self.hover_zone = HoverZone(self.state)
        right_layout.addWidget(self.hover_zone)

        self.splitter.addWidget(self.right_panel)

        # Splitter sizes
        self.splitter.setSizes([280, 500, 360])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        layout.addWidget(self.splitter)
    
    def _connect_signals(self):
        self.table_view.rows_selected.connect(self._on_rows_selected)
        self.table_view.exclude_value.connect(self._on_exclude_value)
        self.table_view.hide_column.connect(self._on_hide_column)
        self.table_view.exclude_column.connect(self._on_exclude_column)
        self.table_view.column_dragged.connect(self._on_column_action)
        self.table_view.column_order_changed.connect(self._on_column_order_changed)
        self.state.selection_changed.connect(self._on_state_selection_changed)
        self.state.group_zone_changed.connect(self._on_group_zone_changed)
        self.state.value_zone_changed.connect(self._on_value_zone_changed)
        self.state.filter_changed.connect(self._on_filter_changed)
        self.state.hover_zone_changed.connect(self._on_hover_zone_changed)
        self.state.limit_to_marking_changed.connect(self._on_limit_to_marking_changed)
        self.state.selection_changed.connect(self._on_selection_for_limit_marking)

    def _on_hover_zone_changed(self):
        """Hover zone changed - trigger refresh if needed"""
        pass  # Hover data is managed by GraphPanel

    def _on_column_order_changed(self, order: List[str]):
        """Update column order in state and refresh model"""
        if not order:
            return
        self.state.set_column_order(order)
        # Refresh table to apply new order
        self._update_table_model(self.engine.df if self.engine.is_loaded else None)

    def set_data(self, df: Optional[pl.DataFrame]):
        # 기존 캐시 클리어
        self.table_model._column_cache.clear()
        if self.grouped_model:
            self.grouped_model._row_cache = []
        self._update_table_model(df)
        self._update_window_controls()
    
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

        hidden_cols = self.state._hidden_columns
        if hidden_cols:
            visible_cols = [col for col in df.columns if col not in hidden_cols]
            if visible_cols:
                df = df.select(visible_cols)

        if self.state.group_columns:
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
            self.group_info_label.setStyleSheet("""
                color: #59B8E3;
                font-size: 10px;
                background: #1E3A5F;
                padding: 3px 8px;
                border-radius: 8px;
            """)
        else:
            self.table_model.set_dataframe(df)
            self.table_view.setModel(self.table_model)
            # 데이터가 잘렸는지 표시
            actual_rows = self.table_model.get_actual_row_count()
            displayed_rows = self.table_model.rowCount()
            if actual_rows > displayed_rows:
                self.group_info_label.setText(f"Showing {displayed_rows:,} of {actual_rows:,} rows")
                self.group_info_label.setStyleSheet("""
                    color: #F59E0B;
                    font-size: 10px;
                    background: #3D2F0A;
                    padding: 3px 8px;
                    border-radius: 8px;
                """)
            else:
                self.group_info_label.setText("")

        header = self.table_view.horizontalHeader()
        for i in range(min(10, self.table_view.model().columnCount())):
            header.resizeSection(i, 120)
    
    def clear(self):
        self.table_model.set_dataframe(None)
        if self.grouped_model:
            self.grouped_model.set_data(None)
        self.group_info_label.setText("")
    
    def _on_search_text_changed(self, text: str):
        """Handle search text change with debouncing"""
        self._pending_search_text = text
        
        # Show/hide clear button
        if text:
            self.search_clear_btn.show()
        else:
            self.search_clear_btn.hide()
            self.search_result_label.setText("")
        
        # Start debounce timer
        self._search_debounce_timer.start()
    
    def _execute_search(self):
        """Execute search after debounce delay"""
        text = self._pending_search_text
        
        if not self.engine.is_loaded:
            return
        
        if not text:
            self._update_table_model(self.engine.df)
            self.search_result_label.setText("")
            return
        
        result = self.engine.search(text)
        
        # Update result count
        if result is not None:
            count = len(result)
            if count == 0:
                self.search_result_label.setText("No results")
                self.search_result_label.setStyleSheet("""
                    QLabel {
                        color: #EF4444;
                        font-size: 11px;
                        padding: 0 8px;
                        background: transparent;
                    }
                """)
            else:
                self.search_result_label.setText(f"{count:,} results")
                self.search_result_label.setStyleSheet("""
                    QLabel {
                        color: #10B981;
                        font-size: 11px;
                        padding: 0 8px;
                        background: transparent;
                    }
                """)
        
        self._update_table_model(result)
    
    def _clear_search(self):
        """Clear search input and restore full data"""
        self.search_input.clear()
        self.search_clear_btn.hide()
        self.search_result_label.setText("")
        self._search_debounce_timer.stop()
        if self.engine.is_loaded:
            self._update_table_model(self.engine.df)
    
    def _on_search(self, text: str):
        """Legacy search handler (kept for compatibility)"""
        self._on_search_text_changed(text)
    
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
        if self.engine.is_loaded:
            self._update_table_model(self.engine.df)
    
    def _on_value_zone_changed(self):
        if self.engine.is_loaded and self.state.group_columns:
            self._update_table_model(self.engine.df)
    
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
    
    # ==================== Filter & Column Handlers ====================
    
    def _on_exclude_value(self, column: str, filter_info: tuple):
        """Handle exclude value from cell context menu"""
        operator, value = filter_info
        self.state.add_filter(column, operator, value)
    
    def _on_hide_column(self, column: str):
        """Handle hide column from header context menu"""
        self.state.toggle_column_visibility(column)
        self._update_hidden_bar()
        self._update_table_model()

    def _on_exclude_column(self, column: str):
        """Handle exclude (drop) column from data"""
        if not self.engine.is_loaded or not column:
            return
        # Confirm destructive action
        reply = QMessageBox.question(
            self, "Exclude Column",
            f"Remove column '{column}' from the active dataset?\n\nThis cannot be undone (reload to restore).",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            # Drop from active dataset df
            df = self.engine.df
            if df is None or column not in df.columns:
                return
            self.engine._df = df.drop(column)
            # Update active dataset in engine
            if self.engine.active_dataset_id and self.engine.active_dataset_id in self.engine._datasets:
                ds = self.engine._datasets[self.engine.active_dataset_id]
                ds.df = self.engine._df
                ds.lazy_df = None
            # Clean state references
            if self.state.x_column == column:
                self.state.set_x_column(None)
            # Remove from groups/values/hover
            self.state._group_columns = [g for g in self.state.group_columns if g.name != column]
            self.state._value_columns = [v for v in self.state.value_columns if v.name != column]
            if column in self.state.hover_columns:
                self.state.remove_hover_column(column)
            # Hidden/column order cleanup
            if column in self.state._hidden_columns:
                self.state._hidden_columns.remove(column)
            if column in self.state.get_column_order():
                self.state.set_column_order([c for c in self.state.get_column_order() if c != column])

            # Refresh UI
            self._update_table_model(self.engine.df)
            self.graph_panel.refresh() if hasattr(self, 'graph_panel') else None
        except Exception as e:
            QMessageBox.warning(self, "Exclude Column", f"Failed to exclude column: {e}")
    
    def _on_column_action(self, action: str):
        """Handle column actions from context menu"""
        if action.startswith("X:"):
            column = action[2:]
            self.state.set_x_column(column)
        elif action.startswith("G:"):
            column = action[2:]
            self.state.add_group_column(column)
        elif action.startswith("V:"):
            column = action[2:]
            self.state.add_value_column(column)
        elif action.startswith("H:"):
            column = action[2:]
            self.state.add_hover_column(column)
    
    def _on_filter_removed(self, index: int):
        """Handle filter removal"""
        self.state.remove_filter(index)
    
    def _on_clear_filters(self):
        """Handle clear all filters"""
        self.state.clear_filters()
    
    def _on_filter_changed(self):
        """Handle filter state change"""
        if self.engine.is_loaded:
            self._apply_filters_and_update()
    
    def _apply_filters_and_update(self):
        """Apply filters to data and update table"""
        df = self.engine.df
        if df is None:
            return

        # Apply all enabled filters sequentially
        filtered_df = df
        for f in self.state.filters:
            if not f.enabled:
                continue
            try:
                col = pl.col(f.column)

                if f.operator == 'eq':
                    filtered_df = filtered_df.filter(col == f.value)
                elif f.operator == 'ne':
                    filtered_df = filtered_df.filter(col != f.value)
                elif f.operator == 'gt':
                    filtered_df = filtered_df.filter(col > f.value)
                elif f.operator == 'lt':
                    filtered_df = filtered_df.filter(col < f.value)
                elif f.operator == 'ge':
                    filtered_df = filtered_df.filter(col >= f.value)
                elif f.operator == 'le':
                    filtered_df = filtered_df.filter(col <= f.value)
                elif f.operator == 'contains':
                    filtered_df = filtered_df.filter(col.str.contains(str(f.value)))
            except Exception as e:
                print(f"Filter error: {e}")
                continue

        # Update visible rows count in state
        self.state.set_visible_rows(len(filtered_df))
        self._update_table_model(filtered_df)
    
    def _on_show_column(self, column: str):
        """Show a hidden column"""
        self.state.toggle_column_visibility(column)
        self._update_hidden_bar()
        self._update_table_model()
    
    def _on_show_all_columns(self):
        """Show all hidden columns"""
        # Need to add a method to state or iterate
        hidden = list(self.state._hidden_columns)
        for col in hidden:
            self.state.toggle_column_visibility(col)
        self._update_hidden_bar()
        self._update_table_model()
    
    def _update_hidden_bar(self):
        """Update hidden columns bar"""
        hidden = list(self.state._hidden_columns)
        self.hidden_bar.update_hidden_columns(hidden)
    
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
                # Create boolean mask
                mask = pl.Series([i in valid_indices for i in range(len(df))])
                filtered_df = df.filter(mask)
                
                # Update label
                self.group_info_label.setText(f"Showing {len(valid_indices)} marked rows")
                self.group_info_label.setStyleSheet("""
                    color: #92400E;
                    font-size: 10px;
                    background: #FEF3C7;
                    padding: 3px 8px;
                    border-radius: 8px;
                """)
                
                self._update_table_model(filtered_df)
            else:
                # No valid selection, show empty or all
                self._update_table_model(df)
        else:
            # Show all data
            self._apply_filters_and_update()
    
    # ==================== Windowed Loading ====================

    def _update_window_controls(self):
        if not self.engine.is_loaded or not self.engine.is_windowed:
            self.window_widget.setVisible(False)
            return

        total_rows = self.engine.total_rows
        window_size = self.engine.window_size
        max_start = max(0, total_rows - window_size)

        self.window_widget.setVisible(True)
        self.window_slider.blockSignals(True)
        self.window_slider.setMinimum(0)
        self.window_slider.setMaximum(max_start)
        self.window_slider.setValue(min(self.engine.window_start, max_start))
        self.window_slider.blockSignals(False)

        size_label = f"{int(window_size/1000)}k"
        if size_label in [self.window_size_combo.itemText(i) for i in range(self.window_size_combo.count())]:
            self.window_size_combo.blockSignals(True)
            self.window_size_combo.setCurrentText(size_label)
            self.window_size_combo.blockSignals(False)

        self._set_window_label(self.engine.window_start, window_size, total_rows)

    def _set_window_label(self, start: int, size: int, total: int):
        end = min(start + size, total) if total else start + size
        self.window_label.setText(f"{start + 1:,}–{end:,} / {total:,}")

    def _apply_window(self, start: int):
        if not self.engine.is_windowed:
            return

        total_rows = self.engine.total_rows
        window_size = self.engine.window_size
        max_start = max(0, total_rows - window_size)
        start = max(0, min(start, max_start))

        if self.engine.set_window(start, window_size):
            self.state.clear_selection()
            self.state.set_visible_rows(len(self.engine.df))
            self.set_data(self.engine.df)
            self.window_changed.emit()

    def _on_window_prev(self):
        self._apply_window(self.engine.window_start - self.engine.window_size)

    def _on_window_next(self):
        self._apply_window(self.engine.window_start + self.engine.window_size)

    def _on_window_slider_changed(self, value: int):
        if not self.engine.is_windowed:
            return
        self._set_window_label(value, self.engine.window_size, self.engine.total_rows)
        self._window_debounce.start()

    def _on_window_slider_released(self):
        self._window_debounce.stop()
        self._apply_window(self.window_slider.value())

    def _apply_window_debounced(self):
        self._apply_window(self.window_slider.value())

    def _on_window_size_changed(self, text: str):
        if not self.engine.is_windowed:
            return
        size = int(text.replace("k", "")) * 1000
        current_start = self.engine.window_start
        self.engine.set_window(current_start, size)
        self._update_window_controls()
        self.state.clear_selection()
        self.state.set_visible_rows(len(self.engine.df))
        self.set_data(self.engine.df)
        self.window_changed.emit()

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
