"""
Filter Panel - Spotfire 스타일 필터 패널

데이터 필터링을 위한 UI 컴포넌트입니다.
"""

from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import polars as pl

try:
    from PySide6.QtCore import Qt, Signal, QObject
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
        QFrame, QPushButton, QLineEdit, QCheckBox, QSlider,
        QListWidget, QListWidgetItem, QComboBox, QGroupBox,
        QToolButton, QSizePolicy, QSpinBox, QDoubleSpinBox
    )
    HAS_QT = True
except ImportError:
    HAS_QT = False
    # Mock classes for testing without Qt
    class QObject:
        pass
    class Signal:
        def __init__(self, *args):
            pass


class FilterType(Enum):
    """필터 타입"""
    RANGE = "range"           # 범위 슬라이더
    CHECKBOX = "checkbox"     # 체크박스 목록
    TEXT_SEARCH = "text"      # 텍스트 검색
    BOOLEAN = "boolean"       # 불리언 (True/False)
    DATE_RANGE = "date_range" # 날짜 범위


@dataclass
class FilterState:
    """필터 상태"""
    column: str
    filter_type: FilterType
    enabled: bool = True

    # Range filter
    range_min: Optional[float] = None
    range_max: Optional[float] = None

    # Checkbox filter
    selected_values: Set[Any] = field(default_factory=set)
    excluded_values: Set[Any] = field(default_factory=set)

    # Text search
    search_text: str = ""
    case_sensitive: bool = False

    # Boolean
    show_true: bool = True
    show_false: bool = True
    show_null: bool = True


class FilterPanelModel:
    """
    필터 패널 모델

    필터 상태를 관리합니다.
    """

    def __init__(self):
        self._data: Optional[pl.DataFrame] = None
        self._filter_states: Dict[str, FilterState] = {}
        self._column_info: Dict[str, Dict[str, Any]] = {}

    def set_data(self, data: pl.DataFrame) -> None:
        """데이터 설정"""
        self._data = data
        self._analyze_columns()

    def _analyze_columns(self) -> None:
        """컬럼 분석"""
        if self._data is None:
            return

        for col in self._data.columns:
            dtype = self._data[col].dtype

            info = {
                "name": col,
                "dtype": str(dtype),
                "unique_count": self._data[col].n_unique(),
                "null_count": self._data[col].null_count(),
            }

            # 필터 타입 결정
            if dtype in (pl.Boolean,):
                info["filter_type"] = FilterType.BOOLEAN
            elif dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                          pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                          pl.Float32, pl.Float64):
                if info["unique_count"] <= 20:
                    info["filter_type"] = FilterType.CHECKBOX
                else:
                    info["filter_type"] = FilterType.RANGE
                    values = self._data[col].drop_nulls()
                    if len(values) > 0:
                        info["min"] = float(values.min())
                        info["max"] = float(values.max())
            elif dtype in (pl.Date, pl.Datetime):
                info["filter_type"] = FilterType.DATE_RANGE
            else:
                # 문자열 타입
                if info["unique_count"] <= 50:
                    info["filter_type"] = FilterType.CHECKBOX
                else:
                    info["filter_type"] = FilterType.TEXT_SEARCH

            self._column_info[col] = info

    def column_count(self) -> int:
        """컬럼 수"""
        return len(self._column_info)

    def get_filter_type(self, column: str) -> FilterType:
        """필터 타입 조회"""
        if column in self._column_info:
            return self._column_info[column]["filter_type"]
        return FilterType.TEXT_SEARCH

    def get_unique_values(self, column: str) -> List[Any]:
        """고유값 조회"""
        if self._data is None or column not in self._data.columns:
            return []
        return self._data[column].unique().sort().to_list()

    def get_value_range(self, column: str) -> Tuple[float, float]:
        """값 범위 조회"""
        if column in self._column_info:
            info = self._column_info[column]
            return (info.get("min", 0), info.get("max", 100))
        return (0, 100)

    def get_filter_state(self, column: str) -> Optional[FilterState]:
        """필터 상태 조회"""
        return self._filter_states.get(column)

    def set_filter_state(self, column: str, state: FilterState) -> None:
        """필터 상태 설정"""
        self._filter_states[column] = state

    def clear_filter(self, column: str) -> None:
        """필터 클리어"""
        if column in self._filter_states:
            del self._filter_states[column]

    def clear_all_filters(self) -> None:
        """모든 필터 클리어"""
        self._filter_states.clear()

    def get_filtered_indices(self) -> Set[int]:
        """필터된 인덱스 반환"""
        if self._data is None:
            return set()

        mask = pl.Series([True] * len(self._data))

        for col, state in self._filter_states.items():
            if not state.enabled:
                continue

            if col not in self._data.columns:
                continue

            if state.filter_type == FilterType.RANGE:
                if state.range_min is not None:
                    mask = mask & (self._data[col] >= state.range_min)
                if state.range_max is not None:
                    mask = mask & (self._data[col] <= state.range_max)

            elif state.filter_type == FilterType.CHECKBOX:
                if state.selected_values:
                    mask = mask & self._data[col].is_in(list(state.selected_values))

            elif state.filter_type == FilterType.TEXT_SEARCH:
                if state.search_text:
                    if state.case_sensitive:
                        mask = mask & self._data[col].cast(pl.Utf8).str.contains(state.search_text)
                    else:
                        mask = mask & self._data[col].cast(pl.Utf8).str.to_lowercase().str.contains(
                            state.search_text.lower()
                        )

            elif state.filter_type == FilterType.BOOLEAN:
                conditions = []
                if state.show_true:
                    conditions.append(self._data[col] == True)
                if state.show_false:
                    conditions.append(self._data[col] == False)
                if state.show_null:
                    conditions.append(self._data[col].is_null())

                if conditions:
                    combined = conditions[0]
                    for c in conditions[1:]:
                        combined = combined | c
                    mask = mask & combined

        return set(i for i, m in enumerate(mask.to_list()) if m)


