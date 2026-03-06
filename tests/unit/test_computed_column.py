"""
Tests for Computed Columns — Feature 3 (PRD §3.3)

UT-3.1 ~ UT-3.11: FormulaParser, ColumnDependencyGraph, DataEngine extensions
"""

import pytest
import math
import polars as pl

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from data_graph_studio.core.formula_parser import (
    FormulaParser,
    FormulaError,
    FormulaSecurityError,
    FormulaColumnError,
    FormulaTypeError,
)
from data_graph_studio.core.column_dependency_graph import (
    ColumnDependencyGraph,
    CycleDetectedError,
)


# ────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────


@pytest.fixture
def parser():
    return FormulaParser()


@pytest.fixture
def sample_df():
    """Numeric sample DataFrame for general tests."""
    return pl.DataFrame(
        {
            "voltage": [1.0, 2.0, 3.0, 4.0, 5.0],
            "current": [0.5, 1.0, 1.5, 2.0, 2.5],
            "temperature": [20.0, 21.0, 22.0, 23.0, 24.0],
        }
    )


@pytest.fixture
def large_df():
    """Larger DataFrame for rolling / diff edge-case tests."""
    return pl.DataFrame(
        {
            "value": list(range(1, 11)),  # [1..10]
            "other": [float(x) for x in range(10, 0, -1)],
        }
    )


@pytest.fixture
def mixed_df():
    """DataFrame with string and numeric columns for type-mismatch tests."""
    return pl.DataFrame(
        {
            "name": ["Alice", "Bob", "Charlie", "Dave", "Eve"],
            "score": [90.0, 80.0, 70.0, 60.0, 50.0],
        }
    )


@pytest.fixture
def div_zero_df():
    """DataFrame with zero divisor for division-by-zero tests."""
    return pl.DataFrame(
        {
            "a": [10.0, 20.0, 30.0],
            "b": [2.0, 0.0, 5.0],
        }
    )


@pytest.fixture
def dep_graph():
    return ColumnDependencyGraph()


# ────────────────────────────────────────────────────────────────
# UT-3.1: ComputedColumn formula parsing (normal)
# ────────────────────────────────────────────────────────────────


class TestUT31_FormulaParsing:
    """UT-3.1: Formula parsing — valid expressions."""

    def test_simple_multiply(self, parser, sample_df):
        """{voltage} * {current} → correct values."""
        result = parser.evaluate("{voltage} * {current}", sample_df)
        expected = [0.5, 2.0, 4.5, 8.0, 12.5]
        assert result.to_list() == pytest.approx(expected)

    def test_arithmetic_operators(self, parser, sample_df):
        """All four arithmetic operators."""
        result = parser.evaluate("{voltage} + {current} - 1", sample_df)
        expected = [0.5, 2.0, 3.5, 5.0, 6.5]
        assert result.to_list() == pytest.approx(expected)

    def test_power_operator(self, parser, sample_df):
        """{voltage} ** 2 → squares."""
        result = parser.evaluate("{voltage} ** 2", sample_df)
        expected = [1.0, 4.0, 9.0, 16.0, 25.0]
        assert result.to_list() == pytest.approx(expected)

    def test_floor_division(self, parser, sample_df):
        """{voltage} // 2 → floor division."""
        result = parser.evaluate("{voltage} // 2", sample_df)
        expected = [0.0, 1.0, 1.0, 2.0, 2.0]
        assert result.to_list() == pytest.approx(expected)

    def test_modulo(self, parser, sample_df):
        """{voltage} % 2 → modulo."""
        result = parser.evaluate("{voltage} % 2", sample_df)
        expected = [1.0, 0.0, 1.0, 0.0, 1.0]
        assert result.to_list() == pytest.approx(expected)

    def test_parenthesized_expression(self, parser, sample_df):
        """({voltage} + {current}) * 2"""
        result = parser.evaluate("({voltage} + {current}) * 2", sample_df)
        expected = [3.0, 6.0, 9.0, 12.0, 15.0]
        assert result.to_list() == pytest.approx(expected)

    def test_builtin_abs(self, parser):
        """abs() on negative values."""
        df = pl.DataFrame({"x": [-3.0, -1.0, 0.0, 1.0, 3.0]})
        result = parser.evaluate("abs({x})", df)
        assert result.to_list() == pytest.approx([3.0, 1.0, 0.0, 1.0, 3.0])

    def test_builtin_round(self, parser):
        """round() with decimals."""
        df = pl.DataFrame({"x": [1.456, 2.789, 3.123]})
        result = parser.evaluate("round({x}, 1)", df)
        assert result.to_list() == pytest.approx([1.5, 2.8, 3.1])

    def test_builtin_sqrt(self, parser):
        """sqrt() on positive values."""
        df = pl.DataFrame({"x": [4.0, 9.0, 16.0]})
        result = parser.evaluate("sqrt({x})", df)
        assert result.to_list() == pytest.approx([2.0, 3.0, 4.0])

    def test_builtin_log(self, parser):
        """log() → natural logarithm."""
        df = pl.DataFrame({"x": [1.0, math.e, math.e**2]})
        result = parser.evaluate("log({x})", df)
        assert result.to_list() == pytest.approx([0.0, 1.0, 2.0], abs=1e-6)

    def test_constant_literal(self, parser, sample_df):
        """Expression with only constants: 3.14 * 2"""
        result = parser.evaluate("3.14 * 2", sample_df)
        assert all(v == pytest.approx(6.28) for v in result.to_list())

    def test_extract_column_references(self, parser):
        """extract_column_references correctly finds {col} names."""
        refs = parser.extract_column_references("{voltage} * {current} + {temperature}")
        assert refs == {"voltage", "current", "temperature"}


