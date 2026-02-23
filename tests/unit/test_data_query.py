"""Unit tests for DataQuery — isolated from DataEngine.

Tests every public method directly with constructed DataFrames.
Covers normal, boundary, error, and property-based cases per method.
"""


import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from data_graph_studio.core.data_query import DataQuery
from data_graph_studio.core.exceptions import QueryError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dq() -> DataQuery:
    return DataQuery()


@pytest.fixture
def int_df() -> pl.DataFrame:
    return pl.DataFrame({"a": [1, 2, 3, 4, 5], "b": [10, 20, 30, 40, 50]})


@pytest.fixture
def mixed_df() -> pl.DataFrame:
    return pl.DataFrame({
        "name": ["alice", "bob", "charlie"],
        "age": [25, 30, 35],
        "score": [1.0, 2.5, 3.7],
    })


# ---------------------------------------------------------------------------
# TestFilter
# ---------------------------------------------------------------------------


class TestFilter:
    def test_eq_filter_returns_matching_rows(self, dq, int_df):
        result = dq.filter(int_df, "a", "eq", 3)
        assert result is not None
        assert len(result) == 1
        assert result["a"][0] == 3

    def test_gt_filter_excludes_equal_value(self, dq, int_df):
        result = dq.filter(int_df, "a", "gt", 3)
        assert result is not None
        assert len(result) == 2
        assert all(v > 3 for v in result["a"].to_list())

    def test_unknown_operator_raises_query_error(self, dq, int_df):
        with pytest.raises(QueryError):
            dq.filter(int_df, "a", "xyz", 1)

    def test_none_df_returns_none(self, dq):
        result = dq.filter(None, "a", "eq", 1)
        assert result is None

    def test_isnull_filter_on_null_column(self, dq):
        df = pl.DataFrame({"x": [1, None, 3, None, 5]})
        result = dq.filter(df, "x", "isnull", None)
        assert result is not None
        assert len(result) == 2
        assert all(v is None for v in result["x"].to_list())

    def test_ne_filter_excludes_matching_row(self, dq, int_df):
        result = dq.filter(int_df, "a", "ne", 3)
        assert len(result) == 4
        assert 3 not in result["a"].to_list()

    def test_contains_filter_on_string_column(self, dq, mixed_df):
        result = dq.filter(mixed_df, "name", "contains", "li")
        # "alice" and "charlie" both contain "li"
        assert len(result) == 2

    def test_startswith_filter(self, dq, mixed_df):
        result = dq.filter(mixed_df, "name", "startswith", "a")
        assert len(result) == 1
        assert result["name"][0] == "alice"

    def test_endswith_filter(self, dq, mixed_df):
        result = dq.filter(mixed_df, "name", "endswith", "e")
        # "alice" and "charlie" end with "e"
        assert len(result) == 2

    def test_notnull_filter_returns_non_null_rows(self, dq):
        df = pl.DataFrame({"a": [1, None, 3, None, 5]})
        result = dq.filter(df, "a", "notnull", None)
        assert len(result) == 3
        assert result["a"].null_count() == 0

    def test_gt_filter_returns_values_above_threshold(self, dq):
        df = pl.DataFrame({"a": [1.0, 2.0, 3.0, 5.0]})
        result = dq.filter(df, "a", "gt", 2.0)
        assert len(result) == 2
        assert all(v > 2.0 for v in result["a"].to_list())


# ---------------------------------------------------------------------------
# TestSort
# ---------------------------------------------------------------------------


class TestSort:
    def test_sort_ascending(self, dq, int_df):
        result = dq.sort(int_df, ["a"])
        assert result is not None
        assert result["a"][0] == 1

    def test_sort_descending(self, dq, int_df):
        result = dq.sort(int_df, ["a"], descending=True)
        assert result is not None
        assert result["a"][0] == 5

    def test_sort_multiple_columns(self, dq):
        # age intentionally out of order to test sorting
        df = pl.DataFrame({"name": ["charlie", "alice", "bob"], "age": [35, 25, 30]})
        result = dq.sort(df, ["age", "name"])
        assert result is not None
        assert result["age"].to_list() == [25, 30, 35]

    def test_none_df_returns_none(self, dq):
        result = dq.sort(None, ["a"])
        assert result is None

    def test_sort_preserves_all_rows(self, dq, int_df):
        result = dq.sort(int_df, ["b"])
        assert result is not None
        assert len(result) == len(int_df)


# ---------------------------------------------------------------------------
# TestGroupAggregate
# ---------------------------------------------------------------------------


