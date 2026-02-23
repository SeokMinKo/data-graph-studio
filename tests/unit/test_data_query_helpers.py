"""
Tests for data_query_helpers.py.

Covers:
- NUMERIC_DTYPES constant membership
- AGG_MAP keys and callable values
- build_filter_ops: all operators, string ops, isnull/notnull
- compute_eager_column_stats: numeric series, string series, empty series, all-null series
- compute_windowed_profile: normal profile, zero-row result, collect_fn returns None, failure
"""

from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest

from data_graph_studio.core.data_query_helpers import (
    AGG_MAP,
    NUMERIC_DTYPES,
    build_filter_ops,
    compute_eager_column_stats,
    compute_windowed_profile,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestNumericDtypes:
    def test_int64_in_numeric_dtypes(self):
        assert pl.Int64 in NUMERIC_DTYPES

    def test_float64_in_numeric_dtypes(self):
        assert pl.Float64 in NUMERIC_DTYPES

    def test_string_not_in_numeric_dtypes(self):
        assert pl.Utf8 not in NUMERIC_DTYPES

    def test_bool_not_in_numeric_dtypes(self):
        assert pl.Boolean not in NUMERIC_DTYPES


class TestAggMap:
    def test_has_expected_keys(self):
        expected = {'sum', 'mean', 'median', 'min', 'max', 'count', 'std', 'var', 'first', 'last'}
        assert set(AGG_MAP.keys()) == expected

    def test_all_values_are_callable(self):
        for key, fn in AGG_MAP.items():
            assert callable(fn), f"AGG_MAP['{key}'] is not callable"

    def test_agg_functions_produce_polars_expr(self):
        for key, fn in AGG_MAP.items():
            expr = fn("value")
            assert isinstance(expr, pl.Expr), f"AGG_MAP['{key}'] did not return pl.Expr"


# ---------------------------------------------------------------------------
# build_filter_ops
# ---------------------------------------------------------------------------

class TestBuildFilterOps:
    def setup_method(self):
        self.df = pl.DataFrame({"score": [1, 2, 3, 4, 5]})

    def test_eq_filters_correctly(self):
        ops = build_filter_ops("score", 3)
        result = self.df.filter(ops['eq'])
        assert result['score'].to_list() == [3]

    def test_ne_excludes_value(self):
        ops = build_filter_ops("score", 3)
        result = self.df.filter(ops['ne'])
        assert 3 not in result['score'].to_list()

    def test_gt_greater_than(self):
        ops = build_filter_ops("score", 3)
        result = self.df.filter(ops['gt'])
        assert all(v > 3 for v in result['score'].to_list())

    def test_lt_less_than(self):
        ops = build_filter_ops("score", 3)
        result = self.df.filter(ops['lt'])
        assert all(v < 3 for v in result['score'].to_list())

    def test_ge_includes_boundary(self):
        ops = build_filter_ops("score", 3)
        result = self.df.filter(ops['ge'])
        assert 3 in result['score'].to_list()
        assert all(v >= 3 for v in result['score'].to_list())

    def test_le_includes_boundary(self):
        ops = build_filter_ops("score", 3)
        result = self.df.filter(ops['le'])
        assert 3 in result['score'].to_list()
        assert all(v <= 3 for v in result['score'].to_list())

    def test_isnull_finds_nulls(self):
        df = pl.DataFrame({"x": [1, None, 3]})
        ops = build_filter_ops("x", None)
        result = df.filter(ops['isnull'])
        assert result.height == 1
        assert result['x'][0] is None

    def test_notnull_excludes_nulls(self):
        df = pl.DataFrame({"x": [1, None, 3]})
        ops = build_filter_ops("x", None)
        result = df.filter(ops['notnull'])
        assert result.height == 2
        assert None not in result['x'].to_list()

    def test_contains_string_op(self):
        df = pl.DataFrame({"name": ["alice", "bob", "charlie"]})
        ops = build_filter_ops("name", "li")
        result = df.filter(ops['contains'])
        # "alice" and "charlie" contain "li"
        assert set(result['name'].to_list()) == {"alice", "charlie"}

    def test_startswith_string_op(self):
        df = pl.DataFrame({"name": ["alice", "bob", "alfred"]})
        ops = build_filter_ops("name", "al")
        result = df.filter(ops['startswith'])
        assert set(result['name'].to_list()) == {"alice", "alfred"}

    def test_endswith_string_op(self):
        df = pl.DataFrame({"name": ["alice", "bob", "eric"]})
        ops = build_filter_ops("name", "ic")
        result = df.filter(ops['endswith'])
        # only "eric" ends with "ic" ("alice" ends with "ce")
        assert set(result['name'].to_list()) == {"eric"}

    def test_returns_all_expected_keys(self):
        ops = build_filter_ops("score", 0)
        expected_keys = {'eq', 'ne', 'gt', 'lt', 'ge', 'le',
                         'contains', 'startswith', 'endswith', 'isnull', 'notnull'}
        assert set(ops.keys()) == expected_keys


# ---------------------------------------------------------------------------
# compute_eager_column_stats
# ---------------------------------------------------------------------------

class TestComputeEagerColumnStats:
    def test_numeric_series_has_stats(self):
        s = pl.Series("val", [1.0, 2.0, 3.0, 4.0, 5.0])
        stats = compute_eager_column_stats(s)
        assert stats['count'] == 5
        assert stats['null_count'] == 0
        assert stats['mean'] == pytest.approx(3.0)
        assert stats['min'] == 1.0
        assert stats['max'] == 5.0
        assert 'q1' in stats
        assert 'q3' in stats

    def test_string_series_lacks_numeric_stats(self):
        s = pl.Series("name", ["a", "b", "c"])
        stats = compute_eager_column_stats(s)
        assert stats['count'] == 3
        assert stats['unique_count'] == 3
        assert 'mean' not in stats
        assert 'sum' not in stats

    def test_null_count_reported(self):
        s = pl.Series("x", [1, None, None, 4], dtype=pl.Int64)
        stats = compute_eager_column_stats(s)
        assert stats['null_count'] == 2

    def test_empty_series_count_is_zero(self):
        s = pl.Series("x", [], dtype=pl.Float64)
        stats = compute_eager_column_stats(s)
        assert stats['count'] == 0
        assert stats['null_count'] == 0

    def test_all_null_series(self):
        s = pl.Series("x", [None, None, None], dtype=pl.Float64)
        stats = compute_eager_column_stats(s)
        assert stats['count'] == 3
        assert stats['null_count'] == 3

    def test_unique_count_correct(self):
        s = pl.Series("x", [1, 1, 2, 3, 3], dtype=pl.Int64)
        stats = compute_eager_column_stats(s)
        assert stats['unique_count'] == 3

    def test_integer_series_has_numeric_stats(self):
        s = pl.Series("n", [10, 20, 30], dtype=pl.Int32)
        stats = compute_eager_column_stats(s)
        assert stats['sum'] == 60
        assert 'std' in stats


# ---------------------------------------------------------------------------
# compute_windowed_profile
# ---------------------------------------------------------------------------

class TestComputeWindowedProfile:
    def _make_lazy(self, data: dict) -> pl.LazyFrame:
        return pl.DataFrame(data).lazy()

    def _passthrough_collect(self, lf: pl.LazyFrame) -> pl.DataFrame:
        return lf.collect()

    def test_normal_profile_has_expected_keys(self):
        lf = self._make_lazy({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        result = compute_windowed_profile(lf, self._passthrough_collect)
        assert result is not None
        assert result['total_rows'] == 3
        assert result['total_columns'] == 2
        assert result['numeric_columns'] == 2
        assert result['text_columns'] == 0
        assert 'missing_percent' in result

    def test_text_column_counted_as_text(self):
        lf = self._make_lazy({"name": ["x", "y"], "val": [1.0, 2.0]})
        result = compute_windowed_profile(lf, self._passthrough_collect)
        assert result is not None
        assert result['numeric_columns'] == 1
        assert result['text_columns'] == 1

    def test_missing_percent_nonzero_when_nulls_present(self):
        lf = pl.DataFrame({"a": [1, None, 3]}).lazy()
        result = compute_windowed_profile(lf, self._passthrough_collect)
        assert result is not None
        assert result['missing_percent'] > 0.0

    def test_no_missing_when_fully_populated(self):
        lf = self._make_lazy({"a": [1, 2, 3]})
        result = compute_windowed_profile(lf, self._passthrough_collect)
        assert result is not None
        assert result['missing_percent'] == 0.0

    def test_collect_fn_returning_none_returns_none(self):
        lf = self._make_lazy({"a": [1, 2, 3]})
        result = compute_windowed_profile(lf, lambda _: None)
        assert result is None

    def test_collect_fn_raising_returns_none(self):
        def bad_collect(lf):
            raise RuntimeError("boom")

        lf = self._make_lazy({"a": [1, 2, 3]})
        result = compute_windowed_profile(lf, bad_collect)
        assert result is None

    def test_empty_dataframe_returns_zero_rows(self):
        lf = pl.DataFrame({"a": [], "b": []}, schema={"a": pl.Float64, "b": pl.Float64}).lazy()
        result = compute_windowed_profile(lf, self._passthrough_collect)
        assert result is not None
        assert result['total_rows'] == 0
        assert result['missing_percent'] == 0.0
