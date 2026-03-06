"""
Bubble Chart - 버블 차트
"""

from typing import List, Dict, Any, Optional
import numpy as np


class BubbleChart:
    """
    버블 차트

    X, Y, Size 3차원 데이터를 표현합니다.
    """

    def calculate(
        self,
        x: List[float],
        y: List[float],
        size: Optional[List[float]] = None,
        color: Optional[List[Any]] = None,
        labels: Optional[List[str]] = None,
        min_bubble_size: float = 10,
        max_bubble_size: float = 100,
        default_size: float = 50,
    ) -> Dict[str, Any]:
        """
        버블 차트 데이터 계산

        Args:
            x: X 값 목록
            y: Y 값 목록
            size: 크기 값 목록 (optional)
            color: 색상 값 목록 (optional)
            labels: 레이블 목록 (optional)
            min_bubble_size: 최소 버블 크기
            max_bubble_size: 최대 버블 크기
            default_size: 기본 버블 크기

        Returns:
            버블 데이터
        """
        n = len(x)

        # 크기 스케일링
        if size is not None and len(size) == n:
            size_arr = np.array(size, dtype=float)

            # NaN 처리
            valid_mask = ~np.isnan(size_arr)
            if np.any(valid_mask):
                min_val = np.nanmin(size_arr)
                max_val = np.nanmax(size_arr)

                if max_val > min_val:
                    # 정규화 후 스케일링
                    normalized = (size_arr - min_val) / (max_val - min_val)
                    scaled_sizes = min_bubble_size + normalized * (
                        max_bubble_size - min_bubble_size
                    )
                else:
                    scaled_sizes = np.full(n, (min_bubble_size + max_bubble_size) / 2)

                # NaN은 기본 크기
                scaled_sizes = np.where(valid_mask, scaled_sizes, default_size)
            else:
                scaled_sizes = np.full(n, default_size)

            scaled_sizes = scaled_sizes.tolist()
        else:
            scaled_sizes = [default_size] * n

        # 레이블
        if labels is None:
            labels = [f"Point {i + 1}" for i in range(n)]

        return {
            "x": list(x),
            "y": list(y),
            "original_sizes": size if size else [default_size] * n,
            "scaled_sizes": scaled_sizes,
            "colors": color,
            "labels": labels,
            "min_bubble_size": min_bubble_size,
            "max_bubble_size": max_bubble_size,
        }

    def get_bubble_data(
        self,
        x: List[float],
        y: List[float],
        size: Optional[List[float]] = None,
        width: float = 100,
        height: float = 100,
        margin: float = 0.1,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        실제 그리기용 버블 데이터

        Returns:
            버블 정보 목록
        """
        result = self.calculate(x, y, size, **kwargs)

        x_arr = np.array(result["x"])
        y_arr = np.array(result["y"])

        # 데이터 범위
        x_min, x_max = np.nanmin(x_arr), np.nanmax(x_arr)
        y_min, y_max = np.nanmin(y_arr), np.nanmax(y_arr)

        # 여백 고려
        m = margin
        usable_width = width * (1 - 2 * m)
        usable_height = height * (1 - 2 * m)

        # 좌표 변환
        if x_max > x_min:
            screen_x = width * m + ((x_arr - x_min) / (x_max - x_min)) * usable_width
        else:
            screen_x = np.full_like(x_arr, width / 2)

        if y_max > y_min:
            screen_y = (
                height
                - height * m
                - ((y_arr - y_min) / (y_max - y_min)) * usable_height
            )
        else:
            screen_y = np.full_like(y_arr, height / 2)

        bubbles = []
        for i in range(len(x_arr)):
            bubbles.append(
                {
                    "x": float(screen_x[i]),
                    "y": float(screen_y[i]),
                    "size": result["scaled_sizes"][i],
                    "original_x": result["x"][i],
                    "original_y": result["y"][i],
                    "original_size": result["original_sizes"][i],
                    "label": result["labels"][i],
                    "color": result["colors"][i] if result["colors"] else None,
                }
            )

        return bubbles
