"""
Property-based tests for the filtering module using Hypothesis.

Invariants tested:
- Filtering never increases row count
- No filters returns all rows
- EQ filter: all result rows match the value
- GT filter: all result rows have value > threshold
- LT filter: all result rows have value < threshold
- Disabled filter behaves like no filter
- Double application of same filter is idempotent
- NE filter: complementary to EQ filter
- BETWEEN filter: all result rows have min_val <= value <= max_val
- IN_LIST filter: all result rows have value in the list
- IS_NULL / IS_NOT_NULL are complementary and cover all rows
- CONTAINS filter: all result rows contain the substring
"""
from __future__ import annotations

from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
import polars as pl

from data_graph_studio.core.filtering import (
    Filter,
    FilterOperator,
    FilterType,
    FilteringManager,
)
from data_graph_studio.core.constants import DEFAULT_SCHEME_NAME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager_with_df(df: pl.DataFrame) -> FilteringManager:
    """Return a fresh FilteringManager (default 'Page' scheme)."""
    return FilteringManager()


def _apply_single(df: pl.DataFrame, filt: Filter) -> pl.DataFrame:
    """Apply one Filter to a DataFrame through FilteringManager."""
    mgr = FilteringManager()
    mgr._schemes[DEFAULT_SCHEME_NAME].add_filter(filt)
    return mgr.apply_filters(DEFAULT_SCHEME_NAME, df)


def _make_int_df(values: list[int]) -> pl.DataFrame:
    assume(len(values) > 0)
    return pl.DataFrame({"x": values})


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

small_int_list = st.lists(
    st.integers(min_value=-1000, max_value=1000),
    min_size=1,
    max_size=50,
)

small_float_list = st.lists(
    st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=50,
)

small_str_list = st.lists(
    st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")), min_size=0, max_size=10),
    min_size=1,
    max_size=30,
)


# ---------------------------------------------------------------------------
# Test 1: Filtering never increases row count (integers)
# ---------------------------------------------------------------------------

