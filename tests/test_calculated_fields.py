"""
Tests for Calculated Fields / Expression Engine
"""

import pytest
import polars as pl
import numpy as np
from datetime import datetime, date, timedelta

from data_graph_studio.core.expression_engine import ExpressionEngine, ExpressionError


class TestExpressionParsing:
    """수식 파싱 테스트"""
    
    @pytest.fixture
    def engine(self):
        return ExpressionEngine()
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'Price': [100, 200, 300, 400, 500],
            'Quantity': [10, 20, 30, 40, 50],
            'Discount': [0.1, 0.2, 0.15, 0.05, 0.25],
            'Name': ['A', 'B', 'C', 'D', 'E'],
            'Date': [date(2024, 1, i) for i in range(1, 6)],
        })
    
    def test_simple_multiplication(self, engine, sample_df):
        """단순 곱셈: Price * Quantity"""
        result = engine.evaluate("Price * Quantity", sample_df)
        expected = [1000, 4000, 9000, 16000, 25000]
        assert result.to_list() == expected
    
    def test_addition(self, engine, sample_df):
        """덧셈: Price + 50"""
        result = engine.evaluate("Price + 50", sample_df)
        expected = [150, 250, 350, 450, 550]
        assert result.to_list() == expected
    
    def test_subtraction(self, engine, sample_df):
        """뺄셈: Price - 100"""
        result = engine.evaluate("Price - 100", sample_df)
        expected = [0, 100, 200, 300, 400]
        assert result.to_list() == expected
    
    def test_division(self, engine, sample_df):
        """나눗셈: Price / Quantity"""
        result = engine.evaluate("Price / Quantity", sample_df)
        expected = [10.0, 10.0, 10.0, 10.0, 10.0]
        assert result.to_list() == expected
    
    def test_complex_expression(self, engine, sample_df):
        """복잡한 수식: Price * Quantity * (1 - Discount)"""
        result = engine.evaluate("Price * Quantity * (1 - Discount)", sample_df)
        # 100*10*0.9=900, 200*20*0.8=3200, 300*30*0.85=7650, 400*40*0.95=15200, 500*50*0.75=18750
        expected = [900.0, 3200.0, 7650.0, 15200.0, 18750.0]
        assert result.to_list() == expected
    
    def test_parentheses_priority(self, engine, sample_df):
        """괄호 우선순위: (Price + 100) * 2"""
        result = engine.evaluate("(Price + 100) * 2", sample_df)
        expected = [400, 600, 800, 1000, 1200]
        assert result.to_list() == expected
    
    def test_negative_number(self, engine, sample_df):
        """음수: -Price"""
        result = engine.evaluate("-Price", sample_df)
        expected = [-100, -200, -300, -400, -500]
        assert result.to_list() == expected


