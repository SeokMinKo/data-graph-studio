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

    # Maximum cache memory in bytes (256 MB)
    CACHE_MAX_MEMORY_BYTES: int = 256 * 1024 * 1024

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
        self._cache_total_bytes: int = 0
        self._cache_sizes: Dict[str, int] = {}  # key -> estimated size in bytes
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
        """캐시에 값을 저장한다 (메모리 기반 eviction 포함)."""
        import sys
        # Remove old entry size if updating
        if key in self._cache_sizes:
            self._cache_total_bytes -= self._cache_sizes[key]

        # Estimate size
        if isinstance(value, pl.DataFrame):
            size = value.estimated_size()
        else:
            size = sys.getsizeof(value)

        self._cache[key] = value
        self._cache_sizes[key] = size
        self._cache_total_bytes += size
        self._cache.move_to_end(key)
        self._evict_cache()

    def _evict_cache(self) -> None:
        # Evict by count
        while len(self._cache) > self._cache_maxsize:
            evicted_key, _ = self._cache.popitem(last=False)
            if evicted_key in self._cache_sizes:
                self._cache_total_bytes -= self._cache_sizes.pop(evicted_key)
        # Evict by memory
        while self._cache_total_bytes > self.CACHE_MAX_MEMORY_BYTES and self._cache:
            evicted_key, _ = self._cache.popitem(last=False)
            if evicted_key in self._cache_sizes:
                self._cache_total_bytes -= self._cache_sizes.pop(evicted_key)

    def _clear_cache(self) -> None:
        self._cache.clear()
        self._cache_sizes.clear()
        self._cache_total_bytes = 0

    def _cache_key(self, operation: str, *args) -> str:
        """dataset별 캐시 키 생성 (F5)."""
        dataset_id = self._datasets_mgr.active_dataset_id if self._datasets_mgr else "default"
        return f"{dataset_id}:{operation}:{repr(args)}"

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

    def append_rows(self, file_path: str, new_row_count: int) -> bool:
        """Incrementally append new rows from the end of a file (streaming optimization).

        Uses skip_rows to avoid loading the entire file into memory.
        Falls back to full reload on error.
        """
        import polars as pl

        current_df = self.df
        if current_df is None:
            return self.load_file(file_path, optimize_memory=True)

        try:
            # Incremental: skip already-loaded rows (+ 1 for header)
            skip = len(current_df)
            new_rows = pl.read_csv(file_path, skip_rows_after_header=skip)
            if len(new_rows) == 0:
                return True
            merged = pl.concat([current_df, new_rows], how="vertical_relaxed")
            self.update_dataframe(merged)
            self._clear_cache()
            return True
        except Exception:
            try:
                # Fallback: scan_csv + tail
                new_rows = pl.scan_csv(file_path).tail(new_row_count).collect()
                merged = pl.concat([current_df, new_rows], how="vertical_relaxed")
                self.update_dataframe(merged)
                self._clear_cache()
                return True
            except Exception:
                return self.load_file(file_path, optimize_memory=True)

    def trim(self, max_rows: int) -> None:
        """Trim the engine DataFrame to at most *max_rows* (tail). Used by sliding window."""
        df = self.df
        if df is not None and len(df) > max_rows:
            self.update_dataframe(df.tail(max_rows))

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

    def replace_dataset_df(self, dataset_id: str, df: pl.DataFrame) -> bool:
        """Replace DataFrame for an existing dataset (used for re-conversion).

        Args:
            dataset_id: ID of the dataset to update.
            df: New polars DataFrame.

        Returns:
            True if successful.
        """
        ds = self._datasets_mgr.get_dataset(dataset_id)
        if ds is None:
            return False
        ds.df = df
        ds.row_count = len(df)
        ds.column_count = len(df.columns)
        # Sync loader if this is the active dataset
        if self._datasets_mgr.active_dataset_id == dataset_id:
            self._loader._df = df
        self._clear_cache()
        return True

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
        null_counts = {col: df[col].null_count() for col in df.columns}
        return {
            'row_count': row_count,
            'col_count': len(df.columns),
            'null_counts': null_counts,
            'null_pct': {col: cnt / max(row_count, 1) * 100 for col, cnt in null_counts.items()},
            'duplicate_rows': row_count - df.n_unique(),
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
        return self._datasets_mgr.MAX_DATASETS

    @property
    def MAX_TOTAL_MEMORY(self):
        return self._datasets_mgr.MAX_TOTAL_MEMORY

    @property
    def DEFAULT_COLORS(self):
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