# ────────────────────────────────────────────────────────────────
# UT-3.2: Formula parsing — non-existent column reference
# ────────────────────────────────────────────────────────────────


class TestUT32_ColumnNotFound:
    """UT-3.2: Referencing a non-existent column raises FormulaColumnError."""

    def test_missing_column_error(self, parser, sample_df):
        with pytest.raises(FormulaColumnError, match="not_exist"):
            parser.evaluate("{not_exist} + 1", sample_df)

    def test_error_lists_available(self, parser, sample_df):
        """Error message should mention available columns."""
        with pytest.raises(FormulaColumnError) as exc_info:
            parser.evaluate("{missing_col} * 2", sample_df)
        msg = str(exc_info.value)
        assert "voltage" in msg or "Available columns" in msg


# ────────────────────────────────────────────────────────────────
# UT-3.3: Moving average accuracy
# ────────────────────────────────────────────────────────────────


class TestUT33_MovingAverage:
    """UT-3.3: Rolling mean accuracy (FR-3.2)."""

    def test_rolling_mean_basic(self, parser, large_df):
        """rolling_mean({value}, 3) with window=3."""
        result = parser.evaluate("rolling_mean({value}, 3)", large_df)
        vals = result.to_list()
        # First 2 values are null (window not full)
        assert vals[0] is None
        assert vals[1] is None
        # 3rd value = mean(1,2,3) = 2.0
        assert vals[2] == pytest.approx(2.0)
        # 4th value = mean(2,3,4) = 3.0
        assert vals[3] == pytest.approx(3.0)
        # last = mean(8,9,10) = 9.0
        assert vals[-1] == pytest.approx(9.0)

    def test_rolling_mean_window_1(self, parser, large_df):
        """window=1 should return original values."""
        result = parser.evaluate("rolling_mean({value}, 1)", large_df)
        expected = [float(x) for x in range(1, 11)]
        assert result.to_list() == pytest.approx(expected)


# ────────────────────────────────────────────────────────────────
# UT-3.4: Normalization accuracy (min-max, z-score)
# ────────────────────────────────────────────────────────────────


class TestUT34_Normalization:
    """UT-3.4: Normalize min-max and z-score (FR-3.5)."""

    def test_min_max_normalization(self, parser):
        """min-max normalize: (x - min) / (max - min)."""
        df = pl.DataFrame({"x": [10.0, 20.0, 30.0, 40.0, 50.0]})
        result = parser.evaluate_normalize("x", "min_max", df)
        expected = [0.0, 0.25, 0.5, 0.75, 1.0]
        assert result.to_list() == pytest.approx(expected)

    def test_zscore_normalization(self, parser):
        """z-score: (x - mean) / std."""
        df = pl.DataFrame({"x": [10.0, 20.0, 30.0, 40.0, 50.0]})
        result = parser.evaluate_normalize("x", "z_score", df)
        vals = result.to_list()
        # Mean = 30, std ≈ 15.81 (ddof=1) or 14.14 (ddof=0)
        # z-score of 10 should be negative, 30 should be ~0, 50 positive
        assert vals[2] == pytest.approx(0.0, abs=0.01)
        assert vals[0] < 0
        assert vals[4] > 0

    def test_min_max_constant_column(self, parser):
        """All-same values → 0.0 (avoid division by zero)."""
        df = pl.DataFrame({"x": [5.0, 5.0, 5.0]})
        result = parser.evaluate_normalize("x", "min_max", df)
        assert result.to_list() == pytest.approx([0.0, 0.0, 0.0])

    def test_zscore_constant_column(self, parser):
        """All-same values → 0.0 (avoid division by zero)."""
        df = pl.DataFrame({"x": [5.0, 5.0, 5.0]})
        result = parser.evaluate_normalize("x", "z_score", df)
        assert result.to_list() == pytest.approx([0.0, 0.0, 0.0])


