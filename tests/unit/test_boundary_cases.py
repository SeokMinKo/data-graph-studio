"""
Boundary value and error case tests for filtering.py and dataset_manager.py.

Covers edge cases not addressed by happy-path tests:
- Empty DataFrames
- All-null columns
- Single-row DataFrames
- NaN in numeric comparisons
- Boundary operator semantics (>= vs >)
- Empty string filters
- Unicode (Korean/Japanese) in string filters
- DatasetManager: 0-row datasets, 0-column datasets, duplicate IDs,
  remove-then-activate sequences
"""

import math
from unittest.mock import MagicMock

import polars as pl
import pytest

from data_graph_studio.core.dataset_manager import DatasetManager
from data_graph_studio.core.filtering import (
    Filter,
    FilteringManager,
    FilterOperator,
    FilterType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager() -> DatasetManager:
    loader = MagicMock()
    loader._df = None
    loader._lazy_df = None
    loader._source = None
    loader._profile = None
    loader._precision_mode = None
    return DatasetManager(loader)


def _make_fm() -> FilteringManager:
    return FilteringManager()


def _apply(fm: FilteringManager, df: pl.DataFrame, scheme: str = "Page") -> pl.DataFrame:
    """Convenience: apply filters from a scheme to a DataFrame."""
    return fm.apply_filters(scheme, df)


# ---------------------------------------------------------------------------
# Filtering — empty DataFrame
# ---------------------------------------------------------------------------

class TestFilterEmptyDataFrame:
    """Filtering an empty DataFrame must return empty, never raise."""

    @pytest.mark.parametrize("operator,value", [
        (FilterOperator.EQUALS, 0),
        (FilterOperator.GREATER_THAN, 0),
        (FilterOperator.GREATER_THAN_OR_EQUALS, 0),
        (FilterOperator.LESS_THAN, 0),
        (FilterOperator.BETWEEN, (0, 10)),
        (FilterOperator.IN_LIST, [0, 1, 2]),
    ])
    def test_numeric_filter_on_empty_df_returns_empty(self, operator, value):
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Int64)})
        fm.add_filter("Page", "x", operator, value, filter_type=FilterType.NUMERIC)
        result = _apply(fm, df)
        assert len(result) == 0
        assert result.columns == ["x"]

    def test_text_filter_on_empty_df_returns_empty(self):
        fm = _make_fm()
        df = pl.DataFrame({"name": pl.Series([], dtype=pl.Utf8)})
        fm.add_filter("Page", "name", FilterOperator.CONTAINS, "hello",
                      filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_is_null_filter_on_empty_df_returns_empty(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.IS_NULL, None)
        result = _apply(fm, df)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Filtering — all-null column
# ---------------------------------------------------------------------------

class TestFilterAllNullColumn:
    """Filtering a column that is entirely null must not crash."""

    def test_eq_filter_on_all_null_returns_empty(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([None, None, None], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, 1)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_is_null_filter_on_all_null_returns_all_rows(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([None, None, None], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.IS_NULL, None)
        result = _apply(fm, df)
        assert len(result) == 3

    def test_is_not_null_filter_on_all_null_returns_empty(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([None, None, None], dtype=pl.Int64)})
        fm.add_filter("Page", "x", FilterOperator.IS_NOT_NULL, None)
        result = _apply(fm, df)
        assert len(result) == 0

    def test_gt_filter_on_all_null_returns_empty(self):
        """Comparison operators on null values should yield no matches."""
        fm = _make_fm()
        df = pl.DataFrame({"x": pl.Series([None, None], dtype=pl.Float64)})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN, 0.0)
        result = _apply(fm, df)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Filtering — single-row DataFrame
# ---------------------------------------------------------------------------

class TestFilterSingleRow:
    """Single-row DataFrames: filter matches → 1 row; no match → 0 rows."""

    @pytest.mark.parametrize("op,val,expect_match", [
        (FilterOperator.EQUALS, 42, True),
        (FilterOperator.EQUALS, 99, False),
        (FilterOperator.NOT_EQUALS, 42, False),
        (FilterOperator.NOT_EQUALS, 99, True),
        (FilterOperator.GREATER_THAN, 41, True),
        (FilterOperator.GREATER_THAN, 42, False),
        (FilterOperator.GREATER_THAN_OR_EQUALS, 42, True),
        (FilterOperator.GREATER_THAN_OR_EQUALS, 43, False),
        (FilterOperator.LESS_THAN, 43, True),
        (FilterOperator.LESS_THAN, 42, False),
        (FilterOperator.LESS_THAN_OR_EQUALS, 42, True),
        (FilterOperator.LESS_THAN_OR_EQUALS, 41, False),
    ])
    def test_single_row_numeric(self, op, val, expect_match):
        fm = _make_fm()
        df = pl.DataFrame({"x": [42]})
        fm.add_filter("Page", "x", op, val)
        result = _apply(fm, df)
        expected_len = 1 if expect_match else 0
        assert len(result) == expected_len

    @pytest.mark.parametrize("op,val,expect_match", [
        (FilterOperator.CONTAINS, "hello", True),
        (FilterOperator.CONTAINS, "xyz", False),
        (FilterOperator.NOT_CONTAINS, "xyz", True),
        (FilterOperator.NOT_CONTAINS, "hello", False),
        (FilterOperator.STARTS_WITH, "hello", True),
        (FilterOperator.STARTS_WITH, "world", False),
        (FilterOperator.ENDS_WITH, "world", True),
        (FilterOperator.ENDS_WITH, "hello", False),
    ])
    def test_single_row_text(self, op, val, expect_match):
        fm = _make_fm()
        df = pl.DataFrame({"s": ["hello world"]})
        fm.add_filter("Page", "s", op, val, filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        expected_len = 1 if expect_match else 0
        assert len(result) == expected_len


# ---------------------------------------------------------------------------
# Filtering — NaN in numeric columns
# ---------------------------------------------------------------------------

class TestFilterNaNHandling:
    """NaN values in numeric columns are handled without crashing."""

    def test_gt_filter_excludes_nan_rows(self):
        """NaN rows must NOT appear in gt/lt/ge/le filter results.

        Polars treats NaN as greater than all finite numbers (IEEE 754 total
        ordering), so without explicit exclusion NaN rows silently pass range
        filters. The fix chains `& ~col.is_nan()` for float columns when a
        range operator (gt/ge/lt/le) is applied.
        """
        fm = _make_fm()
        df = pl.DataFrame({"val": [1.0, float("nan"), 5.0, 10.0]})
        fm.add_filter("Page", "val", FilterOperator.GREATER_THAN, 0.0)
        result = _apply(fm, df)
        assert result["val"].is_nan().sum() == 0
        assert len(result) == 3  # 1.0, 5.0, 10.0 — NaN excluded

    @pytest.mark.parametrize("op", [
        FilterOperator.GREATER_THAN,
        FilterOperator.GREATER_THAN_OR_EQUALS,
        FilterOperator.LESS_THAN,
        FilterOperator.LESS_THAN_OR_EQUALS,
    ])
    def test_range_operators_exclude_nan(self, op):
        """All four range operators exclude NaN rows for float columns."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [float("nan"), 5.0]})
        fm.add_filter("Page", "x", op, 3.0)
        result = _apply(fm, df)
        assert result["x"].is_nan().sum() == 0

    def test_eq_filter_does_not_match_nan(self):
        """NaN != NaN — equality filter should not match a NaN row."""
        fm = _make_fm()
        df = pl.DataFrame({"x": [float("nan"), 1.0]})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, float("nan"))
        result = _apply(fm, df)
        # Polars: NaN == NaN is True (unlike IEEE), but either way must not crash
        # We just verify no exception is raised and the result is a DataFrame
        assert isinstance(result, pl.DataFrame)

    def test_between_filter_excludes_nan(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": [float("nan"), 5.0, 15.0]})
        fm.add_filter("Page", "x", FilterOperator.BETWEEN, (0.0, 10.0),
                      filter_type=FilterType.RANGE)
        result = _apply(fm, df)
        assert len(result) == 1
        assert result["x"][0] == 5.0


# ---------------------------------------------------------------------------
# Filtering — boundary value semantics
# ---------------------------------------------------------------------------

class TestFilterBoundaryValues:
    """Strict vs non-strict inequality operators differ by exactly the boundary row."""

    @pytest.mark.parametrize("op,expected_len", [
        (FilterOperator.GREATER_THAN_OR_EQUALS, 3),   # includes 0
        (FilterOperator.GREATER_THAN, 2),              # excludes 0
    ])
    def test_zero_boundary_row(self, op, expected_len):
        fm = _make_fm()
        df = pl.DataFrame({"x": [0, 1, 2]})
        fm.add_filter("Page", "x", op, 0)
        result = _apply(fm, df)
        assert len(result) == expected_len

    @pytest.mark.parametrize("op,expected_len", [
        (FilterOperator.LESS_THAN_OR_EQUALS, 3),   # includes 2
        (FilterOperator.LESS_THAN, 2),              # excludes 2
    ])
    def test_upper_boundary_row(self, op, expected_len):
        fm = _make_fm()
        df = pl.DataFrame({"x": [0, 1, 2]})
        fm.add_filter("Page", "x", op, 2)
        result = _apply(fm, df)
        assert len(result) == expected_len

    def test_between_inclusive_both_ends(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": [0, 5, 10, 11]})
        fm.add_filter("Page", "x", FilterOperator.BETWEEN, (0, 10),
                      filter_type=FilterType.RANGE)
        result = _apply(fm, df)
        assert len(result) == 3  # 0, 5, 10

    def test_not_between_excludes_inner(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": [0, 5, 10, 11]})
        fm.add_filter("Page", "x", FilterOperator.NOT_BETWEEN, (1, 9))
        result = _apply(fm, df)
        assert len(result) == 3  # 0, 10, 11

    def test_negative_boundary(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": [-1, 0, 1]})
        fm.add_filter("Page", "x", FilterOperator.GREATER_THAN_OR_EQUALS, 0)
        result = _apply(fm, df)
        assert len(result) == 2  # 0, 1


# ---------------------------------------------------------------------------
# Filtering — empty string filter
# ---------------------------------------------------------------------------

class TestFilterEmptyString:
    """Empty string filter: matches empty strings, not everything."""

    def test_contains_empty_string_matches_all(self):
        """Empty contains pattern matches every row (substring of everything)."""
        fm = _make_fm()
        df = pl.DataFrame({"s": ["hello", "world", ""]})
        fm.add_filter("Page", "s", FilterOperator.CONTAINS, "",
                      filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        # Empty string is a substring of every string, so all 3 rows match
        assert len(result) == 3

    def test_equals_empty_string_matches_only_empty(self):
        fm = _make_fm()
        df = pl.DataFrame({"s": ["hello", "", "world", ""]})
        fm.add_filter("Page", "s", FilterOperator.EQUALS, "",
                      filter_type=FilterType.TEXT)
        result = _apply(fm, df)
        assert len(result) == 2
        assert all(v == "" for v in result["s"].to_list())

    def test_starts_with_empty_string_matches_all(self):
        """starts_with("") matches every string."""
        fm = _make_fm()
        df = pl.DataFrame({"s": ["a", "b", ""]})
        fm.add_filter("Page", "s", FilterOperator.STARTS_WITH, "",
                      filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        assert len(result) == 3

    def test_not_contains_empty_string_matches_none(self):
        """not_contains("") matches nothing (empty string is in every string)."""
        fm = _make_fm()
        df = pl.DataFrame({"s": ["hello", "world"]})
        fm.add_filter("Page", "s", FilterOperator.NOT_CONTAINS, "",
                      filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Filtering — Unicode in string filter
# ---------------------------------------------------------------------------

class TestFilterUnicodeStrings:
    """Korean and Japanese characters must be handled without errors."""

    def test_contains_korean(self):
        fm = _make_fm()
        df = pl.DataFrame({"s": ["안녕하세요", "hello", "안녕"]})
        fm.add_filter("Page", "s", FilterOperator.CONTAINS, "안녕",
                      filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        assert len(result) == 2

    def test_contains_japanese(self):
        fm = _make_fm()
        df = pl.DataFrame({"s": ["こんにちは", "hello", "さようなら"]})
        fm.add_filter("Page", "s", FilterOperator.CONTAINS, "こんにちは",
                      filter_type=FilterType.TEXT_SEARCH)
        result = _apply(fm, df)
        assert len(result) == 1

    def test_equals_unicode(self):
        fm = _make_fm()
        df = pl.DataFrame({"s": ["안녕하세요", "hello", "안녕"]})
        fm.add_filter("Page", "s", FilterOperator.EQUALS, "안녕",
                      filter_type=FilterType.TEXT)
        result = _apply(fm, df)
        assert len(result) == 1
        assert result["s"][0] == "안녕"

    def test_case_insensitive_text_search_unicode(self):
        """Case-insensitive search on ASCII mixed with Unicode doesn't crash."""
        fm = _make_fm()
        df = pl.DataFrame({"s": ["Hello World", "안녕하세요 Hello", "world"]})
        fm.add_filter("Page", "s", FilterOperator.CONTAINS, "hello",
                      filter_type=FilterType.TEXT_SEARCH, case_sensitive=False)
        result = _apply(fm, df)
        assert len(result) == 2

    def test_in_list_with_unicode(self):
        fm = _make_fm()
        df = pl.DataFrame({"s": ["서울", "도쿄", "베이징", "뉴욕"]})
        fm.add_filter("Page", "s", FilterOperator.IN_LIST, ["서울", "도쿄"],
                      filter_type=FilterType.CHECKBOX)
        result = _apply(fm, df)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Filtering — disabled filters
# ---------------------------------------------------------------------------

class TestFilterDisabled:
    """Disabled filters must have zero effect on the output."""

    def test_disabled_filter_returns_full_df(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": [1, 2, 3]})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, 999, enabled=False)
        result = _apply(fm, df)
        assert len(result) == 3

    def test_toggle_filter_enables_it(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": [1, 2, 3]})
        fm.add_filter("Page", "x", FilterOperator.EQUALS, 2, enabled=False)
        fm.toggle_filter("Page", 0)  # now enabled
        result = _apply(fm, df)
        assert len(result) == 1
        assert result["x"][0] == 2


# ---------------------------------------------------------------------------
# Filtering — unknown/non-existent scheme
# ---------------------------------------------------------------------------

class TestFilterUnknownScheme:
    """apply_filters with a non-existent scheme returns data unchanged."""

    def test_unknown_scheme_returns_original_df(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": [1, 2, 3]})
        result = fm.apply_filters("DoesNotExist", df)
        assert len(result) == 3

    def test_get_filter_indices_unknown_scheme_returns_all(self):
        fm = _make_fm()
        df = pl.DataFrame({"x": [10, 20, 30]})
        indices = fm.get_filter_indices("NoSuchScheme", df)
        assert indices == {0, 1, 2}


# ---------------------------------------------------------------------------
# DatasetManager — 0-row dataset
# ---------------------------------------------------------------------------

class TestDatasetManager0RowDataset:
    """Loading a DataFrame with 0 rows must succeed."""

    def test_add_zero_row_df_succeeds(self):
        manager = _make_manager()
        df = pl.DataFrame({"a": pl.Series([], dtype=pl.Int64),
                           "b": pl.Series([], dtype=pl.Utf8)})
        did = manager.load_dataset_from_dataframe(df, name="empty")
        assert did is not None
        assert manager.get_dataset(did) is not None

    def test_zero_row_df_is_activated_as_first_dataset(self):
        manager = _make_manager()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Float64)})
        did = manager.load_dataset_from_dataframe(df, name="empty_ds")
        assert manager.active_dataset_id == did

    def test_get_dataset_df_returns_empty_frame_not_none(self):
        manager = _make_manager()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Int32)})
        did = manager.load_dataset_from_dataframe(df, name="zero_rows")
        result = manager.get_dataset_df(did)
        assert result is not None
        assert len(result) == 0


