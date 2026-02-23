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
        """Filter rows in a DataFrame that match a column condition.

        Input:
            df: DataFrame to filter; returns None immediately if None.
            column: Name of the column to apply the filter on.
            operator: Comparison operator string. Supported values: 'eq', 'ne',
                'gt', 'lt', 'ge', 'le', 'contains', 'startswith', 'endswith',
                'isnull', 'notnull'.
            value: The value to compare against; ignored for 'isnull'/'notnull'.

        Output:
            Filtered DataFrame containing only rows where the condition holds.
            Returns None if df is None. For GT/GE/LT/LE operators, NaN rows
            are excluded from the result.

        Raises:
            QueryError: If operator is not one of the supported operator strings.

        Invariants:
            - Result row count <= input row count.
            - Returns None iff df is None.
            - NaN values are never included in GT/GE/LT/LE results.
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
        """Sort a DataFrame by one or more columns.

        Input:
            df: DataFrame to sort; returns None immediately if None.
            columns: List of column names to sort by, applied left-to-right.
            descending: If bool, applies to all columns. If list, must match
                length of columns; each entry controls the corresponding column.

        Output:
            New DataFrame sorted by the specified columns. Returns None if df
            is None. Row count is always equal to the input row count.

        Raises:
            None. Polars errors are caught internally for streaming→eager fallback.

        Invariants:
            - Output row count == input row count.
            - Returns None iff df is None.
        """
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
        """Perform group-by aggregation on a DataFrame.

        Input:
            df: DataFrame to aggregate; returns None immediately if None.
            group_columns: Column names to group by.
            value_columns: Columns to aggregate; zipped with agg_funcs.
            agg_funcs: Aggregation function names, one per value column.
                Supported: 'sum', 'mean', 'median', 'min', 'max', 'count',
                'std', 'var', 'first', 'last'. Unknown func names are silently
                skipped (no corresponding aggregation expression is emitted).

        Output:
            Aggregated DataFrame with one row per unique combination of
            group_columns. Each aggregated value column is named
            ``{col}_{func}``. Returns None if df is None.

        Raises:
            None. Polars errors are caught internally for streaming→eager fallback.

        Invariants:
            - Output columns include all group_columns plus ``{col}_{func}``
              for each valid (value_column, agg_func) pair.
            - Output row count <= input row count.
            - Returns None iff df is None.
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
        """Compute descriptive statistics for a single column.

        Input:
            df: DataFrame containing the column; used for eager stats when not
                in windowed mode. Returns ``{}`` if column not in df.
            column: Name of the column to compute statistics for.
            lazy_df: Full-dataset LazyFrame used in windowed mode to compute
                statistics over the entire dataset rather than just the window.
                Ignored when windowed is False.
            windowed: If True, statistics are computed from lazy_df (full
                dataset); if False, statistics are computed from df directly.
            cache: Optional dict used as a result cache. Cache key is
                ``stats_{column}`` (or ``stats_{column}_windowed`` when
                windowed=True). If the key exists the cached value is returned
                without recomputation; on miss, the result is stored before
                returning.

        Output:
            Dict with numeric statistics for the column. Keys include at
            minimum: ``count``, ``mean``, ``std``, ``min``, ``max``,
            ``median``, ``null_count``, ``unique_count``. Additional keys
            (``q1``, ``q3``, ``sum``) are present for numeric columns.
            Returns ``{}`` if column is absent from both df and lazy_df.

        Raises:
            pl.exceptions.InvalidOperationError: If a numeric aggregation is
                applied to an incompatible dtype inside Polars.

        Invariants:
            - Return type is always a dict (never None).
            - Result is idempotent for the same (df, column, windowed) triple.
            - Cache key uniquely encodes the windowed context to prevent
              stale full-dataset stats from leaking into windowed views.
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
        """Compute statistics for all (or specified) columns in a DataFrame.

        Input:
            df: DataFrame to compute statistics for; returns ``{}`` if None.
            value_columns: Explicit list of column names to include. If None,
                defaults to all columns whose dtype is numeric (per
                NUMERIC_DTYPES). Non-existent column names are silently skipped
                via get_statistics returning ``{}``.
            lazy_df: Forwarded to get_statistics for windowed mode support.
            windowed: Forwarded to get_statistics; controls whether stats are
                drawn from lazy_df or df.
            cache: Forwarded to get_statistics for per-column result caching.

        Output:
            Dict mapping column name to its statistics dict (same shape as
            get_statistics output). Returns ``{}`` if df is None or if
            value_columns resolves to an empty list.

        Raises:
            pl.exceptions.InvalidOperationError: Propagated from get_statistics
                if a column's dtype is incompatible with aggregation.

        Invariants:
            - Return type is always a dict (never None).
            - Keys are exactly the resolved value_columns that are present.
            - Returns ``{}`` iff df is None.
        """
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
        """Return a high-level summary of the full dataset profile.

        Input:
            df: Current DataFrame (used implicitly; not accessed directly in
                the non-windowed path, but kept for API consistency).
            profile: DataProfile object with attributes ``total_rows``,
                ``total_columns``, ``columns``, ``memory_bytes``,
                ``load_time_seconds``. Used when not in windowed mode.
                Returns None if profile is None in non-windowed mode.
            lazy_df: Full-dataset LazyFrame. Required when windowed=True to
                compute aggregate summary on the fly via compute_windowed_profile.
            windowed: If True and lazy_df is provided, computes a live profile
                from lazy_df. If False (or lazy_df is None), falls back to the
                pre-computed profile object.

        Output:
            Dict with keys: ``total_rows``, ``total_columns``,
            ``numeric_columns``, ``text_columns``, ``columns``,
            ``memory_bytes``, ``load_time_seconds`` when using the profile
            path. In windowed mode, shape depends on compute_windowed_profile.
            Returns None if windowed=False and profile is None.

        Raises:
            AttributeError: If profile is not None but lacks required
                attributes (total_rows, total_columns, columns, etc.).

        Invariants:
            - Returns None iff not windowed (or lazy_df is None) and profile
              is None.
            - numeric_columns + text_columns == total_columns in non-windowed
              path.
        """
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
        """Determine whether a column should be treated as categorical.

        Input:
            df: DataFrame containing the column; returns False if None.
            column: Column name to inspect; returns False if not in df.
            max_unique_ratio: Maximum ratio of unique values to total rows for
                numeric and Utf8 columns to be considered categorical.
                Default 0.05 (5%).
            max_unique_count: Maximum absolute count of unique values for a
                numeric column to qualify as categorical. Default 100. For
                numeric columns the effective limit is min(20, max_unique_count).

        Output:
            True if the column is considered categorical, False otherwise.
            Classification rules by dtype:
            - pl.Categorical or pl.Boolean: always True.
            - pl.Date/pl.Datetime/pl.Time: always False.
            - Numeric: True iff unique_count <= min(20, max_unique_count)
              AND unique_count / row_count < max_unique_ratio.
            - pl.Utf8: True iff unique_count <= max_unique_count OR
              unique_count / row_count < max_unique_ratio.
            - Other dtypes: False.

        Raises:
            None. All errors are prevented by early-exit guards.

        Invariants:
            - Returns False iff df is None or column not in df.columns.
            - Return type is always bool.
        """
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
        """Return sorted unique values for a column, up to a limit.

        Input:
            df: DataFrame to query; returns [] if None.
            column: Column name to retrieve unique values from; returns [] if
                not in df.columns.
            limit: Maximum number of unique values to return. Values are sorted
                before the limit is applied, so the result is always the first
                ``limit`` values in ascending order.

        Output:
            Sorted list of up to ``limit`` unique values from the column.
            Values are in ascending order (Polars default sort). Returns []
            if df is None or column is absent.

        Raises:
            None. Early-exit guards prevent all error paths.

        Invariants:
            - Return type is always a list.
            - Result length <= limit.
            - Returns [] iff df is None or column not in df.columns.
            - Values are sorted in ascending order.
        """
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
        """Return a random sample of at most n rows from a DataFrame.

        Input:
            df: DataFrame to sample from; returns None if None.
            n: Maximum number of rows to return. If df has <= n rows, the
                entire DataFrame is returned without sampling.
            seed: Random seed for reproducible sampling. Default 42.

        Output:
            DataFrame with at most n rows. If len(df) <= n, returns df
            unchanged. Returns None if df is None.

        Raises:
            pl.exceptions.InvalidOperationError: May propagate from Polars
                on invalid sample configurations (e.g., fractional n). Not
                caught; callers should handle if needed.

        Invariants:
            - Output row count <= n.
            - Output row count == len(df) when len(df) <= n.
            - Returns None iff df is None.
        """
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
        """Return a contiguous row slice of a DataFrame.

        Input:
            df: DataFrame to slice; returns None if None.
            start: Zero-based index of the first row to include (inclusive).
            end: Zero-based index of the last row to include (exclusive).
                Length of slice is ``end - start``.

        Output:
            DataFrame containing rows from index start up to (but not
            including) end. Returns None if df is None. If the slice range
            exceeds the DataFrame length, Polars clamps it silently.

        Raises:
            None. Polars slice does not raise on out-of-bound ranges.

        Invariants:
            - Output row count == max(0, min(end, len(df)) - start).
            - Returns None iff df is None.
        """
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
        """Search all (or specified) columns for rows matching a text query.

        Input:
            df: DataFrame to search; returns None if None.
            query: Search string. If case_sensitive=False, treated as a
                case-insensitive regex pattern (via ``(?i)`` prefix and
                re.escape). If case_sensitive=True, treated as a literal string.
            columns: Explicit list of columns to search. If None, the first
                min(len(df.columns), max_columns) columns are searched.
            case_sensitive: Whether to perform case-sensitive matching.
                Default False (case-insensitive).
            max_columns: Upper bound on columns searched when columns=None.
                Default 20.

        Output:
            DataFrame containing only rows where at least one searched column
            contains the query string (cast to Utf8 for comparison). Returns
            None if df is None. Returns an empty DataFrame (0 rows) if columns
            resolves to an empty list or all column conditions fail to build.

        Raises:
            None. Per-column errors during condition building are caught and
            logged; that column is skipped without propagating the exception.

        Invariants:
            - Returns None iff df is None.
            - Output row count <= input row count.
            - Every returned row matches the query in at least one searched
              column.
            - Columns with incompatible types are silently skipped.
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
        """Filter rows by multiple column allowlists in a single lazy pass.

        Designed for graph_panel's ``_active_filter`` pattern where the filter
        state is a ``{column: [val, ...]}`` dict. All predicates are combined
        in a single LazyFrame query and collected once, which is more memory-
        efficient than iterating with eager filters.

        Input:
            df: DataFrame to filter; returns None if None.
            filter_map: Dict mapping column names to lists of allowed values.
                Values are cast to str for comparison (matches graph_panel
                behaviour). Keys for columns not in df are silently skipped.
                Keys with empty value lists are silently skipped.

        Output:
            Filtered DataFrame containing only rows where every column in
            filter_map (with a non-empty value list) holds one of the allowed
            values. Returns None if df is None. Returns df unchanged if
            filter_map is empty or all entries are empty/missing.

        Raises:
            pl.exceptions.InvalidOperationError: Propagated from Polars if
                a predicate cannot be evaluated (e.g., dtype cast fails in
                eager fallback).

        Invariants:
            - Returns None iff df is None.
            - Output row count <= input row count.
            - Missing or empty-valued keys in filter_map have no effect.
            - All predicates are AND-combined (row must satisfy all filters).
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
        """Build a value-to-row-indices mapping for a column (deprecated).

        .. deprecated::
            Use Polars native filtering (``df.filter(pl.col(col) == val)``)
            instead. This method exists only for backward compatibility.

        Input:
            df: DataFrame to index; returns ``{}`` if None.
            column: Column name to build the index on; returns ``{}`` if not
                in df.columns.

        Output:
            Dict mapping each unique value in the column to a list of integer
            row indices (0-based) where that value occurs. Returns ``{}`` if
            df is None or column is absent.

        Raises:
            DeprecationWarning: Always emitted via warnings.warn with
                stacklevel=2.

        Invariants:
            - Return type is always a dict.
            - Returns ``{}`` iff df is None or column not in df.columns.
            - Union of all index lists covers every row index in df exactly
              once (complete partition).
        """
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
