"""DataEngine query mixin — DataQuery delegation and LazyFrame helpers."""

from __future__ import annotations

import warnings
from typing import Optional, Dict

import polars as pl


class _DataEngineQueryMixin:
    """Query, statistics, and LazyFrame pipeline methods for DataEngine.

    Attributes accessed from DataEngine:
        _query: DataQuery instance.
        _loader: FileLoader instance (for _lazy_df, is_windowed, profile).
        df: active DataFrame property.
        _indexes: Dict for index storage.
    """

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
