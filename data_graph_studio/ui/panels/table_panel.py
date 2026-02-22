"""
Table Panel - 테이블 뷰 + X Zone + Group Zone + Value Zone
"""

from typing import Optional, List, Dict, Any, Set, Tuple
from collections import OrderedDict
import json
import logging
import polars as pl

logger = logging.getLogger(__name__)

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QTableView, QAbstractItemView, QMenu,
    QLineEdit, QComboBox, QPushButton, QMessageBox,
    QApplication, QListWidget,
    QListWidgetItem, QSlider, QDialog,
    QDialogButtonBox, QFormLayout
)
from PySide6.QtCore import QTimer
from PySide6.QtCore import (
    Qt, Signal, QAbstractTableModel, QModelIndex,
    QMimeData, QByteArray, QItemSelection, QItemSelectionModel, QSize
)
from PySide6.QtGui import QBrush, QColor, QDrag, QAction, QDropEvent, QDragEnterEvent, QKeySequence

from ...core.state import AppState, AggregationType, ValueColumn
from ...core.data_engine import DataEngine
from .grouped_table_model import GroupedTableModel
from .conditional_formatting import ConditionalFormat, ConditionalFormatDialog


class PolarsTableModel(QAbstractTableModel):
    """Polars DataFrame을 위한 Qt 테이블 모델 (최적화 버전)

    성능 최적화:
    - 컬럼 기반 캐싱 (Polars는 컬럼 지향이므로)
    - 직접 인덱스 접근으로 iter_rows() 회피
    - 필요한 데이터만 로드
    - 정렬 인덱스 기반 접근 (메모리 효율)
    - LRU 컬럼 캐시 (OrderedDict)
    - 가상 스크롤 (fetchMore/canFetchMore)
    """

    # 테이블에 표시할 최대 행 수 (성능 보장)
    MAX_DISPLAY_ROWS = 100_000
    FETCH_SIZE = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: Optional[pl.DataFrame] = None
        self._original_df: Optional[pl.DataFrame] = None  # 정렬 전 원본
        self._visible_columns: List[str] = []
        self._row_count = 0
        self._actual_row_count = 0  # 실제 데이터 행 수
        self._total_rows = 0  # for virtual scroll
        self._loaded_rows = 0  # for virtual scroll
        self._virtual_scroll_enabled = False  # opt-in
        # 컬럼 기반 LRU 캐시: column_index -> list of values
        self._column_cache: OrderedDict = OrderedDict()
        self._cache_valid = False
        # 정렬 상태
        self._sort_column: Optional[int] = None
        self._sort_order: Optional[Qt.SortOrder] = None
        self._sort_indices: Optional[pl.Series] = None  # 원본 인덱스 매핑
        self._reverse_sort_map: Dict[int, int] = {}  # Bug 3: O(1) reverse map
        # 멀티 정렬 (F6)
        self._sort_columns: List[Tuple[int, Qt.SortOrder]] = []
        # Focusing 하이라이트
        self._focused_rows: set = set()
        self._focus_brush = QBrush(QColor(200, 240, 200))  # 연한 초록색
        # 검색 하이라이트 (UX 6)
        self._search_matches: Set[Tuple[int, int]] = set()  # (row, col) pairs
        self._search_brush = QBrush(QColor(255, 235, 59, 100))  # 연한 노랑
        # 조건부 서식 (F3)
        self._conditional_formats: Dict[str, ConditionalFormat] = {}
        # 인라인 편집 (F2)
        self._editable = False

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
        self._reverse_sort_map = {}
        self._sort_columns = []
        self._search_matches = set()
        if df is not None:
            self._visible_columns = df.columns
            self._actual_row_count = len(df)
            self._total_rows = min(len(df), self.MAX_DISPLAY_ROWS)
            if self._virtual_scroll_enabled:
                self._loaded_rows = min(self.FETCH_SIZE, self._total_rows)
            else:
                self._loaded_rows = self._total_rows
            self._row_count = self._loaded_rows
            # Update conditional format ranges
            self._update_conditional_format_ranges()
        else:
            self._visible_columns = []
            self._row_count = 0
            self._actual_row_count = 0
            self._total_rows = 0
            self._loaded_rows = 0
        self.endResetModel()

    # ==================== Virtual Scroll (F8) ====================

    def set_virtual_scroll(self, enabled: bool):
        """Enable/disable virtual scroll for large datasets."""
        self._virtual_scroll_enabled = enabled

    def canFetchMore(self, parent=QModelIndex()):
        if not self._virtual_scroll_enabled:
            return False
        return self._loaded_rows < self._total_rows

    def fetchMore(self, parent=QModelIndex()):
        remaining = self._total_rows - self._loaded_rows
        fetch = min(self.FETCH_SIZE, remaining)
        self.beginInsertRows(parent, self._loaded_rows, self._loaded_rows + fetch - 1)
        self._loaded_rows += fetch
        self._row_count = self._loaded_rows
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()):
        return self._row_count

    def columnCount(self, parent=QModelIndex()):
        return len(self._visible_columns)

    def flags(self, index: QModelIndex):
        """F2: Support inline editing when enabled."""
        f = super().flags(index)
        if self._editable:
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index: QModelIndex, value, role=Qt.EditRole) -> bool:
        """F2: Inline cell editing."""
        if role != Qt.EditRole or not self._editable:
            return False
        if not index.isValid() or self._df is None:
            return False
        col_idx = index.column()
        row_idx = index.row()
        if col_idx >= len(self._visible_columns) or row_idx >= self._row_count:
            return False
        col_name = self._visible_columns[col_idx]
        original_row = self._get_original_row(row_idx)
        try:
            series_list = self._df[col_name].to_list()
            series_list[original_row] = value
            new_df = self._df.with_columns(pl.Series(col_name, series_list))
            self._df = new_df
            if self._original_df is not None and self._sort_indices is not None:
                # Also update original
                orig_list = self._original_df[col_name].to_list()
                orig_list[original_row] = value
                self._original_df = self._original_df.with_columns(pl.Series(col_name, orig_list))
            else:
                self._original_df = new_df
            # Invalidate column cache
            if col_idx in self._column_cache:
                del self._column_cache[col_idx]
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True
        except Exception:
            return False

    def set_editable(self, editable: bool):
        self._editable = editable

    def _get_original_row(self, display_row: int) -> int:
        """Get original row index from display row."""
        if self._sort_indices is not None and 0 <= display_row < len(self._sort_indices):
            return int(self._sort_indices[display_row])
        return display_row

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or self._df is None:
            return None

        if role == Qt.BackgroundRole:
            # Search highlight takes priority
            if (index.row(), index.column()) in self._search_matches:
                return self._search_brush
            # Focus highlight
            if index.row() in self._focused_rows:
                return self._focus_brush
            # Conditional formatting (F3)
            if self._conditional_formats:
                col_idx = index.column()
                if col_idx < len(self._visible_columns):
                    col_name = self._visible_columns[col_idx]
                    if col_name in self._conditional_formats:
                        val = self._get_raw_value(index.row(), col_idx)
                        result = self._conditional_formats[col_name].get_color(val)
                        if result is not None:
                            return result
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
                self._column_cache.move_to_end(col)  # LRU touch
                cache = self._column_cache[col]
                if row < len(cache):
                    value = cache[row]
                    if value is None:
                        return ""
                    return str(value)

        return None

    def _get_raw_value(self, row: int, col: int):
        """Get raw (non-string) value for conditional formatting."""
        if col not in self._column_cache:
            self._cache_column(col)
        if col in self._column_cache:
            cache = self._column_cache[col]
            if row < len(cache):
                return cache[row]
        return None

    def set_focused_rows(self, rows: set):
        """Set rows to highlight with focus color."""
        old = self._focused_rows
        self._focused_rows = set(rows)
        # Emit dataChanged for affected rows
        changed = old.symmetric_difference(self._focused_rows)
        if changed and self._row_count > 0:
            min_row = min(r for r in changed if r < self._row_count) if any(r < self._row_count for r in changed) else 0
            max_row = max(r for r in changed if r < self._row_count) if any(r < self._row_count for r in changed) else 0
            col_count = len(self._visible_columns)
            if col_count > 0:
                self.dataChanged.emit(
                    self.index(min_row, 0),
                    self.index(max_row, col_count - 1),
                    [Qt.BackgroundRole],
                )

    # ==================== Search Highlight (UX 6) ====================

    def set_search_matches(self, matches: Set[Tuple[int, int]]):
        """Set search match positions and highlight without model rebuild."""
        self._search_matches = matches
        if self._row_count > 0 and len(self._visible_columns) > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self._row_count - 1, len(self._visible_columns) - 1),
                [Qt.BackgroundRole],
            )

    def clear_search_matches(self):
        self.set_search_matches(set())

    def _cache_column(self, col: int):
        """컬럼 데이터를 LRU 캐시에 로드"""
        if self._df is None or col >= len(self._visible_columns):
            return

        col_name = self._visible_columns[col]
        try:
            if self._row_count < self._actual_row_count:
                col_data = self._df[col_name].head(self._row_count).to_list()
            else:
                col_data = self._df[col_name].to_list()
            self._column_cache[col] = col_data
            self._column_cache.move_to_end(col)
        except Exception:
            self._column_cache[col] = []

        # LRU eviction
        MAX_CACHED_COLUMNS = 50
        while len(self._column_cache) > MAX_CACHED_COLUMNS:
            self._column_cache.popitem(last=False)

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
                    # Multi-sort indicator
                    for i, (sc, so) in enumerate(self._sort_columns):
                        if sc == section:
                            arrow = "▲" if so == Qt.AscendingOrder else "▼"
                            return f"{col_name} {arrow}{i+1}"
                    return col_name
            else:
                return str(section + 1)
        # F4: Column stats tooltip
        elif role == Qt.ToolTipRole and orientation == Qt.Horizontal:
            if self._df is not None and 0 <= section < len(self._visible_columns):
                col_name = self._visible_columns[section]
                try:
                    series = self._df[col_name]
                    dtype = str(series.dtype)
                    null_count = series.null_count()
                    total = len(series)
                    pct = (null_count / total * 100) if total > 0 else 0
                    tooltip = f"<b>{col_name}</b><br>Type: {dtype}<br>Nulls: {null_count} ({pct:.1f}%)"
                    if series.dtype.is_numeric():
                        tooltip += f"<br>Min: {series.min()}<br>Max: {series.max()}<br>Mean: {series.mean():.2f}"
                    return tooltip
                except Exception:
                    return col_name
        return None

    def get_column_name(self, index: int) -> Optional[str]:
        if 0 <= index < len(self._visible_columns):
            return self._visible_columns[index]
        return None

    def get_actual_row_count(self) -> int:
        """실제 데이터 행 수 (표시 제한과 무관)"""
        return self._actual_row_count

    # ==================== 조건부 서식 (F3) ====================

    def set_conditional_format(self, col_name: str, fmt: ConditionalFormat):
        self._conditional_formats[col_name] = fmt
        self._update_conditional_format_ranges()
        if self._row_count > 0 and len(self._visible_columns) > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self._row_count - 1, len(self._visible_columns) - 1),
                [Qt.BackgroundRole],
            )

    def remove_conditional_format(self, col_name: str):
        if col_name in self._conditional_formats:
            del self._conditional_formats[col_name]
            if self._row_count > 0 and len(self._visible_columns) > 0:
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(self._row_count - 1, len(self._visible_columns) - 1),
                    [Qt.BackgroundRole],
                )

    def _update_conditional_format_ranges(self):
        """Update min/max ranges for conditional formats."""
        if self._df is None:
            return
        for col_name, fmt in self._conditional_formats.items():
            if col_name in self._df.columns:
                try:
                    series = self._df[col_name]
                    if series.dtype.is_numeric():
                        fmt.set_range(float(series.min()), float(series.max()))
                except Exception:
                    pass

    # ==================== 정렬 기능 ====================

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder):
        """컬럼 기준 정렬 (멀티 정렬 지원 F6)"""
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

            # Bug 3: Build reverse map for O(1) lookup
            indices_list = self._sort_indices.to_list()
            self._reverse_sort_map = {orig: sorted_idx for sorted_idx, orig in enumerate(indices_list)}

            # 정렬된 DataFrame 저장 (인덱스 컬럼 제거)
            self._df = sorted_df.drop("__original_idx__")

            # 캐시 무효화
            self._column_cache.clear()

            # 정렬 상태 저장
            self._sort_column = column
            self._sort_order = order

            # Virtual scroll reset
            self._total_rows = min(len(self._df), self.MAX_DISPLAY_ROWS)
            self._loaded_rows = min(self.FETCH_SIZE, self._total_rows) if self._virtual_scroll_enabled else self._total_rows
            self._row_count = self._loaded_rows

        except Exception as e:
            # 정렬 실패 시 원본 유지
            logger.error("table_panel.sort_error", extra={"error": str(e)})
            self._df = self._original_df
            self._sort_column = None
            self._sort_order = None
            self._sort_indices = None
            self._reverse_sort_map = {}

        self.endResetModel()

    def sort_multi(self, columns: List[Tuple[int, Qt.SortOrder]]):
        """F6: Multi-column sort."""
        if self._original_df is None or not columns:
            return

        self._sort_columns = columns
        col_names = []
        descending = []
        for col_idx, order in columns:
            if 0 <= col_idx < len(self._visible_columns):
                col_names.append(self._visible_columns[col_idx])
                descending.append(order == Qt.DescendingOrder)

        if not col_names:
            return

        self.beginResetModel()
        try:
            df_with_idx = self._original_df.with_row_index("__original_idx__")
            sorted_df = df_with_idx.sort(col_names, descending=descending, nulls_last=True)
            self._sort_indices = sorted_df["__original_idx__"].cast(pl.Int32)
            indices_list = self._sort_indices.to_list()
            self._reverse_sort_map = {orig: si for si, orig in enumerate(indices_list)}
            self._df = sorted_df.drop("__original_idx__")
            self._column_cache.clear()
            self._sort_column = columns[0][0] if len(columns) == 1 else None
            self._sort_order = columns[0][1] if len(columns) == 1 else None
            self._total_rows = min(len(self._df), self.MAX_DISPLAY_ROWS)
            self._loaded_rows = min(self.FETCH_SIZE, self._total_rows) if self._virtual_scroll_enabled else self._total_rows
            self._row_count = self._loaded_rows
        except Exception as e:
            logger.error("table_panel.multi_sort_error", extra={"error": str(e)})
            self._df = self._original_df
            self._sort_columns = []
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
        self._reverse_sort_map = {}
        self._sort_columns = []
        self._total_rows = min(len(self._df), self.MAX_DISPLAY_ROWS) if self._df is not None else 0
        self._loaded_rows = min(self.FETCH_SIZE, self._total_rows) if self._virtual_scroll_enabled else self._total_rows
        self._row_count = self._loaded_rows
        self.endResetModel()

    def get_sort_column(self) -> Optional[int]:
        """현재 정렬된 컬럼 인덱스 반환"""
        return self._sort_column

    def get_sort_order(self) -> Optional[Qt.SortOrder]:
        """현재 정렬 순서 반환"""
        return self._sort_order

    def get_original_row_index(self, sorted_row: int) -> Optional[int]:
        """정렬된 행 인덱스에서 원본 행 인덱스 반환"""
        if self._sort_indices is None:
            return sorted_row

        if 0 <= sorted_row < len(self._sort_indices):
            return int(self._sort_indices[sorted_row])

        return None

    def get_sorted_row_index(self, original_row: int) -> Optional[int]:
        """원본 행 인덱스에서 정렬된 행 인덱스 반환 (Bug 3: O(1))"""
        if self._sort_indices is None:
            return original_row

        if self._reverse_sort_map:
            return self._reverse_sort_map.get(original_row, -1)

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


