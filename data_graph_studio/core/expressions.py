"""
Advanced Expressions - Spotfire 스타일 수식 엔진

계산 컬럼, OVER 표현식 (윈도우 함수), 데이터 함수 등을 지원합니다.
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
import ast
import polars as pl
import numpy as np

from data_graph_studio.core.expressions_parser import (
    SecurityError, ExpressionType, ValidationResult, ExpressionParser
)


class OverExpression:
    """
    OVER 표현식 (윈도우 함수)

    Spotfire 스타일의 파티션 기반 집계를 지원합니다.
    """

    def __init__(
        self,
        aggregate_func: str,
        value_column: str,
        partition_by: Optional[List[str]] = None,
        order_by: Optional[List[str]] = None
    ):
        self.aggregate_func = aggregate_func.lower()
        self.value_column = value_column
        self.partition_by = partition_by or []
        self.order_by = order_by or []

    def evaluate(self, data: pl.DataFrame) -> pl.Series:
        """표현식 평가"""
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
    """
    계산 컬럼

    수식 기반의 새 컬럼을 정의합니다.
    """
    name: str
    expression: str
    description: str = ""
    data_type: Optional[str] = None

    def __post_init__(self):
        self._parser = ExpressionParser()

    def apply(self, data: pl.DataFrame) -> pl.DataFrame:
        """
        데이터프레임에 계산 컬럼 추가

        Args:
            data: 원본 데이터프레임

        Returns:
            계산 컬럼이 추가된 데이터프레임
        """
        result = self._parser.evaluate(self.expression, data)

        if isinstance(result, pl.Series):
            return data.with_columns(result.alias(self.name))
        else:
            # 스칼라 값인 경우
            return data.with_columns(pl.lit(result).alias(self.name))

    def get_referenced_columns(self) -> Set[str]:
        """참조 컬럼 목록"""
        return self._parser.get_referenced_columns(self.expression)


@dataclass
class DataFunction:
    """
    데이터 함수

    Python 코드를 사용한 커스텀 함수입니다.
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
        """
        AST-scan the function body before exec().

        Raises SecurityError if dunder attribute access or blocked built-in
        names are detected.
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
        """
        함수 실행

        Args:
            data: 입력 데이터프레임
            **kwargs: 함수 파라미터

        Returns:
            함수 실행 결과
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
        except Exception:
            return None


class DataFunctionRegistry:
    """
    데이터 함수 레지스트리

    내장 및 사용자 정의 데이터 함수를 관리합니다.
    """

    def __init__(self):
        self._functions: Dict[str, DataFunction] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """내장 함수 등록"""
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
        """함수 등록"""
        self._functions[func.name] = func

    def unregister(self, name: str) -> None:
        """함수 제거"""
        if name in self._functions:
            del self._functions[name]

    def get(self, name: str) -> Optional[DataFunction]:
        """함수 조회"""
        return self._functions.get(name)

    def list_functions(self) -> List[str]:
        """함수 목록"""
        return list(self._functions.keys())

    def list_builtin_functions(self) -> List[str]:
        """내장 함수 목록"""
        return ['Normalize', 'ZScore', 'Percentile', 'MovingAverage']

    def execute(
        self,
        name: str,
        data: pl.DataFrame,
        **kwargs
    ) -> Any:
        """함수 실행"""
        func = self.get(name)
        if func is None:
            return None
        return func.execute(data, **kwargs)


class ExpressionValidator:
    """
    수식 유효성 검사기
    """

    def __init__(self):
        self._parser = ExpressionParser()

    def validate(
        self,
        expression: str,
        available_columns: List[str]
    ) -> ValidationResult:
        """
        수식 유효성 검사

        Args:
            expression: 검사할 수식
            available_columns: 사용 가능한 컬럼 목록

        Returns:
            유효성 검사 결과
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
        """
        순환 참조 검사

        Args:
            column_name: 새 컬럼 이름
            expression: 새 컬럼 수식
            existing_calculated_columns: 기존 계산 컬럼 {이름: 수식}

        Returns:
            순환 참조 존재 여부
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
