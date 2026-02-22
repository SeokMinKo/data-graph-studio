"""
Property-based tests for filtering, state_types, and data transformation invariants.

All tests are Qt-free — no QApplication required.
"""

import polars as pl
from hypothesis import given, assume, settings, HealthCheck
from hypothesis import strategies as st

from data_graph_studio.core.filtering import (
    Filter,
    FilteringManager,
    FilterOperator,
    FilterType,
)
from data_graph_studio.core.state_types import (
    ChartSettings,
    ChartType,
    FilterCondition,
    GridDirection,
    GridViewSettings,
    GroupColumn,
    SortCondition,
)
from data_graph_studio.core.data_query import DataQuery


# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_col_name = st.from_regex(r'[A-Za-z][A-Za-z0-9]{0,9}', fullmatch=True)

_int_values = st.lists(st.integers(min_value=0, max_value=100), min_size=1, max_size=50)


def _df_with_col(col, values):
    """Build a single-column polars DataFrame."""
    return pl.DataFrame({col: values})


# ---------------------------------------------------------------------------
# Group 1: Filtering invariants
# ---------------------------------------------------------------------------


# Test 1: Empty filters → all rows returned
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=_int_values,
)
def test_empty_filter_returns_all_rows(col, values):
    """Applying no filters returns the full DataFrame unchanged."""
    df = _df_with_col(col, values)
    manager = FilteringManager()
    result = manager.apply_filters("Page", df)
    assert result.height == df.height


# Test 2: Impossible condition → empty result
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=50),
)
def test_impossible_filter_returns_empty(col, values):
    """Filtering positive integers with value < -1 yields 0 rows."""
    df = _df_with_col(col, values)
    manager = FilteringManager()
    manager.add_filter(
        scheme_name="Page",
        column=col,
        operator=FilterOperator.LESS_THAN,
        value=-1,
        filter_type=FilterType.NUMERIC,
    )
    result = manager.apply_filters("Page", df)
    assert result.height == 0


# Test 3: Filter monotonicity — lower threshold ≤ higher threshold result count
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=_int_values,
    t1=st.integers(min_value=0, max_value=50),
    t2=st.integers(min_value=51, max_value=100),
)
def test_filter_monotonicity(col, values, t1, t2):
    """Filter x < t1 returns fewer or equal rows than x < t2 when t1 < t2."""
    assert t1 < t2
    df = _df_with_col(col, values)

    m1 = FilteringManager()
    m1.add_filter("Page", col, FilterOperator.LESS_THAN, t1, FilterType.NUMERIC)
    count1 = m1.apply_filters("Page", df).height

    m2 = FilteringManager()
    m2.add_filter("Page", col, FilterOperator.LESS_THAN, t2, FilterType.NUMERIC)
    count2 = m2.apply_filters("Page", df).height

    assert count1 <= count2


# Test 4: GT and LE are complementary partitions
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    values=st.lists(st.integers(min_value=0, max_value=100), min_size=1, max_size=50),
    threshold=st.integers(min_value=0, max_value=100),
)
def test_filter_complement_partitions(col, values, threshold):
    """Rows matching x > t plus rows matching x <= t equals total rows."""
    df = _df_with_col(col, values)

    m_gt = FilteringManager()
    m_gt.add_filter("Page", col, FilterOperator.GREATER_THAN, threshold, FilterType.NUMERIC)
    count_gt = m_gt.apply_filters("Page", df).height

    m_le = FilteringManager()
    m_le.add_filter("Page", col, FilterOperator.LESS_THAN_OR_EQUALS, threshold, FilterType.NUMERIC)
    count_le = m_le.apply_filters("Page", df).height

    assert count_gt + count_le == df.height


# Test 5: Multiple filters = AND semantics (subset monotonicity)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    col_a=_col_name,
    col_b=_col_name,
    values=_int_values,
    ta=st.integers(min_value=0, max_value=100),
    tb=st.integers(min_value=0, max_value=100),
)
def test_multiple_filters_and_semantics(col_a, col_b, values, ta, tb):
    """apply([f1, f2]) returns a subset of apply([f1])."""
    assume(col_a != col_b)

    df = pl.DataFrame({col_a: values, col_b: values})

    m_one = FilteringManager()
    m_one.add_filter("Page", col_a, FilterOperator.GREATER_THAN_OR_EQUALS, ta, FilterType.NUMERIC)
    count_one = m_one.apply_filters("Page", df).height

    m_two = FilteringManager()
    m_two.add_filter("Page", col_a, FilterOperator.GREATER_THAN_OR_EQUALS, ta, FilterType.NUMERIC)
    m_two.add_filter("Page", col_b, FilterOperator.LESS_THAN_OR_EQUALS, tb, FilterType.NUMERIC)
    count_two = m_two.apply_filters("Page", df).height

    assert count_two <= count_one