class TestBuiltInFunctions:
    """내장 함수 테스트"""
    
    @pytest.fixture
    def engine(self):
        return ExpressionEngine()
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'Value': [10.567, 20.234, 30.789, 40.123, 50.456],
            'Negative': [-5, 10, -15, 20, -25],
            'Text1': ['Hello', 'World', 'Foo', 'Bar', 'Baz'],
            'Text2': [' World', ' Python', ' Bar', ' Baz', ' Qux'],
            'Score': [85, 92, 78, 65, 95],
            'StartDate': [date(2024, 1, 1), date(2024, 2, 15), date(2024, 3, 10), 
                          date(2024, 4, 20), date(2024, 5, 30)],
            'EndDate': [date(2024, 1, 10), date(2024, 2, 20), date(2024, 3, 25),
                        date(2024, 5, 1), date(2024, 6, 15)],
        })
    
    def test_round_function(self, engine, sample_df):
        """ROUND 함수"""
        result = engine.evaluate("ROUND(Value, 1)", sample_df)
        expected = [10.6, 20.2, 30.8, 40.1, 50.5]
        assert result.to_list() == expected
    
    def test_round_to_integer(self, engine, sample_df):
        """ROUND 정수로"""
        result = engine.evaluate("ROUND(Value, 0)", sample_df)
        expected = [11.0, 20.0, 31.0, 40.0, 50.0]
        assert result.to_list() == expected
    
    def test_floor_function(self, engine, sample_df):
        """FLOOR 함수"""
        result = engine.evaluate("FLOOR(Value)", sample_df)
        expected = [10, 20, 30, 40, 50]
        assert result.to_list() == expected
    
    def test_ceil_function(self, engine, sample_df):
        """CEIL 함수"""
        result = engine.evaluate("CEIL(Value)", sample_df)
        expected = [11, 21, 31, 41, 51]
        assert result.to_list() == expected
    
    def test_abs_function(self, engine, sample_df):
        """ABS 함수"""
        result = engine.evaluate("ABS(Negative)", sample_df)
        expected = [5, 10, 15, 20, 25]
        assert result.to_list() == expected
    
    def test_sqrt_function(self, engine, sample_df):
        """SQRT 함수"""
        result = engine.evaluate("SQRT(Score)", sample_df)
        # sqrt(85)=9.22, sqrt(92)=9.59, sqrt(78)=8.83, sqrt(65)=8.06, sqrt(95)=9.75
        assert all(8.0 <= v <= 10.0 for v in result.to_list())
    
    def test_power_function(self, engine, sample_df):
        """POWER 함수"""
        result = engine.evaluate("POWER(2, 3)", sample_df)
        assert all(v == 8.0 for v in result.to_list())
    
    def test_log_function(self, engine, sample_df):
        """LOG 함수 (자연로그)"""
        result = engine.evaluate("LOG(Score)", sample_df)
        # log(85)=4.44, log(92)=4.52, log(78)=4.36, log(65)=4.17, log(95)=4.55
        assert all(4.0 <= v <= 5.0 for v in result.to_list())


class TestStringFunctions:
    """문자열 함수 테스트"""
    
    @pytest.fixture
    def engine(self):
        return ExpressionEngine()
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'FirstName': ['John', 'Jane', 'Bob', 'Alice', 'Charlie'],
            'LastName': ['Doe', 'Smith', 'Johnson', 'Williams', 'Brown'],
            'Email': ['JOHN@EMAIL.COM', 'jane@email.com', 'BOB@test.org', 
                      'alice@demo.net', 'charlie@sample.io'],
        })
    
    def test_concat_function(self, engine, sample_df):
        """CONCAT 함수"""
        result = engine.evaluate("CONCAT(FirstName, ' ', LastName)", sample_df)
        expected = ['John Doe', 'Jane Smith', 'Bob Johnson', 'Alice Williams', 'Charlie Brown']
        assert result.to_list() == expected
    
    def test_upper_function(self, engine, sample_df):
        """UPPER 함수"""
        result = engine.evaluate("UPPER(FirstName)", sample_df)
        expected = ['JOHN', 'JANE', 'BOB', 'ALICE', 'CHARLIE']
        assert result.to_list() == expected
    
    def test_lower_function(self, engine, sample_df):
        """LOWER 함수"""
        result = engine.evaluate("LOWER(Email)", sample_df)
        expected = ['john@email.com', 'jane@email.com', 'bob@test.org', 
                    'alice@demo.net', 'charlie@sample.io']
        assert result.to_list() == expected
    
    def test_len_function(self, engine, sample_df):
        """LEN 함수"""
        result = engine.evaluate("LEN(FirstName)", sample_df)
        expected = [4, 4, 3, 5, 7]
        assert result.to_list() == expected
    
    def test_left_function(self, engine, sample_df):
        """LEFT 함수"""
        result = engine.evaluate("LEFT(FirstName, 2)", sample_df)
        expected = ['Jo', 'Ja', 'Bo', 'Al', 'Ch']
        assert result.to_list() == expected
    
    def test_right_function(self, engine, sample_df):
        """RIGHT 함수"""
        result = engine.evaluate("RIGHT(Email, 3)", sample_df)
        expected = ['COM', 'com', 'org', 'net', '.io']
        assert result.to_list() == expected
    
    def test_trim_function(self, engine, sample_df):
        """TRIM 함수"""
        df = pl.DataFrame({'Text': ['  hello  ', 'world  ', '  test']})
        result = engine.evaluate("TRIM(Text)", df)
        expected = ['hello', 'world', 'test']
        assert result.to_list() == expected
    
    def test_replace_function(self, engine, sample_df):
        """REPLACE 함수"""
        result = engine.evaluate("REPLACE(Email, '@', '[at]')", sample_df)
        assert '[at]' in result[0]


