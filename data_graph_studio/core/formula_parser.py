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

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Error hierarchy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class FormulaError(Exception):
    """Base error for formula operations."""
    pass


class FormulaSecurityError(FormulaError):
    """Raised when a disallowed function / pattern is detected (FR-3.11)."""
    pass


class FormulaColumnError(FormulaError):
    """Raised when a referenced column does not exist (ERR-3.1)."""
    pass


class FormulaTypeError(FormulaError):
    """Raised on type mismatch — e.g. math on string column (ERR-3.3)."""
    pass


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
        pass

    # ── Public API ────────────────────────────────────────────

    def extract_column_references(self, formula: str) -> Set[str]:
        """Return the set of column names referenced via {name}."""
        return set(_COL_REF_RE.findall(formula))

    def validate(self, formula: str, df: pl.DataFrame) -> None:
        """
        Validate a formula against a DataFrame schema.

        Raises FormulaSecurityError, FormulaColumnError, or FormulaTypeError.
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
        """
        Evaluate a formula string against *df* and return a pl.Series.

        Division by zero produces null (ERR-3.2).
        Type mismatches raise FormulaTypeError (ERR-3.3).
        """
        logger.debug("formula_parser.evaluate", extra={"formula": str(formula)[:80]})
        self.validate(formula, df)
        prepared = self._prepare_formula(formula, df)
        return self._eval_prepared(prepared, df)

    def evaluate_moving_avg(
        self, column: str, window: int, df: pl.DataFrame
    ) -> pl.Series:
        """Convenience: rolling_mean for a single column (FR-3.2)."""
        if window <= 0:
            raise ValueError(f"Window must be positive, got {window}")
        self._check_numeric(column, df)
        return df[column].rolling_mean(window_size=window)

    def evaluate_diff(
        self, column: str, n: int, df: pl.DataFrame
    ) -> pl.Series:
        """Convenience: diff for a single column (FR-3.3)."""
        self._check_numeric(column, df)
        return df[column].diff(n=n)

    def evaluate_cumsum(self, column: str, df: pl.DataFrame) -> pl.Series:
        """Convenience: cumsum for a single column (FR-3.4)."""
        self._check_numeric(column, df)
        return df[column].cum_sum()

    def evaluate_normalize(
        self, column: str, method: str, df: pl.DataFrame
    ) -> pl.Series:
        """
        Normalize a column (FR-3.5).

        method: 'min_max' | 'z_score'
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
        """FR-3.11 whitelist / blacklist enforcement."""
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
                func_name = self._get_call_name(node)
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

    @staticmethod
    def _get_call_name(node: ast.Call) -> Optional[str]:
        """Extract function name from an ast.Call node."""
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    # ── Preparation ───────────────────────────────────────────

    def _prepare_formula(self, formula: str, df: pl.DataFrame) -> str:
        """
        Replace {col} references and validate types.

        Returns a cleaned formula string ready for _eval_prepared.
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
        """Raise FormulaTypeError if column is not numeric."""
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
        """Check that all column refs in formula are numeric (for math ops)."""
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
        """
        Evaluate the formula by interpreting it with Polars operations.

        Strategy:
        1. Handle special function forms (rolling_mean, diff, cumsum, etc.)
        2. For general expressions, build a Polars expression via AST.
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
        """Evaluate an aggregate function, returning a scalar broadcast to len(df)."""
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
        """
        Evaluate a general arithmetic / comparison / logic expression.

        Replaces {col} with Polars column data and evaluates via AST.
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

        # Evaluate AST with Polars series
        result = self._eval_ast_node(tree.body, df, col_map)

        if isinstance(result, pl.Series):
            return result
        elif isinstance(result, (int, float)):
            return pl.Series([result] * len(df))
        else:
            return pl.Series([result] * len(df))

    def _eval_ast_node(
        self,
        node: ast.AST,
        df: pl.DataFrame,
        col_map: Dict[str, str],
    ) -> Any:
        """Recursively evaluate an AST node into a pl.Series or scalar."""

        if isinstance(node, ast.Expression):
            return self._eval_ast_node(node.body, df, col_map)

        # ── Numeric literal ───────────────────────────────────
        if isinstance(node, ast.Constant):
            return node.value

        # ── Name (column reference or constant) ───────────────
        if isinstance(node, ast.Name):
            name = node.id
            if name in col_map:
                col_name = col_map[name]
                return df[col_name].cast(pl.Float64)
            # Boolean constants
            if name == 'True':
                return True
            if name == 'False':
                return False
            raise FormulaError(f"Unknown identifier: {name}")

        # ── Unary operator ────────────────────────────────────
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_ast_node(node.operand, df, col_map)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return operand
            if isinstance(node.op, ast.Not):
                return ~operand if isinstance(operand, pl.Series) else not operand
            raise FormulaError(f"Unsupported unary op: {type(node.op).__name__}")

        # ── Binary operator ───────────────────────────────────
        if isinstance(node, ast.BinOp):
            left = self._eval_ast_node(node.left, df, col_map)
            right = self._eval_ast_node(node.right, df, col_map)
            return self._apply_binop(node.op, left, right, df)

        # ── Comparison ────────────────────────────────────────
        if isinstance(node, ast.Compare):
            left = self._eval_ast_node(node.left, df, col_map)
            results = []
            current = left
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_ast_node(comparator, df, col_map)
                results.append(self._apply_cmpop(op, current, right, df))
                current = right
            # Chain comparisons with AND
            result = results[0]
            for r in results[1:]:
                result = result & r
            return result

        # ── Boolean operator ──────────────────────────────────
        if isinstance(node, ast.BoolOp):
            values = [self._eval_ast_node(v, df, col_map) for v in node.values]
            if isinstance(node.op, ast.And):
                result = values[0]
                for v in values[1:]:
                    result = result & v
                return result
            if isinstance(node.op, ast.Or):
                result = values[0]
                for v in values[1:]:
                    result = result | v
                return result

        # ── Call (function) ───────────────────────────────────
        if isinstance(node, ast.Call):
            return self._eval_call(node, df, col_map)

        raise FormulaError(f"Unsupported expression: {ast.dump(node)}")

    def _apply_binop(
        self, op: ast.operator, left: Any, right: Any, df: pl.DataFrame
    ) -> Any:
        """Apply a binary operator."""
        # Ensure at least one side is a Series for proper broadcasting
        left = self._to_series(left, df)
        right = self._to_series(right, df)

        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            # Division by zero → null (ERR-3.2)
            mask = right == 0
            result = left / right
            if isinstance(mask, pl.Series) and mask.any():
                # Replace inf/-inf with null
                result = result.to_frame("__tmp__").select(
                    pl.when(pl.col("__tmp__").is_infinite())
                    .then(None)
                    .otherwise(pl.col("__tmp__"))
                    .alias("__tmp__")
                )["__tmp__"]
            return result
        if isinstance(op, ast.FloorDiv):
            # Floor division by zero → null
            mask = right == 0
            # Polars doesn't have // directly for Series, emulate
            result = (left / right).floor()
            if isinstance(mask, pl.Series) and mask.any():
                result = result.to_frame("__tmp__").select(
                    pl.when(pl.col("__tmp__").is_infinite() | pl.col("__tmp__").is_nan())
                    .then(None)
                    .otherwise(pl.col("__tmp__"))
                    .alias("__tmp__")
                )["__tmp__"]
            return result
        if isinstance(op, ast.Mod):
            # Mod by zero → null
            mask = right == 0
            # Use a safe approach: compute mod, replace where divisor was 0
            if isinstance(mask, pl.Series) and mask.any():
                # Replace zeros with 1 to avoid crash, then mask result
                safe_right = right.to_frame("__r__").select(
                    pl.when(pl.col("__r__") == 0).then(1).otherwise(pl.col("__r__")).alias("__r__")
                )["__r__"]
                result = left % safe_right
                result = result.to_frame("__tmp__").with_columns(
                    pl.when(pl.Series("__mask__", mask)).then(None).otherwise(pl.col("__tmp__")).alias("__tmp__")
                )["__tmp__"]
                return result
            return left % right
        if isinstance(op, ast.Pow):
            return left.pow(right)
        if isinstance(op, ast.BitAnd):
            return left & right
        if isinstance(op, ast.BitOr):
            return left | right

        raise FormulaError(f"Unsupported binary operator: {type(op).__name__}")

    def _apply_cmpop(
        self, op: ast.cmpop, left: Any, right: Any, df: pl.DataFrame
    ) -> Any:
        """Apply a comparison operator."""
        left = self._to_series(left, df)
        right = self._to_series(right, df)

        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right

        raise FormulaError(f"Unsupported comparison: {type(op).__name__}")

    def _eval_call(
        self,
        node: ast.Call,
        df: pl.DataFrame,
        col_map: Dict[str, str],
    ) -> Any:
        """Evaluate a function call node."""
        func_name = self._get_call_name(node)
        if func_name is None:
            raise FormulaError("Complex function calls not supported")

        args = [self._eval_ast_node(a, df, col_map) for a in node.args]

        if func_name == 'abs':
            return self._to_series(args[0], df).abs()
        if func_name == 'round':
            decimals = int(args[1]) if len(args) > 1 else 0
            return self._to_series(args[0], df).round(decimals)
        if func_name == 'sqrt':
            return self._to_series(args[0], df).sqrt()
        if func_name == 'log':
            return self._to_series(args[0], df).log()
        if func_name == 'pow':
            return self._to_series(args[0], df).pow(args[1])
        if func_name == 'clip':
            lo = float(args[1]) if len(args) > 1 else float('-inf')
            hi = float(args[2]) if len(args) > 2 else float('inf')
            return self._to_series(args[0], df).clip(lo, hi)
        if func_name in ('min', 'max'):
            if len(args) == 2 and isinstance(args[0], pl.Series) and isinstance(args[1], pl.Series):
                tmp = pl.DataFrame({'__a': args[0], '__b': args[1]})
                if func_name == 'min':
                    return tmp.select(pl.min_horizontal('__a', '__b'))['__a']
                else:
                    return tmp.select(pl.max_horizontal('__a', '__b'))['__a']
            # single arg aggregate
            s = self._to_series(args[0], df)
            val = s.min() if func_name == 'min' else s.max()
            return pl.Series([val] * len(df))
        if func_name in ('mean', 'std', 'sum', 'count', 'first', 'last'):
            s = self._to_series(args[0], df)
            fn_map = {
                'mean': s.mean, 'std': s.std, 'sum': s.sum, 'count': s.count,
                'first': lambda: s[0] if len(s) > 0 else None,
                'last': lambda: s[-1] if len(s) > 0 else None,
            }
            val = fn_map[func_name]()
            return pl.Series([val] * len(df))
        if func_name == 'shift':
            n = int(args[1]) if len(args) > 1 else 1
            return self._to_series(args[0], df).shift(n)
        if func_name == 'diff':
            n = int(args[1]) if len(args) > 1 else 1
            return self._to_series(args[0], df).diff(n=n)
        if func_name == 'cumsum':
            return self._to_series(args[0], df).cum_sum()
        if func_name == 'rolling_mean':
            window = int(args[1]) if len(args) > 1 else 3
            if window <= 0:
                raise ValueError(f"Window must be positive, got {window}")
            return self._to_series(args[0], df).rolling_mean(window_size=window)

        raise FormulaError(f"Unknown function: {func_name}")

    def _to_series(self, val: Any, df: pl.DataFrame) -> pl.Series:
        """Ensure a value is a pl.Series (broadcast scalars)."""
        if isinstance(val, pl.Series):
            return val
        if isinstance(val, bool):
            return pl.Series([val] * len(df))
        if isinstance(val, (int, float)):
            return pl.Series([float(val)] * len(df))
        return pl.Series([val] * len(df))
