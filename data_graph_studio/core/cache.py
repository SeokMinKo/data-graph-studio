"""
Caching Layer - Multi-level cache for performance optimization
"""

import logging
import time
import hashlib
import json
import sys
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """캐시 레벨"""
    L1 = "L1"  # 현재 뷰 통계 (가장 빠르게 무효화)
    L2 = "L2"  # 컬럼별 통계
    L3 = "L3"  # 정렬 인덱스 (가장 오래 유지)


@dataclass
class CacheEntry:
    """캐시 엔트리"""
    key: str
    data: Any
    level: CacheLevel
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    hits: int = 0
    ttl_seconds: Optional[float] = None
    
    def hit(self):
        """히트 기록"""
        self.hits += 1
        self.last_accessed = time.time()
    
    def is_expired(self) -> bool:
        """만료 여부"""
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds
    
    @property
    def estimated_size(self) -> int:
        """크기 추정 (bytes)"""
        return self._estimate_size(self.data)
    
    def _estimate_size(self, obj: Any) -> int:
        """객체 크기 추정"""
        if obj is None:
            return 0
        
        if isinstance(obj, (str, bytes)):
            return len(obj)
        
        if isinstance(obj, np.ndarray):
            return obj.nbytes
        
        if isinstance(obj, (int, float, bool)):
            return 8
        
        if isinstance(obj, dict):
            return sum(
                self._estimate_size(k) + self._estimate_size(v)
                for k, v in obj.items()
            )
        
        if isinstance(obj, (list, tuple)):
            return sum(self._estimate_size(item) for item in obj)
        
        # 기본: sys.getsizeof 사용
        try:
            return sys.getsizeof(obj)
        except Exception:
            return 64  # default fallback


