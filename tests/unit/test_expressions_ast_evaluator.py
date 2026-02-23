"""
Unit tests for ExpressionEvaluatorHelpers (expressions_ast_evaluator.py).

Tests cover:
- parse_value: string literals, column references, numeric types, fallback
- evaluate_condition: all operators, no-op cases, comparison errors
- evaluate_if: normal case, bad syntax, scalar vs series values
- evaluate_case: WHEN/THEN/ELSE matching, fallback default
- evaluate_string_concat: column + literal concatenation
- handle_math_functions: regex substitution of math names
"""

import re
import pytest
import polars as pl

from data_graph_studio.core.expressions_ast_evaluator import ExpressionEvaluatorHelpers

COLUMN_PATTERN = re.compile(r'^\[([^\]]+)\]$')


def make_helper() -> ExpressionEvaluatorHelpers:
    return ExpressionEvaluatorHelpers(column_pattern=COLUMN_PATTERN)


def sample_df() -> pl.DataFrame:
    return pl.DataFrame({
        "a": [1, 2, 3],
        "b": [10.0, 20.0, 30.0],
        "name": ["alice", "bob", "carol"],
    })


# ---------------------------------------------------------------------------
# parse_value
# ---------------------------------------------------------------------------

class TestParseValue:
    def test_single_quoted_string_literal(self):
        h = make_helper()
        assert h.parse_value("'hello'", sample_df()) == "hello"

    def test_double_quoted_string_literal(self):
        h = make_helper()
        assert h.parse_value('"world"', sample_df()) == "world"

    def test_integer_literal(self):
        h = make_helper()
        result = h.parse_value("42", sample_df())
        assert result == 42
        assert isinstance(result, int)

    def test_float_literal(self):
        h = make_helper()
        result = h.parse_value("3.14", sample_df())
        assert result == pytest.approx(3.14)
        assert isinstance(result, float)

    def test_column_reference_returns_list(self):
        h = make_helper()
        result = h.parse_value("[a]", sample_df())
        assert result == [1, 2, 3]

    def test_column_reference_missing_column_returns_none(self):
        h = make_helper()
        result = h.parse_value("[nonexistent]", sample_df())
        assert result is None

    def test_bare_string_passthrough(self):
        h = make_helper()
        # Not a quoted literal, not a column ref, not a number
        result = h.parse_value("sometoken", sample_df())
        assert result == "sometoken"

    def test_empty_string_literal(self):
        h = make_helper()
        assert h.parse_value("''", sample_df()) == ""


# ---------------------------------------------------------------------------
# evaluate_condition
# ---------------------------------------------------------------------------

class TestEvaluateCondition:
    def test_equality_with_literal(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2, 3]})
        result = h.evaluate_condition("[x] = 2", df)
        assert result == [False, True, False]

    def test_greater_than(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2, 3]})
        result = h.evaluate_condition("[x] > 1", df)
        assert result == [False, True, True]

    def test_less_than_or_equal(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2, 3]})
        result = h.evaluate_condition("[x] <= 2", df)
        assert result == [True, True, False]

    def test_not_equal_operator(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2, 3]})
        result = h.evaluate_condition("[x] != 2", df)
        assert result == [True, False, True]

    def test_diamond_not_equal(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2, 3]})
        result = h.evaluate_condition("[x] <> 2", df)
        assert result == [True, False, True]

    def test_no_operator_returns_all_false(self):
        h = make_helper()
        df = sample_df()
        result = h.evaluate_condition("no_operator_here", df)
        assert all(v is False for v in result)
        assert len(result) == len(df)

    def test_returns_list_of_bools(self):
        h = make_helper()
        df = pl.DataFrame({"x": [5]})
        result = h.evaluate_condition("[x] > 3", df)
        assert isinstance(result, list)
        assert isinstance(result[0], bool)

    def test_incompatible_comparison_appends_false(self):
        h = make_helper()
        # Comparing a string column to a number should not raise, just return False
        df = pl.DataFrame({"name": ["alice", "bob"]})
        result = h.evaluate_condition("[name] > 5", df)
        assert isinstance(result, list)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# evaluate_if
# ---------------------------------------------------------------------------

