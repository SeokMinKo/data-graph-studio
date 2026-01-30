"""
State Management - 앱 상태 관리
"""

from typing import Optional, List, Dict, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from PySide6.QtCore import QObject, Signal


class AggregationType(Enum):
    """집계 함수 타입"""
    SUM = "sum"
    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    STD = "std"
    VAR = "var"
    FIRST = "first"
    LAST = "last"


class ChartType(Enum):
    """차트 타입"""
    # 기본 차트
    LINE = "line"
    BAR = "bar"
    SCATTER = "scatter"
    AREA = "area"
    PIE = "pie"
    HISTOGRAM = "histogram"

    # 통계 차트
    HEATMAP = "heatmap"
    BOX = "box"
    VIOLIN = "violin"

    # Phase 2: 기본 확장 차트
    HORIZONTAL_BAR = "horizontal_bar"
    STACKED_BAR = "stacked_bar"
    STACKED_BAR_100 = "stacked_bar_100"
    BUBBLE = "bubble"
    COMBINATION = "combination"
    DONUT = "donut"

    # Phase 3: 고급 확장 차트
    TREEMAP = "treemap"
    SUNBURST = "sunburst"
    SANKEY = "sankey"
    FUNNEL = "funnel"
    RADAR = "radar"
    GAUGE = "gauge"
    GANTT = "gantt"
    PARALLEL_COORDINATES = "parallel_coordinates"
    NETWORK = "network"

    # Spotfire 특화 차트
    CROSS_TABLE = "cross_table"
    GRAPHICAL_TABLE = "graphical_table"
    SUMMARY_TABLE = "summary_table"
    KPI = "kpi"


class ToolMode(Enum):
    """그래프 툴 모드"""
    ZOOM = "zoom"
    PAN = "pan"
    RECT_SELECT = "rect_select"
    LASSO_SELECT = "lasso_select"


@dataclass
class GroupColumn:
    """그룹 존의 컬럼"""
    name: str
    selected_values: Set[str] = field(default_factory=set)  # 선택된 값들 (빈셋=전체)
    order: int = 0


@dataclass
class ValueColumn:
    """밸류 존의 컬럼"""
    name: str
    aggregation: AggregationType = AggregationType.SUM
    color: str = "#1f77b4"
    use_secondary_axis: bool = False
    order: int = 0


@dataclass
class FilterCondition:
    """필터 조건"""
    column: str
    operator: str  # eq, ne, gt, lt, ge, le, contains, etc.
    value: Any
    enabled: bool = True


@dataclass
class SortCondition:
    """정렬 조건"""
    column: str
    descending: bool = False


@dataclass
class ChartSettings:
    """차트 설정"""
    chart_type: ChartType = ChartType.LINE
    x_column: Optional[str] = None
    
    # 스타일
    line_width: int = 2
    marker_size: int = 6
    fill_opacity: float = 0.3
    show_data_labels: bool = False
    
    # Primary Y축 설정
    x_log_scale: bool = False
    y_log_scale: bool = False
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    y_label: Optional[str] = None
    
    # Secondary Y축 설정
    secondary_y_log_scale: bool = False
    secondary_y_min: Optional[float] = None
    secondary_y_max: Optional[float] = None
    secondary_y_label: Optional[str] = None


@dataclass
class SelectionState:
    """선택 상태"""
    selected_rows: Set[int] = field(default_factory=set)
    highlighted_rows: Set[int] = field(default_factory=set)
    
    @property
    def has_selection(self) -> bool:
        return len(self.selected_rows) > 0
    
    @property
    def selection_count(self) -> int:
        return len(self.selected_rows)
    
    def clear(self):
        self.selected_rows.clear()
        self.highlighted_rows.clear()
    
    def select(self, rows: List[int], add: bool = False):
        if not add:
            self.selected_rows.clear()
        self.selected_rows.update(rows)
    
    def deselect(self, rows: List[int]):
        self.selected_rows.difference_update(rows)
    
    def toggle(self, row: int):
        if row in self.selected_rows:
            self.selected_rows.remove(row)
        else:
            self.selected_rows.add(row)


