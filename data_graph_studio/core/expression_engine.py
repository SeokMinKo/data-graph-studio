"""
Expression Engine - 계산 필드를 위한 수식 엔진
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import polars as pl

from .metrics import get_metrics
from data_graph_studio.core.expression_lexer import (
    ExpressionError,
    TokenType,
    Token,
    Lexer,
    Parser,
)

# Backward-compatible re-exports
__all__ = ["ExpressionEngine", "ExpressionError", "TokenType", "Token", "Lexer", "Parser"]

logger = logging.getLogger(__name__)


class ExpressionEngine:
    """Evaluate expression strings against a Polars DataFrame.

    Supports arithmetic, comparison, and a curated set of built-in functions
    (math, string, conditional, datetime). Uses Lexer/Parser from
    expression_lexer.py to produce an AST, then walks it recursively.
    """

    # 지원 함수 목록
    FUNCTIONS = {
        # 수학 함수
        'ROUND', 'FLOOR', 'CEIL', 'ABS', 'SQRT', 'POWER', 'LOG', 'LOG10', 'EXP',
        'SIN', 'COS', 'TAN', 'MIN', 'MAX',
        # 문자열 함수
        'CONCAT', 'UPPER', 'LOWER', 'LEN', 'LEFT', 'RIGHT', 'TRIM', 'REPLACE',
        'SUBSTRING', 'CONTAINS',
        # 조건 함수
        'IF', 'COALESCE', 'ISNULL', 'IFNULL', 'CASE',
        # 날짜 함수
        'DATE_DIFF', 'YEAR', 'MONTH', 'DAY', 'WEEKDAY', 'HOUR', 'MINUTE', 'SECOND',
        'DATE_ADD', 'DATE_SUB', 'NOW', 'TODAY',
    }

    def __init__(self):
        """Initialize the ExpressionEngine.

        Output: None
        Invariants: stateless — no instance variables; all evaluation state is per-call
        """

    def evaluate(self, expression: str, df: pl.DataFrame) -> pl.Series:
        """Tokenize, parse, and evaluate an expression string against a DataFrame.

        Input:
            expression — str, the formula to evaluate (e.g., "ROUND([col] / 2, 1)").
            df — pl.DataFrame, source data; column names are referenced by identifier tokens.
        Output: pl.Series — one element per row in df; dtype depends on the expression result.
        Raises: ExpressionError — on unknown column, unknown function, or malformed expression.
        Invariants:
            - Increments the "expression.evaluated" metrics counter on each call.
            - len(result) == len(df) for well-formed expressions.
        """
        logger.debug("expression_engine.evaluate", extra={"expr": str(expression)[:80]})
        get_metrics().increment("expression.evaluated")
        with get_metrics().timed_operation("expression.evaluate"):
            # 토큰화
            lexer = Lexer(expression)
            tokens = lexer.tokenize()

            # 파싱
            parser = Parser(tokens)
            ast = parser.parse()

            # 평가
            return self._evaluate_ast(ast, df)

    def _evaluate_ast(self, node: Dict, df: pl.DataFrame) -> pl.Series:
        """Recursively evaluate an AST node against df and return a Series.

        Input: node — Dict with 'type' key; df — source DataFrame.
        Output: pl.Series — result for the subtree rooted at node.
        Raises: ExpressionError — on unknown column, unknown function, or unknown node type.
        """
        node_type = node['type']
        n_rows = len(df) if len(df) > 0 else 1

        if node_type == 'number':
            return pl.Series([node['value']] * n_rows)

        if node_type == 'string':
            return pl.Series([node['value']] * n_rows)

        if node_type == 'column':
            name = node['name']
            if name not in df.columns:
                raise ExpressionError(f"Column '{name}' not found")
            return df[name]

        if node_type == 'unary':
            operand = self._evaluate_ast(node['operand'], df)
            if node['op'] == '-':
                return -operand
            return operand

        if node_type == 'binary':
            left = self._evaluate_ast(node['left'], df)
            right = self._evaluate_ast(node['right'], df)

            op = node['op']
            if op == '+':
                return left + right
            elif op == '-':
                return left - right
            elif op == '*':
                return left * right
            elif op == '/':
                return left / right
            elif op == '%':
                return left % right
            elif op == '^':
                return left.pow(right)

        if node_type == 'comparison':
            left = self._evaluate_ast(node['left'], df)
            right = self._evaluate_ast(node['right'], df)

            op = node['op']
            if op == '==':
                return left == right
            elif op == '!=':
                return left != right
            elif op == '>':
                return left > right
            elif op == '<':
                return left < right
            elif op == '>=':
                return left >= right
            elif op == '<=':
                return left <= right

        if node_type == 'function':
            return self._evaluate_function(node, df)

        raise ExpressionError(f"Unknown node type: {node_type}")

    @staticmethod
    def _get_scalar(arg: Any, default: Any = None) -> Any:
        """Extract a scalar value from a Series or return the value as-is."""
        if isinstance(arg, pl.Series):
            return arg[0] if len(arg) > 0 else default
        return arg

    def _evaluate_function(self, node: Dict, df: pl.DataFrame) -> pl.Series:
        """Dispatch a function AST node to the appropriate handler group.

        Input: node — Dict with 'name' (uppercase str) and 'args' (List[Dict]).
            df — source DataFrame for argument evaluation.
        Output: pl.Series — result of the named function applied to evaluated args.
        Raises: ExpressionError — when the function name is not recognized by any handler.
        """
        func_name = node['name']
        args = [self._evaluate_ast(arg, df) for arg in node['args']]

        result = self._eval_math_function(func_name, args)
        if result is not None:
            return result

        result = self._eval_string_function(func_name, args)
        if result is not None:
            return result

        result = self._eval_conditional_function(func_name, args, df)
        if result is not None:
            return result

        result = self._eval_datetime_function(func_name, args)
        if result is not None:
            return result

        raise ExpressionError(f"Unknown function: {func_name}")

    def _eval_math_function(self, func_name: str, args: list) -> Optional[pl.Series]:
        """Evaluate math/numeric functions. Returns None if func_name not handled."""
        gs = self._get_scalar
        if func_name == 'ROUND':
            decimals = int(gs(args[1], 0)) if len(args) > 1 else 0
            return args[0].round(decimals)
        if func_name == 'FLOOR':
            return args[0].floor()
        if func_name == 'CEIL':
            return args[0].ceil()
        if func_name == 'ABS':
            return args[0].abs()
        if func_name == 'SQRT':
            return args[0].sqrt()
        if func_name == 'POWER':
            base = args[0]
            exp_val = gs(args[1])
            if isinstance(base, pl.Series) and base.n_unique() == 1:
                return pl.Series([base[0] ** exp_val] * len(base))
            return base.pow(exp_val)
        if func_name == 'LOG':
            return args[0].log()
        if func_name == 'LOG10':
            return args[0].log() / math.log(10)
        if func_name == 'EXP':
            return args[0].exp()
        if func_name in ('SIN', 'COS', 'TAN'):
            import numpy as np
            trig = {'SIN': np.sin, 'COS': np.cos, 'TAN': np.tan}[func_name]
            return pl.Series(trig(args[0].to_numpy()))
        if func_name == 'MIN':
            if len(args) == 1:
                return pl.Series([args[0].min()] * len(args[0]))
            result = args[0]
            for arg in args[1:]:
                result = pl.DataFrame({"a": result, "b": arg}).select(pl.min_horizontal("a", "b"))["a"]
            return result
        if func_name == 'MAX':
            if len(args) == 1:
                return pl.Series([args[0].max()] * len(args[0]))
            result = args[0]
            for arg in args[1:]:
                result = pl.DataFrame({"a": result, "b": arg}).select(pl.max_horizontal("a", "b"))["a"]
            return result
        return None

    def _eval_string_function(self, func_name: str, args: list) -> Optional[pl.Series]:
        """Evaluate string functions. Returns None if func_name not handled."""
        gs = self._get_scalar
        if func_name == 'CONCAT':
            result = args[0].cast(pl.Utf8)
            for arg in args[1:]:
                result = result + (arg.cast(pl.Utf8) if isinstance(arg, pl.Series) else str(arg))
            return result
        if func_name == 'UPPER':
            return args[0].str.to_uppercase()
        if func_name == 'LOWER':
            return args[0].str.to_lowercase()
        if func_name == 'LEN':
            return args[0].str.len_chars()
        if func_name == 'LEFT':
            return args[0].str.head(int(gs(args[1])))
        if func_name == 'RIGHT':
            return args[0].str.tail(int(gs(args[1])))
        if func_name == 'TRIM':
            return args[0].str.strip_chars()
        if func_name == 'REPLACE':
            return args[0].str.replace_all(str(gs(args[1])), str(gs(args[2])))
        if func_name == 'CONTAINS':
            return args[0].cast(pl.Utf8).str.contains(str(gs(args[1])))
        if func_name == 'SUBSTRING':
            start = int(gs(args[1])) - 1  # Convert 1-based to 0-based
            length = int(gs(args[2])) if len(args) > 2 else None
            return args[0].str.slice(start, length) if length is not None else args[0].str.slice(start)
        return None

    def _eval_conditional_function(
        self, func_name: str, args: list, df: pl.DataFrame
    ) -> Optional[pl.Series]:
        """Evaluate conditional/null-handling functions. Returns None if not handled."""
        if func_name == 'IF':
            condition = args[0]
            then_value = args[1]
            else_value = args[2] if len(args) > 2 else pl.Series([None] * len(df))
            return pl.Series([
                (then_value[i] if isinstance(then_value, pl.Series) else then_value)
                if condition[i] else
                (else_value[i] if isinstance(else_value, pl.Series) else else_value)
                for i in range(len(condition))
            ])
        if func_name == 'COALESCE':
            result = args[0]
            for arg in args[1:]:
                fill_val = (arg[0] if arg.n_unique() == 1 else arg) if isinstance(arg, pl.Series) else arg
                result = result.fill_null(fill_val)
            return result
        if func_name == 'ISNULL':
            return args[0].is_null()
        if func_name == 'IFNULL':
            return args[0].fill_null(args[1])
        return None

    def _eval_datetime_function(self, func_name: str, args: list) -> Optional[pl.Series]:
        """Evaluate date/time functions. Returns None if func_name not handled."""
        gs = self._get_scalar
        if func_name == 'DATE_DIFF':
            diff = args[0] - args[1]
            unit = str(gs(args[2])).lower()
            unit_map = {
                'days': diff.dt.total_days,
                'hours': diff.dt.total_hours,
                'minutes': diff.dt.total_minutes,
                'seconds': diff.dt.total_seconds,
            }
            return unit_map.get(unit, diff.dt.total_days)()
        simple_dt = {
            'YEAR': lambda s: s.dt.year(),
            'MONTH': lambda s: s.dt.month(),
            'DAY': lambda s: s.dt.day(),
            'WEEKDAY': lambda s: s.dt.weekday(),
            'HOUR': lambda s: s.dt.hour(),
            'MINUTE': lambda s: s.dt.minute(),
            'SECOND': lambda s: s.dt.second(),
        }
        if func_name in simple_dt:
            return simple_dt[func_name](args[0])
        return None

    def add_column(
        self,
        df: pl.DataFrame,
        column_name: str,
        expression: str
    ) -> pl.DataFrame:
        """Evaluate expression and append the result as a new column to df.

        Input:
            df — pl.DataFrame, source data.
            column_name — str, name for the new column; overwrites if it already exists.
            expression — str, formula evaluated via self.evaluate().
        Output: pl.DataFrame — df with the new or replaced column aliased to column_name.
        Raises: ExpressionError — propagated from evaluate() on bad expression.
        """
        result = self.evaluate(expression, df)
        return df.with_columns(result.alias(column_name))

    def validate(
        self,
        expression: str,
        df: pl.DataFrame
    ) -> Tuple[bool, Optional[str]]:
        """Tokenize, parse, and structurally validate an expression without evaluating it.

        Input:
            expression — str, the formula to validate.
            df — pl.DataFrame, used for column existence checks during AST walk.
        Output: Tuple[bool, Optional[str]] — (True, None) when valid;
            (False, error_message) on any parse or validation error.
        Raises: nothing — all exceptions are caught and returned as the error string.
        """
        try:
            # 토큰화
            lexer = Lexer(expression)
            tokens = lexer.tokenize()

            # 파싱
            parser = Parser(tokens)
            ast = parser.parse()

            # AST 검증
            self._validate_ast(ast, df)

            return True, None

        except ExpressionError as e:
            logger.warning("expression_engine.validate.failed", extra={"error": str(e), "expr": str(expression)[:80]})
            return False, str(e)
        except (pl.exceptions.InvalidOperationError, NameError, SyntaxError, TypeError, ValueError) as e:
            logger.warning("expression_engine.validate.failed", extra={"error": str(e), "expr": str(expression)[:80]})
            return False, str(e)

    def _validate_ast(self, node: Dict, df: pl.DataFrame):
        """Walk an AST node and verify column existence and function names.

        Input: node — Dict AST node; df — DataFrame for column lookups.
        Raises: ExpressionError — when a referenced column is absent from df.columns,
            or a function name is not in self.FUNCTIONS.
        """
        node_type = node['type']

        if node_type == 'column':
            name = node['name']
            if name not in df.columns:
                raise ExpressionError(f"Column '{name}' not found")

        elif node_type == 'function':
            func_name = node['name']
            if func_name not in self.FUNCTIONS:
                raise ExpressionError(f"Unknown function: {func_name}")

            for arg in node['args']:
                self._validate_ast(arg, df)

        elif node_type in ('binary', 'comparison'):
            self._validate_ast(node['left'], df)
            self._validate_ast(node['right'], df)

        elif node_type == 'unary':
            self._validate_ast(node['operand'], df)

    def get_referenced_columns(self, expression: str) -> List[str]:
        """Parse an expression and return the unique column names it references.

        Input: expression — str, any valid (or structurally valid) expression string.
        Output: List[str] — deduplicated column names; order is not guaranteed.
        Raises: ExpressionError — on tokenization or parse failure.
        """
        lexer = Lexer(expression)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()

        columns = []
        self._collect_columns(ast, columns)
        return list(set(columns))

    def _collect_columns(self, node: Dict, columns: List[str]):
        """Recursively collect column names from an AST node into columns (in-place).

        Input: node — Dict AST node; columns — mutable list accumulating column names.
        Invariants: columns may contain duplicates; deduplication is done by the caller.
        """
        if node['type'] == 'column':
            columns.append(node['name'])
        elif node['type'] in ('binary', 'comparison'):
            self._collect_columns(node['left'], columns)
            self._collect_columns(node['right'], columns)
        elif node['type'] == 'unary':
            self._collect_columns(node['operand'], columns)
        elif node['type'] == 'function':
            for arg in node['args']:
                self._collect_columns(arg, columns)