class RangeSliderWidget:
    """
    범위 슬라이더 위젯

    최소/최대 값을 선택하는 더블 슬라이더입니다.
    """

    def __init__(
        self,
        min_val: float = 0,
        max_val: float = 100,
        step: float = 1
    ):
        self.min_value = min_val
        self.max_value = max_val
        self.step = step

        self.current_min = min_val
        self.current_max = max_val

        self._widget = None

    def set_range(self, min_val: float, max_val: float) -> None:
        """현재 범위 설정"""
        self.current_min = max(self.min_value, min_val)
        self.current_max = min(self.max_value, max_val)

    def get_filter_value(self) -> Tuple[float, float]:
        """필터 값 반환"""
        return (self.current_min, self.current_max)

    def reset(self) -> None:
        """리셋"""
        self.current_min = self.min_value
        self.current_max = self.max_value


class CheckboxListWidget:
    """
    체크박스 목록 위젯

    다중 선택을 위한 체크박스 목록입니다.
    """

    def __init__(self, values: List[Any]):
        self._all_values = values
        self._selected: Set[Any] = set()
        self._search_filter = ""
        self._widget = None

    def item_count(self) -> int:
        """항목 수"""
        return len(self._all_values)

    def select_all(self) -> None:
        """전체 선택"""
        self._selected = set(self._all_values)

    def deselect_all(self) -> None:
        """전체 해제"""
        self._selected.clear()

    def toggle_item(self, value: Any) -> None:
        """항목 토글"""
        if value in self._selected:
            self._selected.discard(value)
        else:
            self._selected.add(value)

    def set_selected(self, values: Set[Any]) -> None:
        """선택 항목 설정"""
        self._selected = values & set(self._all_values)

    def get_selected_values(self) -> List[Any]:
        """선택된 값 목록"""
        return list(self._selected)

    def set_search_filter(self, text: str) -> None:
        """검색 필터 설정"""
        self._search_filter = text.lower()

    def get_visible_items(self) -> List[Any]:
        """가시적인 항목 목록"""
        if not self._search_filter:
            return self._all_values

        return [
            v for v in self._all_values
            if self._search_filter in str(v).lower()
        ]


class TextSearchWidget:
    """
    텍스트 검색 위젯

    텍스트 필터링을 위한 검색 입력입니다.
    """

    def __init__(self):
        self.search_text = ""
        self.case_sensitive = False
        self._widget = None

    def set_text(self, text: str) -> None:
        """검색 텍스트 설정"""
        self.search_text = text

    def get_text(self) -> str:
        """검색 텍스트 반환"""
        return self.search_text

    def set_case_sensitive(self, sensitive: bool) -> None:
        """대소문자 구분 설정"""
        self.case_sensitive = sensitive


