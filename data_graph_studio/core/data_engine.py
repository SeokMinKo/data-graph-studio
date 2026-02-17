"""
Data Engine — Polars 기반 빅데이터 처리 엔진 (Facade)

5개 하위 모듈(FileLoader, DataQuery, DataExporter, DatasetManager,
ComparisonEngine)을 조합하여 기존 API를 100% 유지하는 Facade 패턴.

기존 import 호환:
    from data_graph_studio.core.data_engine import DataEngine, FileType, ...
"""

import warnings
import logging
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
    MAX_DATASETS = 10
    MAX_TOTAL_MEMORY = 4 * 1024 * 1024 * 1024
    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]

    def __init__(self, precision_mode: PrecisionMode = PrecisionMode.AUTO):
        FL, DQ, DE, DM, CE = _import_submodules()
        self._loader = FL(precision_mode)
        self._query = DQ()
        self._exporter = DE()
        self._datasets_mgr = DM(self._loader)
        self._comparison = CE(self._datasets_mgr)
        self._cache: Dict[str, Any] = {}
        self._cache_maxsize: int = 128
        self._indexes: Dict[str, Dict] = {}
        self._precision_mode = precision_mode

    # -- Cache ----------------------------------------------------------------

    def _evict_cache(self) -> None:
        while len(self._cache) > self._cache_maxsize:
            del self._cache[next(iter(self._cache))]

    def _clear_cache(self) -> None:
        self._cache.clear()

    # -- Properties: FileLoader -----------------------------------------------

    @property
    def df(self) -> Optional[pl.DataFrame]:
        if self._datasets_mgr.active_dataset_id:
            return self._datasets_mgr.get_dataset_df(self._datasets_mgr.active_dataset_id)
        return self._loader._df

    @property
    def _df(self) -> Optional[pl.DataFrame]:
        return self.df

    @_df.setter
    def _df(self, value: Optional[pl.DataFrame]) -> None:
        self._loader._df = value

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
        return self._loader.profile

    @property
    def progress(self) -> LoadingProgress:
        return self._loader.progress

    @property
    def is_loaded(self) -> bool:
        return self.df is not None

    @property
    def row_count(self) -> int:
        if self._loader.is_windowed and self._loader._total_rows > 0:
            return self._loader._total_rows
        return len(self.df) if self.df is not None else 0

    @property
    def column_count(self) -> int:
        df = self.df
        return len(df.columns) if df is not None else 0

    @property
    def columns(self) -> List[str]:
        df = self.df
        return df.columns if df is not None else []

    @property
    def dtypes(self) -> Dict[str, str]:
        df = self.df
        return {c: str(d) for c, d in zip(df.columns, df.dtypes)} if df is not None else {}

    @property
    def is_windowed(self) -> bool:
        return self._loader.is_windowed

    @property
    def total_rows(self) -> int:
        return self._loader.total_rows

    @property
    def window_start(self) -> int:
        return self._loader.window_start

    @property
    def window_size(self) -> int:
        return self._loader.window_size

    @property
    def has_lazy(self) -> bool:
        return self._loader.has_lazy

    # -- FileLoader delegation ------------------------------------------------

    @staticmethod
    def _normalize_encoding(encoding: str) -> str:
        from .file_loader import FileLoader as FL
        return FL._normalize_encoding(encoding)

    def set_progress_callback(self, cb): self._loader.set_progress_callback(cb)
    def detect_file_type(self, path: str) -> FileType: return self._loader.detect_file_type(path)
    def detect_delimiter(self, path, encoding="utf-8", sample_lines=10): return self._loader.detect_delimiter(path, encoding, sample_lines)
    def set_precision_mode(self, mode): self._loader.set_precision_mode(mode)
    def add_precision_column(self, column): self._loader.add_precision_column(column)
    def cancel_loading(self): self._loader.cancel_loading()
    def set_window(self, start, size): return self._loader.set_window(start, size)
    def load_lazy(self, path, **kw): return self._loader.load_lazy(path, **kw)
    def collect_lazy(self, limit=None, optimize_memory=True): return self._loader.collect_lazy(limit, optimize_memory)
    def query_lazy(self, expr): return self._loader.query_lazy(expr)
    def _update_progress(self, **kw): self._loader._update_progress(**kw)
    def _prepare_parquet_from_csv(self, *a, **kw): return self._loader._prepare_parquet_from_csv(*a, **kw)
    def _load_window_from_lazy(self, *a, **kw): return self._loader._load_window_from_lazy(*a, **kw)
    def _collect_streaming(self, lf): return self._loader._collect_streaming(lf)
    def _create_profile(self, df, t): return self._loader._create_profile(df, t)
    def _optimize_memory(self, df): return self._loader._optimize_memory(df)
    def _is_precision_sensitive_column(self, c): return self._loader._is_precision_sensitive_column(c)

    def load_file(self, path: str, **kwargs) -> bool:
        self._clear_cache()
        return self._loader.load_file(path, **kwargs)

    @staticmethod
    def is_binary_etl(path: str) -> bool:
        from .file_loader import FileLoader as FL
        return FL.is_binary_etl(path)

    @staticmethod
    def parse_etl_binary(path: str) -> pl.DataFrame:
        from .file_loader import FileLoader as FL
        return FL.parse_etl_binary(path)

    # -- DataQuery delegation -------------------------------------------------

    def filter(self, column, operator, value): return self._query.filter(self.df, column, operator, value)
    def sort(self, columns, descending=False): return self._query.sort(self.df, columns, descending)
    def group_aggregate(self, group_columns, value_columns, agg_funcs): return self._query.group_aggregate(self.df, group_columns, value_columns, agg_funcs)
    def get_statistics(self, column): return self._query.get_statistics(self.df, column, self._loader._lazy_df, self._loader.is_windowed, self._cache)
    def get_all_statistics(self, value_columns=None): return self._query.get_all_statistics(self.df, value_columns, self._loader._lazy_df, self._loader.is_windowed, self._cache)
    def get_full_profile_summary(self): return self._query.get_full_profile_summary(self.df, self._loader.profile, self._loader._lazy_df, self._loader.is_windowed)
    def is_column_categorical(self, col, max_unique_ratio=0.05, max_unique_count=100): return self._query.is_column_categorical(self.df, col, max_unique_ratio, max_unique_count)
    def get_unique_values(self, col, limit=1000): return self._query.get_unique_values(self.df, col, limit)
    def sample(self, n=10000, seed=42): return self._query.sample(self.df, n, seed)
    def get_slice(self, start, end): return self._query.get_slice(self.df, start, end)
    def search(self, query, columns=None, case_sensitive=False, max_columns=20): return self._query.search(self.df, query, columns, case_sensitive, max_columns)

    def create_index(self, column):
        warnings.warn("create_index is deprecated. Use Polars native filtering.", DeprecationWarning, stacklevel=2)
        if self.df is None or column not in self.df.columns:
            return
        self._indexes[column] = self._query.create_index(self.df, column)

    # -- DataExporter delegation ----------------------------------------------

    def export_csv(self, path, selected_rows=None):
        if self.df is not None: self._exporter.export_csv(self.df, path, selected_rows)

    def export_excel(self, path, selected_rows=None):
        if self.df is not None: self._exporter.export_excel(self.df, path, selected_rows)

    def export_parquet(self, path, selected_rows=None):
        if self.df is not None: self._exporter.export_parquet(self.df, path, selected_rows)

    # -- DatasetManager delegation --------------------------------------------

    @property
    def datasets(self): return self._datasets_mgr.datasets

    @property
    def _datasets(self): return self._datasets_mgr.datasets

    @property
    def dataset_count(self): return self._datasets_mgr.dataset_count

    @property
    def active_dataset_id(self): return self._datasets_mgr.active_dataset_id

    @property
    def _active_dataset_id(self): return self._datasets_mgr._active_dataset_id

    @_active_dataset_id.setter
    def _active_dataset_id(self, value): self._datasets_mgr._active_dataset_id = value

    @property
    def active_dataset(self): return self._datasets_mgr.active_dataset

    @property
    def _color_index(self): return self._datasets_mgr._color_index

    @_color_index.setter
    def _color_index(self, value): self._datasets_mgr._color_index = value

    def get_dataset(self, did): return self._datasets_mgr.get_dataset(did)
    def get_dataset_df(self, did): return self._datasets_mgr.get_dataset_df(did)
    def list_datasets(self): return self._datasets_mgr.list_datasets()
    def get_total_memory_usage(self): return self._datasets_mgr.get_total_memory_usage()
    def can_load_dataset(self, sz): return self._datasets_mgr.can_load_dataset(sz)
    def set_dataset_color(self, did, c): self._datasets_mgr.set_dataset_color(did, c)
    def rename_dataset(self, did, n): self._datasets_mgr.rename_dataset(did, n)
    def get_common_columns(self, ids=None): return self._datasets_mgr.get_common_columns(ids)
    def get_numeric_columns(self, did): return self._datasets_mgr.get_numeric_columns(did)

    def load_dataset(self, path, name=None, dataset_id=None, **kw):
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
        self._clear_cache()
        self._datasets_mgr.clear_all_datasets()
        self._loader._df = self._loader._lazy_df = None
        self._loader._source = self._loader._profile = None

    # -- ComparisonEngine delegation ------------------------------------------

    def align_datasets(self, dataset_ids, key_column, fill_strategy="null"): return self._comparison.align_datasets(dataset_ids, key_column, fill_strategy)
    def calculate_difference(self, dataset_a_id, dataset_b_id, value_column, key_column=None): return self._comparison.calculate_difference(dataset_a_id, dataset_b_id, value_column, key_column)
    def get_comparison_statistics(self, dataset_ids, value_column): return self._comparison.get_comparison_statistics(dataset_ids, value_column)
    def merge_datasets(self, dataset_ids, key_column=None, how="full"): return self._comparison.merge_datasets(dataset_ids, key_column, how)
    def perform_statistical_test(self, dataset_a_id, dataset_b_id, value_column, test_type="auto"): return self._comparison.perform_statistical_test(dataset_a_id, dataset_b_id, value_column, test_type)
    def _select_test_type(self, data_a, data_b): return self._comparison._select_test_type(data_a, data_b)
    def _interpret_test_result(self, *args): return self._comparison._interpret_test_result(*args)
    def calculate_correlation(self, dataset_a_id, dataset_b_id, column_a, column_b=None, method="pearson"): return self._comparison.calculate_correlation(dataset_a_id, dataset_b_id, column_a, column_b, method)
    def calculate_descriptive_comparison(self, dataset_ids, value_column): return self._comparison.calculate_descriptive_comparison(dataset_ids, value_column)
    def get_normality_test(self, dataset_id, value_column): return self._comparison.get_normality_test(dataset_id, value_column)

    # -- clear ----------------------------------------------------------------

    def clear(self):
        """데이터 클리어."""
        self._loader.clear()
        self._indexes.clear()
        self._cache.clear()
