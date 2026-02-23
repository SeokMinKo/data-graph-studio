"""
Advanced Expressions - Spotfire 스타일 수식 엔진

계산 컬럼, OVER 표현식 (윈도우 함수), 데이터 함수 등을 지원합니다.
"""

import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
import ast
import polars as pl
import numpy as np

logger = logging.getLogger(__name__)

from data_graph_studio.core.expressions_parser import (
    SecurityError, ExpressionType, ValidationResult, ExpressionParser
)


class OverExpression:
    """Partition-based window aggregate in Spotfire OVER style.

    Wraps a Polars .over() call for a single aggregate function applied to
    value_column, optionally partitioned by one or more columns.
    """

    def __init__(
        self,
        aggregate_func: str,
        value_column: str,
        partition_by: Optional[List[str]] = None,
        order_by: Optional[List[str]] = None
    ):
        """Initialize an OVER expression.

        Input:
            aggregate_func — str, one of: sum, avg/mean, count, min, max, rank
                (case-insensitive; stored as lowercase).
            value_column — str, name of the column to aggregate.
            partition_by — Optional[List[str]], partition group columns; defaults to [].
            order_by — Optional[List[str]], ordering columns (stored but not used
                by the current Polars implementation).
        """
        self.aggregate_func = aggregate_func.lower()
        self.value_column = value_column
        self.partition_by = partition_by or []
        self.order_by = order_by or []

    def evaluate(self, data: pl.DataFrame) -> pl.Series:
        """Apply the window aggregate to data and return a row-aligned Series.

        Input: data — pl.DataFrame, source data; must contain value_column when
            a non-null result is expected.
        Output: pl.Series — one element per row; null-filled when value_column
            is absent or aggregate_func is not recognized.
        Invariants: When partition_by is non-empty, Polars .over() is used so
            each row receives the aggregate for its partition group.
        """
        if self.value_column not in data.columns:
            return pl.Series([None] * len(data))

        # Polars 윈도우 함수 사용
        expr = pl.col(self.value_column)

        # 집계 함수 적용
        if self.aggregate_func == 'sum':
            expr = expr.sum()
        elif self.aggregate_func in ('avg', 'mean'):
            expr = expr.mean()
        elif self.aggregate_func == 'count':
            expr = expr.count()
        elif self.aggregate_func == 'min':
            expr = expr.min()
        elif self.aggregate_func == 'max':
            expr = expr.max()
        elif self.aggregate_func == 'rank':
            expr = expr.rank()
        else:
            return pl.Series([None] * len(data))

        # 파티션
        if self.partition_by:
            expr = expr.over(self.partition_by)

        return data.select(expr.alias('result'))['result']


@dataclass
class CalculatedColumn:
    """Expression-based derived column definition.

    Stores a name, a Spotfire-style formula, and optional metadata. Evaluation
    is delegated to ExpressionParser. Instantiated as a dataclass; call apply()
    to materialize the column.

    Attributes:
        name: Output column name.
        expression: Spotfire-style formula string.
        description: Human-readable description (optional, not used in evaluation).
        data_type: Expected output dtype hint (optional, not enforced).
    """
    name: str
    expression: str
    description: str = ""
    data_type: Optional[str] = None

    def __post_init__(self):
        self._parser = ExpressionParser()

    def apply(self, data: pl.DataFrame) -> pl.DataFrame:
        """Evaluate the expression and append the result as a new column to data.

        Input: data — pl.DataFrame, source data passed to ExpressionParser.evaluate().
        Output: pl.DataFrame — data with the new column aliased to self.name.
            Scalar results are broadcast to a constant column via pl.lit().
        Raises: propagates any exception from ExpressionParser.evaluate().
        """
        result = self._parser.evaluate(self.expression, data)

        if isinstance(result, pl.Series):
            return data.with_columns(result.alias(self.name))
        else:
            # 스칼라 값인 경우
            return data.with_columns(pl.lit(result).alias(self.name))

    def get_referenced_columns(self) -> Set[str]:
        """Return the set of column names referenced in this column's expression.

        Output: Set[str] — unique column names found via ExpressionParser.get_referenced_columns().
        """
        return self._parser.get_referenced_columns(self.expression)


