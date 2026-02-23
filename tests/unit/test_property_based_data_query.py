"""Property-based tests for DataQuery invariants.

Tests cover sort, filter, sample, slice, and composition invariants
using Hypothesis to find edge cases across randomly generated inputs.
All tests are Qt-free — no QApplication required.
"""

import polars as pl
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from data_graph_studio.core.data_query import DataQuery
from data_graph_studio.core.exceptions import QueryError

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_col_name = st.from_regex(r"[A-Za-z][A-Za-z0-9]{0,9}", fullmatch=True)

_int_values = st.lists(
    st.integers(min_value=-1000, max_value=1000), min_size=1, max_size=60
)

_pos_values = st.lists(
    st.integers(min_value=1, max_value=1000), min_size=1, max_size=60
)

_float_values = st.lists(
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    min_size=1,
    max_size=60,
)


def _df_int(col: str, values: list) -> pl.DataFrame:
    return pl.DataFrame({col: values})


# ---------------------------------------------------------------------------
# 1. sort — preserves row count
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(col=_col_name, values=_int_values, descending=st.booleans())
def test_sort_preserves_row_count(col, values, descending):
    """sort never changes the row count of the DataFrame."""
    df = _df_int(col, values)
    dq = DataQuery()
    result = dq.sort(df, [col], descending=descending)
    assert result is not None
    assert result.height == df.height


# ---------------------------------------------------------------------------
# 2. sort — deterministic (same inputs → same output)
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(col=_col_name, values=_int_values, descending=st.booleans())
def test_sort_deterministic(col, values, descending):
    """sort is deterministic: the same call twice returns identical DataFrames."""
    df = _df_int(col, values)
    dq = DataQuery()
    r1 = dq.sort(df, [col], descending=descending)
    r2 = dq.sort(df, [col], descending=descending)
    assert r1 is not None and r2 is not None
    assert r1.equals(r2)


# ---------------------------------------------------------------------------
# 3. sort — idempotent (sorting an already-sorted df is a no-op)
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(col=_col_name, values=_int_values, descending=st.booleans())
def test_sort_idempotent(col, values, descending):
    """Sorting an already-sorted DataFrame by the same key is a no-op."""
    df = _df_int(col, values)
    dq = DataQuery()
    once = dq.sort(df, [col], descending=descending)
    assert once is not None
    twice = dq.sort(once, [col], descending=descending)
    assert twice is not None
    assert once.equals(twice)


# ---------------------------------------------------------------------------
# 4. sort — ascending then reversed equals descending
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(col=_col_name, values=_int_values)
def test_sort_reverse_property(col, values):
    """Sorting ascending and reversing gives the same order as sorting descending."""
    df = _df_int(col, values)
    dq = DataQuery()
    asc = dq.sort(df, [col], descending=False)
    desc = dq.sort(df, [col], descending=True)
    assert asc is not None and desc is not None
    assert asc[col].to_list() == list(reversed(desc[col].to_list()))


# ---------------------------------------------------------------------------
# 5. filter — deterministic (idempotency on same df)
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=_int_values,
    threshold=st.integers(min_value=-1000, max_value=1000),
)
def test_filter_deterministic(col, values, threshold):
    """Calling filter with the same arguments twice yields equal DataFrames."""
    df = _df_int(col, values)
    dq = DataQuery()
    r1 = dq.filter(df, col, "ge", threshold)
    r2 = dq.filter(df, col, "ge", threshold)
    assert r1 is not None and r2 is not None
    assert r1.equals(r2)


# ---------------------------------------------------------------------------
# 6. filter — never increases row count
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=_int_values,
    threshold=st.integers(min_value=-1000, max_value=1000),
    op=st.sampled_from(["eq", "ne", "gt", "lt", "ge", "le"]),
)
def test_filter_never_increases_row_count(col, values, threshold, op):
    """filter always returns <= the original number of rows."""
    df = _df_int(col, values)
    dq = DataQuery()
    result = dq.filter(df, col, op, threshold)
    assert result is not None
    assert result.height <= df.height


