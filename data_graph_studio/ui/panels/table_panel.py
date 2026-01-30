"""
Table Panel - 테이블 뷰 + X Zone + Group Zone + Value Zone
"""

from typing import Optional, List, Dict, Any
import polars as pl

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QTableView, QHeaderView, QAbstractItemView, QMenu,
    QLineEdit, QComboBox, QPushButton, QScrollArea,
    QSplitter, QSizePolicy, QApplication, QListWidget,
    QListWidgetItem, QGroupBox
)
from PySide6.QtCore import (
    Qt, Signal, Slot, QAbstractTableModel, QModelIndex,
    QMimeData, QByteArray
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
    """

    # 테이블에 표시할 최대 행 수 (성능 보장)
    MAX_DISPLAY_ROWS = 100_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: Optional[pl.DataFrame] = None
        self._visible_columns: List[str] = []
        self._row_count = 0
        self._actual_row_count = 0  # 실제 데이터 행 수
        # 컬럼 기반 캐시: column_index -> list of values
        self._column_cache: Dict[int, list] = {}
        self._cache_valid = False

    def set_dataframe(self, df: Optional[pl.DataFrame]):
        self.beginResetModel()
        self._df = df
        self._column_cache.clear()
        self._cache_valid = False
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
                    return self._visible_columns[section]
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


class DraggableListWidget(QListWidget):
    """드래그 가능한 리스트 위젯"""
    
    item_dropped = Signal(str)
    item_removed = Signal(str)
    order_changed = Signal(list)
    
    def __init__(self, accept_drop: bool = True, single_item: bool = False):
        super().__init__()
        self.single_item = single_item
        self.setDragEnabled(True)
        self.setAcceptDrops(accept_drop)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop if accept_drop else QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
    
    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasText():
            column_name = event.mimeData().text()
            
            # Single item mode: replace existing
            if self.single_item and self.count() > 0:
                old_name = self.item(0).text()
                self.clear()
                self.item_removed.emit(old_name)
            
            self.item_dropped.emit(column_name)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
            self.order_changed.emit([self.item(i).text() for i in range(self.count())])
    
    def add_column(self, name: str):
        # 중복 체크
        for i in range(self.count()):
            if self.item(i).text() == name:
                return
        
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
        self.addItem(item)
    
    def remove_selected(self):
        current = self.currentItem()
        if current:
            name = current.text()
            self.takeItem(self.row(current))
            self.item_removed.emit(name)


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
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ECFDF5, stop:1 #D1FAE5);
                border: 1px solid #6EE7B7;
                border-radius: 12px;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header with float button
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

        self.float_btn = FloatButton()
        header_layout.addWidget(self.float_btn)

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
        
        # Current X column display
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
        x_layout.setContentsMargins(10, 10, 10, 10)
        
        self.x_label = QLabel("(Index)")
        self.x_label.setAlignment(Qt.AlignCenter)
        self.x_label.setStyleSheet("""
            color: #94A3B8;
            font-size: 12px;
            font-style: italic;
            background: transparent;
        """)
        x_layout.addWidget(self.x_label)
        
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
        if column_name:
            self.x_label.setText(f"📊 {column_name}")
            self.x_label.setStyleSheet("""
                color: #047857;
                font-size: 12px;
                font-weight: 600;
                font-style: normal;
                background: transparent;
            """)
            self.x_column_frame.setStyleSheet("""
                QFrame {
                    background: #ECFDF5;
                    border: 2px solid #10B981;
                    border-radius: 8px;
                    min-height: 50px;
                }
            """)
        else:
            self.x_label.setText("(Index)")
            self.x_label.setStyleSheet("""
                color: #94A3B8;
                font-size: 12px;
                font-style: italic;
                background: transparent;
            """)
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
        if event.mimeData().hasText():
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
        if event.mimeData().hasText():
            column_name = event.mimeData().text()
            self._set_x_column(column_name)
            event.acceptProposedAction()


# ==================== Group Zone ====================

class GroupZone(QFrame):
    """Group Zone - Modern drag & drop zone"""
    
    group_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("GroupZone")
        self.setFixedWidth(150)
        self.setAcceptDrops(True)
        
        self._setup_ui()
        self._connect_signals()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #GroupZone {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #F8FAFC, stop:1 #F1F5F9);
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header with icon and float button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        icon = QLabel("📁")
        icon.setStyleSheet("font-size: 16px; background: transparent;")
        header_layout.addWidget(icon)

        header = QLabel("Group By")
        header.setStyleSheet("""
            font-weight: 600;
            font-size: 13px;
            color: #1E293B;
            background: transparent;
        """)
        header_layout.addWidget(header)
        header_layout.addStretch()

        self.float_btn = FloatButton()
        header_layout.addWidget(self.float_btn)

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
        self.list_widget = DraggableListWidget(accept_drop=True)
        self.list_widget.setMaximumHeight(120)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background: white;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 8px 10px;
                margin: 2px 0;
                color: #334155;
                font-weight: 500;
                font-size: 11px;
            }
            QListWidget::item:hover {
                border-color: #6366F1;
                background: #F8FAFC;
            }
            QListWidget::item:selected {
                background: #EEF2FF;
                border-color: #6366F1;
                color: #4338CA;
            }
        """)
        self.list_widget.item_dropped.connect(self._on_column_dropped)
        self.list_widget.item_removed.connect(self._on_column_removed)
        self.list_widget.order_changed.connect(self._on_order_changed)
        layout.addWidget(self.list_widget, 1)
        
        # Remove button
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
        remove_btn.clicked.connect(self.list_widget.remove_selected)
        layout.addWidget(remove_btn)
    
    def _connect_signals(self):
        self.state.group_zone_changed.connect(self._sync_from_state)
    
    def _on_column_dropped(self, column_name: str):
        self.state.add_group_column(column_name)
    
    def _on_column_removed(self, column_name: str):
        self.state.remove_group_column(column_name)
    
    def _on_order_changed(self, new_order: List[str]):
        self.state.reorder_group_columns(new_order)
    
    def _sync_from_state(self):
        self.list_widget.clear()
        for group_col in self.state.group_columns:
            self.list_widget.add_column(group_col.name)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasText():
            column_name = event.mimeData().text()
            self._on_column_dropped(column_name)
            event.acceptProposedAction()


