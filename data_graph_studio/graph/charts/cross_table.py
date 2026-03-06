"""
Cross Table (Pivot Table) - 크로스 테이블/피벗 테이블
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import polars as pl


@dataclass
class CrossTableData:
    """크로스 테이블 데이터"""

    row_headers: List[Any]
    col_headers: List[Any]
    values: Dict[Tuple, Any]
    row_totals: Optional[Dict[Any, Any]] = None
    col_totals: Optional[Dict[Any, Any]] = None
    grand_total: Optional[Any] = None


class CrossTableCalculator:
    """
    크로스 테이블 계산기

    Spotfire의 Cross Table과 유사한 동적 피벗 기능을 제공합니다.
    """

    AGG_FUNCTIONS = {
        "sum": lambda col: pl.col(col).sum(),
        "mean": lambda col: pl.col(col).mean(),
        "median": lambda col: pl.col(col).median(),
        "min": lambda col: pl.col(col).min(),
        "max": lambda col: pl.col(col).max(),
        "count": lambda col: pl.col(col).count(),
        "count_distinct": lambda col: pl.col(col).n_unique(),
        "std": lambda col: pl.col(col).std(),
        "var": lambda col: pl.col(col).var(),
        "first": lambda col: pl.col(col).first(),
        "last": lambda col: pl.col(col).last(),
    }

    def calculate(
        self,
        data: pl.DataFrame,
        row_columns: List[str],
        col_columns: List[str],
        value_column: str,
        agg_func: str = "sum",
        show_row_totals: bool = False,
        show_col_totals: bool = False,
        sort_rows: bool = True,
        sort_cols: bool = True,
    ) -> Dict[str, Any]:
        """
        크로스 테이블 계산

        Args:
            data: 데이터프레임
            row_columns: 행 헤더 컬럼 목록 (계층 지원)
            col_columns: 열 헤더 컬럼 목록 (계층 지원)
            value_column: 값 컬럼
            agg_func: 집계 함수
            show_row_totals: 행 합계 표시
            show_col_totals: 열 합계 표시
            sort_rows: 행 정렬
            sort_cols: 열 정렬

        Returns:
            크로스 테이블 데이터
        """
        # 집계 함수 가져오기
        agg_expr = self.AGG_FUNCTIONS.get(agg_func, self.AGG_FUNCTIONS["sum"])(
            value_column
        )

        # 그룹화 컬럼
        group_cols = row_columns + col_columns

        # 피벗 실행
        pivoted = data.group_by(group_cols).agg(agg_expr.alias("_value_"))

        # 행/열 헤더 추출
        if row_columns:
            row_data = pivoted.select(row_columns).unique()
            if sort_rows:
                row_data = row_data.sort(row_columns)
            row_headers = [
                tuple(row) if len(row_columns) > 1 else row[0]
                for row in row_data.iter_rows()
            ]
        else:
            row_headers = [None]

        if col_columns:
            col_data = pivoted.select(col_columns).unique()
            if sort_cols:
                col_data = col_data.sort(col_columns)
            col_headers = [
                tuple(row) if len(col_columns) > 1 else row[0]
                for row in col_data.iter_rows()
            ]
        else:
            col_headers = [None]

        # 값 매트릭스 구성
        values = {}
        for row in pivoted.iter_rows(named=True):
            row_key = (
                tuple(row[c] for c in row_columns)
                if len(row_columns) > 1
                else (row[row_columns[0]] if row_columns else None)
            )
            col_key = (
                tuple(row[c] for c in col_columns)
                if len(col_columns) > 1
                else (row[col_columns[0]] if col_columns else None)
            )

            # 단일 값인 경우 튜플에서 추출
            if len(row_columns) == 1:
                row_key = row_key
            elif len(row_columns) == 0:
                row_key = None

            if len(col_columns) == 1:
                col_key = col_key
            elif len(col_columns) == 0:
                col_key = None

            values[(row_key, col_key)] = row["_value_"]

        # 합계 계산
        row_totals = None
        col_totals = None
        grand_total = None

        if show_row_totals and row_columns:
            row_totals = {}
            for rh in row_headers:
                total = sum(values.get((rh, ch), 0) or 0 for ch in col_headers)
                row_totals[rh] = total

        if show_col_totals and col_columns:
            col_totals = {}
            for ch in col_headers:
                total = sum(values.get((rh, ch), 0) or 0 for rh in row_headers)
                col_totals[ch] = total

        if show_row_totals and show_col_totals:
            grand_total = sum(values.values())

        return {
            "row_headers": row_headers,
            "col_headers": col_headers,
            "values": values,
            "row_totals": row_totals,
            "col_totals": col_totals,
            "grand_total": grand_total,
            "row_columns": row_columns,
            "col_columns": col_columns,
            "value_column": value_column,
            "agg_func": agg_func,
        }

    def get_cell_value(self, result: Dict[str, Any], row_key: Any, col_key: Any) -> Any:
        """특정 셀의 값 반환"""
        return result["values"].get((row_key, col_key))

    def to_dataframe(self, result: Dict[str, Any]) -> pl.DataFrame:
        """
        결과를 데이터프레임으로 변환

        Returns:
            피벗된 데이터프레임
        """
        row_headers = result["row_headers"]
        col_headers = result["col_headers"]
        values = result["values"]

        # 데이터 구성
        data_dict = {}

        # 행 헤더 컬럼
        if result["row_columns"]:
            if len(result["row_columns"]) == 1:
                data_dict[result["row_columns"][0]] = row_headers
            else:
                for i, col in enumerate(result["row_columns"]):
                    data_dict[col] = [
                        rh[i] if isinstance(rh, tuple) else rh for rh in row_headers
                    ]

        # 값 컬럼
        for ch in col_headers:
            col_name = str(ch) if ch is not None else "Value"
            col_values = []
            for rh in row_headers:
                col_values.append(values.get((rh, ch)))
            data_dict[col_name] = col_values

        # 행 합계
        if result["row_totals"]:
            data_dict["Total"] = [result["row_totals"].get(rh) for rh in row_headers]

        return pl.DataFrame(data_dict)

    def format_value(self, value: Any, format_string: Optional[str] = None) -> str:
        """값 포맷팅"""
        if value is None:
            return ""

        if format_string:
            try:
                return format_string.format(value)
            except (ValueError, TypeError):
                return str(value)

        if isinstance(value, float):
            return f"{value:,.2f}"
        return str(value)


class CrossTableWidget:
    """
    크로스 테이블 위젯 데이터

    UI 렌더링에 필요한 데이터를 제공합니다.
    """

    def __init__(self, calculator: CrossTableCalculator = None):
        self.calculator = calculator or CrossTableCalculator()
        self._result: Optional[Dict[str, Any]] = None

    def set_data(
        self,
        data: pl.DataFrame,
        row_columns: List[str],
        col_columns: List[str],
        value_column: str,
        **kwargs,
    ) -> None:
        """데이터 설정"""
        self._result = self.calculator.calculate(
            data, row_columns, col_columns, value_column, **kwargs
        )

    def get_row_count(self) -> int:
        """행 수 (헤더 제외)"""
        if not self._result:
            return 0
        return len(self._result["row_headers"])

    def get_col_count(self) -> int:
        """열 수 (헤더 제외)"""
        if not self._result:
            return 0
        return len(self._result["col_headers"])

    def get_cell(self, row: int, col: int) -> Any:
        """셀 값"""
        if not self._result:
            return None

        row_key = self._result["row_headers"][row]
        col_key = self._result["col_headers"][col]

        return self._result["values"].get((row_key, col_key))

    def get_row_header(self, row: int) -> Any:
        """행 헤더"""
        if not self._result:
            return None
        return self._result["row_headers"][row]

    def get_col_header(self, col: int) -> Any:
        """열 헤더"""
        if not self._result:
            return None
        return self._result["col_headers"][col]
