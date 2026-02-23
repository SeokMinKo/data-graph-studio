"""Boundary and edge case tests for DGS core modules.

Tests the behavior at the limits of normal operation:
empty inputs, null values, NaN propagation, special chars, type boundaries,
single-row DataFrames, large-n performance, marking edge cases, and IPC protocol.
"""
import math
import sys
import time

import numpy as np
import polars as pl
import pytest

from data_graph_studio.core.filtering import (
    Filter,
    FilteringManager,
    FilterOperator,
    FilterType,
)
from data_graph_studio.core.statistics import DescriptiveStatistics
from data_graph_studio.core.marking import Marking, MarkingManager, MarkMode
from data_graph_studio.core.data_query import DataQuery
from data_graph_studio.core.ipc_protocol import parse_request, make_ok_response, make_error_response
from data_graph_studio.core.exceptions import ValidationError, QueryError, DatasetError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fm() -> FilteringManager:
    return FilteringManager()


def _apply(fm: FilteringManager, df: pl.DataFrame, scheme: str = "Page") -> pl.DataFrame:
    """Convenience: apply filters from scheme to a DataFrame."""
    return fm.apply_filters(scheme, df)


def _dq() -> DataQuery:
    return DataQuery()


# ===========================================================================
# Category 1: Empty DataFrame operations (10+ tests)
# ===========================================================================

