"""
FormulaParser — Computed Column formula → Polars Expression pipeline

PRD §3.3, FR-3.1, FR-3.11

Supports:
- Column references: {column_name}
- Arithmetic: +, -, *, /, //, %, **
- Comparison: >, <, >=, <=, ==, !=
- Logic: and, or, not
- Whitelisted functions: abs, round, log, sqrt, pow, clip, min, max,
  mean, std, sum, count, first, last, shift, diff, cumsum, rolling_mean
- Security: blocks eval, exec, import, __, open, os., sys., subprocess
"""

from __future__ import annotations

import ast
import logging
import re
from typing import Any, Dict, Optional, Set, Tuple

import polars as pl

from data_graph_studio.core.formula_exceptions import (
    FormulaError,
    FormulaSecurityError,
    FormulaColumnError,
    FormulaTypeError,
)
from data_graph_studio.core.formula_ast_evaluator import FormulaAstEvaluator, _get_call_name

# Backward-compatible re-exports
__all__ = [
    "FormulaParser",
    "FormulaError",
    "FormulaSecurityError",
    "FormulaColumnError",
    "FormulaTypeError",
]

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Whitelist / Blacklist
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALLOWED_FUNCTIONS: Set[str] = {
    # Math
    'abs', 'round', 'log', 'sqrt', 'pow', 'clip',
    # Aggregate
    'min', 'max', 'mean', 'std', 'sum', 'count',
    # Positional
    'first', 'last',
    # Window / transform
    'shift', 'diff', 'cumsum', 'rolling_mean',
}

BLOCKED_NAMES: Set[str] = {
    'eval', 'exec', 'compile', 'open',
    'getattr', 'setattr', 'delattr',
    'globals', 'locals', 'vars', 'dir',
    'type', 'isinstance', 'issubclass',
    'breakpoint', 'exit', 'quit',
}

BLOCKED_PREFIXES: Tuple[str, ...] = (
    '__', 'import', 'os.', 'sys.', 'subprocess',
)

# Column reference pattern: {column_name}
_COL_REF_RE = re.compile(r'\{([^}]+)\}')

# Polars numeric dtypes
_NUMERIC_DTYPES = (
    pl.Int8, pl.Int16, pl.Int32, pl.Int64,
    pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
    pl.Float32, pl.Float64,
)


