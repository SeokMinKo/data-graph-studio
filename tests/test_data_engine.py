"""
Data Engine 테스트
"""

import pytest
import tempfile
import os

from data_graph_studio.core.data_engine import DataEngine, FileType, LoadingProgress


class TestDataEngine:
    """DataEngine 클래스 테스트"""
    
    @pytest.fixture
    def engine(self):
        return DataEngine()
    
    @pytest.fixture
    def sample_csv(self):
        """샘플 CSV 파일 생성"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("id,name,value,category\n")
            for i in range(1000):
                f.write(f"{i},item_{i},{i * 1.5},{['A', 'B', 'C'][i % 3]}\n")
            return f.name
    
    def test_init(self, engine):
        """초기화 테스트"""
        assert engine.df is None
        assert engine.is_loaded is False
        assert engine.row_count == 0
        assert engine.column_count == 0
    
    def test_detect_file_type(self, engine):
        """파일 타입 감지 테스트"""
        assert engine.detect_file_type("test.csv") == FileType.CSV
        assert engine.detect_file_type("test.tsv") == FileType.TSV
        assert engine.detect_file_type("test.xlsx") == FileType.EXCEL
        assert engine.detect_file_type("test.parquet") == FileType.PARQUET
        assert engine.detect_file_type("test.json") == FileType.JSON
    
    def test_load_csv(self, engine, sample_csv):
        """CSV 로드 테스트"""
        success = engine.load_file(sample_csv)
        
        assert success is True
        assert engine.is_loaded is True
        assert engine.row_count == 1000
        assert engine.column_count == 4
        assert engine.columns == ['id', 'name', 'value', 'category']
        
        # Cleanup
        os.unlink(sample_csv)
    
    def test_filter(self, engine, sample_csv):
        """필터링 테스트"""
        engine.load_file(sample_csv)
        
        # 값 필터
        result = engine.filter('id', 'gt', 500)
        assert len(result) == 499
        
        # 문자열 필터
        result = engine.filter('category', 'eq', 'A')
        assert len(result) == 334  # 1000 / 3 ≈ 333
        
        os.unlink(sample_csv)
    
    def test_sort(self, engine, sample_csv):
        """정렬 테스트"""
        engine.load_file(sample_csv)
        
        result = engine.sort(['value'], descending=True)
        assert result['value'][0] == 1498.5  # (999 * 1.5)
        
        os.unlink(sample_csv)
    
    def test_group_aggregate(self, engine, sample_csv):
        """그룹 집계 테스트"""
        engine.load_file(sample_csv)
        
        result = engine.group_aggregate(
            ['category'],
            ['value'],
            ['sum']
        )
        
        assert len(result) == 3  # A, B, C
        assert 'value_sum' in result.columns
        
        os.unlink(sample_csv)
    
    def test_statistics(self, engine, sample_csv):
        """통계 테스트"""
        engine.load_file(sample_csv)
        
        stats = engine.get_statistics('value')
        
        assert 'count' in stats
        assert 'mean' in stats
        assert 'min' in stats
        assert 'max' in stats
        assert stats['count'] == 1000
        assert stats['min'] == 0.0
        assert stats['max'] == 1498.5
        
        os.unlink(sample_csv)
    
    def test_sample(self, engine, sample_csv):
        """샘플링 테스트"""
        engine.load_file(sample_csv)
        
        result = engine.sample(n=100)
        assert len(result) == 100
        
        os.unlink(sample_csv)
    
    def test_slice(self, engine, sample_csv):
        """슬라이스 테스트 (가상 스크롤용)"""
        engine.load_file(sample_csv)
        
        result = engine.get_slice(100, 200)
        assert len(result) == 100
        
        os.unlink(sample_csv)
    
    def test_search(self, engine, sample_csv):
        """검색 테스트"""
        engine.load_file(sample_csv)
        
        result = engine.search('item_10')
        assert len(result) > 0
        
        os.unlink(sample_csv)
    
    def test_memory_optimization(self, engine, sample_csv):
        """메모리 최적화 테스트"""
        engine.load_file(sample_csv, optimize_memory=True)
        
        # 프로파일 확인
        assert engine.profile is not None
        assert engine.profile.total_rows == 1000
        assert engine.profile.memory_bytes > 0
        
        os.unlink(sample_csv)


class TestLoadingProgress:
    """LoadingProgress 클래스 테스트"""
    
    def test_progress_percent(self):
        progress = LoadingProgress(total_bytes=1000, loaded_bytes=500)
        assert progress.progress_percent == 50.0
    
    def test_progress_percent_zero(self):
        progress = LoadingProgress(total_bytes=0, loaded_bytes=0)
        assert progress.progress_percent == 0.0
    
    def test_eta(self):
        progress = LoadingProgress(
            total_bytes=1000, 
            loaded_bytes=500,
            elapsed_seconds=5.0
        )
        # 500 bytes in 5 seconds = 100 bytes/sec
        # 500 remaining / 100 = 5 seconds
        assert progress.eta_seconds == 5.0