# ---------------------------------------------------------------------------
# 7. filter — gt and le partition the full row set
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=_int_values,
    threshold=st.integers(min_value=-1000, max_value=1000),
)
def test_filter_gt_le_partition(col, values, threshold):
    """gt(x) + le(x) covers exactly all rows (no overlap, no gap)."""
    df = _df_int(col, values)
    dq = DataQuery()
    gt = dq.filter(df, col, "gt", threshold)
    le = dq.filter(df, col, "le", threshold)
    assert gt is not None and le is not None
    assert gt.height + le.height == df.height


# ---------------------------------------------------------------------------
# 8. sample — result size never exceeds requested n
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=st.lists(st.integers(min_value=-10**9, max_value=10**9), min_size=1, max_size=200),
    n=st.integers(min_value=1, max_value=100),
)
def test_sample_size_invariant(col, values, n):
    """sample(n) always returns at most n rows."""
    df = _df_int(col, values)
    dq = DataQuery()
    result = dq.sample(df, n=n)
    assert result is not None
    assert result.height <= n


# ---------------------------------------------------------------------------
# 9. sample — when df <= n, return all rows unchanged
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=st.lists(st.integers(min_value=-10**9, max_value=10**9), min_size=1, max_size=10),
    n=st.integers(min_value=10, max_value=100),
)
def test_sample_small_df_returns_all(col, values, n):
    """When df.height <= n, sample returns the full DataFrame."""
    df = _df_int(col, values)
    dq = DataQuery()
    result = dq.sample(df, n=n)
    assert result is not None
    assert result.height == df.height


# ---------------------------------------------------------------------------
# 10. get_slice — result length <= (end - start)
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=st.lists(st.integers(min_value=-10**9, max_value=10**9), min_size=1, max_size=100),
    start=st.integers(min_value=0, max_value=50),
    length=st.integers(min_value=0, max_value=50),
)
def test_slice_size_invariant(col, values, start, length):
    """get_slice(start, start+length) returns at most `length` rows."""
    df = _df_int(col, values)
    end = start + length
    dq = DataQuery()
    result = dq.get_slice(df, start, end)
    assert result is not None
    assert result.height <= length


# ---------------------------------------------------------------------------
# 11. get_slice — exact length when slice fits entirely in df
# ---------------------------------------------------------------------------


@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=st.lists(st.integers(min_value=-10**9, max_value=10**9), min_size=10, max_size=100),
    start=st.integers(min_value=0, max_value=5),
    length=st.integers(min_value=1, max_value=5),
)
def test_slice_exact_length_when_within_bounds(col, values, start, length):
    """When slice is fully within df bounds, row count equals (end - start)."""
    df = _df_int(col, values)
    end = start + length
    assume(end <= df.height)
    dq = DataQuery()
    result = dq.get_slice(df, start, end)
    assert result is not None
    assert result.height == length


# ---------------------------------------------------------------------------
# 12. filter on unknown operator raises QueryError
# ---------------------------------------------------------------------------


@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=_pos_values,
    bad_op=st.text(min_size=1, max_size=10).filter(
        lambda s: s not in {"eq", "ne", "gt", "lt", "ge", "le", "contains",
                             "startswith", "endswith", "isnull", "notnull"}
    ),
)
def test_filter_bad_operator_raises_query_error(col, values, bad_op):
    """Passing an unrecognised operator string raises QueryError."""
    df = _df_int(col, values)
    dq = DataQuery()
    with pytest.raises(QueryError):
        dq.filter(df, col, bad_op, 0)


# ---------------------------------------------------------------------------
# 13. sort on non-existent column — Polars raises, not silent
# ---------------------------------------------------------------------------


@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=_int_values,
    bad_col=st.from_regex(r"ZZZ[A-Z]{3}", fullmatch=True),
)
def test_sort_nonexistent_column_raises(col, values, bad_col):
    """sort on a column that does not exist should raise (Polars error)."""
    df = _df_int(col, values)
    assume(bad_col not in df.columns)
    dq = DataQuery()
    with pytest.raises(Exception):
        dq.sort(df, [bad_col])