# ==================== Value Zone ====================

class ValueZone(QFrame):
    """Value Zone - Y-axis values"""
    
    value_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("ValueZone")
        self.setMinimumWidth(180)
        self.setAcceptDrops(True)
        
        self._setup_ui()
        self._connect_signals()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #ValueZone {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FDF4FF, stop:1 #FAF5FF);
                border: 1px solid #E9D5FF;
                border-radius: 12px;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header with float button
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

        self.float_btn = FloatButton()
        header_layout.addWidget(self.float_btn)

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
        
        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        self.value_container = QWidget()
        self.value_container.setStyleSheet("background: transparent;")
        self.value_layout = QVBoxLayout(self.value_container)
        self.value_layout.setContentsMargins(0, 4, 0, 4)
        self.value_layout.setSpacing(6)
        self.value_layout.addStretch()
        
        scroll.setWidget(self.value_container)
        layout.addWidget(scroll, 1)
    
    def _connect_signals(self):
        self.state.value_zone_changed.connect(self._sync_from_state)
    
    def _add_value_card(self, value_col: ValueColumn, index: int):
        """Add value card"""
        card = QFrame()
        card.setObjectName("ValueCard")
        card.setStyleSheet(f"""
            #ValueCard {{
                background: white;
                border: 1px solid {value_col.color}40;
                border-left: 3px solid {value_col.color};
                border-radius: 8px;
            }}
            #ValueCard:hover {{
                background: {value_col.color}08;
                border-color: {value_col.color}60;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(6)
        
        # Header: name + remove
        header_row = QHBoxLayout()
        header_row.setSpacing(4)
        
        name_label = QLabel(f"● {value_col.name[:12]}{'...' if len(value_col.name) > 12 else ''}")
        name_label.setStyleSheet(f"font-weight: 600; font-size: 11px; color: #1E293B; background: transparent;")
        name_label.setToolTip(value_col.name)
        header_row.addWidget(name_label, 1)
        
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(20, 20)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94A3B8;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #FEE2E2;
                color: #EF4444;
            }
        """)
        remove_btn.clicked.connect(lambda: self._remove_value(index))
        header_row.addWidget(remove_btn)
        
        card_layout.addLayout(header_row)
        
        # Aggregation selector
        agg_combo = QComboBox()
        agg_combo.setStyleSheet(f"""
            QComboBox {{
                background: {value_col.color}15;
                border: 1px solid {value_col.color}30;
                border-radius: 5px;
                padding: 4px 8px;
                color: {value_col.color};
                font-weight: 500;
                font-size: 10px;
            }}
            QComboBox:hover {{
                border-color: {value_col.color};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
        """)
        for agg in AggregationType:
            agg_combo.addItem(agg.value.upper(), agg)
        agg_combo.setCurrentText(value_col.aggregation.value.upper())
        agg_combo.currentIndexChanged.connect(
            lambda idx, i=index: self._on_agg_changed(i, agg_combo.currentData())
        )
        card_layout.addWidget(agg_combo)
        
        self.value_layout.insertWidget(self.value_layout.count() - 1, card)
    
    def _on_agg_changed(self, index: int, agg: AggregationType):
        self.state.update_value_column(index, aggregation=agg)
    
    def _remove_value(self, index: int):
        self.state.remove_value_column(index)
    
    def _sync_from_state(self):
        while self.value_layout.count() > 1:
            item = self.value_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        for i, value_col in enumerate(self.state.value_columns):
            self._add_value_card(value_col, i)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasText():
            column_name = event.mimeData().text()
            self.state.add_value_column(column_name)
            event.acceptProposedAction()


