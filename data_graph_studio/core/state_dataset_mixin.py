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
        """Attach an undo stack for recording undoable state mutations.

        Input: stack — UndoStack or None; pass None to disable undo recording.
        Output: None
        Invariants: self._undo_stack is set to the provided value.
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
        """Increment the batch depth, suppressing signal emission until the batch ends.

        Output: None
        Invariants: self._batch_depth >= 1 after this call; signals are deferred.
        """
        self._batch_depth += 1

    def end_batch_update(self):
        """Decrement the batch depth and flush any deferred signals when depth reaches zero.

        Output: None — each deferred signal is emitted at most once.
        Invariants: self._batch_depth >= 0; self._batch_pending_signals is empty when depth == 0.
        """
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
        """Mapping of dataset ID to DatasetState for all loaded datasets."""
        return self.comparison_manager.dataset_states

    @property
    def dataset_metadata(self) -> Dict[str, DatasetMetadata]:
        """Mapping of dataset ID to DatasetMetadata for all loaded datasets."""
        return self.comparison_manager.dataset_metadata

    @property
    def active_dataset_id(self) -> Optional[str]:
        """ID of the currently active dataset, or None if no dataset is active."""
        return self.comparison_manager.active_dataset_id

    @property
    def active_dataset_state(self) -> Optional[DatasetState]:
        """DatasetState of the currently active dataset, or None if none is active."""
        return self.comparison_manager.active_dataset_state

    @property
    def comparison_settings(self) -> ComparisonSettings:
        """Current comparison mode configuration."""
        return self.comparison_manager.comparison_settings

    @property
    def comparison_mode(self) -> ComparisonMode:
        """Active comparison mode (SINGLE or MULTI)."""
        return self.comparison_manager.comparison_mode

    @property
    def dataset_count(self) -> int:
        """Number of datasets currently loaded."""
        return self.comparison_manager.dataset_count

    @property
    def comparison_dataset_ids(self) -> List[str]:
        """Ordered list of dataset IDs selected for multi-dataset comparison."""
        return self.comparison_manager.comparison_dataset_ids

    @property
    def is_profile_comparison_active(self) -> bool:
        """True if profile comparison mode is currently active."""
        return self.comparison_manager.is_profile_comparison_active

    # --- Dataset CRUD ---

    def get_dataset_state(self, dataset_id: str) -> Optional[DatasetState]:
        """Return the DatasetState for a given dataset ID, or None if not found.

        Input: dataset_id — str, must be an existing dataset ID.
        Output: DatasetState or None.
        """
        return self.comparison_manager.get_dataset_state(dataset_id)

    def get_dataset_metadata(self, dataset_id: str) -> Optional[DatasetMetadata]:
        """Return the DatasetMetadata for a given dataset ID, or None if not found.

        Input: dataset_id — str, must be an existing dataset ID.
        Output: DatasetMetadata or None.
        """
        return self.comparison_manager.get_dataset_metadata(dataset_id)

    def add_dataset(self, dataset_id: str, name: str = "", file_path: str = None,
                    row_count: int = 0, column_count: int = 0, memory_bytes: int = 0) -> DatasetState:
        """Register a new dataset and return its DatasetState.

        Input: dataset_id — str, unique identifier for the dataset.
               name — str, human-readable label (default "").
               file_path — str or None, source file path.
               row_count, column_count, memory_bytes — int, size metadata.
        Output: DatasetState — the newly created state object.
        Invariants: dataset_id is present in self.dataset_states after this call.
        """
        return self.comparison_manager.add_dataset(
            dataset_id, name=name, file_path=file_path,
            row_count=row_count, column_count=column_count, memory_bytes=memory_bytes,
        )

    def remove_dataset(self, dataset_id: str) -> bool:
        """Remove a dataset from the application state.

        Input: dataset_id — str, ID of the dataset to remove.
        Output: bool — True if the dataset was found and removed, False otherwise.
        Invariants: dataset_id is absent from self.dataset_states after a successful removal.
        """
        return self.comparison_manager.remove_dataset(dataset_id)

    def activate_dataset(self, dataset_id: str) -> bool:
        """Set a dataset as the active one and trigger state synchronisation.

        In SINGLE mode, activating a dataset syncs its persisted state back into
        the legacy AppState properties via _on_dataset_activated.

        Input: dataset_id — str, ID of an existing dataset.
        Output: bool — True if activation succeeded, False if dataset not found.
        Invariants: self.active_dataset_id == dataset_id on success.
        """
        return self.comparison_manager.activate_dataset(dataset_id)

    def _on_dataset_activated(self, dataset_id: str):
        """ComparisonManager.dataset_activated 신호 수신 → SINGLE 모드 동기화."""
        if self.comparison_manager.comparison_mode == ComparisonMode.SINGLE:
            self._sync_from_dataset_state(dataset_id)

    def update_dataset_metadata(self, dataset_id: str, **kwargs):
        """Update metadata fields of an existing dataset.

        Input: dataset_id — str, ID of the target dataset.
               **kwargs — DatasetMetadata field names and their new values.
        Output: None
        """
        self.comparison_manager.update_dataset_metadata(dataset_id, **kwargs)

    def clear_all_datasets(self):
        """Remove all datasets from the application state.

        Output: None
        Invariants: self.dataset_states is empty after this call.
        """
        self.comparison_manager.clear_all_datasets()

    # --- Comparison mode & settings ---

    def set_comparison_mode(self, mode: ComparisonMode):
        """Switch the comparison mode between SINGLE and MULTI.

        Input: mode — ComparisonMode enum value.
        Output: None
        Invariants: self.comparison_mode == mode after this call.
        """
        self.comparison_manager.set_comparison_mode(mode)

    def set_comparison_datasets(self, dataset_ids: List[str]):
        """Set the full list of datasets used in multi-dataset comparison.

        Input: dataset_ids — List[str], ordered list of dataset IDs to compare.
        Output: None
        Invariants: self.comparison_dataset_ids == dataset_ids after this call.
        """
        self.comparison_manager.set_comparison_datasets(dataset_ids)

    def toggle_dataset_comparison(self, dataset_id: str) -> bool:
        """Add or remove a dataset from the active comparison set.

        Input: dataset_id — str, ID of the dataset to toggle.
        Output: bool — True if the dataset is now included, False if excluded.
        """
        return self.comparison_manager.toggle_dataset_comparison(dataset_id)

    def set_dataset_color(self, dataset_id: str, color: str):
        """Assign a display color to a dataset for use in comparison charts.

        Input: dataset_id — str, ID of the target dataset.
               color — str, CSS hex color string (e.g. "#1f77b4").
        Output: None
        """
        self.comparison_manager.set_dataset_color(dataset_id, color)

    def get_comparison_colors(self) -> Dict[str, str]:
        """Return the color mapping for all datasets in the active comparison set.

        Output: Dict[str, str] — dataset ID to hex color string.
        """
        return self.comparison_manager.get_comparison_colors()

    def update_comparison_settings(self, **kwargs):
        """Update one or more fields of the active ComparisonSettings.

        Input: **kwargs — ComparisonSettings attribute names and their new values.
        Output: None
        """
        self.comparison_manager.update_comparison_settings(**kwargs)

    # ==================== Profile Comparison (PRD §6.1) ====================

    def set_profile_comparison(self, dataset_id: str, profile_ids: List[str]):
        """Enter profile comparison mode for a dataset, comparing the given profiles.

        Per FR-8: any active dataset comparison is automatically cleared on entry.

        Input: dataset_id — str, dataset whose profiles are being compared.
               profile_ids — List[str], profile IDs to include in the comparison.
        Output: None
        Invariants: self.is_profile_comparison_active is True after this call.
        """
        self.comparison_manager.set_profile_comparison(dataset_id, profile_ids)

    def clear_profile_comparison(self):
        """Exit profile comparison mode and return to SINGLE mode.

        Output: None
        Invariants: self.is_profile_comparison_active is False after this call.
        """
        self.comparison_manager.clear_profile_comparison()

    # ==================== Dataset Profiles ====================

    def add_graph_setting_to_dataset(self, dataset_id: str, setting: 'GraphSetting') -> bool:
        """Add a GraphSetting to a dataset's profile list.

        Input: dataset_id — str, target dataset ID.
               setting — GraphSetting, the setting to add.
        Output: bool — True if added successfully, False otherwise.
        """
        return self.comparison_manager.add_graph_setting_to_dataset(dataset_id, setting)

    def remove_graph_setting(self, dataset_id: str, setting_id: str) -> bool:
        """Remove a GraphSetting from a dataset's profile list by ID.

        Input: dataset_id — str, target dataset ID.
               setting_id — str, ID of the setting to remove.
        Output: bool — True if removed, False if not found.
        """
        return self.comparison_manager.remove_graph_setting(dataset_id, setting_id)

    def rename_graph_setting(self, dataset_id: str, setting_id: str, name: str) -> bool:
        """Rename a GraphSetting within a dataset's profile list.

        Input: dataset_id — str, target dataset ID.
               setting_id — str, ID of the setting to rename.
               name — str, new display name.
        Output: bool — True if renamed, False if setting not found.
        """
        return self.comparison_manager.rename_graph_setting(dataset_id, setting_id, name)

    def get_dataset_profiles(self, dataset_id: str) -> List['GraphSetting']:
        """Return all saved GraphSettings associated with a dataset.

        Input: dataset_id — str, target dataset ID.
        Output: List[GraphSetting] — may be empty if none are saved.
        """
        return self.comparison_manager.get_dataset_profiles(dataset_id)

    def build_graph_setting_from_state(self, name: str, dataset_id: str = "") -> 'GraphSetting':
        """Create a GraphSetting snapshot from the current AppState.

        Input: name — str, display name for the new setting.
               dataset_id — str, optional dataset ID to associate the setting with.
        Output: GraphSetting — populated with current chart type, zones, filters, and sorts.
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
        """Update the data-loaded flag and reset row counts.

        Input: loaded — bool; True when data is present, False when cleared.
               total_rows — int, total row count in the loaded dataset (default 0).
        Output: None
        Emits: data_loaded when loaded is True; data_cleared when False.
        Invariants: self._total_rows == self._visible_rows == total_rows after this call.
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
        """Update the visible row count after filter application.

        Input: count — int, number of rows remaining after all filters are applied.
        Output: None
        Invariants: self._visible_rows == count after this call.
        """
        self._visible_rows = count