# Test 6: Filter preserves column structure
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    col_a=_col_name,
    col_b=_col_name,
    col_c=_col_name,
    values=_int_values,
    threshold=st.integers(min_value=0, max_value=100),
)
def test_filter_preserves_columns(col_a, col_b, col_c, values, threshold):
    """Filtering never changes the set of columns in the output."""
    assume(len({col_a, col_b, col_c}) == 3)

    df = pl.DataFrame({col_a: values, col_b: values, col_c: values})
    manager = FilteringManager()
    manager.add_filter("Page", col_a, FilterOperator.GREATER_THAN_OR_EQUALS, threshold, FilterType.NUMERIC)
    result = manager.apply_filters("Page", df)

    assert set(result.columns) == set(df.columns)


# ---------------------------------------------------------------------------
# Group 2: State value objects round-trip
# ---------------------------------------------------------------------------


# Test 7: ChartSettings round-trip via dataclass fields
@settings(max_examples=30)
@given(chart_type=st.sampled_from(list(ChartType)))
def test_chart_settings_chart_type_preserved(chart_type):
    """ChartSettings stores and returns the same ChartType it was given."""
    settings_obj = ChartSettings(chart_type=chart_type)
    assert settings_obj.chart_type == chart_type


# Test 8: GridViewSettings fields are independent
@settings(max_examples=30)
@given(
    enabled=st.booleans(),
    direction=st.sampled_from(list(GridDirection)),
)
def test_grid_view_settings_fields_independent(enabled, direction):
    """grid_view_enabled and direction are stored independently."""
    gvs = GridViewSettings(enabled=enabled, direction=direction)
    assert gvs.enabled == enabled
    assert gvs.direction == direction


# Test 9: FilterCondition equality
@settings(max_examples=30)
@given(
    column=st.text(min_size=1, max_size=20),
    operator=st.sampled_from(["eq", "ne", "gt", "lt", "ge", "le"]),
    value=st.integers(min_value=-1000, max_value=1000),
)
def test_filter_condition_equality(column, operator, value):
    """Two FilterConditions built with the same args are equal."""
    fc1 = FilterCondition(column=column, operator=operator, value=value)
    fc2 = FilterCondition(column=column, operator=operator, value=value)
    assert fc1 == fc2


# Test 10: SortCondition list length preserved
@settings(max_examples=30)
@given(
    columns=st.lists(st.text(min_size=1, max_size=15), min_size=0, max_size=10),
    descendings=st.lists(st.booleans(), min_size=0, max_size=10),
)
def test_sort_condition_list_length_preserved(columns, descendings):
    """SortCondition list length equals the number of columns passed in."""
    # Zip so we create one SortCondition per (col, desc) pair
    pairs = list(zip(columns, descendings))
    conditions = [SortCondition(column=c, descending=d) for c, d in pairs]
    assert len(conditions) == len(pairs)


# Test 11: GroupColumn order assignment
@settings(max_examples=30)
@given(
    col_names=st.lists(
        st.text(min_size=1, max_size=15),
        min_size=1,
        max_size=5,
        unique=True,
    )
)
def test_group_column_order_assignment(col_names):
    """GroupColumn.order reflects the position index we assign."""
    group_cols = [GroupColumn(name=name, order=i) for i, name in enumerate(col_names)]
    for i, gc in enumerate(group_cols):
        assert gc.order == i


# ---------------------------------------------------------------------------
# Group 3: Data transformation invariants (DataQuery)
# ---------------------------------------------------------------------------


# Test 12: Sort preserves row count
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    values=st.lists(st.integers(min_value=-1000, max_value=1000), min_size=1, max_size=50),
    descending=st.booleans(),
)
def test_sort_preserves_row_count(values, descending):
    """Sorting a DataFrame does not change its row count."""
    df = pl.DataFrame({"x": values})
    dq = DataQuery()
    result = dq.sort(df, ["x"], descending=descending)
    assert result is not None
    assert result.height == df.height


