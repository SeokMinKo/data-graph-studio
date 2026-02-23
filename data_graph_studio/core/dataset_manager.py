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
from .types import DatasetId, DatasetInfo, DataSource
from .file_loader import FileLoader
from .exceptions import DataLoadError, DatasetError

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
        """Return the mapping of all loaded datasets.

        Output: Dict[str, DatasetInfo] — live reference keyed by dataset ID
        """
        return self._datasets

    @property
    def dataset_count(self) -> int:
        """Return the number of currently loaded datasets.

        Output: int — count of entries in _datasets, >= 0
        """
        return len(self._datasets)

    @property
    def active_dataset_id(self) -> Optional[str]:
        """Return the ID of the currently active dataset.

        Output: Optional[str] — dataset ID string, or None if none is active
        """
        return self._active_dataset_id

    @property
    def active_dataset(self) -> Optional[DatasetInfo]:
        """Return the DatasetInfo for the currently active dataset, or None.

        Output: Optional[DatasetInfo] — active dataset, or None when no dataset is active
        """
        if self._active_dataset_id:
            return self._datasets.get(self._active_dataset_id)
        return None

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def set_on_dataset_removing(self, callback: Callable[[str], None]) -> None:
        """Register a callback invoked before a dataset is removed.

        Input: callback — Callable[[str], None], receives the dataset_id about to be removed
        Output: None
        Invariants: callback is stored and called once per remove_dataset() invocation before deletion
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
    ) -> Optional[DatasetId]:
        """Load a file from disk and register it as a new dataset.

        Input: path — str, absolute or relative path to the data file
        Input: name — Optional[str], display name; defaults to the file's basename
        Input: dataset_id — Optional[str], explicit ID; auto-generated if None
        Input: **load_kwargs — forwarded verbatim to FileLoader.load_file
        Output: Optional[str] — the assigned dataset_id on success, None on failure or when MAX_DATASETS is reached
        Invariants:
            - on success the dataset is stored in _datasets
            - _active_dataset_id is set if no other dataset was active
            - on failure _loader state is restored to its pre-call value
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
    ) -> Optional[DatasetId]:
        """Register an in-memory Polars DataFrame as a new dataset without file I/O.

        Input: df — pl.DataFrame, the data to register
        Input: name — str, display name for the dataset; defaults to "Untitled"
        Input: dataset_id — Optional[str], explicit ID; auto-generated if None
        Input: source_path — Optional[str], original file path stored in DataSource metadata; empty string if None
        Output: Optional[str] — the assigned dataset_id
        Invariants:
            - dataset is added to _datasets
            - _active_dataset_id is set if no other dataset was active
            - a lazy frame is derived from df and stored alongside it
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

    def remove_dataset(self, dataset_id: DatasetId) -> bool:
        """Remove a dataset and free its memory.

        Input: dataset_id — str, ID of the dataset to remove
        Output: bool — True if removed, False if dataset_id was not found
        Invariants:
            - _on_dataset_removing callback is called before deletion
            - df and lazy_df on the removed DatasetInfo are set to None
            - gc.collect() is called
            - if the removed dataset was active, _active_dataset_id advances to
              the next remaining dataset or becomes None
        """
        if dataset_id not in self._datasets:
            return False

        # 삭제 전 콜백 발행
        if self._on_dataset_removing is not None:
            try:
                self._on_dataset_removing(dataset_id)
            except DatasetError as e:
                logger.warning("dataset_manager.removing_callback_error", extra={"error": e})
            except (TypeError, KeyError, AttributeError) as e:
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

    def activate_dataset(self, dataset_id: DatasetId) -> bool:
        """Set a dataset as the active dataset.

        Input: dataset_id — str, ID of the dataset to activate; must exist in _datasets
        Output: bool — True if activated, False if dataset_id is not found
        Invariants: _active_dataset_id equals dataset_id after a successful call
        """
        if dataset_id not in self._datasets:
            return False
        self._active_dataset_id = dataset_id
        return True

    def list_datasets(self) -> List[DatasetInfo]:
        """Return all loaded datasets as an ordered list.

        Output: List[DatasetInfo] — snapshot of current datasets in insertion order
        """
        return list(self._datasets.values())

    def get_dataset(self, dataset_id: str) -> Optional[DatasetInfo]:
        """Look up a dataset by ID.

        Input: dataset_id — str, the dataset ID to look up
        Output: Optional[DatasetInfo] — the matching DatasetInfo, or None if not found
        """
        return self._datasets.get(dataset_id)

    def get_dataset_df(self, dataset_id: str) -> Optional[pl.DataFrame]:
        """Return the Polars DataFrame for a dataset.

        Input: dataset_id — str, the dataset ID to look up
        Output: Optional[pl.DataFrame] — the DataFrame, or None if the dataset is not found or has no data
        """
        dataset = self._datasets.get(dataset_id)
        return dataset.df if dataset else None

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def get_total_memory_usage(self) -> int:
        """Return the combined memory usage of all loaded datasets.

        Output: int — total bytes used across all datasets, 0 if none are loaded
        """
        return sum(ds.memory_bytes for ds in self._datasets.values())

    def can_load_dataset(self, estimated_size: int) -> Tuple[bool, str]:
        """Check whether a new dataset of the given size can be loaded.

        Input: estimated_size — int, expected memory footprint in bytes of the prospective dataset
        Output: Tuple[bool, str]
            - (True, "") if load is safe
            - (True, warning_msg) if near the memory ceiling
            - (False, reason_msg) if MAX_DATASETS or MAX_TOTAL_MEMORY would be exceeded
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
        """Update the display color of a dataset.

        Input: dataset_id — str, ID of the target dataset
        Input: color — str, hex color string (e.g. '#ff0000')
        Output: None
        Invariants: silently no-ops if dataset_id is not found; no event is emitted
        """
        if dataset_id in self._datasets:
            self._datasets[dataset_id].color = color

    def rename_dataset(self, dataset_id: str, new_name: str) -> None:
        """Change the display name of a dataset.

        Input: dataset_id — str, ID of the target dataset
        Input: new_name — str, replacement display name; must be non-empty by convention
        Output: None
        Invariants: silently no-ops if dataset_id is not found; no event is emitted
        """
        if dataset_id in self._datasets:
            self._datasets[dataset_id].name = new_name

    def clear_all_datasets(self) -> None:
        """Remove every loaded dataset and reset the color cycle.

        Output: None
        Invariants:
            - _datasets is empty, _active_dataset_id is None, and _color_index is 0
              after this call
            - remove_dataset() (including its callback and gc logic) is called for
              each dataset
        """
        for dataset_id in list(self._datasets.keys()):
            self.remove_dataset(dataset_id)
        self._color_index = 0

    # ------------------------------------------------------------------
    # Column utilities
    # ------------------------------------------------------------------

    def get_common_columns(self, dataset_ids: Optional[List[str]] = None) -> List[str]:
        """Return column names present in every specified dataset.

        Input: dataset_ids — Optional[List[str]], IDs of datasets to intersect; defaults to all loaded datasets when None
        Output: List[str] — column names found in all specified datasets; empty list if no datasets qualify
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
        """Return the names of integer and float columns in a dataset.

        Input: dataset_id — str, ID of the target dataset
        Output: List[str] — column names whose dtype is one of Int8/16/32/64 or Float32/64; empty list if the dataset is not found or has no data
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
        """Load multiple files concurrently using a thread pool.

        Input: paths — list of file path strings to load
        Input: max_workers — int, maximum number of concurrent threads; defaults to 4
        Output: Dict[str, Any] — mapping of each path to its dataset_id (str) on success, or a DatasetError instance on failure
        Invariants:
            - each successful path results in a registered dataset via
              load_dataset_from_dataframe
            - failed paths are recorded with an exception but do not abort other loads
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
                except (OSError, MemoryError, DataLoadError, pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError) as e:
                    results[path] = DatasetError(str(e), operation="parallel_load", context={"path": path})
                    logger.error("dataset_manager.parallel_load_failed.unexpected", extra={"path": path, "error": e}, exc_info=True)

        return results