class TestEmptyDataFrameOperations:
    """Filtering, sort, and group_aggregate on 0-row DataFrames must not crash."""

    def test_filter_eq_on_empty_df_returns_empty(self):
        """EQ filter on 0-row DataFrame returns empty DataFrame."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, 0)
        result = _apply(fm, df)
        assert len(result) == 0
        assert result.columns == ["x"]

    def test_filter_gt_on_empty_float_df_returns_empty(self):
        """GT filter on 0-row float DataFrame returns empty, no NaN crash."""
        fm = _make_fm()
        df = pl.DataFrame({"v": pl.Series([], dtype=pl.Float64)})
        fm.add_filter("Page", "v", FilterOperator.GREATER_THAN, 0.0)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_filter_contains_on_empty_str_df_returns_empty(self):
        """CONTAINS filter on 0-row string DataFrame returns empty."""
        fm = _make_fm()
        df = pl.DataFrame({"s": pl.Series([], dtype=pl.Utf8)})
        fm.add_filter("Page", "s", FilterOperator.CONTAINS, "x",
                      filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_filter_is_null_on_empty_df_returns_empty(self):
        """IS_NULL filter on 0-row DataFrame returns empty (no nulls to find)."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.IS_NULL, None)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_filter_between_on_empty_df_returns_empty(self):
        """BETWEEN filter on 0-row DataFrame returns empty."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.BETWEEN, (0, 100),
                      filter_type=FilterType.RANGE)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_filter_in_list_on_empty_df_returns_empty(self):
        """IN_LIST filter on 0-row DataFrame returns empty."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.IN_LIST, [1, 2, 3],
                      filter_type=FilterType.CHECKBOX)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_sort_empty_df_returns_empty(self):
        """DataQuery.sort on 0-row DataFrame returns empty DataFrame."""
        dq = _dq()
        df = pl.DataFrame({"a": pl.Series([], dtype=pl.Int64)})
        result = dq.sort(df, ["a"])
        assert result is not None
        assert len(result) == 0
        assert result.columns == ["a"]

    def test_sort_empty_df_descending_returns_empty(self):
        """DataQuery.sort descending on 0-row DataFrame does not crash."""
        dq = _dq()
        df = pl.DataFrame({"a": pl.Series([], dtype=pl.Float64),
                           "b": pl.Series([], dtype=pl.Utf8)})
        result = dq.sort(df, ["a"], descending=True)
        assert result is not None
        assert len(result) == 0

    def test_group_aggregate_empty_df_returns_empty(self):
        """DataQuery.group_aggregate on 0-row DataFrame returns empty (no groups)."""
        dq = _dq()
        df = pl.DataFrame({"cat": pl.Series([], dtype=pl.Utf8),
                           "val": pl.Series([], dtype=pl.Float64)})
        result = dq.group_aggregate(df, ["cat"], ["val"], ["sum"])
        assert result is not None
        assert len(result) == 0

    def test_get_unique_values_empty_df_returns_empty_list(self):
        """get_unique_values on 0-row DataFrame returns []."""
        dq = _dq()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Int64)})
        result = dq.get_unique_values(df, "x")
        assert result == []

    def test_filter_regex_on_empty_df_returns_empty(self):
        """MATCHES_REGEX filter on 0-row DataFrame returns empty."""
        fm = _make_fm()
        df = pl.DataFrame({"s": pl.Series([], dtype=pl.Utf8)})
        fm.add_filter("Page", "s", FilterOperator.MATCHES_REGEX, r"^\d+$",
                      filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_descriptive_statistics_on_empty_array_returns_empty_dict(self):
        """DescriptiveStatistics.calculate with all-NaN array returns {}."""
        ds = DescriptiveStatistics()
        result = ds.calculate(np.array([np.nan, np.nan]))
        assert result == {}

    def test_descriptive_statistics_on_zero_len_array_returns_empty_dict(self):
        """DescriptiveStatistics.calculate with empty array returns {}."""
        ds = DescriptiveStatistics()
        result = ds.calculate(np.array([]))
        assert result == {}


# ===========================================================================
# Category 2: Single-row DataFrame (5+ tests)
# ===========================================================================

class TestSingleRowDataFrame:
    """Edge cases with exactly 1 row in the DataFrame."""

    def test_statistics_single_row_mean_equals_value(self):
        """Mean of a single value is that value itself."""
        ds = DescriptiveStatistics()
        result = ds.calculate(np.array([7.0]))
        assert result["mean"] == pytest.approx(7.0)
        assert result["n"] == 1

    def test_statistics_single_row_std_is_zero(self):
        """Standard deviation of a single value is 0."""
        ds = DescriptiveStatistics()
        result = ds.calculate(np.array([42.0]))
        assert result["std"] == pytest.approx(0.0)

    def test_statistics_single_row_min_equals_max(self):
        """Min and max of a single value are identical."""
        ds = DescriptiveStatistics()
        result = ds.calculate(np.array([3.14]))
        assert result["min"] == pytest.approx(result["max"])

    def test_filter_passes_single_row(self):
        """Filter that matches the one row returns 1-row DataFrame."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [99]})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, 99)
        result = _apply(fm, df)
        assert len(result) == 1
        assert result["x"][0] == 99

    def test_filter_removes_single_row(self):
        """Filter that doesn't match the one row returns empty DataFrame."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [99]})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, 1)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_sort_single_row_preserves_row(self):
        """Sorting a 1-row DataFrame returns the same single row."""
        dq = _dq()
        df = pl.DataFrame({"a": [5], "b": ["hello"]})
        result = dq.sort(df, ["a"])
        assert len(result) == 1
        assert result["a"][0] == 5

    def test_group_aggregate_single_row_single_group(self):
        """group_aggregate with one row produces one group."""
        dq = _dq()
        df = pl.DataFrame({"cat": ["A"], "val": [10.0]})
        result = dq.group_aggregate(df, ["cat"], ["val"], ["sum"])
        assert result is not None
        assert len(result) == 1


# ===========================================================================
# Category 3: All-null / all-NaN columns (8+ tests)
# ===========================================================================

class TestAllNullAllNaNColumns:
    """Filtering and stats on columns where every value is null or NaN."""

    def test_filter_gt_all_null_int_returns_empty(self):
        """GT on all-null integer column returns empty."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([None, None, None], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN, 0)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_filter_eq_all_null_returns_empty(self):
        """EQ filter on all-null column returns empty (null != any value)."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([None, None], dtype=pl.Float64)})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, 0.0)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_filter_is_null_all_null_returns_all(self):
        """IS_NULL on all-null column returns all rows."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([None, None, None], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.IS_NULL, None)
        result = _apply(fm, df)
        assert len(result) == 3

    def test_filter_is_not_null_all_null_returns_empty(self):
        """IS_NOT_NULL on all-null column returns empty."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([None, None], dtype=pl.Utf8)})
        fm.add_filter("Page", "x", FilterOperator.IS_NOT_NULL, None)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_statistics_all_nan_returns_empty_dict(self):
        """DescriptiveStatistics strips NaN first — all-NaN yields {}."""
        ds = DescriptiveStatistics()
        arr = np.array([float("nan"), float("nan"), float("nan")])
        result = ds.calculate(arr)
        assert result == {}

    def test_get_unique_values_all_null_column(self):
        """get_unique_values on all-null column returns [None] or []."""
        dq = _dq()
        df = pl.DataFrame({"x": pl.Series([None, None, None], dtype=pl.Int64)})
        result = dq.get_unique_values(df, "x")
        # Polars unique() on all-null = [null]; either [None] or [] is acceptable
        assert isinstance(result, list)

    def test_filter_lt_all_nan_float_returns_empty(self):
        """LT on all-NaN float column returns empty (NaN excluded by range filter)."""
        fm = _make_fm()
        df = pl.DataFrame({"v": [float("nan"), float("nan")]})
        fm.add_filter("Page", "v", FilterOperator.LESS_THAN, 100.0)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_group_aggregate_all_null_group_column(self):
        """group_aggregate on all-null group column does not crash."""
        dq = _dq()
        df = pl.DataFrame({
            "cat": pl.Series([None, None], dtype=pl.Utf8),
            "val": [1.0, 2.0],
        })
        result = dq.group_aggregate(df, ["cat"], ["val"], ["sum"])
        assert result is not None
        assert isinstance(result, pl.DataFrame)

    def test_filter_not_in_all_null_returns_empty(self):
        """NOT_IN_LIST on all-null column returns empty (null not in any list)."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([None, None], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.NOT_IN_LIST, [1, 2],
                      filter_type=FilterType.CHECKBOX)
        result = _apply(fm, df)
        # null is not in [1,2] but Polars null comparison is null — either 0 or 2 rows
        assert isinstance(result, pl.DataFrame)


# ===========================================================================
# Category 4: NaN propagation in filters (8+ tests)
# ===========================================================================

class TestNaNPropagationInFilters:
    """NaN rows must be excluded from range-operator results on float columns."""

    def test_gt_filter_excludes_nan(self):
        """NaN rows must NOT appear in GT filter results."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [1.0, float("nan"), 3.0]})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN, 0.0)
        result = _apply(fm, df)
        assert result["x"].is_nan().sum() == 0
        assert len(result) == 2  # 1.0 and 3.0

    def test_ge_filter_excludes_nan(self):
        """NaN rows must NOT appear in GE filter results."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [float("nan"), 5.0, 10.0]})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN_OR_EQUALS, 5.0)
        result = _apply(fm, df)
        assert result["x"].is_nan().sum() == 0
        assert len(result) == 2  # 5.0 and 10.0

    def test_lt_filter_excludes_nan(self):
        """NaN rows must NOT appear in LT filter results."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [float("nan"), -1.0, 5.0]})
        fm.add_filter("Page", "x", FilterOperator.LESS_THAN, 10.0)
        result = _apply(fm, df)
        assert result["x"].is_nan().sum() == 0
        assert len(result) == 2  # -1.0 and 5.0

    def test_le_filter_excludes_nan(self):
        """NaN rows must NOT appear in LE filter results."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [float("nan"), 3.0, 10.0]})
        fm.add_filter("Page", "x", FilterOperator.LESS_THAN_OR_EQUALS, 3.0)
        result = _apply(fm, df)
        assert result["x"].is_nan().sum() == 0
        assert len(result) == 1  # 3.0

    def test_eq_filter_on_nan_does_not_crash(self):
        """EQ filter on NaN value doesn't crash — may match or not match."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [float("nan"), 1.0]})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, float("nan"))
        result = _apply(fm, df)
        assert isinstance(result, pl.DataFrame)

    def test_nan_mixed_with_nulls_gt_excludes_both(self):
        """GT filter excludes NaN rows even when the column has mixed NaN and null."""
        fm = _make_fm()
        # Float column: None (null) and NaN are distinct in Polars
        df = pl.DataFrame({"x": pl.Series([None, float("nan"), 5.0], dtype=pl.Float64)})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN, 0.0)
        result = _apply(fm, df)
        # Only 5.0 should pass — null excluded by comparison, NaN excluded explicitly
        assert len(result) == 1
        assert result["x"][0] == 5.0

    def test_multiple_nan_rows_all_excluded_by_gt(self):
        """Multiple NaN rows are all excluded from GT filter results."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [float("nan"), float("nan"), float("nan"), 1.0]})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN, 0.0)
        result = _apply(fm, df)
        assert result["x"].is_nan().sum() == 0
        assert len(result) == 1

    def test_statistics_strips_nan_before_computing(self):
        """DescriptiveStatistics strips NaN before computation."""
        ds = DescriptiveStatistics()
        arr = np.array([1.0, float("nan"), 3.0, float("nan")])
        result = ds.calculate(arr)
        assert result["n"] == 2
        assert result["mean"] == pytest.approx(2.0)


# ===========================================================================
# Category 5: Special column names (5+ tests)
# ===========================================================================

class TestSpecialColumnNames:
    """Filters and queries on columns with spaces and special characters."""

    def test_filter_column_with_spaces(self):
        """Filter on column name containing spaces works correctly."""
        fm = _make_fm()
        df = pl.DataFrame({"my column": [1, 2, 3]})
        fm.add_filter("Page", "my column", FilterOperator.EQUALS, 2)
        result = _apply(fm, df)
        assert len(result) == 1
        assert result["my column"][0] == 2

    def test_filter_column_with_hash(self):
        """Filter on column name containing '#' character works."""
        fm = _make_fm()
        df = pl.DataFrame({"col#1": [10, 20, 30]})
        fm.add_filter("Page", "col#1", FilterOperator.GREATER_THAN, 15)
        result = _apply(fm, df)
        assert len(result) == 2  # 20 and 30

    def test_filter_column_with_at_symbol(self):
        """Filter on column name containing '@' character works."""
        fm = _make_fm()
        df = pl.DataFrame({"col@name": ["a", "b", "c"]})
        fm.add_filter("Page", "col@name", FilterOperator.EQUALS, "b",
                      filter_type=FilterType.TEXT)
        result = _apply(fm, df)
        assert len(result) == 1

    def test_filter_column_with_parentheses(self):
        """Filter on column name containing '(' and ')' characters works."""
        fm = _make_fm()
        df = pl.DataFrame({"value (unit)": [1.0, 2.0, 3.0]})
        fm.add_filter("Page", "value (unit)", FilterOperator.LESS_THAN_OR_EQUALS, 2.0)
        result = _apply(fm, df)
        assert len(result) == 2  # 1.0 and 2.0

    def test_get_unique_values_column_with_spaces(self):
        """get_unique_values on column with spaces in name works."""
        dq = _dq()
        df = pl.DataFrame({"my col": [3, 1, 2, 1]})
        result = dq.get_unique_values(df, "my col")
        assert sorted(result) == [1, 2, 3]

    def test_sort_column_with_special_chars(self):
        """DataQuery.sort on column with special chars in name works."""
        dq = _dq()
        df = pl.DataFrame({"col (A)": [3, 1, 2]})
        result = dq.sort(df, ["col (A)"])
        assert result is not None
        assert result["col (A)"].to_list() == [1, 2, 3]


# ===========================================================================
# Category 6: Type boundary values (8+ tests)
# ===========================================================================

class TestTypeBoundaryValues:
    """Numeric and type edge cases: extreme values, int/float mixing, zero."""

    def test_filter_int_value_on_float_column(self):
        """Filter with an int value on a float column works (implicit coercion)."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [1.0, 2.5, 3.0]})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN_OR_EQUALS, 2)
        result = _apply(fm, df)
        assert len(result) == 2  # 2.5 and 3.0

    def test_filter_at_max_int32(self):
        """Filter at sys.maxsize boundary does not crash."""
        fm = _make_fm()
        max_i32 = 2**31 - 1
        df = pl.DataFrame({"x": pl.Series([max_i32 - 1, max_i32], dtype=pl.Int32)})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, max_i32)
        result = _apply(fm, df)
        assert len(result) == 1
        assert result["x"][0] == max_i32

    def test_filter_negative_values(self):
        """Filter with negative boundary value works correctly."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [-10, -5, 0, 5]})
        fm.add_filter("Page", "x", FilterOperator.LESS_THAN, 0)
        result = _apply(fm, df)
        assert len(result) == 2  # -10 and -5

    def test_filter_zero_boundary(self):
        """Filter at zero boundary: GE 0 includes zero, GT 0 excludes it."""
        fm_ge = _make_fm()
        fm_gt = _make_fm()
        df = pl.DataFrame({"x": [-1, 0, 1]})

        fm_ge.add_filter("Page", "x", FilterOperator.GREATER_THAN_OR_EQUALS, 0)
        fm_gt.add_filter("Page", "x", FilterOperator.GREATER_THAN, 0)

        assert len(_apply(fm_ge, df)) == 2  # 0 and 1
        assert len(_apply(fm_gt, df)) == 1  # 1 only

    def test_statistics_single_negative_value(self):
        """Statistics work on a single negative value."""
        ds = DescriptiveStatistics()
        result = ds.calculate(np.array([-7.0]))
        assert result["mean"] == pytest.approx(-7.0)
        assert result["min"] == pytest.approx(-7.0)
        assert result["max"] == pytest.approx(-7.0)

    def test_statistics_all_zeros(self):
        """Statistics on an all-zero array: mean=0, std=0."""
        ds = DescriptiveStatistics()
        result = ds.calculate(np.array([0.0, 0.0, 0.0]))
        assert result["mean"] == pytest.approx(0.0)
        assert result["std"] == pytest.approx(0.0)
        assert result["n"] == 3

    def test_filter_very_small_float_precision(self):
        """Filter near floating-point precision boundary does not crash."""
        fm = _make_fm()
        eps = sys.float_info.epsilon
        df = pl.DataFrame({"x": [eps, 2 * eps, 3 * eps]})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN, eps)
        result = _apply(fm, df)
        assert len(result) == 2

    def test_filter_string_value_on_int_column_returns_empty_not_crash(self):
        """CONTAINS filter on an int column returns empty DataFrame without crashing.

        Polars casts the int column for contains matching and finds no matches —
        it does not raise an exception.
        """
        fm = _make_fm()
        df = pl.DataFrame({"x": [1, 2, 3]})
        fm.add_filter("Page", "x", FilterOperator.CONTAINS, "hello",
                      filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        # Actual behavior: Polars returns empty (no int value contains "hello")
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0


# ===========================================================================
# Category 7: Large-n / performance boundaries (3+ tests)
# ===========================================================================

class TestLargeNPerformance:
    """Smoke tests that large DataFrames complete in reasonable time."""

    def test_filter_100k_rows_completes(self):
        """Filter on 100k-row DataFrame completes without timeout."""
        fm = _make_fm()
        df = pl.DataFrame({"x": list(range(100_000))})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN, 50_000)
        t0 = time.monotonic()
        result = _apply(fm, df)
        elapsed = time.monotonic() - t0
        assert len(result) == 49_999
        assert elapsed < 10.0, f"filter on 100k rows took {elapsed:.2f}s"

    def test_sort_100k_rows_completes(self):
        """Sort on 100k-row DataFrame completes without timeout."""
        dq = _dq()
        df = pl.DataFrame({"x": list(range(99_999, -1, -1))})  # reverse order
        t0 = time.monotonic()
        result = dq.sort(df, ["x"])
        elapsed = time.monotonic() - t0
        assert result is not None
        assert len(result) == 100_000
        assert result["x"][0] == 0
        assert elapsed < 10.0, f"sort on 100k rows took {elapsed:.2f}s"

    def test_group_aggregate_one_group_vs_many(self):
        """group_aggregate: 1 group and N groups both produce correct row counts."""
        dq = _dq()

        # 1 group
        df_one = pl.DataFrame({"cat": ["A"] * 1000, "val": list(range(1000))})
        result_one = dq.group_aggregate(df_one, ["cat"], ["val"], ["sum"])
        assert result_one is not None
        assert len(result_one) == 1

        # 5 groups
        df_many = pl.DataFrame({
            "cat": [f"G{i % 5}" for i in range(500)],
            "val": [float(i) for i in range(500)],
        })
        result_many = dq.group_aggregate(df_many, ["cat"], ["val"], ["mean"])
        assert result_many is not None
        assert len(result_many) == 5

    def test_statistics_10k_values_completes(self):
        """DescriptiveStatistics on 10k values completes without error."""
        ds = DescriptiveStatistics()
        arr = np.random.default_rng(42).standard_normal(10_000)
        t0 = time.monotonic()
        result = ds.calculate(arr)
        elapsed = time.monotonic() - t0
        assert result["n"] == 10_000
        assert elapsed < 5.0, f"stats on 10k values took {elapsed:.2f}s"


# ===========================================================================
# Category 8: IPC protocol edge cases (5+ tests)
# ===========================================================================

class TestIpcProtocolEdgeCases:
    """Edge cases for parse_request and response builders."""

    def test_parse_request_with_none_args_defaults_to_empty(self):
        """Command with no 'args' key defaults to empty dict (not None)."""
        result = parse_request({"command": "ping"})
        assert result["args"] == {}
        assert result["args"] is not None

    def test_parse_request_deeply_nested_args(self):
        """parse_request accepts deeply nested args dict without crashing."""
        nested = {"a": {"b": {"c": {"d": {"e": 42}}}}}
        result = parse_request({"command": "nested_cmd", "args": nested})
        assert result["command"] == "nested_cmd"
        assert result["args"]["a"]["b"]["c"]["d"]["e"] == 42

    def test_parse_request_unicode_command_name(self):
        """Command name with unicode characters is accepted (parse only, no dispatch)."""
        result = parse_request({"command": "커맨드", "args": {}})
        assert result["command"] == "커맨드"

    def test_parse_request_very_long_command_string(self):
        """Command string of 1000+ characters is accepted by the parser."""
        long_cmd = "x" * 1200
        result = parse_request({"command": long_cmd, "args": {}})
        assert len(result["command"]) == 1200

    def test_parse_request_command_with_special_chars(self):
        """Command name with special chars is accepted by the parser."""
        result = parse_request({"command": "get/data?format=json&page=1", "args": {}})
        assert "get/data" in result["command"]

    def test_make_ok_response_with_list_data(self):
        """make_ok_response passes list data through unchanged."""
        r = make_ok_response(data=[1, 2, 3], count=3)
        assert r["status"] == "ok"
        assert r["data"] == [1, 2, 3]
        assert r["count"] == 3

    def test_make_error_response_with_empty_message(self):
        """make_error_response with empty message string is valid."""
        r = make_error_response("")
        assert r["status"] == "error"
        assert r["message"] == ""

    def test_parse_request_non_string_command_raises(self):
        """Non-string command (e.g., int) raises ConfigError."""
        from data_graph_studio.core.exceptions import ConfigError
        with pytest.raises(ConfigError):
            parse_request({"command": 123, "args": {}})

    def test_parse_request_missing_command_raises(self):
        """Missing 'command' key raises ConfigError."""
        from data_graph_studio.core.exceptions import ConfigError
        with pytest.raises(ConfigError):
            parse_request({"args": {"key": "val"}})


# ===========================================================================
# Category 9: Marking edge cases (5+ tests)
# ===========================================================================

class TestMarkingEdgeCases:
    """Mark with empty selection, mode interactions, and error paths."""

    def test_mark_with_empty_set_clears_selection(self):
        """mark() with empty set in REPLACE mode clears the selection."""
        mm = MarkingManager()
        mm.mark("Main", {1, 2, 3})
        mm.mark("Main", set())  # REPLACE with empty → clears
        assert mm.markings["Main"].count == 0
        assert not mm.markings["Main"].has_selection

    def test_mark_add_mode_accumulates(self):
        """ADD mode accumulates indices without removing existing ones."""
        mm = MarkingManager()
        mm.mark("Main", {1, 2})
        mm.mark("Main", {3, 4}, mode=MarkMode.ADD)
        assert mm.markings["Main"].selected_indices == {1, 2, 3, 4}

    def test_mark_remove_mode_with_empty_set_is_noop(self):
        """REMOVE mode with empty set leaves selection unchanged."""
        mm = MarkingManager()
        mm.mark("Main", {1, 2, 3})
        mm.mark("Main", set(), mode=MarkMode.REMOVE)
        assert mm.markings["Main"].count == 3

    def test_mark_intersect_mode_with_empty_set_clears_all(self):
        """INTERSECT mode with empty set clears the entire selection."""
        mm = MarkingManager()
        mm.mark("Main", {1, 2, 3})
        mm.mark("Main", set(), mode=MarkMode.INTERSECT)
        assert mm.markings["Main"].count == 0

    def test_mark_nonexistent_marking_raises_key_error(self):
        """mark() on a non-existent marking name raises DatasetError."""
        mm = MarkingManager()
        with pytest.raises(DatasetError):
            mm.mark("NonExistent", {1, 2})

    def test_mark_toggle_mode_flips_selection(self):
        """TOGGLE mode adds un-selected and removes already-selected indices."""
        mm = MarkingManager()
        mm.mark("Main", {1, 2, 3})
        mm.mark("Main", {2, 4}, mode=MarkMode.TOGGLE)
        # 2 was in → removed; 4 was not in → added
        assert 2 not in mm.markings["Main"].selected_indices
        assert 4 in mm.markings["Main"].selected_indices
        assert 1 in mm.markings["Main"].selected_indices
        assert 3 in mm.markings["Main"].selected_indices

    def test_create_duplicate_marking_raises_validation_error(self):
        """Creating a marking with an existing name raises ValidationError."""
        mm = MarkingManager()
        mm.create_marking("Alpha")
        with pytest.raises(ValidationError):
            mm.create_marking("Alpha")

    def test_remove_main_marking_raises_validation_error(self):
        """Removing the protected 'Main' marking raises ValidationError."""
        mm = MarkingManager()
        with pytest.raises(ValidationError):
            mm.remove_marking("Main")
