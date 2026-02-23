"""
Unit tests for the DGS custom exception hierarchy.

Tests cover:
- All subclasses inherit from DGSError and Exception
- DGSError str formatting with and without operation
- context dict storage
- Exception chaining (__cause__)
- catch-by-base-class behaviour
- Sibling exceptions not caught by wrong handler
- All exceptions exported from data_graph_studio.core
"""

import pytest

from data_graph_studio.core.exceptions import (
    DGSError,
    DataLoadError,
    QueryError,
    ExportError,
    ValidationError,
    DatasetError,
    ConfigError,
)

_ALL_SUBCLASSES = [
    DataLoadError,
    QueryError,
    ExportError,
    ValidationError,
    DatasetError,
    ConfigError,
]


# ---------------------------------------------------------------------------
# 1. Hierarchy structure
# ---------------------------------------------------------------------------

class TestHierarchyStructure:
    def test_all_subclasses_inherit_from_dgserror(self):
        for cls in _ALL_SUBCLASSES:
            assert issubclass(cls, DGSError), f"{cls.__name__} must inherit from DGSError"

    def test_all_subclasses_inherit_from_exception(self):
        for cls in _ALL_SUBCLASSES:
            assert issubclass(cls, Exception), f"{cls.__name__} must inherit from Exception"

    def test_dgserror_inherits_from_exception(self):
        assert issubclass(DGSError, Exception)

    def test_subclasses_are_distinct(self):
        # No two subclasses should be the same class
        assert len(set(_ALL_SUBCLASSES)) == len(_ALL_SUBCLASSES)


# ---------------------------------------------------------------------------
# 2. DGSError attributes and __str__
# ---------------------------------------------------------------------------

class TestDGSErrorAttributes:
    def test_str_with_operation_includes_operation(self):
        err = DGSError("something failed", operation="load_file")
        assert "load_file" in str(err)

    def test_str_with_operation_includes_message(self):
        err = DGSError("something failed", operation="load_file")
        assert "something failed" in str(err)

    def test_str_without_operation_is_plain_message(self):
        err = DGSError("plain error")
        assert str(err) == "plain error"

    def test_operation_defaults_to_empty_string(self):
        err = DGSError("plain error")
        assert err.operation == ""

    def test_context_defaults_to_empty_dict(self):
        err = DGSError("no context")
        assert err.context == {}

    def test_context_stored_correctly(self):
        err = DGSError("failed", operation="op", context={"file": "test.csv"})
        assert err.context["file"] == "test.csv"

    def test_context_with_multiple_keys(self):
        ctx = {"file": "data.csv", "row": 42, "col": "price"}
        err = DGSError("failed", context=ctx)
        assert err.context == ctx

    def test_context_none_becomes_empty_dict(self):
        err = DGSError("msg", context=None)
        assert err.context == {}

    def test_str_format_brackets_operation(self):
        err = DGSError("oops", operation="my_op")
        assert str(err) == "[my_op] oops"

    def test_subclass_inherits_str_formatting(self):
        err = DataLoadError("bad file", operation="read_csv")
        assert "[read_csv]" in str(err)
        assert "bad file" in str(err)


# ---------------------------------------------------------------------------
# 3. Exception chaining
# ---------------------------------------------------------------------------

class TestExceptionChaining:
    def test_cause_is_preserved(self):
        original = ValueError("original")
        try:
            try:
                raise original
            except ValueError as e:
                raise DataLoadError("wrapped", operation="test") from e
        except DataLoadError as wrapped:
            assert wrapped.__cause__ is original

    def test_cause_is_none_when_not_chained(self):
        try:
            raise QueryError("standalone")
        except QueryError as e:
            assert e.__cause__ is None

    def test_chaining_works_for_all_subclasses(self):
        cause = RuntimeError("root cause")
        for cls in _ALL_SUBCLASSES:
            try:
                raise cls("wrapped") from cause
            except DGSError as e:
                assert e.__cause__ is cause


# ---------------------------------------------------------------------------
# 4. catch-by-base-class
# ---------------------------------------------------------------------------

class TestCatchByBaseClass:
    def test_catch_dgserror_catches_dataload_error(self):
        with pytest.raises(DGSError):
            raise DataLoadError("test")

    def test_catch_dgserror_catches_query_error(self):
        with pytest.raises(DGSError):
            raise QueryError("q failed")

    def test_catch_dgserror_catches_export_error(self):
        with pytest.raises(DGSError):
            raise ExportError("export failed")

    def test_catch_dgserror_catches_validation_error(self):
        with pytest.raises(DGSError):
            raise ValidationError("bad input")

    def test_catch_dgserror_catches_dataset_error(self):
        with pytest.raises(DGSError):
            raise DatasetError("ds failed")

    def test_catch_dgserror_catches_config_error(self):
        with pytest.raises(DGSError):
            raise ConfigError("config broken")

    def test_catch_exception_catches_dgserror(self):
        with pytest.raises(Exception):
            raise DGSError("base error")


