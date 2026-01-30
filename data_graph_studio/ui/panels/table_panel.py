"""
Table Panel - 테이블 뷰 + Group Zone + Value Zone
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


class PolarsTableModel(QAbstractTableModel):
    """
    Polars DataFrame을 위한 Qt 테이블 모델
    
    가상 스크롤 지원 - 필요한 행만 로드
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: Optional[pl.DataFrame] = None
        self._visible_columns: List[str] = []
        self._row_count = 0
        self._chunk_size = 1000  # 한번에 캐시할 행 수
        self._cache: Dict[int, List] = {}  # row_index -> row_data
    
    def set_dataframe(self, df: Optional[pl.DataFrame]):
        """데이터프레임 설정"""
        self.beginResetModel()
        self._df = df
        if df is not None:
            self._visible_columns = df.columns
            self._row_count = len(df)
        else:
            self._visible_columns = []
            self._row_count = 0
        self._cache.clear()
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
            
            # 캐시 확인
            if row not in self._cache:
                self._load_chunk(row)
            
            if row in self._cache:
                value = self._cache[row][col]
                if value is None:
                    return ""
                return str(value)
        
        return None
    
    def _load_chunk(self, row: int):
        """청크 로드 (가상 스크롤용)"""
        if self._df is None:
            return
        
        # 청크 범위 계산
        chunk_start = (row // self._chunk_size) * self._chunk_size
        chunk_end = min(chunk_start + self._chunk_size, self._row_count)
        
        # 청크 데이터 로드
        chunk_df = self._df.slice(chunk_start, chunk_end - chunk_start)
        
        for i, row_data in enumerate(chunk_df.iter_rows()):
            self._cache[chunk_start + i] = list(row_data)
        
        # 캐시 크기 제한 (메모리 관리)
        if len(self._cache) > self._chunk_size * 10:
            # 가장 오래된 청크 제거
            keys = sorted(self._cache.keys())
            for key in keys[:self._chunk_size]:
                del self._cache[key]
    
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


class DraggableListWidget(QListWidget):
    """드래그 가능한 리스트 위젯"""
    
    item_dropped = Signal(str)  # 드롭된 컬럼 이름
    item_removed = Signal(str)  # 제거된 컬럼 이름
    order_changed = Signal(list)  # 순서 변경
    
    def __init__(self, accept_drop: bool = True):
        super().__init__()
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
            self.item_dropped.emit(column_name)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
            # 순서 변경 알림
            self.order_changed.emit([self.item(i).text() for i in range(self.count())])
    
    def add_column(self, name: str):
        """컬럼 추가"""
        # 중복 체크
        for i in range(self.count()):
            if self.item(i).text() == name:
                return
        
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
        self.addItem(item)
    
    def remove_selected(self):
        """선택된 항목 제거"""
        current = self.currentItem()
        if current:
            name = current.text()
            self.takeItem(self.row(current))
            self.item_removed.emit(name)


class GroupZone(QFrame):
    """Group Zone - Modern drag & drop zone"""
    
    group_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("GroupZone")
        self.setFixedWidth(170)
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
        
        # Header with icon
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
        layout.addLayout(header_layout)
        
        # Help text
        help_label = QLabel("Drag columns here to group data")
        help_label.setStyleSheet("""
            color: #64748B;
            font-size: 11px;
            background: transparent;
        """)
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Drop zone hint
        self.drop_hint = QLabel("Drop columns here")
        self.drop_hint.setStyleSheet("""
            color: #94A3B8;
            font-size: 11px;
            padding: 20px;
            border: 2px dashed #CBD5E1;
            border-radius: 8px;
            background: #F8FAFC;
        """)
        self.drop_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.drop_hint)
        
        # List widget
        self.list_widget = DraggableListWidget(accept_drop=True)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background: white;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 10px 12px;
                margin: 3px 0;
                color: #334155;
                font-weight: 500;
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
                padding: 8px 12px;
                font-weight: 500;
                font-size: 11px;
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
        """상태에서 동기화"""
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


