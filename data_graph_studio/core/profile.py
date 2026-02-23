"""
Graph Profiles - 그래프 설정 프로파일 관리
"""

import logging
import os
import json
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
import dataclasses

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphSetting:
    """단일 그래프 설정 (프로파일).

    ProfileStore가 직접 관리하는 주요 엔티티.
    Profile 클래스는 파일 I/O (.dgp) 용 컨테이너로,
    여러 GraphSetting을 묶어서 내보내기/가져오기할 때 사용.

    일상적인 프로파일 CRUD는 ProfileStore + GraphSetting으로 처리.
    """
    id: str
    name: str
    dataset_id: str
    schema_version: int = 1
    chart_type: str = ""
    x_column: Optional[str] = None
    group_columns: Tuple = ()
    value_columns: Tuple = ()
    hover_columns: Tuple[str, ...] = ()
    filters: Tuple = ()
    sorts: Tuple = ()
    chart_settings: Optional[Mapping[str, Any]] = None
    include_filters: bool = False
    include_sorts: bool = False
    icon: str = "📊"
    description: str = ""
    is_favorite: bool = False
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)

    def __post_init__(self):
        object.__setattr__(self, "group_columns", tuple(self.group_columns))
        object.__setattr__(self, "value_columns", tuple(self.value_columns))
        object.__setattr__(self, "hover_columns", tuple(self.hover_columns))
        object.__setattr__(self, "filters", tuple(self.filters))
        object.__setattr__(self, "sorts", tuple(self.sorts))
        if self.chart_settings is None:
            object.__setattr__(self, "chart_settings", MappingProxyType({}))
        elif not isinstance(self.chart_settings, MappingProxyType):
            object.__setattr__(self, "chart_settings", MappingProxyType(dict(self.chart_settings)))

    @classmethod
    def create_new(cls, name: str, icon: str = "📊", dataset_id: str = "") -> 'GraphSetting':
        """Create a new GraphSetting with a freshly generated UUID and default field values.

        Input: name — str, display name for the setting;
               icon — str, emoji icon (default "📊");
               dataset_id — str, associated dataset ID (default "")
        Output: GraphSetting — a frozen instance with a new UUID, both timestamps set to now, and all columns/filters empty
        """
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            dataset_id=dataset_id,
            icon=icon,
        )

    def with_name(self, name: str) -> 'GraphSetting':
        """Return a new GraphSetting with the given name and an updated modified timestamp.

        Input: name — str, new display name for the setting
        Output: GraphSetting — frozen copy of self with name and modified_at updated
        Invariants: all other fields are identical to the original
        """
        return dataclasses.replace(self, name=name, modified_at=time.time())

    def update_modified(self) -> 'GraphSetting':
        """Return a copy of this GraphSetting with modified_at refreshed to the current time.

        Output: GraphSetting — a new frozen instance identical to self except for an updated modified_at timestamp
        Invariants: all fields except modified_at are identical to the original
        """
        return dataclasses.replace(self, modified_at=time.time())

    def to_dict(self) -> Dict:
        """Serialize this graph setting to a JSON-compatible dictionary.

        Output: Dict — all GraphSetting fields in a JSON-safe format; round-trips with from_dict
        """
        return {
            "id": self.id,
            "name": self.name,
            "dataset_id": self.dataset_id,
            "schema_version": self.schema_version,
            "chart_type": self.chart_type,
            "x_column": self.x_column,
            "group_columns": list(self.group_columns),
            "value_columns": list(self.value_columns),
            "hover_columns": list(self.hover_columns),
            "filters": list(self.filters),
            "sorts": list(self.sorts),
            "chart_settings": dict(self.chart_settings),
            "include_filters": self.include_filters,
            "include_sorts": self.include_sorts,
            "icon": self.icon,
            "description": self.description,
            "is_favorite": self.is_favorite,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'GraphSetting':
        """Deserialize a GraphSetting from a dictionary produced by to_dict.

        Input: data — Dict, as produced by to_dict()
        Output: GraphSetting — fully populated frozen instance; missing keys use defaults
        """
        return cls(
            id=data["id"],
            name=data["name"],
            dataset_id=data.get("dataset_id", ""),
            schema_version=data.get("schema_version", 1),
            chart_type=data.get("chart_type", ""),
            x_column=data.get("x_column"),
            group_columns=tuple(data.get("group_columns", ())),
            value_columns=tuple(data.get("value_columns", ())),
            hover_columns=tuple(data.get("hover_columns", ())),
            filters=tuple(data.get("filters", ())),
            sorts=tuple(data.get("sorts", ())),
            chart_settings=data.get("chart_settings", {}),
            include_filters=data.get("include_filters", False),
            include_sorts=data.get("include_sorts", False),
            icon=data.get("icon", "📊"),
            description=data.get("description", ""),
            is_favorite=data.get("is_favorite", False),
            created_at=data.get("created_at", time.time()),
            modified_at=data.get("modified_at", time.time()),
        )


@dataclass
class Profile:
    """그래프 프로파일"""
    id: str
    name: str
    description: str = ""
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)

    # 데이터 스키마 정보 (호환성 체크용)
    data_schema: Dict = field(default_factory=dict)

    # 그래프 설정 목록
    settings: List[GraphSetting] = field(default_factory=list)

    # 기본 설정 ID
    default_setting_id: Optional[str] = None

    # 메타데이터
    tags: List[str] = field(default_factory=list)
    author: str = ""

    # 파일 경로
    _path: Optional[str] = None

    @classmethod
    def create_new(cls, name: str) -> 'Profile':
        """Create a fresh Profile with a new UUID.

        Input:
            name: Display name for the profile; may be any non-empty string.

        Output:
            A new Profile instance with a freshly generated UUID, both timestamps
            set to the current time, and an empty settings list.

        Raises:
            None.

        Invariants:
            - Returned profile.id is never None or empty.
            - created_at == modified_at immediately after creation.
        """
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            created_at=time.time(),
            modified_at=time.time()
        )

    def add_setting(self, setting: GraphSetting):
        """Append a GraphSetting to this profile.

        Input:
            setting: The GraphSetting to add; must be a valid GraphSetting instance.

        Output:
            None. The setting is appended in-place; modified_at is updated.

        Raises:
            None.

        Invariants:
            - modified_at is always updated to the current time after a successful add.
            - The setting appears at the end of self.settings.
        """
        self.settings.append(setting)
        self.modified_at = time.time()

    def remove_setting(self, setting_id: str) -> bool:
        """Remove a setting by ID from this profile.

        Input:
            setting_id: The UUID of the setting to remove.

        Output:
            True if the setting was found and removed; False if not found.

        Raises:
            None.

        Invariants:
            - If True is returned, the setting no longer appears in self.settings.
            - If the removed setting was the default, default_setting_id is set to None.
            - modified_at is updated only when a setting is actually removed.
        """
        for i, s in enumerate(self.settings):
            if s.id == setting_id:
                self.settings.pop(i)
                self.modified_at = time.time()
                if self.default_setting_id == setting_id:
                    self.default_setting_id = None
                return True
        return False

    def get_setting(self, setting_id: str) -> Optional['GraphSetting']:
        """Look up a setting by its UUID.

        Input:
            setting_id: The UUID of the setting to retrieve.

        Output:
            The matching GraphSetting, or None if no setting with that ID exists.

        Raises:
            None.

        Invariants:
            - Returned object is the same instance stored in self.settings (not a copy).
        """
        for s in self.settings:
            if s.id == setting_id:
                return s
        return None

    def get_setting_by_name(self, name: str) -> Optional['GraphSetting']:
        """Look up the first setting whose name matches.

        Input:
            name: The display name to search for (case-sensitive, exact match).

        Output:
            The first matching GraphSetting, or None if no match exists.
            If multiple settings share the same name, only the first is returned.

        Raises:
            None.

        Invariants:
            - First-match semantics: iteration order of self.settings determines the result.
        """
        for s in self.settings:
            if s.name == name:
                return s
        return None

    def reorder_settings(self, setting_ids: List[str]):
        """Reorder settings according to the given ID sequence.

        Input:
            setting_ids: Ordered list of setting UUIDs defining the new sequence.
                IDs not present in self.settings are silently ignored.
                Settings whose IDs are absent from setting_ids are dropped.

        Output:
            None. self.settings is replaced in-place with the new order.

        Raises:
            None.

        Invariants:
            - After call, len(self.settings) == len(IDs that matched existing settings).
            - modified_at is always updated.
        """
        id_to_setting = {s.id: s for s in self.settings}
        new_settings = []
        for sid in setting_ids:
            if sid in id_to_setting:
                new_settings.append(id_to_setting[sid])
        self.settings = new_settings
        self.modified_at = time.time()

    def to_dict(self) -> Dict:
        """Serialize this profile to a plain dictionary.

        Input:
            None.

        Output:
            Dict with keys: id, name, description, created_at, modified_at,
            data_schema, settings (list of dicts), default_setting_id, tags, author.

        Raises:
            None.

        Invariants:
            - Output is always JSON-serializable (no datetime or custom objects).
        """
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
            'data_schema': self.data_schema,
            'settings': [s.to_dict() for s in self.settings],
            'default_setting_id': self.default_setting_id,
            'tags': self.tags,
            'author': self.author,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Profile':
        """Deserialize a Profile from a plain dictionary.

        Input:
            data: Dict produced by to_dict(). Missing keys receive safe defaults
                (generated UUID for id, current time for timestamps, empty lists/dicts).

        Output:
            A fully initialized Profile instance with all GraphSettings restored.

        Raises:
            None. Missing keys are handled with defaults; no KeyError is raised.

        Invariants:
            - Returned profile.id is never None (defaults to new UUID if absent).
        """
        profile = cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Untitled Profile'),
            description=data.get('description', ''),
            created_at=data.get('created_at', time.time()),
            modified_at=data.get('modified_at', time.time()),
            data_schema=data.get('data_schema', {}),
            default_setting_id=data.get('default_setting_id'),
            tags=data.get('tags', []),
            author=data.get('author', ''),
        )

        # 설정 복원
        settings_data = data.get('settings', [])
        profile.settings = [GraphSetting.from_dict(s) for s in settings_data]

        return profile

    def to_json(self, indent: int = 2) -> str:
        """Serialize this profile to a JSON string.

        Input:
            indent: Number of spaces for JSON indentation; defaults to 2.

        Output:
            JSON string with top-level keys: format_version ('1.0') and profile.

        Raises:
            None.

        Invariants:
            - Output is always valid JSON.
            - Round-trip: Profile.from_json(p.to_json()) produces an equivalent profile.
        """
        file_data = {
            'format_version': '1.0',
            'profile': self.to_dict()
        }
        return json.dumps(file_data, indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'Profile':
        """Deserialize a Profile from a JSON string.

        Input:
            json_str: A JSON string produced by to_json(), or a raw profile dict
                wrapped in the format_version envelope.

        Output:
            A fully initialized Profile instance.

        Raises:
            json.JSONDecodeError: If json_str is not valid JSON.

        Invariants:
            - Handles both the versioned envelope format and bare profile dicts.
        """
        file_data = json.loads(json_str)
        profile_data = file_data.get('profile', file_data)
        return cls.from_dict(profile_data)

    def save(self, path: str):
        """Write this profile to a .dgp file.

        Input:
            path: File path to write to. The .dgp extension is appended automatically
                if not already present.

        Output:
            None. File is written at path; self._path and modified_at are updated.

        Raises:
            OSError: If the file cannot be created or written (permissions, disk full, etc.).

        Invariants:
            - File contents are always valid JSON after a successful save.
            - self._path is updated to the final path (with .dgp extension).
        """
        if not path.endswith('.dgp'):
            path = path + '.dgp'

        self.modified_at = time.time()
        self._path = path

        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> 'Profile':
        """Load a Profile from a .dgp file.

        Input:
            path: Absolute or relative path to a .dgp file.

        Output:
            A fully initialized Profile instance with _path set to path.

        Raises:
            OSError: If the file cannot be opened or read.
            json.JSONDecodeError: If the file contents are not valid JSON.

        Invariants:
            - Returned profile._path is always set to the path argument.
        """
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        profile = cls.from_json(content)
        profile._path = path

        return profile

    def check_compatibility(self, columns: List[str]) -> Dict[str, List[str]]:
        """Check which columns required by this profile are present in a dataset.

        Input:
            columns: List of column names available in the dataset.

        Output:
            Dict with two keys:
            - 'missing': column names required by any setting but absent from columns.
            - 'available': column names required by any setting and present in columns.

        Raises:
            None.

        Invariants:
            - missing ∪ available == all columns referenced across all settings.
            - missing ∩ available == ∅.
        """
        result = {
            'missing': [],
            'available': [],
        }

        # 프로파일에서 사용하는 모든 컬럼 수집
        used_columns: Set[str] = set()
        for setting in self.settings:
            if setting.x_column:
                used_columns.add(setting.x_column)
            for gc in setting.group_columns:
                if 'name' in gc:
                    used_columns.add(gc['name'])
            for vc in setting.value_columns:
                if 'name' in vc:
                    used_columns.add(vc['name'])
            for hc in setting.hover_columns:
                used_columns.add(hc)

        # 호환성 검사
        column_set = set(columns)
        for col in used_columns:
            if col in column_set:
                result['available'].append(col)
            else:
                result['missing'].append(col)

        return result


class ProfileManager:
    """프로파일 매니저"""

    MAX_RECENT_PROFILES = 10
    DEFAULT_PROFILES_DIR = "profiles"

    def __init__(self):
        """Initialize the ProfileManager and set up the profiles directory.

        Output: None
        Invariants: _current is None; _dirty is False; recent profiles are loaded from disk if available
        """
        self._current: Optional[Profile] = None
        self._dirty: bool = False
        self._recent_profiles: List[str] = []
        self._profiles_dir: Optional[Path] = None

        self._setup_profiles_dir()

    def _setup_profiles_dir(self):
        """프로파일 디렉토리 설정"""
        home = os.path.expanduser('~')
        self._profiles_dir = Path(home) / '.data-graph-studio' / self.DEFAULT_PROFILES_DIR
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

        # 최근 프로파일 목록 로드
        self._load_recent_profiles()

    def _load_recent_profiles(self):
        """최근 프로파일 목록 로드"""
        recent_file = self._profiles_dir.parent / 'recent_profiles.json'
        if recent_file.exists():
            try:
                with open(recent_file, 'r', encoding='utf-8') as f:
                    self._recent_profiles = json.load(f)
            except (json.JSONDecodeError, OSError, PermissionError):
                logger.warning("profile.load_recent_profiles.failed", exc_info=True)
                self._recent_profiles = []

    def _save_recent_profiles(self):
        """최근 프로파일 목록 저장"""
        recent_file = self._profiles_dir.parent / 'recent_profiles.json'
        try:
            with open(recent_file, 'w', encoding='utf-8') as f:
                json.dump(self._recent_profiles, f)
        except (OSError, PermissionError):
            logger.warning("profile.save_recent_profiles.failed", exc_info=True)

    @property
    def profiles_dir(self) -> Path:
        """Absolute path to the directory where profiles are stored.

        Output:
            Path object; always an existing directory (created on init if absent).
        """
        return self._profiles_dir

    @property
    def current_profile(self) -> Optional[Profile]:
        """The currently loaded Profile, or None if no profile is open.

        Output:
            Profile instance or None.
        """
        return self._current

    @property
    def is_dirty(self) -> bool:
        """True if the current profile has unsaved changes.

        Output:
            bool. Always False if current_profile is None.
        """
        return self._dirty

    def new_profile(self, name: str = "New Profile") -> Profile:
        """Create and activate a new empty profile.

        Input:
            name: Display name for the new profile; defaults to 'New Profile'.

        Output:
            The newly created Profile, which is now the current profile.

        Raises:
            None.

        Invariants:
            - After call, current_profile is the returned profile.
            - is_dirty is False after this call.
        """
        self._current = Profile.create_new(name)
        self._dirty = False
        return self._current

    def mark_dirty(self):
        """Mark the current profile as having unsaved changes.

        Input:
            None.

        Output:
            None. Sets is_dirty to True.

        Raises:
            None.
        """
        self._dirty = True

    def save(self, path: Optional[str] = None):
        """Save the current profile to disk.

        Input:
            path: Optional file path override. If None, uses the profile's existing
                _path or a default path in profiles_dir.

        Output:
            None. Profile is written to disk; is_dirty is set to False.

        Raises:
            OSError: If the file cannot be created or written.

        Invariants:
            - is_dirty is False after a successful save.
            - The saved path is added to recent profiles.
        """
        if not self._current:
            return

        if path is None:
            path = self._current._path

        if path is None:
            # 기본 경로 사용
            safe_name = "".join(c for c in self._current.name if c.isalnum() or c in "._- ")
            path = str(self._profiles_dir / f"{safe_name}.dgp")

        self._current.save(path)
        self._dirty = False

        self._add_recent_profile(path)

    def load(self, path: str) -> Profile:
        """Load a profile from disk and set it as the current profile.

        Input:
            path: Absolute or relative path to a .dgp file.

        Output:
            The loaded Profile, which is now the current profile.

        Raises:
            OSError: If the file cannot be read.
            json.JSONDecodeError: If the file is not valid JSON.

        Invariants:
            - current_profile is updated to the loaded profile.
            - is_dirty is False after a successful load.
            - The path is added to recent profiles.
        """
        self._current = Profile.load(path)
        self._dirty = False
        self._add_recent_profile(path)
        return self._current

    def _add_recent_profile(self, path: str):
        """최근 프로파일 추가"""
        if path in self._recent_profiles:
            self._recent_profiles.remove(path)

        self._recent_profiles.insert(0, path)
        self._recent_profiles = self._recent_profiles[:self.MAX_RECENT_PROFILES]

        self._save_recent_profiles()

    def get_recent_profiles(self) -> List[str]:
        """Return the list of recently accessed profile file paths.

        Output:
            List of path strings, most recently used first.
            Returns [] if no recent profiles exist.

        Raises:
            None.
        """
        return self._recent_profiles.copy()

    def list_profiles(self) -> List[Path]:
        """Return all .dgp files found in the profiles directory.

        Output:
            Sorted list of Path objects for all .dgp files in profiles_dir.
            Returns [] if no profiles exist.

        Raises:
            None.
        """
        if self._profiles_dir.exists():
            return sorted(self._profiles_dir.glob("*.dgp"))
        return []

    def delete_profile(self, path: str) -> bool:
        """Delete a .dgp profile file from disk.

        Input:
            path: Absolute or relative path to the .dgp file to delete.

        Output:
            True if the file was deleted; False if the file did not exist.

        Raises:
            (OSError, PermissionError): If the file exists but cannot be deleted.

        Invariants:
            - If True is returned, the file no longer exists at path.
        """
        try:
            if os.path.exists(path):
                os.remove(path)
                if path in self._recent_profiles:
                    self._recent_profiles.remove(path)
                    self._save_recent_profiles()
                return True
        except (OSError, PermissionError):
            logger.warning("profile.delete_profile.failed", extra={"path": path}, exc_info=True)
        return False

    def close_profile(self) -> bool:
        """Close the currently open profile without saving.

        Output:
            True if the profile was open and closed successfully.
            False if the profile has unsaved changes (caller should save first).

        Raises:
            None.

        Invariants:
            - If True is returned, current_profile is None and is_dirty is False.
            - If False is returned due to dirty state, current_profile is unchanged.
        """
        if self._dirty:
            return False

        self._current = None
        self._dirty = False
        return True

    def add_setting_to_current(self, setting: GraphSetting):
        """Add a GraphSetting to the current profile.

        Input:
            setting: The GraphSetting to add.

        Output:
            None.

        Raises:
            None. If no profile is currently open, the call is a silent no-op.

        Invariants:
            - If current_profile is not None, is_dirty is True after a successful add.
            - If current_profile is None, this method is a no-op.
        """
        if self._current:
            self._current.add_setting(setting)
            self._dirty = True

    def remove_setting_from_current(self, setting_id: str) -> bool:
        """Remove a setting from the current profile by ID.

        Input:
            setting_id: UUID of the setting to remove.

        Output:
            True if removed; False if setting_id not found in current profile.

        Raises:
            None. Returns False if no profile is currently open.

        Invariants:
            - If True is returned, setting is no longer in current_profile.settings.
        """
        if self._current:
            result = self._current.remove_setting(setting_id)
            if result:
                self._dirty = True
            return result
        return False
