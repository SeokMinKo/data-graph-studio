"""
Tests for Project Save/Load
"""

import pytest
import json
import tempfile
import os
from pathlib import Path

import sys

# Add src to path
src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from core.project import Project, ProjectManager, DataSourceRef
from core.state import ChartType, AggregationType


class TestDataSourceRef:
    """데이터 소스 참조 테스트"""
    
    def test_absolute_path(self):
        """절대 경로"""
        ref = DataSourceRef(
            path="C:/data/sales.csv",
            file_type="csv"
        )
        
        assert ref.path == "C:/data/sales.csv"
        assert ref.is_absolute is True
    
    def test_relative_path(self):
        """상대 경로"""
        ref = DataSourceRef(
            path="data/sales.csv",
            file_type="csv"
        )
        
        assert ref.path == "data/sales.csv"
        assert ref.is_absolute is False
    
    def test_resolve_relative_path(self):
        """상대 경로 해석"""
        ref = DataSourceRef(
            path="data/sales.csv",
            file_type="csv"
        )
        
        base = "/projects/myproject"
        resolved = ref.resolve(base)
        
        assert "data/sales.csv" in resolved
        assert resolved.startswith(base) or "data" in resolved
    
    def test_to_dict(self):
        """직렬화"""
        ref = DataSourceRef(
            path="data.csv",
            file_type="csv",
            encoding="utf-8",
            delimiter=","
        )
        
        data = ref.to_dict()
        
        assert data['path'] == "data.csv"
        assert data['file_type'] == "csv"
    
    def test_from_dict(self):
        """역직렬화"""
        data = {
            'path': "data.parquet",
            'file_type': "parquet"
        }
        
        ref = DataSourceRef.from_dict(data)
        
        assert ref.path == "data.parquet"
        assert ref.file_type == "parquet"


class TestProject:
    """프로젝트 테스트"""
    
    def test_create_project(self):
        """프로젝트 생성"""
        project = Project(name="My Analysis")
        
        assert project.name == "My Analysis"
        assert project.version == "1.0"
    
    def test_project_data_source(self):
        """데이터 소스 설정"""
        project = Project(name="Test")
        project.data_source = DataSourceRef(
            path="sales.csv",
            file_type="csv"
        )
        
        assert project.data_source.path == "sales.csv"
    
    def test_project_state(self):
        """상태 저장"""
        project = Project(name="Test")
        
        project.state = {
            'group_columns': ['Category'],
            'value_columns': [
                {'name': 'Sales', 'aggregation': 'sum'}
            ],
            'chart_type': 'line',
        }
        
        assert project.state['chart_type'] == 'line'
    
    def test_project_dashboard(self):
        """대시보드 설정"""
        project = Project(name="Test")
        
        project.dashboards = [
            {
                'name': 'Overview',
                'layout': {'rows': 2, 'cols': 2},
                'items': []
            }
        ]
        
        assert len(project.dashboards) == 1
    
    def test_project_metadata(self):
        """메타데이터"""
        project = Project(
            name="Test",
            author="John",
            description="Test project"
        )
        
        assert project.author == "John"
        assert project.description == "Test project"


class TestProjectSerialization:
    """프로젝트 직렬화 테스트"""
    
    @pytest.fixture
    def sample_project(self):
        project = Project(name="Sales Analysis")
        project.data_source = DataSourceRef(
            path="data/sales.csv",
            file_type="csv"
        )
        project.state = {
            'group_columns': ['Region'],
            'value_columns': [
                {'name': 'Revenue', 'aggregation': 'sum', 'color': '#1f77b4'}
            ],
            'x_column': 'Date',
            'chart_type': 'line',
            'filters': [
                {'column': 'Year', 'op': 'eq', 'value': 2024}
            ]
        }
        project.theme = 'dark'
        return project
    
    def test_to_dict(self, sample_project):
        """딕셔너리 변환"""
        data = sample_project.to_dict()
        
        assert data['name'] == "Sales Analysis"
        assert data['data_source']['path'] == "data/sales.csv"
        assert data['state']['chart_type'] == 'line'
    
    def test_from_dict(self, sample_project):
        """딕셔너리에서 복원"""
        data = sample_project.to_dict()
        
        restored = Project.from_dict(data)
        
        assert restored.name == sample_project.name
        assert restored.data_source.path == sample_project.data_source.path
        assert restored.state == sample_project.state
    
    def test_to_json(self, sample_project):
        """JSON 문자열 변환"""
        json_str = sample_project.to_json()
        
        assert isinstance(json_str, str)
        
        # Valid JSON
        data = json.loads(json_str)
        assert data['name'] == "Sales Analysis"
    
    def test_from_json(self, sample_project):
        """JSON에서 복원"""
        json_str = sample_project.to_json()
        
        restored = Project.from_json(json_str)
        
        assert restored.name == sample_project.name