class FormulaParser:
    """
    Parse and evaluate user formulas into Polars results.

    Usage:
        parser = FormulaParser()
        series = parser.evaluate("{voltage} * {current}", df)
    """

    def __init__(self) -> None:
        """Initialise FormulaParser with a fresh AST evaluator.

        Output: None
        Invariants: self._ast_eval is a ready FormulaAstEvaluator instance.
        """
        self._ast_eval = FormulaAstEvaluator()

    # ── Public API ────────────────────────────────────────────

    def extract_column_references(self, formula: str) -> Set[str]:
        """Return the set of column names referenced via {name} syntax.

        Input: formula — str, raw formula string
        Output: Set[str] — zero or more column names found between braces
        """
        return set(_COL_REF_RE.findall(formula))

    def validate(self, formula: str, df: pl.DataFrame) -> None:
        """Validate a formula against a DataFrame schema without evaluating it.

        Input: formula — str, raw formula string; df — pl.DataFrame, provides column names
        Output: None
        Raises: FormulaSecurityError — blocked identifier or prefix found;
                FormulaColumnError — referenced column absent from df
        """
        self._security_check(formula)
        # Check column references exist
        refs = self.extract_column_references(formula)
        available = set(df.columns)
        for ref in refs:
            if ref not in available:
                raise FormulaColumnError(
                    f"Column '{ref}' not found. "
                    f"Available columns: {sorted(available)}"
                )

    def evaluate(self, formula: str, df: pl.DataFrame) -> pl.Series:
        """Evaluate a formula string against df and return a pl.Series.

        Input: formula — str, raw formula with {col} references; df — pl.DataFrame, source data
        Output: pl.Series — computed result, length == len(df)
        Raises: FormulaSecurityError — blocked construct detected;
                FormulaColumnError — referenced column not in df;
                FormulaTypeError — non-numeric column used in numeric context;
                FormulaError — syntax error or unsupported expression
        Invariants: division by zero produces null (ERR-3.2); df is not mutated
        """
        logger.debug("formula_parser.evaluate", extra={"formula": str(formula)[:80]})
        self.validate(formula, df)
        prepared = self._prepare_formula(formula, df)
        return self._eval_prepared(prepared, df)

    def evaluate_moving_avg(
        self, column: str, window: int, df: pl.DataFrame
    ) -> pl.Series:
        """Compute rolling mean for a single numeric column (FR-3.2).

        Input: column — str, column name; window — int, positive window size; df — pl.DataFrame
        Output: pl.Series — rolling mean, same length as df, nulls at leading edge
        Raises: ValueError — window <= 0; FormulaTypeError — column is not numeric;
                FormulaColumnError — column not in df
        """
        if window <= 0:
            raise ValueError(f"Window must be positive, got {window}")
        self._check_numeric(column, df)
        return df[column].rolling_mean(window_size=window)

    def evaluate_diff(
        self, column: str, n: int, df: pl.DataFrame
    ) -> pl.Series:
        """Compute element-wise difference (lag n) for a numeric column (FR-3.3).

        Input: column — str, column name; n — int, lag steps; df — pl.DataFrame
        Output: pl.Series — differenced series, first n values are null
        Raises: FormulaTypeError — column is not numeric; FormulaColumnError — column not in df
        """
        self._check_numeric(column, df)
        return df[column].diff(n=n)

    def evaluate_cumsum(self, column: str, df: pl.DataFrame) -> pl.Series:
        """Compute cumulative sum for a single numeric column (FR-3.4).

        Input: column — str, column name; df — pl.DataFrame
        Output: pl.Series — cumulative sum, same length as df
        Raises: FormulaTypeError — column is not numeric; FormulaColumnError — column not in df
        """
        self._check_numeric(column, df)
        return df[column].cum_sum()

    def evaluate_normalize(
        self, column: str, method: str, df: pl.DataFrame
    ) -> pl.Series:
        """Normalize a numeric column using min-max or z-score scaling (FR-3.5).

        Input: column — str, column name; method — str, 'min_max' | 'z_score';
               df — pl.DataFrame
        Output: pl.Series (Float64) — normalized values, same length as df;
                all-zeros if range/std is zero
        Raises: FormulaError — unknown method; FormulaTypeError — column is not numeric;
                FormulaColumnError — column not in df
        """
        self._check_numeric(column, df)
        series = df[column].cast(pl.Float64)

        if method == 'min_max':
            mn = series.min()
            mx = series.max()
            if mn == mx:
                return pl.Series([0.0] * len(series))
            return (series - mn) / (mx - mn)

        elif method == 'z_score':
            mean_val = series.mean()
            std_val = series.std()
            if std_val is None or std_val == 0:
                return pl.Series([0.0] * len(series))
            return (series - mean_val) / std_val

        else:
            raise FormulaError(f"Unknown normalization method: {method}")

    # ── Security ──────────────────────────────────────────────

    def _security_check(self, formula: str) -> None:
        """Enforce FR-3.11 security whitelist/blacklist on raw formula text.

        Input: formula — str, raw formula before column-reference substitution
        Output: None
        Raises: FormulaSecurityError — blocked prefix, dunder identifier,
                or non-whitelisted function call detected
        """
        # Check for blocked prefixes / keywords in raw text
        lower = formula.lower()
        for prefix in BLOCKED_PREFIXES:
            if prefix in lower:
                raise FormulaSecurityError(
                    f"Pattern '{prefix}' is not allowed. "
                    f"Allowed functions: {sorted(ALLOWED_FUNCTIONS)}"
                )

        # Remove column references before AST check
        cleaned = _COL_REF_RE.sub('_placeholder', formula)

        # Try to parse as Python AST for deeper inspection
        try:
            tree = ast.parse(cleaned, mode='eval')
        except SyntaxError:
            # If it doesn't parse as Python, let the evaluator handle it
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = _get_call_name(node)
                if func_name is not None:
                    if func_name in BLOCKED_NAMES:
                        raise FormulaSecurityError(
                            f"Function '{func_name}' is not allowed. "
                            f"Allowed functions: {sorted(ALLOWED_FUNCTIONS)}"
                        )
                    if func_name.startswith('__'):
                        raise FormulaSecurityError(
                            f"Identifier '{func_name}' is not allowed (dunder). "
                            f"Allowed functions: {sorted(ALLOWED_FUNCTIONS)}"
                        )
                    if func_name not in ALLOWED_FUNCTIONS and func_name != '_placeholder':
                        raise FormulaSecurityError(
                            f"Function '{func_name}' is not allowed. "
                            f"Allowed functions: {sorted(ALLOWED_FUNCTIONS)}"
                        )
            elif isinstance(node, ast.Name):
                name = node.id
                if name.startswith('__'):
                    raise FormulaSecurityError(
                        f"Identifier '{name}' is not allowed (dunder). "
                        f"Allowed functions: {sorted(ALLOWED_FUNCTIONS)}"
                    )
                if name in BLOCKED_NAMES:
                    raise FormulaSecurityError(
                        f"Identifier '{name}' is not allowed. "
                        f"Allowed functions: {sorted(ALLOWED_FUNCTIONS)}"
                    )

    # ── Preparation ───────────────────────────────────────────

    def _prepare_formula(self, formula: str, df: pl.DataFrame) -> str:
        """Validate column references exist in df and return the formula unchanged.

        Input: formula — str, raw formula string; df — pl.DataFrame, reference schema
        Output: str — same formula string (column existence confirmed)
        Raises: FormulaColumnError — any {col} reference is absent from df.columns
        """
        refs = self.extract_column_references(formula)
        available = set(df.columns)

        for ref in refs:
            if ref not in available:
                raise FormulaColumnError(
                    f"Column '{ref}' not found. "
                    f"Available columns: {sorted(available)}"
                )

        return formula

    # ── Type Checking ─────────────────────────────────────────

    def _check_numeric(self, column: str, df: pl.DataFrame) -> None:
        """Assert that a column exists in df and has a numeric dtype.

        Input: column — str, column name; df — pl.DataFrame
        Output: None
        Raises: FormulaColumnError — column not in df;
                FormulaTypeError — column dtype not in _NUMERIC_DTYPES
        """
        if column not in df.columns:
            raise FormulaColumnError(
                f"Column '{column}' not found. "
                f"Available columns: {sorted(df.columns)}"
            )
        dtype = df[column].dtype
        if dtype not in _NUMERIC_DTYPES:
            raise FormulaTypeError(
                f"Type error: column '{column}' is {dtype}, expected numeric."
            )

    def _check_numeric_refs(self, formula: str, df: pl.DataFrame) -> None:
        """Check that every {col} reference in formula resolves to a numeric column.

        Input: formula — str, formula containing zero or more {col} tokens; df — pl.DataFrame
        Output: None
        Raises: FormulaTypeError — any referenced column has a non-numeric dtype
        """
        refs = self.extract_column_references(formula)
        for ref in refs:
            if ref in df.columns:
                dtype = df[ref].dtype
                if dtype not in _NUMERIC_DTYPES:
                    raise FormulaTypeError(
                        f"Type error: column '{ref}' is {dtype}, expected numeric."
                    )

    # ── Evaluation Engine ─────────────────────────────────────

    def _eval_prepared(self, formula: str, df: pl.DataFrame) -> pl.Series:
        """Dispatch a validated formula to the appropriate evaluation path.

        Input: formula — str, security-checked formula with {col} refs intact;
               df — pl.DataFrame
        Output: pl.Series — computed result, length == len(df)
        Invariants: tries special-function patterns first; falls back to AST evaluator
        """
        stripped = formula.strip()
        result = self._eval_special_function(stripped, df)
        if result is not None:
            return result
        return self._eval_general_expression(stripped, df)

    def _eval_special_function(
        self, stripped: str, df: pl.DataFrame
    ) -> "Optional[pl.Series]":
        """Try to match and evaluate a named special-function form.

        Returns the computed Series, or None if no pattern matches.
        """
        # rolling_mean({col}, window)
        m = re.match(r'^rolling_mean\(\s*\{([^}]+)\}\s*,\s*(\d+)\s*\)$', stripped)
        if m:
            col, window = m.group(1), int(m.group(2))
            if window <= 0:
                raise ValueError(f"Window must be positive, got {window}")
            self._check_numeric(col, df)
            return df[col].rolling_mean(window_size=window)

        # diff({col}) or diff({col}, n)
        m = re.match(r'^diff\(\s*\{([^}]+)\}\s*(?:,\s*(\d+)\s*)?\)$', stripped)
        if m:
            col = m.group(1)
            n = int(m.group(2)) if m.group(2) else 1
            self._check_numeric(col, df)
            return df[col].diff(n=n)

        # cumsum({col})
        m = re.match(r'^cumsum\(\s*\{([^}]+)\}\s*\)$', stripped)
        if m:
            col = m.group(1)
            self._check_numeric(col, df)
            return df[col].cum_sum()

        # shift({col}, n)
        m = re.match(r'^shift\(\s*\{([^}]+)\}\s*,\s*(-?\d+)\s*\)$', stripped)
        if m:
            col, n = m.group(1), int(m.group(2))
            self._check_numeric(col, df)
            return df[col].shift(n)

        # Aggregate functions: sum/mean/std/count/first/last/min/max({col})
        for fn in ('sum', 'mean', 'std', 'count', 'first', 'last', 'min', 'max'):
            m = re.match(rf'^{fn}\(\s*\{{([^}}]+)\}}\s*\)$', stripped)
            if m:
                col = m.group(1)
                self._check_numeric(col, df)
                return self._eval_aggregate(fn, col, df)

        return self._eval_math_special_function(stripped, df)

    def _eval_math_special_function(
        self, stripped: str, df: pl.DataFrame
    ) -> "Optional[pl.Series]":
        """Match single-column math special forms (clip, abs, round, sqrt, log, pow, min2, max2).

        Returns the computed Series, or None if no pattern matches.
        """
        # clip({col}, lo, hi)
        m = re.match(
            r'^clip\(\s*\{([^}]+)\}\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)$', stripped
        )
        if m:
            col = m.group(1)
            self._check_numeric(col, df)
            return df[col].clip(float(m.group(2)), float(m.group(3)))

        # abs({col})
        m = re.match(r'^abs\(\s*\{([^}]+)\}\s*\)$', stripped)
        if m:
            col = m.group(1)
            self._check_numeric(col, df)
            return df[col].abs()

        # round({col}, decimals)
        m = re.match(r'^round\(\s*\{([^}]+)\}\s*,\s*(\d+)\s*\)$', stripped)
        if m:
            col, decimals = m.group(1), int(m.group(2))
            self._check_numeric(col, df)
            return df[col].round(decimals)

        # sqrt({col})
        m = re.match(r'^sqrt\(\s*\{([^}]+)\}\s*\)$', stripped)
        if m:
            col = m.group(1)
            self._check_numeric(col, df)
            return df[col].sqrt()

        # log({col})
        m = re.match(r'^log\(\s*\{([^}]+)\}\s*\)$', stripped)
        if m:
            col = m.group(1)
            self._check_numeric(col, df)
            return df[col].log()

        # pow({col}, exp)
        m = re.match(r'^pow\(\s*\{([^}]+)\}\s*,\s*([^)]+)\s*\)$', stripped)
        if m:
            col = m.group(1)
            self._check_numeric(col, df)
            return df[col].pow(float(m.group(2)))

        # min({col1}, {col2})  — element-wise
        m = re.match(r'^min\(\s*\{([^}]+)\}\s*,\s*\{([^}]+)\}\s*\)$', stripped)
        if m:
            c1, c2 = m.group(1), m.group(2)
            self._check_numeric(c1, df)
            self._check_numeric(c2, df)
            out = df.select(pl.min_horizontal(c1, c2))
            return out[out.columns[0]]

        # max({col1}, {col2})  — element-wise
        m = re.match(r'^max\(\s*\{([^}]+)\}\s*,\s*\{([^}]+)\}\s*\)$', stripped)
        if m:
            c1, c2 = m.group(1), m.group(2)
            self._check_numeric(c1, df)
            self._check_numeric(c2, df)
            out = df.select(pl.max_horizontal(c1, c2))
            return out[out.columns[0]]

        return None

    def _eval_aggregate(self, fn: str, col: str, df: pl.DataFrame) -> pl.Series:
        """Evaluate an aggregate function and broadcast the scalar result to len(df).

        Input: fn — str, one of sum/mean/std/count/first/last/min/max;
               col — str, numeric column name; df — pl.DataFrame
        Output: pl.Series — constant series of length len(df) containing the aggregate value
        """
        series = df[col]
        mapping = {
            'sum': series.sum,
            'mean': series.mean,
            'std': series.std,
            'count': series.count,
            'first': lambda: series[0] if len(series) > 0 else None,
            'last': lambda: series[-1] if len(series) > 0 else None,
            'min': series.min,
            'max': series.max,
        }
        val = mapping[fn]()
        return pl.Series([val] * len(df))

    def _eval_general_expression(self, formula: str, df: pl.DataFrame) -> pl.Series:
        """Evaluate a general arithmetic, comparison, or logic expression via AST.

        Input: formula — str, formula with {col} references; df — pl.DataFrame
        Output: pl.Series — computed result, length == len(df)
        Raises: FormulaError — Python SyntaxError parsing the expression;
                FormulaTypeError — non-numeric column in arithmetic context
        Invariants: {col} tokens are replaced with safe placeholder variable names
                    before AST parsing; df is not mutated
        """
        # Type-check numeric columns used in math context
        self._check_numeric_refs(formula, df)

        # Build column substitution
        refs = self.extract_column_references(formula)
        expr = formula

        # Replace {col} with safe placeholder variable names
        col_map: Dict[str, str] = {}
        for ref in refs:
            safe = f'__col_{ref.replace(" ", "_").replace("-", "_")}__'
            col_map[safe] = ref
            expr = expr.replace(f'{{{ref}}}', safe)

        # Replace ** before we parse (Python AST handles it natively)
        # Replace // for floor division

        try:
            tree = ast.parse(expr, mode='eval')
        except SyntaxError as e:
            logger.warning("formula_parser.eval_general.syntax_error", extra={"error": str(e), "formula": str(formula)[:50]})
            raise FormulaError(f"Syntax error in formula: {e}")

        # Evaluate AST with Polars series — delegate to FormulaAstEvaluator
        result = self._ast_eval.eval_node(tree.body, df, col_map)

        if isinstance(result, pl.Series):
            return result
        elif isinstance(result, (int, float)):
            return pl.Series([result] * len(df))
        else:
            return pl.Series([result] * len(df))
