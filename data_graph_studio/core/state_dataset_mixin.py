"""
DatasetMixin - Dataset management methods extracted from AppState.

All methods operate on shared instance state (self.*) and can call
self.emit(...) because AppState also inherits from Observable.
"""

from typing import Optional, List, Dict, Any, TYPE_CHECKING
import copy
import uuid

from .comparison_manager import (
    ComparisonMode,
    ComparisonSettings,
    DatasetMetadata,
    DatasetState,
)

if TYPE_CHECKING:
    from .profile import Profile, GraphSetting

from .state_types import (
    AggregationType,
    ChartType,
    GroupColumn,
    ValueColumn,
    FilterCondition,
    SortCondition,
    ChartSettings,
)
from .undo_manager import UndoStack, UndoCommand


class DatasetMixin:
    """Mixin providing dataset management capabilities to AppState."""

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
                    self.emit(sig_name)
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
        self.emit("group_zone_changed")
        self.emit("value_zone_changed")
        self.emit("hover_zone_changed")
        self.emit("chart_settings_changed")
        self.emit("filter_changed")
        self.emit("sort_changed")

    def _sync_to_dataset_state(self, dataset_id: str = None):
        """
        기존 AppState 속성들을 데이터셋 상태로 동기화

        단일 모드에서 상태 변경 시 호출됨
        """
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
            self.emit("data_loaded")
        else:
            self.emit("data_cleared")

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