class TestConditionalFunctions:
    """조건 함수 테스트"""
    
    @pytest.fixture
    def engine(self):
        return ExpressionEngine()
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'Score': [85, 92, 78, 65, 95],
            'Status': ['Active', 'Inactive', 'Active', 'Pending', 'Active'],
            'Value': [None, 100, None, 200, 300],
        })
    
    def test_if_function_numeric(self, engine, sample_df):
        """IF 함수 (숫자 조건)"""
        result = engine.evaluate("IF(Score >= 90, 'A', 'B')", sample_df)
        expected = ['B', 'A', 'B', 'B', 'A']
        assert result.to_list() == expected
    
    def test_if_function_string(self, engine, sample_df):
        """IF 함수 (문자열 조건)"""
        result = engine.evaluate("IF(Status == 'Active', 1, 0)", sample_df)
        expected = [1, 0, 1, 0, 1]
        assert result.to_list() == expected
    
    def test_if_nested(self, engine, sample_df):
        """중첩 IF: IF(Score >= 90, 'A', IF(Score >= 80, 'B', 'C'))"""
        result = engine.evaluate("IF(Score >= 90, 'A', IF(Score >= 80, 'B', 'C'))", sample_df)
        expected = ['B', 'A', 'C', 'C', 'A']
        assert result.to_list() == expected
    
    def test_coalesce_function(self, engine, sample_df):
        """COALESCE 함수 (NULL 대체)"""
        result = engine.evaluate("COALESCE(Value, 0)", sample_df)
        expected = [0, 100, 0, 200, 300]
        assert result.to_list() == expected
    
    def test_isnull_function(self, engine, sample_df):
        """ISNULL 함수"""
        result = engine.evaluate("ISNULL(Value)", sample_df)
        expected = [True, False, True, False, False]
        assert result.to_list() == expected


class TestDateFunctions:
    """날짜 함수 테스트"""
    
    @pytest.fixture
    def engine(self):
        return ExpressionEngine()
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'StartDate': [date(2024, 1, 15), date(2024, 3, 20), date(2024, 6, 10),
                          date(2024, 9, 5), date(2024, 12, 25)],
            'EndDate': [date(2024, 2, 15), date(2024, 4, 20), date(2024, 7, 10),
                        date(2024, 10, 5), date(2025, 1, 25)],
        })
    
    def test_date_diff_days(self, engine, sample_df):
        """DATE_DIFF 함수 (일수 차이)"""
        result = engine.evaluate("DATE_DIFF(EndDate, StartDate, 'days')", sample_df)
        expected = [31, 31, 30, 30, 31]
        assert result.to_list() == expected
    
    def test_year_function(self, engine, sample_df):
        """YEAR 함수"""
        result = engine.evaluate("YEAR(StartDate)", sample_df)
        expected = [2024, 2024, 2024, 2024, 2024]
        assert result.to_list() == expected
    
    def test_month_function(self, engine, sample_df):
        """MONTH 함수"""
        result = engine.evaluate("MONTH(StartDate)", sample_df)
        expected = [1, 3, 6, 9, 12]
        assert result.to_list() == expected
    
    def test_day_function(self, engine, sample_df):
        """DAY 함수"""
        result = engine.evaluate("DAY(StartDate)", sample_df)
        expected = [15, 20, 10, 5, 25]
        assert result.to_list() == expected
    
    def test_weekday_function(self, engine, sample_df):
        """WEEKDAY 함수"""
        result = engine.evaluate("WEEKDAY(StartDate)", sample_df)
        # 2024-01-15=Monday(0), 2024-03-20=Wednesday(2), ...
        assert all(0 <= v <= 6 for v in result.to_list())


