"""
Funnel Chart - 퍼널 차트
"""

from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class FunnelData:
    """퍼널 데이터"""
    stages: List[str]
    values: List[float]
    widths: List[float]
    conversion_rates: List[float]


class FunnelCalculator:
    """
    퍼널 차트 계산기

    전환율 분석에 사용되는 퍼널 시각화를 계산합니다.
    """

    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]

    def calculate(
        self,
        stages: List[str],
        values: List[float],
        normalize_widths: bool = True
    ) -> Dict[str, Any]:
        """
        퍼널 데이터 계산

        Args:
            stages: 단계 이름 목록
            values: 각 단계의 값 목록
            normalize_widths: 폭 정규화 여부

        Returns:
            퍼널 데이터
        """
        n = len(stages)

        if n == 0 or len(values) != n:
            return {
                "stages": [],
                "values": [],
                "widths": [],
                "conversion_rates": [],
                "percentages": [],
                "colors": []
            }

        # 최대값
        max_val = max(values) if values else 1

        # 폭 계산
        if normalize_widths and max_val > 0:
            widths = [v / max_val for v in values]
        else:
            widths = list(values)

        # 전환율 계산 (이전 단계 대비)
        conversion_rates = []
        for i in range(n):
            if i == 0:
                conversion_rates.append(100.0)  # 첫 단계는 100%
            else:
                prev_val = values[i - 1]
                if prev_val > 0:
                    rate = (values[i] / prev_val) * 100
                else:
                    rate = 0
                conversion_rates.append(rate)

        # 전체 대비 퍼센트
        percentages = [(v / values[0]) * 100 if values[0] > 0 else 0 for v in values]

        # 색상
        colors = [self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)] for i in range(n)]

        return {
            "stages": list(stages),
            "values": list(values),
            "widths": widths,
            "conversion_rates": conversion_rates,
            "percentages": percentages,
            "colors": colors,
            "total_conversion": percentages[-1] if percentages else 0
        }

    def get_funnel_shapes(
        self,
        stages: List[str],
        values: List[float],
        width: float,
        height: float,
        margin: float = 0.1,
        gap: float = 2,
        symmetric: bool = True,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        퍼널 모양 좌표 계산

        Args:
            stages: 단계 목록
            values: 값 목록
            width: 전체 너비
            height: 전체 높이
            margin: 여백 비율
            gap: 단계 간 간격
            symmetric: 좌우 대칭 여부

        Returns:
            퍼널 모양 데이터
        """
        result = self.calculate(stages, values, **kwargs)

        n = len(result["stages"])
        if n == 0:
            return []

        # 여백
        m = margin
        usable_width = width * (1 - 2 * m)
        usable_height = height * (1 - 2 * m)

        # 각 단계의 높이
        total_gap = gap * (n - 1)
        stage_height = (usable_height - total_gap) / n

        shapes = []
        center_x = width / 2

        for i, (stage, value, w, rate, pct, color) in enumerate(zip(
            result["stages"],
            result["values"],
            result["widths"],
            result["conversion_rates"],
            result["percentages"],
            result["colors"]
        )):
            # 현재 단계의 폭
            current_width = usable_width * w

            # 다음 단계의 폭 (마지막은 동일)
            if i < n - 1:
                next_width = usable_width * result["widths"][i + 1]
            else:
                next_width = current_width * 0.8  # 마지막은 약간 좁게

            # Y 위치
            y_top = height * m + i * (stage_height + gap)
            y_bottom = y_top + stage_height

            if symmetric:
                # 좌우 대칭 사다리꼴
                shapes.append({
                    "stage": stage,
                    "value": value,
                    "conversion_rate": rate,
                    "percentage": pct,
                    "color": color,
                    "points": [
                        (center_x - current_width / 2, y_top),      # 좌상
                        (center_x + current_width / 2, y_top),      # 우상
                        (center_x + next_width / 2, y_bottom),      # 우하
                        (center_x - next_width / 2, y_bottom),      # 좌하
                    ],
                    "label_x": center_x,
                    "label_y": (y_top + y_bottom) / 2,
                    "y_top": y_top,
                    "y_bottom": y_bottom
                })
            else:
                # 왼쪽 정렬 사다리꼴
                left_x = width * m
                shapes.append({
                    "stage": stage,
                    "value": value,
                    "conversion_rate": rate,
                    "percentage": pct,
                    "color": color,
                    "points": [
                        (left_x, y_top),
                        (left_x + current_width, y_top),
                        (left_x + next_width, y_bottom),
                        (left_x, y_bottom),
                    ],
                    "label_x": left_x + current_width / 2,
                    "label_y": (y_top + y_bottom) / 2,
                    "y_top": y_top,
                    "y_bottom": y_bottom
                })

        return shapes

    def get_summary(self, stages: List[str], values: List[float]) -> Dict[str, Any]:
        """
        퍼널 요약 통계

        Returns:
            요약 정보
        """
        result = self.calculate(stages, values)

        if not result["stages"]:
            return {
                "total_stages": 0,
                "start_value": 0,
                "end_value": 0,
                "total_conversion": 0,
                "biggest_drop_stage": None,
                "biggest_drop_rate": 0
            }

        # 가장 큰 이탈 단계 찾기
        biggest_drop_idx = 0
        biggest_drop = 0

        for i in range(1, len(result["conversion_rates"])):
            drop = 100 - result["conversion_rates"][i]
            if drop > biggest_drop:
                biggest_drop = drop
                biggest_drop_idx = i

        return {
            "total_stages": len(result["stages"]),
            "start_value": result["values"][0],
            "end_value": result["values"][-1],
            "total_conversion": result["total_conversion"],
            "biggest_drop_stage": result["stages"][biggest_drop_idx] if biggest_drop_idx > 0 else None,
            "biggest_drop_rate": biggest_drop
        }
