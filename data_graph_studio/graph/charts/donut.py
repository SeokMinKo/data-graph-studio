"""
Donut Chart - 도넛 차트
"""

from typing import List, Dict, Any, Optional
import numpy as np


class DonutChart:
    """
    도넛 차트

    파이 차트의 변형으로, 중앙에 공간이 있어 KPI 표시 등에 유용합니다.
    """

    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]

    def calculate(
        self,
        labels: List[str],
        values: List[float],
        inner_radius_ratio: float = 0.5,
        start_angle: float = 90,
        sort_by_value: bool = False,
        colors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        도넛 차트 데이터 계산

        Args:
            labels: 레이블 목록
            values: 값 목록
            inner_radius_ratio: 내부 반지름 비율 (0~1, 0이면 파이 차트)
            start_angle: 시작 각도 (도)
            sort_by_value: 값으로 정렬
            colors: 색상 목록

        Returns:
            도넛 데이터
        """
        # 유효한 값만 필터링
        valid_pairs = [(lbl, v) for lbl, v in zip(labels, values) if v > 0]

        if not valid_pairs:
            return {
                "labels": [],
                "values": [],
                "angles": [],
                "percentages": [],
                "start_angles": [],
                "end_angles": [],
                "inner_radius_ratio": inner_radius_ratio,
                "colors": []
            }

        if sort_by_value:
            valid_pairs.sort(key=lambda x: x[1], reverse=True)

        sorted_labels = [p[0] for p in valid_pairs]
        sorted_values = [p[1] for p in valid_pairs]

        # 총합
        total = sum(sorted_values)

        # 각도 및 퍼센트 계산
        angles = [(v / total) * 360 for v in sorted_values]
        percentages = [(v / total) * 100 for v in sorted_values]

        # 시작/끝 각도 계산
        start_angles = []
        end_angles = []
        current_angle = start_angle

        for angle in angles:
            start_angles.append(current_angle)
            current_angle += angle
            end_angles.append(current_angle)

        # 색상
        if colors is None:
            colors = [self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)]
                      for i in range(len(sorted_labels))]

        return {
            "labels": sorted_labels,
            "values": sorted_values,
            "angles": angles,
            "percentages": percentages,
            "start_angles": start_angles,
            "end_angles": end_angles,
            "inner_radius_ratio": inner_radius_ratio,
            "colors": colors,
            "total": total
        }

    def get_arc_paths(
        self,
        labels: List[str],
        values: List[float],
        center_x: float,
        center_y: float,
        outer_radius: float,
        inner_radius_ratio: float = 0.5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        SVG/Canvas용 호 경로 계산

        Returns:
            호 정보 목록
        """
        result = self.calculate(labels, values, inner_radius_ratio, **kwargs)

        inner_radius = outer_radius * inner_radius_ratio

        arcs = []
        for i, label in enumerate(result["labels"]):
            start_rad = np.radians(result["start_angles"][i])
            end_rad = np.radians(result["end_angles"][i])

            # 호의 중간점 (레이블 위치용)
            mid_rad = (start_rad + end_rad) / 2
            label_radius = (outer_radius + inner_radius) / 2

            arcs.append({
                "label": label,
                "value": result["values"][i],
                "percentage": result["percentages"][i],
                "start_angle": result["start_angles"][i],
                "end_angle": result["end_angles"][i],
                "color": result["colors"][i],
                # 호 포인트
                "outer_start": (
                    center_x + outer_radius * np.cos(start_rad),
                    center_y - outer_radius * np.sin(start_rad)
                ),
                "outer_end": (
                    center_x + outer_radius * np.cos(end_rad),
                    center_y - outer_radius * np.sin(end_rad)
                ),
                "inner_start": (
                    center_x + inner_radius * np.cos(start_rad),
                    center_y - inner_radius * np.sin(start_rad)
                ),
                "inner_end": (
                    center_x + inner_radius * np.cos(end_rad),
                    center_y - inner_radius * np.sin(end_rad)
                ),
                # 레이블 위치
                "label_x": center_x + label_radius * np.cos(mid_rad),
                "label_y": center_y - label_radius * np.sin(mid_rad)
            })

        return arcs

    def get_center_text(
        self,
        values: List[float],
        format_str: str = "{:,.0f}",
        title: str = "Total"
    ) -> Dict[str, Any]:
        """
        중앙 텍스트 정보

        Returns:
            중앙 텍스트 정보
        """
        total = sum(v for v in values if v > 0)

        return {
            "title": title,
            "value": format_str.format(total),
            "raw_value": total
        }
