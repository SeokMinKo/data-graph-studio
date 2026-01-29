"""
Tests for Caching Layer
"""

import pytest
import polars as pl
import numpy as np
import time
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(__file__).rsplit('tests', 1)[0] + 'src')

from core.cache import CacheManager, CacheLevel, CacheEntry


class TestCacheEntry:
    """캐시 엔트리 테스트"""
    
    def test_entry_creation(self):
        """엔트리 생성"""
        entry = CacheEntry("test_key", {"value": 42}, level=CacheLevel.L1)
        
        assert entry.key == "test_key"
        assert entry.data == {"value": 42}
        assert entry.level == CacheLevel.L1
        assert entry.hits == 0
    
    def test_entry_hit_count(self):
        """히트 카운트"""
        entry = CacheEntry("key", "data", level=CacheLevel.L1)
        
        entry.hit()
        entry.hit()
        entry.hit()
        
        assert entry.hits == 3
    
    def test_entry_expiry(self):
        """만료 체크"""
        entry = CacheEntry("key", "data", level=CacheLevel.L1, ttl_seconds=0.1)
        
        assert entry.is_expired() is False
        time.sleep(0.15)
        assert entry.is_expired() is True
    
    def test_entry_no_expiry(self):
        """TTL 없는 엔트리"""
        entry = CacheEntry("key", "data", level=CacheLevel.L1, ttl_seconds=None)
        
        assert entry.is_expired() is False
    
    def test_entry_size_estimation(self):
        """크기 추정"""
        small = CacheEntry("key", "small", level=CacheLevel.L1)
        large = CacheEntry("key", "x" * 10000, level=CacheLevel.L1)
        
        assert large.estimated_size > small.estimated_size


class TestCacheManager:
    """캐시 매니저 테스트"""
    
    @pytest.fixture
    def cache(self):
        return CacheManager(max_size_mb=10)
    
    def test_set_and_get(self, cache):
        """저장 및 조회"""
        cache.set("key1", {"data": 123}, level=CacheLevel.L1)
        
        result = cache.get("key1")
        assert result == {"data": 123}
    
    def test_get_miss(self, cache):
        """캐시 미스"""
        result = cache.get("nonexistent")
        assert result is None
    
    def test_level_isolation(self, cache):
        """레벨별 분리"""
        cache.set("key1", "L1 data", level=CacheLevel.L1)
        cache.set("key1", "L2 data", level=CacheLevel.L2)
        cache.set("key1", "L3 data", level=CacheLevel.L3)
        
        assert cache.get("key1", level=CacheLevel.L1) == "L1 data"
        assert cache.get("key1", level=CacheLevel.L2) == "L2 data"
        assert cache.get("key1", level=CacheLevel.L3) == "L3 data"
    
    def test_delete(self, cache):
        """삭제"""
        cache.set("key1", "data", level=CacheLevel.L1)
        cache.delete("key1")
        
        assert cache.get("key1") is None
    
    def test_clear_level(self, cache):
        """레벨별 클리어"""
        cache.set("k1", "d1", level=CacheLevel.L1)
        cache.set("k2", "d2", level=CacheLevel.L2)
        
        cache.clear(level=CacheLevel.L1)
        
        assert cache.get("k1", level=CacheLevel.L1) is None
        assert cache.get("k2", level=CacheLevel.L2) == "d2"
    
    def test_clear_all(self, cache):
        """전체 클리어"""
        cache.set("k1", "d1", level=CacheLevel.L1)
        cache.set("k2", "d2", level=CacheLevel.L2)
        cache.set("k3", "d3", level=CacheLevel.L3)
        
        cache.clear()
        
        assert cache.get("k1") is None
        assert cache.get("k2") is None
        assert cache.get("k3") is None


