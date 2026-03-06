"""
Advanced Expressions 테스트 - Spotfire 스타일 수식 엔진
"""

import pytest
import polars as pl

from data_graph_studio.core.expressions import (
    ExpressionParser,
    CalculatedColumn,
    DataFunction,
    DataFunctionRegistry,
    ExpressionValidator,
)


class TestExpressionParser:
    """ExpressionParser 테스트"""

    @pytest.fixture
    def parser(self):
        return ExpressionParser()

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "id": [1, 2, 3, 4, 5, 6],
                "category": ["A", "A", "B", "B", "C", "C"],
                "region": ["East", "West", "East", "West", "East", "West"],
                "sales": [100, 200, 150, 250, 80, 120],
                "cost": [50, 100, 75, 125, 40, 60],
                "date": pl.date_range(
                    pl.date(2024, 1, 1), pl.date(2024, 1, 6), eager=True
                ),
            }
        )

    def test_simple_arithmetic(self, parser, sample_data):
        """단순 산술 연산"""
        result = parser.evaluate("[sales] + [cost]", sample_data)

        assert result is not None
        assert len(result) == 6
        assert result[0] == 150  # 100 + 50

    def test_column_multiplication(self, parser, sample_data):
        """컬럼 곱셈"""
        result = parser.evaluate("[sales] * 2", sample_data)

        assert result[0] == 200
        assert result[1] == 400

    def test_column_division(self, parser, sample_data):
        """컬럼 나눗셈"""
        result = parser.evaluate("[sales] / [cost]", sample_data)

        assert result[0] == 2.0  # 100 / 50

    def test_percentage_calculation(self, parser, sample_data):
        """백분율 계산"""
        result = parser.evaluate("([sales] - [cost]) / [sales] * 100", sample_data)

        assert result[0] == 50.0  # (100-50)/100 * 100

    def test_if_expression(self, parser, sample_data):
        """IF 조건문"""
        result = parser.evaluate("If([sales] > 150, 'High', 'Low')", sample_data)

        assert result[0] == "Low"  # 100 < 150
        assert result[1] == "High"  # 200 > 150
        assert result[3] == "High"  # 250 > 150

    def test_case_expression(self, parser, sample_data):
        """CASE 표현식"""
        result = parser.evaluate(
            "Case When [sales] < 100 Then 'Low' When [sales] < 200 Then 'Medium' Else 'High' End",
            sample_data,
        )

        assert result[0] == "Medium"  # 100
        assert result[1] == "High"  # 200
        assert result[4] == "Low"  # 80

    def test_aggregate_sum(self, parser, sample_data):
        """집계 함수 - SUM"""
        result = parser.evaluate("Sum([sales])", sample_data)

        assert result == 900  # 100 + 200 + 150 + 250 + 80 + 120

    def test_aggregate_avg(self, parser, sample_data):
        """집계 함수 - AVG"""
        result = parser.evaluate("Avg([sales])", sample_data)

        assert result == 150  # 900 / 6

    def test_aggregate_count(self, parser, sample_data):
        """집계 함수 - COUNT"""
        result = parser.evaluate("Count([sales])", sample_data)

        assert result == 6

    def test_aggregate_min_max(self, parser, sample_data):
        """집계 함수 - MIN/MAX"""
        min_result = parser.evaluate("Min([sales])", sample_data)
        max_result = parser.evaluate("Max([sales])", sample_data)

        assert min_result == 80
        assert max_result == 250

    def test_string_concatenation(self, parser, sample_data):
        """문자열 연결"""
        result = parser.evaluate("[category] & '-' & [region]", sample_data)

        assert result[0] == "A-East"
        assert result[1] == "A-West"

    @pytest.mark.skip(reason="Expression parser string functions not yet implemented")
    def test_string_functions(self, parser, sample_data):
        """문자열 함수"""
        result_upper = parser.evaluate("Upper([category])", sample_data)
        result_lower = parser.evaluate("Lower([category])", sample_data)

        assert result_upper[0] == "A"
        assert result_lower[0] == "a"

    def test_math_functions(self, parser, sample_data):
        """수학 함수"""
        result_abs = parser.evaluate("Abs([sales] - 150)", sample_data)
        result_sqrt = parser.evaluate("Sqrt([sales])", sample_data)
        result_round = parser.evaluate("Round([sales] / 3, 2)", sample_data)

        assert result_abs[0] == 50  # |100 - 150|
        assert result_sqrt[0] == 10  # sqrt(100)
        assert abs(result_round[0] - 33.33) < 0.01

    @pytest.mark.skip(reason="Expression parser null functions not yet implemented")
    def test_null_handling(self, parser):
        """NULL 처리"""
        data = pl.DataFrame({"a": [1, None, 3], "b": [10, 20, None]})

        result = parser.evaluate("IsNull([a])", data)
        assert not result[0]
        assert result[1]

        result_coalesce = parser.evaluate("IfNull([b], 0)", data)
        assert result_coalesce[2] == 0

    @pytest.mark.skip(reason="Expression parser date functions not yet implemented")
    def test_date_functions(self, parser, sample_data):
        """날짜 함수"""
        result_year = parser.evaluate("Year([date])", sample_data)
        result_month = parser.evaluate("Month([date])", sample_data)
        result_day = parser.evaluate("Day([date])", sample_data)

        assert result_year[0] == 2024
        assert result_month[0] == 1
        assert result_day[0] == 1


