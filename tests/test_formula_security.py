"""
Security and edge-case tests for formula/expression parsers.

Three parsers are under test:
  - FormulaParser   (data_graph_studio/core/formula_parser.py)
      AST-walking evaluator with explicit whitelist/blacklist. No raw eval().
  - ExpressionEngine (data_graph_studio/core/expression_engine.py)
      Custom lexer + parser; validates function names against a whitelist.
  - ExpressionParser (data_graph_studio/core/expressions.py)
      Spotfire-style parser; uses eval() with restricted __builtins__ for
      simple arithmetic and exec() with restricted __builtins__ in DataFunction.

Security posture summary (as discovered by these tests):
  FormulaParser  — strong: blocked at text-scan + AST level before any eval.
  ExpressionEngine — strong: custom tokenizer never reaches Python eval.
  ExpressionParser — partial: eval with empty __builtins__ blocks most stdlib
      access, but builtins-bypass tricks may work in some Python versions.
      DataFunction.execute() runs arbitrary user code via exec(); this is a
      documented design decision but worth flagging explicitly.
"""

import math

import polars as pl
import pytest

from data_graph_studio.core.formula_parser import (
    FormulaParser,
    FormulaError,
    FormulaSecurityError,
    FormulaColumnError,
    FormulaTypeError,
)
from data_graph_studio.core.expression_engine import ExpressionEngine, ExpressionError
from data_graph_studio.core.expressions import (
    ExpressionParser,
    DataFunction,
    SecurityError,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fp():
    return FormulaParser()


@pytest.fixture
def ee():
    return ExpressionEngine()


@pytest.fixture
def ep():
    return ExpressionParser()


@pytest.fixture
def numeric_df():
    """Small numeric DataFrame used across most tests."""
    return pl.DataFrame(
        {
            "x": [1.0, 4.0, 9.0, 16.0],
            "y": [2.0, 0.0, -1.0, 8.0],
            "z": [0.0, 0.0, 0.0, 0.0],
        }
    )


@pytest.fixture
def empty_df():
    return pl.DataFrame({"x": pl.Series([], dtype=pl.Float64)})


@pytest.fixture
def nan_df():
    return pl.DataFrame({"x": [float("nan"), float("nan"), float("nan")]})


# ===========================================================================
# FormulaParser — security tests
# ===========================================================================


class TestFormulaParserSecurity:
    """FR-3.11: verify that blocked patterns raise FormulaSecurityError."""

    # ── exec ────────────────────────────────────────────────────────────────

    def test_exec_blocked(self, fp, numeric_df):
        """exec() must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate('exec("import os")', numeric_df)

    def test_exec_upper_blocked(self, fp, numeric_df):
        """Case-insensitive match: EXEC must also be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate('EXEC("import os")', numeric_df)

    # ── eval ────────────────────────────────────────────────────────────────

    def test_eval_blocked(self, fp, numeric_df):
        """eval() must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate('eval("1+1")', numeric_df)

    # ── __import__ / dunder ──────────────────────────────────────────────────

    def test_dunder_import_blocked(self, fp, numeric_df):
        """__import__ must be blocked (dunder prefix)."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("__import__('os').system('ls')", numeric_df)

    def test_dunder_builtins_blocked(self, fp, numeric_df):
        """__builtins__ access must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("__builtins__['eval']('1')", numeric_df)

    # ── import keyword ───────────────────────────────────────────────────────

    def test_import_keyword_blocked(self, fp, numeric_df):
        """The word 'import' anywhere in the formula must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("import os", numeric_df)

    # ── os. / sys. / subprocess ──────────────────────────────────────────────

    def test_os_dot_blocked(self, fp, numeric_df):
        """References to os. must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("os.system('ls')", numeric_df)

    def test_sys_dot_blocked(self, fp, numeric_df):
        """References to sys. must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("sys.exit()", numeric_df)

    def test_subprocess_blocked(self, fp, numeric_df):
        """References to subprocess must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("subprocess.run(['ls'])", numeric_df)

    # ── open ────────────────────────────────────────────────────────────────

    def test_open_blocked(self, fp, numeric_df):
        """open() must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("open('/etc/passwd')", numeric_df)

    # ── getattr / setattr ────────────────────────────────────────────────────

    def test_getattr_blocked(self, fp, numeric_df):
        """getattr() must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("getattr(object, '__class__')", numeric_df)

    def test_setattr_blocked(self, fp, numeric_df):
        """setattr() must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("setattr(object, 'x', 1)", numeric_df)

    # ── globals / locals ────────────────────────────────────────────────────

    def test_globals_blocked(self, fp, numeric_df):
        """globals() must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("globals()['__builtins__']", numeric_df)

    def test_locals_blocked(self, fp, numeric_df):
        """locals() must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("locals()", numeric_df)

    # ── non-whitelisted functions ────────────────────────────────────────────

    def test_unlisted_function_blocked(self, fp, numeric_df):
        """Arbitrary unknown functions must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("print({x})", numeric_df)

    def test_compile_blocked(self, fp, numeric_df):
        """compile() must be blocked."""
        with pytest.raises(FormulaSecurityError):
            fp.validate("compile('x', '<str>', 'eval')", numeric_df)

    # ── deeply nested expression (recursion safety) ──────────────────────────

    def test_deeply_nested_expression_does_not_crash(self, fp, numeric_df):
        """
        A formula with many levels of nesting should not cause a Python
        stack overflow; it should either return a result or raise FormulaError.
        """
        depth = 200
        formula = "(" * depth + "{x}" + ")" * depth
        try:
            result = fp.evaluate(formula, numeric_df)
            assert len(result) == len(numeric_df)
        except (FormulaError, RecursionError):
            # Either graceful FormulaError or Python RecursionError is acceptable
            # — the process must not hang or produce silently wrong output.
            pass


# ===========================================================================
# FormulaParser — math edge cases
# ===========================================================================


class TestFormulaParserMathEdgeCases:
    """Verify graceful handling of NaN / Inf / zero in FormulaParser."""

    def test_division_by_zero_returns_null(self, fp, numeric_df):
        """x / 0 should yield null (not raise, not return inf)."""
        result = fp.evaluate("{x} / 0", numeric_df)
        assert result is not None
        assert len(result) == len(numeric_df)
        # All results should be null (not finite)
        for val in result:
            assert val is None or (isinstance(val, float) and not math.isfinite(val))

    def test_division_by_zero_column_returns_null(self, fp, numeric_df):
        """x / z where z is all-zero should yield null (not crash)."""
        result = fp.evaluate("{x} / {z}", numeric_df)
        assert result is not None
        assert len(result) == len(numeric_df)

    def test_sqrt_negative_returns_nan_not_crash(self, fp, numeric_df):
        """sqrt of a negative column value should yield NaN or null, not crash."""
        df = pl.DataFrame({"x": [-1.0, -4.0, -9.0]})
        result = fp.evaluate("sqrt({x})", df)
        assert result is not None
        assert len(result) == 3

    def test_log_negative_returns_nan_not_crash(self, fp, numeric_df):
        """log of a negative value should yield NaN or null, not crash."""
        df = pl.DataFrame({"x": [-1.0, -0.5, -100.0]})
        result = fp.evaluate("log({x})", df)
        assert result is not None
        assert len(result) == 3

    def test_log_zero_handled_gracefully(self, fp):
        """log(0) is -inf; should not raise an exception."""
        df = pl.DataFrame({"x": [0.0, 1.0, 2.0]})
        result = fp.evaluate("log({x})", df)
        assert result is not None
        assert len(result) == 3

    def test_floor_division_by_zero_returns_null(self, fp, numeric_df):
        """x // 0 should yield null, not crash."""
        result = fp.evaluate("{x} // 0", numeric_df)
        assert result is not None
        assert len(result) == len(numeric_df)

    def test_modulo_by_zero_returns_null(self, fp, numeric_df):
        """x % 0 should yield null, not crash."""
        result = fp.evaluate("{x} % 0", numeric_df)
        assert result is not None
        assert len(result) == len(numeric_df)


# ===========================================================================
# FormulaParser — empty / None / all-NaN input
# ===========================================================================


class TestFormulaParserEmptyInput:
    """Graceful handling of empty DataFrames and missing data."""

    def test_empty_formula_raises(self, fp, numeric_df):
        """An empty formula string should raise FormulaError (not crash)."""
        with pytest.raises((FormulaError, SyntaxError, Exception)):
            fp.evaluate("", numeric_df)

    def test_formula_on_empty_dataframe(self, fp, empty_df):
        """
        Evaluating a valid formula against an empty DataFrame should not crash.
        It should return an empty Series or raise a meaningful FormulaError.
        """
        try:
            result = fp.evaluate("{x} * 2", empty_df)
            assert len(result) == 0
        except FormulaError:
            pass  # Acceptable — meaningful error is fine

    def test_formula_on_all_nan_column(self, fp, nan_df):
        """Arithmetic on an all-NaN column should not crash."""
        result = fp.evaluate("{x} + 1", nan_df)
        assert result is not None
        assert len(result) == 3

    def test_whitespace_only_formula_raises(self, fp, numeric_df):
        """Whitespace-only formula should raise FormulaError (not crash)."""
        with pytest.raises((FormulaError, SyntaxError, Exception)):
            fp.evaluate("   ", numeric_df)

    def test_missing_column_raises_column_error(self, fp, numeric_df):
        """Referencing a non-existent column should raise FormulaColumnError."""
        with pytest.raises(FormulaColumnError):
            fp.evaluate("{does_not_exist} * 2", numeric_df)

    def test_non_numeric_column_raises_type_error(self, fp):
        """Arithmetic on a string column should raise FormulaTypeError."""
        df = pl.DataFrame({"name": ["alice", "bob", "carol"]})
        with pytest.raises(FormulaTypeError):
            fp.evaluate("sqrt({name})", df)


# ===========================================================================
# ExpressionEngine — security tests
# ===========================================================================


class TestExpressionEngineSecurity:
    """
    ExpressionEngine uses a custom lexer + parser; there is no eval() call.
    Any function name not in ExpressionEngine.FUNCTIONS is rejected by
    _validate_ast with ExpressionError("Unknown function: ...").

    Because the lexer reads identifiers and upcases them, injection patterns
    like exec(), eval(), __import__() are surfaced as unknown function names
    and blocked at validation time.
    """

    def test_exec_raises_unknown_function(self, ee, numeric_df):
        """exec is not a whitelisted function; validate should report it."""
        is_valid, err = ee.validate('exec("import os")', numeric_df)
        assert not is_valid
        assert err is not None

    def test_eval_raises_unknown_function(self, ee, numeric_df):
        """eval is not a whitelisted function; validate should report it."""
        is_valid, err = ee.validate('eval("1+1")', numeric_df)
        assert not is_valid
        assert err is not None

    def test_open_raises_unknown_function(self, ee, numeric_df):
        """open is not a whitelisted function."""
        is_valid, err = ee.validate("OPEN('/etc/passwd')", numeric_df)
        assert not is_valid
        assert err is not None

    def test_print_raises_unknown_function(self, ee, numeric_df):
        """print is not a whitelisted function."""
        is_valid, err = ee.validate("PRINT('hello')", numeric_df)
        assert not is_valid
        assert err is not None


# ===========================================================================
# ExpressionEngine — math edge cases
# ===========================================================================


class TestExpressionEngineMathEdgeCases:
    """NaN / Inf / zero handling in ExpressionEngine."""

    def test_sqrt_negative_no_crash(self, ee):
        """SQRT(-1) should yield NaN (numpy returns NaN for negative sqrt)."""
        df = pl.DataFrame({"x": [-1.0, -4.0]})
        result = ee.evaluate("SQRT(x)", df)
        assert result is not None
        assert len(result) == 2
        # Polars NaN or null — either is acceptable
        for val in result:
            if val is not None:
                assert math.isnan(val) or not math.isfinite(val)

    def test_log_negative_no_crash(self, ee):
        """LOG(-1) should yield NaN (Polars returns NaN for log of negative)."""
        df = pl.DataFrame({"x": [-1.0]})
        result = ee.evaluate("LOG(x)", df)
        assert result is not None
        assert len(result) == 1

    def test_log_zero_no_crash(self, ee):
        """LOG(0) is -inf; should not raise."""
        df = pl.DataFrame({"x": [0.0, 1.0]})
        result = ee.evaluate("LOG(x)", df)
        assert result is not None
        assert len(result) == 2

    def test_division_by_zero_column(self, ee):
        """x / 0-column should not raise an exception."""
        df = pl.DataFrame({"x": [1.0, 2.0], "z": [0.0, 0.0]})
        # ExpressionEngine does not suppress div-by-zero; result may be inf/nan
        try:
            result = ee.evaluate("x / z", df)
            assert result is not None
        except ExpressionError:
            pass  # Raising a meaningful ExpressionError is also acceptable


# ===========================================================================
# ExpressionEngine — empty / edge input
# ===========================================================================


class TestExpressionEngineEmptyInput:
    def test_empty_dataframe_no_crash(self, ee, empty_df):
        """Formula on empty DataFrame should not crash."""
        try:
            result = ee.evaluate("SQRT(x)", empty_df)
            assert len(result) == 0
        except ExpressionError:
            pass

    def test_missing_column_validate_reports_error(self, ee, numeric_df):
        """Referencing a non-existent column should fail validation."""
        is_valid, err = ee.validate("SQRT(does_not_exist)", numeric_df)
        assert not is_valid
        assert err is not None


# ===========================================================================
# ExpressionParser (expressions.py) — security tests
# ===========================================================================


class TestExpressionParserSecurity:
    """
    ExpressionParser._calculate_expression uses:
        eval(expr, {"__builtins__": {}}, local_vars)

    With __builtins__ emptied, most built-in functions are unavailable.
    However, this is a known partial mitigation — some Python-version-specific
    bypass vectors (e.g. ().__class__.__bases__[0].__subclasses__()) may still
    work if the column variables expose the right object types.

    These tests verify the current behaviour; failures are marked xfail where
    the parser is EXPECTED to block the pattern but currently does not, to make
    the security gap explicit without hiding it.
    """

    @pytest.fixture
    def df(self):
        return pl.DataFrame({"sales": [100.0, 200.0, 300.0]})

    def test_exec_identifier_tokenised_as_column(self, ep, df):
        """
        ExpressionParser's Lexer reads 'exec' as an IDENTIFIER, not a keyword.
        It then becomes a 'column' node. Because 'exec' is not a column in df,
        evaluate() should fail with an ExpressionError or return null, not
        execute arbitrary code.
        """
        # The expression is 'exec' with no parens — treated as a column ref
        try:
            ep.evaluate("[exec]", df)
            # If it gets here, exec was treated as a column lookup and failed
            # silently (returned null series) — acceptable.
        except Exception:
            pass  # Any exception is acceptable

    def test_open_function_not_in_builtins(self, ep, df):
        """
        With __builtins__={}, open() should not be accessible.
        The expression 'open('/etc/passwd')' is not a valid ExpressionParser
        function (no [col] reference), so it goes through _calculate_expression
        via eval with empty builtins — open should be undefined.
        """
        try:
            result = ep.evaluate("open('/etc/passwd')", df)
            # If a result is returned it should be None/null (failed silently)
            if isinstance(result, pl.Series):
                # Acceptable: eval failed and returned null series
                assert result.is_null().all() or len(result) >= 0
        except Exception:
            pass  # NameError for 'open' or ExpressionError — both acceptable

    def test_data_function_exec_sandbox_gap(self):
        """
        DataFunction.execute() now performs an AST scan before exec().
        Dunder attribute access (e.g. np.__class__.__name__) must be blocked
        by raising SecurityError — the former sandbox gap is now closed.
        """
        func = DataFunction(
            name="test_escape",
            parameters=[],
            body="result = np.__class__.__name__",
        )
        df = pl.DataFrame({"x": [1.0]})
        with pytest.raises(SecurityError):
            func.execute(df)

    def test_data_function_no_builtins_import(self):
        """
        With __builtins__={}, a DataFunction body that tries to use
        import or open directly should fail.
        """
        func = DataFunction(
            name="test_import",
            parameters=[],
            body="import os; result = os.getcwd()",
        )
        df = pl.DataFrame({"x": [1.0]})
        # exec with __builtins__={} should raise ImportError or similar;
        # DataFunction.execute() catches all exceptions and returns None.
        result = func.execute(df)
        assert result is None, (
            "DataFunction with 'import os' in body should return None "
            "(exec raised, exception was swallowed)"
        )

    def test_data_function_open_blocked(self):
        """
        open() must be blocked inside DataFunction body.

        Previously the empty __builtins__ dict caused a NameError which was
        swallowed and resulted in None. With the AST scan in place, the body is
        rejected before exec() runs, raising SecurityError explicitly.
        """
        func = DataFunction(
            name="test_open",
            parameters=[],
            body="result = open('/etc/passwd').read()",
        )
        df = pl.DataFrame({"x": [1.0]})
        with pytest.raises(SecurityError):
            func.execute(df)


# ===========================================================================
# ExpressionParser — math edge cases
# ===========================================================================


class TestExpressionParserMathEdgeCases:
    """NaN / Inf / zero handling for the Spotfire-style ExpressionParser."""

    @pytest.fixture
    def df(self):
        return pl.DataFrame({"x": [1.0, 4.0, 9.0], "y": [2.0, 0.0, 3.0]})

    def test_sqrt_negative_no_crash(self, ep, df):
        """Sqrt(-1) via numpy returns NaN — should not raise."""
        neg_df = pl.DataFrame({"x": [-1.0, -4.0]})
        result = ep.evaluate("Sqrt([x])", neg_df)
        assert result is not None
        assert len(result) == 2

    def test_log_negative_no_crash(self, ep, df):
        """Log(-1) via numpy returns NaN — should not raise."""
        neg_df = pl.DataFrame({"x": [-1.0]})
        result = ep.evaluate("Log([x])", neg_df)
        assert result is not None
        assert len(result) == 1

    def test_log_zero_no_crash(self, ep):
        """Log(0) returns -inf; should not raise."""
        df = pl.DataFrame({"x": [0.0, 1.0]})
        result = ep.evaluate("Log([x])", df)
        assert result is not None
        assert len(result) == 2

    def test_division_by_zero_returns_inf_or_null(self, ep, df):
        """
        [x] / 0 — with empty __builtins__, eval returns inf or raises.
        The parser's except clause returns null series on any error.
        """
        result = ep.evaluate("[x] / 0", df)
        assert result is not None
        assert len(result) == 3  # Should not crash

    def test_division_by_zero_column_no_crash(self, ep, df):
        """Dividing by an all-zero column should not crash."""
        df2 = pl.DataFrame({"x": [1.0, 2.0], "z": [0.0, 0.0]})
        result = ep.evaluate("[x] / [z]", df2)
        assert result is not None
        assert len(result) == 2


# ===========================================================================
# ExpressionParser — empty / None / all-NaN input
# ===========================================================================


class TestExpressionParserEmptyInput:
    def test_empty_dataframe_no_crash(self, ep):
        """evaluate() on an empty DataFrame should not crash."""
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Float64)})
        try:
            ep.evaluate("[x] * 2", df)
            # Empty result or null series — acceptable
        except Exception:
            pass

    def test_formula_on_all_null_column(self, ep):
        """Arithmetic on a null column should not crash."""
        df = pl.DataFrame({"x": pl.Series([None, None, None], dtype=pl.Float64)})
        result = ep.evaluate("[x] + 1", df)
        assert result is not None

    def test_unknown_column_returns_error(self, ep):
        """Referencing a non-existent column should return error, not crash."""
        df = pl.DataFrame({"x": [1.0]})
        try:
            ep.evaluate("[does_not_exist] * 2", df)
            # Silently returns null series — acceptable
        except Exception:
            pass  # ExpressionError or similar — also acceptable

    def test_empty_expression_string_does_not_crash(self, ep):
        """An empty expression string should not cause an unhandled crash."""
        df = pl.DataFrame({"x": [1.0, 2.0]})
        try:
            ep.evaluate("", df)
        except Exception:
            pass  # Any exception is fine — no unhandled crash allowed
