"""
Graph Profiles - 그래프 설정 프로파일 관리
"""

import os
import json
import time
import uuid
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
import dataclasses


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
    version: int = 1
    schema_version: int = 1
    chart_type: str = ""
    x_column: Optional[str] = None
    group_columns: Tuple = ()
    value_columns: Tuple = ()
    hover_columns: Tuple[str, ...] = ()
    filters: Tuple = ()
    sorts: Tuple = ()
    chart_settings: Dict = None
    include_filters: bool = False
    include_sorts: bool = False
    icon: str = "📊"
    description: str = ""
    is_favorite: bool = False
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)

    # Current schema version for migration
    CURRENT_VERSION: int = field(default=1, init=False, repr=False, compare=False)

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
        """새 GraphSetting 생성"""
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            dataset_id=dataset_id,
            icon=icon,
        )

    def normalized_chart_settings(self) -> Dict:
        """Return chart_settings as a plain dict with defaults filled in.

        Used for reliable equality comparison.
        """
        defaults = {
            "show_legend": True,
            "show_grid": True,
            "show_markers": False,
            "line_width": 2,
            "marker_size": 6,
            "opacity": 1.0,
            "color_palette": "default",
        }
        result = dict(defaults)
        if self.chart_settings:
            result.update(dict(self.chart_settings))
        return result

    def with_name(self, name: str) -> 'GraphSetting':
        return dataclasses.replace(self, name=name, modified_at=time.time())

    def update_modified(self) -> 'GraphSetting':
        """수정 시간 업데이트한 새 인스턴스 반환 (frozen이므로 replace 사용)"""
        return dataclasses.replace(self, modified_at=time.time())

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "dataset_id": self.dataset_id,
            "version": self.version,
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
        """Deserialize from dict with version migration support."""
        data = cls._migrate(dict(data))
        return cls(
            id=data["id"],
            name=data["name"],
            dataset_id=data.get("dataset_id", ""),
            version=data.get("version", 1),
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

    @classmethod
    def _migrate(cls, data: Dict) -> Dict:
        """Apply version migrations sequentially.

        Each migration function takes a dict and returns a dict.
        Add new migrations as ``_migrate_vN_to_vM`` class methods.
        """
        version = data.get("version", 0)
        # Migration v0 → v1: add version field (no-op, just stamp)
        if version < 1:
            data["version"] = 1
        # Future migrations go here:
        # if version < 2:
        #     data = cls._migrate_v1_to_v2(data)
        #     data["version"] = 2
        return data


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
        """새 프로파일 생성"""
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            created_at=time.time(),
            modified_at=time.time()
        )

    def add_setting(self, setting: GraphSetting):
        """설정 추가"""
        self.settings.append(setting)
        self.modified_at = time.time()

    def remove_setting(self, setting_id: str) -> bool:
        """설정 제거"""
        for i, s in enumerate(self.settings):
            if s.id == setting_id:
                self.settings.pop(i)
                self.modified_at = time.time()
                if self.default_setting_id == setting_id:
                    self.default_setting_id = None
                return True
        return False

    def get_setting(self, setting_id: str) -> Optional[GraphSetting]:
        """설정 가져오기"""
        for s in self.settings:
            if s.id == setting_id:
                return s
        return None

    def get_setting_by_name(self, name: str) -> Optional[GraphSetting]:
        """이름으로 설정 가져오기"""
        for s in self.settings:
            if s.name == name:
                return s
        return None

    def reorder_settings(self, setting_ids: List[str]):
        """설정 순서 변경"""
        id_to_setting = {s.id: s for s in self.settings}
        new_settings = []
        for sid in setting_ids:
            if sid in id_to_setting:
                new_settings.append(id_to_setting[sid])
        self.settings = new_settings
        self.modified_at = time.time()

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
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
        """딕셔너리에서 복원"""
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
        """JSON 문자열로 변환"""
        file_data = {
            'format_version': '1.0',
            'profile': self.to_dict()
        }
        return json.dumps(file_data, indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'Profile':
        """JSON에서 복원"""
        file_data = json.loads(json_str)
        profile_data = file_data.get('profile', file_data)
        return cls.from_dict(profile_data)

    def save(self, path: str):
        """파일로 저장"""
        if not path.endswith('.dgp'):
            path = path + '.dgp'

        self.modified_at = time.time()
        self._path = path

        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> 'Profile':
        """파일에서 로드"""
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        profile = cls.from_json(content)
        profile._path = path

        return profile

    def check_compatibility(self, columns: List[str]) -> Dict[str, List[str]]:
        """
        데이터 컬럼과 프로파일 호환성 검사

        Returns:
            Dict with 'missing' and 'available' column lists
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
            except Exception:
                self._recent_profiles = []

    def _save_recent_profiles(self):
        """최근 프로파일 목록 저장"""
        recent_file = self._profiles_dir.parent / 'recent_profiles.json'
        try:
            with open(recent_file, 'w', encoding='utf-8') as f:
                json.dump(self._recent_profiles, f)
        except Exception:
            pass

    @property
    def profiles_dir(self) -> Path:
        """프로파일 디렉토리"""
        return self._profiles_dir

    @property
    def current_profile(self) -> Optional[Profile]:
        """현재 프로파일"""
        return self._current

    @property
    def is_dirty(self) -> bool:
        """수정 여부"""
        return self._dirty

    def new_profile(self, name: str = "New Profile") -> Profile:
        """새 프로파일 생성"""
        self._current = Profile.create_new(name)
        self._dirty = False
        return self._current

    def mark_dirty(self):
        """수정됨으로 표시"""
        self._dirty = True

    def save(self, path: Optional[str] = None):
        """저장"""
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
        """로드"""
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
        """최근 프로파일 목록"""
        return self._recent_profiles.copy()

    def list_profiles(self) -> List[Path]:
        """프로파일 디렉토리의 모든 프로파일 목록"""
        if self._profiles_dir.exists():
            return sorted(self._profiles_dir.glob("*.dgp"))
        return []

    def delete_profile(self, path: str) -> bool:
        """프로파일 삭제 (send2trash 사용, fallback: os.remove)"""
        try:
            if os.path.exists(path):
                try:
                    from send2trash import send2trash  # type: ignore
                    send2trash(path)
                except ImportError:
                    import logging
                    logging.getLogger(__name__).info(
                        "send2trash not installed, using os.remove for %s", path
                    )
                    os.remove(path)
                if path in self._recent_profiles:
                    self._recent_profiles.remove(path)
                    self._save_recent_profiles()
                return True
        except Exception:
            pass
        return False

    def close_profile(self) -> bool:
        """프로파일 닫기"""
        if self._dirty:
            return False

        self._current = None
        self._dirty = False
        return True

    def add_setting_to_current(self, setting: GraphSetting):
        """현재 프로파일에 설정 추가"""
        if self._current:
            self._current.add_setting(setting)
            self._dirty = True

    def remove_setting_from_current(self, setting_id: str) -> bool:
        """현재 프로파일에서 설정 제거"""
        if self._current:
            result = self._current.remove_setting(setting_id)
            if result:
                self._dirty = True
            return result
        return False