class TestGroupAggregate:
    def test_group_sum(self, dq, mixed_df):
        result = dq.group_aggregate(mixed_df, ["name"], ["age"], ["sum"])
        assert result is not None
        assert "age_sum" in result.columns

    def test_group_mean(self, dq, mixed_df):
        result = dq.group_aggregate(mixed_df, ["name"], ["score"], ["mean"])
        assert result is not None
        assert "score_mean" in result.columns

    def test_none_df_returns_none(self, dq):
        result = dq.group_aggregate(None, ["name"], ["age"], ["sum"])
        assert result is None

    def test_result_columns_named_col_func(self, dq, mixed_df):
        result = dq.group_aggregate(mixed_df, ["name"], ["age"], ["max"])
        assert result is not None
        assert "age_max" in result.columns

    def test_unsupported_agg_skipped_gracefully(self, dq, mixed_df):
        # "badop" not in AGG_MAP — should produce a result with only group cols
        result = dq.group_aggregate(mixed_df, ["name"], ["age"], ["badop"])
        assert result is not None
        # Only group columns remain (no age_badop column)
        assert "age_badop" not in result.columns
        assert "name" in result.columns


# ---------------------------------------------------------------------------
# TestGetStatistics
# ---------------------------------------------------------------------------


class TestGetStatistics:
    def test_returns_dict_with_count_mean_std(self, dq, int_df):
        result = dq.get_statistics(int_df, "a")
        assert isinstance(result, dict)
        assert "count" in result
        assert "mean" in result
        assert "std" in result
        assert result["count"] == 5
        assert result["mean"] == pytest.approx(3.0)

    def test_missing_column_returns_empty_dict(self, dq, int_df):
        result = dq.get_statistics(int_df, "nonexistent")
        assert result == {}

    def test_none_df_returns_empty_dict(self, dq):
        result = dq.get_statistics(None, "a")
        assert result == {}

    def test_cache_hit_returns_cached(self, dq, int_df):
        cache = {}
        dq.get_statistics(int_df, "a", cache=cache)
        # Poison the cache with a sentinel value to verify cache is returned
        cache["stats_a"] = {"count": 999}
        second = dq.get_statistics(int_df, "a", cache=cache)
        assert second["count"] == 999


# ---------------------------------------------------------------------------
# TestGetAllStatistics
# ---------------------------------------------------------------------------


class TestGetAllStatistics:
    def test_returns_stats_for_numeric_cols_only(self, dq, mixed_df):
        result = dq.get_all_statistics(mixed_df)
        assert isinstance(result, dict)
        # "name" is Utf8 — should be excluded since only numeric by default
        assert "name" not in result
        assert "age" in result
        assert "score" in result

    def test_none_df_returns_empty_dict(self, dq):
        result = dq.get_all_statistics(None)
        assert result == {}

    def test_explicit_columns_honored(self, dq, mixed_df):
        result = dq.get_all_statistics(mixed_df, value_columns=["age"])
        assert list(result.keys()) == ["age"]


# ---------------------------------------------------------------------------
# TestIsColumnCategorical
# ---------------------------------------------------------------------------


class TestIsColumnCategorical:
    def test_low_cardinality_int_is_categorical(self, dq):
        # Need > 20 rows with <= 3 unique values AND unique/len < 0.05
        # 3 / 100 = 0.03 < 0.05, and 3 <= min(20, 100) = 20
        data = ([1] * 34) + ([2] * 33) + ([3] * 33)
        df = pl.DataFrame({"x": data})
        assert dq.is_column_categorical(df, "x") is True

    def test_high_cardinality_int_is_not_categorical(self, dq):
        df = pl.DataFrame({"x": list(range(1000))})
        assert dq.is_column_categorical(df, "x") is False

    def test_none_df_returns_false(self, dq):
        assert dq.is_column_categorical(None, "a") is False

    def test_missing_column_returns_false(self, dq, int_df):
        assert dq.is_column_categorical(int_df, "nonexistent") is False


# ---------------------------------------------------------------------------
# TestGetUniqueValues
# ---------------------------------------------------------------------------


class TestGetUniqueValues:
    def test_returns_unique_list(self, dq):
        df = pl.DataFrame({"x": [3, 1, 2, 1, 3]})
        result = dq.get_unique_values(df, "x")
        assert sorted(result) == result  # sorted ascending
        assert len(set(result)) == len(result)  # no duplicates

    def test_none_df_returns_empty_list(self, dq):
        result = dq.get_unique_values(None, "a")
        assert result == []

    def test_missing_column_returns_empty_list(self, dq, int_df):
        result = dq.get_unique_values(int_df, "nonexistent")
        assert result == []


