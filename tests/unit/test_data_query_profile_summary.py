"""
Tests for DataQuery.get_full_profile_summary.

Covers the bug where numeric_columns and text_columns were missing
from the non-windowed (profile-based) return dict.
"""

from data_graph_studio.core.data_query import DataQuery
from data_graph_studio.core.types import ColumnInfo, DataProfile


def _make_profile(columns):
    return DataProfile(
        total_rows=100,
        total_columns=len(columns),
        memory_bytes=1024,
        columns=columns,
        load_time_seconds=0.5,
    )


class TestGetFullProfileSummaryNonWindowed:
    def setup_method(self):
        self.query = DataQuery()

    def test_returns_none_when_profile_is_none(self):
        result = self.query.get_full_profile_summary(df=None, profile=None)
        assert result is None

    def test_includes_numeric_columns_count(self):
        cols = [
            ColumnInfo("a", "Float64", is_numeric=True),
            ColumnInfo("b", "Float64", is_numeric=True),
            ColumnInfo("c", "Utf8", is_numeric=False),
        ]
        profile = _make_profile(cols)
        result = self.query.get_full_profile_summary(df=None, profile=profile)
        assert result["numeric_columns"] == 2

    def test_includes_text_columns_count(self):
        cols = [
            ColumnInfo("a", "Float64", is_numeric=True),
            ColumnInfo("b", "Utf8", is_numeric=False, is_temporal=False),
            ColumnInfo("c", "Utf8", is_numeric=False, is_temporal=False),
        ]
        profile = _make_profile(cols)
        result = self.query.get_full_profile_summary(df=None, profile=profile)
        assert result["text_columns"] == 2

    def test_temporal_columns_count_as_text(self):
        cols = [
            ColumnInfo("ts", "Date", is_numeric=False, is_temporal=True),
            ColumnInfo("val", "Float64", is_numeric=True),
        ]
        profile = _make_profile(cols)
        result = self.query.get_full_profile_summary(df=None, profile=profile)
        # temporal is counted as text in profile_ui_controller (text_cols + temporal_cols)
        assert result["text_columns"] == 1

    def test_preserves_existing_fields(self):
        cols = [ColumnInfo("x", "Float64", is_numeric=True)]
        profile = _make_profile(cols)
        result = self.query.get_full_profile_summary(df=None, profile=profile)
        assert result["total_rows"] == 100
        assert result["total_columns"] == 1
        assert result["memory_bytes"] == 1024
        assert result["load_time_seconds"] == 0.5