# ==================== X-Axis Zone ====================

class XAxisZone(QFrame):
    """X-Axis Zone - X축 컬럼 선택"""
    
    x_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
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
    column_type_convert = Signal(str, str)  # column_name, target_type
    column_freeze = Signal(str)  # column name
    column_unfreeze = Signal(str)  # column name
    conditional_format_requested = Signal(str)  # column name
    multi_sort_requested = Signal(int, object)  # column, Qt.SortOrder
    
    def __init__(self):
        super().__init__()
        
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setDragEnabled(True)
        
        # Styles handled by global theme stylesheet
        self.setObjectName("dataTableView")
        
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
        
        # Multi-sort state
        self._pending_multi_sort: List[Tuple[int, Qt.SortOrder]] = []
    
    def setModel(self, model):
        """Bug 4: Reconnect selectionModel on every model swap."""
        super().setModel(model)
        sel_model = self.selectionModel()
        if sel_model:
            sel_model.selectionChanged.connect(self._on_selection_changed)

    # F1: Multi-cell Ctrl+C copy
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self._copy_selection_to_clipboard()
            return
        super().keyPressEvent(event)

    def _copy_selection_to_clipboard(self):
        """Copy selected cells as TSV to clipboard."""
        sel = self.selectionModel()
        if not sel:
            return
        indexes = sel.selectedIndexes()
        if not indexes:
            return
        rows = sorted(set(idx.row() for idx in indexes))
        cols = sorted(set(idx.column() for idx in indexes))
        lines = []
        for r in rows:
            line = []
            for c in cols:
                idx = self.model().index(r, c)
                line.append(str(self.model().data(idx, Qt.DisplayRole) or ""))
            lines.append("\t".join(line))
        QApplication.clipboard().setText("\n".join(lines))
    
    def _on_header_pressed(self, logical_index: int):
        # Store column name for context menu / reorder
        pass

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
        # Ctrl+drag to zones removed (zones moved to Data tab in Chart Options)
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

        # Set as — 최상위에 펼쳐서 배치
        set_x = QAction("📐 Set as X-Axis", self)
        set_x.triggered.connect(lambda: self.column_dragged.emit(f"X:{column_name}"))
        menu.addAction(set_x)

        set_y = QAction("📊 Set as Y-Axis Value", self)
        set_y.triggered.connect(lambda: self.column_dragged.emit(f"V:{column_name}"))
        menu.addAction(set_y)

        set_g = QAction("📁 Set as Group By", self)
        set_g.triggered.connect(lambda: self.column_dragged.emit(f"G:{column_name}"))
        menu.addAction(set_g)

        set_h = QAction("💬 Set as Hover Data", self)
        set_h.triggered.connect(lambda: self.column_dragged.emit(f"H:{column_name}"))
        menu.addAction(set_h)

        menu.addSeparator()

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

        # F5: Convert Type submenu
        type_menu = menu.addMenu("🔄 Convert Type")
        for dtype_name in ["Int64", "Float64", "String", "Date", "Boolean"]:
            act = QAction(dtype_name, self)
            act.triggered.connect(lambda checked=False, t=dtype_name: self.column_type_convert.emit(column_name, t))
            type_menu.addAction(act)

        # F3: Conditional Formatting
        cond_fmt = QAction("🎨 Conditional Formatting...", self)
        cond_fmt.triggered.connect(lambda: self.conditional_format_requested.emit(column_name))
        menu.addAction(cond_fmt)

        # F7: Freeze/Unfreeze Column
        freeze_act = QAction("📌 Freeze Column", self)
        freeze_act.triggered.connect(lambda: self.column_freeze.emit(column_name))
        menu.addAction(freeze_act)

        unfreeze_act = QAction("📌 Unfreeze Column", self)
        unfreeze_act.triggered.connect(lambda: self.column_unfreeze.emit(column_name))
        menu.addAction(unfreeze_act)

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


