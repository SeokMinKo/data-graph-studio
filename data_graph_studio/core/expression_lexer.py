"""
Expression lexer/parser — extracted from expression_engine.py

Contains: ExpressionError, TokenType, Token, Lexer, Parser
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List


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
        """Return the token at the current parse position."""
        return self.tokens[self.pos]

    def advance(self) -> Token:
        """Return the current token and advance the position by one."""
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
