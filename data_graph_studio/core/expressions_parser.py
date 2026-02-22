"""
Expression Parser - Spotfire 스타일 수식 파서

수식 파싱, 평가 및 유효성 검사를 위한 핵심 클래스들을 포함합니다.
"""

from typing import List, Dict, Any, Optional, Union, Set
from dataclasses import dataclass, field
from enum import Enum
import ast
import re
import polars as pl
import numpy as np


class SecurityError(Exception):
    """Raised when a DataFunction body contains disallowed constructs."""


class ExpressionType(Enum):
    """표현식 타입"""
    ARITHMETIC = "arithmetic"       # 산술 연산
    COMPARISON = "comparison"       # 비교 연산
    LOGICAL = "logical"            # 논리 연산
    AGGREGATE = "aggregate"        # 집계 함수
    WINDOW = "window"              # 윈도우 함수 (OVER)
    STRING = "string"              # 문자열 함수
    DATE = "date"                  # 날짜 함수
    MATH = "math"                  # 수학 함수
    CONDITIONAL = "conditional"    # 조건문


@dataclass
class ValidationResult:
    """유효성 검사 결과"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    referenced_columns: Set[str] = field(default_factory=set)


class ExpressionParser:
    """
    수식 파서

    Spotfire 스타일의 수식을 파싱하고 평가합니다.
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

    def evaluate(
        self,
        expression: str,
        data: pl.DataFrame,
        context: Optional[Dict[str, Any]] = None
    ) -> Union[pl.Series, Any]:
        """
        수식 평가

        Args:
            expression: 평가할 수식
            data: 데이터프레임
            context: 추가 컨텍스트 (변수 등)

        Returns:
            평가 결과 (Series 또는 스칼라)
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
            return self._evaluate_conditional(expression, data)

        # 일반 표현식
        return self._evaluate_simple(expression, data, context)

    def _is_aggregate_expression(self, expression: str) -> bool:
        """집계 표현식인지 확인"""
        expr_lower = expression.lower()
        for func in self.AGGREGATE_FUNCTIONS:
            if re.search(rf'\b{func}\s*\(', expr_lower):
                # OVER가 있으면 윈도우 함수
                if 'over' not in expr_lower:
                    return True
        return False

    def _is_conditional_expression(self, expression: str) -> bool:
        """조건 표현식인지 확인"""
        expr_lower = expression.lower().strip()
        return expr_lower.startswith('if(') or expr_lower.startswith('case ')

    def _evaluate_simple(
        self,
        expression: str,
        data: pl.DataFrame,
        context: Dict[str, Any]
    ) -> pl.Series:
        """단순 수식 평가"""
        # 컬럼 참조를 Polars 표현식으로 변환
        expr = expression

        # 문자열 함수 처리
        expr = self._handle_string_functions(expr, data)

        # 수학 함수 처리
        expr = self._handle_math_functions(expr, data)

        # 날짜 함수 처리
        expr = self._handle_date_functions(expr, data)

        # NULL 처리 함수
        expr = self._handle_null_functions(expr, data)

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
        """수식 계산"""
        # 간단한 산술 연산 처리
        expr = expression

        # 컬럼 참조를 numpy 배열로 변환
        local_vars = {}
        for col in columns_used:
            if col in data.columns:
                # 언더스코어로 컬럼명 변환 (특수문자 처리)
                safe_name = f"_col_{col.replace(' ', '_').replace('-', '_')}"
                local_vars[safe_name] = data[col].to_numpy()
                expr = expr.replace(f'[{col}]', safe_name)

        # 문자열 연결 연산자 (&) 처리
        if '&' in expr:
            return self._evaluate_string_concat(expression, data)

        # numpy 함수 추가
        local_vars['np'] = np

        try:
            # 안전한 평가
            result = eval(expr, {"__builtins__": {}, "np": np}, local_vars)

            if isinstance(result, np.ndarray):
                return pl.Series(result)
            elif isinstance(result, (int, float)):
                return pl.Series([result] * len(data))
            return pl.Series(result)

        except Exception:
            # 평가 실패 시 None 반환
            return pl.Series([None] * len(data))

    def _evaluate_aggregate(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> Any:
        """집계 표현식 평가"""
        expr_lower = expression.lower()

        # 컬럼 추출
        col_match = self._column_pattern.search(expression)
        if not col_match:
            return None

        col_name = col_match.group(1)
        if col_name not in data.columns:
            return None

        values = data[col_name]

        # 함수 적용
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
        """OVER 표현식 평가 (윈도우 함수)"""
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
        """누적 집계"""
        if value_col not in data.columns:
            return pl.Series([None] * len(data))

        if func_name == 'sum':
            return data.select(
                pl.col(value_col).cum_sum().over(partition_col).alias('result')
            )['result']
        elif func_name in ('avg', 'mean'):
            # 누적 평균
            cum_sum = data.select(
                pl.col(value_col).cum_sum().over(partition_col).alias('sum')
            )['sum']
            cum_count = data.select(
                pl.col(value_col).cum_count().over(partition_col).alias('count')
            )['count']
            return cum_sum / cum_count

        return pl.Series([None] * len(data))

    def _evaluate_conditional(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> pl.Series:
        """조건문 평가"""
        expr_lower = expression.lower().strip()

        if expr_lower.startswith('if('):
            return self._evaluate_if(expression, data)
        elif expr_lower.startswith('case '):
            return self._evaluate_case(expression, data)

        return pl.Series([None] * len(data))

    def _evaluate_if(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> pl.Series:
        """IF 표현식 평가: If(condition, true_value, false_value)"""
        # 간단한 파싱
        match = re.match(
            r"If\s*\(\s*(.+?)\s*,\s*(.+?)\s*,\s*(.+?)\s*\)",
            expression,
            re.IGNORECASE
        )

        if not match:
            return pl.Series([None] * len(data))

        condition_expr = match.group(1)
        true_expr = match.group(2)
        false_expr = match.group(3)

        # 조건 평가
        condition = self._evaluate_condition(condition_expr, data)

        # true/false 값 평가
        true_val = self._parse_value(true_expr, data)
        false_val = self._parse_value(false_expr, data)

        # 결과 생성
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

    def _evaluate_case(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> pl.Series:
        """CASE 표현식 평가"""
        # Case When ... Then ... Else ... End
        when_pattern = re.compile(
            r'When\s+(.+?)\s+Then\s+(.+?)(?=\s+When|\s+Else|\s+End)',
            re.IGNORECASE
        )
        else_pattern = re.compile(r'Else\s+(.+?)\s+End', re.IGNORECASE)

        when_matches = when_pattern.findall(expression)
        else_match = else_pattern.search(expression)

        default_val = else_match.group(1).strip() if else_match else None

        result = [None] * len(data)

        # 각 행에 대해 조건 평가
        for i in range(len(data)):
            row_data = data.slice(i, 1)
            matched = False

            for condition, value in when_matches:
                cond_result = self._evaluate_condition(condition, row_data)
                if cond_result[0]:
                    result[i] = self._parse_value(value.strip(), row_data)
                    if isinstance(result[i], (list, pl.Series)):
                        result[i] = result[i][0]
                    matched = True
                    break

            if not matched and default_val is not None:
                result[i] = self._parse_value(default_val, row_data)
                if isinstance(result[i], (list, pl.Series)):
                    result[i] = result[i][0]

        return pl.Series(result)

    def _evaluate_condition(
        self,
        condition: str,
        data: pl.DataFrame
    ) -> List[bool]:
        """조건식 평가"""
        # 비교 연산자 추출
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

        # 컬럼 값 추출
        left_val = self._parse_value(left, data)
        right_val = self._parse_value(right, data)

        # 비교
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

    def _parse_value(
        self,
        value_str: str,
        data: pl.DataFrame
    ) -> Any:
        """값 문자열 파싱"""
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

    def _handle_string_functions(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> str:
        """문자열 함수 처리"""
        expr = expression

        # Upper([col])
        for match in re.finditer(r'Upper\s*\(\s*\[([^\]]+)\]\s*\)', expr, re.IGNORECASE):
            col = match.group(1)
            if col in data.columns:
                # 직접 결과 반환을 위해 플래그 설정
                pass

        # Lower([col])
        for match in re.finditer(r'Lower\s*\(\s*\[([^\]]+)\]\s*\)', expr, re.IGNORECASE):
            col = match.group(1)
            if col in data.columns:
                pass

        return expr

    def _handle_math_functions(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> str:
        """수학 함수 처리"""
        expr = expression

        # Abs
        expr = re.sub(r'Abs\s*\(', 'np.abs(', expr, flags=re.IGNORECASE)

        # Sqrt
        expr = re.sub(r'Sqrt\s*\(', 'np.sqrt(', expr, flags=re.IGNORECASE)

        # Round
        expr = re.sub(r'Round\s*\(', 'np.round(', expr, flags=re.IGNORECASE)

        # Log
        expr = re.sub(r'Log\s*\(', 'np.log(', expr, flags=re.IGNORECASE)

        # Exp
        expr = re.sub(r'Exp\s*\(', 'np.exp(', expr, flags=re.IGNORECASE)

        # Power
        expr = re.sub(r'Power\s*\(', 'np.power(', expr, flags=re.IGNORECASE)

        return expr

    def _handle_date_functions(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> str:
        """날짜 함수 처리"""
        # Year, Month, Day 등
        # 이 함수들은 별도 처리 필요
        return expression

    def _handle_null_functions(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> str:
        """NULL 처리 함수"""
        return expression

    def _evaluate_string_concat(
        self,
        expression: str,
        data: pl.DataFrame
    ) -> pl.Series:
        """문자열 연결 평가"""
        parts = expression.split('&')
        result = [''] * len(data)

        for part in parts:
            part = part.strip()

            # 컬럼 참조
            col_match = self._column_pattern.match(part)
            if col_match:
                col_name = col_match.group(1)
                if col_name in data.columns:
                    values = data[col_name].cast(pl.Utf8).to_list()
                    result = [r + str(v) for r, v in zip(result, values)]

            # 문자열 리터럴
            elif (part.startswith("'") and part.endswith("'")) or \
                 (part.startswith('"') and part.endswith('"')):
                literal = part[1:-1]
                result = [r + literal for r in result]

        return pl.Series(result)

    def get_referenced_columns(self, expression: str) -> Set[str]:
        """수식에서 참조하는 컬럼 목록"""
        return set(self._column_pattern.findall(expression))