class TestAddCalculatedColumn:
    """계산 필드 추가 테스트"""
    
    @pytest.fixture
    def engine(self):
        return ExpressionEngine()
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'Price': [100, 200, 300],
            'Quantity': [10, 20, 30],
        })
    
    def test_add_calculated_column(self, engine, sample_df):
        """새 컬럼 추가"""
        new_df = engine.add_column(sample_df, "Total", "Price * Quantity")
        assert "Total" in new_df.columns
        assert new_df["Total"].to_list() == [1000, 4000, 9000]
    
    def test_multiple_calculated_columns(self, engine, sample_df):
        """여러 계산 컬럼 추가"""
        new_df = sample_df.clone()
        new_df = engine.add_column(new_df, "Total", "Price * Quantity")
        new_df = engine.add_column(new_df, "UnitPrice", "Total / Quantity")
        assert "Total" in new_df.columns
        assert "UnitPrice" in new_df.columns
        assert new_df["UnitPrice"].to_list() == [100.0, 200.0, 300.0]
    
    def test_expression_with_new_column(self, engine, sample_df):
        """새 컬럼을 사용하는 수식"""
        new_df = engine.add_column(sample_df, "Total", "Price * Quantity")
        new_df = engine.add_column(new_df, "Tax", "Total * 0.1")
        assert new_df["Tax"].to_list() == [100.0, 400.0, 900.0]


class TestExpressionValidation:
    """수식 유효성 검사 테스트"""
    
    @pytest.fixture
    def engine(self):
        return ExpressionEngine()
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'Price': [100, 200, 300],
        })
    
    def test_validate_valid_expression(self, engine, sample_df):
        """유효한 수식 검증"""
        is_valid, error = engine.validate("Price * 2", sample_df)
        assert is_valid is True
        assert error is None
    
    def test_validate_invalid_column(self, engine, sample_df):
        """존재하지 않는 컬럼"""
        is_valid, error = engine.validate("NonExistent * 2", sample_df)
        assert is_valid is False
        assert "NonExistent" in error
    
    def test_validate_syntax_error(self, engine, sample_df):
        """문법 오류"""
        is_valid, error = engine.validate("Price * * 2", sample_df)
        assert is_valid is False
    
    def test_validate_unknown_function(self, engine, sample_df):
        """알 수 없는 함수"""
        is_valid, error = engine.validate("UNKNOWN_FUNC(Price)", sample_df)
        assert is_valid is False
        assert "UNKNOWN_FUNC" in error


class TestExpressionError:
    """수식 오류 처리 테스트"""
    
    @pytest.fixture
    def engine(self):
        return ExpressionEngine()
    
    def test_division_by_zero(self, engine):
        """0으로 나누기"""
        df = pl.DataFrame({'A': [10, 20, 30], 'B': [2, 0, 5]})
        result = engine.evaluate("A / B", df)
        # Polars returns inf for division by zero
        assert result[1] == float('inf')
    
    def test_empty_dataframe(self, engine):
        """빈 데이터프레임"""
        df = pl.DataFrame({'A': []})
        result = engine.evaluate("A * 2", df)
        assert len(result) == 0
    
    def test_null_handling(self, engine):
        """NULL 처리"""
        df = pl.DataFrame({'A': [10, None, 30]})
        result = engine.evaluate("A * 2", df)
        assert result[0] == 20
        assert result[1] is None
        assert result[2] == 60