class CacheManager:
    """
    Multi-level Cache Manager
    
    Levels:
    - L1: 현재 뷰 통계 (필터/선택 변경 시 무효화)
    - L2: 컬럼별 통계 (데이터 변경 시 무효화)
    - L3: 정렬 인덱스 (데이터 변경 시 무효화)
    """
    
    def __init__(self, max_size_mb: float = 100):
        """
        Args:
            max_size_mb: 최대 캐시 크기 (MB)
        """
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        
        # 레벨별 캐시 저장소
        self._caches: Dict[CacheLevel, Dict[str, CacheEntry]] = {
            CacheLevel.L1: {},
            CacheLevel.L2: {},
            CacheLevel.L3: {},
        }
        
        # 통계
        self._hits = 0
        self._misses = 0
    
    # ==================== 기본 연산 ====================
    
    def set(
        self,
        key: str,
        data: Any,
        level: CacheLevel = CacheLevel.L1,
        ttl_seconds: Optional[float] = None
    ):
        """캐시 저장"""
        entry = CacheEntry(key, data, level, ttl_seconds=ttl_seconds)
        
        # 크기 확인 및 필요시 제거
        self._ensure_space(entry.estimated_size)
        
        self._caches[level][key] = entry
    
    def get(
        self,
        key: str,
        level: Optional[CacheLevel] = None
    ) -> Optional[Any]:
        """캐시 조회"""
        levels = [level] if level else list(CacheLevel)
        
        for lvl in levels:
            if key in self._caches[lvl]:
                entry = self._caches[lvl][key]
                
                # 만료 체크
                if entry.is_expired():
                    del self._caches[lvl][key]
                    continue
                
                entry.hit()
                self._hits += 1
                return entry.data
        
        self._misses += 1
        logger.debug("cache.miss", extra={"key": str(key)[:80]})
        return None
    
    def delete(self, key: str, level: Optional[CacheLevel] = None):
        """캐시 삭제"""
        levels = [level] if level else list(CacheLevel)
        
        for lvl in levels:
            self._caches[lvl].pop(key, None)
    
    def clear(self, level: Optional[CacheLevel] = None):
        """캐시 클리어"""
        if level:
            self._caches[level].clear()
        else:
            for lvl in CacheLevel:
                self._caches[lvl].clear()
    
    # ==================== L1: View Stats ====================
    
    def set_view_stats(self, view_key: str, stats: Dict[str, Any]):
        """뷰 통계 저장"""
        self.set(f"view:{view_key}", stats, level=CacheLevel.L1)
    
    def get_view_stats(self, view_key: str) -> Optional[Dict[str, Any]]:
        """뷰 통계 조회"""
        return self.get(f"view:{view_key}", level=CacheLevel.L1)
    
    def invalidate_view_stats(self):
        """모든 뷰 통계 무효화"""
        self.clear(level=CacheLevel.L1)
    
    def generate_filter_key(self, filters: List[Dict]) -> str:
        """필터 기반 키 생성"""
        # 필터 정렬 및 직렬화
        sorted_filters = sorted(filters, key=lambda f: (f.get('column', ''), f.get('op', '')))
        filter_str = json.dumps(sorted_filters, sort_keys=True)
        return hashlib.md5(filter_str.encode()).hexdigest()
    
    # ==================== L2: Column Stats ====================
    
    def set_column_stats(self, column: str, stats: Dict[str, Any]):
        """컬럼 통계 저장"""
        self.set(f"col:{column}", stats, level=CacheLevel.L2)
    
    def get_column_stats(self, column: str) -> Optional[Dict[str, Any]]:
        """컬럼 통계 조회"""
        return self.get(f"col:{column}", level=CacheLevel.L2)
    
    def invalidate_column_stats(self, column: str):
        """특정 컬럼 통계 무효화"""
        self.delete(f"col:{column}", level=CacheLevel.L2)
    
    def invalidate_all_column_stats(self):
        """모든 컬럼 통계 무효화"""
        self.clear(level=CacheLevel.L2)
    
    # ==================== L3: Sort Index ====================
    
    def set_sort_index(self, column: str, descending: bool, index: np.ndarray):
        """정렬 인덱스 저장"""
        key = f"sort:{column}:{'desc' if descending else 'asc'}"
        self.set(key, index, level=CacheLevel.L3)
    
    def get_sort_index(self, column: str, descending: bool) -> Optional[np.ndarray]:
        """정렬 인덱스 조회"""
        key = f"sort:{column}:{'desc' if descending else 'asc'}"
        return self.get(key, level=CacheLevel.L3)
    
    def invalidate_sort_index(self, column: str):
        """특정 컬럼 정렬 인덱스 무효화"""
        self.delete(f"sort:{column}:asc", level=CacheLevel.L3)
        self.delete(f"sort:{column}:desc", level=CacheLevel.L3)
    
    # ==================== 무효화 이벤트 ====================
    
    def on_data_changed(self):
        """데이터 변경 시 전체 무효화"""
        self.clear()
    
    def on_filter_changed(self):
        """필터 변경 시 L1 무효화"""
        self.clear(level=CacheLevel.L1)
    
    def on_column_changed(self, column: str):
        """컬럼 데이터 변경"""
        self.invalidate_column_stats(column)
        self.invalidate_sort_index(column)
        self.invalidate_view_stats()  # 뷰도 무효화
    
    # ==================== 메모리 관리 ====================
    
    def get_total_size(self) -> int:
        """총 캐시 크기 (bytes)"""
        total = 0
        for cache in self._caches.values():
            for entry in cache.values():
                total += entry.estimated_size
        return total
    
    def _ensure_space(self, needed: int):
        """필요한 공간 확보"""
        current = self.get_total_size()

        if current + needed <= self.max_size_bytes:
            return

        # Collect all entries in a single pass, sorted by last_accessed (LRU first)
        candidates = []
        for level in [CacheLevel.L1, CacheLevel.L2, CacheLevel.L3]:
            for key, entry in self._caches[level].items():
                candidates.append((entry.last_accessed, level, key, entry.estimated_size))

        candidates.sort(key=lambda c: c[0])

        # Evict entries in LRU order until there is enough space
        evicted = 0
        for _, level, key, size in candidates:
            if current + needed <= self.max_size_bytes:
                break
            del self._caches[level][key]
            current -= size
            evicted += 1
        if evicted:
            logger.debug("cache.evict", extra={"count": evicted})
    
    # ==================== 통계 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계"""
        entry_count = sum(len(cache) for cache in self._caches.values())
        total = self._hits + self._misses
        
        total_size = self.get_total_size()
        return {
            'hits': self._hits,
            'misses': self._misses,
            'hit_ratio': self._hits / total if total > 0 else 0.0,
            'entry_count': entry_count,
            'size_bytes': total_size,
            'size_mb': total_size / (1024 * 1024),
            'l1_count': len(self._caches[CacheLevel.L1]),
            'l2_count': len(self._caches[CacheLevel.L2]),
            'l3_count': len(self._caches[CacheLevel.L3]),
        }
    
    def reset_stats(self):
        """통계 리셋"""
        self._hits = 0
        self._misses = 0
