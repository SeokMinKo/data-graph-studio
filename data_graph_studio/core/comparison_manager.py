"""
ComparisonManager — 멀티 데이터셋 비교 상태 관리

AppState에서 추출한 비교 관련 책임을 담당.
AppState는 이 클래스를 인스턴스로 보유하고 public API를 위임(delegate)한다.

이 모듈은 비교 관련 타입(ComparisonMode, ComparisonSettings, DatasetMetadata,
DatasetState, DEFAULT_DATASET_COLORS)도 함께 정의하여 state.py와의 순환 임포트를
방지한다. state.py는 이 모듈에서 해당 타입들을 re-import한다.
"""

import logging
import uuid
from typing import Optional, List, Dict, Set, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

from data_graph_studio.core.constants import DATASET_ID_LENGTH
from data_graph_studio.core.observable import Observable

if TYPE_CHECKING:
    from .profile import GraphSetting


# ==================== Comparison Types (moved from state.py) ====================

class ComparisonMode(Enum):
    """데이터셋 비교 모드"""
    SINGLE = "single"               # 단일 데이터셋 (기존 모드)
    OVERLAY = "overlay"             # 오버레이 비교 (하나의 차트에 여러 데이터셋)
    SIDE_BY_SIDE = "side_by_side"   # 병렬 비교 (각각 독립 패널)
    DIFFERENCE = "difference"       # 차이 분석 (두 데이터셋 간 차이)


