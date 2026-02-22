"""
State Management - 앱 상태 관리

멀티 데이터셋 비교 기능 지원
"""

from typing import Optional, List, Dict, Any, Set, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import uuid
import copy
import time
from PySide6.QtCore import QObject, Signal

from .undo_manager import UndoStack, UndoCommand, UndoActionType
# comparison_manager defines the comparison types and ComparisonManager class.
# We import the types here so existing code using
#   from data_graph_studio.core.state import ComparisonMode, ...
# continues to work unchanged (backward compatibility).
from .comparison_manager import (
    ComparisonManager,
    ComparisonMode,
    ComparisonSettings,
    DatasetMetadata,
    DatasetState,
    DEFAULT_DATASET_COLORS,
)

if TYPE_CHECKING:
    from .profile import Profile, GraphSetting


# ==================== Theme State (PRD §3.6 / §9.3) ====================

@dataclass
class ThemeState:
    """테마 상태 - PRD §9.3"""
    current: str = "system"    # "light" | "dark" | "system"


# 차이 모드 색상 (비교 색상 팔레트는 comparison_manager.py 참조)
from data_graph_studio.core.constants import (
    DIFF_POSITIVE_COLOR,
    DIFF_NEGATIVE_COLOR,
    DIFF_NEUTRAL_COLOR,
)


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
        """True if at least one row is selected."""
        return len(self.selected_rows) > 0

    @property
    def selection_count(self) -> int:
        """Number of currently selected rows."""
        return len(self.selected_rows)

    def clear(self):
        """Clear all selected and highlighted rows."""
        self.selected_rows.clear()
        self.highlighted_rows.clear()

    def select(self, rows: List[int], add: bool = False):
        """
        Add rows to the selection set.

        Args:
            rows: Row indices to select. Must be non-negative.
            add: If True, add to existing selection. If False, replace it.
        """
        invalid = [r for r in rows if not isinstance(r, int) or r < 0]
        if invalid:
            raise ValueError(f"row index must be a non-negative integer, got: {invalid[:3]}")
        if not add:
            self.selected_rows.clear()
        self.selected_rows.update(rows)

    def deselect(self, rows: List[int]):
        """
        Remove rows from the selection set.

        Args:
            rows: Row indices to deselect.
        """
        invalid = [r for r in rows if not isinstance(r, int) or r < 0]
        if invalid:
            raise ValueError(f"row index must be a non-negative integer, got: {invalid[:3]}")
        self.selected_rows.difference_update(rows)

    def toggle(self, row: int):
        """
        Toggle selection state of a single row.

        Args:
            row: Row index to toggle.
        """
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
    hover_zone_changed = Signal()  # New signal for hover columns

    filter_changed = Signal()
    sort_changed = Signal()

    selection_changed = Signal()
    limit_to_marking_changed = Signal(bool)  # Limit table to marked rows

    chart_settings_changed = Signal()
    tool_mode_changed = Signal()
    grid_view_changed = Signal()  # Grid View 설정 변경

    # Summary 업데이트
    summary_updated = Signal(dict)  # 통계 데이터

    # Profile signals
    profile_loaded = Signal(object)       # Profile
    profile_cleared = Signal()
    profile_saved = Signal()
    setting_activated = Signal(str)       # setting_id
    setting_added = Signal(str)           # setting_id
    setting_removed = Signal(str)         # setting_id
    floating_window_opened = Signal(str)  # setting_id
    floating_window_closed = Signal(str)  # window_id

    # Multi-dataset comparison signals
    dataset_added = Signal(str)           # dataset_id
    dataset_removed = Signal(str)         # dataset_id
    dataset_activated = Signal(str)       # dataset_id
    dataset_updated = Signal(str)         # dataset_id
    comparison_mode_changed = Signal(str) # mode
    comparison_settings_changed = Signal()

    def __init__(self):
        super().__init__()

        # Undo/Redo (session-only)
        self._undo_stack: Optional[UndoStack] = None
        self._undo_paused: int = 0

        # Batch update (signal batching)
        self._batch_depth: int = 0
        self._batch_pending_signals: List[str] = []

        # 데이터 상태
        self._data_loaded: bool = False
        self._total_rows: int = 0
        self._visible_rows: int = 0

        # Group Zone
        self._group_columns: List[GroupColumn] = []

        # Value Zone
        self._value_columns: List[ValueColumn] = []

        # Hover Zone - columns to show on hover
        self._hover_columns: List[str] = []

        # X축 컬럼
        self._x_column: Optional[str] = None

        # 필터 & 정렬
        self._filters: List[FilterCondition] = []
        self._sorts: List[SortCondition] = []

        # 선택 상태
        self._selection = SelectionState()
        self._limit_to_marking = False  # When True, table shows only marked rows

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

        # Profile 관련
        self._current_profile: Optional['Profile'] = None
        self._current_setting_id: Optional[str] = None
        self._floating_windows: Dict[str, Any] = {}  # window_id -> FloatingGraphWindow

        # Multi-dataset comparison — delegated to ComparisonManager
        # Lazy import avoids circular dependency with comparison_manager.py
        from .comparison_manager import ComparisonManager
        self.comparison_manager = ComparisonManager()

        # Forward ComparisonManager events through AppState's own Qt signals so
        # all existing external listeners (connected to AppState) still work.
        self.comparison_manager.subscribe("dataset_added", self.dataset_added.emit)
        self.comparison_manager.subscribe("dataset_removed", self.dataset_removed.emit)
        self.comparison_manager.subscribe("dataset_activated", self.dataset_activated.emit)
        self.comparison_manager.subscribe("dataset_updated", self.dataset_updated.emit)
        self.comparison_manager.subscribe("comparison_mode_changed", self.comparison_mode_changed.emit)
        self.comparison_manager.subscribe("comparison_settings_changed", self.comparison_settings_changed.emit)

        # Sync AppState legacy props when active dataset changes in SINGLE mode
        self.comparison_manager.subscribe("dataset_activated", self._on_dataset_activated)

    # ==================== Batch Update ====================

    def set_undo_stack(self, stack: Optional[UndoStack]) -> None:
        """
        Attach an undo stack for recording undoable state mutations.

        Args:
            stack: UndoStack instance to use, or None to disable undo recording.
        """
        self._undo_stack = stack

    def _push_undo(self, cmd: UndoCommand) -> None:
        if not self._undo_stack:
            return
        if self._undo_paused > 0:
            return
        # AppState methods usually already applied the mutation; only record.
        self._undo_stack.record(cmd)

    def begin_batch_update(self):
        """시그널 일괄 발행을 위한 배치 시작"""
        self._batch_depth += 1

    def end_batch_update(self):
        """배치 종료 시 보류된 시그널 발행"""
        self._batch_depth = max(0, self._batch_depth - 1)
        if self._batch_depth == 0:
            # 보류된 시그널 한 번씩만 발행
            emitted = set()
            for sig_name in self._batch_pending_signals:
                if sig_name not in emitted:
                    sig = getattr(self, sig_name, None)
                    if sig is not None:
                        sig.emit()
                    emitted.add(sig_name)
            self._batch_pending_signals.clear()

    # ==================== Multi-Dataset Comparison (delegates to ComparisonManager) ====================

    # --- Internal proxy properties (backward-compat for tests/internal code that accesses _xx) ---
    # These return the underlying mutable dicts from ComparisonManager so direct item
    # assignment (state._dataset_states["x"] = ...) still works as before.

    @property
    def _dataset_states(self) -> Dict[str, DatasetState]:
        return self.comparison_manager._dataset_states

    @_dataset_states.setter
    def _dataset_states(self, value):
        self.comparison_manager._dataset_states = value

    @property
    def _dataset_metadata(self) -> Dict[str, DatasetMetadata]:
        return self.comparison_manager._dataset_metadata

    @_dataset_metadata.setter
    def _dataset_metadata(self, value):
        self.comparison_manager._dataset_metadata = value

    @property
    def _active_dataset_id(self) -> Optional[str]:
        return self.comparison_manager._active_dataset_id

    @_active_dataset_id.setter
    def _active_dataset_id(self, value: Optional[str]):
        self.comparison_manager._active_dataset_id = value

    @property
    def _comparison_settings(self) -> ComparisonSettings:
        return self.comparison_manager._comparison_settings

    @_comparison_settings.setter
    def _comparison_settings(self, value: ComparisonSettings):
        self.comparison_manager._comparison_settings = value

    # --- Public properties ---

    @property
    def dataset_states(self) -> Dict[str, DatasetState]:
        """모든 데이터셋 상태"""
        return self.comparison_manager.dataset_states

    @property
    def dataset_metadata(self) -> Dict[str, DatasetMetadata]:
        """모든 데이터셋 메타데이터"""
        return self.comparison_manager.dataset_metadata

    @property
    def active_dataset_id(self) -> Optional[str]:
        """현재 활성 데이터셋 ID"""
        return self.comparison_manager.active_dataset_id

    @property
    def active_dataset_state(self) -> Optional[DatasetState]:
        """현재 활성 데이터셋의 상태"""
        return self.comparison_manager.active_dataset_state

    @property
    def comparison_settings(self) -> ComparisonSettings:
        """비교 모드 설정"""
        return self.comparison_manager.comparison_settings

    @property
    def comparison_mode(self) -> ComparisonMode:
        """현재 비교 모드"""
        return self.comparison_manager.comparison_mode

    @property
    def dataset_count(self) -> int:
        """로드된 데이터셋 수"""
        return self.comparison_manager.dataset_count

    @property
    def comparison_dataset_ids(self) -> List[str]:
        """비교 대상 데이터셋 ID 목록"""
        return self.comparison_manager.comparison_dataset_ids

    @property
    def is_profile_comparison_active(self) -> bool:
        """프로파일 비교 모드 활성 여부"""
        return self.comparison_manager.is_profile_comparison_active

    # --- Dataset CRUD ---

    def get_dataset_state(self, dataset_id: str) -> Optional[DatasetState]:
        """특정 데이터셋의 상태 조회"""
        return self.comparison_manager.get_dataset_state(dataset_id)

    def get_dataset_metadata(self, dataset_id: str) -> Optional[DatasetMetadata]:
        """특정 데이터셋의 메타데이터 조회"""
        return self.comparison_manager.get_dataset_metadata(dataset_id)

    def add_dataset(self, dataset_id: str, name: str = "", file_path: str = None,
                    row_count: int = 0, column_count: int = 0, memory_bytes: int = 0) -> DatasetState:
        """새 데이터셋 추가. 생성된 DatasetState 반환."""
        return self.comparison_manager.add_dataset(
            dataset_id, name=name, file_path=file_path,
            row_count=row_count, column_count=column_count, memory_bytes=memory_bytes,
        )

    def remove_dataset(self, dataset_id: str) -> bool:
        """데이터셋 제거"""
        return self.comparison_manager.remove_dataset(dataset_id)

    def activate_dataset(self, dataset_id: str) -> bool:
        """데이터셋 활성화.

        단일 모드에서는 활성 데이터셋의 상태를 기존 AppState 속성들과 동기화.
        동기화는 _on_dataset_activated 슬롯에서 처리됨.
        """
        return self.comparison_manager.activate_dataset(dataset_id)

    def _on_dataset_activated(self, dataset_id: str):
        """ComparisonManager.dataset_activated 신호 수신 → SINGLE 모드 동기화."""
        if self.comparison_manager.comparison_mode == ComparisonMode.SINGLE:
            self._sync_from_dataset_state(dataset_id)

    def update_dataset_metadata(self, dataset_id: str, **kwargs):
        """데이터셋 메타데이터 업데이트"""
        self.comparison_manager.update_dataset_metadata(dataset_id, **kwargs)

    def clear_all_datasets(self):
        """모든 데이터셋 제거"""
        self.comparison_manager.clear_all_datasets()

    # --- Comparison mode & settings ---

    def set_comparison_mode(self, mode: ComparisonMode):
        """비교 모드 설정"""
        self.comparison_manager.set_comparison_mode(mode)

    def set_comparison_datasets(self, dataset_ids: List[str]):
        """비교 대상 데이터셋 설정"""
        self.comparison_manager.set_comparison_datasets(dataset_ids)

    def toggle_dataset_comparison(self, dataset_id: str) -> bool:
        """데이터셋 비교 포함 여부 토글"""
        return self.comparison_manager.toggle_dataset_comparison(dataset_id)

    def set_dataset_color(self, dataset_id: str, color: str):
        """데이터셋 색상 설정"""
        self.comparison_manager.set_dataset_color(dataset_id, color)

    def get_comparison_colors(self) -> Dict[str, str]:
        """비교 대상 데이터셋들의 색상 매핑"""
        return self.comparison_manager.get_comparison_colors()

    def update_comparison_settings(self, **kwargs):
        """비교 설정 업데이트"""
        self.comparison_manager.update_comparison_settings(**kwargs)

    # ==================== Profile Comparison (PRD §6.1) ====================

    def set_profile_comparison(self, dataset_id: str, profile_ids: List[str]):
        """프로파일 비교 모드 진입. FR-8: 데이터셋 비교가 활성이면 자동 해제."""
        self.comparison_manager.set_profile_comparison(dataset_id, profile_ids)

    def clear_profile_comparison(self):
        """프로파일 비교 모드 종료 → SINGLE 모드 복귀."""
        self.comparison_manager.clear_profile_comparison()

    # ==================== Dataset Profiles ====================

    def add_graph_setting_to_dataset(self, dataset_id: str, setting: 'GraphSetting') -> bool:
        """
        Add a GraphSetting to a dataset's profile list.

        Args:
            dataset_id: Target dataset identifier.
            setting: GraphSetting to add.

        Returns:
            True if the setting was added successfully, False otherwise.
        """
        return self.comparison_manager.add_graph_setting_to_dataset(dataset_id, setting)

    def remove_graph_setting(self, dataset_id: str, setting_id: str) -> bool:
        """
        Remove a GraphSetting from a dataset's profile list.

        Args:
            dataset_id: Target dataset identifier.
            setting_id: ID of the setting to remove.

        Returns:
            True if the setting was removed, False if not found.
        """
        return self.comparison_manager.remove_graph_setting(dataset_id, setting_id)

    def rename_graph_setting(self, dataset_id: str, setting_id: str, name: str) -> bool:
        """
        Rename a GraphSetting within a dataset's profile list.

        Args:
            dataset_id: Target dataset identifier.
            setting_id: ID of the setting to rename.
            name: New display name for the setting.

        Returns:
            True if the rename succeeded, False if the setting was not found.
        """
        return self.comparison_manager.rename_graph_setting(dataset_id, setting_id, name)

    def get_dataset_profiles(self, dataset_id: str) -> List['GraphSetting']:
        """
        Return all saved GraphSettings for a dataset.

        Args:
            dataset_id: Target dataset identifier.

        Returns:
            List of GraphSetting objects associated with the dataset.
        """
        return self.comparison_manager.get_dataset_profiles(dataset_id)

    def build_graph_setting_from_state(self, name: str, dataset_id: str = "") -> 'GraphSetting':
        """
        Create a GraphSetting snapshot from the current AppState.

        Args:
            name: Display name for the new setting.
            dataset_id: Optional dataset ID to associate the setting with.

        Returns:
            A new GraphSetting populated with the current chart, zone, filter, and sort state.
        """
        from .profile import GraphSetting
        current = self.get_current_graph_state()
        gs = GraphSetting(
            id=str(uuid.uuid4()),
            name=name,
            dataset_id=dataset_id,
            chart_type=current.get('chart_type', 'line'),
            x_column=current.get('x_column'),
            group_columns=tuple(current.get('group_columns', [])),
            value_columns=tuple(current.get('value_columns', [])),
            hover_columns=tuple(current.get('hover_columns', [])),
            chart_settings=current.get('chart_settings', {}),
            filters=tuple(current.get('filters', [])),
            sorts=tuple(current.get('sorts', [])),
        )
        return gs

    def _sync_from_dataset_state(self, dataset_id: str):
        """
        데이터셋 상태를 기존 AppState 속성들로 동기화

        단일 모드에서 활성 데이터셋 전환 시 호출됨
        """
        import copy
        state = self.comparison_manager.dataset_states.get(dataset_id)
        if not state:
            return

        # 기존 속성들 업데이트 (하위 호환성) - 깊은 복사 사용
        self._x_column = state.x_column
        self._group_columns = copy.deepcopy(state.group_columns)
        self._value_columns = copy.deepcopy(state.value_columns)
        self._hover_columns = copy.deepcopy(state.hover_columns)
        self._filters = copy.deepcopy(state.filters)
        self._sorts = copy.deepcopy(state.sorts)
        # Selection은 참조 유지 (양방향 동기화 필요)
        self._selection = state.selection
        self._chart_settings = copy.deepcopy(state.chart_settings)

        # 시그널 발생
        self.group_zone_changed.emit()
        self.value_zone_changed.emit()
        self.hover_zone_changed.emit()
        self.chart_settings_changed.emit()
        self.filter_changed.emit()
        self.sort_changed.emit()

    def _sync_to_dataset_state(self, dataset_id: str = None):
        """
        기존 AppState 속성들을 데이터셋 상태로 동기화

        단일 모드에서 상태 변경 시 호출됨
        """
        import copy
        target_id = dataset_id or self.comparison_manager.active_dataset_id
        dataset_states = self.comparison_manager.dataset_states
        if not target_id or target_id not in dataset_states:
            return

        state = dataset_states[target_id]
        state.x_column = self._x_column
        state.group_columns = copy.deepcopy(self._group_columns)
        state.value_columns = copy.deepcopy(self._value_columns)
        state.hover_columns = copy.deepcopy(self._hover_columns)
        state.filters = copy.deepcopy(self._filters)
        state.sorts = copy.deepcopy(self._sorts)
        # Selection은 참조 유지 (양방향 동기화 필요)
        state.selection = self._selection
        state.chart_settings = copy.deepcopy(self._chart_settings)

    # ==================== Data ====================

    @property
    def is_data_loaded(self) -> bool:
        """True if a dataset has been loaded into the application."""
        return self._data_loaded

    def set_data_loaded(self, loaded: bool, total_rows: int = 0):
        """
        Update the data-loaded state and row count.

        Sets _data_loaded and _total_rows/_visible_rows, then emits
        data_loaded if loaded is True, or data_cleared otherwise.

        Args:
            loaded: True when data has been loaded, False when cleared.
            total_rows: Total number of rows in the loaded dataset.

        Emits:
            data_loaded signal when loaded is True.
            data_cleared signal when loaded is False.
        """
        self._data_loaded = loaded
        self._total_rows = total_rows
        self._visible_rows = total_rows
        if loaded:
            self.data_loaded.emit()
        else:
            self.data_cleared.emit()

    @property
    def total_rows(self) -> int:
        """Total number of rows in the loaded dataset, unaffected by filters."""
        return self._total_rows

    @property
    def visible_rows(self) -> int:
        """Number of rows currently visible after applying active filters."""
        return self._visible_rows

    def set_visible_rows(self, count: int):
        """
        Update the visible row count after filter application.

        Args:
            count: Number of rows remaining after filters are applied.
        """
        self._visible_rows = count

    # ==================== Group Zone ====================

    @property
    def group_columns(self) -> List[GroupColumn]:
        """Ordered list of columns currently in the Group Zone."""
        return self._group_columns

    def add_group_column(self, name: str, index: int = -1):
        """
        Add a column to the Group Zone, ignoring duplicates.

        Args:
            name: Column name to add.
            index: Position to insert at. -1 appends to the end.

        Emits:
            group_zone_changed signal.
        """
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
        """
        Remove a column from the Group Zone by name.

        Args:
            name: Column name to remove. No-op if not present.

        Emits:
            group_zone_changed signal.
        """
        self._group_columns = [g for g in self._group_columns if g.name != name]
        self._reorder_groups()
        self.group_zone_changed.emit()

    def reorder_group_columns(self, new_order: List[str]):
        """
        Reorder Group Zone columns to match the given name sequence.

        Args:
            new_order: Column names in the desired order. Names not present in
                the current group columns are silently ignored.

        Emits:
            group_zone_changed signal.
        """
        name_to_col = {g.name: g for g in self._group_columns}
        self._group_columns = [name_to_col[name] for name in new_order if name in name_to_col]
        self._reorder_groups()
        self.group_zone_changed.emit()

    def _reorder_groups(self):
        for i, g in enumerate(self._group_columns):
            g.order = i

    def clear_group_zone(self):
        """
        Remove all columns from the Group Zone.

        Emits:
            group_zone_changed signal.
        """
        self._group_columns.clear()
        self.group_zone_changed.emit()

    # ==================== Value Zone ====================

    @property
    def value_columns(self) -> List[ValueColumn]:
        """Ordered list of columns currently in the Value Zone."""
        return self._value_columns

    def add_value_column(
        self,
        name: str,
        aggregation: AggregationType = AggregationType.SUM,
        index: int = -1
    ):
        """
        Add a column to the Value Zone with automatic color assignment.

        Duplicate column names are allowed when combined with different aggregations.

        Args:
            name: Column name to add.
            aggregation: Aggregation function to apply. Defaults to SUM.
            index: Position to insert at. -1 appends to the end.

        Emits:
            value_zone_changed signal.
        """
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
        """
        Remove a Value Zone column by list index.

        Args:
            index: Zero-based index of the column to remove. No-op if out of range.

        Emits:
            value_zone_changed signal.
        """
        if 0 <= index < len(self._value_columns):
            self._value_columns.pop(index)
            self._reorder_values()
            self.value_zone_changed.emit()

    def update_value_column(
        self,
        index: int,
        aggregation: Optional[AggregationType] = None,
        color: Optional[str] = None,
        use_secondary_axis: Optional[bool] = None,
        formula: Optional[str] = None
    ):
        """
        Update properties of an existing Value Zone column.

        Only non-None arguments are applied. No-op if the index is out of range.

        Args:
            index: Zero-based index of the column to update.
            aggregation: New aggregation function, or None to leave unchanged.
            color: New hex color string, or None to leave unchanged.
            use_secondary_axis: Assign to secondary Y axis if True, or None to leave unchanged.
            formula: Y-value formula expression (e.g. "y*2"), or None to leave unchanged.

        Emits:
            value_zone_changed signal if any property was updated.
        """
        if 0 <= index < len(self._value_columns):
            if aggregation is not None:
                self._value_columns[index].aggregation = aggregation
            if color is not None:
                self._value_columns[index].color = color
            if use_secondary_axis is not None:
                self._value_columns[index].use_secondary_axis = use_secondary_axis
            if formula is not None:
                self._value_columns[index].formula = formula
            self.value_zone_changed.emit()

    def _reorder_values(self):
        for i, v in enumerate(self._value_columns):
            v.order = i

    def clear_value_zone(self):
        """
        Remove all columns from the Value Zone.

        Emits:
            value_zone_changed signal.
        """
        self._value_columns.clear()
        self.value_zone_changed.emit()

    def remove_value_column_by_name(self, name: str):
        """Remove value column by name."""
        self._value_columns = [v for v in self._value_columns if v.name != name]
        self._reorder_values()
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

    # ==================== Hover Zone ====================

    @property
    def hover_columns(self) -> List[str]:
        """Ordered list of column names shown in the chart hover tooltip."""
        return self._hover_columns

    def add_hover_column(self, name: str):
        """Add column to hover display"""
        if name not in self._hover_columns:
            self._hover_columns.append(name)
            self.hover_zone_changed.emit()

    def remove_hover_column(self, name: str):
        """Remove column from hover display"""
        if name in self._hover_columns:
            self._hover_columns.remove(name)
            self.hover_zone_changed.emit()

    def clear_hover_columns(self):
        """Clear all hover columns"""
        self._hover_columns.clear()
        self.hover_zone_changed.emit()

    # ==================== X Column ====================

    @property
    def x_column(self) -> Optional[str]:
        """Column name used as the X axis, or None if not set."""
        return self._x_column

    def set_x_column(self, name: Optional[str]):
        """
        Set the X axis column.

        Args:
            name: Column name to use for the X axis, or None to clear.

        Emits:
            chart_settings_changed signal.
        """
        self._x_column = name
        self.chart_settings_changed.emit()

    # ==================== Filters ====================

    @property
    def filters(self) -> List[FilterCondition]:
        """List of active filter conditions applied to the dataset."""
        return self._filters

    def add_filter(self, column: str, operator: str, value: Any):
        """
        Append a new filter condition and record an undo entry.

        Args:
            column: Column name to filter on.
            operator: Comparison operator (e.g. "eq", "ne", "gt", "lt", "contains").
            value: Value to compare against.

        Emits:
            filter_changed signal.
        """
        before = copy.deepcopy(self._filters)
        self._filters.append(FilterCondition(column, operator, value))
        self.filter_changed.emit()
        after = copy.deepcopy(self._filters)

        def _apply(value_filters):
            self._undo_paused += 1
            try:
                self._filters = copy.deepcopy(value_filters)
                self.filter_changed.emit()
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.FILTER_CHANGE,
                description=f"Filter: + {column} {operator} {value}",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    def remove_filter(self, index: int):
        """
        Remove a filter condition by index and record an undo entry.

        Args:
            index: Zero-based index of the filter to remove. No-op if out of range.

        Emits:
            filter_changed signal.
        """
        if not (0 <= index < len(self._filters)):
            return
        before = copy.deepcopy(self._filters)
        removed = self._filters[index]
        self._filters.pop(index)
        self.filter_changed.emit()
        after = copy.deepcopy(self._filters)

        def _apply(value_filters):
            self._undo_paused += 1
            try:
                self._filters = copy.deepcopy(value_filters)
                self.filter_changed.emit()
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.FILTER_CHANGE,
                description=f"Filter: - {removed.column}",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    def clear_filters(self):
        """
        Remove all filter conditions and record an undo entry.

        No-op if there are no active filters.

        Emits:
            filter_changed signal.
        """
        if not self._filters:
            return
        before = copy.deepcopy(self._filters)
        self._filters.clear()
        self.filter_changed.emit()
        after = copy.deepcopy(self._filters)

        def _apply(value_filters):
            self._undo_paused += 1
            try:
                self._filters = copy.deepcopy(value_filters)
                self.filter_changed.emit()
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.FILTER_CHANGE,
                description="Filter: Clear",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    def toggle_filter(self, index: int):
        """
        Toggle the enabled state of a filter condition and record an undo entry.

        Args:
            index: Zero-based index of the filter to toggle. No-op if out of range.

        Emits:
            filter_changed signal.
        """
        if not (0 <= index < len(self._filters)):
            return
        before = copy.deepcopy(self._filters)
        self._filters[index].enabled = not self._filters[index].enabled
        self.filter_changed.emit()
        after = copy.deepcopy(self._filters)

        def _apply(value_filters):
            self._undo_paused += 1
            try:
                self._filters = copy.deepcopy(value_filters)
                self.filter_changed.emit()
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.FILTER_CHANGE,
                description=f"Filter: Toggle {self._filters[index].column}",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    # ==================== Sorts ====================

    @property
    def sorts(self) -> List[SortCondition]:
        """List of active sort conditions applied to the dataset."""
        return self._sorts

    def set_sort(self, column: str, descending: bool = False, add: bool = False):
        """
        Set a sort condition on a column and record an undo entry.

        Any existing sort on the same column is removed before adding the new one.

        Args:
            column: Column name to sort by.
            descending: Sort in descending order if True, ascending if False.
            add: If True, add to existing sorts. If False, replace all sorts.

        Emits:
            sort_changed signal.
        """
        before = copy.deepcopy(self._sorts)

        if not add:
            self._sorts.clear()

        # 기존 정렬 제거
        self._sorts = [s for s in self._sorts if s.column != column]
        self._sorts.append(SortCondition(column, descending))
        self.sort_changed.emit()

        after = copy.deepcopy(self._sorts)
        if before != after:
            def _apply(value):
                self._undo_paused += 1
                try:
                    self._sorts = copy.deepcopy(value)
                    self.sort_changed.emit()
                finally:
                    self._undo_paused = max(0, self._undo_paused - 1)

            self._push_undo(
                UndoCommand(
                    action_type=UndoActionType.SORT_CHANGE,
                    description=f"Sort: {column} ({'DESC' if descending else 'ASC'})",
                    do=lambda: _apply(after),
                    undo=lambda: _apply(before),
                    timestamp=time.time(),
                )
            )

    def clear_sorts(self):
        """
        Remove all sort conditions and record an undo entry.

        No-op if there are no active sorts.

        Emits:
            sort_changed signal.
        """
        before = copy.deepcopy(self._sorts)
        if not self._sorts:
            return
        self._sorts.clear()
        self.sort_changed.emit()

        after = copy.deepcopy(self._sorts)

        def _apply(value):
            self._undo_paused += 1
            try:
                self._sorts = copy.deepcopy(value)
                self.sort_changed.emit()
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.SORT_CHANGE,
                description="Sort: Clear",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    # ==================== Selection ====================

    @property
    def selection(self) -> SelectionState:
        """Current row selection state."""
        return self._selection

    def select_rows(self, rows: List[int], add: bool = False):
        """
        Select the given rows, optionally adding to the existing selection.

        Args:
            rows: Row indices to select.
            add: If True, add to existing selection. If False, replace it.

        Emits:
            selection_changed signal.
        """
        self._selection.select(rows, add)
        self.selection_changed.emit()

    def deselect_rows(self, rows: List[int]):
        """
        Remove the given rows from the selection.

        Args:
            rows: Row indices to deselect.

        Emits:
            selection_changed signal.
        """
        self._selection.deselect(rows)
        self.selection_changed.emit()

    def toggle_row(self, row: int):
        """
        Toggle the selection state of a single row.

        Args:
            row: Row index to toggle.

        Emits:
            selection_changed signal.
        """
        self._selection.toggle(row)
        self.selection_changed.emit()

    def clear_selection(self):
        """
        Clear all selected and highlighted rows.

        Emits:
            selection_changed signal.
        """
        self._selection.clear()
        self.selection_changed.emit()

    def select_all(self):
        """
        Select all visible rows.

        Emits:
            selection_changed signal.
        """
        self._selection.select(list(range(self._visible_rows)))
        self.selection_changed.emit()

    # ==================== Limit to Marking ====================

    @property
    def limit_to_marking(self) -> bool:
        """When True, table shows only marked/selected rows"""
        return self._limit_to_marking

    def set_limit_to_marking(self, enabled: bool):
        """Toggle limit to marking mode"""
        if self._limit_to_marking != enabled:
            self._limit_to_marking = enabled
            self.limit_to_marking_changed.emit(enabled)

    # ==================== Chart Settings ====================

    @property
    def chart_settings(self) -> ChartSettings:
        """Current chart configuration including type, axes, and style options."""
        return self._chart_settings

    def set_chart_type(self, chart_type: ChartType):
        """
        Change the active chart type and record an undo entry.

        Args:
            chart_type: ChartType enum value to apply.

        Emits:
            chart_settings_changed signal.
        """
        before = copy.deepcopy(self._chart_settings)
        self._chart_settings.chart_type = chart_type
        self.chart_settings_changed.emit()
        after = copy.deepcopy(self._chart_settings)

        def _apply(settings: ChartSettings):
            self._undo_paused += 1
            try:
                self._chart_settings = copy.deepcopy(settings)
                self.chart_settings_changed.emit()
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        if before != after:
            self._push_undo(
                UndoCommand(
                    action_type=UndoActionType.CHART_SETTINGS,
                    description=f"Chart: Type → {chart_type.value}",
                    do=lambda: _apply(after),
                    undo=lambda: _apply(before),
                    timestamp=time.time(),
                )
            )

    def update_chart_settings(self, **kwargs):
        """
        Update one or more chart settings fields and record an undo entry.

        Only fields that exist on ChartSettings and whose values differ from the
        current state are applied. No-op if nothing changed.

        Args:
            **kwargs: ChartSettings attribute names and their new values
                (e.g. line_width=3, y_log_scale=True).

        Emits:
            chart_settings_changed signal if any field changed.
        """
        before = copy.deepcopy(self._chart_settings)
        changed = False
        for key, value in kwargs.items():
            if hasattr(self._chart_settings, key):
                if getattr(self._chart_settings, key) != value:
                    setattr(self._chart_settings, key, value)
                    changed = True
        if not changed:
            return
        self.chart_settings_changed.emit()
        after = copy.deepcopy(self._chart_settings)

        def _apply(settings: ChartSettings):
            self._undo_paused += 1
            try:
                self._chart_settings = copy.deepcopy(settings)
                self.chart_settings_changed.emit()
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        keys = ", ".join(sorted(kwargs.keys()))
        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.CHART_SETTINGS,
                description=f"Chart: Update ({keys})",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    # ==================== Tool Mode ====================

    @property
    def tool_mode(self) -> ToolMode:
        """Currently active chart interaction tool mode."""
        return self._tool_mode

    def set_tool_mode(self, mode: ToolMode):
        """
        Set the active chart tool mode.

        Args:
            mode: ToolMode enum value to activate.

        Emits:
            tool_mode_changed signal.
        """
        self._tool_mode = mode
        self.tool_mode_changed.emit()

    # ==================== Grid View ====================

    @property
    def grid_view_settings(self) -> GridViewSettings:
        """Grid View 설정"""
        return self._chart_settings.grid_view

    def set_grid_view_enabled(self, enabled: bool):
        """Grid View 활성화/비활성화"""
        if self._chart_settings.grid_view.enabled != enabled:
            self._chart_settings.grid_view.enabled = enabled
            self.grid_view_changed.emit()

    def set_grid_view_split_by(self, column: Optional[str]):
        """Grid View 분할 기준 열 설정"""
        if self._chart_settings.grid_view.split_by != column:
            self._chart_settings.grid_view.split_by = column
            self.grid_view_changed.emit()

    def set_grid_view_direction(self, direction: GridDirection):
        """Grid View 방향 설정"""
        if self._chart_settings.grid_view.direction != direction:
            self._chart_settings.grid_view.direction = direction
            self.grid_view_changed.emit()

    def update_grid_view_settings(self, **kwargs):
        """Grid View 설정 업데이트"""
        changed = False
        for key, value in kwargs.items():
            if hasattr(self._chart_settings.grid_view, key):
                current = getattr(self._chart_settings.grid_view, key)
                if current != value:
                    setattr(self._chart_settings.grid_view, key, value)
                    changed = True
        if changed:
            self.grid_view_changed.emit()

    # ==================== Layout ====================

    @property
    def layout_ratios(self) -> Dict[str, float]:
        """Height ratios for 'summary', 'graph', and 'table' panels (sum to 1.0)."""
        return self._layout_ratios

    def set_layout_ratio(self, section: str, ratio: float):
        """
        Set the height ratio for a layout section, redistributing the remainder.

        The difference between the old and new ratio is spread evenly across all
        other sections to keep the total at 1.0.

        Args:
            section: Layout section key — one of 'summary', 'graph', or 'table'.
            ratio: New ratio for the section. Ignored if the section key is unknown.
        """
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
        """
        Set the display order of table columns.

        Args:
            order: Full list of column names in the desired display order.
        """
        self._column_order = order

    def get_column_order(self) -> List[str]:
        """
        Return the current column display order.

        Returns:
            List of column names in display order.
        """
        return self._column_order

    @property
    def hidden_columns(self) -> Set[str]:
        """Read-only access to hidden columns set."""
        return frozenset(self._hidden_columns)

    def hide_column(self, column: str):
        """Hide a specific column."""
        self._hidden_columns.add(column)

    def unhide_column(self, column: str):
        """Unhide a specific column."""
        self._hidden_columns.discard(column)

    def is_column_hidden(self, column: str) -> bool:
        """Check if a column is hidden."""
        return column in self._hidden_columns

    def toggle_column_visibility(self, column: str):
        """
        Toggle whether a column is hidden in the table view.

        Args:
            column: Column name to show if hidden, or hide if visible.
        """
        if column in self._hidden_columns:
            self._hidden_columns.remove(column)
        else:
            self._hidden_columns.add(column)

    def get_visible_columns(self) -> List[str]:
        """
        Return the ordered list of columns that are not hidden.

        Returns:
            Column names from _column_order that are not in _hidden_columns.
        """
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
        self._hover_columns.clear()
        self._x_column = None
        self._filters.clear()
        self._sorts.clear()
        self._selection.clear()
        self._chart_settings = ChartSettings()
        self._tool_mode = ToolMode.PAN
        self._column_order.clear()
        self._hidden_columns.clear()

        self.data_cleared.emit()

    # ==================== Profile ====================

    @property
    def current_profile(self) -> Optional['Profile']:
        """현재 프로파일"""
        return self._current_profile

    @property
    def current_setting_id(self) -> Optional[str]:
        """현재 활성 설정 ID"""
        return self._current_setting_id

    @property
    def current_setting(self) -> Optional['GraphSetting']:
        """현재 활성 설정"""
        if self._current_profile and self._current_setting_id:
            return self._current_profile.get_setting(self._current_setting_id)
        return None

    @property
    def floating_windows(self) -> Dict[str, Any]:
        """플로팅 윈도우 목록"""
        return self._floating_windows

    def set_profile(self, profile: Optional['Profile']):
        """프로파일 설정"""
        self._current_profile = profile
        self._current_setting_id = None
        if profile:
            # 기본 설정이 있으면 활성화
            if profile.default_setting_id:
                self._current_setting_id = profile.default_setting_id
            elif profile.settings:
                self._current_setting_id = profile.settings[0].id
            self.profile_loaded.emit(profile)
        else:
            self.profile_cleared.emit()

    def activate_setting(self, setting_id: str):
        """설정 활성화"""
        if self._current_profile:
            setting = self._current_profile.get_setting(setting_id)
            if setting:
                self._current_setting_id = setting_id
                self.setting_activated.emit(setting_id)

    def add_setting(self, setting: 'GraphSetting'):
        """현재 프로파일에 설정 추가"""
        if self._current_profile:
            self._current_profile.add_setting(setting)
            self.setting_added.emit(setting.id)

    def remove_setting(self, setting_id: str):
        """현재 프로파일에서 설정 제거"""
        if self._current_profile:
            if self._current_profile.remove_setting(setting_id):
                if self._current_setting_id == setting_id:
                    # 다른 설정으로 전환
                    if self._current_profile.settings:
                        self._current_setting_id = self._current_profile.settings[0].id
                    else:
                        self._current_setting_id = None
                self.setting_removed.emit(setting_id)

    def register_floating_window(self, window_id: str, window: Any):
        """플로팅 윈도우 등록"""
        self._floating_windows[window_id] = window
        self.floating_window_opened.emit(window_id)

    def unregister_floating_window(self, window_id: str):
        """플로팅 윈도우 해제"""
        if window_id in self._floating_windows:
            del self._floating_windows[window_id]
            self.floating_window_closed.emit(window_id)

    def get_current_graph_state(self) -> Dict[str, Any]:
        """현재 그래프 상태를 딕셔너리로 반환 (설정 저장용)"""
        return {
            'chart_type': self._chart_settings.chart_type.value,
            'x_column': self._x_column,
            'group_columns': [
                {
                    'name': gc.name,
                    'selected_values': list(gc.selected_values),
                    'order': gc.order
                }
                for gc in self._group_columns
            ],
            'value_columns': [
                {
                    'name': vc.name,
                    'aggregation': vc.aggregation.value,
                    'color': vc.color,
                    'use_secondary_axis': vc.use_secondary_axis,
                    'order': vc.order,
                    'formula': vc.formula
                }
                for vc in self._value_columns
            ],
            'hover_columns': self._hover_columns.copy(),
            'chart_settings': {
                'line_width': self._chart_settings.line_width,
                'marker_size': self._chart_settings.marker_size,
                'fill_opacity': self._chart_settings.fill_opacity,
                'show_data_labels': self._chart_settings.show_data_labels,
                'x_log_scale': self._chart_settings.x_log_scale,
                'y_log_scale': self._chart_settings.y_log_scale,
                'y_min': self._chart_settings.y_min,
                'y_max': self._chart_settings.y_max,
                'y_label': self._chart_settings.y_label,
                'secondary_y_log_scale': self._chart_settings.secondary_y_log_scale,
                'secondary_y_min': self._chart_settings.secondary_y_min,
                'secondary_y_max': self._chart_settings.secondary_y_max,
                'secondary_y_label': self._chart_settings.secondary_y_label,
            },
            'filters': [
                {
                    'column': f.column,
                    'operator': f.operator,
                    'value': f.value,
                    'enabled': f.enabled
                }
                for f in self._filters
            ],
            'sorts': [
                {
                    'column': s.column,
                    'descending': s.descending
                }
                for s in self._sorts
            ],
        }

    def apply_graph_setting(self, setting: 'GraphSetting'):
        """GraphSetting을 현재 상태에 적용"""

        # 차트 타입
        try:
            self._chart_settings.chart_type = ChartType(setting.chart_type)
        except ValueError:
            pass

        # X축 컬럼
        self._x_column = setting.x_column

        # Group Zone 복원
        self._group_columns.clear()
        for gc_data in setting.group_columns:
            gc = GroupColumn(
                name=gc_data.get('name', ''),
                selected_values=set(gc_data.get('selected_values', [])),
                order=gc_data.get('order', 0)
            )
            self._group_columns.append(gc)

        # Value Zone 복원
        self._value_columns.clear()
        for vc_data in setting.value_columns:
            try:
                agg = AggregationType(vc_data.get('aggregation', 'sum'))
            except ValueError:
                agg = AggregationType.SUM
            vc = ValueColumn(
                name=vc_data.get('name', ''),
                aggregation=agg,
                color=vc_data.get('color', '#1f77b4'),
                use_secondary_axis=vc_data.get('use_secondary_axis', False),
                order=vc_data.get('order', 0),
                formula=vc_data.get('formula', '')
            )
            self._value_columns.append(vc)

        # Hover Zone 복원
        self._hover_columns = list(setting.hover_columns)

        # 차트 설정 복원
        cs = setting.chart_settings
        if cs:
            self._chart_settings.line_width = cs.get('line_width', 2)
            self._chart_settings.marker_size = cs.get('marker_size', 6)
            self._chart_settings.fill_opacity = cs.get('fill_opacity', 0.3)
            self._chart_settings.show_data_labels = cs.get('show_data_labels', False)
            self._chart_settings.x_log_scale = cs.get('x_log_scale', False)
            self._chart_settings.y_log_scale = cs.get('y_log_scale', False)
            self._chart_settings.y_min = cs.get('y_min')
            self._chart_settings.y_max = cs.get('y_max')
            self._chart_settings.y_label = cs.get('y_label')
            self._chart_settings.secondary_y_log_scale = cs.get('secondary_y_log_scale', False)
            self._chart_settings.secondary_y_min = cs.get('secondary_y_min')
            self._chart_settings.secondary_y_max = cs.get('secondary_y_max')
            self._chart_settings.secondary_y_label = cs.get('secondary_y_label')

        # 필터 복원 (include_filters가 True인 경우만)
        if setting.include_filters:
            self._filters.clear()
            for f_data in setting.filters:
                f = FilterCondition(
                    column=f_data.get('column', ''),
                    operator=f_data.get('operator', 'eq'),
                    value=f_data.get('value'),
                    enabled=f_data.get('enabled', True)
                )
                self._filters.append(f)

        # 정렬 복원 (include_sorts가 True인 경우만)
        if setting.include_sorts:
            self._sorts.clear()
            for s_data in setting.sorts:
                s = SortCondition(
                    column=s_data.get('column', ''),
                    descending=s_data.get('descending', False)
                )
                self._sorts.append(s)

        # 시그널 발생
        self.group_zone_changed.emit()
        self.value_zone_changed.emit()
        self.hover_zone_changed.emit()
        self.chart_settings_changed.emit()
        if setting.include_filters:
            self.filter_changed.emit()
        if setting.include_sorts:
            self.sort_changed.emit()
