"""
FormulaAstEvaluator — AST evaluation helpers extracted from formula_parser.py

Handles _eval_ast_node, _apply_binop, _apply_cmpop, _eval_call, _to_series.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, Optional

import polars as pl

from data_graph_studio.core.formula_exceptions import FormulaError


class FormulaAstEvaluator:
    """Stateless helper that evaluates Python AST nodes into Polars Series.

    Input: node — ast.AST, the root of a parsed formula expression tree
    Input: df — pl.DataFrame, provides column data for name lookups
    Input: col_map — Dict[str, str], maps formula identifiers to DataFrame column names
    Output: pl.Series or scalar value produced by evaluating the expression
    Raises: FormulaError — for unknown identifiers, unsupported operators, or unknown functions
    Invariants: df is not modified; col_map keys must match column names in df
    """

    # ── Public entry point ────────────────────────────────────

    def eval_node(
        self,
        node: ast.AST,
        df: pl.DataFrame,
        col_map: Dict[str, str],
    ) -> Any:
        """Evaluate an AST node into a Polars Series or scalar.

        Input: node — ast.AST, root of the expression tree
        Input: df — pl.DataFrame, source data for column references
        Input: col_map — Dict[str, str], identifier-to-column-name mapping
        Output: pl.Series or Python scalar result of the expression
        Raises: FormulaError — if the node type or identifier is unsupported
        """
        return self._eval_ast_node(node, df, col_map)

    # ── Internal AST evaluation ───────────────────────────────

    def _eval_ast_node(
        self,
        node: ast.AST,
        df: pl.DataFrame,
        col_map: Dict[str, str],
    ) -> Any:
        """Recursively dispatch an AST node to the appropriate evaluation branch.

        Input: node — ast.AST, one of Expression/Constant/Name/UnaryOp/BinOp/Compare/BoolOp/Call
        Input: df — pl.DataFrame, source data for column lookups
        Input: col_map — Dict[str, str], identifier-to-column mapping
        Output: pl.Series or scalar produced by the node
        Raises: FormulaError — for unsupported node types, unknown identifiers, or unsupported operators
        Invariants: chained comparisons are folded with element-wise AND
        """

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
        """Apply an arithmetic or bitwise binary operator element-wise.

        Input: op — ast.operator, one of Add/Sub/Mult/Div/FloorDiv/Mod/Pow/BitAnd/BitOr
        Input: left — pl.Series or scalar, left operand
        Input: right — pl.Series or scalar, right operand
        Input: df — pl.DataFrame, used for scalar broadcasting via _to_series
        Output: pl.Series result of the operation
        Raises: FormulaError — for unsupported operator types
        Invariants: division and modulo by zero produce null (not inf/nan)
        """
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
        """Apply a comparison operator element-wise, returning a boolean Series.

        Input: op — ast.cmpop, one of Gt/Lt/GtE/LtE/Eq/NotEq
        Input: left — pl.Series or scalar, left operand
        Input: right — pl.Series or scalar, right operand
        Input: df — pl.DataFrame, used for scalar broadcasting
        Output: pl.Series of bool, element-wise comparison result
        Raises: FormulaError — for unsupported comparison operators
        """
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
        """Evaluate a function-call AST node against supported formula functions.

        Input: node — ast.Call, the call node with func and args
        Input: df — pl.DataFrame, source data for column references
        Input: col_map — Dict[str, str], identifier-to-column mapping
        Output: pl.Series result of the function applied to its arguments
        Raises: FormulaError — for complex call expressions or unknown function names
        Raises: ValueError — if rolling_mean window is not positive
        Invariants: aggregate functions (mean/std/sum/count/first/last) broadcast
                    their scalar result to a constant Series of length len(df)
        """
        func_name = _get_call_name(node)
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
        """Coerce a scalar or Series value to a pl.Series of length len(df).

        Input: val — Any, either a pl.Series or a Python bool/int/float/other scalar
        Input: df — pl.DataFrame, used only to determine the target length for broadcasting
        Output: pl.Series of length len(df)
        Invariants: existing Series are returned as-is; scalars are broadcast to len(df) elements
        """
        if isinstance(val, pl.Series):
            return val
        if isinstance(val, bool):
            return pl.Series([val] * len(df))
        if isinstance(val, (int, float)):
            return pl.Series([float(val)] * len(df))
        return pl.Series([val] * len(df))


def _get_call_name(node: ast.Call) -> Optional[str]:
    """Extract the function name string from an ast.Call node.

    Input: node — ast.Call, the call node to inspect
    Output: str function name if the callee is a plain Name or Attribute; None otherwise
    """
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
