"""
DatasetManager — 멀티 데이터셋 관리 모듈

데이터셋 CRUD, 메모리 관리, 메타데이터, 컬럼 유틸리티를 제공한다.
FileLoader를 주입받아 파일 로딩을 위임한다.

상태 소유:
    _datasets, _active_dataset_id
"""

import gc
import uuid
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Callable, Any

import polars as pl

from .constants import DATASET_ID_LENGTH, MEMORY_WARNING_THRESHOLD
from .types import DatasetInfo, DataSource
from .file_loader import FileLoader
from .exceptions import DatasetError

logger = logging.getLogger(__name__)


class DatasetManager:
    """멀티 데이터셋 관리 클래스.

    Attributes:
        _datasets: 데이터셋 ID → DatasetInfo 매핑.
        _active_dataset_id: 현재 활성 데이터셋 ID.
        _loader: 파일 로딩에 사용할 FileLoader (주입됨).
    """

    MAX_DATASETS = 10
    MAX_TOTAL_MEMORY = 4 * 1024 * 1024 * 1024  # 4GB

    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]

    def __init__(self, loader: FileLoader):
        """DatasetManager를 초기화한다.

        Args:
            loader: 파일 로딩에 사용할 FileLoader 인스턴스.
        """
        self._loader = loader
        self._datasets: Dict[str, DatasetInfo] = {}
        self._active_dataset_id: Optional[str] = None
        self._color_index: int = 0
        self._on_dataset_removing: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def datasets(self) -> Dict[str, DatasetInfo]:
        """모든 데이터셋."""
        return self._datasets

    @property
    def dataset_count(self) -> int:
        """로드된 데이터셋 수."""
        return len(self._datasets)

    @property
    def active_dataset_id(self) -> Optional[str]:
        """현재 활성 데이터셋 ID."""
        return self._active_dataset_id

    @property
    def active_dataset(self) -> Optional[DatasetInfo]:
        """현재 활성 데이터셋."""
        if self._active_dataset_id:
            return self._datasets.get(self._active_dataset_id)
        return None

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def set_on_dataset_removing(self, callback: Callable[[str], None]) -> None:
        """데이터셋 삭제 전 콜백을 설정한다.

        Args:
            callback: dataset_id를 받는 콜백 함수.
        """
        self._on_dataset_removing = callback

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def load_dataset(
        self,
        path: str,
        name: Optional[str] = None,
        dataset_id: Optional[str] = None,
        **load_kwargs: Any,
    ) -> Optional[str]:
        """새 데이터셋을 로드한다.

        Args:
            path: 파일 경로.
            name: 표시 이름 (None이면 파일명).
            dataset_id: 데이터셋 ID (None이면 자동 생성).
            **load_kwargs: FileLoader.load_file에 전달할 추가 인자.

        Returns:
            생성된 dataset_id. 실패 시 None.
        """
        # MAX_DATASETS 체크
        if len(self._datasets) >= self.MAX_DATASETS:
            logger.warning("dataset_manager.max_datasets_reached", extra={"limit": self.MAX_DATASETS})
            return None

        if dataset_id is None:
            dataset_id = str(uuid.uuid4())[:DATASET_ID_LENGTH]

        if name is None:
            name = Path(path).name

        color = self.DEFAULT_COLORS[self._color_index % len(self.DEFAULT_COLORS)]
        self._color_index += 1

        # 로딩 전 상태 백업 (부분 실패 복원용)
        prev_df = self._loader._df
        prev_lazy_df = self._loader._lazy_df
        prev_source = self._loader._source
        prev_profile = self._loader._profile

        dataset = DatasetInfo(
            id=dataset_id,
            name=name,
            color=color,
        )

        success = self._loader.load_file(path, **load_kwargs)

        if not success:
            # 로딩 실패 시 이전 상태 복원
            self._loader._df = prev_df
            self._loader._lazy_df = prev_lazy_df
            self._loader._source = prev_source
            self._loader._profile = prev_profile
            return None

        # 로드된 데이터를 DatasetInfo에 이전
        dataset.df = self._loader._df
        dataset.lazy_df = self._loader._lazy_df
        dataset.source = self._loader._source
        dataset.profile = self._loader._profile

        self._datasets[dataset_id] = dataset

        if self._active_dataset_id is None:
            self._active_dataset_id = dataset_id

        logger.info("dataset_manager.dataset_loaded", extra={"dataset_id": dataset_id, "dataset_name": name, "row_count": dataset.row_count})
        return dataset_id

    def load_dataset_from_dataframe(
        self,
        df: pl.DataFrame,
        name: str = "Untitled",
        dataset_id: Optional[str] = None,
        source_path: Optional[str] = None,
    ) -> Optional[str]:
        """DataFrame을 직접 데이터셋으로 등록한다.

        Args:
            df: 로드할 polars DataFrame.
            name: 표시 이름.
            dataset_id: 데이터셋 ID (None이면 자동 생성).
            source_path: 원본 파일 경로 (메타데이터용).

        Returns:
            생성된 dataset_id. 실패 시 None.
        """
        if dataset_id is None:
            dataset_id = str(uuid.uuid4())[:DATASET_ID_LENGTH]

        color = self.DEFAULT_COLORS[self._color_index % len(self.DEFAULT_COLORS)]
        self._color_index += 1

        dataset = DatasetInfo(
            id=dataset_id,
            name=name,
            color=color,
        )
        dataset.df = df
        dataset.lazy_df = df.lazy()
        dataset.source = DataSource(
            path=source_path or "",
        )

        self._datasets[dataset_id] = dataset

        if self._active_dataset_id is None:
            self._active_dataset_id = dataset_id

        logger.info("dataset_manager.dataset_from_dataframe", extra={"dataset_id": dataset_id, "dataset_name": name, "row_count": dataset.row_count})
        return dataset_id

    def remove_dataset(self, dataset_id: str) -> bool:
        """데이터셋을 제거한다.

        Args:
            dataset_id: 제거할 데이터셋 ID.

        Returns:
            성공 여부.
        """
        if dataset_id not in self._datasets:
            return False

        # 삭제 전 콜백 발행
        if self._on_dataset_removing is not None:
            try:
                self._on_dataset_removing(dataset_id)
            except DatasetError as e:
                logger.warning("dataset_manager.removing_callback_error", extra={"error": e})
            except Exception as e:
                logger.warning("dataset_manager.removing_callback_error.unexpected", extra={"error": e}, exc_info=True)

        dataset = self._datasets[dataset_id]
        dataset.df = None
        dataset.lazy_df = None
        del self._datasets[dataset_id]

        if self._active_dataset_id == dataset_id:
            if self._datasets:
                self._active_dataset_id = next(iter(self._datasets.keys()))
            else:
                self._active_dataset_id = None

        gc.collect()
        logger.info("dataset_manager.dataset_removed", extra={"dataset_id": dataset_id})
        return True

    def activate_dataset(self, dataset_id: str) -> bool:
        """데이터셋을 활성화한다.

        Args:
            dataset_id: 활성화할 데이터셋 ID.

        Returns:
            성공 여부.
        """
        if dataset_id not in self._datasets:
            return False
        self._active_dataset_id = dataset_id
        return True

    def list_datasets(self) -> List[DatasetInfo]:
        """데이터셋 목록을 반환한다.

        Returns:
            DatasetInfo 리스트.
        """
        return list(self._datasets.values())

    def get_dataset(self, dataset_id: str) -> Optional[DatasetInfo]:
        """특정 데이터셋을 조회한다.

        Args:
            dataset_id: 데이터셋 ID.

        Returns:
            DatasetInfo 또는 None.
        """
        return self._datasets.get(dataset_id)

    def get_dataset_df(self, dataset_id: str) -> Optional[pl.DataFrame]:
        """특정 데이터셋의 DataFrame을 반환한다.

        Args:
            dataset_id: 데이터셋 ID.

        Returns:
            DataFrame 또는 None.
        """
        dataset = self._datasets.get(dataset_id)
        return dataset.df if dataset else None

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def get_total_memory_usage(self) -> int:
        """전체 데이터셋 메모리 사용량을 반환한다.

        Returns:
            바이트 단위 메모리 사용량.
        """
        return sum(ds.memory_bytes for ds in self._datasets.values())

    def can_load_dataset(self, estimated_size: int) -> Tuple[bool, str]:
        """데이터셋 로드 가능 여부를 확인한다.

        Args:
            estimated_size: 예상 메모리 크기 (bytes).

        Returns:
            (로드 가능 여부, 메시지) 튜플.
        """
        if len(self._datasets) >= self.MAX_DATASETS:
            return False, f"최대 데이터셋 수({self.MAX_DATASETS})에 도달했습니다."

        current = self.get_total_memory_usage()
        projected = current + estimated_size

        if projected > self.MAX_TOTAL_MEMORY:
            return False, (
                f"메모리 한도 초과. 현재: {current / 1e9:.1f}GB, "
                f"필요: {estimated_size / 1e9:.1f}GB, "
                f"한도: {self.MAX_TOTAL_MEMORY / 1e9:.1f}GB"
            )

        if projected > self.MAX_TOTAL_MEMORY * MEMORY_WARNING_THRESHOLD:
            return True, "⚠️ 메모리 사용량이 높습니다. 일부 데이터셋 제거를 권장합니다."

        return True, ""

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def set_dataset_color(self, dataset_id: str, color: str) -> None:
        """데이터셋 색상을 설정한다.

        Args:
            dataset_id: 데이터셋 ID.
            color: 색상 코드 (예: '#ff0000').
        """
        if dataset_id in self._datasets:
            self._datasets[dataset_id].color = color

    def rename_dataset(self, dataset_id: str, new_name: str) -> None:
        """데이터셋 이름을 변경한다.

        Args:
            dataset_id: 데이터셋 ID.
            new_name: 새 이름.
        """
        if dataset_id in self._datasets:
            self._datasets[dataset_id].name = new_name

    def clear_all_datasets(self) -> None:
        """모든 데이터셋을 제거한다."""
        for dataset_id in list(self._datasets.keys()):
            self.remove_dataset(dataset_id)
        self._color_index = 0

    # ------------------------------------------------------------------
    # Column utilities
    # ------------------------------------------------------------------

    def get_common_columns(self, dataset_ids: Optional[List[str]] = None) -> List[str]:
        """여러 데이터셋의 공통 컬럼을 반환한다.

        Args:
            dataset_ids: 대상 데이터셋 ID 목록 (None이면 전체).

        Returns:
            공통 컬럼 이름 목록.
        """
        if dataset_ids is None:
            dataset_ids = list(self._datasets.keys())

        if not dataset_ids:
            return []

        first_id = dataset_ids[0]
        common = set(self._datasets[first_id].columns) if first_id in self._datasets else set()

        for did in dataset_ids[1:]:
            if did in self._datasets:
                common &= set(self._datasets[did].columns)

        return list(common)

    def get_numeric_columns(self, dataset_id: str) -> List[str]:
        """데이터셋의 숫자형 컬럼 목록을 반환한다.

        Args:
            dataset_id: 데이터셋 ID.

        Returns:
            숫자형 컬럼 이름 목록.
        """
        dataset = self._datasets.get(dataset_id)
        if dataset is None or dataset.df is None:
            return []

        return [
            col for col in dataset.df.columns
            if dataset.df[col].dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                                          pl.Float32, pl.Float64]
        ]

    # ------------------------------------------------------------------
    # Parallel loading (F7)
    # ------------------------------------------------------------------

    def load_datasets_parallel(
        self, paths: list, max_workers: int = 4,
    ) -> Dict[str, Any]:
        """여러 파일을 병렬로 로드한다.

        Args:
            paths: 파일 경로 목록.
            max_workers: 최대 워커 수.

        Returns:
            {path: dataset_id_or_exception} 매핑.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: Dict[str, Any] = {}

        def _load_single(p: str):
            loader = FileLoader(self._loader._precision_mode)
            success = loader.load_file(p)
            if not success:
                raise DatasetError(
                    f"Failed to load {p}",
                    operation="_load_single",
                    context={"path": str(p)},
                )
            return loader._df

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_load_single, p): p for p in paths}
            for future in as_completed(futures):
                path = futures[future]
                try:
                    df = future.result()
                    did = self.load_dataset_from_dataframe(
                        df, name=Path(path).name, source_path=path,
                    )
                    results[path] = did
                except DatasetError as e:
                    results[path] = e
                    logger.error("dataset_manager.parallel_load_failed", extra={"path": path, "error": e}, exc_info=True)
                except Exception as e:
                    results[path] = DatasetError(str(e), operation="parallel_load", context={"path": path})
                    logger.error("dataset_manager.parallel_load_failed.unexpected", extra={"path": path, "error": e}, exc_info=True)

        return results