# ---------------------------------------------------------------------------
# TestSample
# ---------------------------------------------------------------------------


class TestSample:
    def test_returns_n_rows_when_df_larger(self, dq, int_df):
        result = dq.sample(int_df, n=3, seed=42)
        assert len(result) == 3

    def test_returns_full_df_when_n_gte_len(self, dq, int_df):
        result = dq.sample(int_df, n=10, seed=42)
        assert result is int_df  # same object (passthrough)

    def test_none_df_returns_none(self, dq):
        assert dq.sample(None, n=3) is None


# ---------------------------------------------------------------------------
# TestGetSlice
# ---------------------------------------------------------------------------


class TestGetSlice:
    def test_returns_correct_rows(self, dq, int_df):
        result = dq.get_slice(int_df, 1, 3)
        assert len(result) == 2
        assert result["a"].to_list() == [2, 3]

    def test_none_df_returns_none(self, dq):
        assert dq.get_slice(None, 0, 5) is None


# ---------------------------------------------------------------------------
# TestSearch
# ---------------------------------------------------------------------------


class TestSearch:
    def test_finds_string_match_in_text_column(self, dq, mixed_df):
        result = dq.search(mixed_df, "alice")
        assert result is not None
        assert len(result) == 1

    def test_case_insensitive_search(self, dq, mixed_df):
        result = dq.search(mixed_df, "ALICE", case_sensitive=False)
        assert result is not None
        assert len(result) == 1

    def test_no_match_returns_empty_df(self, dq, mixed_df):
        result = dq.search(mixed_df, "zzznomatch")
        assert result is not None
        assert len(result) == 0

    def test_none_df_returns_none(self, dq):
        result = dq.search(None, "q")
        assert result is None


# ---------------------------------------------------------------------------
# TestFilterByMap
# ---------------------------------------------------------------------------


class TestFilterByMap:
    def test_single_filter_in_map(self, dq, int_df):
        # filter_by_map casts values to str for comparison
        result = dq.filter_by_map(int_df, {"a": [1, 2]})
        assert result is not None
        assert len(result) == 2

    def test_missing_key_silently_skipped(self, dq, int_df):
        result = dq.filter_by_map(int_df, {"nonexistent": [1]})
        assert result is not None
        # applied_any=False, so original df is returned
        assert len(result) == len(int_df)

    def test_none_df_returns_none(self, dq):
        result = dq.filter_by_map(None, {})
        assert result is None


# ---------------------------------------------------------------------------
# TestCreateIndex
# ---------------------------------------------------------------------------


class TestCreateIndex:
    def test_creates_mapping_col_value_to_row_indices(self, dq, int_df):
        with pytest.warns(DeprecationWarning):
            index = dq.create_index(int_df, "a")
        assert isinstance(index, dict)
        # Each value 1-5 should be a key
        assert set(index.keys()) == {1, 2, 3, 4, 5}
        # Each key maps to a list of row indices
        for val, indices in index.items():
            assert isinstance(indices, list)

    def test_none_df_returns_empty_dict(self, dq):
        with pytest.warns(DeprecationWarning):
            result = dq.create_index(None, "a")
        assert result == {}


# ---------------------------------------------------------------------------
# TestProperties (hypothesis-based)
# ---------------------------------------------------------------------------


def _small_int_df_strategy():
    """Strategy: small DataFrame with a single int column 'x' and values 0-10."""
    return st.lists(
        st.integers(min_value=0, max_value=10),
        min_size=1,
        max_size=20,
    ).map(lambda vals: pl.DataFrame({"x": vals}))


class TestProperties:
    @settings(max_examples=40)
    @given(df_vals=_small_int_df_strategy(), target=st.integers(min_value=0, max_value=10))
    def test_filter_result_rows_lte_input_rows(self, df_vals, target):
        dq = DataQuery()
        result = dq.filter(df_vals, "x", "eq", target)
        assert result is not None
        assert len(result) <= len(df_vals)

    @settings(max_examples=40)
    @given(df_vals=_small_int_df_strategy())
    def test_sort_preserves_row_count(self, df_vals):
        dq = DataQuery()
        result = dq.sort(df_vals, ["x"])
        assert result is not None
        assert len(result) == len(df_vals)

    @settings(max_examples=40)
    @given(df_vals=_small_int_df_strategy())
    def test_group_aggregate_result_rows_lte_input(self, df_vals):
        dq = DataQuery()
        result = dq.group_aggregate(df_vals, ["x"], ["x"], ["sum"])
        assert result is not None
        assert len(result) <= len(df_vals)
