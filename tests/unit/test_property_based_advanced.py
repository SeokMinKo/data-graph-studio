"""
Advanced property-based tests for formula_parser, expression_engine, and statistics.

All tests are Qt-free — no QApplication required.
"""

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from data_graph_studio.core.formula_parser import (
    FormulaParser,
    FormulaError,
    FormulaColumnError,
    FormulaTypeError,
)
from data_graph_studio.core.expression_engine import ExpressionEngine, ExpressionError
from data_graph_studio.core.statistics import (
    CorrelationAnalyzer,
    CorrelationMethod,
    DescriptiveStatistics,
)

# Blocked patterns that FormulaParser's security check looks for in the formula string
_BLOCKED_PREFIXES = ('__', 'import', 'os.', 'sys.', 'subprocess')


def _is_safe_col_name(name: str) -> bool:
    """Return True if the column name won't trigger the formula security check."""
    lower = name.lower()
    return not any(bp in lower for bp in _BLOCKED_PREFIXES)


# ---------------------------------------------------------------------------
# Group 1: FormulaParser invariants
# ---------------------------------------------------------------------------

# Strategy for valid Python identifiers that start with a letter.
# No consecutive underscores to avoid the '__' security block.
_identifier_strategy = st.from_regex(r'[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*', fullmatch=True).filter(
    lambda s: len(s) <= 12 and _is_safe_col_name(s)
)

_safe_floats = st.floats(
    allow_nan=False,
    allow_infinity=False,
    min_value=-1e6,
    max_value=1e6,
)


@settings(max_examples=30, deadline=None)
@given(
    col_name=_identifier_strategy,
    values=st.lists(_safe_floats, min_size=1, max_size=20),
)
def test_formula_column_reference_does_not_crash(col_name, values):
    """Any valid column name referenced in {col} syntax should evaluate without error."""
    df = pl.DataFrame({col_name: values})
    parser = FormulaParser()

    # A formula that just references the column should return the column itself
    result = parser.evaluate(f"{{{col_name}}}", df)

    assert isinstance(result, pl.Series), "Expected a pl.Series result"
    assert len(result) == len(values), "Result length must match input length"


@settings(max_examples=30, deadline=None)
@given(
    col_name=_identifier_strategy,
    values=st.lists(
        st.integers(min_value=-1000, max_value=1000),
        min_size=1,
        max_size=30,
    ),
)
def test_formula_additive_identity(col_name, values):
    """Formula '{col} + 0' must produce the same values as just '{col}'."""
    df = pl.DataFrame({col_name: values})
    parser = FormulaParser()

    result_col = parser.evaluate(f"{{{col_name}}}", df)
    result_add = parser.evaluate(f"{{{col_name}}} + 0", df)

    assert result_col.cast(pl.Float64).to_list() == pytest.approx(
        result_add.cast(pl.Float64).to_list()
    ), "Additive identity failed: {col} + 0 != {col}"


@settings(max_examples=30, deadline=None)
@given(
    col_a=_identifier_strategy,
    col_b=_identifier_strategy,
    values=st.lists(
        st.integers(min_value=-500, max_value=500),
        min_size=2,
        max_size=30,
    ),
)
def test_formula_addition_commutativity(col_a, col_b, values):
    """Formula '{a} + {b}' must equal '{b} + {a}' for any numeric data."""
    assume(col_a != col_b)

    df = pl.DataFrame({col_a: values, col_b: values})
    parser = FormulaParser()

    result_ab = parser.evaluate(f"{{{col_a}}} + {{{col_b}}}", df)
    result_ba = parser.evaluate(f"{{{col_b}}} + {{{col_a}}}", df)

    assert result_ab.cast(pl.Float64).to_list() == pytest.approx(
        result_ba.cast(pl.Float64).to_list()
    ), "Addition commutativity failed: {a}+{b} != {b}+{a}"