@given(values=small_int_list, threshold=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_filter_never_increases_row_count_gt(values, threshold):
    """GT filter result must have <= rows than original."""
    df = pl.DataFrame({"x": values})
    filt = Filter(column="x", operator=FilterOperator.GREATER_THAN, value=threshold)
    result = _apply_single(df, filt)
    assert len(result) <= len(df)


@given(values=small_int_list, threshold=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_filter_never_increases_row_count_lt(values, threshold):
    """LT filter result must have <= rows than original."""
    df = pl.DataFrame({"x": values})
    filt = Filter(column="x", operator=FilterOperator.LESS_THAN, value=threshold)
    result = _apply_single(df, filt)
    assert len(result) <= len(df)


@given(values=small_int_list, target=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_filter_never_increases_row_count_eq(values, target):
    """EQ filter result must have <= rows than original."""
    df = pl.DataFrame({"x": values})
    filt = Filter(column="x", operator=FilterOperator.EQUALS, value=target)
    result = _apply_single(df, filt)
    assert len(result) <= len(df)


# ---------------------------------------------------------------------------
# Test 2: No enabled filters returns all rows
# ---------------------------------------------------------------------------

@given(values=small_int_list)
@settings(max_examples=80)
def test_no_filters_returns_all_rows(values):
    """An empty scheme returns the full DataFrame unchanged."""
    df = pl.DataFrame({"x": values})
    mgr = FilteringManager()
    result = mgr.apply_filters(DEFAULT_SCHEME_NAME, df)
    assert len(result) == len(df)


# ---------------------------------------------------------------------------
# Test 3: EQ filter — all result rows have the filtered value
# ---------------------------------------------------------------------------

@given(values=small_int_list, target=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_eq_filter_all_result_rows_match(values, target):
    """After EQ filter, every row's 'x' equals target."""
    df = pl.DataFrame({"x": values})
    filt = Filter(column="x", operator=FilterOperator.EQUALS, value=target)
    result = _apply_single(df, filt)
    if len(result) > 0:
        assert result["x"].to_list() == [target] * len(result)


# ---------------------------------------------------------------------------
# Test 4: GT filter — all result rows strictly > threshold
# ---------------------------------------------------------------------------

@given(values=small_int_list, threshold=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_gt_filter_all_result_rows_greater(values, threshold):
    """After GT filter, every row's 'x' is strictly > threshold."""
    df = pl.DataFrame({"x": values})
    filt = Filter(column="x", operator=FilterOperator.GREATER_THAN, value=threshold)
    result = _apply_single(df, filt)
    if len(result) > 0:
        assert all(v > threshold for v in result["x"].to_list())


# ---------------------------------------------------------------------------
# Test 5: LT filter — all result rows strictly < threshold
# ---------------------------------------------------------------------------

@given(values=small_int_list, threshold=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_lt_filter_all_result_rows_less(values, threshold):
    """After LT filter, every row's 'x' is strictly < threshold."""
    df = pl.DataFrame({"x": values})
    filt = Filter(column="x", operator=FilterOperator.LESS_THAN, value=threshold)
    result = _apply_single(df, filt)
    if len(result) > 0:
        assert all(v < threshold for v in result["x"].to_list())


# ---------------------------------------------------------------------------
# Test 6: Disabled filter behaves like no filter
# ---------------------------------------------------------------------------

@given(values=small_int_list, threshold=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_disabled_filter_returns_all_rows(values, threshold):
    """A disabled filter must not reduce the row count."""
    df = pl.DataFrame({"x": values})
    filt = Filter(
        column="x",
        operator=FilterOperator.GREATER_THAN,
        value=threshold,
        enabled=False,
    )
    result = _apply_single(df, filt)
    assert len(result) == len(df)


# ---------------------------------------------------------------------------
# Test 7: Double application of same filter is idempotent
# ---------------------------------------------------------------------------

@given(values=small_int_list, threshold=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_filter_idempotent(values, threshold):
    """Applying the same GT filter twice gives the same result as once."""
    df = pl.DataFrame({"x": values})
    filt = Filter(column="x", operator=FilterOperator.GREATER_THAN, value=threshold)

    once = _apply_single(df, filt)
    twice = _apply_single(once, filt)

    assert len(twice) == len(once)
    if len(once) > 0:
        assert once["x"].to_list() == twice["x"].to_list()


# ---------------------------------------------------------------------------
# Test 8: NE filter complementary to EQ
# ---------------------------------------------------------------------------

@given(values=small_int_list, target=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_ne_filter_complementary_to_eq(values, target):
    """EQ count + NE count == total row count."""
    df = pl.DataFrame({"x": values})
    eq_filt = Filter(column="x", operator=FilterOperator.EQUALS, value=target)
    ne_filt = Filter(column="x", operator=FilterOperator.NOT_EQUALS, value=target)

    eq_result = _apply_single(df, eq_filt)
    ne_result = _apply_single(df, ne_filt)

    assert len(eq_result) + len(ne_result) == len(df)


# ---------------------------------------------------------------------------
# Test 9: BETWEEN filter — all result rows within [min_val, max_val]
# ---------------------------------------------------------------------------

@given(
    values=small_int_list,
    bounds=st.tuples(
        st.integers(min_value=-1000, max_value=0),
        st.integers(min_value=0, max_value=1000),
    ),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_between_filter_all_rows_in_range(values, bounds):
    """After BETWEEN filter, all result rows satisfy min <= x <= max."""
    lo, hi = bounds
    df = pl.DataFrame({"x": values})
    filt = Filter(column="x", operator=FilterOperator.BETWEEN, value=(lo, hi))
    result = _apply_single(df, filt)
    if len(result) > 0:
        assert all(lo <= v <= hi for v in result["x"].to_list())


# ---------------------------------------------------------------------------
# Test 10: IN_LIST filter — result rows are all in the allowed list
# ---------------------------------------------------------------------------

@given(
    values=small_int_list,
    allowed=st.lists(st.integers(min_value=-1000, max_value=1000), min_size=1, max_size=10),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_in_list_filter_result_rows_in_allowed(values, allowed):
    """After IN_LIST filter, all result rows have x in the allowed list."""
    df = pl.DataFrame({"x": values})
    filt = Filter(column="x", operator=FilterOperator.IN_LIST, value=allowed)
    result = _apply_single(df, filt)
    allowed_set = set(allowed)
    if len(result) > 0:
        assert all(v in allowed_set for v in result["x"].to_list())


# ---------------------------------------------------------------------------
# Test 11: IS_NULL and IS_NOT_NULL are complementary
# ---------------------------------------------------------------------------

@given(
    non_null_values=st.lists(st.integers(min_value=-100, max_value=100), min_size=0, max_size=20),
    null_count=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
def test_is_null_and_is_not_null_complementary(non_null_values, null_count):
    """IS_NULL count + IS_NOT_NULL count == total row count."""
    assume(len(non_null_values) + null_count > 0)
    all_values = non_null_values + [None] * null_count
    df = pl.DataFrame({"x": all_values})

    null_filt = Filter(column="x", operator=FilterOperator.IS_NULL, value=None)
    not_null_filt = Filter(column="x", operator=FilterOperator.IS_NOT_NULL, value=None)

    null_result = _apply_single(df, null_filt)
    not_null_result = _apply_single(df, not_null_filt)

    assert len(null_result) + len(not_null_result) == len(df)


# ---------------------------------------------------------------------------
# Test 12: GE and LE filters
# ---------------------------------------------------------------------------

@given(values=small_int_list, threshold=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
def test_ge_filter_includes_equal(values, threshold):
    """GE filter includes rows equal to threshold (count >= GT count)."""
    df = pl.DataFrame({"x": values})
    ge_filt = Filter(column="x", operator=FilterOperator.GREATER_THAN_OR_EQUALS, value=threshold)
    gt_filt = Filter(column="x", operator=FilterOperator.GREATER_THAN, value=threshold)

    ge_result = _apply_single(df, ge_filt)
    gt_result = _apply_single(df, gt_filt)

    assert len(ge_result) >= len(gt_result)


@given(values=small_int_list, threshold=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
def test_le_filter_includes_equal(values, threshold):
    """LE filter includes rows equal to threshold (count >= LT count)."""
    df = pl.DataFrame({"x": values})
    le_filt = Filter(column="x", operator=FilterOperator.LESS_THAN_OR_EQUALS, value=threshold)
    lt_filt = Filter(column="x", operator=FilterOperator.LESS_THAN, value=threshold)

    le_result = _apply_single(df, le_filt)
    lt_result = _apply_single(df, lt_filt)

    assert len(le_result) >= len(lt_result)


# ---------------------------------------------------------------------------
# Test 13: CONTAINS filter — all result rows contain the substring
# ---------------------------------------------------------------------------

@given(
    values=small_str_list,
    needle=st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")), min_size=0, max_size=4),
)
@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
def test_contains_filter_all_rows_match(values, needle):
    """After CONTAINS filter, all rows have 'x' containing needle."""
    df = pl.DataFrame({"x": values})
    filt = Filter(
        column="x",
        operator=FilterOperator.CONTAINS,
        value=needle,
        filter_type=FilterType.TEXT_SEARCH,
        case_sensitive=True,
    )
    result = _apply_single(df, filt)
    if len(result) > 0:
        assert all(needle in v for v in result["x"].to_list())


# ---------------------------------------------------------------------------
# Test 14: Multiple filters — result row count <= each individual filter count
# ---------------------------------------------------------------------------

@given(
    values=small_int_list,
    lo=st.integers(min_value=-500, max_value=0),
    hi=st.integers(min_value=0, max_value=500),
)
@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
def test_multiple_filters_more_restrictive(values, lo, hi):
    """Applying GT+LT together yields <= rows than either alone."""
    df = pl.DataFrame({"x": values})

    gt_filt = Filter(column="x", operator=FilterOperator.GREATER_THAN, value=lo)
    lt_filt = Filter(column="x", operator=FilterOperator.LESS_THAN, value=hi)

    mgr = FilteringManager()
    mgr._schemes[DEFAULT_SCHEME_NAME].add_filter(gt_filt)
    mgr._schemes[DEFAULT_SCHEME_NAME].add_filter(lt_filt)
    combined = mgr.apply_filters(DEFAULT_SCHEME_NAME, df)

    gt_only = _apply_single(df, gt_filt)
    lt_only = _apply_single(df, lt_filt)

    assert len(combined) <= len(gt_only)
    assert len(combined) <= len(lt_only)