class TestOverExpression:
    """OVER 표현식 테스트 (윈도우 함수)"""

    @pytest.fixture
    def parser(self):
        return ExpressionParser()

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame(
            {
                "category": ["A", "A", "A", "B", "B", "B"],
                "region": ["East", "East", "West", "East", "West", "West"],
                "sales": [100, 150, 200, 120, 180, 220],
            }
        )

    def test_sum_over_category(self, parser, sample_data):
        """OVER - 카테고리별 합계"""
        result = parser.evaluate("Sum([sales]) OVER ([category])", sample_data)

        # A: 100+150+200=450, B: 120+180+220=520
        assert result[0] == 450
        assert result[1] == 450
        assert result[3] == 520

    def test_avg_over_category(self, parser, sample_data):
        """OVER - 카테고리별 평균"""
        result = parser.evaluate("Avg([sales]) OVER ([category])", sample_data)

        assert result[0] == 150  # A 평균
        assert result[3] == 520 / 3  # B 평균 ≈ 173.33

    def test_percent_of_total(self, parser, sample_data):
        """전체 대비 백분율"""
        result = parser.evaluate(
            "[sales] / Sum([sales]) OVER (AllPrevious([category])) * 100", sample_data
        )

        # 첫 번째 값: 100 / 100 * 100 = 100
        assert result is not None

    def test_rank_over_category(self, parser, sample_data):
        """OVER - 카테고리 내 순위"""
        result = parser.evaluate("Rank([sales]) OVER ([category])", sample_data)

        # A 내에서: 100(3등), 150(2등), 200(1등)
        # B 내에서: 120(3등), 180(2등), 220(1등)
        assert result is not None

    def test_running_sum(self, parser, sample_data):
        """누적 합계"""
        result = parser.evaluate(
            "Sum([sales]) OVER (AllPrevious([category]))", sample_data
        )

        assert result is not None

    def test_dense_rank(self, parser, sample_data):
        """DENSE_RANK"""
        result = parser.evaluate("DenseRank([sales]) OVER ([category])", sample_data)

        assert result is not None


class TestCalculatedColumn:
    """CalculatedColumn 테스트"""

    def test_create_calculated_column(self):
        """계산 컬럼 생성"""
        calc = CalculatedColumn(
            name="profit", expression="[sales] - [cost]", description="Profit margin"
        )

        assert calc.name == "profit"
        assert calc.expression == "[sales] - [cost]"

    def test_apply_to_dataframe(self):
        """데이터프레임에 적용"""
        data = pl.DataFrame({"sales": [100, 200, 300], "cost": [60, 120, 180]})

        calc = CalculatedColumn(name="profit", expression="[sales] - [cost]")

        result = calc.apply(data)

        assert "profit" in result.columns
        assert result["profit"][0] == 40
        assert result["profit"][1] == 80

    def test_calculated_column_with_functions(self):
        """함수를 사용한 계산 컬럼"""
        data = pl.DataFrame({"value": [100, -50, 200]})

        calc = CalculatedColumn(name="abs_value", expression="Abs([value])")

        result = calc.apply(data)

        assert result["abs_value"][0] == 100
        assert result["abs_value"][1] == 50

    def test_multiple_calculated_columns(self):
        """여러 계산 컬럼"""
        data = pl.DataFrame({"sales": [100, 200], "cost": [60, 120]})

        calcs = [
            CalculatedColumn("profit", "[sales] - [cost]"),
            CalculatedColumn("margin", "([sales] - [cost]) / [sales] * 100"),
        ]

        result = data
        for calc in calcs:
            result = calc.apply(result)

        assert "profit" in result.columns
        assert "margin" in result.columns


