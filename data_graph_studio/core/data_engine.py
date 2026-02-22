"""
Data Engine — Polars 기반 빅데이터 처리 엔진 (Facade)

5개 하위 모듈(FileLoader, DataQuery, DataExporter, DatasetManager,
ComparisonEngine)을 조합하여 기존 API를 100% 유지하는 Facade 패턴.

기존 import 호환:
    from data_graph_studio.core.data_engine import DataEngine, FileType, ...
"""

import warnings
import logging
import time
from collections import OrderedDict
from typing import Optional, List, Dict, Any, Set

import polars as pl

# Re-export types for backward compatibility
from .types import (  # noqa: F401
    FileType, DelimiterType, LoadingProgress, ColumnInfo, DataProfile,
    DatasetInfo, DataSource, PrecisionMode,
)

# Re-export optional dependency flags
try:
    from scipy import stats as scipy_stats  # noqa: F401
    from scipy.stats import pearsonr, spearmanr, ttest_ind, mannwhitneyu, ks_2samp  # noqa: F401
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from etl.etl import IEtlFileObserver, build_from_stream  # noqa: F401
    from etl.system import System  # noqa: F401
    HAS_ETL_PARSER = True
except ImportError:
    HAS_ETL_PARSER = False

logger = logging.getLogger(__name__)


def _import_submodules():
    """하위 모듈을 지연 임포트한다."""
    from .file_loader import FileLoader
    from .data_query import DataQuery
    from .data_exporter import DataExporter
    from .dataset_manager import DatasetManager
    from .comparison_engine import ComparisonEngine
    return FileLoader, DataQuery, DataExporter, DatasetManager, ComparisonEngine


