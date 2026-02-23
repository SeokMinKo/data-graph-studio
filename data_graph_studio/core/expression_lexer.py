"""
Expression lexer/parser — extracted from expression_engine.py

Contains: ExpressionError, TokenType, Token, Lexer, Parser
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List


class ExpressionError(Exception):
    """Raised when an expression cannot be tokenized, parsed, or evaluated."""


class TokenType(Enum):
    """Discriminator enum for Token variants produced by Lexer."""
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
    """Single lexical unit produced by Lexer.

    Attributes:
        type: TokenType discriminator.
        value: Raw value — int/float for NUMBER, str for all others, None for EOF.
        position: Byte offset in the original expression string.
    """
    type: TokenType
    value: Any
    position: int = 0


class Lexer:
    """Tokenizer for expression strings.

    Converts a raw expression string into a flat list of Token objects for
    consumption by Parser. Handles numbers, quoted strings, identifiers,
    arithmetic operators, comparison operators, parentheses, and commas.
    """

    OPERATORS = {'+', '-', '*', '/', '%', '^'}
    COMPARISONS = {'==', '!=', '>=', '<=', '>', '<'}

    def __init__(self, expression: str):
        """Initialize the lexer with the expression to tokenize.

        Input: expression — str, the raw expression string (may be empty).
        """
        self.expression = expression
        self.pos = 0
        self.length = len(expression)

    def tokenize(self) -> List[Token]:
        """Scan the expression and return all tokens including a terminal EOF.

        Output: List[Token] — ordered tokens; the last element is always
            Token(EOF, None). Two-character comparison operators are emitted as
            a single COMPARISON token before single-character ones are tried.
        Raises: ExpressionError — when an unrecognized character is encountered.
        Invariants: result[-1].type == TokenType.EOF.
        """
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
        """Consume a numeric literal from the current position and return a NUMBER token.

        Output: Token(NUMBER, int | float, start_pos) — int when no decimal point
            is present, float otherwise.
        Invariants: self.pos is advanced past the consumed digits and optional dot.
        """
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
        """Consume a quoted string literal (single or double quotes) and return a STRING token.

        Output: Token(STRING, str, start_pos) — the unquoted, backslash-unescaped content.
        Raises: ExpressionError — when the string is not closed before end of input.
        Invariants: self.pos is advanced past the closing quote.
        """
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
        """Consume an alphanumeric/underscore identifier and return an IDENTIFIER token.

        Output: Token(IDENTIFIER, str, start_pos) — the identifier text as-is.
        Invariants: self.pos is advanced past the last alphanumeric or underscore character.
        """
        start = self.pos

        while self.pos < self.length:
            char = self.expression[self.pos]
            if char.isalnum() or char == '_':
                self.pos += 1
            else:
                break

        return Token(TokenType.IDENTIFIER, self.expression[start:self.pos], start)


class Parser:
    """Recursive-descent parser that converts a token list into a nested AST dict.

    Precedence (lowest to highest): comparison → additive → multiplicative →
    power → unary → primary (number/string/column/function call/parenthesized expr).
    All AST nodes are plain dicts with a 'type' key.
    """

    def __init__(self, tokens: List[Token]):
        """Initialize the parser with a token stream from Lexer.

        Input: tokens — List[Token], must end with an EOF token.
        """
        self.tokens = tokens
        self.pos = 0

    @property
    def current(self) -> Token:
        """Return the token at the current parse position.

        Output: Token — the token at self.pos (never past the EOF token)
        """
        return self.tokens[self.pos]

    def advance(self) -> Token:
        """Return the current token and advance the position by one.

        Output: Token — the token that was current before advancing
        Invariants: pos is not incremented past len(tokens) - 1 (EOF is the last token)
        """
        token = self.current
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return token

    def parse(self) -> Dict:
        """Parse the full token stream and return the root AST node.

        Output: Dict — root AST node, same shape as parse_expression().
        Raises: ExpressionError — on any structural parse error.
        """
        return self.parse_expression()

    def parse_expression(self) -> Dict:
        """Parse a comparison expression (lowest precedence level).

        Output: Dict — {'type': 'comparison', 'op': str, 'left': Dict, 'right': Dict}
            when a comparison operator is present, otherwise the inner additive node.
        """
        left = self.parse_additive()

        while self.current.type == TokenType.COMPARISON:
            op = self.advance().value
            right = self.parse_additive()
            left = {'type': 'comparison', 'op': op, 'left': left, 'right': right}

        return left

    def parse_additive(self) -> Dict:
        """Parse addition and subtraction (left-associative).

        Output: Dict — {'type': 'binary', 'op': '+'/'-', 'left': Dict, 'right': Dict}
            or the inner multiplicative node when no + / - is present.
        """
        left = self.parse_multiplicative()

        while self.current.type == TokenType.OPERATOR and self.current.value in ('+', '-'):
            op = self.advance().value
            right = self.parse_multiplicative()
            left = {'type': 'binary', 'op': op, 'left': left, 'right': right}

        return left

    def parse_multiplicative(self) -> Dict:
        """Parse multiplication, division, and modulo (left-associative).

        Output: Dict — {'type': 'binary', 'op': '*'/'/'/'%', 'left': Dict, 'right': Dict}
            or the inner power node when none of those operators is present.
        """
        left = self.parse_power()

        while self.current.type == TokenType.OPERATOR and self.current.value in ('*', '/', '%'):
            op = self.advance().value
            right = self.parse_power()
            left = {'type': 'binary', 'op': op, 'left': left, 'right': right}

        return left

    def parse_power(self) -> Dict:
        """Parse exponentiation (right-associative via recursion).

        Output: Dict — {'type': 'binary', 'op': '^', 'left': Dict, 'right': Dict}
            or the inner unary node when no '^' is present.
        """
        left = self.parse_unary()

        if self.current.type == TokenType.OPERATOR and self.current.value == '^':
            self.advance()
            right = self.parse_power()  # 우결합
            return {'type': 'binary', 'op': '^', 'left': left, 'right': right}

        return left

    def parse_unary(self) -> Dict:
        """Parse a unary negation or delegate to parse_primary.

        Output: Dict — {'type': 'unary', 'op': '-', 'operand': Dict}
            when a leading minus is present, otherwise the inner primary node.
        """
        if self.current.type == TokenType.OPERATOR and self.current.value == '-':
            self.advance()
            operand = self.parse_unary()
            return {'type': 'unary', 'op': '-', 'operand': operand}

        return self.parse_primary()

    def parse_primary(self) -> Dict:
        """Parse a primary expression: number, string, column reference, function call, or parenthesized expression.

        Output: Dict — one of:
            {'type': 'number', 'value': int | float}
            {'type': 'string', 'value': str}
            {'type': 'column', 'name': str}
            {'type': 'function', 'name': str (uppercase), 'args': List[Dict]}
            or the inner expression for a parenthesized group.
        Raises: ExpressionError — on unexpected token or unmatched closing parenthesis.
        """
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
        """Parse a function call argument list and return a function AST node.

        Input: name — str, the function name as seen in the token stream
            (will be uppercased in the output node).
        Output: Dict — {'type': 'function', 'name': str (uppercase), 'args': List[Dict]},
            where each arg is a fully parsed expression node.
        Raises: ExpressionError — when the closing ')' is missing.
        Invariants: self.pos is advanced past the closing ')'.
        """
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
