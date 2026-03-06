"""
Box Plot Chart
"""

import numpy as np
import polars as pl
from typing import Dict, List, Any, Tuple


class BoxPlotChart:
    """Box Plot 차트"""

    def calculate_stats(
        self,
        df: pl.DataFrame,
        category_col: str,
        value_col: str,
        whisker_iqr: float = 1.5,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Box plot 통계 계산

        Args:
            df: 데이터프레임
            category_col: 카테고리 컬럼
            value_col: 값 컬럼
            whisker_iqr: Whisker IQR 배수 (기본 1.5)

        Returns:
            카테고리별 통계 딕셔너리
        """
        result = {}

        categories = df[category_col].unique().to_list()

        for cat in categories:
            cat_data = df.filter(pl.col(category_col) == cat)[value_col].to_numpy()
            cat_data = cat_data[~np.isnan(cat_data)]  # Remove NaN

            if len(cat_data) == 0:
                continue

            # 사분위수 계산
            q1 = np.percentile(cat_data, 25)
            median = np.percentile(cat_data, 50)
            q3 = np.percentile(cat_data, 75)
            iqr = q3 - q1

            # Whisker 범위 계산
            whisker_low_limit = q1 - whisker_iqr * iqr
            whisker_high_limit = q3 + whisker_iqr * iqr

            # 실제 데이터 범위 내에서 whisker 결정
            within_range = cat_data[
                (cat_data >= whisker_low_limit) & (cat_data <= whisker_high_limit)
            ]

            if len(within_range) > 0:
                whisker_low = within_range.min()
                whisker_high = within_range.max()
            else:
                whisker_low = q1
                whisker_high = q3

            # 이상치 찾기
            outliers = cat_data[
                (cat_data < whisker_low_limit) | (cat_data > whisker_high_limit)
            ]

            result[cat] = {
                "median": float(median),
                "q1": float(q1),
                "q3": float(q3),
                "whisker_low": float(whisker_low),
                "whisker_high": float(whisker_high),
                "outliers": outliers.tolist(),
                "min": float(cat_data.min()),
                "max": float(cat_data.max()),
                "mean": float(cat_data.mean()),
                "std": float(cat_data.std()),
                "count": len(cat_data),
            }

        return result

    def get_plot_data(
        self, stats: Dict[str, Dict[str, Any]]
    ) -> Tuple[List[str], List[Dict]]:
        """
        PyQtGraph용 플롯 데이터 생성

        Returns:
            (카테고리 목록, 박스 데이터 목록)
        """
        categories = list(stats.keys())
        boxes = []

        for i, cat in enumerate(categories):
            s = stats[cat]
            boxes.append(
                {
                    "x": i,
                    "q1": s["q1"],
                    "median": s["median"],
                    "q3": s["q3"],
                    "whisker_low": s["whisker_low"],
                    "whisker_high": s["whisker_high"],
                    "outliers": [(i, o) for o in s["outliers"]],
                }
            )

        return categories, boxes
