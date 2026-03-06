"""Tests for DataQuery module."""

import pytest

from data_graph_studio.core.data_query import DataQuery


@pytest.fixture
def query():
    return DataQuery()


class TestDataQueryFilter:
    def test_data_query_filter_eq_returns_matches(self, query, sample_df):
        result = query.filter(sample_df, "city", "eq", "Seoul")
        assert result is not None
        assert all(v == "Seoul" for v in result["city"].to_list())

    def test_data_query_filter_gt_returns_matches(self, query, sample_df):
        result = query.filter(sample_df, "age", "gt", 30)
        assert all(v > 30 for v in result["age"].to_list())

    def test_data_query_filter_none_df_returns_none(self, query):
        assert query.filter(None, "x", "eq", 1) is None

    def test_data_query_filter_unknown_operator_raises(self, query, sample_df):
        with pytest.raises(ValueError, match="Unknown operator"):
            query.filter(sample_df, "age", "unknown", 1)

    def test_data_query_filter_empty_result(self, query, sample_df):
        result = query.filter(sample_df, "age", "gt", 999)
        assert len(result) == 0


class TestDataQuerySort:
    def test_data_query_sort_ascending(self, query, sample_df):
        result = query.sort(sample_df, ["age"])
        ages = result["age"].to_list()
        assert ages == sorted(ages)

    def test_data_query_sort_descending(self, query, sample_df):
        result = query.sort(sample_df, ["age"], descending=True)
        ages = result["age"].to_list()
        assert ages == sorted(ages, reverse=True)

    def test_data_query_sort_none_returns_none(self, query):
        assert query.sort(None, ["x"]) is None


class TestDataQueryStatistics:
    def test_data_query_get_statistics_numeric(self, query, sample_df):
        stats = query.get_statistics(sample_df, "age")
        assert "count" in stats
        assert "mean" in stats
        assert stats["count"] == 10

    def test_data_query_get_statistics_nonexistent_column(self, query, sample_df):
        stats = query.get_statistics(sample_df, "nonexistent")
        assert stats == {}

    def test_data_query_get_statistics_with_cache(self, query, sample_df):
        cache = {}
        stats1 = query.get_statistics(sample_df, "age", cache=cache)
        stats2 = query.get_statistics(sample_df, "age", cache=cache)
        assert stats1 == stats2
        assert "stats_age" in cache

    def test_data_query_get_all_statistics(self, query, sample_df):
        all_stats = query.get_all_statistics(sample_df)
        assert "age" in all_stats
        assert "score" in all_stats


class TestDataQueryMisc:
    def test_data_query_is_column_categorical(self, query, sample_df):
        assert query.is_column_categorical(sample_df, "city") is True
        assert query.is_column_categorical(None, "city") is False

    def test_data_query_get_unique_values(self, query, sample_df):
        values = query.get_unique_values(sample_df, "city")
        assert "Seoul" in values
        assert len(values) == 3

    def test_data_query_sample_small_df(self, query, sample_df):
        result = query.sample(sample_df, n=100)
        assert len(result) == 10  # df smaller than n

    def test_data_query_get_slice(self, query, sample_df):
        result = query.get_slice(sample_df, 2, 5)
        assert len(result) == 3

    def test_data_query_search(self, query, sample_df):
        result = query.search(sample_df, "Alice")
        assert len(result) >= 1

    def test_data_query_search_case_insensitive(self, query, sample_df):
        result = query.search(sample_df, "alice", case_sensitive=False)
        assert len(result) >= 1

    def test_data_query_group_aggregate(self, query, sample_df):
        result = query.group_aggregate(sample_df, ["city"], ["age"], ["mean"])
        assert result is not None
        assert "age_mean" in result.columns