class AppState(QObject):
    """
    앱 전역 상태 관리
    
    Signals로 상태 변경을 UI에 알림
    """
    
    # Signals
    data_loaded = Signal()
    data_cleared = Signal()
    
    group_zone_changed = Signal()
    value_zone_changed = Signal()
    
    filter_changed = Signal()
    sort_changed = Signal()
    
    selection_changed = Signal()
    
    chart_settings_changed = Signal()
    tool_mode_changed = Signal()
    
    # Summary 업데이트
    summary_updated = Signal(dict)  # 통계 데이터
    
    def __init__(self):
        super().__init__()
        
        # 데이터 상태
        self._data_loaded: bool = False
        self._total_rows: int = 0
        self._visible_rows: int = 0
        
        # Group Zone
        self._group_columns: List[GroupColumn] = []
        
        # Value Zone
        self._value_columns: List[ValueColumn] = []
        
        # X축 컬럼
        self._x_column: Optional[str] = None
        
        # 필터 & 정렬
        self._filters: List[FilterCondition] = []
        self._sorts: List[SortCondition] = []
        
        # 선택 상태
        self._selection = SelectionState()
        
        # 차트 설정
        self._chart_settings = ChartSettings()
        
        # 툴 모드
        self._tool_mode = ToolMode.PAN
        
        # 레이아웃 (높이 비율)
        self._layout_ratios = {
            'summary': 0.10,
            'graph': 0.45,
            'table': 0.45
        }
        
        # 컬럼 순서 (테이블)
        self._column_order: List[str] = []
        self._hidden_columns: Set[str] = set()
    
    # ==================== Data ====================
    
    @property
    def is_data_loaded(self) -> bool:
        return self._data_loaded
    
    def set_data_loaded(self, loaded: bool, total_rows: int = 0):
        self._data_loaded = loaded
        self._total_rows = total_rows
        self._visible_rows = total_rows
        if loaded:
            self.data_loaded.emit()
        else:
            self.data_cleared.emit()
    
    @property
    def total_rows(self) -> int:
        return self._total_rows
    
    @property
    def visible_rows(self) -> int:
        return self._visible_rows
    
    def set_visible_rows(self, count: int):
        self._visible_rows = count
    
    # ==================== Group Zone ====================
    
    @property
    def group_columns(self) -> List[GroupColumn]:
        return self._group_columns
    
    def add_group_column(self, name: str, index: int = -1):
        # 중복 방지
        if any(g.name == name for g in self._group_columns):
            return
        
        col = GroupColumn(name=name, order=len(self._group_columns))
        if index < 0:
            self._group_columns.append(col)
        else:
            self._group_columns.insert(index, col)
            self._reorder_groups()
        
        self.group_zone_changed.emit()
    
    def remove_group_column(self, name: str):
        self._group_columns = [g for g in self._group_columns if g.name != name]
        self._reorder_groups()
        self.group_zone_changed.emit()
    
    def reorder_group_columns(self, new_order: List[str]):
        name_to_col = {g.name: g for g in self._group_columns}
        self._group_columns = [name_to_col[name] for name in new_order if name in name_to_col]
        self._reorder_groups()
        self.group_zone_changed.emit()
    
    def _reorder_groups(self):
        for i, g in enumerate(self._group_columns):
            g.order = i
    
    def clear_group_zone(self):
        self._group_columns.clear()
        self.group_zone_changed.emit()
    
    # ==================== Value Zone ====================
    
    @property
    def value_columns(self) -> List[ValueColumn]:
        return self._value_columns
    
    def add_value_column(
        self, 
        name: str, 
        aggregation: AggregationType = AggregationType.SUM,
        index: int = -1
    ):
        # 중복 허용 (같은 컬럼 다른 집계)
        col = ValueColumn(
            name=name, 
            aggregation=aggregation,
            order=len(self._value_columns)
        )
        
        # 색상 자동 할당
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
        col.color = colors[len(self._value_columns) % len(colors)]
        
        if index < 0:
            self._value_columns.append(col)
        else:
            self._value_columns.insert(index, col)
            self._reorder_values()
        
        self.value_zone_changed.emit()
    
    def remove_value_column(self, index: int):
        if 0 <= index < len(self._value_columns):
            self._value_columns.pop(index)
            self._reorder_values()
            self.value_zone_changed.emit()
    
    def update_value_column(
        self, 
        index: int, 
        aggregation: Optional[AggregationType] = None,
        color: Optional[str] = None,
        use_secondary_axis: Optional[bool] = None
    ):
        if 0 <= index < len(self._value_columns):
            if aggregation is not None:
                self._value_columns[index].aggregation = aggregation
            if color is not None:
                self._value_columns[index].color = color
            if use_secondary_axis is not None:
                self._value_columns[index].use_secondary_axis = use_secondary_axis
            self.value_zone_changed.emit()
    
    def _reorder_values(self):
        for i, v in enumerate(self._value_columns):
            v.order = i
    
    def clear_value_zone(self):
        self._value_columns.clear()
        self.value_zone_changed.emit()
    
    def get_primary_values(self) -> List[ValueColumn]:
        """Primary 축에 할당된 값 컬럼 목록"""
        return [v for v in self._value_columns if not v.use_secondary_axis]
    
    def get_secondary_values(self) -> List[ValueColumn]:
        """Secondary 축에 할당된 값 컬럼 목록"""
        return [v for v in self._value_columns if v.use_secondary_axis]
    
    def has_secondary_axis(self) -> bool:
        """Secondary 축 존재 여부"""
        return any(v.use_secondary_axis for v in self._value_columns)
    
    # ==================== X Column ====================
    
    @property
    def x_column(self) -> Optional[str]:
        return self._x_column
    
    def set_x_column(self, name: Optional[str]):
        self._x_column = name
        self.chart_settings_changed.emit()
    
    # ==================== Filters ====================
    
    @property
    def filters(self) -> List[FilterCondition]:
        return self._filters
    
    def add_filter(self, column: str, operator: str, value: Any):
        self._filters.append(FilterCondition(column, operator, value))
        self.filter_changed.emit()
    
    def remove_filter(self, index: int):
        if 0 <= index < len(self._filters):
            self._filters.pop(index)
            self.filter_changed.emit()
    
    def clear_filters(self):
        self._filters.clear()
        self.filter_changed.emit()
    
    def toggle_filter(self, index: int):
        if 0 <= index < len(self._filters):
            self._filters[index].enabled = not self._filters[index].enabled
            self.filter_changed.emit()
    
    # ==================== Sorts ====================
    
    @property
    def sorts(self) -> List[SortCondition]:
        return self._sorts
    
    def set_sort(self, column: str, descending: bool = False, add: bool = False):
        if not add:
            self._sorts.clear()
        
        # 기존 정렬 제거
        self._sorts = [s for s in self._sorts if s.column != column]
        self._sorts.append(SortCondition(column, descending))
        self.sort_changed.emit()
    
    def clear_sorts(self):
        self._sorts.clear()
        self.sort_changed.emit()
    
    # ==================== Selection ====================
    
    @property
    def selection(self) -> SelectionState:
        return self._selection
    
    def select_rows(self, rows: List[int], add: bool = False):
        self._selection.select(rows, add)
        self.selection_changed.emit()
    
    def deselect_rows(self, rows: List[int]):
        self._selection.deselect(rows)
        self.selection_changed.emit()
    
    def toggle_row(self, row: int):
        self._selection.toggle(row)
        self.selection_changed.emit()
    
    def clear_selection(self):
        self._selection.clear()
        self.selection_changed.emit()
    
    def select_all(self):
        self._selection.select(list(range(self._visible_rows)))
        self.selection_changed.emit()
    
    # ==================== Chart Settings ====================
    
    @property
    def chart_settings(self) -> ChartSettings:
        return self._chart_settings
    
    def set_chart_type(self, chart_type: ChartType):
        self._chart_settings.chart_type = chart_type
        self.chart_settings_changed.emit()
    
    def update_chart_settings(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self._chart_settings, key):
                setattr(self._chart_settings, key, value)
        self.chart_settings_changed.emit()
    
    # ==================== Tool Mode ====================
    
    @property
    def tool_mode(self) -> ToolMode:
        return self._tool_mode
    
    def set_tool_mode(self, mode: ToolMode):
        self._tool_mode = mode
        self.tool_mode_changed.emit()
    
    # ==================== Layout ====================
    
    @property
    def layout_ratios(self) -> Dict[str, float]:
        return self._layout_ratios
    
    def set_layout_ratio(self, section: str, ratio: float):
        if section in self._layout_ratios:
            # 비율 조정 (합이 1이 되도록)
            old_ratio = self._layout_ratios[section]
            diff = ratio - old_ratio
            
            other_sections = [k for k in self._layout_ratios if k != section]
            for other in other_sections:
                self._layout_ratios[other] -= diff / len(other_sections)
            
            self._layout_ratios[section] = ratio
    
    # ==================== Column Order ====================
    
    def set_column_order(self, order: List[str]):
        self._column_order = order
    
    def get_column_order(self) -> List[str]:
        return self._column_order
    
    def toggle_column_visibility(self, column: str):
        if column in self._hidden_columns:
            self._hidden_columns.remove(column)
        else:
            self._hidden_columns.add(column)
    
    def get_visible_columns(self) -> List[str]:
        return [c for c in self._column_order if c not in self._hidden_columns]
    
    # ==================== Summary Update ====================
    
    def update_summary(self, stats: Dict[str, Any]):
        """Summary 패널 업데이트"""
        self.summary_updated.emit(stats)
    
    # ==================== Reset ====================
    
    def reset(self):
        """전체 상태 초기화"""
        self._data_loaded = False
        self._total_rows = 0
        self._visible_rows = 0
        self._group_columns.clear()
        self._value_columns.clear()
        self._x_column = None
        self._filters.clear()
        self._sorts.clear()
        self._selection.clear()
        self._chart_settings = ChartSettings()
        self._tool_mode = ToolMode.PAN
        self._column_order.clear()
        self._hidden_columns.clear()
        
        self.data_cleared.emit()