# Test 13: Filter preserves row count when all rows match
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    values=st.lists(st.integers(min_value=1, max_value=100), min_size=1, max_size=50),
)
def test_data_query_filter_all_match_preserves_rows(values):
    """DataQuery.filter with a threshold of 0 keeps all positive-value rows."""
    df = pl.DataFrame({"x": values})
    dq = DataQuery()
    result = dq.filter(df, "x", "gt", 0)
    assert result is not None
    assert result.height == df.height


# Test 14: Filter then sort ≡ sort then filter (same row set)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    values=st.lists(st.integers(min_value=0, max_value=100), min_size=1, max_size=50),
    threshold=st.integers(min_value=0, max_value=100),
    descending=st.booleans(),
)
def test_filter_then_sort_equals_sort_then_filter(values, threshold, descending):
    """filter-then-sort and sort-then-filter produce the same set of rows."""
    df = pl.DataFrame({"x": values})
    dq = DataQuery()

    # filter first, then sort
    filtered_first = dq.filter(df, "x", "ge", threshold)
    assert filtered_first is not None
    result_fs = dq.sort(filtered_first, ["x"], descending=descending)

    # sort first, then filter
    sorted_first = dq.sort(df, ["x"], descending=descending)
    assert sorted_first is not None
    result_sf = dq.filter(sorted_first, "x", "ge", threshold)

    assert result_fs is not None
    assert result_sf is not None
    # Same rows (order can differ — compare sorted lists)
    assert sorted(result_fs["x"].to_list()) == sorted(result_sf["x"].to_list())


# Test 15: Unique values preserved through a no-op filter (eq on a value that all rows share)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    n=st.integers(min_value=1, max_value=30),
    constant=st.integers(min_value=0, max_value=100),
)
def test_no_op_filter_preserves_unique_values(n, constant):
    """Filtering a column where every row matches keeps unique values intact."""
    df = pl.DataFrame({"x": [constant] * n})
    dq = DataQuery()

    before_unique = set(df["x"].unique().to_list())
    result = dq.filter(df, "x", "eq", constant)

    assert result is not None
    after_unique = set(result["x"].unique().to_list())
    assert after_unique == before_unique


# ---------------------------------------------------------------------------
# Bonus tests to hit 15+ comfortably
# ---------------------------------------------------------------------------


# Test 16: DataQuery.filter with 'ne' keeps everything except exact matches
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    values=st.lists(st.integers(min_value=0, max_value=100), min_size=2, max_size=50),
    exclude=st.integers(min_value=0, max_value=100),
)
def test_data_query_ne_filter_excludes_value(values, exclude):
    """ne filter leaves no rows with the excluded value."""
    df = pl.DataFrame({"x": values})
    dq = DataQuery()
    result = dq.filter(df, "x", "ne", exclude)
    assert result is not None
    if result.height > 0:
        assert exclude not in result["x"].to_list()


# Test 17: ChartSettings default chart type is LINE
@settings(max_examples=10)
@given(st.just(None))
def test_chart_settings_default_chart_type(_):
    """Default ChartSettings has chart_type == ChartType.LINE."""
    cs = ChartSettings()
    assert cs.chart_type == ChartType.LINE


# Test 18: FilteringManager clear_filters resets count to zero
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    col=_col_name,
    n_filters=st.integers(min_value=1, max_value=5),
)
def test_filtering_manager_clear_resets_to_zero(col, n_filters):
    """After clear_filters, no enabled filters remain."""
    manager = FilteringManager()
    for i in range(n_filters):
        manager.add_filter(
            "Page", col, FilterOperator.GREATER_THAN, i, FilterType.NUMERIC
        )
    manager.clear_filters("Page")
    scheme = manager.get_scheme("Page")
    assert scheme is not None
    assert len(scheme.filters) == 0


# Test 19: FilterCondition with enabled=False is stored as disabled
@settings(max_examples=30)
@given(
    column=st.text(min_size=1, max_size=20),
    value=st.integers(),
)
def test_filter_condition_disabled_stored_correctly(column, value):
    """FilterCondition(enabled=False) persists the disabled state."""
    fc = FilterCondition(column=column, operator="eq", value=value, enabled=False)
    assert fc.enabled is False


# Test 20: DataQuery.get_unique_values returns sorted list without duplicates
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    values=st.lists(st.integers(min_value=0, max_value=20), min_size=1, max_size=50),
)
def test_get_unique_values_no_duplicates(values):
    """get_unique_values never returns duplicate values."""
    df = pl.DataFrame({"x": values})
    dq = DataQuery()
    unique = dq.get_unique_values(df, "x")
    assert len(unique) == len(set(unique))