class DataEngine:
    """빅데이터 처리 엔진 Facade.

    Attributes:
        _loader: 파일 I/O 담당.
        _query: 조회/변환/통계 담당.
        _exporter: 내보내기 담당.
        _datasets_mgr: 멀티 데이터셋 관리.
        _comparison: 비교 분석.
        _cache: LRU 캐시 (maxsize=128).
    """

    DEFAULT_CHUNK_SIZE = 100_000
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024
    LAZY_EVAL_THRESHOLD = 1024 * 1024 * 1024
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 0.5

    def __init__(self, precision_mode: PrecisionMode = PrecisionMode.AUTO):
        from .transform_chain import TransformChain

        FL, DQ, DE, DM, CE = _import_submodules()
        self._loader = FL(precision_mode)
        self._query = DQ()
        self._exporter = DE()
        self._datasets_mgr = DM(self._loader)
        self._comparison = CE(self._datasets_mgr)
        self._cache: OrderedDict = OrderedDict()
        self._cache_maxsize: int = 128
        self._indexes: Dict[str, Dict] = {}
        self._precision_mode = precision_mode
        self._transform_chain = TransformChain()
        self._virtual_columns: Set[str] = set()
        self._current_file_path: Optional[str] = None

    # -- Cache (real LRU via OrderedDict) ------------------------------------

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

    # -- Properties: FileLoader -----------------------------------------------

    @property
    def df(self) -> Optional[pl.DataFrame]:
        """Active DataFrame: returns the active dataset's DataFrame, or the loader's DataFrame if no dataset is active."""
        if self._datasets_mgr.active_dataset_id:
            return self._datasets_mgr.get_dataset_df(self._datasets_mgr.active_dataset_id)
        return self._loader._df

    @property
    def _df(self) -> Optional[pl.DataFrame]:
        return self.df

    @_df.setter
    def _df(self, value: Optional[pl.DataFrame]) -> None:
        """Backward-compatible setter. Prefer update_dataframe()."""
        self._loader._df = value

    def update_dataframe(self, df: Optional[pl.DataFrame]) -> None:
        """공식 API: DataFrame 업데이트 + dataset sync + cache clear."""
        self._loader._df = df
        # active dataset sync
        if self._datasets_mgr and self._datasets_mgr.active_dataset:
            self._datasets_mgr.active_dataset.df = df
        self._clear_cache()

    def drop_column(self, col_name: str) -> None:
        """컬럼 삭제 (dataset sync + cache clear)."""
        if self.df is None or col_name not in self.df.columns:
            return
        new_df = self.df.drop(col_name)
        self.update_dataframe(new_df)
        # transform chain 기록
        from .transform_chain import TransformStep
        self._transform_chain.add(TransformStep(
            name=f"Drop column '{col_name}'",
            operation='drop',
            params={'column': col_name},
            timestamp=time.time(),
        ))
        # virtual columns 추적 제거
        self._virtual_columns.discard(col_name)

    @property
    def _lazy_df(self) -> Optional[pl.LazyFrame]:
        return self._loader._lazy_df

    @_lazy_df.setter
    def _lazy_df(self, value: Optional[pl.LazyFrame]) -> None:
        self._loader._lazy_df = value

    @property
    def _source(self) -> Optional[DataSource]:
        return self._loader._source

    @_source.setter
    def _source(self, value: Optional[DataSource]) -> None:
        self._loader._source = value

    @property
    def _profile(self) -> Optional[DataProfile]:
        return self._loader._profile

    @_profile.setter
    def _profile(self, value: Optional[DataProfile]) -> None:
        self._loader._profile = value

    @property
    def _progress(self) -> LoadingProgress:
        return self._loader._progress

    @property
    def _cancel_loading(self) -> bool:
        return self._loader._cancel_loading

    @_cancel_loading.setter
    def _cancel_loading(self, value: bool) -> None:
        self._loader._cancel_loading = value

    @property
    def _precision_columns(self) -> Set[str]:
        return self._loader._precision_columns

    @property
    def profile(self) -> Optional[DataProfile]:
        """Current DataProfile for the loaded file, or None if no file is loaded."""
        return self._loader.profile

    @property
    def progress(self) -> LoadingProgress:
        """Current LoadingProgress snapshot for any in-progress file load operation."""
        return self._loader.progress

    @property
    def is_loaded(self) -> bool:
        """True if a DataFrame is currently loaded and available."""
        return self.df is not None

    @property
    def row_count(self) -> int:
        """Total number of rows: uses the full file row count when windowed, otherwise the in-memory DataFrame length."""
        if self._loader.is_windowed and self._loader._total_rows > 0:
            return self._loader._total_rows
        return len(self.df) if self.df is not None else 0

    @property
    def column_count(self) -> int:
        """Number of columns in the active DataFrame, or 0 if no data is loaded."""
        df = self.df
        return len(df.columns) if df is not None else 0

    @property
    def columns(self) -> List[str]:
        """Ordered list of column names in the active DataFrame, or an empty list if no data is loaded."""
        df = self.df
        return df.columns if df is not None else []

    @property
    def dtypes(self) -> Dict[str, str]:
        """Mapping of column name to its Polars dtype string for the active DataFrame."""
        df = self.df
        return {c: str(d) for c, d in zip(df.columns, df.dtypes)} if df is not None else {}

    @property
    def is_windowed(self) -> bool:
        """True if the loaded data is a windowed slice of a larger file rather than the full file."""
        return self._loader.is_windowed

    @property
    def total_rows(self) -> int:
        """Total row count of the source file, including rows outside the current window."""
        return self._loader.total_rows

    @property
    def window_start(self) -> int:
        """Zero-based row index of the first row in the current window."""
        return self._loader.window_start

    @property
    def window_size(self) -> int:
        """Maximum number of rows included in the current window."""
        return self._loader.window_size

    @property
    def has_lazy(self) -> bool:
        """True if a Polars LazyFrame is available for the current data source."""
        return self._loader.has_lazy

    # -- FileLoader delegation ------------------------------------------------

    @staticmethod
    def _normalize_encoding(encoding: str) -> str:
        from .file_loader import FileLoader as FL
        return FL._normalize_encoding(encoding)

    def set_progress_callback(self, cb):
        """Register a callback to receive LoadingProgress updates during file loading."""
        self._loader.set_progress_callback(cb)

    def detect_file_type(self, path: str) -> FileType:
        """Detect and return the FileType for the file at the given path based on its extension and content."""
        return self._loader.detect_file_type(path)

    def detect_delimiter(self, path, encoding="utf-8", sample_lines=10):
        """Detect the delimiter used in a delimited text file by sampling the first few lines.

        Args:
            path: Path to the file to inspect.
            encoding: File encoding to use when reading sample lines.
            sample_lines: Number of lines to sample for delimiter detection.

        Returns:
            A DelimiterType value representing the detected delimiter.
        """
        return self._loader.detect_delimiter(path, encoding, sample_lines)

    def set_precision_mode(self, mode):
        """Set the precision mode that controls how floating-point columns are handled during loading.

        Args:
            mode: A PrecisionMode value (e.g., AUTO, HIGH, STANDARD).
        """
        self._loader.set_precision_mode(mode)

    def add_precision_column(self, column):
        """Mark a specific column to be treated with high-precision numeric handling.

        Args:
            column: Column name to add to the precision-sensitive set.
        """
        self._loader.add_precision_column(column)

    def cancel_loading(self):
        """Signal the file loader to abort any in-progress load operation."""
        self._loader.cancel_loading()

    def set_window(self, start, size):
        """Configure windowed loading to read a row slice from the source file.

        Args:
            start: Zero-based index of the first row to include.
            size: Maximum number of rows to load into memory.

        Returns:
            True if the window was applied successfully, False otherwise.
        """
        return self._loader.set_window(start, size)

    def load_lazy(self, path, **kw):
        """Load a file as a Polars LazyFrame without immediately collecting it into memory.

        Args:
            path: Path to the file to load.
            **kw: Additional keyword arguments forwarded to the underlying loader.

        Returns:
            A Polars LazyFrame for the file, or None on failure.
        """
        return self._loader.load_lazy(path, **kw)

    def collect_lazy(self, limit=None, optimize_memory=True):
        """Collect the current LazyFrame into a DataFrame, optionally limiting rows and optimizing memory.

        Args:
            limit: Maximum number of rows to collect; None collects all rows.
            optimize_memory: If True, applies memory-reduction passes after collection.

        Returns:
            A Polars DataFrame, or None if no LazyFrame is available.
        """
        return self._loader.collect_lazy(limit, optimize_memory)

    def query_lazy(self, expr):
        """Apply a Polars expression to the current LazyFrame and return the filtered LazyFrame.

        Args:
            expr: A Polars expression to apply as a filter or transformation.

        Returns:
            A new LazyFrame with the expression applied, or None if no LazyFrame exists.
        """
        return self._loader.query_lazy(expr)
    def _update_progress(self, **kw): self._loader._update_progress(**kw)
    def _prepare_parquet_from_csv(self, *a, **kw): return self._loader._prepare_parquet_from_csv(*a, **kw)
    def _load_window_from_lazy(self, *a, **kw): return self._loader._load_window_from_lazy(*a, **kw)
    def _collect_streaming(self, lf): return self._loader._collect_streaming(lf)
    def _create_profile(self, df, t): return self._loader._create_profile(df, t)
    def _optimize_memory(self, df): return self._loader._optimize_memory(df)
    def _is_precision_sensitive_column(self, c): return self._loader._is_precision_sensitive_column(c)

    def load_file(self, path: str, **kwargs) -> bool:
        """Load a file into the engine, clearing the cache beforehand and returning success status.

        Args:
            path: Absolute or relative path to the file to load.
            **kwargs: Additional keyword arguments forwarded to the underlying FileLoader.

        Returns:
            True if the file was loaded successfully, False otherwise.
        """
        self._clear_cache()
        return self._loader.load_file(path, **kwargs)

    def append_rows(self, file_path: str, new_row_count: int) -> bool:
        """Incrementally append new rows from the end of a file (streaming optimization).

        Reads the last *new_row_count* rows from *file_path* and concatenates
        them to the current DataFrame.  Falls back to full reload on error.
        """
        import polars as pl

        current_df = self.df
        if current_df is None:
            return self.load_file(file_path, optimize_memory=True)

        try:
            full_df = pl.read_csv(file_path)
            new_rows = full_df.tail(new_row_count)
            merged = pl.concat([current_df, new_rows], how="vertical_relaxed")
            self.update_dataframe(merged)
            self._clear_cache()
            return True
        except Exception:
            return self.load_file(file_path, optimize_memory=True)

    @staticmethod
    def is_binary_etl(path: str) -> bool:
        """Return True if the file at path is a binary ETL format that requires the ETL parser.

        Args:
            path: Path to the file to inspect.
        """
        from .file_loader import FileLoader as FL
        return FL.is_binary_etl(path)

    @staticmethod
    def parse_etl_binary(path: str) -> pl.DataFrame:
        """Parse a binary ETL file and return its contents as a Polars DataFrame.

        Args:
            path: Path to the binary ETL file.

        Returns:
            A Polars DataFrame containing the parsed ETL data.

        Raises:
            ImportError: If the optional ETL parser dependency is not installed.
        """
        from .file_loader import FileLoader as FL
        return FL.parse_etl_binary(path)

    # -- DataQuery delegation -------------------------------------------------

    def get_filtered_df(self, filter_map: Dict[str, list]) -> Optional[pl.DataFrame]:
        """``{column: [values]}`` 필터 맵을 Polars lazy 레이어에서 처리 후 반환한다.

        graph_panel의 ``_active_filter`` 를 그대로 받아서 사용할 수 있다.
        필터가 없거나 데이터가 없으면 현재 ``df`` 를 그대로 반환한다.
        """
        return self._query.filter_by_map(self.df, filter_map)

    def filter(self, column, operator, value):
        """Filter the active DataFrame on a single column using a comparison operator and value.

        Args:
            column: Name of the column to filter on.
            operator: Comparison operator string (e.g., "==", "!=", ">", "<", "contains").
            value: The value to compare each row's column entry against.

        Returns:
            A filtered Polars DataFrame, or None if no data is loaded.
        """
        return self._query.filter(self.df, column, operator, value)

    def sort(self, columns, descending=False):
        """Sort the active DataFrame by one or more columns.

        Args:
            columns: A column name or list of column names to sort by.
            descending: If True, sort in descending order; defaults to ascending.

        Returns:
            A sorted Polars DataFrame, or None if no data is loaded.
        """
        return self._query.sort(self.df, columns, descending)

    def group_aggregate(self, group_columns, value_columns, agg_funcs):
        """Group the active DataFrame and apply aggregation functions to value columns.

        Args:
            group_columns: Column name or list of column names to group by.
            value_columns: Column name or list of column names to aggregate.
            agg_funcs: Aggregation function name or list of names (e.g., "sum", "mean", "count").

        Returns:
            A Polars DataFrame with one row per group and aggregated values.
        """
        return self._query.group_aggregate(self.df, group_columns, value_columns, agg_funcs)

    def get_statistics(self, column):
        """Compute descriptive statistics for a single column in the active DataFrame.

        Args:
            column: Name of the column to analyse.

        Returns:
            A dict containing statistics such as min, max, mean, median, std, and null_count.
        """
        return self._query.get_statistics(self.df, column, self._loader._lazy_df, self._loader.is_windowed, self._cache)

    def get_all_statistics(self, value_columns=None):
        """Compute descriptive statistics for all (or a subset of) numeric columns.

        Args:
            value_columns: List of column names to include; None includes all numeric columns.

        Returns:
            A dict mapping column name to its statistics dict.
        """
        return self._query.get_all_statistics(self.df, value_columns, self._loader._lazy_df, self._loader.is_windowed, self._cache)

    def get_full_profile_summary(self):
        """Return a comprehensive profile summary combining per-column statistics and the DataProfile.

        Returns:
            A dict with row_count, column_count, per-column statistics, and profile metadata.
        """
        return self._query.get_full_profile_summary(self.df, self._loader.profile, self._loader._lazy_df, self._loader.is_windowed)

    def is_column_categorical(self, col, max_unique_ratio=0.05, max_unique_count=100):
        """Determine whether a column should be treated as categorical based on its cardinality.

        Args:
            col: Column name to evaluate.
            max_unique_ratio: Maximum ratio of unique values to total rows for categorical classification.
            max_unique_count: Maximum absolute number of unique values for categorical classification.

        Returns:
            True if the column is considered categorical, False otherwise.
        """
        return self._query.is_column_categorical(self.df, col, max_unique_ratio, max_unique_count)

    def get_unique_values(self, col, limit=1000):
        """Return the distinct values present in a column, up to a specified limit.

        Args:
            col: Column name to inspect.
            limit: Maximum number of unique values to return.

        Returns:
            A list of unique values from the column.
        """
        return self._query.get_unique_values(self.df, col, limit)

    def sample(self, n=10000, seed=42):
        """Draw a random sample of rows from the active DataFrame.

        Args:
            n: Number of rows to sample; if fewer rows exist, all rows are returned.
            seed: Random seed for reproducibility.

        Returns:
            A Polars DataFrame containing the sampled rows.
        """
        return self._query.sample(self.df, n, seed)

    def get_slice(self, start, end):
        """Return a contiguous row slice from the active DataFrame.

        Args:
            start: Zero-based index of the first row to include.
            end: Zero-based index of the last row to include (exclusive).

        Returns:
            A Polars DataFrame containing the requested rows.
        """
        return self._query.get_slice(self.df, start, end)

    def search(self, query, columns=None, case_sensitive=False, max_columns=20):
        """Search for a string query across columns in the active DataFrame.

        Args:
            query: The search string to look for in cell values.
            columns: List of column names to search; None searches all string-compatible columns.
            case_sensitive: If True, performs a case-sensitive match.
            max_columns: Maximum number of columns to include in the search.

        Returns:
            A Polars DataFrame containing only the rows that match the query.
        """
        return self._query.search(self.df, query, columns, case_sensitive, max_columns)

    def create_index(self, column):
        """Build and cache an index for a column to accelerate repeated lookups.

        Args:
            column: Name of the column to index.

        .. deprecated::
            Use Polars native filtering instead; this method will be removed in a future release.
        """
        warnings.warn("create_index is deprecated. Use Polars native filtering.", DeprecationWarning, stacklevel=2)
        if self.df is None or column not in self.df.columns:
            return
        self._indexes[column] = self._query.create_index(self.df, column)

    # -- DataExporter delegation ----------------------------------------------

    def export_csv(self, path, selected_rows=None):
        """Export the active DataFrame (or a row subset) to a CSV file.

        Args:
            path: Destination file path for the exported CSV.
            selected_rows: Optional list of row indices to include; None exports all rows.
        """
        if self.df is not None:
            self._exporter.export_csv(self.df, path, selected_rows)

    def export_excel(self, path, selected_rows=None):
        """Export the active DataFrame (or a row subset) to an Excel (.xlsx) file.

        Args:
            path: Destination file path for the exported Excel file.
            selected_rows: Optional list of row indices to include; None exports all rows.
        """
        if self.df is not None:
            self._exporter.export_excel(self.df, path, selected_rows)

    def export_parquet(self, path, selected_rows=None):
        """Export the active DataFrame (or a row subset) to a Parquet file.

        Args:
            path: Destination file path for the exported Parquet file.
            selected_rows: Optional list of row indices to include; None exports all rows.
        """
        if self.df is not None:
            self._exporter.export_parquet(self.df, path, selected_rows)

    # -- DatasetManager delegation --------------------------------------------

    @property
    def datasets(self):
        """Ordered mapping of dataset ID to DatasetInfo for all loaded datasets."""
        return self._datasets_mgr.datasets

    @property
    def _datasets(self): return self._datasets_mgr.datasets

    @property
    def dataset_count(self):
        """Number of datasets currently held in the dataset manager."""
        return self._datasets_mgr.dataset_count

    @property
    def active_dataset_id(self):
        """ID of the currently active dataset, or None if no dataset is active."""
        return self._datasets_mgr.active_dataset_id

    @property
    def _active_dataset_id(self): return self._datasets_mgr._active_dataset_id

    @_active_dataset_id.setter
    def _active_dataset_id(self, value): self._datasets_mgr._active_dataset_id = value

    @property
    def active_dataset(self):
        """DatasetInfo for the currently active dataset, or None if no dataset is active."""
        return self._datasets_mgr.active_dataset

    @property
    def _color_index(self): return self._datasets_mgr._color_index

    @_color_index.setter
    def _color_index(self, value): self._datasets_mgr._color_index = value

    def get_dataset(self, did):
        """Return the DatasetInfo for the given dataset ID, or None if it does not exist.

        Args:
            did: Dataset ID string to look up.
        """
        return self._datasets_mgr.get_dataset(did)

    def get_dataset_df(self, did):
        """Return the Polars DataFrame for the given dataset ID, or None if unavailable.

        Args:
            did: Dataset ID string to look up.
        """
        return self._datasets_mgr.get_dataset_df(did)

    def list_datasets(self):
        """Return a list of summary dicts (id, name, row_count, column_count) for all loaded datasets."""
        return self._datasets_mgr.list_datasets()

    def get_total_memory_usage(self):
        """Return the combined estimated memory usage in bytes for all loaded datasets."""
        return self._datasets_mgr.get_total_memory_usage()

    def can_load_dataset(self, sz):
        """Check whether a new dataset of the given byte size can be loaded without exceeding memory limits.

        Args:
            sz: Estimated size in bytes of the dataset to be loaded.

        Returns:
            True if loading is within limits, False otherwise.
        """
        return self._datasets_mgr.can_load_dataset(sz)

    def set_dataset_color(self, did, c):
        """Assign a display color to the specified dataset.

        Args:
            did: Dataset ID string.
            c: Color value (hex string or name) to assign.
        """
        self._datasets_mgr.set_dataset_color(did, c)

    def rename_dataset(self, did, n):
        """Rename the specified dataset.

        Args:
            did: Dataset ID string.
            n: New name string for the dataset.
        """
        self._datasets_mgr.rename_dataset(did, n)

    def get_common_columns(self, ids=None):
        """Return the list of column names shared by all specified (or all loaded) datasets.

        Args:
            ids: List of dataset IDs to compare; None compares all loaded datasets.

        Returns:
            A list of column name strings common to all specified datasets.
        """
        return self._datasets_mgr.get_common_columns(ids)

    def get_numeric_columns(self, did):
        """Return the list of numeric column names for the specified dataset.

        Args:
            did: Dataset ID string.

        Returns:
            A list of column names whose Polars dtype is numeric.
        """
        return self._datasets_mgr.get_numeric_columns(did)

    def load_dataset(self, path, name=None, dataset_id=None, **kw):
        """Load a file as a new dataset, clearing the cache first.

        Args:
            path: Path to the file to load.
            name: Human-readable name for the dataset; defaults to the file's basename.
            dataset_id: Explicit ID string; auto-generated if not provided.
            **kw: Additional keyword arguments forwarded to the dataset manager loader.

        Returns:
            The dataset ID string if loading succeeded, or None on failure.
        """
        self._clear_cache()
        return self._datasets_mgr.load_dataset(path, name, dataset_id, **kw)

    def load_dataset_from_dataframe(self, df, name="Untitled", dataset_id=None, source_path=None):
        """DataFrame을 직접 데이터셋으로 로드한다."""
        self._clear_cache()
        result = self._datasets_mgr.load_dataset_from_dataframe(
            df, name=name, dataset_id=dataset_id, source_path=source_path
        )
        if result:
            self._sync_active_dataset()
        return result

    def remove_dataset(self, dataset_id):
        """Remove the specified dataset, then sync the loader to the new active dataset.

        Args:
            dataset_id: ID string of the dataset to remove.

        Returns:
            True if the dataset was found and removed, False otherwise.
        """
        self._clear_cache()
        result = self._datasets_mgr.remove_dataset(dataset_id)
        active = self._datasets_mgr.active_dataset
        if active:
            self._loader._df, self._loader._lazy_df = active.df, active.lazy_df
            self._loader._source, self._loader._profile = active.source, active.profile
        elif not self._datasets_mgr.datasets:
            self._loader._df = self._loader._lazy_df = None
            self._loader._source = self._loader._profile = None
        return result

    def activate_dataset(self, dataset_id):
        """Set the specified dataset as active and sync the loader's state to it.

        Args:
            dataset_id: ID string of the dataset to activate.

        Returns:
            True if activation succeeded, False if the dataset ID was not found.
        """
        self._clear_cache()
        result = self._datasets_mgr.activate_dataset(dataset_id)
        if result:
            self._sync_active_dataset()
        return result

    def _sync_active_dataset(self):
        ds = self._datasets_mgr.active_dataset
        if ds:
            self._loader._df, self._loader._lazy_df = ds.df, ds.lazy_df
            self._loader._source, self._loader._profile = ds.source, ds.profile

    def clear_all_datasets(self):
        """Remove all datasets and reset the loader's state to an empty state."""
        self._clear_cache()
        self._datasets_mgr.clear_all_datasets()
        self._loader._df = self._loader._lazy_df = None
        self._loader._source = self._loader._profile = None

    # -- ComparisonEngine delegation ------------------------------------------

    def align_datasets(self, dataset_ids, key_column, fill_strategy="null"):
        """Align multiple datasets on a shared key column, filling missing values according to the strategy.

        Args:
            dataset_ids: List of dataset ID strings to align.
            key_column: Column name used as the join key across all datasets.
            fill_strategy: How to fill missing values after alignment; "null" leaves them as null.

        Returns:
            A Polars DataFrame with all datasets merged and aligned on the key column.
        """
        return self._comparison.align_datasets(dataset_ids, key_column, fill_strategy)

    def calculate_difference(self, dataset_a_id, dataset_b_id, value_column, key_column=None):
        """Compute the row-wise difference between a value column in two datasets.

        Args:
            dataset_a_id: ID string of the first (base) dataset.
            dataset_b_id: ID string of the second (comparison) dataset.
            value_column: Name of the numeric column to subtract.
            key_column: Optional column to align rows before differencing; uses positional alignment if None.

        Returns:
            A Polars DataFrame with the original values and their computed differences.
        """
        return self._comparison.calculate_difference(dataset_a_id, dataset_b_id, value_column, key_column)

    def get_comparison_statistics(self, dataset_ids, value_column):
        """Gather descriptive statistics for a value column across multiple datasets for side-by-side comparison.

        Args:
            dataset_ids: List of dataset ID strings to include.
            value_column: Name of the column to summarise in each dataset.

        Returns:
            A dict mapping dataset ID to its statistics dict for the given column.
        """
        return self._comparison.get_comparison_statistics(dataset_ids, value_column)

    def merge_datasets(self, dataset_ids, key_column=None, how="full"):
        """Merge multiple datasets into a single DataFrame using the specified join strategy.

        Args:
            dataset_ids: List of dataset ID strings to merge.
            key_column: Column name to join on; if None, datasets are concatenated vertically.
            how: Join type string (e.g., "full", "inner", "left").

        Returns:
            A merged Polars DataFrame.
        """
        return self._comparison.merge_datasets(dataset_ids, key_column, how)

    def perform_statistical_test(self, dataset_a_id, dataset_b_id, value_column, test_type="auto"):
        """Run a statistical significance test comparing a numeric column between two datasets.

        Args:
            dataset_a_id: ID string of the first dataset.
            dataset_b_id: ID string of the second dataset.
            value_column: Name of the numeric column to test.
            test_type: Test to run ("auto", "ttest", "mannwhitney", or "ks"); "auto" selects based on normality.

        Returns:
            A dict with the test name, statistic, p-value, and a human-readable interpretation.

        Raises:
            ImportError: If scipy is not installed.
        """
        return self._comparison.perform_statistical_test(dataset_a_id, dataset_b_id, value_column, test_type)

    def calculate_correlation(self, dataset_a_id, dataset_b_id, column_a, column_b=None, method="pearson"):
        """Calculate the correlation coefficient between columns in two datasets.

        Args:
            dataset_a_id: ID string of the first dataset.
            dataset_b_id: ID string of the second dataset.
            column_a: Column name from the first dataset (and from the second if column_b is None).
            column_b: Column name from the second dataset; defaults to column_a if not provided.
            method: Correlation method to use ("pearson" or "spearman").

        Returns:
            A dict containing the correlation coefficient and p-value.

        Raises:
            ImportError: If scipy is not installed.
        """
        return self._comparison.calculate_correlation(dataset_a_id, dataset_b_id, column_a, column_b, method)

    def calculate_descriptive_comparison(self, dataset_ids, value_column):
        """Produce a structured descriptive comparison of a value column across multiple datasets.

        Args:
            dataset_ids: List of dataset ID strings to compare.
            value_column: Name of the column to describe in each dataset.

        Returns:
            A dict mapping dataset ID to a descriptive statistics summary dict.
        """
        return self._comparison.calculate_descriptive_comparison(dataset_ids, value_column)

    def get_normality_test(self, dataset_id, value_column):
        """Test whether a column's distribution is approximately normal using the Shapiro-Wilk test.

        Args:
            dataset_id: ID string of the dataset containing the column.
            value_column: Name of the numeric column to test.

        Returns:
            A dict with the test statistic, p-value, and a boolean indicating normality.

        Raises:
            ImportError: If scipy is not installed.
        """
        return self._comparison.get_normality_test(dataset_id, value_column)

    # -- clear ----------------------------------------------------------------

    def recommend_chart_type(
        self,
        x_col: Optional[str],
        y_cols: List[str],
        group_cols: Optional[List[str]] = None,
    ) -> List[tuple]:
        """데이터 특성 분석 후 추천 차트 타입 반환 (최대 3개, 이유 포함).

        Returns list of (ChartType, reason_str) tuples.
        """
        if self.df is None:
            return []

        from .state import ChartType

        recommendations: list = []
        group_cols = group_cols or []

        x_is_cat = self.is_column_categorical(x_col) if x_col else False
        x_is_time = False
        if x_col:
            col_lower = x_col.lower()
            if "time" in col_lower or "date" in col_lower:
                x_is_time = True
            else:
                dt = self.dtypes.get(x_col, "")
                if isinstance(dt, str) and dt.startswith("datetime"):
                    x_is_time = True
                elif hasattr(dt, "__str__") and "datetime" in str(dt).lower():
                    x_is_time = True

        n_rows = len(self.df) if self.df is not None else 0
        n_y = len(y_cols)
        has_groups = bool(group_cols)

        if x_is_time:
            recommendations.append((ChartType.LINE, "시계열 데이터 → 라인 차트"))
            if n_y >= 2:
                recommendations.append((ChartType.AREA, "다중 시계열 → 영역 차트"))
        elif x_is_cat:
            recommendations.append((ChartType.BAR, "카테고리 데이터 → 바 차트"))
            if has_groups:
                recommendations.append((ChartType.STACKED_BAR, "그룹 카테고리 → 누적 바"))
        elif n_rows > 1000:
            recommendations.append((ChartType.SCATTER, "대량 데이터 → 산점도"))

        # 분포 분석
        if n_y == 1 and not x_is_time:
            recommendations.append((ChartType.HISTOGRAM, "단일 변수 분포 → 히스토그램"))
        if x_is_cat and n_y == 1:
            recommendations.append((ChartType.BOX, "카테고리별 분포 → 박스플롯"))

        # Fallback: at least one recommendation
        if not recommendations:
            if n_y >= 2:
                recommendations.append((ChartType.LINE, "다중 Y 컬럼 → 라인 차트"))
            elif n_y == 1:
                recommendations.append((ChartType.BAR, "단일 Y 컬럼 → 바 차트"))

        return recommendations[:3]

    # -- LazyFrame pipeline (F1) ---------------------------------------------

    def lazy_query(self) -> Optional[pl.LazyFrame]:
        """현재 데이터에 대한 LazyFrame 반환."""
        if self.df is None:
            return None
        return self.df.lazy()

    def execute_query(self, lazy: pl.LazyFrame) -> pl.DataFrame:
        """LazyFrame 실행."""
        return lazy.collect()

    # -- Column type casting (F3) ---------------------------------------------

    def cast_column(self, col_name: str, target_dtype) -> bool:
        """컬럼 타입을 변환한다."""
        if self.df is None or col_name not in self.df.columns:
            return False
        try:
            new_df = self.df.with_columns(pl.col(col_name).cast(target_dtype))
            self.update_dataframe(new_df)
            from .transform_chain import TransformStep
            self._transform_chain.add(TransformStep(
                name=f"Cast '{col_name}' to {target_dtype}",
                operation='cast',
                params={'column': col_name, 'dtype': str(target_dtype)},
                timestamp=time.time(),
            ))
            return True
        except Exception:
            return False

    # -- Data quality report (F4) ---------------------------------------------

    def data_quality_report(self) -> Dict[str, Any]:
        """null 비율, 중복 행, 타입별 통계."""
        if self.df is None:
            return {}
        df = self.df
        row_count = len(df)
        return {
            'row_count': row_count,
            'col_count': len(df.columns),
            'null_counts': {col: df[col].null_count() for col in df.columns},
            'null_pct': {col: df[col].null_count() / max(row_count, 1) * 100 for col in df.columns},
            'duplicate_rows': row_count - len(df.unique()),
            'dtypes': dict(zip(df.columns, [str(d) for d in df.dtypes])),
        }

    # -- Virtual columns (F6) -------------------------------------------------

    def add_virtual_column(self, name: str, expr: pl.Expr) -> bool:
        """가상 컬럼 추가."""
        if self.df is None:
            return False
        try:
            new_df = self.df.with_columns(expr.alias(name))
            self.update_dataframe(new_df)
            self._virtual_columns.add(name)
            return True
        except Exception:
            return False

    # -- State sync (7) -------------------------------------------------------

    def sync_dataset_state(self) -> None:
        """DatasetManager → loader 동기화."""
        ds = self._datasets_mgr.active_dataset
        if ds:
            self._loader._df = ds.df
            self._loader._lazy_df = ds.lazy_df
            self._loader._source = ds.source
            self._loader._profile = ds.profile

    # -- Lineage (F8) ---------------------------------------------------------

    @property
    def lineage(self) -> List[Dict[str, Any]]:
        """전체 변환 이력."""
        return self._transform_chain.get_lineage()

    @property
    def transform_chain(self):
        """TransformChain 인스턴스."""
        return self._transform_chain

    # -- MAX_DATASETS / MAX_TOTAL_MEMORY / DEFAULT_COLORS → DatasetManager ----

    @property
    def MAX_DATASETS(self):
        """Maximum number of datasets that can be loaded simultaneously."""
        return self._datasets_mgr.MAX_DATASETS

    @property
    def MAX_TOTAL_MEMORY(self):
        """Maximum combined memory (in bytes) allowed across all loaded datasets."""
        return self._datasets_mgr.MAX_TOTAL_MEMORY

    @property
    def DEFAULT_COLORS(self):
        """Ordered list of default hex color strings assigned to new datasets."""
        return self._datasets_mgr.DEFAULT_COLORS

    # -- clear ----------------------------------------------------------------

    def clear(self):
        """데이터 클리어."""
        self._loader.clear()
        self._indexes.clear()
        self._cache.clear()
        self._transform_chain.clear()
        self._virtual_columns.clear()
        self._current_file_path = None
