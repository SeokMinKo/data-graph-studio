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

from .constants import LRU_CACHE_MAXSIZE
from .data_engine_dataset_mixin import DatasetMixin
from .data_engine_analysis_mixin import AnalysisMixin
from .exceptions import QueryError, ValidationError
from .metrics import get_metrics

logger = logging.getLogger(__name__)


def _import_submodules():
    """하위 모듈을 지연 임포트한다."""
    from .file_loader import FileLoader
    from .data_query import DataQuery
    from .data_exporter import DataExporter
    from .dataset_manager import DatasetManager
    from .comparison_engine import ComparisonEngine
    return FileLoader, DataQuery, DataExporter, DatasetManager, ComparisonEngine


class DataEngine(DatasetMixin, AnalysisMixin):
    """빅데이터 처리 엔진 Facade.

    Attributes:
        _loader: 파일 I/O 담당.
        _query: 조회/변환/통계 담당.
        _exporter: 내보내기 담당.
        _datasets_mgr: 멀티 데이터셋 관리.
        _comparison: 비교 분석.
        _cache: LRU 캐시 (maxsize=128).
    """

    def __init__(self, precision_mode: PrecisionMode = PrecisionMode.AUTO):
        """Initialize all sub-components of the DataEngine facade.

        Input: precision_mode — PrecisionMode, controls float precision handling (default AUTO)
        Output: None
        Invariants: all sub-components are freshly initialized; no data is loaded; cache is empty
        """
        from .transform_chain import TransformChain

        FL, DQ, DE, DM, CE = _import_submodules()
        self._loader = FL(precision_mode)
        self._query = DQ()
        self._exporter = DE()
        self._datasets_mgr = DM(self._loader)
        self._comparison = CE(self._datasets_mgr)
        self._cache: OrderedDict = OrderedDict()
        self._cache_maxsize: int = LRU_CACHE_MAXSIZE
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
        """Active DataFrame: returns the active dataset's DataFrame, or the loader's DataFrame if no dataset is active.

        Output: Optional[pl.DataFrame] — the current working DataFrame, or None if nothing is loaded
        """
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
        """Update the active DataFrame, sync with the active dataset, and clear the cache.

        Input:
            df: New DataFrame to set, or None to clear the loaded data.

        Output:
            None. Side effects: loader and active dataset df are updated, cache is cleared.

        Raises:
            None

        Invariants:
            - After call, self.df returns the same object passed as df.
            - Cache is always cleared regardless of df value.
        """
        self._loader._df = df
        # active dataset sync
        if self._datasets_mgr and self._datasets_mgr.active_dataset:
            self._datasets_mgr.active_dataset.df = df
        self._clear_cache()

    def drop_column(self, col_name: str) -> None:
        """Remove a column from the active DataFrame and record the step in the transform chain.

        Input:
            col_name: Non-empty string name of the column to remove; must exist in the
                active DataFrame (silently no-ops if DataFrame is None or column absent).

        Output:
            None. Side effects: active DataFrame loses the specified column, transform chain
            is updated, virtual_columns set is updated.

        Raises:
            ValidationError: if col_name is not a non-empty string.

        Invariants:
            - Column count decreases by exactly 1 when column existed.
            - All other columns are unchanged.
        """
        if not isinstance(col_name, str) or not col_name.strip():
            raise ValidationError(
                f"column name must be a non-empty string, got {col_name!r}",
                operation="drop_column",
                context={"col_name": col_name},
            )
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
        """Current DataProfile for the loaded file, or None if no file is loaded.

        Output: Optional[DataProfile] — column-level statistics snapshot, or None
        """
        return self._loader.profile

    @property
    def progress(self) -> LoadingProgress:
        """Current LoadingProgress snapshot for any in-progress file load operation.

        Output: LoadingProgress — live progress state; never None
        """
        return self._loader.progress

    @property
    def is_loaded(self) -> bool:
        """True if a DataFrame is currently loaded and available.

        Output: bool — True when df is not None
        """
        return self.df is not None

    @property
    def row_count(self) -> int:
        """Total number of rows: uses the full file row count when windowed, otherwise the in-memory DataFrame length.

        Output: int — row count, never negative
        """
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

    def set_progress_callback(self, cb) -> None:
        """Register a callback to receive LoadingProgress updates during file loading.

        Input:
            cb: Callable that accepts a LoadingProgress argument; called periodically
                during load operations.

        Output:
            None.

        Raises:
            None

        Invariants:
            - Only one callback is active at a time; calling again replaces the previous.
        """
        self._loader.set_progress_callback(cb)

    def detect_file_type(self, path: str) -> FileType:
        """Detect and return the FileType for the file at the given path based on its extension and content.

        Input:
            path: Non-empty filesystem path string pointing to an existing file.

        Output:
            FileType enum member representing the detected format (e.g., CSV, PARQUET, EXCEL).

        Raises:
            None

        Invariants:
            - Does not modify engine state.
            - Returns a valid FileType for any path; falls back to a default if format is unknown.
        """
        return self._loader.detect_file_type(path)

    def detect_delimiter(self, path, encoding="utf-8", sample_lines=10):
        """Detect the delimiter used in a delimited text file by sampling the first few lines.

        Input:
            path: Path to the delimited text file.
            encoding: Character encoding to use when reading the sample (default "utf-8").
            sample_lines: Number of lines to inspect for delimiter detection (default 10).

        Output:
            Single-character string representing the detected delimiter (e.g. ",", "\\t", ";").

        Raises:
            None

        Invariants:
            - Does not modify engine state.
            - sample_lines >= 1.
        """
        return self._loader.detect_delimiter(path, encoding, sample_lines)

    def set_precision_mode(self, mode) -> None:
        """Set the precision mode controlling how floating-point columns are handled during loading.

        Input:
            mode: PrecisionMode enum value (AUTO, HIGH, or STANDARD).

        Output:
            None.

        Raises:
            None

        Invariants:
            - Affects only subsequently loaded files, not the current DataFrame.
        """
        self._loader.set_precision_mode(mode)

    def add_precision_column(self, column) -> None:
        """Mark a specific column to be treated with high-precision numeric handling.

        Input:
            column: Non-empty string column name to flag for high-precision loading.

        Output:
            None.

        Raises:
            None

        Invariants:
            - Precision column set is append-only via this method.
            - Affects only subsequently loaded files.
        """
        self._loader.add_precision_column(column)

    def cancel_loading(self) -> None:
        """Signal the file loader to abort any in-progress load operation.

        Input:
            None

        Output:
            None. Side effect: sets the internal cancel flag so the loader exits early.

        Raises:
            None

        Invariants:
            - Safe to call when no load is in progress (no-op).
        """
        self._loader.cancel_loading()

    def set_window(self, start, size):
        """Configure windowed loading to read a row slice from the source file.

        Input:
            start: Zero-based index of the first row to include (>= 0).
            size: Maximum number of rows to include in the window (>= 1).

        Output:
            Return value delegated from FileLoader.set_window().

        Raises:
            None

        Invariants:
            - is_windowed becomes True after this call.
            - window_start == start, window_size == size after the call.
        """
        return self._loader.set_window(start, size)

    def load_lazy(self, path, **kw):
        """Load a file as a Polars LazyFrame without immediately collecting it into memory.

        Input:
            path: Filesystem path to the file to load.
            **kw: Additional keyword arguments forwarded to FileLoader.load_lazy().

        Output:
            True on success, False on failure (delegated from FileLoader).

        Raises:
            DataLoadError: if the file cannot be parsed or is unsupported.

        Invariants:
            - has_lazy becomes True on success.
            - df remains None until collect_lazy() is called.
        """
        return self._loader.load_lazy(path, **kw)

    def collect_lazy(self, limit=None, optimize_memory=True):
        """Collect the current LazyFrame into a DataFrame, optionally limiting rows.

        Input:
            limit: Maximum number of rows to collect, or None to collect all rows.
            optimize_memory: Whether to apply memory-optimisation passes before collecting
                (default True).

        Output:
            True if the LazyFrame was collected successfully, False if no LazyFrame is available.

        Raises:
            None

        Invariants:
            - Row count <= limit when limit is not None.
            - Operation is timed via MetricsCollector.timed_operation("engine.collect_lazy").
        """
        with get_metrics().timed_operation("engine.collect_lazy"):
            return self._loader.collect_lazy(limit, optimize_memory)

    def query_lazy(self, expr):
        """Apply a Polars expression to the current LazyFrame and return the filtered LazyFrame.

        Input:
            expr: A Polars expression (pl.Expr) to filter or transform the LazyFrame.

        Output:
            Filtered pl.LazyFrame, or None if no LazyFrame is available.

        Raises:
            None

        Invariants:
            - Does not collect data; result is still lazy.
        """
        return self._loader.query_lazy(expr)

    def _update_progress(self, **kw): self._loader._update_progress(**kw)
    def _is_precision_sensitive_column(self, c): return self._loader._is_precision_sensitive_column(c)

    def load_file(self, path: str, **kwargs) -> bool:
        """Load a file into the engine, clearing cache first.

        Input:
            path: Non-empty filesystem path to the file to load.
            **kwargs: Additional options forwarded to FileLoader.load_file()
                (e.g., encoding, delimiter, optimize_memory).

        Output:
            True if the file was loaded successfully, False otherwise.

        Raises:
            DataLoadError: if the file format is unsupported or parsing fails.

        Invariants:
            - Cache is cleared before loading begins.
            - is_loaded becomes True on success.
            - Operation is timed via MetricsCollector.timed_operation("engine.load_file").
        """
        with get_metrics().timed_operation("engine.load_file"):
            self._clear_cache()
            return self._loader.load_file(path, **kwargs)

    def append_rows(self, file_path: str, new_row_count: int) -> bool:
        """Incrementally append new rows from the end of a file; falls back to full reload on error.

        Input:
            file_path: Path to the CSV file containing the full updated data.
            new_row_count: Number of rows from the tail of file_path to append (>= 1).

        Output:
            True on success (either incremental append or full reload), False if full reload fails.

        Raises:
            None (exceptions trigger fallback full reload).

        Invariants:
            - If current df is None, performs a full load instead of incremental append.
            - Row count after successful append equals original row count + new_row_count.
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
        except (pl.exceptions.PolarsError, OSError):
            logger.warning("data_engine.append_rows.failed, falling back to full reload", extra={"path": str(file_path)}, exc_info=True)
            return self.load_file(file_path, optimize_memory=True)

    @staticmethod
    def is_binary_etl(path: str) -> bool:
        """Return True if the file is a binary ETL format requiring the ETL parser.

        Input:
            path: Filesystem path string to inspect.

        Output:
            True if the file uses the binary ETL format, False otherwise.

        Raises:
            None

        Invariants:
            - Pure inspection; does not modify any state.
        """
        from .file_loader import FileLoader as FL
        return FL.is_binary_etl(path)

    @staticmethod
    def parse_etl_binary(path: str) -> pl.DataFrame:
        """Parse a binary ETL file and return its contents as a Polars DataFrame.

        Input:
            path: Filesystem path to the binary ETL file; must exist and be a valid ETL file.

        Output:
            pl.DataFrame containing the parsed records.

        Raises:
            DataLoadError: if the file cannot be parsed as a valid ETL binary.

        Invariants:
            - Returned DataFrame schema matches the ETL file's declared schema.
        """
        from .file_loader import FileLoader as FL
        return FL.parse_etl_binary(path)

    # -- DataQuery delegation -------------------------------------------------

    def get_filtered_df(self, filter_map: Dict[str, list]) -> Optional[pl.DataFrame]:
        """Apply a ``{column: [values]}`` filter map via Polars lazy layer and return the result.

        Input:
            filter_map: Dict mapping column names to lists of allowed values.
                Keys must be existing column names in the active DataFrame.

        Output:
            Filtered pl.DataFrame with the same columns, or None if no data is loaded.
            Missing columns in filter_map are silently ignored.

        Raises:
            None

        Invariants:
            - Result row count <= active DataFrame row count.
            - Column set is unchanged.
        """
        return self._query.filter_by_map(self.df, filter_map)

    def filter(self, column, operator, value):
        """Filter the active DataFrame on a single column.

        Input:
            column: Name of the column to filter on; must exist in the active DataFrame.
            operator: Filter operator string (e.g., "eq", "gt", "contains").
            value: Value to compare against; type must be compatible with the column dtype.

        Output:
            Filtered pl.DataFrame, or None if no data is loaded.

        Raises:
            QueryError: if operator is invalid or column does not exist.

        Invariants:
            - Result row count <= active DataFrame row count.
            - Column set is unchanged.
        """
        return self._query.filter(self.df, column, operator, value)

    def sort(self, columns, descending=False):
        """Sort the active DataFrame by one or more columns.

        Input:
            columns: Column name string or list of column name strings to sort by.
            descending: If True, sort in descending order (default False).

        Output:
            Sorted pl.DataFrame with the same shape, or None if no data is loaded.

        Raises:
            pl.exceptions.InvalidOperationError: if any column does not exist in the DataFrame.

        Invariants:
            - Row count and column set are unchanged.
        """
        return self._query.sort(self.df, columns, descending)

    def group_aggregate(self, group_columns, value_columns, agg_funcs):
        """Group and aggregate the active DataFrame.

        Input:
            group_columns: List of column names to group by.
            value_columns: List of column names to aggregate.
            agg_funcs: List of aggregation function strings (e.g., ["sum", "mean"]).

        Output:
            Aggregated pl.DataFrame; one row per unique combination of group_columns.

        Raises:
            QueryError: if any specified column does not exist.

        Invariants:
            - Result row count <= active DataFrame row count.
            - Result contains group_columns plus one column per (value_col, agg_func) pair.
        """
        return self._query.group_aggregate(self.df, group_columns, value_columns, agg_funcs)

    def get_statistics(self, column):
        """Compute descriptive statistics for a single column.

        Input:
            column: Name of the column to analyse; must exist in the active DataFrame.

        Output:
            Dict mapping stat name to value (e.g., mean, std, min, max, q1, q3),
            or None if no data is loaded. Returns {} silently if column does not exist.

        Raises:
            None

        Invariants:
            - Does not modify engine state.
            - Result is cached; repeat calls with the same column are O(1).
        """
        return self._query.get_statistics(self.df, column, self._loader._lazy_df, self._loader.is_windowed, self._cache)

    def get_all_statistics(self, value_columns=None):
        """Compute descriptive statistics for all (or a subset of) numeric columns.

        Input:
            value_columns: Optional list of column names to restrict to; if None, all
                numeric columns are included.

        Output:
            Dict mapping column name to its statistics dict, or None if no data is loaded.
            Missing or non-existent columns are silently skipped.

        Raises:
            None

        Invariants:
            - Does not modify engine state.
            - Only numeric columns produce entries; non-numeric columns are skipped.
        """
        return self._query.get_all_statistics(self.df, value_columns, self._loader._lazy_df, self._loader.is_windowed, self._cache)

    def get_full_profile_summary(self):
        """Return a comprehensive profile summary combining per-column statistics and the DataProfile.

        Input:
            None

        Output:
            Dict with profile-level metadata and per-column statistics, or None if no data is loaded.

        Raises:
            None

        Invariants:
            - Does not modify engine state.
        """
        return self._query.get_full_profile_summary(self.df, self._loader.profile, self._loader._lazy_df, self._loader.is_windowed)

    def is_column_categorical(self, col, max_unique_ratio=0.05, max_unique_count=100):
        """Determine whether a column should be treated as categorical based on its cardinality.

        Input:
            col: Column name string; must exist in the active DataFrame.
            max_unique_ratio: Fraction threshold — columns with unique/total <= this are
                categorical (default 0.05).
            max_unique_count: Absolute threshold — columns with unique count <= this are
                categorical (default 100).

        Output:
            True if the column is classified as categorical, False otherwise.

        Raises:
            None

        Invariants:
            - Does not modify engine state.
            - Returns False if no data is loaded or column does not exist.
        """
        return self._query.is_column_categorical(self.df, col, max_unique_ratio, max_unique_count)

    def get_unique_values(self, col, limit=1000):
        """Return the distinct values present in a column, up to a specified limit.

        Input:
            col: Column name string; must exist in the active DataFrame.
            limit: Maximum number of distinct values to return (default 1000).

        Output:
            List of unique values for the column, or an empty list if no data is loaded
            or if the column does not exist.

        Raises:
            None

        Invariants:
            - Result length <= limit.
            - Does not modify engine state.
        """
        return self._query.get_unique_values(self.df, col, limit)

    def sample(self, n=10000, seed=42):
        """Draw a random sample of rows from the active DataFrame.

        Input:
            n: Number of rows to sample (default 10000); capped at the actual row count.
            seed: Random seed for reproducibility (default 42).

        Output:
            pl.DataFrame of sampled rows with the same columns, or None if no data is loaded.

        Raises:
            None

        Invariants:
            - Result row count <= min(n, active row count).
            - Column set is unchanged.
        """
        return self._query.sample(self.df, n, seed)

    def get_slice(self, start, end):
        """Return a contiguous row slice from the active DataFrame.

        Input:
            start: Zero-based index of the first row to include (>= 0).
            end: Zero-based exclusive end index (end > start).

        Output:
            pl.DataFrame slice with rows [start, end), or None if no data is loaded.

        Raises:
            None

        Invariants:
            - Result row count == min(end, row_count) - start (or 0 if out of range).
            - Column set is unchanged.
        """
        return self._query.get_slice(self.df, start, end)

    def search(self, query, columns=None, case_sensitive=False, max_columns=20):
        """Search for a string query across columns in the active DataFrame.

        Input:
            query: Non-empty search string.
            columns: Optional list of column names to restrict the search to; if None,
                up to max_columns columns are searched.
            case_sensitive: If True, search is case-sensitive (default False).
            max_columns: Maximum number of columns to scan (default 20).

        Output:
            pl.DataFrame of matching rows, or None if no data is loaded.

        Raises:
            None

        Invariants:
            - Result row count <= active DataFrame row count.
            - Column set is unchanged.
        """
        return self._query.search(self.df, query, columns, case_sensitive, max_columns)

    def create_index(self, column) -> None:
        """Build and cache an index for a column (deprecated — use Polars native filtering).

        Input:
            column: Name of the column to index; must exist in the active DataFrame.

        Output:
            None. Side effect: index stored in self._indexes[column].

        Raises:
            DeprecationWarning: always raised as a warning at call time.

        Invariants:
            - No-op if no data is loaded or column does not exist.
        """
        warnings.warn("create_index is deprecated. Use Polars native filtering.", DeprecationWarning, stacklevel=2)
        if self.df is None or column not in self.df.columns:
            return
        self._indexes[column] = self._query.create_index(self.df, column)

    # -- DataExporter delegation ----------------------------------------------

    def export_csv(self, path, selected_rows=None) -> None:
        """Export the active DataFrame (or a row subset) to a CSV file.

        Input:
            path: Destination filesystem path string for the output CSV file.
            selected_rows: Optional list of zero-based row indices to export; if None,
                all rows are exported.

        Output:
            None. Side effect: CSV file is written to path.

        Raises:
            ExportError: if the file cannot be written.

        Invariants:
            - No-op if no data is loaded.
            - Exported column set matches the active DataFrame.
        """
        if self.df is not None:
            self._exporter.export_csv(self.df, path, selected_rows)

    def export_excel(self, path, selected_rows=None) -> None:
        """Export the active DataFrame (or a row subset) to an Excel (.xlsx) file.

        Input:
            path: Destination filesystem path string for the output .xlsx file.
            selected_rows: Optional list of zero-based row indices to export; if None,
                all rows are exported.

        Output:
            None. Side effect: Excel file is written to path.

        Raises:
            ExportError: if the file cannot be written or openpyxl is not installed.

        Invariants:
            - No-op if no data is loaded.
            - Exported column set matches the active DataFrame.
        """
        if self.df is not None:
            self._exporter.export_excel(self.df, path, selected_rows)

    def export_parquet(self, path, selected_rows=None) -> None:
        """Export the active DataFrame (or a row subset) to a Parquet file.

        Input:
            path: Destination filesystem path string for the output .parquet file.
            selected_rows: Optional list of zero-based row indices to export; if None,
                all rows are exported.

        Output:
            None. Side effect: Parquet file is written to path.

        Raises:
            ExportError: if the file cannot be written.

        Invariants:
            - No-op if no data is loaded.
            - Exported column set matches the active DataFrame.
        """
        if self.df is not None:
            self._exporter.export_parquet(self.df, path, selected_rows)

    # -- LazyFrame pipeline (F1) ---------------------------------------------

    def lazy_query(self) -> Optional[pl.LazyFrame]:
        """Return a LazyFrame built from the current active DataFrame.

        Input:
            None

        Output:
            pl.LazyFrame wrapping the active DataFrame, or None if no data is loaded.

        Raises:
            None

        Invariants:
            - Does not modify engine state.
            - Returned LazyFrame reflects the DataFrame at call time; later mutations
              to the active DataFrame are not reflected.
        """
        if self.df is None:
            return None
        return self.df.lazy()

    def execute_query(self, lazy: pl.LazyFrame) -> pl.DataFrame:
        """Collect a LazyFrame into a materialised DataFrame.

        Input:
            lazy: A valid pl.LazyFrame to execute; must not be None.

        Output:
            pl.DataFrame resulting from collecting the LazyFrame.

        Raises:
            None

        Invariants:
            - Schema of the result matches the schema declared by the LazyFrame.
        """
        return lazy.collect()

    # -- Column type casting (F3) ---------------------------------------------

    def cast_column(self, col_name: str, target_dtype) -> bool:
        """Cast a column to a new Polars dtype and record the step in the transform chain.

        Input:
            col_name: Name of the column to cast; must exist in the active DataFrame.
            target_dtype: Target Polars dtype (e.g., pl.Int64, pl.Float32).

        Output:
            True if the cast succeeded, False if no data is loaded or column does not exist.

        Raises:
            QueryError: if the cast operation fails (e.g., incompatible dtype).

        Invariants:
            - Column count and all other columns are unchanged on success.
            - Transform chain always records the step on success.
        """
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
        except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, pl.exceptions.SchemaError, TypeError) as e:
            raise QueryError(
                f"Cannot cast column '{col_name}' to {target_dtype}",
                operation="cast_column",
                context={"column": col_name, "dtype": str(target_dtype)},
            ) from e

    # -- State sync (7) -------------------------------------------------------

    def sync_dataset_state(self) -> None:
        """Synchronise loader state from the active dataset in DatasetManager.

        Input:
            None

        Output:
            None. Side effect: loader's _df, _lazy_df, _source, and _profile are set
            to match the active dataset's values.

        Raises:
            None

        Invariants:
            - No-op if no dataset is currently active.
            - After the call, loader and active dataset share the same DataFrame reference.
        """
        ds = self._datasets_mgr.active_dataset
        if ds:
            self._loader._df = ds.df
            self._loader._lazy_df = ds.lazy_df
            self._loader._source = ds.source
            self._loader._profile = ds.profile

    # -- Lineage (F8) ---------------------------------------------------------

    @property
    def lineage(self) -> List[Dict[str, Any]]:
        """Return the full ordered list of transform steps applied since the last clear.

        Output: List[Dict[str, Any]] — each entry is a serialised TransformStep snapshot.
        Invariants: length equals the number of successful cast/drop/add operations recorded.
        """
        return self._transform_chain.get_lineage()

    @property
    def transform_chain(self):
        """Return the TransformChain instance that records all column transform steps.

        Output: TransformChain — live reference; mutate with caution.
        """
        return self._transform_chain

    # -- clear ----------------------------------------------------------------

    def clear(self) -> None:
        """Reset all engine state: loader, indexes, cache, transform chain, virtual columns, and file path.

        Input:
            None

        Output:
            None. Side effect: all internal state is cleared to its post-__init__ default.

        Raises:
            None

        Invariants:
            - After call, is_loaded is False and all collections are empty.
        """
        self._loader.clear()
        self._indexes.clear()
        self._cache.clear()
        self._transform_chain.clear()
        self._virtual_columns.clear()
        self._current_file_path = None