# ==================== Table Panel ====================

class TablePanel(QWidget):
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
        self.state.selection_changed.connect(self._on_state_selection_changed)
        self.state.group_zone_changed.connect(self._on_group_zone_changed)
        self.state.value_zone_changed.connect(self._on_value_zone_changed)
        self.state.filter_changed.connect(self._on_filter_changed)
        self.state.limit_to_marking_changed.connect(self._on_limit_to_marking_changed)
        self.state.selection_changed.connect(self._on_selection_for_limit_marking)

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
                pass
        else:
            # Row-level table view
            self.table_model.set_dataframe(df)
            self.table_view.setModel(self.table_model)

            # Disable grouped-only controls
            try:
                self.expand_btn.setEnabled(False)
                self.collapse_btn.setEnabled(False)
            except Exception:
                pass

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
                self.search_result_label.setProperty("state", "notfound")
            else:
                self.search_result_label.setText(f"{count:,} results")
                self.search_result_label.setProperty("state", "found")
            self.search_result_label.style().unpolish(self.search_result_label)
            self.search_result_label.style().polish(self.search_result_label)
        
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
            self.engine.drop_column(column)
            # Clean state references
            if self.state.x_column == column:
                self.state.set_x_column(None)
            # Remove from groups/values/hover
            self.state.remove_group_column(column)
            self.state.remove_value_column_by_name(column)
            if column in self.state.hover_columns:
                self.state.remove_hover_column(column)
            # Hidden/column order cleanup
            self.state.unhide_column(column)
            if column in self.state.get_column_order():
                self.state.set_column_order([c for c in self.state.get_column_order() if c != column])

            # Refresh UI
            self._update_table_model(self.engine.df)
            self.graph_panel.refresh() if hasattr(self, 'graph_panel') else None
        except Exception as e:
            QMessageBox.warning(self, "Exclude Column", f"Failed to exclude column: {e}")
    
    def _on_column_action(self, action: str):
        """Handle column actions from header context menu (Set as X/Y/Group/Hover)"""
        feedback = ""
        if action.startswith("X:"):
            column = action[2:]
            self.state.set_x_column(column)
            feedback = f"Set '{column}' as X-Axis"
        elif action.startswith("G:"):
            column = action[2:]
            self.state.add_group_column(column)
            feedback = f"Added '{column}' to Group By"
        elif action.startswith("V:"):
            column = action[2:]
            self.state.add_value_column(column)
            feedback = f"Added '{column}' to Y-Axis"
        elif action.startswith("H:"):
            column = action[2:]
            self.state.add_hover_column(column)
            feedback = f"Added '{column}' to Hover"
        
        # Show statusbar feedback
        if feedback:
            main_window = self.window()
            if main_window and hasattr(main_window, 'statusbar'):
                main_window.statusbar.showMessage(feedback, 3000)
    
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
                # UX 10: Show filter error to user instead of print
                main_window = self.window()
                if main_window and hasattr(main_window, 'statusBar'):
                    main_window.statusBar().showMessage(
                        f"Filter error on '{f.column}': {e}", 5000
                    )
                continue

        # Update visible rows count in state
        self.state.set_visible_rows(len(filtered_df))
        self._update_table_model(filtered_df)
    
    def _on_show_column(self, column: str):
        """Show a hidden column"""
        self.state.unhide_column(column)
        self._update_hidden_bar()
        self._update_table_model()
    
    def _on_show_all_columns(self):
        """Show all hidden columns"""
        hidden = list(self.state.hidden_columns)
        for col in hidden:
            self.state.unhide_column(col)
        self._update_hidden_bar()
        self._update_table_model()
    
    def _update_hidden_bar(self):
        """Update hidden columns bar"""
        hidden = list(self.state.hidden_columns)
        self.hidden_bar.update_hidden_columns(hidden)

    # ==================== Table View Mode ====================

    def _on_table_view_mode_changed(self):
        """Handle table view mode changes."""
        if not self.engine.is_loaded:
            return

        mode = None
        try:
            mode = self.table_view_mode_combo.currentData()
        except Exception:
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
    
    # ==================== Focusing ====================

    def _on_focus_toggled(self, checked: bool):
        """Toggle focus mode."""
        self._focus_enabled = checked
        if checked:
            self._update_focus_from_selection()
        else:
            self._clear_focus()

    def _update_focus_from_selection(self):
        """Update focus state from current selection."""
        if not self._focus_enabled or not self.engine.is_loaded:
            self._clear_focus()
            return

        selected = self.state.selection.selected_rows
        if not selected:
            self._clear_focus()
            return

        max_row = len(self.engine.df) if self.engine.df is not None else 0
        valid = sorted(r for r in selected if 0 <= r < max_row)
        if not valid:
            self._clear_focus()
            return

        self._focus_sorted_rows = valid
        self._focus_current_idx = 0

        # Highlight rows in model
        model = self.table_view.model()
        if isinstance(model, PolarsTableModel):
            model.set_focused_rows(set(valid))

        self._update_focus_nav()
        self._scroll_to_focus_current()

    def _clear_focus(self):
        """Clear all focus state."""
        self._focus_sorted_rows = []
        self._focus_current_idx = 0
        self.focus_prev_btn.setEnabled(False)
        self.focus_next_btn.setEnabled(False)
        self.focus_label.setText("")

        model = self.table_view.model()
        if isinstance(model, PolarsTableModel):
            model.set_focused_rows(set())

    def _update_focus_nav(self):
        """Update back/next buttons and label."""
        count = len(self._focus_sorted_rows)
        if count == 0:
            self.focus_prev_btn.setEnabled(False)
            self.focus_next_btn.setEnabled(False)
            self.focus_label.setText("")
            return

        idx = self._focus_current_idx
        self.focus_prev_btn.setEnabled(idx > 0)
        self.focus_next_btn.setEnabled(idx < count - 1)
        self.focus_label.setText(f"{idx + 1}/{count}")

    def _scroll_to_focus_current(self):
        """Scroll table to the current focus row."""
        if not self._focus_sorted_rows:
            return
        row = self._focus_sorted_rows[self._focus_current_idx]
        model = self.table_view.model()
        if model and row < model.rowCount():
            index = model.index(row, 0)
            self.table_view.scrollTo(index, QAbstractItemView.PositionAtCenter)

    def _on_focus_prev(self):
        if self._focus_current_idx > 0:
            self._focus_current_idx -= 1
            self._update_focus_nav()
            self._scroll_to_focus_current()

    def _on_focus_next(self):
        if self._focus_current_idx < len(self._focus_sorted_rows) - 1:
            self._focus_current_idx += 1
            self._update_focus_nav()
            self._scroll_to_focus_current()

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

    # ==================== F2: Edit Mode ====================

    def _on_edit_toggle(self, checked: bool):
        self.table_model.set_editable(checked)

    # ==================== F5: Column Type Conversion ====================

    def _on_column_type_convert(self, column_name: str, target_type: str):
        """Handle column type conversion from header menu."""
        if not self.engine.is_loaded:
            return
        dtype_map = {
            "Int64": pl.Int64,
            "Float64": pl.Float64,
            "String": pl.Utf8,
            "Date": pl.Date,
            "Boolean": pl.Boolean,
        }
        target = dtype_map.get(target_type)
        if target is None:
            return
        try:
            success = self.engine.cast_column(column_name, target)
            if success:
                self._update_table_model(self.engine.df)
                main_window = self.window()
                if main_window and hasattr(main_window, 'statusBar'):
                    main_window.statusBar().showMessage(
                        f"Converted '{column_name}' to {target_type}", 3000
                    )
            else:
                QMessageBox.warning(self, "Type Conversion", f"Failed to convert '{column_name}' to {target_type}")
        except Exception as e:
            QMessageBox.warning(self, "Type Conversion", f"Error: {e}")

    # ==================== F3: Conditional Formatting ====================

    def _on_conditional_format_requested(self, column_name: str):
        """Show conditional formatting dialog for a column."""
        dialog = ConditionalFormatDialog(column_name, self)
        if dialog.exec() == QDialog.Accepted:
            fmt = dialog.get_format()
            if fmt:
                self.table_model.set_conditional_format(column_name, fmt)
            else:
                self.table_model.remove_conditional_format(column_name)

    # ==================== F7: Freeze Columns ====================

    def _on_freeze_column(self, column_name: str):
        """Freeze a column (pin to left)."""
        if column_name not in self._frozen_columns:
            self._frozen_columns.append(column_name)
            self._update_table_model()

    def _on_unfreeze_column(self, column_name: str):
        """Unfreeze a column."""
        if column_name in self._frozen_columns:
            self._frozen_columns.remove(column_name)
            self._update_table_model()

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


