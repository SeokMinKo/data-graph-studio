"""
State Types - Value Objects and Enums for State Management

Pure value objects and enums with no AppState references.
Extracted from state.py for improved modularity.
"""

from typing import Optional, List, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from data_graph_studio.core.exceptions import ValidationError


# ==================== Theme State (PRD §3.6 / §9.3) ====================

@dataclass
class ThemeState:
    """테마 상태 - PRD §9.3"""
    current: str = "system"    # "light" | "dark" | "system"


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
    # Drawing modes
    LINE_DRAW = "line_draw"
    ARROW_DRAW = "arrow_draw"
    CIRCLE_DRAW = "circle_draw"
    RECT_DRAW = "rect_draw"
    TEXT_DRAW = "text_draw"


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
    formula: str = ""  # Y값에 적용할 수식 (예: "y*2", "y+100", "LOG(y)")


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


class GridDirection(Enum):
    """Grid View 방향"""
    ROW = "row"       # 가로 나열
    COLUMN = "column" # 세로 나열
    WRAP = "wrap"     # 자동 줄바꿈


@dataclass
class GridViewSettings:
    """Grid View (Facet Grid) 설정"""
    enabled: bool = False
    split_by: Optional[str] = None  # 분할 기준 열
    direction: GridDirection = GridDirection.WRAP
    max_columns: int = 4  # Wrap 모드에서 최대 열 수


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

    # Grid View 설정
    grid_view: GridViewSettings = field(default_factory=GridViewSettings)


@dataclass
class SelectionState:
    """선택 상태"""
    selected_rows: Set[int] = field(default_factory=set)
    highlighted_rows: Set[int] = field(default_factory=set)

    @property
    def has_selection(self) -> bool:
        """Return True if at least one row is selected.

        Output: bool — True when selected_rows is non-empty
        """
        return len(self.selected_rows) > 0

    @property
    def selection_count(self) -> int:
        """Return the number of currently selected rows.

        Output: int — len(selected_rows), >= 0
        """
        return len(self.selected_rows)

    def clear(self):
        """Clear all selected and highlighted rows.

        Output: None
        Invariants: selected_rows and highlighted_rows are empty after this call
        """
        self.selected_rows.clear()
        self.highlighted_rows.clear()

    def select(self, rows: List[int], add: bool = False):
        """Add rows to the selection set.

        Input: rows — List[int], row indices to select (must be non-negative integers);
               add — bool; if True merges with existing selection, if False replaces it.
        Output: None
        Raises: ValidationError — if any row index is not a non-negative integer.
        Invariants: all elements of rows are present in selected_rows after this call.
        """
        invalid = [r for r in rows if not isinstance(r, int) or r < 0]
        if invalid:
            raise ValidationError(
                f"row index must be a non-negative integer, got: {invalid[:3]}",
                operation="select",
                context={"invalid_sample": invalid[:3]},
            )
        if not add:
            self.selected_rows.clear()
        self.selected_rows.update(rows)

    def deselect(self, rows: List[int]):
        """Remove rows from the selection set.

        Input: rows — List[int], row indices to deselect (must be non-negative integers).
        Output: None
        Raises: ValidationError — if any row index is not a non-negative integer.
        Invariants: no element of rows remains in selected_rows after this call.
        """
        invalid = [r for r in rows if not isinstance(r, int) or r < 0]
        if invalid:
            raise ValidationError(
                f"row index must be a non-negative integer, got: {invalid[:3]}",
                operation="deselect",
                context={"invalid_sample": invalid[:3]},
            )
        self.selected_rows.difference_update(rows)

    def toggle(self, row: int):
        """Toggle the selection state of a single row.

        Input: row — int, row index to toggle (non-negative).
        Output: None
        Invariants: if row was selected it is deselected, and vice versa.
        """
        if row in self.selected_rows:
            self.selected_rows.remove(row)
        else:
            self.selected_rows.add(row)