# ────────────────────────────────────────────────────────────────
# UT-3.5: Cycle detection (A→B→A → error)
# ────────────────────────────────────────────────────────────────


class TestUT35_CycleDetection:
    """UT-3.5: ColumnDependencyGraph cycle detection (FR-3.10)."""

    def test_direct_cycle(self, dep_graph):
        """A depends on B, B depends on A → cycle."""
        dep_graph.add_column("A", {"B"})
        with pytest.raises(CycleDetectedError, match="Circular dependency"):
            dep_graph.add_column("B", {"A"})

    def test_indirect_cycle(self, dep_graph):
        """A→B, B→C, C→A → cycle."""
        dep_graph.add_column("A", {"B"})
        dep_graph.add_column("B", {"C"})
        with pytest.raises(CycleDetectedError):
            dep_graph.add_column("C", {"A"})

    def test_self_reference(self, dep_graph):
        """A depends on itself → cycle."""
        with pytest.raises(CycleDetectedError):
            dep_graph.add_column("A", {"A"})

    def test_no_cycle(self, dep_graph):
        """A→B, B→C (no cycle) — should succeed."""
        dep_graph.add_column("C", set())
        dep_graph.add_column("B", {"C"})
        dep_graph.add_column("A", {"B"})
        assert not dep_graph.has_cycle()

    def test_cycle_error_message_contains_path(self, dep_graph):
        """Error message should contain the cycle path."""
        dep_graph.add_column("A", {"B"})
        with pytest.raises(CycleDetectedError) as exc_info:
            dep_graph.add_column("B", {"A"})
        msg = str(exc_info.value)
        assert "A" in msg and "B" in msg


# ────────────────────────────────────────────────────────────────
# UT-3.6: DAG topological sort order
# ────────────────────────────────────────────────────────────────


class TestUT36_TopologicalSort:
    """UT-3.6: Topological sort order for evaluation."""

    def test_linear_chain(self, dep_graph):
        """C (no deps), B→C, A→B  ⇒ order must be [C, B, A]."""
        dep_graph.add_column("C", set())
        dep_graph.add_column("B", {"C"})
        dep_graph.add_column("A", {"B"})
        order = dep_graph.get_evaluation_order()
        assert order.index("C") < order.index("B") < order.index("A")

    def test_diamond_dependency(self, dep_graph):
        """D = no deps, B→D, C→D, A→{B,C}."""
        dep_graph.add_column("D", set())
        dep_graph.add_column("B", {"D"})
        dep_graph.add_column("C", {"D"})
        dep_graph.add_column("A", {"B", "C"})
        order = dep_graph.get_evaluation_order()
        assert order.index("D") < order.index("B")
        assert order.index("D") < order.index("C")
        assert order.index("B") < order.index("A")
        assert order.index("C") < order.index("A")

    def test_independent_columns(self, dep_graph):
        """Independent columns — all appear in order, any order OK."""
        dep_graph.add_column("X", set())
        dep_graph.add_column("Y", set())
        dep_graph.add_column("Z", set())
        order = dep_graph.get_evaluation_order()
        assert set(order) == {"X", "Y", "Z"}

    def test_empty_graph(self, dep_graph):
        """Empty graph → empty list."""
        assert dep_graph.get_evaluation_order() == []


# ────────────────────────────────────────────────────────────────
# UT-3.7: Whitelist — allowed functions succeed
# ────────────────────────────────────────────────────────────────


