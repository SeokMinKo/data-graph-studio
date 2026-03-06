"""
Heatmap Chart
"""

import numpy as np
import polars as pl
from typing import Dict, List, Tuple, Optional
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize


class HeatmapChart:
    """Heatmap 차트"""

    def create_matrix(
        self,
        df: pl.DataFrame,
        row_col: str,
        col_col: str,
        value_col: str,
        agg: str = "sum",
    ) -> Tuple[np.ndarray, List[str], List[str]]:
        """
        히트맵 매트릭스 생성

        Args:
            df: 데이터프레임
            row_col: 행 카테고리 컬럼
            col_col: 열 카테고리 컬럼
            value_col: 값 컬럼
            agg: 집계 함수 ('sum', 'mean', 'count', 'min', 'max')

        Returns:
            (매트릭스, 행 라벨, 열 라벨)
        """
        # 집계
        agg_map = {
            "sum": pl.col(value_col).sum(),
            "mean": pl.col(value_col).mean(),
            "count": pl.col(value_col).count(),
            "min": pl.col(value_col).min(),
            "max": pl.col(value_col).max(),
        }

        agg_expr = agg_map.get(agg, agg_map["sum"])

        grouped = df.group_by([row_col, col_col]).agg(agg_expr.alias("value"))

        # 유니크 라벨
        row_labels = sorted(df[row_col].unique().to_list())
        col_labels = sorted(df[col_col].unique().to_list())

        # 매트릭스 생성
        matrix = np.zeros((len(row_labels), len(col_labels)))
        matrix[:] = np.nan

        row_idx = {label: i for i, label in enumerate(row_labels)}
        col_idx = {label: i for i, label in enumerate(col_labels)}

        for row in grouped.iter_rows(named=True):
            r = row_idx.get(row[row_col])
            c = col_idx.get(row[col_col])
            if r is not None and c is not None:
                matrix[r, c] = row["value"]

        return matrix, row_labels, col_labels

    def get_color_scale(
        self,
        matrix: np.ndarray,
        colormap: str = "viridis",
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
    ) -> np.ndarray:
        """
        컬러 스케일 생성

        Args:
            matrix: 값 매트릭스
            colormap: Matplotlib 컬러맵 이름
            vmin: 최소값 (None이면 자동)
            vmax: 최대값 (None이면 자동)

        Returns:
            RGBA 배열 (shape: matrix.shape + (4,))
        """
        if vmin is None:
            vmin = np.nanmin(matrix)
        if vmax is None:
            vmax = np.nanmax(matrix)

        cmap = plt.get_cmap(colormap)
        norm = Normalize(vmin=vmin, vmax=vmax)

        # 정규화된 값
        normalized = norm(matrix)

        # 컬러맵 적용
        colors = cmap(normalized)

        # NaN 처리 (투명)
        nan_mask = np.isnan(matrix)
        colors[nan_mask] = [0, 0, 0, 0]

        return colors

    def get_annotations(
        self,
        matrix: np.ndarray,
        row_labels: List[str],
        col_labels: List[str],
        fmt: str = ".2f",
    ) -> List[Dict]:
        """
        셀 어노테이션 생성

        Returns:
            어노테이션 목록 [{row, col, value, text}, ...]
        """
        annotations = []

        for i, row_label in enumerate(row_labels):
            for j, col_label in enumerate(col_labels):
                value = matrix[i, j]
                if not np.isnan(value):
                    annotations.append(
                        {
                            "row": i,
                            "col": j,
                            "row_label": row_label,
                            "col_label": col_label,
                            "value": value,
                            "text": f"{value:{fmt}}",
                        }
                    )

        return annotations

    def get_plot_data(
        self,
        matrix: np.ndarray,
        row_labels: List[str],
        col_labels: List[str],
        colormap: str = "viridis",
    ) -> Dict:
        """
        PyQtGraph용 플롯 데이터
        """
        colors = self.get_color_scale(matrix, colormap)
        annotations = self.get_annotations(matrix, row_labels, col_labels)

        return {
            "matrix": matrix,
            "colors": colors,
            "row_labels": row_labels,
            "col_labels": col_labels,
            "annotations": annotations,
        }