@dataclass
class DatasetMetadata:
    """데이터셋 메타데이터"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:DATASET_ID_LENGTH])
    name: str = ""
    file_path: Optional[str] = None
    color: str = "#1f77b4"
    created_at: datetime = field(default_factory=datetime.now)
    row_count: int = 0
    column_count: int = 0
    memory_bytes: int = 0
    is_active: bool = False
    compare_enabled: bool = True  # 비교에 포함할지 여부


# 기본 데이터셋 색상 팔레트
DEFAULT_DATASET_COLORS = [
    "#1f77b4",  # 파랑
    "#ff7f0e",  # 주황
    "#2ca02c",  # 초록
    "#d62728",  # 빨강
    "#9467bd",  # 보라
    "#8c564b",  # 갈색
    "#e377c2",  # 분홍
    "#7f7f7f",  # 회색
    "#bcbd22",  # 올리브
    "#17becf",  # 청록
]


@dataclass
class ComparisonSettings:
    """비교 모드 설정"""
    mode: ComparisonMode = field(default_factory=lambda: ComparisonMode.SINGLE)
    comparison_datasets: List[str] = field(default_factory=list)  # 비교 대상 데이터셋 ID들
    key_column: Optional[str] = None  # 정렬/조인 기준 컬럼
    sync_scroll: bool = True
    sync_zoom: bool = True
    sync_pan_x: bool = True
    sync_pan_y: bool = True
    sync_selection: bool = False
    auto_align: bool = True  # 키 컬럼 기준 자동 정렬

    # Profile comparison fields (PRD §6.1)
    comparison_target: str = "dataset"  # "dataset" | "profile"
    comparison_profile_ids: List[str] = field(default_factory=list)
    comparison_dataset_id: str = ""  # 프로파일 비교 시 대상 데이터셋 ID


# ==================== DatasetState (moved from state.py) ====================
# Note: DatasetState references types from state.py (GroupColumn, ValueColumn, etc.)
# Those live in state.py and are imported below via TYPE_CHECKING. At runtime,
# DatasetState is a plain dataclass so forward refs resolve fine.

if TYPE_CHECKING:
    from .state import GroupColumn, ValueColumn, FilterCondition, SortCondition, SelectionState, ChartSettings, GraphSetting as _GraphSetting


@dataclass
class DatasetState:
    """
    개별 데이터셋의 상태.

    각 데이터셋은 독립적인 그래프 설정, 필터, 정렬 등을 가질 수 있음.
    """
    dataset_id: str
    x_column: Optional[str] = None
    group_columns: List = field(default_factory=list)          # List[GroupColumn]
    value_columns: List = field(default_factory=list)          # List[ValueColumn]
    hover_columns: List[str] = field(default_factory=list)
    filters: List = field(default_factory=list)                # List[FilterCondition]
    sorts: List = field(default_factory=list)                  # List[SortCondition]
    selection: object = field(default_factory=lambda: None)    # SelectionState (set at runtime)
    chart_settings: object = field(default_factory=lambda: None)  # ChartSettings (set at runtime)
    profiles: List = field(default_factory=list)               # List[GraphSetting]

    def __post_init__(self):
        """Initialise runtime fields with their default objects after dataclass construction.

        Output: None
        Invariants: self.selection is a SelectionState and self.chart_settings is a ChartSettings
                    instance after this call; lazy imports avoid circular dependencies
        """
        # Import lazily to avoid circular dependency at class definition time
        from .state import SelectionState, ChartSettings
        if self.selection is None:
            self.selection = SelectionState()
        if self.chart_settings is None:
            self.chart_settings = ChartSettings()

    def clone(self) -> 'DatasetState':
        """Return a deep copy of this DatasetState.

        Output: DatasetState — independent copy with all fields duplicated
        Invariants: original is unchanged; result.dataset_id == self.dataset_id
        """
        import copy
        return copy.deepcopy(self)

    def reset(self):
        """Reset all mutable fields to their initial empty/default values.

        Output: None
        Invariants: x_column is None; all list fields are empty; selection and chart_settings are fresh defaults
        """
        from .state import ChartSettings
        self.x_column = None
        self.group_columns.clear()
        self.value_columns.clear()
        self.hover_columns.clear()
        self.filters.clear()
        self.sorts.clear()
        self.selection.clear()
        self.chart_settings = ChartSettings()
        self.profiles.clear()


# ==================== ComparisonManager ====================

class ComparisonManager(Observable):
    """
    멀티 데이터셋 비교 상태 및 프로파일 비교 관리.

    Events:
        dataset_added(str)              — 데이터셋 추가됨
        dataset_removed(str)            — 데이터셋 제거됨
        dataset_activated(str)          — 데이터셋 활성화됨
        dataset_updated(str)            — 데이터셋 메타데이터 변경됨
        comparison_mode_changed(str)    — 비교 모드 변경됨 (mode.value)
        comparison_settings_changed()   — 비교 설정 변경됨
    """

    def __init__(self):
        """Initialize the ComparisonManager with empty state and default settings.

        Output: None
        Invariants: _dataset_states and _dataset_metadata are empty; _active_dataset_id is None;
                    _comparison_settings defaults to SINGLE mode; _dataset_color_index starts at 0
        """
        super().__init__()

        self._dataset_states: Dict[str, DatasetState] = {}
        self._dataset_metadata: Dict[str, DatasetMetadata] = {}
        self._active_dataset_id: Optional[str] = None
        self._comparison_settings: ComparisonSettings = ComparisonSettings()
        self._dataset_color_index: int = 0

    # ==================== Properties ====================

    @property
    def dataset_states(self) -> Dict[str, DatasetState]:
        """Return the mapping of dataset ID to DatasetState.

        Output: Dict[str, DatasetState] — live reference; mutate with caution
        """
        return self._dataset_states

    @property
    def dataset_metadata(self) -> Dict[str, DatasetMetadata]:
        """Return the mapping of dataset ID to DatasetMetadata.

        Output: Dict[str, DatasetMetadata] — live reference; mutate with caution
        """
        return self._dataset_metadata

    @property
    def active_dataset_id(self) -> Optional[str]:
        """Return the ID of the currently active dataset.

        Output: Optional[str] — dataset ID string, or None if no dataset is active
        """
        return self._active_dataset_id

    @property
    def active_dataset_state(self) -> Optional[DatasetState]:
        """Return the DatasetState of the currently active dataset, or None.

        Output: Optional[DatasetState] — state for active dataset, or None when no dataset is active
        """
        if self._active_dataset_id:
            return self._dataset_states.get(self._active_dataset_id)
        return None

    @property
    def comparison_settings(self) -> ComparisonSettings:
        """Return the current comparison settings.

        Output: ComparisonSettings — live reference containing mode, sync flags, and dataset IDs
        """
        return self._comparison_settings

    @property
    def comparison_mode(self) -> ComparisonMode:
        """Return the active comparison mode.

        Output: ComparisonMode — current mode enum value (SINGLE, OVERLAY, SIDE_BY_SIDE, or DIFFERENCE)
        """
        return self._comparison_settings.mode

    @property
    def dataset_count(self) -> int:
        """Return the number of loaded datasets.

        Output: int — count of entries in _dataset_states, >= 0
        """
        return len(self._dataset_states)

    @property
    def comparison_dataset_ids(self) -> List[str]:
        """Return the list of dataset IDs included in comparison.

        Output: List[str] — ordered list of dataset IDs from comparison_settings
        """
        return self._comparison_settings.comparison_datasets

    @property
    def is_profile_comparison_active(self) -> bool:
        """Return True when profile comparison mode is active with at least two profiles.

        Output: bool — True only when target=="profile", mode!=SINGLE, and >= 2 profile IDs are set
        """
        return (
            self._comparison_settings.comparison_target == "profile"
            and len(self._comparison_settings.comparison_profile_ids) >= 2
            and self._comparison_settings.mode != ComparisonMode.SINGLE
        )

    # ==================== Dataset CRUD ====================

    def get_dataset_state(self, dataset_id: str) -> Optional[DatasetState]:
        """Return the DatasetState for a dataset.

        Input: dataset_id — str, the dataset ID to look up
        Output: Optional[DatasetState] — the matching state, or None if not found
        """
        return self._dataset_states.get(dataset_id)

    def get_dataset_metadata(self, dataset_id: str) -> Optional[DatasetMetadata]:
        """Return the DatasetMetadata for a dataset.

        Input: dataset_id — str, the dataset ID to look up
        Output: Optional[DatasetMetadata] — the matching metadata, or None if not found
        """
        return self._dataset_metadata.get(dataset_id)

    def add_dataset(
        self,
        dataset_id: str,
        name: str = "",
        file_path: str = None,
        row_count: int = 0,
        column_count: int = 0,
        memory_bytes: int = 0,
    ) -> DatasetState:
        """Register a new dataset with metadata and create its initial state.

        Input: dataset_id — str, unique identifier for this dataset
        Input: name — str, display name; defaults to "Dataset N" where N is the current count + 1
        Input: file_path — Optional[str], source file path stored in metadata
        Input: row_count — int, number of rows, stored in metadata
        Input: column_count — int, number of columns, stored in metadata
        Input: memory_bytes — int, estimated memory footprint in bytes
        Output: DatasetState — the newly created state object for this dataset
        Invariants: dataset_id is added to _dataset_states and _dataset_metadata; appended to comparison_datasets if compare_enabled; "dataset_added" event is emitted; _active_dataset_id is set if this is the first dataset
        """
        color = DEFAULT_DATASET_COLORS[self._dataset_color_index % len(DEFAULT_DATASET_COLORS)]
        self._dataset_color_index += 1

        metadata = DatasetMetadata(
            id=dataset_id,
            name=name or f"Dataset {len(self._dataset_metadata) + 1}",
            file_path=file_path,
            color=color,
            row_count=row_count,
            column_count=column_count,
            memory_bytes=memory_bytes,
            is_active=len(self._dataset_states) == 0,
        )
        self._dataset_metadata[dataset_id] = metadata

        state = DatasetState(dataset_id=dataset_id)
        self._dataset_states[dataset_id] = state

        if self._active_dataset_id is None:
            self._active_dataset_id = dataset_id
            metadata.is_active = True

        if metadata.compare_enabled:
            self._comparison_settings.comparison_datasets.append(dataset_id)

        logger.debug("comparison_manager.add_dataset", extra={"dataset_id": dataset_id, "dataset_name": name})
        self.emit("dataset_added", dataset_id)
        return state

    def remove_dataset(self, dataset_id: str) -> bool:
        """Remove a dataset from state and metadata.

        Input: dataset_id — str, ID of the dataset to remove
        Output: bool — True if removed, False if dataset_id was not found
        Invariants: dataset_id is purged from _dataset_states, _dataset_metadata, and comparison_datasets; if the removed dataset was active, _active_dataset_id advances to the next remaining dataset or becomes None; "dataset_removed" event is emitted
        """
        if dataset_id not in self._dataset_states:
            return False

        del self._dataset_states[dataset_id]
        del self._dataset_metadata[dataset_id]

        if dataset_id in self._comparison_settings.comparison_datasets:
            self._comparison_settings.comparison_datasets.remove(dataset_id)

        if self._active_dataset_id == dataset_id:
            if self._dataset_states:
                self._active_dataset_id = next(iter(self._dataset_states.keys()))
                self._dataset_metadata[self._active_dataset_id].is_active = True
                self.emit("dataset_activated", self._active_dataset_id)
            else:
                self._active_dataset_id = None

        logger.debug("comparison_manager.remove_dataset", extra={"dataset_id": dataset_id})
        self.emit("dataset_removed", dataset_id)
        return True

    def activate_dataset(self, dataset_id: str) -> bool:
        """Set a dataset as the active dataset.

        Input: dataset_id — str, ID of the dataset to activate; must exist in _dataset_states
        Output: bool — True if activated, False if dataset_id is not found
        Invariants: previously active dataset's is_active flag is set to False; new dataset's is_active flag is set to True; "dataset_activated" event is emitted
        """
        if dataset_id not in self._dataset_states:
            return False

        if self._active_dataset_id and self._active_dataset_id in self._dataset_metadata:
            self._dataset_metadata[self._active_dataset_id].is_active = False

        self._active_dataset_id = dataset_id
        self._dataset_metadata[dataset_id].is_active = True
        self.emit("dataset_activated", dataset_id)
        return True

    def update_dataset_metadata(self, dataset_id: str, **kwargs):
        """Update arbitrary fields on a dataset's DatasetMetadata.

        Input: dataset_id — str, ID of the target dataset
        Input: **kwargs — keyword arguments whose names match DatasetMetadata field names; unknown keys are silently skipped via hasattr guard
        Output: None
        Invariants: only recognised DatasetMetadata attributes are modified; "dataset_updated" event is emitted if dataset_id is found
        """
        if dataset_id in self._dataset_metadata:
            metadata = self._dataset_metadata[dataset_id]
            for key, value in kwargs.items():
                if hasattr(metadata, key):
                    setattr(metadata, key, value)
            self.emit("dataset_updated", dataset_id)

    def clear_all_datasets(self):
        """Remove every dataset and reset the color cycle.

        Output: None
        Invariants: _dataset_states and _dataset_metadata are empty after this call; _dataset_color_index is reset to 0; remove_dataset() is called for each entry, emitting "dataset_removed" per dataset
        """
        dataset_ids = list(self._dataset_states.keys())
        for did in dataset_ids:
            self.remove_dataset(did)
        self._dataset_color_index = 0

    # ==================== Comparison Mode & Settings ====================

    def set_comparison_mode(self, mode: ComparisonMode):
        """Set the active comparison mode, clearing any active profile comparison.

        Input: mode — ComparisonMode, the desired comparison mode
        Output: None
        Invariants: if profile comparison was active it is cleared (target reset to "dataset", profile IDs cleared); "comparison_mode_changed" is emitted only when the mode actually changes; "comparison_settings_changed" is always emitted when mode or profile state changes
        """
        was_profile = self._comparison_settings.comparison_target == "profile"
        if was_profile:
            self._comparison_settings.comparison_target = "dataset"
            self._comparison_settings.comparison_profile_ids.clear()
            self._comparison_settings.comparison_dataset_id = ""

        if self._comparison_settings.mode != mode:
            self._comparison_settings.mode = mode
            self.emit("comparison_mode_changed", mode.value)
            self.emit("comparison_settings_changed")
        elif was_profile:
            self.emit("comparison_settings_changed")

    def set_comparison_datasets(self, dataset_ids: List[str]):
        """Replace the list of datasets included in comparison, clearing profile comparison if active.

        Input: dataset_ids — List[str], desired dataset IDs; IDs not present in _dataset_states are filtered out
        Output: None
        Invariants: comparison_datasets contains only valid, currently-loaded IDs after this call; profile comparison target is reset to "dataset" if it was active; "comparison_settings_changed" is emitted
        """
        if self._comparison_settings.comparison_target == "profile":
            self._comparison_settings.comparison_target = "dataset"
            self._comparison_settings.comparison_profile_ids.clear()
            self._comparison_settings.comparison_dataset_id = ""

        valid_ids = [did for did in dataset_ids if did in self._dataset_states]
        self._comparison_settings.comparison_datasets = valid_ids
        self.emit("comparison_settings_changed")

    def toggle_dataset_comparison(self, dataset_id: str) -> bool:
        """Toggle whether a dataset is included in the active comparison.

        Input: dataset_id — str, ID of the dataset to toggle; must exist in _dataset_metadata
        Output: bool — the new compare_enabled value after toggling; False if dataset_id is not found
        Invariants: dataset_id is added to or removed from comparison_datasets to match the new compare_enabled flag; "comparison_settings_changed" is emitted
        """
        if dataset_id not in self._dataset_metadata:
            return False

        metadata = self._dataset_metadata[dataset_id]
        metadata.compare_enabled = not metadata.compare_enabled

        if metadata.compare_enabled:
            if dataset_id not in self._comparison_settings.comparison_datasets:
                self._comparison_settings.comparison_datasets.append(dataset_id)
        else:
            if dataset_id in self._comparison_settings.comparison_datasets:
                self._comparison_settings.comparison_datasets.remove(dataset_id)

        self.emit("comparison_settings_changed")
        return metadata.compare_enabled

    def set_dataset_color(self, dataset_id: str, color: str):
        """Update the display color of a dataset.

        Input: dataset_id — str, ID of the target dataset
        Input: color — str, hex color string (e.g. '#ff7f0e')
        Output: None
        Invariants: silently no-ops if dataset_id is not found; "dataset_updated" event is emitted on success
        """
        if dataset_id in self._dataset_metadata:
            self._dataset_metadata[dataset_id].color = color
            self.emit("dataset_updated", dataset_id)

    def get_comparison_colors(self) -> Dict[str, str]:
        """Return a color mapping for all datasets currently included in comparison.

        Output: Dict[str, str] — mapping of dataset_id to hex color string for each ID in comparison_datasets that has metadata; omits IDs whose metadata is missing
        """
        return {
            did: self._dataset_metadata[did].color
            for did in self._comparison_settings.comparison_datasets
            if did in self._dataset_metadata
        }

    def update_comparison_settings(self, **kwargs):
        """Update arbitrary fields on the current ComparisonSettings.

        Input: **kwargs — keyword arguments whose names match ComparisonSettings field names; unknown keys are silently skipped via hasattr guard
        Output: None
        Invariants: "comparison_settings_changed" is emitted after applying any provided values
        """
        for key, value in kwargs.items():
            if hasattr(self._comparison_settings, key):
                setattr(self._comparison_settings, key, value)
        self.emit("comparison_settings_changed")

    # ==================== Profile Comparison (PRD §6.1) ====================

    def set_profile_comparison(self, dataset_id: str, profile_ids: List[str]):
        """Enter profile comparison mode for the specified dataset and profiles.

        Input: dataset_id — str, the dataset whose profiles are being compared
        Input: profile_ids — List[str], IDs of the profiles to compare; at least two are needed for is_profile_comparison_active to return True
        Output: None
        Invariants: comparison_target is set to "profile"; existing dataset comparison list is cleared; mode is promoted to SIDE_BY_SIDE if it was SINGLE; "comparison_mode_changed" is emitted when mode changes; "comparison_settings_changed" is always emitted
        """
        self._comparison_settings.comparison_datasets.clear()
        self._comparison_settings.comparison_target = "profile"
        self._comparison_settings.comparison_dataset_id = dataset_id
        self._comparison_settings.comparison_profile_ids = list(profile_ids)

        mode_changed = False
        if self._comparison_settings.mode == ComparisonMode.SINGLE:
            self._comparison_settings.mode = ComparisonMode.SIDE_BY_SIDE
            mode_changed = True

        if mode_changed:
            self.emit("comparison_mode_changed", self._comparison_settings.mode.value)
        self.emit("comparison_settings_changed")

    def clear_profile_comparison(self):
        """Exit profile comparison mode and return to SINGLE comparison mode.

        Output: None
        Invariants: comparison_target is reset to "dataset", comparison_profile_ids is cleared, mode is set to SINGLE; "comparison_mode_changed" is emitted if mode changed; "comparison_settings_changed" is emitted if profile comparison was active or mode changed
        """
        was_active = self.is_profile_comparison_active

        self._comparison_settings.comparison_target = "dataset"
        self._comparison_settings.comparison_profile_ids.clear()
        self._comparison_settings.comparison_dataset_id = ""

        mode_changed = self._comparison_settings.mode != ComparisonMode.SINGLE
        self._comparison_settings.mode = ComparisonMode.SINGLE

        if was_active or mode_changed:
            if mode_changed:
                self.emit("comparison_mode_changed", ComparisonMode.SINGLE.value)
            self.emit("comparison_settings_changed")

    # ==================== Dataset Profiles ====================

    def add_graph_setting_to_dataset(self, dataset_id: str, setting: 'GraphSetting') -> bool:
        """Append a graph setting (profile) to a dataset's profile list.

        Input: dataset_id — str, ID of the target dataset
        Input: setting — GraphSetting, the profile to append
        Output: bool — True if appended, False if dataset_id is not found
        Invariants: setting is appended to state.profiles; "dataset_updated" event is emitted on success
        """
        state = self._dataset_states.get(dataset_id)
        if not state:
            return False
        state.profiles.append(setting)
        self.emit("dataset_updated", dataset_id)
        return True

    def remove_graph_setting(self, dataset_id: str, setting_id: str) -> bool:
        """Remove a graph setting from a dataset by its ID.

        Input: dataset_id — str, ID of the target dataset
        Input: setting_id — str, ID of the GraphSetting to remove
        Output: bool — True if a matching setting was found and removed, False if the dataset was not found or the setting_id did not match any profile
        Invariants: state.profiles is rebuilt without the matched entry; "dataset_updated" event is emitted only when a setting was actually removed
        """
        state = self._dataset_states.get(dataset_id)
        if not state:
            return False
        before = len(state.profiles)
        state.profiles = [s for s in state.profiles if s.id != setting_id]
        if len(state.profiles) != before:
            self.emit("dataset_updated", dataset_id)
            return True
        return False

    def rename_graph_setting(self, dataset_id: str, setting_id: str, name: str) -> bool:
        """Rename a graph setting within a dataset's profile list.

        Input: dataset_id — str, ID of the target dataset
        Input: setting_id — str, ID of the GraphSetting to rename
        Input: name — str, new display name for the setting
        Output: bool — True if the setting was found and renamed, False if the dataset or setting_id was not found
        Invariants: the setting is replaced in-place via GraphSetting.with_name(); "dataset_updated" event is emitted on success
        """
        state = self._dataset_states.get(dataset_id)
        if not state:
            return False
        for i, s in enumerate(state.profiles):
            if s.id == setting_id:
                state.profiles[i] = s.with_name(name)
                self.emit("dataset_updated", dataset_id)
                return True
        return False

    def get_dataset_profiles(self, dataset_id: str) -> List['GraphSetting']:
        """Return all graph settings (profiles) for a dataset.

        Input: dataset_id — str, the dataset ID to look up
        Output: List[GraphSetting] — the dataset's profiles list, or an empty list if the dataset is not found
        """
        state = self._dataset_states.get(dataset_id)
        return state.profiles if state else []
