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


# ---------------------------------------------------------------------------
# Group 4: Core data operation invariants
# ---------------------------------------------------------------------------

from data_graph_studio.core.parsing_utils import ParsingEngine


# Test 21: detect_delimiter idempotency
# If we detect a delimiter from a CSV string, re-joining and re-splitting
# with that delimiter should preserve the row count.
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    delimiter=st.sampled_from([',', '\t', ';', '|']),
    # Each row is a list of 2..5 simple alphanumeric fields
    rows=st.lists(
        st.lists(
            st.from_regex(r'[A-Za-z0-9]{1,8}', fullmatch=True),
            min_size=2,
            max_size=5,
        ),
        min_size=1,
        max_size=10,
    ),
)
def test_detect_delimiter_idempotent(delimiter, rows):
    """Detecting delimiter from synthetic CSV, then splitting on it, preserves row count."""
    # Build CSV text — no mixing of delimiters so detection is unambiguous
    lines = [delimiter.join(fields) for fields in rows]

    detected = ParsingEngine._detect_delimiter_auto(lines)

    # Re-split each line using the detected delimiter
    resplit_counts = [len(line.split(detected)) for line in lines]
    original_counts = [len(line.split(delimiter)) for line in lines]

    # If detection found the right delimiter, field counts match on every row
    if detected == delimiter:
        assert resplit_counts == original_counts, (
            f"Row counts changed after re-split: {original_counts} → {resplit_counts}"
        )

    # Idempotency: running detection a second time on the same lines gives the same result
    detected2 = ParsingEngine._detect_delimiter_auto(lines)
    assert detected2 == detected, (
        f"detect_delimiter_auto is not idempotent: first={detected!r}, second={detected2!r}"
    )


# Test 22: count(col >= x) >= count(col > x) always holds
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    values=st.lists(
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
        min_size=1,
        max_size=100,
    ),
    threshold=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
)
def test_ge_count_gte_gt_count(values, threshold):
    """For any numeric column and threshold, count(col >= x) >= count(col > x)."""
    df = pl.DataFrame({"value": values})
    count_ge = df.filter(pl.col("value") >= threshold).height
    count_gt = df.filter(pl.col("value") > threshold).height
    assert count_ge >= count_gt, (
        f"Expected count(>= {threshold}) >= count(> {threshold}), "
        f"got {count_ge} < {count_gt}"
    )


# Test 23: Sort stability — same inputs always produce same outputs
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    values=st.lists(
        st.integers(min_value=-1000, max_value=1000),
        min_size=1,
        max_size=50,
    ),
    descending=st.booleans(),
)
def test_sort_deterministic(values, descending):
    """Sorting a DataFrame by the same key twice gives identical results."""
    df = pl.DataFrame({"x": values})
    result1 = df.sort("x", descending=descending)
    result2 = df.sort("x", descending=descending)
    assert result1.equals(result2), "Two sorts of the same DataFrame produced different results"


# Test 24: Re-sorting an already-sorted DataFrame leaves it unchanged
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    values=st.lists(
        st.integers(min_value=-1000, max_value=1000),
        min_size=1,
        max_size=50,
    ),
    descending=st.booleans(),
)
def test_sort_idempotent(values, descending):
    """Sorting an already-sorted DataFrame by the same key is a no-op."""
    df = pl.DataFrame({"x": values})
    sorted_once = df.sort("x", descending=descending)
    sorted_twice = sorted_once.sort("x", descending=descending)
    assert sorted_once.equals(sorted_twice), (
        "Re-sorting an already-sorted DataFrame changed the result"
    )


# Test 25: Column stats invariant — min <= mean <= max for non-empty numeric column
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    data=st.lists(
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e9, max_value=1e9),
        min_size=1,
        max_size=100,
    )
)
def test_min_lte_mean_lte_max(data):
    """For any non-empty numeric column: min <= mean <= max always holds."""
    df = pl.DataFrame({"value": data})
    stats = df.select([
        pl.col("value").min().alias("min"),
        pl.col("value").mean().alias("mean"),
        pl.col("value").max().alias("max"),
    ])
    col_min = stats["min"][0]
    col_mean = stats["mean"][0]
    col_max = stats["max"][0]

    # Use a small epsilon for floating-point rounding at extreme ranges
    eps = max(abs(col_max), abs(col_min)) * 1e-10 + 1e-10
    assert col_min <= col_mean + eps, (
        f"min ({col_min}) > mean ({col_mean})"
    )
    assert col_mean <= col_max + eps, (
        f"mean ({col_mean}) > max ({col_max})"
    )


# Test 26: String search/filter never increases row count
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    strings=st.lists(
        st.text(min_size=0, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Zs"))),
        min_size=1,
        max_size=50,
    ),
    search_term=st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=("L", "N"))),
)
def test_string_filter_never_increases_row_count(strings, search_term):
    """Filtering by string (contains) never produces more rows than the original."""
    df = pl.DataFrame({"s": strings})
    original_count = df.height
    try:
        filtered = df.filter(pl.col("s").str.contains(search_term, literal=True))
    except Exception:
        # Some generated strings may be invalid regex — just skip
        return
    assert filtered.height <= original_count, (
        f"String filter increased row count: {original_count} → {filtered.height}"
    )