class ValueZone(QFrame):
    """Value Zone - Modern aggregation zone"""
    
    value_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("ValueZone")
        self.setFixedWidth(200)
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
        
        # Header with icon
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        icon = QLabel("📊")
        icon.setStyleSheet("font-size: 16px; background: transparent;")
        header_layout.addWidget(icon)
        
        header = QLabel("Values")
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
        help_label = QLabel("Drag numeric columns for aggregation")
        help_label.setStyleSheet("""
            color: #9333EA;
            font-size: 11px;
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
        self.value_layout.setSpacing(8)
        self.value_layout.addStretch()
        
        scroll.setWidget(self.value_container)
        layout.addWidget(scroll, 1)
    
    def _connect_signals(self):
        self.state.value_zone_changed.connect(self._sync_from_state)
    
    def _add_value_card(self, value_col: ValueColumn, index: int):
        """Add modern value card"""
        card = QFrame()
        card.setObjectName("ValueCard")
        card.setStyleSheet(f"""
            #ValueCard {{
                background: white;
                border: 1px solid {value_col.color}40;
                border-left: 4px solid {value_col.color};
                border-radius: 10px;
            }}
            #ValueCard:hover {{
                background: {value_col.color}08;
                border-color: {value_col.color}60;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)
        
        # Header row: name + remove button
        header_row = QHBoxLayout()
        header_row.setSpacing(4)
        
        # Color dot + Column name
        name_label = QLabel(f"● {value_col.name[:15]}{'...' if len(value_col.name) > 15 else ''}")
        name_label.setStyleSheet(f"""
            font-weight: 600;
            font-size: 12px;
            color: #1E293B;
            background: transparent;
        """)
        header_row.addWidget(name_label, 1)
        
        # Remove button (x)
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(22, 22)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94A3B8;
                border: none;
                border-radius: 11px;
                font-size: 16px;
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
                border-radius: 6px;
                padding: 6px 10px;
                color: {value_col.color};
                font-weight: 500;
                font-size: 11px;
            }}
            QComboBox:hover {{
                border-color: {value_col.color};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {value_col.color};
            }}
        """)
        for agg in AggregationType:
            agg_combo.addItem(agg.value.upper(), agg)
        agg_combo.setCurrentText(value_col.aggregation.value.upper())
        agg_combo.currentIndexChanged.connect(
            lambda idx, i=index: self._on_agg_changed(i, agg_combo.currentData())
        )
        card_layout.addWidget(agg_combo)
        
        # Add to layout (before stretch)
        self.value_layout.insertWidget(self.value_layout.count() - 1, card)
    
    def _on_agg_changed(self, index: int, agg: AggregationType):
        self.state.update_value_column(index, aggregation=agg)
    
    def _remove_value(self, index: int):
        self.state.remove_value_column(index)
    
    def _sync_from_state(self):
        """상태에서 동기화"""
        # 기존 카드 제거
        while self.value_layout.count() > 1:  # stretch 유지
            item = self.value_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 새 카드 추가
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


class DataTableView(QTableView):
    """데이터 테이블 뷰"""
    
    column_dragged = Signal(str)  # 드래그 시작된 컬럼
    rows_selected = Signal(list)  # 선택된 행들
    
    def __init__(self):
        super().__init__()
        
        # 설정
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setDragEnabled(True)
        
        # 헤더 설정
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._show_header_menu)
        
        # 드래그 시작
        self.horizontalHeader().sectionPressed.connect(self._on_header_pressed)
        
        # 선택 변경
        self.selectionModel_connected = False
    
    def setModel(self, model):
        super().setModel(model)
        if model and not self.selectionModel_connected:
            self.selectionModel().selectionChanged.connect(self._on_selection_changed)
            self.selectionModel_connected = True
    
    def _on_header_pressed(self, logical_index: int):
        """헤더 클릭 - 드래그 시작"""
        model = self.model()
        if model:
            column_name = model.get_column_name(logical_index)
            if column_name:
                # 드래그 시작
                drag = QDrag(self)
                mime_data = QMimeData()
                mime_data.setText(column_name)
                drag.setMimeData(mime_data)
                drag.exec(Qt.CopyAction)
    
    def _on_selection_changed(self, selected, deselected):
        """선택 변경"""
        indexes = self.selectionModel().selectedRows()
        rows = [idx.row() for idx in indexes]
        self.rows_selected.emit(rows)
    
    def _show_header_menu(self, pos):
        """헤더 컨텍스트 메뉴"""
        logical_index = self.horizontalHeader().logicalIndexAt(pos)
        model = self.model()
        if not model:
            return
        
        column_name = model.get_column_name(logical_index)
        if not column_name:
            return
        
        menu = QMenu(self)
        
        # 정렬
        sort_asc = QAction(f"Sort Ascending", self)
        sort_asc.triggered.connect(lambda: self.sortByColumn(logical_index, Qt.AscendingOrder))
        menu.addAction(sort_asc)
        
        sort_desc = QAction(f"Sort Descending", self)
        sort_desc.triggered.connect(lambda: self.sortByColumn(logical_index, Qt.DescendingOrder))
        menu.addAction(sort_desc)
        
        menu.addSeparator()
        
        # Group/Value에 추가
        add_to_group = QAction(f"Add to Group Zone", self)
        add_to_group.triggered.connect(lambda: self.column_dragged.emit(column_name))
        menu.addAction(add_to_group)
        
        menu.exec(self.horizontalHeader().mapToGlobal(pos))


class TablePanel(QWidget):
    """
    Table Panel
    
    구조:
    ┌────────────┬─────────────────────────────┬────────────┐
    │   Group    │         Data Table          │   Value    │
    │   Zone     │                             │   Zone     │
    │  (150px)   │                             │  (180px)   │
    └────────────┴─────────────────────────────┴────────────┘
    """
    
    file_dropped = Signal(str)  # 파일 드롭
    
    def __init__(self, state: AppState, engine: DataEngine):
        super().__init__()
        self.state = state
        self.engine = engine
        
        self.setAcceptDrops(True)
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 스플리터
        splitter = QSplitter(Qt.Horizontal)
        
        # Group Zone (왼쪽)
        self.group_zone = GroupZone(self.state)
        splitter.addWidget(self.group_zone)
        
        # 테이블 영역 (중앙)
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(4, 4, 4, 4)
        table_layout.setSpacing(4)
        
        # Modern search bar
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 8)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search data...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                padding: 10px 16px 10px 40px;
                font-size: 13px;
                color: #334155;
            }
            QLineEdit:focus {
                border: 2px solid #6366F1;
                background: #FAFAFF;
            }
            QLineEdit::placeholder {
                color: #94A3B8;
            }
        """)
        # Note: Search icon would need to be overlaid with a QLabel
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        
        table_layout.addLayout(search_layout)
        
        # Toolbar for expand/collapse
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        
        expand_btn = QPushButton("▼ Expand All")
        expand_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #6366F1;
                border: 1px solid #6366F1;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover { background: #EEF2FF; }
        """)
        expand_btn.clicked.connect(self._expand_all)
        toolbar.addWidget(expand_btn)
        
        collapse_btn = QPushButton("▶ Collapse All")
        collapse_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #6366F1;
                border: 1px solid #6366F1;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover { background: #EEF2FF; }
        """)
        collapse_btn.clicked.connect(self._collapse_all)
        toolbar.addWidget(collapse_btn)
        
        toolbar.addStretch()
        
        self.group_info_label = QLabel("")
        self.group_info_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        toolbar.addWidget(self.group_info_label)
        
        table_layout.addLayout(toolbar)
        
        # Table view with grouped model
        self.table_view = DataTableView()
        self.table_model = PolarsTableModel()
        self.grouped_model = None  # Will be created when grouping
        self.table_view.setModel(self.table_model)
        
        # Enable click to expand/collapse
        self.table_view.clicked.connect(self._on_table_clicked)
        
        table_layout.addWidget(self.table_view)
        
        splitter.addWidget(table_container)
        
        # Value Zone (오른쪽)
        self.value_zone = ValueZone(self.state)
        splitter.addWidget(self.value_zone)
        
        # 스플리터 비율
        splitter.setSizes([150, 500, 180])
        splitter.setStretchFactor(0, 0)  # Group: 고정
        splitter.setStretchFactor(1, 1)  # Table: 확장
        splitter.setStretchFactor(2, 0)  # Value: 고정
        
        layout.addWidget(splitter)
    
    def _connect_signals(self):
        self.table_view.rows_selected.connect(self._on_rows_selected)
        self.state.selection_changed.connect(self._on_state_selection_changed)
        self.state.group_zone_changed.connect(self._on_group_zone_changed)
        self.state.value_zone_changed.connect(self._on_value_zone_changed)
    
    def set_data(self, df: Optional[pl.DataFrame]):
        """Set data and apply grouping if configured"""
        self._update_table_model(df)
    
    def _update_table_model(self, df: Optional[pl.DataFrame] = None):
        """Update table model with current grouping"""
        if df is None:
            df = self.engine.df if self.engine.is_loaded else None
        
        if df is None:
            self.table_model.set_dataframe(None)
            self.group_info_label.setText("")
            return
        
        # Check if grouping is active
        if self.state.group_columns:
            # Use grouped model
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
            
            # Update info label
            group_names = " → ".join(group_cols)
            self.group_info_label.setText(f"Grouped by: {group_names}")
            self.group_info_label.setStyleSheet("""
                color: #6366F1;
                font-size: 11px;
                background: #EEF2FF;
                padding: 4px 10px;
                border-radius: 10px;
            """)
        else:
            # Use flat model
            self.table_model.set_dataframe(df)
            self.table_view.setModel(self.table_model)
            self.group_info_label.setText("")
        
        # Adjust column widths
        header = self.table_view.horizontalHeader()
        for i in range(min(10, self.table_view.model().columnCount())):
            header.resizeSection(i, 150)
    
    def clear(self):
        """Clear table"""
        self.table_model.set_dataframe(None)
        if self.grouped_model:
            self.grouped_model.set_data(None)
        self.group_info_label.setText("")
    
    def _on_search(self, text: str):
        """Search filter"""
        if not text or not self.engine.is_loaded:
            self._update_table_model(self.engine.df)
            return
        
        result = self.engine.search(text)
        self._update_table_model(result)
    
    def _on_rows_selected(self, rows: List[int]):
        """Handle row selection from table"""
        # If using grouped model, get actual row indices
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
        """Handle selection change from state (e.g., from graph)"""
        # TODO: Highlight selected rows in table
        pass
    
    def _on_group_zone_changed(self):
        """Handle group zone change - rebuild table"""
        if self.engine.is_loaded:
            self._update_table_model(self.engine.df)
    
    def _on_value_zone_changed(self):
        """Handle value zone change - update aggregates"""
        if self.engine.is_loaded and self.state.group_columns:
            self._update_table_model(self.engine.df)
    
    def _on_table_clicked(self, index):
        """Handle table click for expand/collapse"""
        if index.column() == 0 and self.grouped_model and self.state.group_columns:
            # Check if this is a group header
            is_header = self.grouped_model.data(index, Qt.UserRole + 1)
            if is_header:
                self.grouped_model.toggle_expand(index.row())
    
    def _expand_all(self):
        """Expand all groups"""
        if self.grouped_model and self.state.group_columns:
            self.grouped_model.expand_all()
    
    def _collapse_all(self):
        """Collapse all groups"""
        if self.grouped_model and self.state.group_columns:
            self.grouped_model.collapse_all()
    
    def get_group_data(self) -> List:
        """Get group data for graph rendering"""
        if self.grouped_model and self.state.group_columns:
            return self.grouped_model.get_group_data()
        return []
    
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
