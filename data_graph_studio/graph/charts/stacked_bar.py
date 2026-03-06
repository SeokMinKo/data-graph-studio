"""
Stacked Bar Chart - 누적 막대 차트
"""

from typing import List, Dict, Any
import polars as pl


class StackedBarChart:
    """
    누적 막대 차트

    일반 스택 또는 100% 스택을 지원합니다.
    """

    DEFAULT_COLORS = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
    ]

    def calculate(
        self,
        data: pl.DataFrame,
        category_col: str,
        group_col: str,
        value_col: str,
        agg_func: str = "sum",
        normalize: bool = False,
        sort_categories: bool = False,
        sort_groups: bool = False,
    ) -> Dict[str, Any]:
        """
        누적 막대 데이터 계산

        Args:
            data: 데이터프레임
            category_col: 카테고리 컬럼 (X축)
            group_col: 그룹 컬럼 (스택)
            value_col: 값 컬럼
            agg_func: 집계 함수 (sum, mean, count, etc.)
            normalize: 100% 스택 여부
            sort_categories: 카테고리 정렬
            sort_groups: 그룹 정렬

        Returns:
            스택 데이터
        """
        # 집계
        if agg_func == "sum":
            agg_expr = pl.col(value_col).sum()
        elif agg_func == "mean":
            agg_expr = pl.col(value_col).mean()
        elif agg_func == "count":
            agg_expr = pl.col(value_col).count()
        elif agg_func == "min":
            agg_expr = pl.col(value_col).min()
        elif agg_func == "max":
            agg_expr = pl.col(value_col).max()
        else:
            agg_expr = pl.col(value_col).sum()

        # 그룹별 집계
        grouped = data.group_by([category_col, group_col]).agg(agg_expr.alias("value"))

        # 카테고리 및 그룹 목록
        categories = (
            grouped[category_col].unique().sort().to_list()
            if sort_categories
            else grouped[category_col].unique().to_list()
        )
        groups = (
            grouped[group_col].unique().sort().to_list()
            if sort_groups
            else grouped[group_col].unique().to_list()
        )

        # 스택 값 구성
        stacked_values = {}
        for cat in categories:
            stacked_values[cat] = {}
            cat_data = grouped.filter(pl.col(category_col) == cat)

            for grp in groups:
                grp_data = cat_data.filter(pl.col(group_col) == grp)
                if len(grp_data) > 0:
                    stacked_values[cat][grp] = grp_data["value"][0]
                else:
                    stacked_values[cat][grp] = 0

        # 100% 정규화
        if normalize:
            for cat in categories:
                total = sum(stacked_values[cat].values())
                if total > 0:
                    for grp in groups:
                        stacked_values[cat][grp] = (
                            stacked_values[cat][grp] / total
                        ) * 100

        # 스택 시작 위치 계산
        stack_positions = {}
        for cat in categories:
            stack_positions[cat] = {}
            cumsum = 0
            for grp in groups:
                stack_positions[cat][grp] = {
                    "start": cumsum,
                    "end": cumsum + stacked_values[cat][grp],
                    "value": stacked_values[cat][grp],
                }
                cumsum += stacked_values[cat][grp]

        # 색상 매핑
        colors = {
            grp: self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
            for i, grp in enumerate(groups)
        }

        return {
            "categories": categories,
            "groups": groups,
            "stacked_values": stacked_values,
            "stack_positions": stack_positions,
            "colors": colors,
            "normalized": normalize,
        }

    def get_bar_rects(
        self,
        data: pl.DataFrame,
        category_col: str,
        group_col: str,
        value_col: str,
        width: float,
        height: float,
        margin: float = 0.1,
        horizontal: bool = False,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        실제 그리기용 사각형 좌표 계산

        Returns:
            사각형 정보 목록
        """
        result = self.calculate(data, category_col, group_col, value_col, **kwargs)

        categories = result["categories"]
        groups = result["groups"]
        stack_positions = result["stack_positions"]
        colors = result["colors"]

        if not categories:
            return []

        # 여백 계산
        m = margin
        usable_width = width * (1 - 2 * m)
        usable_height = height * (1 - 2 * m)

        # 최대값
        max_val = (
            max(stack_positions[cat][groups[-1]]["end"] for cat in categories)
            if categories and groups
            else 1
        )

        # 막대 너비/높이
        n_cats = len(categories)

        rects = []

        if horizontal:
            bar_height_total = usable_height / n_cats
            bar_height = bar_height_total * 0.8

            for i, cat in enumerate(categories):
                y = (
                    height * m
                    + i * bar_height_total
                    + (bar_height_total - bar_height) / 2
                )

                for grp in groups:
                    pos = stack_positions[cat][grp]
                    x_start = width * m + (pos["start"] / max_val) * usable_width
                    bar_width = (pos["value"] / max_val) * usable_width

                    rects.append(
                        {
                            "x": x_start,
                            "y": y,
                            "width": bar_width,
                            "height": bar_height,
                            "category": cat,
                            "group": grp,
                            "value": pos["value"],
                            "color": colors[grp],
                        }
                    )
        else:
            bar_width_total = usable_width / n_cats
            bar_width = bar_width_total * 0.8

            for i, cat in enumerate(categories):
                x = width * m + i * bar_width_total + (bar_width_total - bar_width) / 2

                for grp in groups:
                    pos = stack_positions[cat][grp]
                    y_start = (
                        height - height * m - (pos["end"] / max_val) * usable_height
                    )
                    bar_height = (pos["value"] / max_val) * usable_height

                    rects.append(
                        {
                            "x": x,
                            "y": y_start,
                            "width": bar_width,
                            "height": bar_height,
                            "category": cat,
                            "group": grp,
                            "value": pos["value"],
                            "color": colors[grp],
                        }
                    )

        return rects
