"""
Horizontal Bar Chart - 수평 막대 차트
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class HorizontalBarResult:
    """수평 막대 차트 계산 결과"""
    y_positions: List[float]
    widths: List[float]
    categories: List[str]
    sorted_categories: List[str]
    sorted_values: List[float]
    colors: Optional[List[str]] = None


class HorizontalBarChart:
    """
    수평 막대 차트

    긴 레이블이나 순위 표시에 적합합니다.
    """

    def __init__(self):
        self.bar_height: float = 0.8
        self.spacing: float = 0.2

    def calculate(
        self,
        categories: List[str],
        values: List[float],
        sort_by_value: bool = False,
        descending: bool = True,
        colors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        수평 막대 차트 데이터 계산

        Args:
            categories: 카테고리 목록
            values: 값 목록
            sort_by_value: 값으로 정렬 여부
            descending: 내림차순 여부
            colors: 색상 목록

        Returns:
            차트 데이터
        """
        n = len(categories)

        # 정렬
        if sort_by_value:
            sorted_pairs = sorted(
                zip(categories, values),
                key=lambda x: x[1],
                reverse=descending
            )
            sorted_categories = [p[0] for p in sorted_pairs]
            sorted_values = [p[1] for p in sorted_pairs]
        else:
            sorted_categories = list(categories)
            sorted_values = list(values)

        # Y 위치 계산 (위에서 아래로)
        y_positions = list(range(n))

        return {
            "y_positions": y_positions,
            "widths": sorted_values,
            "categories": categories,
            "sorted_categories": sorted_categories,
            "sorted_values": sorted_values,
            "bar_height": self.bar_height,
            "colors": colors
        }

    def get_bar_rects(
        self,
        categories: List[str],
        values: List[float],
        width: float,
        height: float,
        margin: float = 0.1,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        실제 그리기용 사각형 좌표 계산

        Args:
            categories: 카테고리 목록
            values: 값 목록
            width: 전체 너비
            height: 전체 높이
            margin: 여백 비율

        Returns:
            사각형 정보 목록
        """
        result = self.calculate(categories, values, **kwargs)

        n = len(result["sorted_categories"])
        if n == 0:
            return []

        # 여백 계산
        left_margin = width * margin
        right_margin = width * margin
        top_margin = height * margin
        bottom_margin = height * margin

        usable_width = width - left_margin - right_margin
        usable_height = height - top_margin - bottom_margin

        # 최대값
        max_val = max(result["sorted_values"]) if result["sorted_values"] else 1

        # 막대 높이
        bar_total_height = usable_height / n
        bar_height = bar_total_height * self.bar_height

        rects = []
        for i, (cat, val) in enumerate(zip(result["sorted_categories"], result["sorted_values"])):
            bar_width = (val / max_val) * usable_width if max_val > 0 else 0

            y = top_margin + i * bar_total_height + (bar_total_height - bar_height) / 2

            rects.append({
                "x": left_margin,
                "y": y,
                "width": bar_width,
                "height": bar_height,
                "category": cat,
                "value": val,
                "index": i
            })

        return rects