@settings(max_examples=30, deadline=None)
@given(
    col_name=_identifier_strategy,
    values=st.lists(
        st.floats(allow_nan=False, allow_infinity=False, min_value=0.001, max_value=1e5),
        min_size=1,
        max_size=20,
    ),
)
def test_formula_multiplicative_identity(col_name, values):
    """Formula '{col} * 1' must produce the same values as '{col}'."""
    df = pl.DataFrame({col_name: values})
    parser = FormulaParser()

    result_col = parser.evaluate(f"{{{col_name}}}", df)
    result_mul = parser.evaluate(f"{{{col_name}}} * 1", df)

    assert result_col.cast(pl.Float64).to_list() == pytest.approx(
        result_mul.cast(pl.Float64).to_list()
    ), "Multiplicative identity failed: {col} * 1 != {col}"


# ---------------------------------------------------------------------------
# Group 2: ExpressionEngine invariants
# ---------------------------------------------------------------------------


@settings(max_examples=30, deadline=None)
@given(
    values=st.lists(
        st.integers(min_value=-1000, max_value=1000),
        min_size=2,
        max_size=50,
    )
)
def test_expression_engine_additive_identity(values):
    """ExpressionEngine: 'x + 0' must equal 'x'."""
    df = pl.DataFrame({"x": values})
    engine = ExpressionEngine()

    result_x = engine.evaluate("x", df)
    result_add = engine.evaluate("x + 0", df)

    assert result_x is not None
    assert result_add is not None
    assert result_x.cast(pl.Float64).to_list() == pytest.approx(
        result_add.cast(pl.Float64).to_list()
    ), "x + 0 should equal x"


@settings(max_examples=30, deadline=None)
@given(
    values=st.lists(
        st.integers(min_value=-1000, max_value=1000),
        min_size=2,
        max_size=50,
    )
)
def test_expression_engine_multiplicative_identity(values):
    """ExpressionEngine: 'x * 1' must equal 'x'."""
    df = pl.DataFrame({"x": values})
    engine = ExpressionEngine()

    result_x = engine.evaluate("x", df)
    result_mul = engine.evaluate("x * 1", df)

    assert result_x is not None
    assert result_mul is not None
    assert result_x.cast(pl.Float64).to_list() == pytest.approx(
        result_mul.cast(pl.Float64).to_list()
    ), "x * 1 should equal x"


@settings(max_examples=30, deadline=None)
@given(
    rows=st.lists(
        st.tuples(
            st.integers(min_value=-500, max_value=500),
            st.integers(min_value=-500, max_value=500),
        ),
        min_size=2,
        max_size=50,
    )
)
def test_expression_engine_addition_commutativity(rows):
    """ExpressionEngine: 'x + y' must equal 'y + x'."""
    x_values = [r[0] for r in rows]
    y_values = [r[1] for r in rows]

    df = pl.DataFrame({"x": x_values, "y": y_values})
    engine = ExpressionEngine()

    result_xy = engine.evaluate("x + y", df)
    result_yx = engine.evaluate("y + x", df)

    assert result_xy is not None
    assert result_yx is not None
    assert result_xy.cast(pl.Float64).to_list() == pytest.approx(
        result_yx.cast(pl.Float64).to_list()
    ), "x + y should equal y + x"


# ---------------------------------------------------------------------------
# Group 3: Statistical invariants
# ---------------------------------------------------------------------------


@settings(max_examples=30, deadline=None)
@given(
    values=st.lists(
        _safe_floats,
        min_size=2,
        max_size=100,
    )
)
def test_descriptive_stats_keys_present(values):
    """DescriptiveStatistics.calculate() must always return the expected set of keys."""
    stats = DescriptiveStatistics()
    data = np.array(values, dtype=float)
    # Skip if all NaN after hypothesis generates degenerate input
    assume(np.any(~np.isnan(data)))

    result = stats.calculate(data)

    expected_keys = {"mean", "median", "std", "var", "min", "max", "q1", "q3", "iqr", "n"}
    assert expected_keys.issubset(result.keys()), (
        f"Missing keys: {expected_keys - result.keys()}"
    )