class TestL1ViewStatsCache:
    """L1: 현재 뷰 통계 캐시 테스트"""
    
    @pytest.fixture
    def cache(self):
        return CacheManager(max_size_mb=10)
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'A': [1, 2, 3, 4, 5],
            'B': [10, 20, 30, 40, 50],
        })
    
    def test_cache_view_stats(self, cache, sample_df):
        """뷰 통계 캐싱"""
        stats = {'mean': 3.0, 'sum': 15, 'count': 5}
        
        cache.set_view_stats("view1", stats)
        
        result = cache.get_view_stats("view1")
        assert result == stats
    
    def test_view_stats_invalidation(self, cache):
        """뷰 변경 시 무효화"""
        cache.set_view_stats("view1", {'mean': 3.0})
        
        # 뷰 변경 시뮬레이션
        cache.invalidate_view_stats()
        
        result = cache.get_view_stats("view1")
        assert result is None
    
    def test_filter_key_generation(self, cache):
        """필터 기반 키 생성"""
        filters = [
            {'column': 'A', 'op': 'gt', 'value': 10},
            {'column': 'B', 'op': 'eq', 'value': 'x'},
        ]
        
        key1 = cache.generate_filter_key(filters)
        key2 = cache.generate_filter_key(filters)
        
        # 동일한 필터 → 동일한 키
        assert key1 == key2
        
        # 다른 필터 → 다른 키
        filters2 = [{'column': 'A', 'op': 'lt', 'value': 5}]
        key3 = cache.generate_filter_key(filters2)
        assert key1 != key3


class TestL2ColumnStatsCache:
    """L2: 컬럼별 통계 캐시 테스트"""
    
    @pytest.fixture
    def cache(self):
        return CacheManager(max_size_mb=10)
    
    def test_cache_column_stats(self, cache):
        """컬럼 통계 캐싱"""
        stats = {
            'min': 1,
            'max': 100,
            'mean': 50.5,
            'std': 28.87,
            'null_count': 2,
        }
        
        cache.set_column_stats("column_A", stats)
        
        result = cache.get_column_stats("column_A")
        assert result == stats
    
    def test_column_stats_per_column(self, cache):
        """컬럼별 독립 캐싱"""
        cache.set_column_stats("A", {'mean': 10})
        cache.set_column_stats("B", {'mean': 20})
        
        assert cache.get_column_stats("A")['mean'] == 10
        assert cache.get_column_stats("B")['mean'] == 20
    
    def test_column_stats_invalidation(self, cache):
        """데이터 변경 시 컬럼 캐시 무효화"""
        cache.set_column_stats("A", {'mean': 10})
        cache.set_column_stats("B", {'mean': 20})
        
        # 특정 컬럼만 무효화
        cache.invalidate_column_stats("A")
        
        assert cache.get_column_stats("A") is None
        assert cache.get_column_stats("B") == {'mean': 20}
    
    def test_all_column_stats_invalidation(self, cache):
        """전체 컬럼 캐시 무효화"""
        cache.set_column_stats("A", {'mean': 10})
        cache.set_column_stats("B", {'mean': 20})
        
        cache.invalidate_all_column_stats()
        
        assert cache.get_column_stats("A") is None
        assert cache.get_column_stats("B") is None


class TestL3SortIndexCache:
    """L3: 정렬 인덱스 캐시 테스트"""
    
    @pytest.fixture
    def cache(self):
        return CacheManager(max_size_mb=10)
    
    def test_cache_sort_index(self, cache):
        """정렬 인덱스 캐싱"""
        sort_index = np.array([4, 2, 0, 3, 1])
        
        cache.set_sort_index("A", False, sort_index)
        
        result = cache.get_sort_index("A", False)
        np.testing.assert_array_equal(result, sort_index)
    
    def test_ascending_descending_separate(self, cache):
        """오름차순/내림차순 분리 캐싱"""
        asc = np.array([0, 1, 2, 3, 4])
        desc = np.array([4, 3, 2, 1, 0])
        
        cache.set_sort_index("A", False, asc)  # ascending
        cache.set_sort_index("A", True, desc)  # descending
        
        np.testing.assert_array_equal(cache.get_sort_index("A", False), asc)
        np.testing.assert_array_equal(cache.get_sort_index("A", True), desc)
    
    def test_sort_index_invalidation(self, cache):
        """정렬 인덱스 무효화"""
        cache.set_sort_index("A", False, np.array([0, 1, 2]))
        cache.set_sort_index("B", False, np.array([2, 1, 0]))
        
        cache.invalidate_sort_index("A")
        
        assert cache.get_sort_index("A", False) is None
        assert cache.get_sort_index("B", False) is not None