class TestUT37_WhitelistAllowed:
    """UT-3.7: Allowed functions pass whitelist check."""

    @pytest.mark.parametrize(
        "formula",
        [
            "abs({x})",
            "round({x}, 2)",
            "sqrt({x})",
            "log({x})",
            "pow({x}, 2)",
            "min({x}, {y})",
            "max({x}, {y})",
            "sum({x})",
            "mean({x})",
            "std({x})",
            "count({x})",
            "first({x})",
            "last({x})",
            "shift({x}, 1)",
            "diff({x})",
            "cumsum({x})",
            "rolling_mean({x}, 3)",
            "clip({x}, 0, 10)",
        ],
    )
    def test_allowed_functions(self, parser, formula):
        """All whitelisted functions should pass validation."""
        df = pl.DataFrame(
            {"x": [1.0, 2.0, 3.0, 4.0, 5.0], "y": [5.0, 4.0, 3.0, 2.0, 1.0]}
        )
        # Should not raise FormulaSecurityError
        parser.validate(formula, df)


# ────────────────────────────────────────────────────────────────
# UT-3.8: Whitelist — disallowed functions blocked
# ────────────────────────────────────────────────────────────────


class TestUT38_WhitelistBlocked:
    """UT-3.8: Disallowed functions raise FormulaSecurityError."""

    @pytest.mark.parametrize(
        "formula,blocked",
        [
            ('eval("1+1")', "eval"),
            ('exec("x=1")', "exec"),
            ('__import__("os")', "__import__"),
            ('open("/etc/passwd")', "open"),
        ],
    )
    def test_blocked_functions(self, parser, formula, blocked):
        df = pl.DataFrame({"x": [1.0, 2.0, 3.0]})
        with pytest.raises(FormulaSecurityError, match="not allowed"):
            parser.validate(formula, df)

    def test_blocked_dunder(self, parser):
        """Identifiers starting with __ are blocked."""
        df = pl.DataFrame({"x": [1.0]})
        with pytest.raises(FormulaSecurityError):
            parser.validate("__builtins__", df)

    def test_blocked_import_keyword(self, parser):
        """import statement is blocked."""
        df = pl.DataFrame({"x": [1.0]})
        with pytest.raises(FormulaSecurityError):
            parser.validate("import os", df)

    def test_error_message_lists_allowed(self, parser):
        """Error message should list allowed functions."""
        df = pl.DataFrame({"x": [1.0]})
        with pytest.raises(FormulaSecurityError) as exc_info:
            parser.validate("eval({x})", df)
        msg = str(exc_info.value)
        assert "Allowed functions" in msg or "not allowed" in msg


# ────────────────────────────────────────────────────────────────
# UT-3.9: Division by zero → null
# ────────────────────────────────────────────────────────────────


class TestUT39_DivisionByZero:
    """UT-3.9: {a} / {b} where b=0 → null (ERR-3.2)."""

    def test_div_zero_produces_null(self, parser, div_zero_df):
        result = parser.evaluate("{a} / {b}", div_zero_df)
        vals = result.to_list()
        assert vals[0] == pytest.approx(5.0)
        assert vals[1] is None  # 20/0 → null
        assert vals[2] == pytest.approx(6.0)

    def test_floor_div_zero_produces_null(self, parser, div_zero_df):
        result = parser.evaluate("{a} // {b}", div_zero_df)
        vals = result.to_list()
        assert vals[1] is None  # 20//0 → null

    def test_modulo_zero_produces_null(self, parser, div_zero_df):
        result = parser.evaluate("{a} % {b}", div_zero_df)
        vals = result.to_list()
        assert vals[1] is None  # 20%0 → null


# ────────────────────────────────────────────────────────────────
# UT-3.10: Type mismatch error
# ────────────────────────────────────────────────────────────────


class TestUT310_TypeMismatch:
    """UT-3.10: String column + math op → FormulaTypeError (ERR-3.3)."""

    def test_string_plus_number(self, parser, mixed_df):
        """Arithmetic on a string column raises FormulaTypeError."""
        with pytest.raises(FormulaTypeError, match="name"):
            parser.evaluate("{name} + 1", mixed_df)

    def test_string_multiply(self, parser, mixed_df):
        with pytest.raises(FormulaTypeError, match="name"):
            parser.evaluate("{name} * 2", mixed_df)

    def test_math_func_on_string(self, parser, mixed_df):
        """sqrt(string_column) → FormulaTypeError."""
        with pytest.raises(FormulaTypeError, match="name"):
            parser.evaluate("sqrt({name})", mixed_df)


# ────────────────────────────────────────────────────────────────
# UT-3.11: Moving average edge cases (window=0, window > row count)
# ────────────────────────────────────────────────────────────────


