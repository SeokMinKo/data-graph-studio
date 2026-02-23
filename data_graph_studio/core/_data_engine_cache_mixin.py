"""DataEngine cache mixin — LRU cache management."""

from __future__ import annotations

from typing import Any


class _DataEngineCacheMixin:
    """LRU cache helpers for DataEngine.

    Attributes accessed from DataEngine:
        _cache: OrderedDict used as the LRU cache store.
        _cache_maxsize: Maximum number of entries before eviction.
        _datasets_mgr: DatasetManager used to build dataset-scoped cache keys.
    """

    def _get_cache(self, key: str) -> Any:
        """캐시에서 값을 가져온다 (LRU: 접근 시 끝으로 이동)."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _set_cache(self, key: str, value: Any) -> None:
        """캐시에 값을 저장한다."""
        self._cache[key] = value
        self._cache.move_to_end(key)
        self._evict_cache()

    def _evict_cache(self) -> None:
        while len(self._cache) > self._cache_maxsize:
            self._cache.popitem(last=False)  # 가장 오래 안 쓴 것 제거

    def _clear_cache(self) -> None:
        self._cache.clear()

    def _cache_key(self, operation: str, *args) -> str:
        """dataset별 캐시 키 생성 (F5)."""
        dataset_id = self._datasets_mgr.active_dataset_id if self._datasets_mgr else "default"
        return f"{dataset_id}:{operation}:{hash(args)}"