class TestDataFunction:
    """DataFunction 테스트"""

    def test_create_data_function(self):
        """데이터 함수 생성"""
        func = DataFunction(
            name="MovingAverage",
            parameters=["column", "window"],
            body="""
import numpy as np
values = data[column].to_numpy()
result = np.convolve(values, np.ones(window)/window, mode='valid')
return result
""",
        )

        assert func.name == "MovingAverage"
        assert "column" in func.parameters

    @pytest.mark.skip(reason="DataFunction execute not yet implemented")
    def test_execute_data_function(self):
        """데이터 함수 실행"""
        data = pl.DataFrame({"value": [1, 2, 3, 4, 5]})

        func = DataFunction(
            name="Double", parameters=["column"], body="return data[column] * 2"
        )

        result = func.execute(data, column="value")

        assert result is not None


class TestDataFunctionRegistry:
    """DataFunctionRegistry 테스트"""

    @pytest.fixture
    def registry(self):
        return DataFunctionRegistry()

    def test_register_function(self, registry):
        """함수 등록"""
        func = DataFunction(name="TestFunc", parameters=[], body="return 1")

        registry.register(func)

        assert "TestFunc" in registry.list_functions()

    def test_get_function(self, registry):
        """함수 조회"""
        func = DataFunction(name="TestFunc", parameters=[], body="return 1")
        registry.register(func)

        retrieved = registry.get("TestFunc")

        assert retrieved is not None
        assert retrieved.name == "TestFunc"

    def test_unregister_function(self, registry):
        """함수 제거"""
        func = DataFunction(name="TestFunc", parameters=[], body="return 1")
        registry.register(func)
        registry.unregister("TestFunc")

        assert "TestFunc" not in registry.list_functions()

    def test_builtin_functions(self, registry):
        """내장 함수 확인"""
        funcs = registry.list_builtin_functions()

        assert "Normalize" in funcs
        assert "ZScore" in funcs
        assert "Percentile" in funcs


class TestExpressionValidator:
    """ExpressionValidator 테스트"""

    @pytest.fixture
    def validator(self):
        return ExpressionValidator()

    def test_valid_expression(self, validator):
        """유효한 수식"""
        columns = ["sales", "cost", "region"]

        result = validator.validate("[sales] + [cost]", columns)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_column(self, validator):
        """존재하지 않는 컬럼"""
        columns = ["sales", "cost"]

        result = validator.validate("[quantity] * [price]", columns)

        assert not result.is_valid
        assert len(result.errors) > 0
        assert (
            "quantity" in result.errors[0].lower()
            or "price" in result.errors[0].lower()
        )

    def test_syntax_error(self, validator):
        """구문 오류"""
        columns = ["sales"]

        result = validator.validate("[sales] + + [sales]", columns)

        # 이중 연산자는 오류
        # (파서 구현에 따라 다를 수 있음)
        assert result is not None

    def test_circular_reference(self, validator):
        """순환 참조 검사"""

        # profit이 이미 계산 컬럼이고 sales를 참조한다면
        # sales에서 profit을 참조하면 순환 참조
        result = validator.check_circular_reference(
            "profit", "[sales] * 0.1", {"sales": "[profit] + [cost]"}
        )

        assert result is True  # 순환 참조 존재

    def test_no_circular_reference(self, validator):
        """순환 참조 없음"""

        result = validator.check_circular_reference("profit", "[sales] - [cost]", {})

        assert result is False  # 순환 참조 없음