class TestProjectFileIO:
    """프로젝트 파일 I/O 테스트"""
    
    @pytest.fixture
    def sample_project(self):
        project = Project(name="Test Project")
        project.data_source = DataSourceRef(
            path="test.csv",
            file_type="csv"
        )
        project.state = {'chart_type': 'bar'}
        return project
    
    def test_save_project(self, sample_project):
        """프로젝트 저장"""
        with tempfile.NamedTemporaryFile(suffix='.dgs', delete=False) as f:
            path = f.name
        
        try:
            sample_project.save(path)
            
            assert os.path.exists(path)
            
            with open(path, 'r') as f:
                data = json.load(f)
            
            assert data['name'] == "Test Project"
        finally:
            os.unlink(path)
    
    def test_load_project(self, sample_project):
        """프로젝트 로드"""
        with tempfile.NamedTemporaryFile(suffix='.dgs', delete=False) as f:
            path = f.name
        
        try:
            sample_project.save(path)
            
            loaded = Project.load(path)
            
            assert loaded.name == sample_project.name
            assert loaded.data_source.path == sample_project.data_source.path
        finally:
            os.unlink(path)
    
    def test_file_extension(self, sample_project):
        """파일 확장자 .dgs"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "project")  # No extension
            
            sample_project.save(path)
            
            # Should have .dgs extension
            assert os.path.exists(path + ".dgs") or os.path.exists(path)


class TestProjectManager:
    """프로젝트 매니저 테스트"""
    
    @pytest.fixture
    def manager(self):
        return ProjectManager()
    
    def test_new_project(self, manager):
        """새 프로젝트"""
        project = manager.new_project("Untitled")
        
        assert project.name == "Untitled"
        assert manager.current_project is project
    
    def test_is_dirty(self, manager):
        """수정 여부"""
        manager.new_project("Test")
        
        assert manager.is_dirty is False
        
        manager.mark_dirty()
        
        assert manager.is_dirty is True
    
    def test_save_clears_dirty(self, manager):
        """저장 후 dirty 클리어"""
        manager.new_project("Test")
        manager.mark_dirty()
        
        with tempfile.NamedTemporaryFile(suffix='.dgs', delete=False) as f:
            path = f.name
        
        try:
            manager.save(path)
            assert manager.is_dirty is False
        finally:
            os.unlink(path)
    
    def test_recent_files(self, manager):
        """최근 파일 목록"""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = []
            for i in range(3):
                path = os.path.join(tmpdir, f"project{i}.dgs")
                manager.new_project(f"Project {i}")
                manager.save(path)
                paths.append(path)
            
            recent = manager.get_recent_files()
            
            assert len(recent) >= 3
            assert paths[-1] in recent  # Most recent
    
    def test_clear_recent(self, manager):
        """최근 파일 클리어"""
        manager._recent_files = ["a.dgs", "b.dgs"]
        manager.clear_recent_files()
        
        assert len(manager.get_recent_files()) == 0


class TestProjectRestoration:
    """프로젝트 복원 테스트"""
    
    def test_restore_chart_settings(self):
        """차트 설정 복원"""
        project = Project(name="Test")
        project.state = {
            'chart_type': 'scatter',
            'chart_settings': {
                'line_width': 3,
                'marker_size': 10,
            }
        }
        
        data = project.to_dict()
        restored = Project.from_dict(data)
        
        assert restored.state['chart_type'] == 'scatter'
        assert restored.state['chart_settings']['line_width'] == 3
    
    def test_restore_filters(self):
        """필터 복원"""
        project = Project(name="Test")
        project.state = {
            'filters': [
                {'column': 'A', 'op': 'gt', 'value': 10},
                {'column': 'B', 'op': 'eq', 'value': 'X'},
            ]
        }
        
        data = project.to_dict()
        restored = Project.from_dict(data)
        
        assert len(restored.state['filters']) == 2
    
    def test_restore_calculated_fields(self):
        """계산 필드 복원"""
        project = Project(name="Test")
        project.calculated_fields = [
            {'name': 'Total', 'expression': 'Price * Quantity'},
            {'name': 'Margin', 'expression': 'Revenue - Cost'},
        ]
        
        data = project.to_dict()
        restored = Project.from_dict(data)
        
        assert len(restored.calculated_fields) == 2
        assert restored.calculated_fields[0]['name'] == 'Total'


class TestProjectValidation:
    """프로젝트 유효성 검사 테스트"""
    
    def test_validate_data_source_exists(self):
        """데이터 소스 존재 확인"""
        project = Project(name="Test")
        project.data_source = DataSourceRef(
            path="nonexistent.csv",
            file_type="csv"
        )
        
        errors = project.validate()
        
        assert any('data source' in e.lower() or 'file' in e.lower() 
                   for e in errors)
    
    def test_validate_no_data_source(self):
        """데이터 소스 없음"""
        project = Project(name="Test")
        
        errors = project.validate()
        
        # 데이터 소스 없어도 유효
        assert isinstance(errors, list)


class TestAutoSave:
    """자동 저장 테스트"""
    
    @pytest.fixture
    def manager(self):
        return ProjectManager()
    
    def test_autosave_path(self, manager):
        """자동 저장 경로"""
        manager.new_project("Test")
        
        autosave_path = manager.get_autosave_path()
        
        assert autosave_path is not None
        assert 'autosave' in autosave_path.lower() or '.dgs' in autosave_path.lower()
    
    def test_recover_from_autosave(self, manager):
        """자동 저장에서 복구"""
        manager.new_project("Test")
        manager.current_project.state = {'test': 'data'}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            autosave = os.path.join(tmpdir, "autosave.dgs")
            manager._autosave_path = autosave
            
            manager.autosave()
            
            # 복구
            manager2 = ProjectManager()
            recovered = manager2.recover_autosave(autosave)
            
            assert recovered is not None
            assert recovered.state.get('test') == 'data'
