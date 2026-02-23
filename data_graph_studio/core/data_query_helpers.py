"""
data_query_helpers — Module-level constants and pure helper functions for DataQuery.

Extracted to keep data_query.py concise.  All logic here is stateless.
"""

import logging
from typing import Any, Dict, Optional

import polars as pl

logger = logging.getLogger(__name__)


# Polars numeric dtype set used for statistics checks.
NUMERIC_DTYPES = (
    pl.Int8, pl.Int16, pl.Int32, pl.Int64,
    pl.Float32, pl.Float64,
)

# Aggregation function map used by DataQuery.group_aggregate.
AGG_MAP: Dict[str, Any] = {
    'sum': lambda c: pl.col(c).sum(),
    'mean': lambda c: pl.col(c).mean(),
    'median': lambda c: pl.col(c).median(),
    'min': lambda c: pl.col(c).min(),
    'max': lambda c: pl.col(c).max(),
    'count': lambda c: pl.col(c).count(),
    'std': lambda c: pl.col(c).std(),
    'var': lambda c: pl.col(c).var(),
    'first': lambda c: pl.col(c).first(),
    'last': lambda c: pl.col(c).last(),
}


def build_filter_ops(column: str, value: Any) -> Dict[str, Any]:
    """Return the operator-expression mapping for a single column/value pair.

    Input: column — str, name of the DataFrame column to filter on
           value — Any, scalar comparison value
    Output: Dict[str, Any] — mapping of operator string to Polars expression (pl.Expr or bool expr)
    """
    col = pl.col(column)
    return {
        'eq': col == value,
        'ne': col != value,
        'gt': col > value,
        'lt': col < value,
        'ge': col >= value,
        'le': col <= value,
        'contains': col.str.contains(str(value)),
        'startswith': col.str.starts_with(str(value)),
        'endswith': col.str.ends_with(str(value)),
        'isnull': col.is_null(),
        'notnull': col.is_not_null(),
    }


def compute_eager_column_stats(series: pl.Series) -> Dict[str, Any]:
    """Compute basic statistics for a Polars Series (eager path).

    Input: series — pl.Series, the column data to summarise
    Output: Dict[str, Any] — always contains count, null_count, unique_count; numeric dtypes also include sum, mean, median, std, min, max, q1, q3
    """
    stats: Dict[str, Any] = {
        'count': len(series),
        'null_count': series.null_count(),
        'unique_count': series.n_unique(),
    }
    if series.dtype in NUMERIC_DTYPES:
        stats.update({
            'sum': series.sum(),
            'mean': series.mean(),
            'median': series.median(),
            'std': series.std(),
            'min': series.min(),
            'max': series.max(),
            'q1': series.quantile(0.25),
            'q3': series.quantile(0.75),
        })
    return stats


def compute_windowed_profile(
    lazy_df: pl.LazyFrame,
    collect_streaming_fn: Any,
) -> Optional[Dict[str, Any]]:
    """Compute profile summary statistics from a LazyFrame (windowed mode).

    Args:
        lazy_df: The full-dataset LazyFrame.
        collect_streaming_fn: Callable that collects a LazyFrame (streaming-aware).

    Returns:
        Profile summary dict or None on failure.
    """
    try:
        schema = lazy_df.collect_schema()
        total_columns = len(schema)
        numeric_cols = sum(1 for dtype in schema.values() if dtype in NUMERIC_DTYPES)

        null_exprs = [pl.col(c).null_count().alias(c) for c in schema.keys()]
        stats_df = collect_streaming_fn(
            lazy_df.select([pl.len().alias('total_rows')] + null_exprs)
        )
        if stats_df is None or stats_df.height == 0:
            return None

        total_rows = int(stats_df[0, 'total_rows'])
        total_nulls = sum(
            int(stats_df[0, c]) for c in schema.keys() if c in stats_df.columns
        )
        total_cells = total_rows * total_columns if total_rows > 0 else 0
        missing_percent = (total_nulls / total_cells * 100) if total_cells > 0 else 0.0

        return {
            'total_rows': total_rows,
            'total_columns': total_columns,
            'numeric_columns': numeric_cols,
            'text_columns': total_columns - numeric_cols,
            'missing_percent': missing_percent,
            'memory_bytes': 0,
            'load_time_seconds': 0,
        }
    except (pl.exceptions.PolarsError, RuntimeError, ValueError, TypeError):
        logger.debug("data_query_helpers.profile_summary.failed", exc_info=True)
        return None