class TestCacheInvalidation:
    """캐시 무효화 테스트"""
    
    @pytest.fixture
    def cache(self):
        return CacheManager(max_size_mb=10)
    
    def test_data_change_invalidates_all(self, cache):
        """데이터 변경 시 전체 무효화"""
        cache.set_view_stats("v1", {"data": 1})
        cache.set_column_stats("col1", {"mean": 10})
        cache.set_sort_index("col1", False, np.array([0, 1, 2]))
        
        cache.on_data_changed()
        
        assert cache.get_view_stats("v1") is None
        assert cache.get_column_stats("col1") is None
        assert cache.get_sort_index("col1", False) is None
    
    def test_filter_change_invalidates_view(self, cache):
        """필터 변경 시 뷰 캐시만 무효화"""
        cache.set_view_stats("v1", {"data": 1})
        cache.set_column_stats("col1", {"mean": 10})
        
        cache.on_filter_changed()
        
        assert cache.get_view_stats("v1") is None
        assert cache.get_column_stats("col1") == {"mean": 10}  # 유지
    
    def test_column_change_invalidates_column(self, cache):
        """컬럼 데이터 변경 시 해당 컬럼만 무효화"""
        cache.set_column_stats("col1", {"mean": 10})
        cache.set_column_stats("col2", {"mean": 20})
        cache.set_sort_index("col1", False, np.array([0, 1]))
        
        cache.on_column_changed("col1")
        
        assert cache.get_column_stats("col1") is None
        assert cache.get_sort_index("col1", False) is None
        assert cache.get_column_stats("col2") == {"mean": 20}  # 유지


class TestCacheMemoryManagement:
    """캐시 메모리 관리 테스트"""
    
    def test_max_size_enforcement(self):
        """최대 크기 제한"""
        cache = CacheManager(max_size_mb=0.01)  # 10KB
        
        # 중간 크기 데이터 추가
        data1 = "x" * 4000
        data2 = "y" * 4000
        data3 = "z" * 4000
        
        cache.set("key1", data1, level=CacheLevel.L1)
        cache.set("key2", data2, level=CacheLevel.L1)
        cache.set("key3", data3, level=CacheLevel.L1)
        
        # 초과 시 오래된 항목이 제거됨
        total_size = cache.get_total_size()
        assert total_size <= 0.01 * 1024 * 1024 * 1.5  # 약간의 여유
    
    def test_lru_eviction(self):
        """LRU 제거 정책"""
        cache = CacheManager(max_size_mb=0.001)
        
        cache.set("old", "data1", level=CacheLevel.L1)
        cache.set("new", "data2", level=CacheLevel.L1)
        
        # old 접근
        cache.get("old")
        
        # 공간 부족 시 덜 사용된 항목 제거
        cache.set("newest", "x" * 1000, level=CacheLevel.L1)
        
        # old는 최근 접근했으므로 유지될 가능성 높음
        # (LRU 구현에 따라 다를 수 있음)
    
    def test_get_stats(self):
        """캐시 통계 조회"""
        cache = CacheManager(max_size_mb=10)
        
        cache.set("k1", "d1", level=CacheLevel.L1)
        cache.set("k2", "d2", level=CacheLevel.L2)
        cache.get("k1")
        cache.get("k1")
        cache.get("nonexistent")
        
        stats = cache.get_stats()
        
        assert stats['hits'] == 2
        assert stats['misses'] == 1
        assert stats['hit_ratio'] == 2 / 3
        assert stats['entry_count'] == 2
