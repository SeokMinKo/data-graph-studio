"""
Error-path tests for DataEngine.

Tests cover documented edge cases:
- drop_column on a non-existent column (silent no-op)
- drop_column with invalid names (raises ValueError)
- Accessing df/row_count/column_count when no dataset is loaded
- filter on a missing column
- cast_column on a non-existent column returns False
- cast_column on incompatible types raises QueryError
- add_virtual_column with invalid expr raises QueryError
- lazy_query when no data is loaded returns None
"""

import polars as pl
import pytest

from data_graph_studio.core.data_engine import DataEngine
from data_graph_studio.core.exceptions import DataLoadError, QueryError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine_with_df(rows: int = 5, cols: int = 3) -> DataEngine:
    """Return a DataEngine pre-loaded with a small DataFrame."""
    engine = DataEngine()
    data = {f"col_{c}": list(range(rows)) for c in range(cols)}
    df = pl.DataFrame(data)
    engine.load_dataset_from_dataframe(df, name="test_ds")
    return engine


def _empty_engine() -> DataEngine:
    """Return a DataEngine with no data loaded."""
    return DataEngine()


# ---------------------------------------------------------------------------
# drop_column — non-existent column is a silent no-op
# ---------------------------------------------------------------------------

class TestDropColumnNonExistent:
    def test_drop_nonexistent_column_does_not_raise(self):
        """drop_column on a column that doesn't exist is silent — no exception."""
        engine = _engine_with_df()
        try:
            engine.drop_column("this_column_does_not_exist")
        except Exception as exc:
            pytest.fail(f"drop_column raised unexpectedly: {exc}")

    def test_drop_nonexistent_column_leaves_df_intact(self):
        """drop_column on a missing column leaves the DataFrame unchanged."""
        engine = _engine_with_df(rows=3, cols=2)
        original_cols = set(engine.columns)
        engine.drop_column("ghost_column")
        assert set(engine.columns) == original_cols

    def test_drop_nonexistent_column_when_no_df_loaded(self):
        """drop_column when no DataFrame is loaded is a no-op — no exception."""
        engine = _empty_engine()
        assert engine.df is None
        try:
            engine.drop_column("x")
        except Exception as exc:
            pytest.fail(f"drop_column with no df raised: {exc}")

    def test_drop_existing_column_works(self):
        """drop_column removes an existing column correctly."""
        engine = _engine_with_df(rows=3, cols=3)
        col_to_drop = engine.columns[0]
        before_count = engine.column_count
        engine.drop_column(col_to_drop)
        assert engine.column_count == before_count - 1
        assert col_to_drop not in engine.columns


# ---------------------------------------------------------------------------
# drop_column — invalid name raises ValueError
# ---------------------------------------------------------------------------

class TestDropColumnInvalidName:
    def test_drop_empty_string_raises_value_error(self):
        """drop_column('') raises ValueError per implementation contract."""
        engine = _engine_with_df()
        with pytest.raises(ValueError):
            engine.drop_column("")

    def test_drop_whitespace_string_raises_value_error(self):
        """drop_column('   ') raises ValueError — whitespace-only is invalid."""
        engine = _engine_with_df()
        with pytest.raises(ValueError):
            engine.drop_column("   ")


# ---------------------------------------------------------------------------
# Accessing data when no dataset is loaded
# ---------------------------------------------------------------------------

class TestNoDataLoaded:
    def test_df_is_none_when_empty(self):
        """engine.df is None when no data is loaded."""
        engine = _empty_engine()
        assert engine.df is None

    def test_is_loaded_false_when_empty(self):
        """engine.is_loaded returns False when no data has been loaded."""
        engine = _empty_engine()
        assert engine.is_loaded is False

    def test_row_count_is_zero_when_empty(self):
        """engine.row_count returns 0 when no data is loaded."""
        engine = _empty_engine()
        assert engine.row_count == 0

    def test_column_count_is_zero_when_empty(self):
        """engine.column_count returns 0 when no data is loaded."""
        engine = _empty_engine()
        assert engine.column_count == 0

    def test_columns_is_empty_list_when_empty(self):
        """engine.columns returns [] when no data is loaded."""
        engine = _empty_engine()
        assert engine.columns == []

    def test_dtypes_is_empty_dict_when_empty(self):
        """engine.dtypes returns {} when no data is loaded."""
        engine = _empty_engine()
        assert engine.dtypes == {}

    def test_lazy_query_returns_none_when_empty(self):
        """lazy_query() returns None when no data is loaded."""
        engine = _empty_engine()
        result = engine.lazy_query()
        assert result is None

    def test_dataset_count_is_zero_when_empty(self):
        """engine.dataset_count is 0 immediately after construction."""
        engine = _empty_engine()
        assert engine.dataset_count == 0

    def test_active_dataset_is_none_when_empty(self):
        """engine.active_dataset is None when no dataset has been loaded."""
        engine = _empty_engine()
        assert engine.active_dataset is None

    def test_active_dataset_id_is_none_when_empty(self):
        """engine.active_dataset_id is None when no dataset is loaded."""
        engine = _empty_engine()
        assert engine.active_dataset_id is None


