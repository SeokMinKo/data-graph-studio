"""
DataQuery — 데이터 조회/변환/통계 모듈 (stateless)

모든 메서드는 pl.DataFrame을 첫 번째 인자로 받아 동작한다.
내부 상태를 갖지 않으며, optional cache 파라미터로 결과를 캐싱할 수 있다.
"""

import re
import warnings
import logging
from typing import Optional, List, Dict, Any, Union

import polars as pl

from data_graph_studio.core.data_query_helpers import (
    NUMERIC_DTYPES,
    AGG_MAP,
    build_filter_ops,
    compute_eager_column_stats,
    compute_windowed_profile,
)
from data_graph_studio.core.metrics import get_metrics

logger = logging.getLogger(__name__)


class DataQuery:
    """Stateless 데이터 조회/변환/통계 클래스.

    모든 메서드는 순수 함수에 가깝게 설계되어 있으며,
    DataFrame을 인자로 받아 결과를 반환한다.
    """

    def filter(
        self,
        df: pl.DataFrame,
        column: str,
        operator: str,
        value: Any,
    ) -> Optional[pl.DataFrame]:
        """조건에 맞는 행을 필터링한다.

        Supported operators: 'eq', 'ne', 'gt', 'lt', 'ge', 'le',
        'contains', 'startswith', 'endswith', 'isnull', 'notnull'.
        Raises ValueError for unknown operators.
        """
        if df is None:
            return None

        ops = build_filter_ops(column, value)
        if operator not in ops:
            from data_graph_studio.core.exceptions import QueryError
            raise QueryError(
                f"Unknown operator: {operator}",
                operation="filter",
                context={"operator": operator, "column": column},
            )

        try:
            return self._collect_streaming(df.lazy().filter(ops[operator]))
        except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, MemoryError) as e:
            logger.debug("data_query.filter.streaming_fallback",
                         extra={"reason": type(e).__name__, "operator": operator, "column": column})
            return df.filter(ops[operator])

    def sort(
        self,
        df: pl.DataFrame,
        columns: List[str],
        descending: Union[bool, List[bool]] = False,
    ) -> Optional[pl.DataFrame]:
        """DataFrame을 정렬한다."""
        if df is None:
            return None
        try:
            return self._collect_streaming(df.lazy().sort(columns, descending=descending))
        except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, MemoryError) as e:
            logger.debug("data_query.sort.streaming_fallback",
                         extra={"reason": type(e).__name__, "columns": columns})
            return df.sort(columns, descending=descending)

    def group_aggregate(
        self,
        df: pl.DataFrame,
        group_columns: List[str],
        value_columns: List[str],
        agg_funcs: List[str],
    ) -> Optional[pl.DataFrame]:
        """그룹별 집계를 수행한다.

        agg_funcs: 'sum', 'mean', 'median', 'min', 'max', 'count', 'std', 'var',
        'first', 'last'.
        """
        if df is None:
            return None

        agg_exprs = [
            AGG_MAP[func](col).alias(f"{col}_{func}")
            for col, func in zip(value_columns, agg_funcs)
            if func in AGG_MAP
        ]

        get_metrics().increment("query.executed")
        try:
            return self._collect_streaming(df.lazy().group_by(group_columns).agg(agg_exprs))
        except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, MemoryError) as e:
            logger.debug("data_query.group_aggregate.streaming_fallback",
                         extra={"reason": type(e).__name__, "group_columns": group_columns})
            return df.group_by(group_columns).agg(agg_exprs)

    def get_statistics(
        self,
        df: pl.DataFrame,
        column: str,
        lazy_df: Optional[pl.LazyFrame] = None,
        windowed: bool = False,
        cache: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """컬럼 통계를 계산한다.

        Args:
            df: 대상 DataFrame.
            column: 통계 대상 컬럼.
            lazy_df: windowed 모드에서 전체 통계용 LazyFrame.
            windowed: windowed 모드 여부.
            cache: 결과 캐시 딕셔너리 (있으면 캐시에서 조회/저장).
        """
        # Include windowed context so full-dataset stats aren't returned in windowed mode.
        cache_key = f"stats_{column}_windowed" if windowed else f"stats_{column}"
        if cache is not None and cache_key in cache:
            return cache[cache_key]

        result = self._compute_statistics(df, column, lazy_df, windowed)

        if cache is not None:
            cache[cache_key] = result

        return result

    def get_all_statistics(
        self,
        df: pl.DataFrame,
        value_columns: Optional[List[str]] = None,
        lazy_df: Optional[pl.LazyFrame] = None,
        windowed: bool = False,
        cache: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """모든 (또는 지정된) 컬럼의 통계를 반환한다."""
        if df is None:
            return {}

        if value_columns is None:
            value_columns = [
                col for col in df.columns
                if df[col].dtype in NUMERIC_DTYPES
            ]

        return {
            col: self.get_statistics(df, col, lazy_df, windowed, cache)
            for col in value_columns
        }

    def get_full_profile_summary(
        self,
        df: pl.DataFrame,
        profile: Any = None,
        lazy_df: Optional[pl.LazyFrame] = None,
        windowed: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """전체 데이터 기준 요약 통계를 반환한다."""
        if not windowed or lazy_df is None:
            if profile is None:
                return None
            numeric_columns = sum(1 for c in profile.columns if c.is_numeric)
            return {
                'total_rows': profile.total_rows,
                'total_columns': profile.total_columns,
                'numeric_columns': numeric_columns,
                'text_columns': profile.total_columns - numeric_columns,
                'columns': profile.columns,
                'memory_bytes': profile.memory_bytes,
                'load_time_seconds': profile.load_time_seconds,
            }

        return compute_windowed_profile(lazy_df, self._collect_streaming)

    def is_column_categorical(
        self,
        df: pl.DataFrame,
        column: str,
        max_unique_ratio: float = 0.05,
        max_unique_count: int = 100,
    ) -> bool:
        """컬럼이 categorical인지 판단한다."""
        if df is None or column not in df.columns:
            return False

        series = df[column]
        dtype = series.dtype

        if dtype == pl.Categorical:
            return True

        if dtype in NUMERIC_DTYPES:
            unique_count = series.n_unique()
            return unique_count <= min(20, max_unique_count) and unique_count / len(series) < max_unique_ratio

        if dtype in [pl.Date, pl.Datetime, pl.Time]:
            return False

        if dtype == pl.Utf8:
            row_count = len(series)
            unique_count = series.n_unique()
            return unique_count <= max_unique_count or (row_count > 0 and unique_count / row_count < max_unique_ratio)

        if dtype == pl.Boolean:
            return True

        return False

    def get_unique_values(
        self,
        df: pl.DataFrame,
        column: str,
        limit: int = 1000,
    ) -> List[Any]:
        """컬럼의 유니크 값 목록을 반환한다."""
        if df is None or column not in df.columns:
            return []
        # sort() is intentional: results are shown in dropdowns/axis labels where
        # alphabetical order matters to users. O(n log n) cost is acceptable here.
        return df[column].unique().sort().head(limit).to_list()

    def sample(
        self,
        df: pl.DataFrame,
        n: int = 10000,
        seed: int = 42,
    ) -> Optional[pl.DataFrame]:
        """DataFrame에서 샘플링한다."""
        if df is None:
            return None
        if len(df) <= n:
            return df
        return df.sample(n=n, seed=seed)

    def get_slice(
        self,
        df: pl.DataFrame,
        start: int,
        end: int,
    ) -> Optional[pl.DataFrame]:
        """DataFrame 슬라이스를 반환한다."""
        if df is None:
            return None
        return df.slice(start, end - start)

    def search(
        self,
        df: pl.DataFrame,
        query: str,
        columns: Optional[List[str]] = None,
        case_sensitive: bool = False,
        max_columns: int = 20,
    ) -> Optional[pl.DataFrame]:
        """텍스트 검색을 수행한다.

        Args:
            df: 대상 DataFrame.
            query: 검색어.
            columns: 검색할 컬럼 목록 (None이면 전체).
            case_sensitive: 대소문자 구분 여부.
            max_columns: 검색할 최대 컬럼 수.
        """
        if df is None:
            return None

        if columns is None:
            columns = df.columns[:max_columns]

        if not columns:
            return df.head(0)

        if not case_sensitive:
            query_pattern = f"(?i){re.escape(query)}"
            literal = False
        else:
            query_pattern = query
            literal = True

        conditions = []
        for col in columns:
            try:
                cond = pl.col(col).cast(pl.Utf8).str.contains(query_pattern, literal=literal)
                conditions.append(cond)
            except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, TypeError) as e:
                logger.warning("data_query.search.column_skip",
                               extra={"col": col, "reason": type(e).__name__})
                continue

        if not conditions:
            return df.head(0)

        combined = conditions[0]
        for cond in conditions[1:]:
            combined = combined | cond

        return df.filter(combined)

    def filter_by_map(
        self,
        df: pl.DataFrame,
        filter_map: Dict[str, List[Any]],
    ) -> Optional[pl.DataFrame]:
        """여러 컬럼의 값 목록 필터를 Polars LazyFrame에 한 번에 적용한다.

        graph_panel의 ``_active_filter`` (``{column: [val, ...]}`` 형태) 에
        맞춰 설계된 편의 메서드.  필터는 lazy 평가 레이어에서 결합된 후
        ``collect()`` 한 번만 호출되므로, eager 루프 방식보다 메모리 효율이 높다.

        Args:
            df: 대상 DataFrame.  None이면 None을 반환한다.
            filter_map: ``{컬럼명: 허용 값 리스트}`` 딕셔너리.
        """
        if df is None:
            return None
        if not filter_map:
            return df

        # Build a single lazy query with all filter predicates combined.
        lf: pl.LazyFrame = df.lazy()
        applied_any = False
        for col_name, values in filter_map.items():
            if not values:
                continue
            if col_name not in df.columns:
                continue
            # Cast to Utf8 for robust cross-dtype comparison (matches graph_panel behaviour).
            lf = lf.filter(pl.col(col_name).cast(pl.Utf8).is_in([str(v) for v in values]))
            applied_any = True

        if not applied_any:
            return df

        try:
            return self._collect_streaming(lf)
        except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, MemoryError) as e:
            logger.debug("data_query.filter_by_map.streaming_fallback",
                         extra={"reason": type(e).__name__, "filter_columns": list(filter_map.keys())})
            return lf.collect()

    def create_index(self, df: pl.DataFrame, column: str) -> Dict[Any, List[int]]:
        """인덱스를 생성한다 (deprecated)."""
        warnings.warn(
            "create_index is deprecated. Use Polars native filtering instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if df is None or column not in df.columns:
            return {}

        index: Dict[Any, List[int]] = {}
        unique_vals = df[column].unique().to_list()
        for val in unique_vals:
            mask = df[column] == val
            indices = df.with_row_index().filter(mask)["index"].to_list()
            index[val] = indices
        return index

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_statistics(
        self,
        df: pl.DataFrame,
        column: str,
        lazy_df: Optional[pl.LazyFrame],
        windowed: bool,
    ) -> Dict[str, Any]:
        """통계를 실제로 계산한다."""
        if windowed and lazy_df is not None:
            try:
                if column not in lazy_df.columns:
                    return {}
                dtype = lazy_df.schema.get(column)
                exprs = [
                    pl.len().alias('count'),
                    pl.col(column).null_count().alias('null_count'),
                    pl.col(column).n_unique().alias('unique_count'),
                ]
                if dtype in NUMERIC_DTYPES:
                    exprs.extend([
                        pl.col(column).sum().alias('sum'),
                        pl.col(column).mean().alias('mean'),
                        pl.col(column).median().alias('median'),
                        pl.col(column).std().alias('std'),
                        pl.col(column).min().alias('min'),
                        pl.col(column).max().alias('max'),
                        pl.col(column).quantile(0.25).alias('q1'),
                        pl.col(column).quantile(0.75).alias('q3'),
                    ])
                stats_df = self._collect_streaming(lazy_df.select(exprs))
                if stats_df is not None and stats_df.height > 0:
                    return stats_df.to_dicts()[0]
            except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, MemoryError) as e:
                logger.debug("data_query.windowed_stats.streaming_fallback",
                             extra={"reason": type(e).__name__, "column": column})

        if df is None or column not in df.columns:
            return {}

        return compute_eager_column_stats(df[column])

    @staticmethod
    def _collect_streaming(lazy_df: pl.LazyFrame) -> pl.DataFrame:
        """LazyFrame을 streaming 모드로 수집한다."""
        try:
            return lazy_df.collect(engine="streaming")
        except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, MemoryError, OSError) as e:
            logger.debug("data_query.collect_streaming.engine_fallback",
                         extra={"reason": type(e).__name__})
            return lazy_df.collect()
