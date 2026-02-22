"""
Tests capturing current behavior of Filter.to_expression() for dispatch table refactoring.

Each test verifies the Polars expression produced by a given filter operator is correct
by applying it to a small DataFrame and checking the results.
"""

import pytest
import polars as pl

from data_graph_studio.core.filtering import (
    Filter,
    FilterOperator,
    FilterType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_filter(operator, value, column="col", case_sensitive=True):
    return Filter(
        column=column,
        operator=operator,
        value=value,
        enabled=True,
        case_sensitive=case_sensitive,
    )


def apply_expr(f: Filter, df: pl.DataFrame) -> pl.DataFrame:
    expr = f.to_expression()
    assert expr is not None, "to_expression() returned None unexpectedly"
    return df.filter(expr)


# ---------------------------------------------------------------------------
# Comparison operators
# ---------------------------------------------------------------------------

class TestComparisonOperators:
    @pytest.fixture
    def num_df(self):
        return pl.DataFrame({"col": [10, 20, 30, 40, 50]})

    def test_equals(self, num_df):
        f = make_filter(FilterOperator.EQUALS, 30)
        result = apply_expr(f, num_df)
        assert result["col"].to_list() == [30]

    def test_not_equals(self, num_df):
        f = make_filter(FilterOperator.NOT_EQUALS, 30)
        result = apply_expr(f, num_df)
        assert result["col"].to_list() == [10, 20, 40, 50]

    def test_greater_than(self, num_df):
        f = make_filter(FilterOperator.GREATER_THAN, 30)
        result = apply_expr(f, num_df)
        assert result["col"].to_list() == [40, 50]

    def test_greater_than_or_equals(self, num_df):
        f = make_filter(FilterOperator.GREATER_THAN_OR_EQUALS, 30)
        result = apply_expr(f, num_df)
        assert result["col"].to_list() == [30, 40, 50]

    def test_less_than(self, num_df):
        f = make_filter(FilterOperator.LESS_THAN, 30)
        result = apply_expr(f, num_df)
        assert result["col"].to_list() == [10, 20]

    def test_less_than_or_equals(self, num_df):
        f = make_filter(FilterOperator.LESS_THAN_OR_EQUALS, 30)
        result = apply_expr(f, num_df)
        assert result["col"].to_list() == [10, 20, 30]


# ---------------------------------------------------------------------------
# Range operators
# ---------------------------------------------------------------------------

class TestRangeOperators:
    @pytest.fixture
    def num_df(self):
        return pl.DataFrame({"col": [10, 20, 30, 40, 50]})

    def test_between_inclusive(self, num_df):
        f = make_filter(FilterOperator.BETWEEN, (20, 40))
        result = apply_expr(f, num_df)
        assert result["col"].to_list() == [20, 30, 40]

    def test_not_between(self, num_df):
        f = make_filter(FilterOperator.NOT_BETWEEN, (20, 40))
        result = apply_expr(f, num_df)
        assert result["col"].to_list() == [10, 50]

    def test_between_returns_none_for_invalid_value(self):
        f = make_filter(FilterOperator.BETWEEN, 42)  # not a 2-tuple
        expr = f.to_expression()
        assert expr is None

    def test_not_between_returns_none_for_invalid_value(self):
        f = make_filter(FilterOperator.NOT_BETWEEN, 42)
        expr = f.to_expression()
        assert expr is None


# ---------------------------------------------------------------------------
# List operators
# ---------------------------------------------------------------------------

class TestListOperators:
    @pytest.fixture
    def str_df(self):
        return pl.DataFrame({"col": ["Asia", "Europe", "Asia", "America", "Europe"]})

    def test_in_list(self, str_df):
        f = make_filter(FilterOperator.IN_LIST, ["Asia", "Europe"])
        result = apply_expr(f, str_df)
        assert set(result["col"].to_list()) == {"Asia", "Europe"}

    def test_not_in_list(self, str_df):
        f = make_filter(FilterOperator.NOT_IN_LIST, ["Asia", "Europe"])
        result = apply_expr(f, str_df)
        assert result["col"].to_list() == ["America"]

    def test_in_list_with_set(self, str_df):
        f = make_filter(FilterOperator.IN_LIST, {"Asia"})
        result = apply_expr(f, str_df)
        assert all(v == "Asia" for v in result["col"].to_list())

    def test_in_list_returns_none_for_invalid_value(self):
        f = make_filter(FilterOperator.IN_LIST, "not_a_list")
        expr = f.to_expression()
        assert expr is None

    def test_not_in_list_returns_none_for_invalid_value(self):
        f = make_filter(FilterOperator.NOT_IN_LIST, "not_a_list")
        expr = f.to_expression()
        assert expr is None


# ---------------------------------------------------------------------------
# String operators — case-sensitive
# ---------------------------------------------------------------------------

class TestStringOperatorsCaseSensitive:
    @pytest.fixture
    def str_df(self):
        return pl.DataFrame({"col": ["Apple", "Banana", "apricot", "Cherry"]})

    def test_contains_case_sensitive_match(self, str_df):
        f = make_filter(FilterOperator.CONTAINS, "an", case_sensitive=True)
        result = apply_expr(f, str_df)
        assert result["col"].to_list() == ["Banana"]

    def test_contains_case_sensitive_no_match(self, str_df):
        # uppercase "AN" should NOT match "Banana" when case_sensitive=True
        f = make_filter(FilterOperator.CONTAINS, "AN", case_sensitive=True)
        result = apply_expr(f, str_df)
        assert result["col"].to_list() == []

    def test_not_contains_case_sensitive(self, str_df):
        f = make_filter(FilterOperator.NOT_CONTAINS, "an", case_sensitive=True)
        result = apply_expr(f, str_df)
        assert "Banana" not in result["col"].to_list()

    def test_starts_with_case_sensitive(self, str_df):
        f = make_filter(FilterOperator.STARTS_WITH, "A", case_sensitive=True)
        result = apply_expr(f, str_df)
        assert result["col"].to_list() == ["Apple"]

    def test_ends_with_case_sensitive(self, str_df):
        f = make_filter(FilterOperator.ENDS_WITH, "e", case_sensitive=True)
        result = apply_expr(f, str_df)
        assert result["col"].to_list() == ["Apple"]


# ---------------------------------------------------------------------------
# String operators — case-insensitive
# ---------------------------------------------------------------------------

class TestStringOperatorsCaseInsensitive:
    @pytest.fixture
    def str_df(self):
        return pl.DataFrame({"col": ["Apple", "Banana", "apricot", "Cherry"]})

    def test_contains_case_insensitive(self, str_df):
        f = make_filter(FilterOperator.CONTAINS, "APPLE", case_sensitive=False)
        result = apply_expr(f, str_df)
        assert result["col"].to_list() == ["Apple"]

    def test_not_contains_case_insensitive(self, str_df):
        f = make_filter(FilterOperator.NOT_CONTAINS, "APPLE", case_sensitive=False)
        result = apply_expr(f, str_df)
        assert "Apple" not in result["col"].to_list()

    def test_starts_with_case_insensitive(self, str_df):
        f = make_filter(FilterOperator.STARTS_WITH, "a", case_sensitive=False)
        result = apply_expr(f, str_df)
        assert set(result["col"].to_list()) == {"Apple", "apricot"}

    def test_ends_with_case_insensitive(self, str_df):
        # "Apple" ends with "e"/"E", "apricot" ends with "t" — only Apple matches
        f = make_filter(FilterOperator.ENDS_WITH, "E", case_sensitive=False)
        result = apply_expr(f, str_df)
        assert result["col"].to_list() == ["Apple"]


# ---------------------------------------------------------------------------
# Regex operator
# ---------------------------------------------------------------------------

class TestRegexOperator:
    @pytest.fixture
    def str_df(self):
        return pl.DataFrame({"col": ["foo123", "bar456", "baz789", "foo999"]})

    def test_matches_regex(self, str_df):
        f = make_filter(FilterOperator.MATCHES_REGEX, r"^foo")
        result = apply_expr(f, str_df)
        assert result["col"].to_list() == ["foo123", "foo999"]

    def test_matches_regex_digits(self, str_df):
        f = make_filter(FilterOperator.MATCHES_REGEX, r"\d{3}$")
        result = apply_expr(f, str_df)
        assert len(result) == 4  # all end with 3 digits


# ---------------------------------------------------------------------------
# Null operators
# ---------------------------------------------------------------------------

class TestNullOperators:
    @pytest.fixture
    def nullable_df(self):
        return pl.DataFrame({"col": [1, None, 3, None, 5]})

    def test_is_null(self, nullable_df):
        f = make_filter(FilterOperator.IS_NULL, None)
        result = apply_expr(f, nullable_df)
        assert len(result) == 2
        assert result["col"].to_list() == [None, None]

    def test_is_not_null(self, nullable_df):
        f = make_filter(FilterOperator.IS_NOT_NULL, None)
        result = apply_expr(f, nullable_df)
        assert len(result) == 3
        assert None not in result["col"].to_list()


# ---------------------------------------------------------------------------
# Boolean operators
# ---------------------------------------------------------------------------

class TestBooleanOperators:
    @pytest.fixture
    def bool_df(self):
        return pl.DataFrame({"col": [True, False, True, False, True]})

    def test_is_true(self, bool_df):
        f = make_filter(FilterOperator.IS_TRUE, None)
        result = apply_expr(f, bool_df)
        assert len(result) == 3
        assert all(v is True for v in result["col"].to_list())

    def test_is_false_filter(self):
        """is_false filter returns rows where column is False."""
        df = pl.DataFrame({"active": [True, False, True, False]})
        f = make_filter(FilterOperator.IS_FALSE, None, column="active")
        result = apply_expr(f, df)
        assert result.shape[0] == 2
        assert result["active"].to_list() == [False, False]


# ---------------------------------------------------------------------------
# Disabled filter
# ---------------------------------------------------------------------------

class TestDisabledFilter:
    def test_disabled_filter_returns_none(self):
        f = Filter(
            column="col",
            operator=FilterOperator.EQUALS,
            value=42,
            enabled=False,
        )
        assert f.to_expression() is None
