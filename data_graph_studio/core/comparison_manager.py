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
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
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
        # Import lazily to avoid circular dependency at class definition time
        from .state import SelectionState, ChartSettings
        if self.selection is None:
            self.selection = SelectionState()
        if self.chart_settings is None:
            self.chart_settings = ChartSettings()

    def clone(self) -> 'DatasetState':
        """상태 복제"""
        import copy
        return copy.deepcopy(self)

    def reset(self):
        """상태 초기화"""
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
        super().__init__()

        self._dataset_states: Dict[str, DatasetState] = {}
        self._dataset_metadata: Dict[str, DatasetMetadata] = {}
        self._active_dataset_id: Optional[str] = None
        self._comparison_settings: ComparisonSettings = ComparisonSettings()
        self._dataset_color_index: int = 0

    # ==================== Properties ====================

    @property
    def dataset_states(self) -> Dict[str, DatasetState]:
        """Return the mapping of dataset ID to DatasetState."""
        return self._dataset_states

    @property
    def dataset_metadata(self) -> Dict[str, DatasetMetadata]:
        """Return the mapping of dataset ID to DatasetMetadata."""
        return self._dataset_metadata

    @property
    def active_dataset_id(self) -> Optional[str]:
        """Return the ID of the currently active dataset."""
        return self._active_dataset_id

    @property
    def active_dataset_state(self) -> Optional[DatasetState]:
        """Return the DatasetState of the currently active dataset, or None."""
        if self._active_dataset_id:
            return self._dataset_states.get(self._active_dataset_id)
        return None

    @property
    def comparison_settings(self) -> ComparisonSettings:
        """Return the current comparison settings."""
        return self._comparison_settings

    @property
    def comparison_mode(self) -> ComparisonMode:
        """Return the active comparison mode."""
        return self._comparison_settings.mode

    @property
    def dataset_count(self) -> int:
        """Return the number of loaded datasets."""
        return len(self._dataset_states)

    @property
    def comparison_dataset_ids(self) -> List[str]:
        """Return the list of dataset IDs included in comparison."""
        return self._comparison_settings.comparison_datasets

    @property
    def is_profile_comparison_active(self) -> bool:
        """Return True when profile comparison mode is active with at least two profiles."""
        return (
            self._comparison_settings.comparison_target == "profile"
            and len(self._comparison_settings.comparison_profile_ids) >= 2
            and self._comparison_settings.mode != ComparisonMode.SINGLE
        )

    # ==================== Dataset CRUD ====================

    def get_dataset_state(self, dataset_id: str) -> Optional[DatasetState]:
        """Return the DatasetState for the given ID, or None if not found."""
        return self._dataset_states.get(dataset_id)

    def get_dataset_metadata(self, dataset_id: str) -> Optional[DatasetMetadata]:
        """Return the DatasetMetadata for the given ID, or None if not found."""
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
        """새 데이터셋 추가. 생성된 DatasetState 반환."""
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

        logger.debug("comparison_manager.add_dataset", extra={"dataset_id": dataset_id, "name": name})
        self.emit("dataset_added", dataset_id)
        return state

    def remove_dataset(self, dataset_id: str) -> bool:
        """데이터셋 제거. 성공 여부 반환."""
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
        """데이터셋 활성화. 성공 여부 반환."""
        if dataset_id not in self._dataset_states:
            return False

        if self._active_dataset_id and self._active_dataset_id in self._dataset_metadata:
            self._dataset_metadata[self._active_dataset_id].is_active = False

        self._active_dataset_id = dataset_id
        self._dataset_metadata[dataset_id].is_active = True
        self.emit("dataset_activated", dataset_id)
        return True

    def update_dataset_metadata(self, dataset_id: str, **kwargs):
        """데이터셋 메타데이터 업데이트."""
        if dataset_id in self._dataset_metadata:
            metadata = self._dataset_metadata[dataset_id]
            for key, value in kwargs.items():
                if hasattr(metadata, key):
                    setattr(metadata, key, value)
            self.emit("dataset_updated", dataset_id)

    def clear_all_datasets(self):
        """모든 데이터셋 제거."""
        dataset_ids = list(self._dataset_states.keys())
        for did in dataset_ids:
            self.remove_dataset(did)
        self._dataset_color_index = 0

    # ==================== Comparison Mode & Settings ====================

    def set_comparison_mode(self, mode: ComparisonMode):
        """비교 모드 설정. FR-8: 데이터셋 비교 진입 시 프로파일 비교 해제."""
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
        """비교 대상 데이터셋 설정. FR-8: 프로파일 비교 자동 해제."""
        if self._comparison_settings.comparison_target == "profile":
            self._comparison_settings.comparison_target = "dataset"
            self._comparison_settings.comparison_profile_ids.clear()
            self._comparison_settings.comparison_dataset_id = ""

        valid_ids = [did for did in dataset_ids if did in self._dataset_states]
        self._comparison_settings.comparison_datasets = valid_ids
        self.emit("comparison_settings_changed")

    def toggle_dataset_comparison(self, dataset_id: str) -> bool:
        """데이터셋 비교 포함 여부 토글. 변경 후 상태 반환."""
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
        """데이터셋 색상 설정."""
        if dataset_id in self._dataset_metadata:
            self._dataset_metadata[dataset_id].color = color
            self.emit("dataset_updated", dataset_id)

    def get_comparison_colors(self) -> Dict[str, str]:
        """비교 대상 데이터셋들의 색상 매핑 반환."""
        return {
            did: self._dataset_metadata[did].color
            for did in self._comparison_settings.comparison_datasets
            if did in self._dataset_metadata
        }

    def update_comparison_settings(self, **kwargs):
        """비교 설정 업데이트."""
        for key, value in kwargs.items():
            if hasattr(self._comparison_settings, key):
                setattr(self._comparison_settings, key, value)
        self.emit("comparison_settings_changed")

    # ==================== Profile Comparison (PRD §6.1) ====================

    def set_profile_comparison(self, dataset_id: str, profile_ids: List[str]):
        """
        프로파일 비교 모드 진입.

        FR-8: 데이터셋 비교가 활성이면 자동 해제.
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
        """프로파일 비교 모드 종료 → SINGLE 모드 복귀."""
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
        """Add a graph setting (profile) to the specified dataset."""
        state = self._dataset_states.get(dataset_id)
        if not state:
            return False
        state.profiles.append(setting)
        self.emit("dataset_updated", dataset_id)
        return True

    def remove_graph_setting(self, dataset_id: str, setting_id: str) -> bool:
        """Remove a graph setting from a dataset by setting ID."""
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
        """Rename a graph setting within a dataset."""
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
        """Return all graph settings (profiles) for the given dataset."""
        state = self._dataset_states.get(dataset_id)
        return state.profiles if state else []