@dataclass
class DataFunction:
    """User-defined function executed as sandboxed Python code.

    The function body is AST-scanned before exec() to block dunder access and
    dangerous built-in names. The exec() sandbox exposes only numpy (np),
    polars (pl), the input DataFrame (data), and any extra kwargs.

    Attributes:
        name: Function identifier used by DataFunctionRegistry.
        parameters: Ordered list of expected parameter names (informational).
        body: Python source code; must assign to a local variable named 'result'.
        description: Human-readable description.
        return_type: Expected return type hint (not enforced).
    """
    name: str
    parameters: List[str]
    body: str
    description: str = ""
    return_type: str = "any"

    _BLOCKED_NAMES: frozenset = frozenset(
        {'exec', 'eval', 'compile', '__import__', 'open', 'getattr',
         'setattr', 'delattr', 'globals', 'locals', 'vars', 'dir',
         'breakpoint', 'input', 'print'}
    )

    def _validate_body_ast(self, body: str) -> None:
        """AST-scan the function body before exec() to block dangerous constructs.

        Input: body — str, Python source code to validate.
        Raises:
            SecurityError — when a dunder attribute access (__..__) is detected.
            SecurityError — when a name in _BLOCKED_NAMES is referenced.
            SecurityError — when body contains a SyntaxError.
        Invariants: Called unconditionally before every exec() in execute().
        """
        try:
            tree = ast.parse(body)
        except SyntaxError as exc:
            raise SecurityError(f"Syntax error in DataFunction body: {exc}") from exc

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.startswith('__'):
                raise SecurityError(
                    f"Dunder attribute access not allowed: {node.attr!r}"
                )
            if isinstance(node, ast.Name) and node.id in self._BLOCKED_NAMES:
                raise SecurityError(
                    f"Blocked identifier in DataFunction body: {node.id!r}"
                )

    def execute(
        self,
        data: pl.DataFrame,
        **kwargs
    ) -> Any:
        """Execute the function body in a sandboxed environment.

        Input:
            data — pl.DataFrame, available as 'data' inside the body.
            **kwargs — additional named variables exposed inside the body.
        Output: Any — the value assigned to 'result' inside the body;
            None when 'result' is never assigned or an exception occurs.
        Raises:
            SecurityError — propagated from _validate_body_ast() when body fails AST check.
        Invariants:
            - _validate_body_ast() always runs before exec().
            - exec() uses empty __builtins__; only np, pl, data, and kwargs are accessible.
            - Non-SecurityError exceptions are logged at DEBUG and return None.
        """
        # AST validation before exec — blocks dunder access and dangerous names
        self._validate_body_ast(self.body)

        # 안전한 실행 환경
        local_vars = {
            'data': data,
            'np': np,
            'pl': pl,
            **kwargs
        }

        try:
            exec(self.body, {"__builtins__": {}}, local_vars)
            return local_vars.get('result')
        except SecurityError:
            raise
        except (NameError, SyntaxError, TypeError, ValueError, ZeroDivisionError):
            logger.debug("expressions.data_function.exec_failed", exc_info=True)
            return None