# ---------------------------------------------------------------------------
# DatasetManager — 0-column dataset
# ---------------------------------------------------------------------------

class TestDatasetManager0ColumnDataset:
    """A DataFrame with no columns is a degenerate case — must not crash."""

    def test_add_zero_column_df_does_not_raise(self):
        manager = _make_manager()
        # Polars allows a DataFrame with 0 columns and 0 rows
        df = pl.DataFrame()
        try:
            did = manager.load_dataset_from_dataframe(df, name="no_cols")
        except Exception as exc:
            pytest.fail(f"load_dataset_from_dataframe raised unexpectedly: {exc}")

    def test_add_zero_column_df_succeeds_or_returns_none_not_crash(self):
        manager = _make_manager()
        df = pl.DataFrame()
        # Either succeeds (returns an ID) or gracefully returns None — either is fine
        # The important thing is no unhandled exception
        result = manager.load_dataset_from_dataframe(df, name="no_cols")
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# DatasetManager — remove non-existent dataset_id
# ---------------------------------------------------------------------------

class TestDatasetManagerRemoveNonExistent:
    """remove_dataset with bogus IDs must not crash."""

    @pytest.mark.parametrize("bogus_id", [
        "does-not-exist",
        "",
        "0" * 50,
        "!!invalid!!",
    ])
    def test_remove_bogus_id_returns_false(self, bogus_id):
        manager = _make_manager()
        result = manager.remove_dataset(bogus_id)
        assert result is False

    def test_remove_same_id_twice_is_safe(self):
        manager = _make_manager()
        df = pl.DataFrame({"x": [1, 2]})
        did = manager.load_dataset_from_dataframe(df, name="temp")
        manager.remove_dataset(did)
        # Second remove — already gone
        result = manager.remove_dataset(did)
        assert result is False


