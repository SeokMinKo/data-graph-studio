"""
Caching Layer — Multi-level LRU cache for performance optimization.

Three levels with distinct invalidation semantics:
  L1 — current-view statistics; invalidated on filter or selection change.
  L2 — per-column statistics; invalidated when column data changes.
  L3 — sort indices; invalidated when column data changes.

Eviction is LRU across all levels when total size exceeds max_size_mb.
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
    """Cache tier identifier used to select invalidation scope.

    L1 — view statistics (invalidated most aggressively).
    L2 — column-level statistics.
    L3 — sort indices (invalidated least aggressively).
    """

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


@dataclass
class CacheEntry:
    """A single cached value with metadata for TTL expiry and LRU eviction.

    Tracks access count (hits), last_accessed timestamp for LRU ordering,
    and an optional TTL for time-based expiry.
    """

    key: str
    data: Any
    level: CacheLevel
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    hits: int = 0
    ttl_seconds: Optional[float] = None

    def hit(self) -> None:
        """Record a cache hit by incrementing the hit counter and updating last_accessed.

        Invariants: hits increases by 1; last_accessed set to current time
        """
        self.hits += 1
        self.last_accessed = time.time()

    def is_expired(self) -> bool:
        """Return True if this entry has exceeded its TTL.

        Output: bool — False when ttl_seconds is None (entries never expire by default)
        """
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    @property
    def estimated_size(self) -> int:
        """Estimated memory footprint of the cached data in bytes.

        Output: int — byte estimate; delegates to _estimate_size(self.data)
        """
        return self._estimate_size(self.data)

    def _estimate_size(self, obj: Any) -> int:
        """Recursively estimate the byte size of an arbitrary Python object.

        Input: obj — Any, the object to size
        Output: int — byte estimate; falls back to sys.getsizeof or 64 on failure
        Invariants: never raises; unknown types default to 64 bytes
        """
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
    """Multi-level LRU cache for computed view statistics, column stats, and sort indices.

    Provides typed accessor pairs (set_*/get_*) for each cache level and event-driven
    invalidation helpers (on_data_changed, on_filter_changed, on_column_changed).
    Evicts least-recently-used entries when total size exceeds max_size_mb.
    """

    def __init__(self, max_size_mb: float = 100):
        """Initialize with a byte-based size cap.

        Input: max_size_mb — float, maximum total cache size in megabytes (default 100)
        Invariants: all three level caches start empty; hit/miss counters start at 0
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
    ) -> None:
        """Store a value in the specified cache level.

        Input: key — str, cache key
               data — Any, value to store
               level — CacheLevel, target tier (default L1)
               ttl_seconds — float | None, expiry duration; None means no expiry
        Invariants: may evict LRU entries if size budget is exceeded before storing
        """
        entry = CacheEntry(key, data, level, ttl_seconds=ttl_seconds)
        
        # 크기 확인 및 필요시 제거
        self._ensure_space(entry.estimated_size)
        
        self._caches[level][key] = entry
    
    def get(
        self,
        key: str,
        level: Optional[CacheLevel] = None
    ) -> Optional[Any]:
        """Retrieve a value from the cache, searching all levels when level is None.

        Input: key — str, cache key to look up
               level — CacheLevel | None, restrict search to one level if provided
        Output: Any | None — cached value, or None on miss or expiry
        Invariants: expired entries are deleted on access; hit counter incremented on hit
        """
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
    
    def delete(self, key: str, level: Optional[CacheLevel] = None) -> None:
        """Remove a key from one or all cache levels.

        Input: key — str, cache key to remove
               level — CacheLevel | None, restrict deletion to one level if provided
        Invariants: no-op for keys that do not exist; does not affect other keys
        """
        levels = [level] if level else list(CacheLevel)
        
        for lvl in levels:
            self._caches[lvl].pop(key, None)
    
    def clear(self, level: Optional[CacheLevel] = None) -> None:
        """Evict all entries from one level or from every level.

        Input: level — CacheLevel | None, target level; None clears all three levels
        Invariants: hit/miss counters are NOT reset; use reset_stats() for that
        """
        if level:
            self._caches[level].clear()
        else:
            for lvl in CacheLevel:
                self._caches[lvl].clear()
    
    # ==================== L1: View Stats ====================
    
    def set_view_stats(self, view_key: str, stats: Dict[str, Any]) -> None:
        """Store view statistics under the given view key in the L1 cache.

        Input: view_key — str, opaque key identifying the current view state
               stats — Dict[str, Any], computed statistics for that view
        """
        self.set(f"view:{view_key}", stats, level=CacheLevel.L1)

    def get_view_stats(self, view_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve L1-cached view statistics for the given view key.

        Input: view_key — str, view identifier
        Output: Dict[str, Any] | None — cached stats, or None on miss/expiry
        """
        return self.get(f"view:{view_key}", level=CacheLevel.L1)

    def invalidate_view_stats(self) -> None:
        """Clear all L1 view statistics.

        Invariants: L2 and L3 entries are not affected
        """
        self.clear(level=CacheLevel.L1)

    def generate_filter_key(self, filters: List[Dict]) -> str:
        """Produce a stable MD5 cache key from a list of filter dicts.

        Input: filters — List[Dict], filter definitions (order-independent)
        Output: str — 32-character hex MD5 digest; identical for any ordering of filters
        """
        # 필터 정렬 및 직렬화
        sorted_filters = sorted(filters, key=lambda f: (f.get('column', ''), f.get('op', '')))
        filter_str = json.dumps(sorted_filters, sort_keys=True)
        return hashlib.md5(filter_str.encode()).hexdigest()
    
    # ==================== L2: Column Stats ====================
    
    def set_column_stats(self, column: str, stats: Dict[str, Any]) -> None:
        """Store per-column statistics in the L2 cache.

        Input: column — str, column name used as part of the cache key
               stats — Dict[str, Any], computed statistics for that column
        """
        self.set(f"col:{column}", stats, level=CacheLevel.L2)

    def get_column_stats(self, column: str) -> Optional[Dict[str, Any]]:
        """Retrieve L2-cached statistics for a specific column.

        Input: column — str, column name
        Output: Dict[str, Any] | None — cached stats, or None on miss/expiry
        """
        return self.get(f"col:{column}", level=CacheLevel.L2)

    def invalidate_column_stats(self, column: str) -> None:
        """Remove the L2 cache entry for a specific column.

        Input: column — str, column name whose stats should be invalidated
        Invariants: no-op if no entry exists for that column
        """
        self.delete(f"col:{column}", level=CacheLevel.L2)

    def invalidate_all_column_stats(self) -> None:
        """Clear all L2 column statistics entries.

        Invariants: L1 and L3 entries are not affected
        """
        self.clear(level=CacheLevel.L2)
    
    # ==================== L3: Sort Index ====================
    
    def set_sort_index(self, column: str, descending: bool, index: np.ndarray) -> None:
        """Store a pre-computed sort index in the L3 cache.

        Input: column — str, column that was sorted
               descending — bool, sort direction
               index — np.ndarray, integer index array mapping sorted to original positions
        Invariants: separate entries for asc and desc; keyed as "sort:{column}:{dir}"
        """
        key = f"sort:{column}:{'desc' if descending else 'asc'}"
        self.set(key, index, level=CacheLevel.L3)

    def get_sort_index(self, column: str, descending: bool) -> Optional[np.ndarray]:
        """Retrieve a cached sort index from the L3 cache.

        Input: column — str, column name
               descending — bool, sort direction
        Output: np.ndarray | None — cached index array, or None on miss
        """
        key = f"sort:{column}:{'desc' if descending else 'asc'}"
        return self.get(key, level=CacheLevel.L3)

    def invalidate_sort_index(self, column: str) -> None:
        """Remove both ascending and descending sort indices for a column from L3.

        Input: column — str, column whose sort indices should be invalidated
        Invariants: both "sort:{column}:asc" and "sort:{column}:desc" are deleted
        """
        self.delete(f"sort:{column}:asc", level=CacheLevel.L3)
        self.delete(f"sort:{column}:desc", level=CacheLevel.L3)
    
    # ==================== 무효화 이벤트 ====================
    
    def on_data_changed(self) -> None:
        """Invalidate all cache levels when the underlying dataset changes.

        Invariants: all L1, L2, and L3 entries are cleared
        """
        self.clear()

    def on_filter_changed(self) -> None:
        """Invalidate only L1 (view stats) when a filter is applied or removed.

        Invariants: L2 and L3 entries are preserved
        """
        self.clear(level=CacheLevel.L1)

    def on_column_changed(self, column: str) -> None:
        """Invalidate all derived data for a specific column.

        Input: column — str, the column whose data has changed
        Invariants: invalidates column stats (L2), sort indices (L3), and all view stats (L1)
        """
        self.invalidate_column_stats(column)
        self.invalidate_sort_index(column)
        self.invalidate_view_stats()
    
    # ==================== 메모리 관리 ====================
    
    def get_total_size(self) -> int:
        """Return the total estimated byte size of all cached entries across all levels.

        Output: int — sum of estimated_size for every CacheEntry
        """
        total = 0
        for cache in self._caches.values():
            for entry in cache.values():
                total += entry.estimated_size
        return total
    
    def _ensure_space(self, needed: int) -> None:
        """Evict LRU entries across all levels until there is room for `needed` bytes.

        Input: needed — int, byte count required for the incoming entry
        Invariants: evicts in LRU order (oldest last_accessed first); logs eviction count
        """
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
        """Return a snapshot of cache performance and memory metrics.

        Output: Dict[str, Any] — hits, misses, hit_ratio, entry_count,
                size_bytes, size_mb, l1_count, l2_count, l3_count
        """
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
    
    def reset_stats(self) -> None:
        """Reset hit and miss counters to zero without clearing cached data.

        Invariants: _hits and _misses are both 0 after return; cache contents unchanged
        """
        self._hits = 0
        self._misses = 0