class DataFunctionRegistry:
    """Registry for built-in and user-defined DataFunction instances.

    Built-in functions (Normalize, ZScore, Percentile, MovingAverage) are
    registered on construction. Custom functions can be added with register()
    and removed with unregister().
    """

    def __init__(self):
        self._functions: Dict[str, DataFunction] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register the four built-in DataFunctions: Normalize, ZScore, Percentile, MovingAverage."""
        # Normalize (정규화)
        self._functions['Normalize'] = DataFunction(
            name='Normalize',
            parameters=['column'],
            body='''
values = data[column].to_numpy()
min_val = np.min(values)
max_val = np.max(values)
result = (values - min_val) / (max_val - min_val) if max_val != min_val else values
''',
            description='값을 0-1 범위로 정규화'
        )

        # ZScore (표준화)
        self._functions['ZScore'] = DataFunction(
            name='ZScore',
            parameters=['column'],
            body='''
values = data[column].to_numpy()
result = (values - np.mean(values)) / np.std(values) if np.std(values) != 0 else values
''',
            description='Z-점수로 표준화'
        )

        # Percentile
        self._functions['Percentile'] = DataFunction(
            name='Percentile',
            parameters=['column', 'percentile'],
            body='''
values = data[column].to_numpy()
result = np.percentile(values, percentile)
''',
            description='백분위수 계산'
        )

        # MovingAverage
        self._functions['MovingAverage'] = DataFunction(
            name='MovingAverage',
            parameters=['column', 'window'],
            body='''
values = data[column].to_numpy()
result = np.convolve(values, np.ones(window)/window, mode='same')
''',
            description='이동 평균'
        )

    def register(self, func: DataFunction) -> None:
        """Add or replace a DataFunction in the registry.

        Input: func — DataFunction, keyed by func.name; overwrites any existing entry.
        """
        self._functions[func.name] = func

    def unregister(self, name: str) -> None:
        """Remove a function from the registry by name; no-op if name not found.

        Input: name — str, the function name to remove.
        """
        if name in self._functions:
            del self._functions[name]

    def get(self, name: str) -> Optional[DataFunction]:
        """Look up a DataFunction by name.

        Input: name — str, function name.
        Output: Optional[DataFunction] — the function object, or None if not registered.
        """
        return self._functions.get(name)

    def list_functions(self) -> List[str]:
        """Return the names of all registered functions (built-in and user-defined).

        Output: List[str] — function names in insertion order.
        """
        return list(self._functions.keys())

    def list_builtin_functions(self) -> List[str]:
        """Return the names of the four built-in functions registered at construction.

        Output: List[str] — ['Normalize', 'ZScore', 'Percentile', 'MovingAverage'].
        """
        return ['Normalize', 'ZScore', 'Percentile', 'MovingAverage']

    def execute(
        self,
        name: str,
        data: pl.DataFrame,
        **kwargs
    ) -> Any:
        """Look up a function by name and execute it against data.

        Input:
            name — str, the function name to look up.
            data — pl.DataFrame, passed to DataFunction.execute().
            **kwargs — additional named variables forwarded to the function body.
        Output: Any — function result, or None when name is not registered.
        Raises: SecurityError — propagated from DataFunction.execute() on unsafe body.
        """
        func = self.get(name)
        if func is None:
            return None
        return func.execute(data, **kwargs)


class ExpressionValidator:
    """Validates Spotfire-style expressions against a known column list.

    Checks for: column existence, balanced parentheses, balanced brackets.
    Also provides circular-reference detection for networks of calculated columns.
    """

    def __init__(self):
        self._parser = ExpressionParser()

    def validate(
        self,
        expression: str,
        available_columns: List[str]
    ) -> ValidationResult:
        """Validate an expression against the given column list.

        Input:
            expression — str, the formula to validate.
            available_columns — List[str], column names considered valid references.
        Output: ValidationResult — is_valid=True iff errors is empty;
            errors contains messages for missing columns and unbalanced brackets/parens;
            referenced_columns holds all [bracket]-extracted column names.
        Raises: nothing — all errors are returned in ValidationResult.errors.
        """
        errors = []
        warnings = []

        # 참조 컬럼 추출
        referenced = self._parser.get_referenced_columns(expression)

        # 존재하지 않는 컬럼 확인
        for col in referenced:
            if col not in available_columns:
                errors.append(f"Column '{col}' does not exist")

        # 괄호 균형 검사
        if expression.count('(') != expression.count(')'):
            errors.append("Unbalanced parentheses")

        # 대괄호 균형 검사
        if expression.count('[') != expression.count(']'):
            errors.append("Unbalanced brackets")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            referenced_columns=referenced
        )

    def check_circular_reference(
        self,
        column_name: str,
        expression: str,
        existing_calculated_columns: Dict[str, str]
    ) -> bool:
        """Detect whether adding column_name with expression would create a circular dependency.

        Input:
            column_name — str, name of the proposed new calculated column.
            expression — str, formula for column_name.
            existing_calculated_columns — Dict[str, str], map of existing calculated
                column names to their expressions.
        Output: bool — True when a cycle is detected (i.e., following dependencies of
            expression eventually leads back to column_name); False otherwise.
        Raises: nothing.
        Invariants: Uses iterative DFS with a visited set to prevent infinite recursion
            on pre-existing cycles in existing_calculated_columns.
        """
        # 현재 컬럼이 참조하는 컬럼들
        referenced = self._parser.get_referenced_columns(expression)

        # DFS로 순환 참조 검사
        visited = set()

        def has_cycle(col: str) -> bool:
            """Return True if following col's dependencies eventually reaches column_name."""
            if col == column_name:
                return True
            if col in visited:
                return False

            visited.add(col)

            if col in existing_calculated_columns:
                refs = self._parser.get_referenced_columns(
                    existing_calculated_columns[col]
                )
                for ref in refs:
                    if has_cycle(ref):
                        return True

            return False

        for ref in referenced:
            if has_cycle(ref):
                return True

        return False