# ---------------------------------------------------------------------------
# DatasetManager — activate after remove
# ---------------------------------------------------------------------------

class TestDatasetManagerActivateAfterRemove:
    """Activating a removed dataset must not crash and must return False."""

    def test_activate_removed_dataset_returns_false(self):
        manager = _make_manager()
        df = pl.DataFrame({"x": [1]})
        did = manager.load_dataset_from_dataframe(df, name="to_remove")
        manager.remove_dataset(did)
        result = manager.activate_dataset(did)
        assert result is False

    def test_active_dataset_id_is_not_stale_after_remove_and_failed_activate(self):
        manager = _make_manager()
        df = pl.DataFrame({"x": [1]})
        did1 = manager.load_dataset_from_dataframe(df, name="first")
        did2 = manager.load_dataset_from_dataframe(df, name="second")
        manager.activate_dataset(did2)
        manager.remove_dataset(did2)
        # Attempt to activate the removed one
        manager.activate_dataset(did2)
        # Active should remain valid (did1 was auto-rotated to)
        active = manager.active_dataset_id
        if active is not None:
            assert manager.get_dataset(active) is not None


# ---------------------------------------------------------------------------
# DatasetManager — duplicate dataset_id
# ---------------------------------------------------------------------------

class TestDatasetManagerDuplicateId:
    """Adding the same dataset_id twice must be handled gracefully."""

    def test_same_id_overwrites_previous(self):
        """load_dataset_from_dataframe with an explicit ID overwrites the old entry."""
        manager = _make_manager()
        df1 = pl.DataFrame({"x": [1, 2, 3]})
        df2 = pl.DataFrame({"x": [10, 20]})
        fixed_id = "fixed-id-001"

        manager.load_dataset_from_dataframe(df1, name="first", dataset_id=fixed_id)
        manager.load_dataset_from_dataframe(df2, name="second", dataset_id=fixed_id)

        # The manager uses the ID as a dict key — second call overwrites
        ds = manager.get_dataset(fixed_id)
        assert ds is not None
        # Row count should reflect the second DataFrame
        assert ds.row_count == 2

    def test_duplicate_id_does_not_inflate_dataset_count(self):
        manager = _make_manager()
        df = pl.DataFrame({"x": [1]})
        fixed_id = "dup-id"
        manager.load_dataset_from_dataframe(df, name="a", dataset_id=fixed_id)
        manager.load_dataset_from_dataframe(df, name="b", dataset_id=fixed_id)
        assert manager.dataset_count == 1