# ==================== Data Table View ====================

class DataTableView(QTableView):
    """데이터 테이블 뷰"""
    
    column_dragged = Signal(str)
    rows_selected = Signal(list)
    exclude_value = Signal(str, object)  # column, value
    hide_column = Signal(str)  # column name
    
    def __init__(self):
        super().__init__()
        
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setDragEnabled(True)
        
        # Context menu for cells
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_cell_menu)
        
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._show_header_menu)
        self.horizontalHeader().sectionPressed.connect(self._on_header_pressed)
        
        self.selectionModel_connected = False
    
    def setModel(self, model):
        super().setModel(model)
        if model and not self.selectionModel_connected:
            self.selectionModel().selectionChanged.connect(self._on_selection_changed)
            self.selectionModel_connected = True
    
    def _on_header_pressed(self, logical_index: int):
        model = self.model()
        if model:
            column_name = model.get_column_name(logical_index)
            if column_name:
                drag = QDrag(self)
                mime_data = QMimeData()
                mime_data.setText(column_name)
                drag.setMimeData(mime_data)
                drag.exec(Qt.CopyAction)
    
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
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #EEF2FF;
                color: #4338CA;
            }
            QMenu::separator {
                height: 1px;
                background: #E5E7EB;
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
        
        hide_col = QAction("🚫 Hide Column", self)
        hide_col.triggered.connect(lambda: self.hide_column.emit(column_name))
        menu.addAction(hide_col)
        
        menu.addSeparator()
        
        add_to_x = QAction("📐 Set as X-Axis", self)
        add_to_x.triggered.connect(lambda: self.column_dragged.emit(f"X:{column_name}"))
        menu.addAction(add_to_x)
        
        add_to_group = QAction("📁 Add to Group", self)
        add_to_group.triggered.connect(lambda: self.column_dragged.emit(f"G:{column_name}"))
        menu.addAction(add_to_group)
        
        add_to_value = QAction("📊 Add to Values", self)
        add_to_value.triggered.connect(lambda: self.column_dragged.emit(f"V:{column_name}"))
        menu.addAction(add_to_value)
        
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
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #EEF2FF;
                color: #4338CA;
            }
            QMenu::separator {
                height: 1px;
                background: #E5E7EB;
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
                border: 1px solid #FCD34D;
                border-radius: 8px;
                padding: 4px;
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
                background: {'#FEF3C7' if filter_cond.enabled else '#F3F4F6'};
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
            color: {'#92400E' if filter_cond.enabled else '#6B7280'};
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
                background: #EEF2FF;
                border: 1px solid #C7D2FE;
                border-radius: 8px;
                padding: 4px;
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
        label.setStyleSheet("font-size: 11px; color: #4338CA; background: transparent;")
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
                border: 1px solid #6366F1;
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
            more.setStyleSheet("font-size: 10px; color: #6B7280; background: transparent;")
            self.columns_layout.addWidget(more)
    
    def _create_column_chip(self, column: str) -> QWidget:
        chip = QFrame()
        chip.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #C7D2FE;
                border-radius: 10px;
            }
        """)
        
        layout = QHBoxLayout(chip)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(2)
        
        label = QLabel(column[:12] + "..." if len(column) > 12 else column)
        label.setStyleSheet("font-size: 10px; color: #4338CA; background: transparent;")
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
    ┌──────────┬──────────┬─────────────────────┬────────────┐
    │  X Zone  │  Group   │     Data Table      │   Values   │
    │ (150px)  │  Zone    │                     │   Zone     │
    │          │ (150px)  │                     │  (180px+)  │
    └──────────┴──────────┴─────────────────────┴────────────┘
    """
    
    file_dropped = Signal(str)
    
    def __init__(self, state: AppState, engine: DataEngine):
        super().__init__()
        self.state = state
        self.engine = engine

        # Float windows tracking
        self._float_windows: Dict[str, FloatWindow] = {}
        self._placeholders: Dict[str, QWidget] = {}

        self.setAcceptDrops(True)

        self._setup_ui()
        self._connect_signals()
        self._setup_float_handlers()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)

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
        
        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 6)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search data...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                color: #334155;
            }
            QLineEdit:focus {
                border: 2px solid #6366F1;
                background: #FAFAFF;
            }
        """)
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        
        table_layout.addLayout(search_layout)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        
        expand_btn = QPushButton("▼ Expand")
        expand_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #6366F1;
                border: 1px solid #6366F1;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 500;
            }
            QPushButton:hover { background: #EEF2FF; }
        """)
        expand_btn.clicked.connect(self._expand_all)
        toolbar.addWidget(expand_btn)
        
        collapse_btn = QPushButton("▶ Collapse")
        collapse_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #6366F1;
                border: 1px solid #6366F1;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 500;
            }
            QPushButton:hover { background: #EEF2FF; }
        """)
        collapse_btn.clicked.connect(self._collapse_all)
        toolbar.addWidget(collapse_btn)
        
        toolbar.addStretch()
        
        self.group_info_label = QLabel("")
        self.group_info_label.setStyleSheet("color: #6B7280; font-size: 10px;")
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

        # Value Zone (right)
        self.value_zone = ValueZone(self.state)
        self.splitter.addWidget(self.value_zone)

        # Splitter sizes
        self.splitter.setSizes([310, 500, 200])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        layout.addWidget(self.splitter)
    
    def _connect_signals(self):
        self.table_view.rows_selected.connect(self._on_rows_selected)
        self.table_view.exclude_value.connect(self._on_exclude_value)
        self.table_view.hide_column.connect(self._on_hide_column)
        self.table_view.column_dragged.connect(self._on_column_action)
        self.state.selection_changed.connect(self._on_state_selection_changed)
        self.state.group_zone_changed.connect(self._on_group_zone_changed)
        self.state.value_zone_changed.connect(self._on_value_zone_changed)
        self.state.filter_changed.connect(self._on_filter_changed)

    def _setup_float_handlers(self):
        """Float 버튼 핸들러 설정"""
        # Connect float buttons
        self.x_zone.float_btn.clicked.connect(lambda: self._float_section("x_zone"))
        self.group_zone.float_btn.clicked.connect(lambda: self._float_section("group_zone"))
        self.value_zone.float_btn.clicked.connect(lambda: self._float_section("value_zone"))

        # Create placeholders
        for key, title in [("x_zone", "📐 X-Axis"), ("group_zone", "📁 Group By"), ("value_zone", "📊 Y-Axis Values")]:
            placeholder = QFrame()
            placeholder.setStyleSheet("""
                QFrame {
                    background: #F9FAFB;
                    border: 2px dashed #D1D5DB;
                    border-radius: 8px;
                }
            """)
            layout = QVBoxLayout(placeholder)
            layout.setAlignment(Qt.AlignCenter)
            label = QLabel(f"📤 {title}\n\nFloating")
            label.setStyleSheet("color: #9CA3AF; font-size: 10px; background: transparent;")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            placeholder.hide()
            self._placeholders[key] = placeholder

    def _float_section(self, section_key: str):
        """섹션을 독립 창으로 분리"""
        if section_key in self._float_windows:
            self._float_windows[section_key].raise_()
            self._float_windows[section_key].activateWindow()
            return

        section_map = {
            "x_zone": (self.x_zone, "📐 X-Axis"),
            "group_zone": (self.group_zone, "📁 Group By"),
            "value_zone": (self.value_zone, "📊 Y-Axis Values"),
        }

        if section_key not in section_map:
            return

        widget, title = section_map[section_key]

        # 메인 윈도우 찾기
        main_window = self._find_main_window()

        # Float window 생성
        float_window = FloatWindow(title, widget, main_window)
        float_window.dock_requested.connect(lambda: self._dock_section(section_key))
        self._float_windows[section_key] = float_window

        # 플레이스홀더 설정
        placeholder = self._placeholders[section_key]

        # X Zone과 Group Zone은 left_panel 내부에 있음
        if section_key in ["x_zone", "group_zone"]:
            left_layout = self.left_panel.layout()
            idx = 0 if section_key == "x_zone" else 1
            left_layout.replaceWidget(widget, placeholder)
        else:  # value_zone
            self.splitter.replaceWidget(2, placeholder)

        placeholder.show()

        # Float 버튼 비활성화
        if hasattr(widget, 'float_btn'):
            widget.float_btn.setEnabled(False)

        float_window.show()

    def _dock_section(self, section_key: str):
        """섹션을 메인 창으로 복귀"""
        if section_key not in self._float_windows:
            return

        float_window = self._float_windows[section_key]
        widget = float_window.get_content_widget()
        placeholder = self._placeholders[section_key]

        # X Zone과 Group Zone은 left_panel 내부에 있음
        if section_key in ["x_zone", "group_zone"]:
            left_layout = self.left_panel.layout()
            left_layout.replaceWidget(placeholder, widget)
        else:  # value_zone
            self.splitter.replaceWidget(2, widget)

        placeholder.hide()
        widget.show()

        # Float 버튼 활성화
        if hasattr(widget, 'float_btn'):
            widget.float_btn.setEnabled(True)

        # Float window 정리
        float_window.close()
        float_window.deleteLater()
        del self._float_windows[section_key]

    def _find_main_window(self):
        """메인 윈도우 찾기"""
        widget = self
        while widget:
            if widget.inherits("QMainWindow"):
                return widget
            widget = widget.parentWidget()
        return None
    
    def set_data(self, df: Optional[pl.DataFrame]):
        self._update_table_model(df)
    
    def _update_table_model(self, df: Optional[pl.DataFrame] = None):
        if df is None:
            df = self.engine.df if self.engine.is_loaded else None

        if df is None:
            self.table_model.set_dataframe(None)
            self.group_info_label.setText("")
            return

        # Apply hidden columns filter
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
                color: #6366F1;
                font-size: 10px;
                background: #EEF2FF;
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
                    background: #FEF3C7;
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
    
    def _on_search(self, text: str):
        if not text or not self.engine.is_loaded:
            self._update_table_model(self.engine.df)
            return
        
        result = self.engine.search(text)
        self._update_table_model(result)
    
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
        pass
    
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