class TestUT311_RollingEdgeCases:
    """UT-3.11: Boundary cases for rolling_mean."""

    def test_window_zero_raises(self, parser, large_df):
        """window=0 → error."""
        with pytest.raises((FormulaError, ValueError)):
            parser.evaluate("rolling_mean({value}, 0)", large_df)

    def test_window_negative_raises(self, parser, large_df):
        """window<0 → error."""
        with pytest.raises((FormulaError, ValueError)):
            parser.evaluate("rolling_mean({value}, -1)", large_df)

    def test_window_exceeds_row_count(self, parser, large_df):
        """window > row count → all nulls except possibly the last few."""
        result = parser.evaluate("rolling_mean({value}, 100)", large_df)
        vals = result.to_list()
        # With window=100 and only 10 rows, all values should be null
        assert all(v is None for v in vals)


# ────────────────────────────────────────────────────────────────
# Additional tests: ColumnDependencyGraph operations
# ────────────────────────────────────────────────────────────────


class TestDependencyGraphOperations:
    """Additional tests for remove_column and get_dependents."""

    def test_remove_column(self, dep_graph):
        """Removing a column removes it from the graph."""
        dep_graph.add_column("A", set())
        dep_graph.add_column("B", {"A"})
        dep_graph.remove_column("B")
        assert "B" not in dep_graph.get_evaluation_order()

    def test_get_dependents(self, dep_graph):
        """get_dependents returns all columns that depend on a given column."""
        dep_graph.add_column("base", set())
        dep_graph.add_column("derived1", {"base"})
        dep_graph.add_column("derived2", {"base"})
        dep_graph.add_column("derived3", {"derived1"})
        dependents = dep_graph.get_dependents("base")
        assert dependents == {"derived1", "derived2", "derived3"}

    def test_get_dependents_no_deps(self, dep_graph):
        """Column with no dependents returns empty set."""
        dep_graph.add_column("lonely", set())
        assert dep_graph.get_dependents("lonely") == set()

    def test_remove_and_re_add(self, dep_graph):
        """Can remove and re-add a column with different deps."""
        dep_graph.add_column("A", set())
        dep_graph.add_column("B", {"A"})
        dep_graph.remove_column("B")
        dep_graph.add_column("B", set())  # No longer depends on A
        order = dep_graph.get_evaluation_order()
        assert "A" in order and "B" in order


# ────────────────────────────────────────────────────────────────
# Additional tests: Diff, Cumsum
# ────────────────────────────────────────────────────────────────


class TestDiffAndCumsum:
    """Tests for diff (FR-3.3) and cumsum (FR-3.4)."""

    def test_diff_basic(self, parser, large_df):
        """diff({value}) → first element is null, rest are differences."""
        result = parser.evaluate("diff({value})", large_df)
        vals = result.to_list()
        assert vals[0] is None
        # All diffs should be 1 (consecutive integers)
        assert all(v == 1 for v in vals[1:])

    def test_diff_order_2(self, parser, large_df):
        """diff({value}, 2) → 2nd-order difference."""
        result = parser.evaluate("diff({value}, 2)", large_df)
        vals = result.to_list()
        assert vals[0] is None
        assert vals[1] is None
        # 2nd-order diff of consecutive integers = 2 each
        assert vals[2] == 2

    def test_cumsum_basic(self, parser, large_df):
        """cumsum({value}) → cumulative sum."""
        result = parser.evaluate("cumsum({value})", large_df)
        vals = result.to_list()
        assert vals[0] == 1
        assert vals[1] == 3  # 1+2
        assert vals[2] == 6  # 1+2+3
        assert vals[-1] == 55  # sum(1..10)


# ────────────────────────────────────────────────────────────────
# Additional tests: Comparison and logic operators
# ────────────────────────────────────────────────────────────────


class TestComparisonAndLogic:
    """Tests for comparison and logical operators."""

    def test_greater_than(self, parser, sample_df):
        result = parser.evaluate("{voltage} > 3", sample_df)
        assert result.to_list() == [False, False, False, True, True]

    def test_equals(self, parser, sample_df):
        result = parser.evaluate("{voltage} == 3.0", sample_df)
        assert result.to_list() == [False, False, True, False, False]

    def test_not_equals(self, parser, sample_df):
        result = parser.evaluate("{voltage} != 3.0", sample_df)
        assert result.to_list() == [True, True, False, True, True]
