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
from .exceptions import QueryError
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
        if not isinstance(col_name, str) or not col_name.strip():
            raise ValueError(f"column name must be a non-empty string, got {col_name!r}")
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
        """Detect the delimiter used in a delimited text file by sampling the first few lines."""
        return self._loader.detect_delimiter(path, encoding, sample_lines)

    def set_precision_mode(self, mode):
        """Set the precision mode controlling how floating-point columns are handled during loading."""
        self._loader.set_precision_mode(mode)

    def add_precision_column(self, column):
        """Mark a specific column to be treated with high-precision numeric handling."""
        self._loader.add_precision_column(column)

    def cancel_loading(self):
        """Signal the file loader to abort any in-progress load operation."""
        self._loader.cancel_loading()

    def set_window(self, start, size):
        """Configure windowed loading to read a row slice from the source file."""
        return self._loader.set_window(start, size)

    def load_lazy(self, path, **kw):
        """Load a file as a Polars LazyFrame without immediately collecting it into memory."""
        return self._loader.load_lazy(path, **kw)

    def collect_lazy(self, limit=None, optimize_memory=True):
        """Collect the current LazyFrame into a DataFrame, optionally limiting rows."""
        with get_metrics().timed_operation("engine.collect_lazy"):
            return self._loader.collect_lazy(limit, optimize_memory)

    def query_lazy(self, expr):
        """Apply a Polars expression to the current LazyFrame and return the filtered LazyFrame."""
        return self._loader.query_lazy(expr)

    def _update_progress(self, **kw): self._loader._update_progress(**kw)
    def _is_precision_sensitive_column(self, c): return self._loader._is_precision_sensitive_column(c)

    def load_file(self, path: str, **kwargs) -> bool:
        """Load a file into the engine, clearing cache first."""
        with get_metrics().timed_operation("engine.load_file"):
            self._clear_cache()
            return self._loader.load_file(path, **kwargs)

    def append_rows(self, file_path: str, new_row_count: int) -> bool:
        """Incrementally append new rows from the end of a file; falls back to full reload on error."""
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
            logger.warning("data_engine.append_rows.failed, falling back to full reload", extra={"path": str(file_path)}, exc_info=True)
            return self.load_file(file_path, optimize_memory=True)

    @staticmethod
    def is_binary_etl(path: str) -> bool:
        """Return True if the file is a binary ETL format requiring the ETL parser."""
        from .file_loader import FileLoader as FL
        return FL.is_binary_etl(path)

    @staticmethod
    def parse_etl_binary(path: str) -> pl.DataFrame:
        """Parse a binary ETL file and return its contents as a Polars DataFrame."""
        from .file_loader import FileLoader as FL
        return FL.parse_etl_binary(path)

    # -- DataQuery delegation -------------------------------------------------

    def get_filtered_df(self, filter_map: Dict[str, list]) -> Optional[pl.DataFrame]:
        """``{column: [values]}`` 필터 맵을 Polars lazy 레이어에서 처리 후 반환한다."""
        return self._query.filter_by_map(self.df, filter_map)

    def filter(self, column, operator, value):
        """Filter the active DataFrame on a single column."""
        return self._query.filter(self.df, column, operator, value)

    def sort(self, columns, descending=False):
        """Sort the active DataFrame by one or more columns."""
        return self._query.sort(self.df, columns, descending)

    def group_aggregate(self, group_columns, value_columns, agg_funcs):
        """Group and aggregate the active DataFrame."""
        return self._query.group_aggregate(self.df, group_columns, value_columns, agg_funcs)

    def get_statistics(self, column):
        """Compute descriptive statistics for a single column."""
        return self._query.get_statistics(self.df, column, self._loader._lazy_df, self._loader.is_windowed, self._cache)

    def get_all_statistics(self, value_columns=None):
        """Compute descriptive statistics for all (or a subset of) numeric columns."""
        return self._query.get_all_statistics(self.df, value_columns, self._loader._lazy_df, self._loader.is_windowed, self._cache)

    def get_full_profile_summary(self):
        """Return a comprehensive profile summary combining per-column statistics and the DataProfile."""
        return self._query.get_full_profile_summary(self.df, self._loader.profile, self._loader._lazy_df, self._loader.is_windowed)

    def is_column_categorical(self, col, max_unique_ratio=0.05, max_unique_count=100):
        """Determine whether a column should be treated as categorical based on its cardinality."""
        return self._query.is_column_categorical(self.df, col, max_unique_ratio, max_unique_count)

    def get_unique_values(self, col, limit=1000):
        """Return the distinct values present in a column, up to a specified limit."""
        return self._query.get_unique_values(self.df, col, limit)

    def sample(self, n=10000, seed=42):
        """Draw a random sample of rows from the active DataFrame."""
        return self._query.sample(self.df, n, seed)

    def get_slice(self, start, end):
        """Return a contiguous row slice from the active DataFrame."""
        return self._query.get_slice(self.df, start, end)

    def search(self, query, columns=None, case_sensitive=False, max_columns=20):
        """Search for a string query across columns in the active DataFrame."""
        return self._query.search(self.df, query, columns, case_sensitive, max_columns)

    def create_index(self, column):
        """Build and cache an index for a column (deprecated — use Polars native filtering)."""
        warnings.warn("create_index is deprecated. Use Polars native filtering.", DeprecationWarning, stacklevel=2)
        if self.df is None or column not in self.df.columns:
            return
        self._indexes[column] = self._query.create_index(self.df, column)

    # -- DataExporter delegation ----------------------------------------------

    def export_csv(self, path, selected_rows=None):
        """Export the active DataFrame (or a row subset) to a CSV file."""
        if self.df is not None:
            self._exporter.export_csv(self.df, path, selected_rows)

    def export_excel(self, path, selected_rows=None):
        """Export the active DataFrame (or a row subset) to an Excel (.xlsx) file."""
        if self.df is not None:
            self._exporter.export_excel(self.df, path, selected_rows)

    def export_parquet(self, path, selected_rows=None):
        """Export the active DataFrame (or a row subset) to a Parquet file."""
        if self.df is not None:
            self._exporter.export_parquet(self.df, path, selected_rows)

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
        except Exception as e:
            raise QueryError(
                f"Cannot cast column '{col_name}' to {target_dtype}",
                operation="cast_column",
                context={"column": col_name, "dtype": str(target_dtype)},
            ) from e

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

    # -- clear ----------------------------------------------------------------

    def clear(self):
        """데이터 클리어."""
        self._loader.clear()
        self._indexes.clear()
        self._cache.clear()
        self._transform_chain.clear()
        self._virtual_columns.clear()
        self._current_file_path = None