class FilterWidget:
    """
    필터 위젯

    단일 컬럼의 필터 UI입니다.
    """

    def __init__(
        self,
        column: str,
        filter_type: FilterType,
        values: Optional[List[Any]] = None,
        value_range: Optional[Tuple[float, float]] = None
    ):
        self.column = column
        self.filter_type = filter_type
        self.enabled = True

        # 타입별 위젯 생성
        if filter_type == FilterType.RANGE and value_range:
            self._widget = RangeSliderWidget(value_range[0], value_range[1])
        elif filter_type == FilterType.CHECKBOX and values:
            self._widget = CheckboxListWidget(values)
        elif filter_type == FilterType.TEXT_SEARCH:
            self._widget = TextSearchWidget()
        else:
            self._widget = None

    def get_filter_state(self) -> FilterState:
        """필터 상태 반환"""
        state = FilterState(
            column=self.column,
            filter_type=self.filter_type,
            enabled=self.enabled
        )

        if isinstance(self._widget, RangeSliderWidget):
            min_val, max_val = self._widget.get_filter_value()
            state.range_min = min_val
            state.range_max = max_val

        elif isinstance(self._widget, CheckboxListWidget):
            state.selected_values = set(self._widget.get_selected_values())

        elif isinstance(self._widget, TextSearchWidget):
            state.search_text = self._widget.get_text()
            state.case_sensitive = self._widget.case_sensitive

        return state

    def reset(self) -> None:
        """리셋"""
        if hasattr(self._widget, 'reset'):
            self._widget.reset()
        elif isinstance(self._widget, CheckboxListWidget):
            self._widget.select_all()
        elif isinstance(self._widget, TextSearchWidget):
            self._widget.set_text("")


if HAS_QT:
    class FilterPanelWidget(QWidget):
        """
        필터 패널 위젯

        모든 컬럼의 필터를 표시하는 패널입니다.
        """

        filter_changed = Signal()

        def __init__(self, parent=None):
            super().__init__(parent)

            self._model = FilterPanelModel()
            self._filter_widgets: Dict[str, FilterWidget] = {}

            self.setAccessibleName("Filter Panel")
            self.setAccessibleDescription("Data filtering controls for each column")

            self._setup_ui()

        def _setup_ui(self) -> None:
            """UI 설정"""
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)

            # 헤더
            header = QFrame()
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(8, 4, 8, 4)

            title = QLabel("Filters")
            title.setStyleSheet("font-weight: bold;")
            header_layout.addWidget(title)

            header_layout.addStretch()

            reset_btn = QPushButton("Reset All")
            reset_btn.setToolTip("Reset all filters to default values")
            reset_btn.clicked.connect(self._reset_all_filters)
            header_layout.addWidget(reset_btn)

            layout.addWidget(header)

            # 스크롤 영역
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)

            self._filter_container = QWidget()
            self._filter_layout = QVBoxLayout(self._filter_container)
            self._filter_layout.setContentsMargins(8, 8, 8, 8)
            self._filter_layout.setSpacing(8)
            self._filter_layout.addStretch()

            scroll.setWidget(self._filter_container)
            layout.addWidget(scroll)

        def set_data(self, data: pl.DataFrame) -> None:
            """데이터 설정"""
            self._model.set_data(data)
            self._build_filters()

        def _build_filters(self) -> None:
            """필터 위젯 생성"""
            # 기존 위젯 제거
            for i in reversed(range(self._filter_layout.count() - 1)):
                item = self._filter_layout.itemAt(i)
                if item.widget():
                    item.widget().deleteLater()

            self._filter_widgets.clear()

            # 새 필터 생성
            if self._model._data is None:
                return

            for col in self._model._data.columns:
                filter_type = self._model.get_filter_type(col)

                values = None
                value_range = None

                if filter_type == FilterType.CHECKBOX:
                    values = self._model.get_unique_values(col)
                elif filter_type == FilterType.RANGE:
                    value_range = self._model.get_value_range(col)

                widget = FilterWidget(col, filter_type, values, value_range)
                self._filter_widgets[col] = widget

                # UI 추가 (간소화)
                group = QGroupBox(col)
                group_layout = QVBoxLayout(group)
                group_layout.addWidget(QLabel(f"Type: {filter_type.value}"))

                idx = self._filter_layout.count() - 1
                self._filter_layout.insertWidget(idx, group)

        def _reset_all_filters(self) -> None:
            """모든 필터 리셋"""
            for widget in self._filter_widgets.values():
                widget.reset()
            self._model.clear_all_filters()
            self.filter_changed.emit()

        def get_filtered_indices(self) -> Set[int]:
            """필터된 인덱스 반환"""
            # 현재 위젯 상태를 모델에 반영
            for col, widget in self._filter_widgets.items():
                state = widget.get_filter_state()
                self._model.set_filter_state(col, state)

            return self._model.get_filtered_indices()