# ---------------------------------------------------------------------------
# 5. Siblings don't catch each other
# ---------------------------------------------------------------------------

class TestSiblingIsolation:
    def test_dataload_does_not_catch_query_error(self):
        """QueryError raised while catching DataLoadError should escape."""
        with pytest.raises(QueryError):
            try:
                raise QueryError("query failed")
            except DataLoadError:
                pass  # must not reach here

    def test_config_does_not_catch_export_error(self):
        with pytest.raises(ExportError):
            try:
                raise ExportError("export failed")
            except ConfigError:
                pass

    def test_validation_does_not_catch_dataset_error(self):
        with pytest.raises(DatasetError):
            try:
                raise DatasetError("ds error")
            except ValidationError:
                pass


# ---------------------------------------------------------------------------
# 6. core __init__ exports
# ---------------------------------------------------------------------------

class TestCoreExports:
    def test_dgserror_importable_from_core(self):
        from data_graph_studio.core import DGSError  # noqa: F401

    def test_dataload_error_importable_from_core(self):
        from data_graph_studio.core import DataLoadError  # noqa: F401

    def test_query_error_importable_from_core(self):
        from data_graph_studio.core import QueryError  # noqa: F401

    def test_export_error_importable_from_core(self):
        from data_graph_studio.core import ExportError  # noqa: F401

    def test_validation_error_importable_from_core(self):
        from data_graph_studio.core import ValidationError  # noqa: F401

    def test_dataset_error_importable_from_core(self):
        from data_graph_studio.core import DatasetError  # noqa: F401

    def test_config_error_importable_from_core(self):
        from data_graph_studio.core import ConfigError  # noqa: F401

    def test_core_all_includes_all_exception_classes(self):
        import data_graph_studio.core as core
        for name in ["DGSError", "DataLoadError", "QueryError", "ExportError",
                     "ValidationError", "DatasetError", "ConfigError"]:
            assert name in core.__all__, f"{name} missing from core.__all__"


# ---------------------------------------------------------------------------
# 7. Spot-check: filtering module re-raises QueryError transparently
# ---------------------------------------------------------------------------

class TestFilteringQueryErrorPassthrough:
    """
    FilteringManager._apply_single_filter() has:
        except QueryError:
            raise
        except Exception as e:
            raise QueryError(...) from e

    QueryError propagates directly; other exceptions are wrapped in QueryError
    at the filter execution boundary. Both are tested via monkey-patching.
    """

    def _make_filter(self):
        import polars as pl
        from data_graph_studio.core.filtering import Filter, FilterOperator, FilterType
        f = Filter(
            column="a",
            operator=FilterOperator.GREATER_THAN,
            value=0,
            filter_type=FilterType.NUMERIC,
        )
        # Sanity: expression must be non-None so the filter actually runs
        assert f.to_expression() is not None
        return f

    def test_query_error_propagates_through_apply_single_filter(self, monkeypatch):
        import polars as pl
        from data_graph_studio.core.filtering import FilteringManager

        manager = FilteringManager()
        df = pl.DataFrame({"a": [1, 2, 3]})
        f = self._make_filter()

        def _raise_query_error(*args, **kwargs):
            raise QueryError("injected query error", operation="test")

        monkeypatch.setattr(pl.DataFrame, "filter", _raise_query_error)

        with pytest.raises(QueryError, match="injected query error"):
            manager._apply_single_filter(df, f)

    def test_generic_exception_is_wrapped_as_query_error(self, monkeypatch):
        """Non-QueryError exceptions are wrapped in QueryError at the filter boundary."""
        import polars as pl
        from data_graph_studio.core.filtering import FilteringManager

        manager = FilteringManager()
        df = pl.DataFrame({"a": [1, 2, 3]})
        f = self._make_filter()

        def _raise_generic(*args, **kwargs):
            raise RuntimeError("some polars internal error")

        monkeypatch.setattr(pl.DataFrame, "filter", _raise_generic)

        with pytest.raises(QueryError, match="Filter execution failed") as exc_info:
            manager._apply_single_filter(df, f)

        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert exc_info.value.context["column"] == "a"
        assert exc_info.value.context["operator"] == "gt"
