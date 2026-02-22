"""
State Management - 앱 상태 관리

멀티 데이터셋 비교 기능 지원
"""

from typing import Optional, List, Dict, Any, Set, TYPE_CHECKING
import copy
from .observable import Observable

from .undo_manager import UndoStack
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

# 차이 모드 색상 (비교 색상 팔레트는 comparison_manager.py 참조)
from data_graph_studio.core.constants import (
    DIFF_POSITIVE_COLOR,
    DIFF_NEGATIVE_COLOR,
    DIFF_NEUTRAL_COLOR,
)

# Value objects and enums live in state_types.py.
# Re-exported here so all existing imports remain valid:
#   from data_graph_studio.core.state import ChartType  (still works)
from .state_types import (
    ThemeState,
    AggregationType,
    ChartType,
    ToolMode,
    GroupColumn,
    ValueColumn,
    FilterCondition,
    SortCondition,
    GridDirection,
    GridViewSettings,
    ChartSettings,
    SelectionState,
)

# Mixin classes
from .state_dataset_mixin import DatasetMixin
from .state_column_mixin import ColumnZoneMixin
from .state_filter_mixin import FilterSortMixin
from .state_view_mixin import ViewSettingsMixin


class AppState(DatasetMixin, ColumnZoneMixin, FilterSortMixin, ViewSettingsMixin, Observable):
    """
    앱 전역 상태 관리

    Observable events로 상태 변경을 알림
    """

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

        # Forward ComparisonManager events through AppState's own Observable events so
        # all existing external listeners (subscribed to AppState) still work.
        self.comparison_manager.subscribe("dataset_added", lambda *a: self.emit("dataset_added", *a))
        self.comparison_manager.subscribe("dataset_removed", lambda *a: self.emit("dataset_removed", *a))
        self.comparison_manager.subscribe("dataset_activated", lambda *a: self.emit("dataset_activated", *a))
        self.comparison_manager.subscribe("dataset_updated", lambda *a: self.emit("dataset_updated", *a))
        self.comparison_manager.subscribe("comparison_mode_changed", lambda *a: self.emit("comparison_mode_changed", *a))
        self.comparison_manager.subscribe("comparison_settings_changed", lambda *a: self.emit("comparison_settings_changed", *a))

        # Sync AppState legacy props when active dataset changes in SINGLE mode
        self.comparison_manager.subscribe("dataset_activated", self._on_dataset_activated)

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
        self.emit("selection_changed")

    def deselect_rows(self, rows: List[int]):
        """
        Remove the given rows from the selection.

        Args:
            rows: Row indices to deselect.

        Emits:
            selection_changed signal.
        """
        self._selection.deselect(rows)
        self.emit("selection_changed")

    def toggle_row(self, row: int):
        """
        Toggle the selection state of a single row.

        Args:
            row: Row index to toggle.

        Emits:
            selection_changed signal.
        """
        self._selection.toggle(row)
        self.emit("selection_changed")

    def clear_selection(self):
        """
        Clear all selected and highlighted rows.

        Emits:
            selection_changed signal.
        """
        self._selection.clear()
        self.emit("selection_changed")

    def select_all(self):
        """
        Select all visible rows.

        Emits:
            selection_changed signal.
        """
        self._selection.select(list(range(self._visible_rows)))
        self.emit("selection_changed")

    # ==================== Limit to Marking ====================

    @property
    def limit_to_marking(self) -> bool:
        """When True, table shows only marked/selected rows"""
        return self._limit_to_marking

    def set_limit_to_marking(self, enabled: bool):
        """Toggle limit to marking mode"""
        if self._limit_to_marking != enabled:
            self._limit_to_marking = enabled
            self.emit("limit_to_marking_changed", enabled)

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

        self.emit("data_cleared")

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
            self.emit("profile_loaded", profile)
        else:
            self.emit("profile_cleared")

    def activate_setting(self, setting_id: str):
        """설정 활성화"""
        if self._current_profile:
            setting = self._current_profile.get_setting(setting_id)
            if setting:
                self._current_setting_id = setting_id
                self.emit("setting_activated", setting_id)

    def add_setting(self, setting: 'GraphSetting'):
        """현재 프로파일에 설정 추가"""
        if self._current_profile:
            self._current_profile.add_setting(setting)
            self.emit("setting_added", setting.id)

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
                self.emit("setting_removed", setting_id)

    def register_floating_window(self, window_id: str, window: Any):
        """플로팅 윈도우 등록"""
        self._floating_windows[window_id] = window
        self.emit("floating_window_opened", window_id)

    def unregister_floating_window(self, window_id: str):
        """플로팅 윈도우 해제"""
        if window_id in self._floating_windows:
            del self._floating_windows[window_id]
            self.emit("floating_window_closed", window_id)

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
        self.emit("group_zone_changed")
        self.emit("value_zone_changed")
        self.emit("hover_zone_changed")
        self.emit("chart_settings_changed")
        if setting.include_filters:
            self.emit("filter_changed")
        if setting.include_sorts:
            self.emit("sort_changed")

