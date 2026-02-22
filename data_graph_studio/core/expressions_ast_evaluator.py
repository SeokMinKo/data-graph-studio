"""
ExpressionEvaluatorHelpers — AST/conditional evaluation helpers extracted from
expressions_parser.py.

Handles:
- Conditional evaluation: _evaluate_conditional, _evaluate_if, _evaluate_case,
  _evaluate_condition
- Value parsing: _parse_value
- Expression transformations: _handle_string_functions, _handle_math_functions,
  _handle_date_functions, _handle_null_functions
- String concatenation: _evaluate_string_concat
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

import polars as pl
import numpy as np


class ExpressionEvaluatorHelpers:
    """Stateless helper methods for ExpressionParser evaluation."""

    def __init__(self, column_pattern: re.Pattern):
        """
        Args:
            column_pattern: compiled regex matching [column_name] references.
        """
        self._column_pattern = column_pattern

    # ------------------------------------------------------------------
    # Conditional evaluation
    # ------------------------------------------------------------------

    def evaluate_conditional(
        self,
        expression: str,
        data: pl.DataFrame,
    ) -> pl.Series:
        """조건문 평가 (If / Case)."""
        expr_lower = expression.lower().strip()
        if expr_lower.startswith('if('):
            return self.evaluate_if(expression, data)
        elif expr_lower.startswith('case '):
            return self.evaluate_case(expression, data)
        return pl.Series([None] * len(data))

    def evaluate_if(
        self,
        expression: str,
        data: pl.DataFrame,
    ) -> pl.Series:
        """IF 표현식 평가: If(condition, true_value, false_value)."""
        match = re.match(
            r"If\s*\(\s*(.+?)\s*,\s*(.+?)\s*,\s*(.+?)\s*\)",
            expression,
            re.IGNORECASE,
        )
        if not match:
            return pl.Series([None] * len(data))

        condition_expr = match.group(1)
        true_expr = match.group(2)
        false_expr = match.group(3)

        condition = self.evaluate_condition(condition_expr, data)
        true_val = self.parse_value(true_expr, data)
        false_val = self.parse_value(false_expr, data)

        result = []
        for i, cond in enumerate(condition):
            if cond:
                if isinstance(true_val, (list, pl.Series, np.ndarray)):
                    result.append(true_val[i])
                else:
                    result.append(true_val)
            else:
                if isinstance(false_val, (list, pl.Series, np.ndarray)):
                    result.append(false_val[i])
                else:
                    result.append(false_val)

        return pl.Series(result)

    def evaluate_case(
        self,
        expression: str,
        data: pl.DataFrame,
    ) -> pl.Series:
        """CASE 표현식 평가: Case When ... Then ... Else ... End."""
        when_pattern = re.compile(
            r'When\s+(.+?)\s+Then\s+(.+?)(?=\s+When|\s+Else|\s+End)',
            re.IGNORECASE,
        )
        else_pattern = re.compile(r'Else\s+(.+?)\s+End', re.IGNORECASE)

        when_matches = when_pattern.findall(expression)
        else_match = else_pattern.search(expression)
        default_val = else_match.group(1).strip() if else_match else None

        result = [None] * len(data)

        for i in range(len(data)):
            row_data = data.slice(i, 1)
            matched = False

            for condition, value in when_matches:
                cond_result = self.evaluate_condition(condition, row_data)
                if cond_result[0]:
                    result[i] = self.parse_value(value.strip(), row_data)
                    if isinstance(result[i], (list, pl.Series)):
                        result[i] = result[i][0]
                    matched = True
                    break

            if not matched and default_val is not None:
                result[i] = self.parse_value(default_val, row_data)
                if isinstance(result[i], (list, pl.Series)):
                    result[i] = result[i][0]

        return pl.Series(result)

    def evaluate_condition(
        self,
        condition: str,
        data: pl.DataFrame,
    ) -> List[bool]:
        """조건식 평가."""
        operators = ['>=', '<=', '!=', '<>', '=', '>', '<']
        op = None
        for o in operators:
            if o in condition:
                op = o
                break

        if op is None:
            return [False] * len(data)

        parts = condition.split(op)
        if len(parts) != 2:
            return [False] * len(data)

        left = parts[0].strip()
        right = parts[1].strip()

        left_val = self.parse_value(left, data)
        right_val = self.parse_value(right, data)

        result = []
        for i in range(len(data)):
            lv = left_val[i] if isinstance(left_val, (list, pl.Series, np.ndarray)) else left_val
            rv = right_val[i] if isinstance(right_val, (list, pl.Series, np.ndarray)) else right_val

            try:
                if op == '=' or op == '==':
                    result.append(lv == rv)
                elif op == '!=' or op == '<>':
                    result.append(lv != rv)
                elif op == '>':
                    result.append(lv > rv)
                elif op == '<':
                    result.append(lv < rv)
                elif op == '>=':
                    result.append(lv >= rv)
                elif op == '<=':
                    result.append(lv <= rv)
                else:
                    result.append(False)
            except Exception:
                result.append(False)

        return result

    # ------------------------------------------------------------------
    # Value parsing
    # ------------------------------------------------------------------

    def parse_value(
        self,
        value_str: str,
        data: pl.DataFrame,
    ) -> Any:
        """값 문자열 파싱."""
        value_str = value_str.strip()

        # 문자열 리터럴
        if (value_str.startswith("'") and value_str.endswith("'")) or \
           (value_str.startswith('"') and value_str.endswith('"')):
            return value_str[1:-1]

        # 컬럼 참조
        col_match = self._column_pattern.match(value_str)
        if col_match:
            col_name = col_match.group(1)
            if col_name in data.columns:
                return data[col_name].to_list()
            return None

        # 숫자
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        return value_str

    # ------------------------------------------------------------------
    # Expression transformation helpers
    # ------------------------------------------------------------------

    def handle_string_functions(
        self,
        expression: str,
        data: pl.DataFrame,
    ) -> str:
        """문자열 함수 처리."""
        expr = expression
        for match in re.finditer(r'Upper\s*\(\s*\[([^\]]+)\]\s*\)', expr, re.IGNORECASE):
            col = match.group(1)
            if col in data.columns:
                pass
        for match in re.finditer(r'Lower\s*\(\s*\[([^\]]+)\]\s*\)', expr, re.IGNORECASE):
            col = match.group(1)
            if col in data.columns:
                pass
        return expr

    def handle_math_functions(
        self,
        expression: str,
        data: pl.DataFrame,
    ) -> str:
        """수학 함수 처리."""
        expr = expression
        expr = re.sub(r'Abs\s*\(', 'np.abs(', expr, flags=re.IGNORECASE)
        expr = re.sub(r'Sqrt\s*\(', 'np.sqrt(', expr, flags=re.IGNORECASE)
        expr = re.sub(r'Round\s*\(', 'np.round(', expr, flags=re.IGNORECASE)
        expr = re.sub(r'Log\s*\(', 'np.log(', expr, flags=re.IGNORECASE)
        expr = re.sub(r'Exp\s*\(', 'np.exp(', expr, flags=re.IGNORECASE)
        expr = re.sub(r'Power\s*\(', 'np.power(', expr, flags=re.IGNORECASE)
        return expr

    def handle_date_functions(
        self,
        expression: str,
        data: pl.DataFrame,
    ) -> str:
        """날짜 함수 처리."""
        return expression

    def handle_null_functions(
        self,
        expression: str,
        data: pl.DataFrame,
    ) -> str:
        """NULL 처리 함수."""
        return expression

    # ------------------------------------------------------------------
    # String concatenation
    # ------------------------------------------------------------------

    def evaluate_string_concat(
        self,
        expression: str,
        data: pl.DataFrame,
    ) -> pl.Series:
        """문자열 연결 평가 (&)."""
        parts = expression.split('&')
        result = [''] * len(data)

        for part in parts:
            part = part.strip()

            col_match = self._column_pattern.match(part)
            if col_match:
                col_name = col_match.group(1)
                if col_name in data.columns:
                    values = data[col_name].cast(pl.Utf8).to_list()
                    result = [r + str(v) for r, v in zip(result, values)]
            elif (part.startswith("'") and part.endswith("'")) or \
                 (part.startswith('"') and part.endswith('"')):
                literal = part[1:-1]
                result = [r + literal for r in result]

        return pl.Series(result)