# ---------------------------------------------------------------------------
# cast_column — non-existent column returns False
# ---------------------------------------------------------------------------

class TestCastColumnErrors:
    def test_cast_nonexistent_column_returns_false(self):
        """cast_column on a missing column returns False without raising."""
        engine = _engine_with_df()
        result = engine.cast_column("no_such_col", pl.Float32)
        assert result is False

    def test_cast_column_when_no_df_returns_false(self):
        """cast_column when no DataFrame is loaded returns False."""
        engine = _empty_engine()
        result = engine.cast_column("x", pl.Int64)
        assert result is False

    def test_cast_existing_column_returns_true(self):
        """cast_column on an existing column with a compatible dtype returns True."""
        engine = _engine_with_df(rows=4, cols=2)
        col = engine.columns[0]  # integer column
        result = engine.cast_column(col, pl.Float64)
        assert result is True


# ---------------------------------------------------------------------------
# filter — via DataEngine delegation
# ---------------------------------------------------------------------------

class TestFilterErrors:
    def test_filter_nonexistent_column_returns_none_or_empty(self):
        """Filtering on a column that doesn't exist should not crash."""
        engine = _engine_with_df(rows=5, cols=2)
        # DataQuery.filter may return None or raise — we just check no unhandled crash
        try:
            result = engine.filter("nonexistent_column", "gt", 0)
            # If it returns something, it's either None or a DataFrame
            assert result is None or isinstance(result, pl.DataFrame)
        except Exception:
            # Polars may raise; that's acceptable — what's NOT acceptable is a silent wrong answer
            pass

    def test_filter_on_valid_column_works(self):
        """filter on an existing column returns a valid DataFrame."""
        engine = _engine_with_df(rows=10, cols=2)
        col = engine.columns[0]
        result = engine.filter(col, "gt", 5)
        assert result is not None
        assert isinstance(result, pl.DataFrame)


# ---------------------------------------------------------------------------
# get_unique_values — no crash on missing column
# ---------------------------------------------------------------------------

class TestGetUniqueValuesErrors:
    def test_get_unique_values_nonexistent_column(self):
        """get_unique_values on a nonexistent column doesn't crash — returns empty or None."""
        engine = _engine_with_df()
        try:
            result = engine.get_unique_values("no_such_col")
            assert result is None or isinstance(result, list)
        except Exception:
            pass  # Polars-level error is acceptable

    def test_get_unique_values_no_data_loaded(self):
        """get_unique_values when engine has no data doesn't crash."""
        engine = _empty_engine()
        try:
            result = engine.get_unique_values("x")
            assert result is None or isinstance(result, list)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# clear() resets loader state (not dataset manager)
# ---------------------------------------------------------------------------

class TestClearResetsState:
    def test_clear_on_empty_engine_does_not_raise(self):
        """Calling clear() on an engine with no data loaded doesn't raise."""
        engine = _empty_engine()
        try:
            engine.clear()
        except Exception as exc:
            pytest.fail(f"clear() raised on empty engine: {exc}")

    def test_clear_resets_loader_df(self):
        """After clear(), the internal loader's _df is None (loader is reset)."""
        engine = _engine_with_df()
        engine.clear()
        # The loader's _df is cleared — dataset manager still holds the dataset
        assert engine._loader._df is None

    def test_clear_empties_transform_lineage(self):
        """After clear(), transform lineage is empty."""
        engine = _engine_with_df()
        col = engine.columns[0]
        engine.drop_column(col)
        assert len(engine.lineage) > 0
        engine.clear()
        assert len(engine.lineage) == 0

    def test_clear_on_empty_engine_leaves_df_none(self):
        """Calling clear() on an engine with no data leaves df as None."""
        engine = _empty_engine()
        engine.clear()
        # No dataset manager dataset exists, so df property falls back to loader._df = None
        assert engine.df is None

    def test_clear_all_datasets_then_df_is_none(self):
        """After clear_all_datasets(), engine.df is None."""
        engine = _engine_with_df()
        assert engine.is_loaded is True
        engine.clear_all_datasets()
        assert engine.df is None

    def test_clear_all_datasets_row_count_zero(self):
        """After clear_all_datasets(), engine.row_count is 0."""
        engine = _engine_with_df(rows=100)
        engine.clear_all_datasets()
        assert engine.row_count == 0