@settings(max_examples=30, deadline=None)
@given(
    values=st.lists(
        _safe_floats,
        min_size=2,
        max_size=100,
    )
)
def test_descriptive_stats_range_invariant(values):
    """min <= mean <= max and min <= median <= max for any valid input."""
    stats = DescriptiveStatistics()
    data = np.array(values, dtype=float)
    assume(np.any(~np.isnan(data)))

    result = stats.calculate(data)
    if not result:
        return

    eps = abs(result["max"]) * 1e-10 + 1e-10
    assert result["min"] <= result["mean"] + eps and result["mean"] <= result["max"] + eps, (
        f"Range invariant failed: min={result['min']}, mean={result['mean']}, max={result['max']}"
    )
    assert result["min"] <= result["median"] + eps and result["median"] <= result["max"] + eps, (
        f"Median range invariant failed: min={result['min']}, median={result['median']}, max={result['max']}"
    )


@settings(max_examples=30, deadline=None)
@given(
    n_rows=st.integers(min_value=3, max_value=50),
    n_cols=st.integers(min_value=2, max_value=5),
)
def test_correlation_matrix_symmetry(n_rows, n_cols):
    """Correlation matrix must be symmetric: corr[i][j] == corr[j][i]."""
    rng = np.random.default_rng(seed=42)
    data_dict = {f"col_{i}": rng.standard_normal(n_rows).tolist() for i in range(n_cols)}
    df = pl.DataFrame(data_dict)
    columns = list(data_dict.keys())

    analyzer = CorrelationAnalyzer()
    result = analyzer.calculate_correlation(df, columns, CorrelationMethod.PEARSON)

    matrix = result.matrix
    n = len(columns)

    for i in range(n):
        for j in range(n):
            assert abs(matrix[i, j] - matrix[j, i]) < 1e-10, (
                f"Correlation matrix not symmetric at [{i},{j}]: "
                f"{matrix[i, j]} vs {matrix[j, i]}"
            )


@settings(max_examples=30, deadline=None)
@given(
    n_rows=st.integers(min_value=3, max_value=50),
    n_cols=st.integers(min_value=2, max_value=4),
)
def test_correlation_matrix_diagonal_is_one(n_rows, n_cols):
    """Diagonal of correlation matrix must always be 1.0 (self-correlation)."""
    rng = np.random.default_rng(seed=7)
    data_dict = {f"var_{i}": rng.standard_normal(n_rows).tolist() for i in range(n_cols)}
    df = pl.DataFrame(data_dict)
    columns = list(data_dict.keys())

    analyzer = CorrelationAnalyzer()
    result = analyzer.calculate_correlation(df, columns, CorrelationMethod.PEARSON)

    for i in range(n_cols):
        assert abs(result.matrix[i, i] - 1.0) < 1e-10, (
            f"Diagonal element [{i},{i}] is {result.matrix[i, i]}, expected 1.0"
        )


@settings(max_examples=30, deadline=None)
@given(
    n_rows=st.integers(min_value=3, max_value=50),
    n_cols=st.integers(min_value=2, max_value=4),
)
def test_correlation_values_bounded(n_rows, n_cols):
    """All correlation values must be in [-1, 1]."""
    rng = np.random.default_rng(seed=13)
    data_dict = {f"x_{i}": rng.standard_normal(n_rows).tolist() for i in range(n_cols)}
    df = pl.DataFrame(data_dict)
    columns = list(data_dict.keys())

    analyzer = CorrelationAnalyzer()
    result = analyzer.calculate_correlation(df, columns, CorrelationMethod.PEARSON)

    assert np.all(result.matrix >= -1.0 - 1e-10), "Correlation value below -1"
    assert np.all(result.matrix <= 1.0 + 1e-10), "Correlation value above +1"