class TestEvaluateIf:
    def test_basic_if_scalar_branches(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2, 3]})
        series = h.evaluate_if("If([x] > 1, 'big', 'small')", df)
        assert list(series) == ["small", "big", "big"]

    def test_if_returns_polars_series(self):
        h = make_helper()
        df = pl.DataFrame({"x": [10]})
        result = h.evaluate_if("If([x] > 5, 1, 0)", df)
        assert isinstance(result, pl.Series)

    def test_if_with_bad_syntax_returns_null_series(self):
        h = make_helper()
        df = sample_df()
        result = h.evaluate_if("If(bad syntax no parens", df)
        assert len(result) == len(df)
        assert all(v is None for v in result.to_list())

    def test_if_length_matches_dataframe(self):
        h = make_helper()
        df = pl.DataFrame({"v": list(range(100))})
        result = h.evaluate_if("If([v] > 50, 1, 0)", df)
        assert len(result) == 100


# ---------------------------------------------------------------------------
# evaluate_conditional (dispatch)
# ---------------------------------------------------------------------------

class TestEvaluateConditional:
    def test_dispatches_to_evaluate_if(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2]})
        result = h.evaluate_conditional("If([x] = 1, 'yes', 'no')", df)
        assert list(result) == ["yes", "no"]

    def test_dispatches_to_evaluate_case(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2, 99]})
        expr = "Case When [x] = 1 Then 'one' When [x] = 2 Then 'two' Else 'other' End"
        result = h.evaluate_conditional(expr, df)
        assert result[0] == "one"
        assert result[1] == "two"
        assert result[2] == "other"

    def test_unrecognised_expression_returns_null_series(self):
        h = make_helper()
        df = sample_df()
        result = h.evaluate_conditional("UNKNOWN_EXPR", df)
        assert len(result) == len(df)
        assert all(v is None for v in result.to_list())


# ---------------------------------------------------------------------------
# evaluate_case
# ---------------------------------------------------------------------------

class TestEvaluateCase:
    def test_when_then_else(self):
        h = make_helper()
        df = pl.DataFrame({"grade": [90, 75, 50]})
        expr = "Case When [grade] >= 80 Then 'A' When [grade] >= 70 Then 'B' Else 'C' End"
        result = h.evaluate_case(expr, df)
        assert result[0] == "A"
        assert result[1] == "B"
        assert result[2] == "C"

    def test_no_match_no_else_gives_none(self):
        h = make_helper()
        df = pl.DataFrame({"x": [999]})
        expr = "Case When [x] = 1 Then 'one' End"
        result = h.evaluate_case(expr, df)
        assert result[0] is None

    def test_returns_polars_series(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1]})
        result = h.evaluate_case("Case When [x] = 1 Then 'hit' Else 'miss' End", df)
        assert isinstance(result, pl.Series)

    def test_length_matches_dataframe(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2, 3, 4, 5]})
        result = h.evaluate_case("Case When [x] > 3 Then 'high' Else 'low' End", df)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# evaluate_string_concat
# ---------------------------------------------------------------------------

class TestEvaluateStringConcat:
    def test_column_and_literal(self):
        h = make_helper()
        df = pl.DataFrame({"first": ["John", "Jane"]})
        result = h.evaluate_string_concat("[first] & ' Smith'", df)
        assert list(result) == ["John Smith", "Jane Smith"]

    def test_two_columns(self):
        h = make_helper()
        df = pl.DataFrame({"a": ["foo"], "b": ["bar"]})
        result = h.evaluate_string_concat("[a] & [b]", df)
        assert result[0] == "foobar"

    def test_literal_only(self):
        h = make_helper()
        df = pl.DataFrame({"x": [1, 2]})
        result = h.evaluate_string_concat("'hello'", df)
        assert list(result) == ["hello", "hello"]

    def test_returns_polars_series(self):
        h = make_helper()
        df = pl.DataFrame({"x": ["a"]})
        result = h.evaluate_string_concat("[x]", df)
        assert isinstance(result, pl.Series)

    def test_empty_dataframe_returns_empty_series(self):
        h = make_helper()
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Utf8)})
        result = h.evaluate_string_concat("[x] & '_suffix'", df)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# handle_math_functions
# ---------------------------------------------------------------------------

class TestHandleMathFunctions:
    def test_abs_replaced(self):
        h = make_helper()
        result = h.handle_math_functions("Abs([x])", sample_df())
        assert "np.abs(" in result

    def test_sqrt_replaced(self):
        h = make_helper()
        result = h.handle_math_functions("Sqrt([x])", sample_df())
        assert "np.sqrt(" in result

    def test_log_replaced(self):
        h = make_helper()
        result = h.handle_math_functions("Log([x])", sample_df())
        assert "np.log(" in result

    def test_returns_string(self):
        h = make_helper()
        result = h.handle_math_functions("Round(3.5)", sample_df())
        assert isinstance(result, str)

    def test_no_math_functions_unchanged(self):
        h = make_helper()
        expr = "[a] + [b]"
        result = h.handle_math_functions(expr, sample_df())
        assert result == expr