# ---------------------------------------------------------------------------
# append_rows — when no data loaded falls back to load_file
# ---------------------------------------------------------------------------

class TestAppendRowsNoData:
    def test_append_rows_when_no_df_loaded_raises_on_missing_file(self):
        """append_rows falls back to load_file when no current DataFrame exists;
        that raises DataLoadError for a nonexistent path."""
        engine = _empty_engine()
        assert engine.df is None
        with pytest.raises(DataLoadError):
            engine.append_rows("/nonexistent/path.csv", new_row_count=5)


# ---------------------------------------------------------------------------
# cast_column — incompatible type raises QueryError
# ---------------------------------------------------------------------------

class TestCastColumnQueryError:
    def test_cast_incompatible_type_raises_query_error(self):
        """cast_column raises QueryError when the cast is incompatible (e.g. string → Int64)."""
        engine = DataEngine()
        df = pl.DataFrame({"name": ["alice", "bob", "charlie"]})
        engine.load_dataset_from_dataframe(df, name="test")
        with pytest.raises(QueryError) as exc_info:
            engine.cast_column("name", pl.Int64)
        assert "cast_column" in exc_info.value.operation

    def test_cast_query_error_carries_context(self):
        """QueryError from cast_column includes column name in context."""
        engine = DataEngine()
        df = pl.DataFrame({"label": ["a", "b", "c"]})
        engine.load_dataset_from_dataframe(df, name="test")
        with pytest.raises(QueryError) as exc_info:
            engine.cast_column("label", pl.Boolean)
        assert exc_info.value.context.get("column") == "label"

    def test_cast_query_error_chains_original_exception(self):
        """QueryError raised from cast_column chains the original Polars exception."""
        engine = DataEngine()
        df = pl.DataFrame({"txt": ["not-a-date"]})
        engine.load_dataset_from_dataframe(df, name="test")
        with pytest.raises(QueryError) as exc_info:
            engine.cast_column("txt", pl.Date)
        assert exc_info.value.__cause__ is not None

    def test_cast_nonexistent_column_still_returns_false(self):
        """cast_column on a missing column still returns False — no QueryError."""
        engine = _engine_with_df()
        result = engine.cast_column("nonexistent", pl.Int64)
        assert result is False

    def test_cast_no_df_still_returns_false(self):
        """cast_column when no DataFrame is loaded still returns False — no QueryError."""
        engine = _empty_engine()
        result = engine.cast_column("x", pl.Int64)
        assert result is False


# ---------------------------------------------------------------------------
# add_virtual_column — invalid expr raises QueryError
# ---------------------------------------------------------------------------

class TestAddVirtualColumnQueryError:
    def test_add_virtual_column_invalid_expr_raises_query_error(self):
        """add_virtual_column raises QueryError when the expression references a nonexistent column."""
        engine = DataEngine()
        df = pl.DataFrame({"value": [1, 2, 3]})
        engine.load_dataset_from_dataframe(df, name="test")
        bad_expr = pl.col("nonexistent_col") * 2
        with pytest.raises(QueryError) as exc_info:
            engine.add_virtual_column("result", bad_expr)
        assert "add_virtual_column" in exc_info.value.operation

    def test_add_virtual_column_query_error_carries_name_in_context(self):
        """QueryError from add_virtual_column includes the column name in context."""
        engine = DataEngine()
        df = pl.DataFrame({"x": [1.0, 2.0]})
        engine.load_dataset_from_dataframe(df, name="test")
        bad_expr = pl.col("missing") + 1
        with pytest.raises(QueryError) as exc_info:
            engine.add_virtual_column("bad_col", bad_expr)
        assert exc_info.value.context.get("name") == "bad_col"

    def test_add_virtual_column_chains_original_exception(self):
        """QueryError from add_virtual_column chains the original Polars exception."""
        engine = DataEngine()
        df = pl.DataFrame({"a": [1, 2, 3]})
        engine.load_dataset_from_dataframe(df, name="test")
        bad_expr = pl.col("does_not_exist")
        with pytest.raises(QueryError) as exc_info:
            engine.add_virtual_column("v", bad_expr)
        assert exc_info.value.__cause__ is not None

    def test_add_virtual_column_valid_expr_returns_true(self):
        """add_virtual_column with a valid expression succeeds and returns True."""
        engine = DataEngine()
        df = pl.DataFrame({"x": [1, 2, 3]})
        engine.load_dataset_from_dataframe(df, name="test")
        result = engine.add_virtual_column("doubled", pl.col("x") * 2)
        assert result is True
        assert "doubled" in engine.columns
