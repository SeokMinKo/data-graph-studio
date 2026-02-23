"""PolarsTableModel - Qt table model backed by a Polars DataFrame."""

from typing import Optional, List, Dict, Set, Tuple
from collections import OrderedDict
import logging
import polars as pl

logger = logging.getLogger(__name__)

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex,
)
from PySide6.QtGui import QBrush, QColor

from .conditional_formatting import ConditionalFormat


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
            logger.exception("polars_table_model.setData.error")
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
            logger.warning("polars_table_model.fill_column_cache.error", exc_info=True)
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
                    logger.warning("polars_table_model.headerData.tooltip.error", exc_info=True)
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
                    logger.warning("polars_table_model.update_conditional_format_ranges.error", exc_info=True)

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
            logger.error("table_panel.sort_error", extra={"error": str(e)}, exc_info=True)
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
            logger.error("table_panel.multi_sort_error", extra={"error": str(e)}, exc_info=True)
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
