"""
TreeMap Chart - 트리맵 차트
"""

from typing import List, Dict, Any
from dataclasses import dataclass
import polars as pl


@dataclass
class TreeMapData:
    """트리맵 데이터"""
    rectangles: List[Dict[str, Any]]
    total_value: float


class TreeMapCalculator:
    """
    트리맵 계산기

    Squarified TreeMap 알고리즘을 사용하여
    면적이 값에 비례하는 사각형을 계산합니다.
    """

    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]

    def calculate(
        self,
        data: pl.DataFrame,
        hierarchy_columns: List[str],
        value_column: str,
        width: float = 100,
        height: float = 100,
        padding: float = 1,
        min_area: float = 1
    ) -> Dict[str, Any]:
        """
        트리맵 사각형 계산

        Args:
            data: 데이터프레임
            hierarchy_columns: 계층 컬럼 목록
            value_column: 크기를 결정하는 값 컬럼
            width: 전체 너비
            height: 전체 높이
            padding: 사각형 간 패딩
            min_area: 최소 면적 (이보다 작으면 표시 안 함)

        Returns:
            트리맵 데이터
        """
        # 첫 번째 계층으로 그룹화
        if not hierarchy_columns:
            return {"rectangles": [], "total_value": 0}

        first_level = hierarchy_columns[0]

        # 집계
        grouped = (
            data
            .group_by(first_level)
            .agg(pl.col(value_column).sum().alias("_value_"))
            .sort("_value_", descending=True)
        )

        total = grouped["_value_"].sum()

        if total <= 0:
            return {"rectangles": [], "total_value": 0}

        # 값과 레이블 추출
        items = [
            {"label": row[first_level], "value": row["_value_"]}
            for row in grouped.iter_rows(named=True)
            if row["_value_"] > 0
        ]

        # Squarified 알고리즘으로 사각형 계산
        rectangles = self._squarify(
            items, 0, 0, width, height, total, padding
        )

        # 색상 할당
        for i, rect in enumerate(rectangles):
            rect["color"] = self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
            rect["percentage"] = (rect["value"] / total) * 100

        # 면적이 너무 작은 것 필터링
        rectangles = [r for r in rectangles
                      if r["width"] * r["height"] >= min_area]

        return {
            "rectangles": rectangles,
            "total_value": total,
            "hierarchy": hierarchy_columns
        }

    def _squarify(
        self,
        items: List[Dict],
        x: float,
        y: float,
        width: float,
        height: float,
        total: float,
        padding: float
    ) -> List[Dict[str, Any]]:
        """
        Squarified TreeMap 알고리즘

        최대한 정사각형에 가까운 사각형을 생성합니다.
        """
        if not items or width <= 0 or height <= 0:
            return []

        # 값에 따른 면적 비율 계산
        scale = (width * height) / total if total > 0 else 0

        rectangles = []
        remaining_items = list(items)

        current_x = x
        current_y = y
        current_width = width
        current_height = height

        while remaining_items:
            # 더 짧은 축 선택
            is_horizontal = current_width >= current_height

            # 현재 행/열에 추가할 항목들
            row_items = []
            row_total = 0

            # 가장 좋은 aspect ratio를 찾음
            best_ratio = float('inf')

            for i, item in enumerate(remaining_items):
                test_items = row_items + [item]
                test_total = row_total + item["value"]

                # 이 행의 면적
                row_area = test_total * scale

                if is_horizontal:
                    row_area / current_height if current_height > 0 else 0
                else:
                    row_area / current_width if current_width > 0 else 0

                # Aspect ratio 계산
                worst_ratio = 0
                for test_item in test_items:
                    item_area = test_item["value"] * scale
                    if is_horizontal:
                        item_height = current_height
                        item_width = item_area / item_height if item_height > 0 else 0
                    else:
                        item_width = current_width
                        item_height = item_area / item_width if item_width > 0 else 0

                    ratio = max(item_width, item_height) / max(min(item_width, item_height), 0.001)
                    worst_ratio = max(worst_ratio, ratio)

                if worst_ratio <= best_ratio:
                    best_ratio = worst_ratio
                    row_items = test_items
                    row_total = test_total
                else:
                    break

            # 현재 행의 사각형들 생성
            row_area = row_total * scale

            if is_horizontal:
                row_width = row_area / current_height if current_height > 0 else 0
                item_y = current_y
                for item in row_items:
                    item_area = item["value"] * scale
                    item_height = item_area / row_width if row_width > 0 else 0

                    rectangles.append({
                        "x": current_x + padding / 2,
                        "y": item_y + padding / 2,
                        "width": max(0, row_width - padding),
                        "height": max(0, item_height - padding),
                        "label": item["label"],
                        "value": item["value"]
                    })
                    item_y += item_height

                current_x += row_width
                current_width -= row_width
            else:
                row_height = row_area / current_width if current_width > 0 else 0
                item_x = current_x
                for item in row_items:
                    item_area = item["value"] * scale
                    item_width = item_area / row_height if row_height > 0 else 0

                    rectangles.append({
                        "x": item_x + padding / 2,
                        "y": current_y + padding / 2,
                        "width": max(0, item_width - padding),
                        "height": max(0, row_height - padding),
                        "label": item["label"],
                        "value": item["value"]
                    })
                    item_x += item_width

                current_y += row_height
                current_height -= row_height

            # 처리된 항목 제거
            remaining_items = remaining_items[len(row_items):]

        return rectangles

    def get_color_scale(
        self,
        values: List[float],
        color_min: str = "#f7fbff",
        color_max: str = "#08306b"
    ) -> List[str]:
        """
        값에 따른 색상 스케일 계산

        Args:
            values: 값 목록
            color_min: 최소값 색상
            color_max: 최대값 색상

        Returns:
            색상 목록
        """
        if not values:
            return []

        min_val = min(values)
        max_val = max(values)

        # 색상 파싱
        def hex_to_rgb(hex_color):
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

        def rgb_to_hex(rgb):
            return '#{:02x}{:02x}{:02x}'.format(*rgb)

        min_rgb = hex_to_rgb(color_min)
        max_rgb = hex_to_rgb(color_max)

        colors = []
        for v in values:
            if max_val == min_val:
                t = 0.5
            else:
                t = (v - min_val) / (max_val - min_val)

            rgb = tuple(int(min_rgb[i] + t * (max_rgb[i] - min_rgb[i])) for i in range(3))
            colors.append(rgb_to_hex(rgb))

        return colors
