"""
Data Engine — Polars 기반 빅데이터 처리 엔진 (Facade)

5개 하위 모듈(FileLoader, DataQuery, DataExporter, DatasetManager,
ComparisonEngine)을 조합하여 기존 API를 100% 유지하는 Facade 패턴.

기존 import 호환:
    from data_graph_studio.core.data_engine import DataEngine, FileType, ...
"""

import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set

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
from ._data_engine_cache_mixin import _DataEngineCacheMixin
from ._data_engine_loader_mixin import _DataEngineLoaderMixin
from ._data_engine_query_mixin import _DataEngineQueryMixin
from ._data_engine_export_mixin import _DataEngineExportMixin
from .exceptions import QueryError


def _import_submodules():
    """하위 모듈을 지연 임포트한다."""
    from .file_loader import FileLoader
    from .data_query import DataQuery
    from .data_exporter import DataExporter
    from .dataset_manager import DatasetManager
    from .comparison_engine import ComparisonEngine
    return FileLoader, DataQuery, DataExporter, DatasetManager, ComparisonEngine


class DataEngine(_DataEngineCacheMixin, _DataEngineLoaderMixin, _DataEngineQueryMixin, _DataEngineExportMixin, DatasetMixin, AnalysisMixin):
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