# ==================== F9: Pivot Table Dialog ====================

class PivotTableDialog(QDialog):
    """Dialog for creating pivot tables from data."""

    def __init__(self, df: pl.DataFrame, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pivot Table")
        self.setMinimumSize(500, 400)
        self._df = df
        self._result_df: Optional[pl.DataFrame] = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        columns = df.columns

        self.index_combo = QComboBox()
        self.index_combo.addItems(columns)
        form.addRow("Row (Index):", self.index_combo)

        self.columns_combo = QComboBox()
        self.columns_combo.addItems(columns)
        if len(columns) > 1:
            self.columns_combo.setCurrentIndex(1)
        form.addRow("Column:", self.columns_combo)

        self.values_combo = QComboBox()
        # Only numeric columns for values
        numeric_cols = [c for c in columns if df[c].dtype.is_numeric()]
        self.values_combo.addItems(numeric_cols if numeric_cols else columns)
        form.addRow("Values:", self.values_combo)

        self.agg_combo = QComboBox()
        self.agg_combo.addItems(["first", "sum", "mean", "count", "min", "max"])
        self.agg_combo.setCurrentText("sum")
        form.addRow("Aggregation:", self.agg_combo)

        layout.addLayout(form)

        # Preview button
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(self._preview)
        layout.addWidget(preview_btn)

        # Result table
        self.result_view = QTableView()
        self.result_model = PolarsTableModel()
        self.result_view.setModel(self.result_model)
        layout.addWidget(self.result_view)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _preview(self):
        try:
            idx = self.index_combo.currentText()
            cols = self.columns_combo.currentText()
            vals = self.values_combo.currentText()
            agg = self.agg_combo.currentText()

            self._result_df = self._df.pivot(
                values=vals, index=idx, on=cols,
                aggregate_function=agg
            )
            self.result_model.set_dataframe(self._result_df)
        except Exception as e:
            QMessageBox.warning(self, "Pivot Error", str(e))

    def get_result(self) -> Optional[pl.DataFrame]:
        return self._result_df
