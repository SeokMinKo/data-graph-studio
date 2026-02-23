"""
Expression Parser - Spotfire 스타일 수식 파서

수식 파싱, 평가 및 유효성 검사를 위한 핵심 클래스들을 포함합니다.

Conditional/helper evaluation methods live in expressions_ast_evaluator.py.
"""

import logging
from typing import List, Dict, Any, Optional, Union, Set
from dataclasses import dataclass, field
from enum import Enum
import re
import polars as pl
import numpy as np

from data_graph_studio.core.expressions_ast_evaluator import ExpressionEvaluatorHelpers

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a DataFunction body contains disallowed constructs."""


class ExpressionType(Enum):
    """Categorizes an expression by its primary operation for routing/display purposes."""
    ARITHMETIC = "arithmetic"
    COMPARISON = "comparison"
    LOGICAL = "logical"
    AGGREGATE = "aggregate"
    WINDOW = "window"
    STRING = "string"
    DATE = "date"
    MATH = "math"
    CONDITIONAL = "conditional"


@dataclass
class ValidationResult:
    """Result of ExpressionParser or ExpressionValidator validation.

    Attributes:
        is_valid: True iff errors is empty.
        errors: List of human-readable error descriptions; non-empty means invalid.
        warnings: Non-fatal issues (e.g., missing optional columns) that don't
            block evaluation.
        referenced_columns: Set of column names extracted from the expression.
    """
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    referenced_columns: Set[str] = field(default_factory=set)


class ExpressionParser:
    """Spotfire-style expression parser and evaluator for Polars DataFrames.

    Handles four expression categories in priority order:
    1. OVER expressions (window/partition-based aggregation via regex detection)
    2. Aggregate expressions (sum, avg, count, etc. without OVER)
    3. Conditional expressions (If(…) / Case When … End)
    4. Simple arithmetic/string/math/date expressions (via numpy eval)

    Column references use Spotfire bracket notation: [ColumnName].
    Delegate helpers (string/math/date/null transforms, IF, CASE, &-concat)
    live in ExpressionEvaluatorHelpers (expressions_ast_evaluator.py).
    """

    # 집계 함수 목록
    AGGREGATE_FUNCTIONS = {
        'sum', 'avg', 'mean', 'count', 'min', 'max',
        'median', 'std', 'var', 'first', 'last'
    }

    # 윈도우 함수 목록
    WINDOW_FUNCTIONS = {
        'rank', 'denserank', 'dense_rank', 'rownumber', 'row_number',
        'lag', 'lead', 'firstvalue', 'lastvalue'
    }

    def __init__(self):
        """Initialize compiled regex patterns and delegate helper instance.

        Output: None
        Invariants: five compiled regex patterns are cached; an ExpressionEvaluatorHelpers
            instance is created and stored for conditional/string/date evaluation
        """
        # 컬럼 참조 패턴: [column_name]
        self._column_pattern = re.compile(r'\[([^\]]+)\]')

        # 함수 호출 패턴: FunctionName(...)
        self._function_pattern = re.compile(r'(\w+)\s*\(')

        # OVER 패턴
        self._over_pattern = re.compile(
            r'(\w+)\s*\(\s*\[([^\]]+)\]\s*\)\s*OVER\s*\(\s*\[?([^\]\)]+)\]?\s*\)',
            re.IGNORECASE
        )

        # 문자열 연결 패턴
        self._concat_pattern = re.compile(r"'([^']*)'|\"([^\"]*)\"")

        # Delegate helpers
        self._helpers = ExpressionEvaluatorHelpers(self._column_pattern)

    def evaluate(
        self,
        expression: str,
        data: pl.DataFrame,
        context: Optional[Dict[str, Any]] = None
    ) -> Union[pl.Series, Any]:
        """Evaluate a Spotfire-style expression against a DataFrame.

        Input:
            expression — str, the formula string (column refs as [Name]).
            data — pl.DataFrame, source data for column lookups.
            context — Optional[Dict[str, Any]], additional named variables
                (currently unused but reserved for future variable binding).
        Output: Union[pl.Series, Any] — pl.Series (one element per row) for
            row-level expressions; scalar for aggregate expressions.
        Raises: nothing directly — each sub-evaluator catches its own errors and
            may return a null-filled Series on failure.
        Invariants: OVER detection takes priority over aggregate detection.
        """
        if context is None:
            context = {}

        # OVER 표현식 확인
        over_match = self._over_pattern.search(expression)
        if over_match:
            return self._evaluate_over_expression(expression, data, over_match)

        # 집계 함수 확인
        if self._is_aggregate_expression(expression):
            return self._evaluate_aggregate(expression, data)

        # 조건문 확인 (If, Case)
        if self._is_conditional_expression(expression):
            return self._helpers.evaluate_conditional(expression, data)

        # 일반 표현식
        return self._evaluate_simple(expression, data, context)

    def _is_aggregate_expression(self, expression: str) -> bool:
        """Return True if expression contains an aggregate function call without OVER.

        Input: expression — str to classify.
        Output: bool — True when a bare aggregate function (no OVER clause) is found.
        """
        expr_lower = expression.lower()
        for func in self.AGGREGATE_FUNCTIONS:
            if re.search(rf'\b{func}\s*\(', expr_lower):
                # OVER가 있으면 윈도우 함수
                if 'over' not in expr_lower:
                    return True
        return False

    def _is_conditional_expression(self, expression: str) -> bool:
        """Return True if expression starts with If( or Case (case-insensitive).

        Input: expression — str to classify.
        Output: bool.
        """
        expr_lower = expression.lower().strip()
        return expr_lower.startswith('if(') or expr_lower.startswith('case ')

    def _evaluate_simple(
        self,
        expression: str,
        data: pl.DataFrame,
        context: Dict[str, Any]
    ) -> pl.Series:
        """Evaluate a non-aggregate, non-conditional expression via numpy eval fallback.

        Input:
            expression — str, a formula with [col] references, string/math/date/null
                function calls, or arithmetic operators.
            data — pl.DataFrame, source data.
            context — Dict, currently unused.
        Output: pl.Series — row-level result; null-filled on eval failure.
        """
        expr = expression

        # 문자열 함수 처리
        expr = self._helpers.handle_string_functions(expr, data)

        # 수학 함수 처리
        expr = self._helpers.handle_math_functions(expr, data)

        # 날짜 함수 처리
        expr = self._helpers.handle_date_functions(expr, data)

        # NULL 처리 함수
        expr = self._helpers.handle_null_functions(expr, data)

        # 컬럼 참조 변환
        columns_used = self._column_pattern.findall(expr)

        # 컬럼 값으로 직접 계산
        result = self._calculate_expression(expr, data, columns_used)

        return result

    def _calculate_expression(
        self,
        expression: str,
        data: pl.DataFrame,
        columns_used: List[str]
    ) -> pl.Series:
        """Compute an expression by substituting column refs with numpy arrays and eval()ing.

        Input:
            expression — str with [col] references already partially transformed
                by handle_* helpers.
            data — pl.DataFrame for column value lookup.
            columns_used — List[str] of column names extracted from expression.
        Output: pl.Series — result; null-filled Series on eval error or & operator
            (delegated to evaluate_string_concat).
        Invariants: eval() runs with empty __builtins__ and only numpy exposed.
        """
        expr = expression

        # 컬럼 참조를 numpy 배열로 변환
        local_vars = {}
        for col in columns_used:
            if col in data.columns:
                safe_name = f"_col_{col.replace(' ', '_').replace('-', '_')}"
                local_vars[safe_name] = data[col].to_numpy()
                expr = expr.replace(f'[{col}]', safe_name)

        # 문자열 연결 연산자 (&) 처리
        if '&' in expr:
            return self._helpers.evaluate_string_concat(expression, data)

        # numpy 함수 추가
        local_vars['np'] = np

        try:
            result = eval(expr, {"__builtins__": {}, "np": np}, local_vars)

            if isinstance(result, np.ndarray):
                return pl.Series(result)
            elif isinstance(result, (int, float)):
                return pl.Series([result] * len(data))
            return pl.Series(result)

        except (SyntaxError, ValueError, TypeError):
            logger.debug("expressions_parser.evaluate_numpy.failed", exc_info=True)
            return pl.Series([None] * len(data))

    def _evaluate_aggregate(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> Any:
        """Evaluate a bare aggregate function (sum/avg/mean/count/min/max/median/std/var/first/last).

        Input:
            expression — str containing exactly one aggregate function call with a [col] ref.
            data — pl.DataFrame, source data.
        Output: Any — scalar aggregate result (int/float/None); None when column not found
            or no aggregate function matched.
        """
        expr_lower = expression.lower()

        col_match = self._column_pattern.search(expression)
        if not col_match:
            return None

        col_name = col_match.group(1)
        if col_name not in data.columns:
            return None

        values = data[col_name]

        if 'sum(' in expr_lower:
            return values.sum()
        elif 'avg(' in expr_lower or 'mean(' in expr_lower:
            return values.mean()
        elif 'count(' in expr_lower:
            return len(values)
        elif 'min(' in expr_lower:
            return values.min()
        elif 'max(' in expr_lower:
            return values.max()
        elif 'median(' in expr_lower:
            return values.median()
        elif 'std(' in expr_lower:
            return values.std()
        elif 'var(' in expr_lower:
            return values.var()
        elif 'first(' in expr_lower:
            return values[0] if len(values) > 0 else None
        elif 'last(' in expr_lower:
            return values[-1] if len(values) > 0 else None

        return None

    def _evaluate_over_expression(
        self,
        expression: str,
        data: pl.DataFrame,
        match: re.Match
    ) -> pl.Series:
        """Evaluate a Spotfire-style OVER (window) expression using Polars .over().

        Input:
            expression — str, the full expression (unused after regex extraction).
            data — pl.DataFrame, source data.
            match — re.Match from self._over_pattern; groups: (func, value_col, partition).
        Output: pl.Series — partition-aggregated result aligned to df row order;
            null-filled when value_col is missing, partition_col is missing, or
            func is not one of sum/avg/mean/count/min/max/rank/denserank/dense_rank.
        Invariants: AllPrevious(…) partition syntax is detected first and routes to
            _evaluate_running_aggregate.
        """
        func_name = match.group(1).lower()
        value_col = match.group(2)
        partition_col = match.group(3)

        # AllPrevious 처리
        if partition_col.lower().startswith('allprevious'):
            inner_match = re.search(r'\[([^\]]+)\]', partition_col)
            if inner_match:
                partition_col = inner_match.group(1)
                return self._evaluate_running_aggregate(func_name, value_col, partition_col, data)

        if value_col not in data.columns:
            return pl.Series([None] * len(data))

        # 파티션별 집계
        if partition_col in data.columns:
            if func_name == 'sum':
                result = data.select(
                    pl.col(value_col).sum().over(partition_col).alias('result')
                )['result']
            elif func_name in ('avg', 'mean'):
                result = data.select(
                    pl.col(value_col).mean().over(partition_col).alias('result')
                )['result']
            elif func_name == 'count':
                result = data.select(
                    pl.col(value_col).count().over(partition_col).alias('result')
                )['result']
            elif func_name == 'min':
                result = data.select(
                    pl.col(value_col).min().over(partition_col).alias('result')
                )['result']
            elif func_name == 'max':
                result = data.select(
                    pl.col(value_col).max().over(partition_col).alias('result')
                )['result']
            elif func_name in ('rank', 'denserank', 'dense_rank'):
                result = data.select(
                    pl.col(value_col).rank(method='dense', descending=True).over(partition_col).alias('result')
                )['result']
            else:
                result = pl.Series([None] * len(data))

            return result

        return pl.Series([None] * len(data))

    def _evaluate_running_aggregate(
        self,
        func_name: str,
        value_col: str,
        partition_col: str,
        data: pl.DataFrame
    ) -> pl.Series:
        """Evaluate a running (cumulative) aggregate using Polars cum_sum / cum_count.

        Input:
            func_name — str, one of 'sum', 'avg', 'mean' (lowercase).
            value_col — str, name of the column to aggregate.
            partition_col — str, name of the column that defines partition groups.
            data — pl.DataFrame, source data.
        Output: pl.Series — row-aligned cumulative result; null-filled Series when
            value_col is absent from data or func_name is not supported.
        """
        if value_col not in data.columns:
            return pl.Series([None] * len(data))

        if func_name == 'sum':
            return data.select(
                pl.col(value_col).cum_sum().over(partition_col).alias('result')
            )['result']
        elif func_name in ('avg', 'mean'):
            cum_sum = data.select(
                pl.col(value_col).cum_sum().over(partition_col).alias('sum')
            )['sum']
            cum_count = data.select(
                pl.col(value_col).cum_count().over(partition_col).alias('count')
            )['count']
            return cum_sum / cum_count

        return pl.Series([None] * len(data))

    # -- Conditional evaluation (delegates to helpers) -------------------------

    def _evaluate_conditional(self, expression: str, data: pl.DataFrame) -> pl.Series:
        return self._helpers.evaluate_conditional(expression, data)

    def _evaluate_if(self, expression: str, data: pl.DataFrame) -> pl.Series:
        return self._helpers.evaluate_if(expression, data)

    def _evaluate_case(self, expression: str, data: pl.DataFrame) -> pl.Series:
        return self._helpers.evaluate_case(expression, data)

    def _evaluate_condition(self, condition: str, data: pl.DataFrame) -> List[bool]:
        return self._helpers.evaluate_condition(condition, data)

    def _parse_value(self, value_str: str, data: pl.DataFrame) -> Any:
        return self._helpers.parse_value(value_str, data)

    # -- Expression transformations (delegates to helpers) ---------------------

    def _handle_string_functions(self, expression: str, data: pl.DataFrame) -> str:
        return self._helpers.handle_string_functions(expression, data)

    def _handle_math_functions(self, expression: str, data: pl.DataFrame) -> str:
        return self._helpers.handle_math_functions(expression, data)

    def _handle_date_functions(self, expression: str, data: pl.DataFrame) -> str:
        return self._helpers.handle_date_functions(expression, data)

    def _handle_null_functions(self, expression: str, data: pl.DataFrame) -> str:
        return self._helpers.handle_null_functions(expression, data)

    def _evaluate_string_concat(self, expression: str, data: pl.DataFrame) -> pl.Series:
        return self._helpers.evaluate_string_concat(expression, data)

    def get_referenced_columns(self, expression: str) -> Set[str]:
        """Extract the set of column names referenced by bracket notation in expression.

        Input: expression — str, any Spotfire-style expression.
        Output: Set[str] — unique column names found inside [brackets]; empty set if none.
        """
        return set(self._column_pattern.findall(expression))
