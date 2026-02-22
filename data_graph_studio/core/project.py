"""
Project Save/Load - .dgs file format
"""

import logging
import os
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DataSourceRef:
    """데이터 소스 참조"""
    path: str
    file_type: str
    encoding: str = "utf-8"
    delimiter: str = ","
    has_header: bool = True
    sheet_name: Optional[str] = None
    dataset_id: Optional[str] = None  # Multi-dataset support
    name: Optional[str] = None  # Display name
    color: Optional[str] = None  # Chart color
    is_active: bool = False  # Active dataset flag

    @property
    def is_absolute(self) -> bool:
        """절대 경로 여부"""
        if os.path.isabs(self.path):
            return True
        # Windows drive letter paths (e.g., C:/foo or C:\foo)
        if len(self.path) >= 3 and self.path[1] == ':' and (self.path[2] == '/' or self.path[2] == '\\'):
            return True
        return False

    def resolve(self, base_dir: str) -> str:
        """상대 경로를 절대 경로로 변환"""
        if self.is_absolute:
            return self.path
        return os.path.join(base_dir, self.path)

    def to_dict(self) -> Dict:
        """Serialize this data source reference to a dictionary."""
        return {
            'path': self.path,
            'file_type': self.file_type,
            'encoding': self.encoding,
            'delimiter': self.delimiter,
            'has_header': self.has_header,
            'sheet_name': self.sheet_name,
            'dataset_id': self.dataset_id,
            'name': self.name,
            'color': self.color,
            'is_active': self.is_active,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'DataSourceRef':
        """Deserialize a DataSourceRef from a dictionary produced by to_dict."""
        return cls(
            path=data['path'],
            file_type=data['file_type'],
            encoding=data.get('encoding', 'utf-8'),
            delimiter=data.get('delimiter', ','),
            has_header=data.get('has_header', True),
            sheet_name=data.get('sheet_name'),
            dataset_id=data.get('dataset_id'),
            name=data.get('name'),
            color=data.get('color'),
            is_active=data.get('is_active', False),
        )


@dataclass
class ComparisonState:
    """비교 상태 저장"""
    mode: str = "single"  # single, overlay, side_by_side, difference
    comparison_datasets: List[str] = field(default_factory=list)
    key_column: Optional[str] = None
    sync_scroll: bool = True
    sync_zoom: bool = True

    def to_dict(self) -> Dict:
        """Serialize this comparison state to a dictionary."""
        return {
            'mode': self.mode,
            'comparison_datasets': self.comparison_datasets,
            'key_column': self.key_column,
            'sync_scroll': self.sync_scroll,
            'sync_zoom': self.sync_zoom,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ComparisonState':
        """Deserialize a ComparisonState from a dictionary produced by to_dict."""
        return cls(
            mode=data.get('mode', 'single'),
            comparison_datasets=data.get('comparison_datasets', []),
            key_column=data.get('key_column'),
            sync_scroll=data.get('sync_scroll', True),
            sync_zoom=data.get('sync_zoom', True),
        )


@dataclass
class Project:
    """프로젝트"""
    name: str
    version: str = "1.1"  # Version bump for multi-dataset support
    author: str = ""
    description: str = ""
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)

    # 데이터 소스 (단일 - 호환성)
    data_source: Optional[DataSourceRef] = None

    # 다중 데이터 소스 (멀티 데이터셋 지원)
    data_sources: List[DataSourceRef] = field(default_factory=list)

    # 비교 상태
    comparison_state: Optional[ComparisonState] = None

    # 앱 상태
    state: Dict[str, Any] = field(default_factory=dict)

    # 대시보드
    dashboards: List[Dict] = field(default_factory=list)

    # 계산 필드
    calculated_fields: List[Dict] = field(default_factory=list)

    # 프로파일 (GraphSetting.to_dict() 형태)
    profiles: List[Dict] = field(default_factory=list)

    # 테마
    theme: str = "midnight"

    # 저장 경로
    _path: Optional[str] = None

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'created_at': self.created_at,
            'modified_at': self.modified_at,
            'data_source': self.data_source.to_dict() if self.data_source else None,
            'data_sources': [ds.to_dict() for ds in self.data_sources],
            'comparison_state': self.comparison_state.to_dict() if self.comparison_state else None,
            'state': self.state,
            'dashboards': self.dashboards,
            'calculated_fields': self.calculated_fields,
            'profiles': self.profiles,
            'theme': self.theme,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Project':
        """딕셔너리에서 복원"""
        project = cls(
            name=data['name'],
            version=data.get('version', '1.0'),
            author=data.get('author', ''),
            description=data.get('description', ''),
            created_at=data.get('created_at', time.time()),
            modified_at=data.get('modified_at', time.time()),
        )

        # 단일 데이터 소스 (레거시 지원)
        if data.get('data_source'):
            project.data_source = DataSourceRef.from_dict(data['data_source'])

        # 다중 데이터 소스
        if data.get('data_sources'):
            project.data_sources = [
                DataSourceRef.from_dict(ds) for ds in data['data_sources']
            ]
        # 레거시 프로젝트에서 data_source를 data_sources로 마이그레이션
        elif project.data_source and not project.data_sources:
            project.data_sources = [project.data_source]

        # 비교 상태
        if data.get('comparison_state'):
            project.comparison_state = ComparisonState.from_dict(data['comparison_state'])

        project.state = data.get('state', {})
        project.dashboards = data.get('dashboards', [])
        project.calculated_fields = data.get('calculated_fields', [])
        project.profiles = data.get('profiles', [])
        project.theme = data.get('theme', 'midnight')

        return project

    def add_data_source(self, source: DataSourceRef):
        """데이터 소스 추가"""
        self.data_sources.append(source)
        # 첫 번째면 레거시 호환성을 위해 data_source에도 설정
        if len(self.data_sources) == 1:
            self.data_source = source

    def remove_data_source(self, dataset_id: str) -> bool:
        """데이터 소스 제거"""
        for i, ds in enumerate(self.data_sources):
            if ds.dataset_id == dataset_id:
                self.data_sources.pop(i)
                if self.data_source and self.data_source.dataset_id == dataset_id:
                    self.data_source = self.data_sources[0] if self.data_sources else None
                return True
        return False

    def get_data_source(self, dataset_id: str) -> Optional[DataSourceRef]:
        """데이터 소스 가져오기"""
        for ds in self.data_sources:
            if ds.dataset_id == dataset_id:
                return ds
        return None

    def get_all_data_sources(self) -> List[DataSourceRef]:
        """모든 데이터 소스 반환"""
        return self.data_sources.copy()
    
    def to_json(self, indent: int = 2) -> str:
        """JSON 문자열로 변환"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Project':
        """JSON에서 복원"""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def save(self, path: str):
        """파일로 저장"""
        # .dgs 확장자 보장
        if not path.endswith('.dgs'):
            path = path + '.dgs'

        self.modified_at = time.time()
        self._path = path

        logger.debug("project.save", extra={"path": path, "name": self.name})
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())
    
    @classmethod
    def load(cls, path: str) -> 'Project':
        """파일에서 로드"""
        logger.debug("project.load", extra={"path": path})
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        project = cls.from_json(content)
        project._path = path

        return project
    
    def validate(self) -> List[str]:
        """유효성 검사"""
        errors = []

        # 모든 데이터 소스 검증
        for ds in self.data_sources:
            path = ds.path
            if self._path:
                base_dir = os.path.dirname(self._path)
                path = ds.resolve(base_dir)

            if not os.path.exists(path):
                name = ds.name or ds.path
                errors.append(f"Data source file not found: {name} ({path})")

        # 레거시 단일 소스 검증 (data_sources가 비어있는 경우)
        if not self.data_sources and self.data_source:
            path = self.data_source.path
            if self._path:
                base_dir = os.path.dirname(self._path)
                path = self.data_source.resolve(base_dir)

            if not os.path.exists(path):
                errors.append(f"Data source file not found: {path}")

        return errors


class ProjectManager:
    """프로젝트 매니저"""
    
    MAX_RECENT_FILES = 10
    
    def __init__(self):
        self._current: Optional[Project] = None
        self._dirty: bool = False
        self._recent_files: List[str] = []
        self._autosave_path: Optional[str] = None
    
    @property
    def current_project(self) -> Optional[Project]:
        """현재 프로젝트"""
        return self._current
    
    @property
    def is_dirty(self) -> bool:
        """수정 여부"""
        return self._dirty
    
    def new_project(self, name: str = "Untitled") -> Project:
        """새 프로젝트 생성"""
        self._current = Project(name=name)
        self._dirty = False
        return self._current
    
    def mark_dirty(self):
        """수정됨으로 표시"""
        self._dirty = True
    
    def save(self, path: Optional[str] = None):
        """저장"""
        if not self._current:
            logger.warning("project_manager.save.no_project")
            return

        if path is None:
            path = self._current._path

        if path is None:
            raise ValueError("No path specified")

        logger.debug("project_manager.save", extra={"path": path})
        self._current.save(path)
        self._dirty = False

        self._add_recent_file(path)
    
    def load(self, path: str) -> Project:
        """로드"""
        logger.debug("project_manager.load", extra={"path": path})
        self._current = Project.load(path)
        self._dirty = False
        self._add_recent_file(path)
        return self._current
    
    def _add_recent_file(self, path: str):
        """최근 파일 추가"""
        # 이미 있으면 제거
        if path in self._recent_files:
            self._recent_files.remove(path)
        
        # 앞에 추가
        self._recent_files.insert(0, path)
        
        # 최대 개수 유지
        self._recent_files = self._recent_files[:self.MAX_RECENT_FILES]
    
    def get_recent_files(self) -> List[str]:
        """최근 파일 목록"""
        return self._recent_files.copy()
    
    def clear_recent_files(self):
        """최근 파일 클리어"""
        self._recent_files.clear()
    
    def get_autosave_path(self) -> Optional[str]:
        """자동 저장 경로"""
        if self._autosave_path:
            return self._autosave_path
        
        # 기본 경로
        home = os.path.expanduser('~')
        autosave_dir = os.path.join(home, '.data-graph-studio', 'autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        
        return os.path.join(autosave_dir, 'autosave.dgs')
    
    def autosave(self):
        """자동 저장"""
        if not self._current:
            return
        
        path = self.get_autosave_path()
        if path:
            self._current.save(path)
    
    def recover_autosave(self, path: str) -> Optional[Project]:
        """자동 저장에서 복구"""
        if os.path.exists(path):
            return Project.load(path)
        return None
    
    def close_project(self) -> bool:
        """프로젝트 닫기"""
        if self._dirty:
            logger.warning("project_manager.close_project.unsaved_changes")
            return False

        logger.debug("project_manager.close_project")
        self._current = None
        self._dirty = False
        return True
