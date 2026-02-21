"""
Expression Engine - 계산 필드를 위한 수식 엔진
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import polars as pl


class ExpressionError(Exception):
    """수식 오류"""
    pass


class TokenType(Enum):
    """토큰 타입"""
    NUMBER = "NUMBER"
    STRING = "STRING"
    IDENTIFIER = "IDENTIFIER"
    OPERATOR = "OPERATOR"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    COMMA = "COMMA"
    COMPARISON = "COMPARISON"
    EOF = "EOF"


@dataclass
class Token:
    """토큰"""
    type: TokenType
    value: Any
    position: int = 0


class Lexer:
    """수식 렉서"""
    
    OPERATORS = {'+', '-', '*', '/', '%', '^'}
    COMPARISONS = {'==', '!=', '>=', '<=', '>', '<'}
    
    def __init__(self, expression: str):
        self.expression = expression
        self.pos = 0
        self.length = len(expression)
    
    def tokenize(self) -> List[Token]:
        """토큰화"""
        tokens = []
        
        while self.pos < self.length:
            char = self.expression[self.pos]
            
            # 공백 스킵
            if char.isspace():
                self.pos += 1
                continue
            
            # 숫자
            if char.isdigit() or (char == '.' and self.pos + 1 < self.length and 
                                   self.expression[self.pos + 1].isdigit()):
                tokens.append(self._read_number())
                continue
            
            # 문자열 (따옴표)
            if char in ('"', "'"):
                tokens.append(self._read_string())
                continue
            
            # 식별자 또는 함수
            if char.isalpha() or char == '_':
                tokens.append(self._read_identifier())
                continue
            
            # 비교 연산자 (2글자)
            if self.pos + 1 < self.length:
                two_char = self.expression[self.pos:self.pos + 2]
                if two_char in self.COMPARISONS:
                    tokens.append(Token(TokenType.COMPARISON, two_char, self.pos))
                    self.pos += 2
                    continue
            
            # 단일 비교 연산자
            if char in {'>', '<'}:
                tokens.append(Token(TokenType.COMPARISON, char, self.pos))
                self.pos += 1
                continue
            
            # 연산자
            if char in self.OPERATORS:
                tokens.append(Token(TokenType.OPERATOR, char, self.pos))
                self.pos += 1
                continue
            
            # 괄호
            if char == '(':
                tokens.append(Token(TokenType.LPAREN, '(', self.pos))
                self.pos += 1
                continue
            
            if char == ')':
                tokens.append(Token(TokenType.RPAREN, ')', self.pos))
                self.pos += 1
                continue
            
            # 쉼표
            if char == ',':
                tokens.append(Token(TokenType.COMMA, ',', self.pos))
                self.pos += 1
                continue
            
            raise ExpressionError(f"Unknown character '{char}' at position {self.pos}")
        
        tokens.append(Token(TokenType.EOF, None, self.pos))
        return tokens
    
    def _read_number(self) -> Token:
        """숫자 읽기"""
        start = self.pos
        has_dot = False
        
        while self.pos < self.length:
            char = self.expression[self.pos]
            if char.isdigit():
                self.pos += 1
            elif char == '.' and not has_dot:
                has_dot = True
                self.pos += 1
            else:
                break
        
        value = float(self.expression[start:self.pos])
        if not has_dot:
            value = int(value)
        
        return Token(TokenType.NUMBER, value, start)
    
    def _read_string(self) -> Token:
        """문자열 읽기"""
        quote = self.expression[self.pos]
        start = self.pos
        self.pos += 1  # Skip opening quote
        
        result = []
        while self.pos < self.length:
            char = self.expression[self.pos]
            if char == quote:
                self.pos += 1  # Skip closing quote
                return Token(TokenType.STRING, ''.join(result), start)
            elif char == '\\' and self.pos + 1 < self.length:
                self.pos += 1
                result.append(self.expression[self.pos])
            else:
                result.append(char)
            self.pos += 1
        
        raise ExpressionError(f"Unterminated string starting at position {start}")
    
    def _read_identifier(self) -> Token:
        """식별자 읽기"""
        start = self.pos
        
        while self.pos < self.length:
            char = self.expression[self.pos]
            if char.isalnum() or char == '_':
                self.pos += 1
            else:
                break
        
        return Token(TokenType.IDENTIFIER, self.expression[start:self.pos], start)


class Parser:
    """수식 파서 (AST 생성)"""
    
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
    
    @property
    def current(self) -> Token:
        return self.tokens[self.pos]
    
    def advance(self) -> Token:
        token = self.current
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return token
    
    def parse(self) -> Dict:
        """파싱 시작"""
        return self.parse_expression()
    
    def parse_expression(self) -> Dict:
        """비교 연산 파싱"""
        left = self.parse_additive()
        
        while self.current.type == TokenType.COMPARISON:
            op = self.advance().value
            right = self.parse_additive()
            left = {'type': 'comparison', 'op': op, 'left': left, 'right': right}
        
        return left
    
    def parse_additive(self) -> Dict:
        """덧셈/뺄셈 파싱"""
        left = self.parse_multiplicative()
        
        while self.current.type == TokenType.OPERATOR and self.current.value in ('+', '-'):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = {'type': 'binary', 'op': op, 'left': left, 'right': right}
        
        return left
    
    def parse_multiplicative(self) -> Dict:
        """곱셈/나눗셈 파싱"""
        left = self.parse_power()
        
        while self.current.type == TokenType.OPERATOR and self.current.value in ('*', '/', '%'):
            op = self.advance().value
            right = self.parse_power()
            left = {'type': 'binary', 'op': op, 'left': left, 'right': right}
        
        return left
    
    def parse_power(self) -> Dict:
        """거듭제곱 파싱"""
        left = self.parse_unary()
        
        if self.current.type == TokenType.OPERATOR and self.current.value == '^':
            self.advance()
            right = self.parse_power()  # 우결합
            return {'type': 'binary', 'op': '^', 'left': left, 'right': right}
        
        return left
    
    def parse_unary(self) -> Dict:
        """단항 연산 파싱"""
        if self.current.type == TokenType.OPERATOR and self.current.value == '-':
            self.advance()
            operand = self.parse_unary()
            return {'type': 'unary', 'op': '-', 'operand': operand}
        
        return self.parse_primary()
    
    def parse_primary(self) -> Dict:
        """기본 요소 파싱"""
        token = self.current
        
        # 숫자
        if token.type == TokenType.NUMBER:
            self.advance()
            return {'type': 'number', 'value': token.value}
        
        # 문자열
        if token.type == TokenType.STRING:
            self.advance()
            return {'type': 'string', 'value': token.value}
        
        # 식별자 (컬럼 또는 함수)
        if token.type == TokenType.IDENTIFIER:
            self.advance()
            
            # 함수 호출
            if self.current.type == TokenType.LPAREN:
                return self.parse_function_call(token.value)
            
            # 컬럼 참조
            return {'type': 'column', 'name': token.value}
        
        # 괄호
        if token.type == TokenType.LPAREN:
            self.advance()
            expr = self.parse_expression()
            if self.current.type != TokenType.RPAREN:
                raise ExpressionError(f"Expected ')' at position {self.current.position}")
            self.advance()
            return expr
        
        raise ExpressionError(f"Unexpected token '{token.value}' at position {token.position}")
    
    def parse_function_call(self, name: str) -> Dict:
        """함수 호출 파싱"""
        self.advance()  # Skip '('
        
        args = []
        if self.current.type != TokenType.RPAREN:
            args.append(self.parse_expression())
            
            while self.current.type == TokenType.COMMA:
                self.advance()
                args.append(self.parse_expression())
        
        if self.current.type != TokenType.RPAREN:
            raise ExpressionError(f"Expected ')' in function call at position {self.current.position}")
        self.advance()
        
        return {'type': 'function', 'name': name.upper(), 'args': args}


class ExpressionEngine:
    """
    수식 엔진
    
    Features:
    - 사칙연산, 비교 연산
    - 내장 함수 (ROUND, IF, CONCAT, DATE_DIFF 등)
    - 컬럼 참조
    - 계산 필드 추가
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
        pass
    
    def evaluate(self, expression: str, df: pl.DataFrame) -> pl.Series:
        """
        수식 평가
        
        Args:
            expression: 수식 문자열
            df: 데이터프레임
        
        Returns:
            계산된 Series
        """
        # 토큰화
        lexer = Lexer(expression)
        tokens = lexer.tokenize()
        
        # 파싱
        parser = Parser(tokens)
        ast = parser.parse()
        
        # 평가
        return self._evaluate_ast(ast, df)
    
    def _evaluate_ast(self, node: Dict, df: pl.DataFrame) -> pl.Series:
        """AST 평가"""
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
    
    def _evaluate_function(self, node: Dict, df: pl.DataFrame) -> pl.Series:
        """함수 평가"""
        func_name = node['name']
        args = [self._evaluate_ast(arg, df) for arg in node['args']]
        
        # Helper to get scalar value from Series
        def get_scalar(arg, default=None):
            if isinstance(arg, pl.Series):
                return arg[0] if len(arg) > 0 else default
            return arg
        
        # 수학 함수
        if func_name == 'ROUND':
            decimals = int(get_scalar(args[1], 0)) if len(args) > 1 else 0
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
            exp_val = get_scalar(args[1])
            
            # If base is a constant series (all same values)
            if isinstance(base, pl.Series) and base.n_unique() == 1:
                base_val = base[0]
                result_val = base_val ** exp_val
                return pl.Series([result_val] * len(base))
            
            return base.pow(exp_val)
        
        if func_name == 'LOG':
            return args[0].log()
        
        if func_name == 'LOG10':
            return args[0].log() / math.log(10)
        
        if func_name == 'EXP':
            return args[0].exp()
        
        if func_name == 'SIN':
            # Convert to numpy for trig, then back to Series
            import numpy as np
            arr = args[0].to_numpy()
            return pl.Series(np.sin(arr))
        
        if func_name == 'COS':
            import numpy as np
            arr = args[0].to_numpy()
            return pl.Series(np.cos(arr))
        
        if func_name == 'TAN':
            import numpy as np
            arr = args[0].to_numpy()
            return pl.Series(np.tan(arr))
        
        if func_name == 'MIN':
            # MIN with multiple arguments - element-wise minimum
            if len(args) == 1:
                # Single column - return scalar repeated
                min_val = args[0].min()
                return pl.Series([min_val] * len(args[0]))
            else:
                # Multiple columns - element-wise min
                result = args[0]
                for arg in args[1:]:
                    # Use zip_with for element-wise comparison
                    combined = pl.DataFrame({"a": result, "b": arg})
                    result = combined.select(pl.min_horizontal("a", "b"))["a"]
                return result
        
        if func_name == 'MAX':
            # MAX with multiple arguments - element-wise maximum
            if len(args) == 1:
                # Single column - return scalar repeated
                max_val = args[0].max()
                return pl.Series([max_val] * len(args[0]))
            else:
                # Multiple columns - element-wise max
                result = args[0]
                for arg in args[1:]:
                    combined = pl.DataFrame({"a": result, "b": arg})
                    result = combined.select(pl.max_horizontal("a", "b"))["a"]
                return result
        
        # 문자열 함수
        if func_name == 'CONCAT':
            result = args[0].cast(pl.Utf8)
            for arg in args[1:]:
                if isinstance(arg, pl.Series):
                    # Check if it's a constant string series
                    if arg.dtype == pl.Utf8 or arg.n_unique() == 1:
                        result = result + arg.cast(pl.Utf8)
                    else:
                        result = result + arg.cast(pl.Utf8)
                else:
                    result = result + str(arg)
            return result
        
        if func_name == 'UPPER':
            return args[0].str.to_uppercase()
        
        if func_name == 'LOWER':
            return args[0].str.to_lowercase()
        
        if func_name == 'LEN':
            return args[0].str.len_chars()
        
        if func_name == 'LEFT':
            n = int(get_scalar(args[1]))
            return args[0].str.head(n)
        
        if func_name == 'RIGHT':
            n = int(get_scalar(args[1]))
            return args[0].str.tail(n)
        
        if func_name == 'TRIM':
            return args[0].str.strip_chars()
        
        if func_name == 'REPLACE':
            old = str(get_scalar(args[1]))
            new = str(get_scalar(args[2]))
            return args[0].str.replace_all(old, new)
        
        if func_name == 'CONTAINS':
            # Check if string contains substring, returns boolean series
            substring = str(get_scalar(args[1]))
            return args[0].cast(pl.Utf8).str.contains(substring)
        
        if func_name == 'SUBSTRING':
            # SUBSTRING(str, start, length) - 1-based indexing like SQL
            start = int(get_scalar(args[1])) - 1  # Convert to 0-based
            length = int(get_scalar(args[2])) if len(args) > 2 else None
            if length is not None:
                return args[0].str.slice(start, length)
            else:
                return args[0].str.slice(start)
        
        # 조건 함수
        if func_name == 'IF':
            condition = args[0]
            then_value = args[1]
            else_value = args[2] if len(args) > 2 else pl.Series([None] * len(df))
            
            # Build result using numpy-style conditional
            result = []
            for i in range(len(condition)):
                if condition[i]:
                    result.append(then_value[i] if isinstance(then_value, pl.Series) else then_value)
                else:
                    result.append(else_value[i] if isinstance(else_value, pl.Series) else else_value)
            return pl.Series(result)
        
        if func_name == 'COALESCE':
            result = args[0]
            for arg in args[1:]:
                if isinstance(arg, pl.Series):
                    fill_val = arg[0] if arg.n_unique() == 1 else arg
                else:
                    fill_val = arg
                result = result.fill_null(fill_val)
            return result
        
        if func_name == 'ISNULL':
            return args[0].is_null()
        
        if func_name == 'IFNULL':
            return args[0].fill_null(args[1])
        
        # 날짜 함수
        if func_name == 'DATE_DIFF':
            end_date = args[0]
            start_date = args[1]
            unit = str(get_scalar(args[2]))
            
            diff = end_date - start_date
            if unit.lower() == 'days':
                return diff.dt.total_days()
            elif unit.lower() == 'hours':
                return diff.dt.total_hours()
            elif unit.lower() == 'minutes':
                return diff.dt.total_minutes()
            elif unit.lower() == 'seconds':
                return diff.dt.total_seconds()
            return diff.dt.total_days()
        
        if func_name == 'YEAR':
            return args[0].dt.year()
        
        if func_name == 'MONTH':
            return args[0].dt.month()
        
        if func_name == 'DAY':
            return args[0].dt.day()
        
        if func_name == 'WEEKDAY':
            return args[0].dt.weekday()
        
        if func_name == 'HOUR':
            return args[0].dt.hour()
        
        if func_name == 'MINUTE':
            return args[0].dt.minute()
        
        if func_name == 'SECOND':
            return args[0].dt.second()
        
        raise ExpressionError(f"Unknown function: {func_name}")
    
    def add_column(
        self, 
        df: pl.DataFrame, 
        column_name: str, 
        expression: str
    ) -> pl.DataFrame:
        """
        계산 필드 컬럼 추가
        
        Args:
            df: 원본 데이터프레임
            column_name: 새 컬럼 이름
            expression: 수식
        
        Returns:
            새 컬럼이 추가된 데이터프레임
        """
        result = self.evaluate(expression, df)
        return df.with_columns(result.alias(column_name))
    
    def validate(
        self, 
        expression: str, 
        df: pl.DataFrame
    ) -> Tuple[bool, Optional[str]]:
        """
        수식 유효성 검사
        
        Returns:
            (is_valid, error_message)
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
            return False, str(e)
        except Exception as e:
            return False, str(e)
    
    def _validate_ast(self, node: Dict, df: pl.DataFrame):
        """AST 유효성 검증"""
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
        """수식에서 참조하는 컬럼 목록 반환"""
        lexer = Lexer(expression)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()
        
        columns = []
        self._collect_columns(ast, columns)
        return list(set(columns))
    
    def _collect_columns(self, node: Dict, columns: List[str]):
        """AST에서 컬럼 참조 수집"""
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
