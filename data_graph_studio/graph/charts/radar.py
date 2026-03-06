"""
Radar Chart (Spider Chart) - 레이더/스파이더 차트
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import math


@dataclass
class RadarData:
    """레이더 차트 데이터"""

    axes: List[str]
    series_coordinates: Dict[str, List[Tuple[float, float]]]
    axis_angles: List[float]


class RadarCalculator:
    """
    레이더 차트 계산기

    다차원 데이터를 방사형으로 시각화합니다.
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
        axes: List[str],
        series: List[Dict[str, Any]],
        max_value: Optional[float] = None,
        min_value: float = 0,
        start_angle: float = 90,  # 12시 방향 시작
    ) -> Dict[str, Any]:
        """
        레이더 차트 좌표 계산

        Args:
            axes: 축 이름 목록
            series: 시리즈 목록 [{"name": str, "values": list, "color": str}]
            max_value: 최대값 (None이면 자동)
            min_value: 최소값
            start_angle: 시작 각도 (도)

        Returns:
            레이더 데이터
        """
        n_axes = len(axes)

        if n_axes == 0:
            return {
                "axes": [],
                "axis_angles": [],
                "series_coordinates": {},
                "series_colors": {},
                "max_value": 0,
                "min_value": 0,
                "grid_values": [],
            }

        # 축 각도 계산 (등간격)
        angle_step = 360 / n_axes
        axis_angles = [(start_angle - i * angle_step) % 360 for i in range(n_axes)]

        # 최대값 결정
        if max_value is None:
            all_values = []
            for s in series:
                all_values.extend([v for v in s.get("values", []) if v is not None])
            max_value = max(all_values) if all_values else 1

        # 그리드 값 (동심원)
        n_grids = 5
        grid_step = (max_value - min_value) / n_grids
        grid_values = [min_value + grid_step * (i + 1) for i in range(n_grids)]

        # 각 시리즈의 좌표 계산
        series_coordinates = {}
        series_colors = {}

        for idx, s in enumerate(series):
            name = s.get("name", f"Series {idx + 1}")
            values = s.get("values", [])
            color = s.get("color", self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)])

            # 값이 부족하면 0으로 채움
            if len(values) < n_axes:
                values = values + [0] * (n_axes - len(values))
            elif len(values) > n_axes:
                values = values[:n_axes]

            # 좌표 변환
            coords = []
            for i, (angle, value) in enumerate(zip(axis_angles, values)):
                if value is None:
                    value = 0

                # 정규화 (0~1)
                if max_value > min_value:
                    normalized = (value - min_value) / (max_value - min_value)
                else:
                    normalized = 0

                # 극좌표 → 직교좌표
                rad = math.radians(angle)
                x = normalized * math.cos(rad)
                y = normalized * math.sin(rad)

                coords.append((x, y))

            series_coordinates[name] = coords
            series_colors[name] = color

        return {
            "axes": list(axes),
            "axis_angles": axis_angles,
            "series_coordinates": series_coordinates,
            "series_colors": series_colors,
            "max_value": max_value,
            "min_value": min_value,
            "grid_values": grid_values,
        }

    def get_polygon_points(
        self,
        axes: List[str],
        series: List[Dict[str, Any]],
        center_x: float,
        center_y: float,
        radius: float,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        실제 그리기용 폴리곤 포인트 계산

        Args:
            axes: 축 이름 목록
            series: 시리즈 목록
            center_x: 중심 X 좌표
            center_y: 중심 Y 좌표
            radius: 반지름

        Returns:
            폴리곤 데이터
        """
        result = self.calculate(axes, series, **kwargs)

        len(result["axes"])

        # 축 라인 끝점
        axis_endpoints = []
        for angle in result["axis_angles"]:
            rad = math.radians(angle)
            x = center_x + radius * math.cos(rad)
            y = center_y - radius * math.sin(rad)  # Y 반전 (화면 좌표계)
            axis_endpoints.append((x, y))

        # 그리드 폴리곤
        grid_polygons = []
        for grid_val in result["grid_values"]:
            if result["max_value"] > result["min_value"]:
                grid_radius = (
                    radius
                    * (grid_val - result["min_value"])
                    / (result["max_value"] - result["min_value"])
                )
            else:
                grid_radius = 0

            points = []
            for angle in result["axis_angles"]:
                rad = math.radians(angle)
                x = center_x + grid_radius * math.cos(rad)
                y = center_y - grid_radius * math.sin(rad)
                points.append((x, y))

            grid_polygons.append({"value": grid_val, "points": points})

        # 시리즈 폴리곤
        series_polygons = {}
        for name, coords in result["series_coordinates"].items():
            points = []
            for x, y in coords:
                screen_x = center_x + x * radius
                screen_y = center_y - y * radius  # Y 반전
                points.append((screen_x, screen_y))

            series_polygons[name] = {
                "points": points,
                "color": result["series_colors"][name],
            }

        return {
            "center": (center_x, center_y),
            "radius": radius,
            "axes": result["axes"],
            "axis_endpoints": axis_endpoints,
            "axis_angles": result["axis_angles"],
            "grid_polygons": grid_polygons,
            "series_polygons": series_polygons,
            "max_value": result["max_value"],
            "min_value": result["min_value"],
        }

    def calculate_area(self, coords: List[Tuple[float, float]]) -> float:
        """
        폴리곤 면적 계산 (Shoelace formula)

        Args:
            coords: 좌표 목록

        Returns:
            면적
        """
        n = len(coords)
        if n < 3:
            return 0

        area = 0
        for i in range(n):
            j = (i + 1) % n
            area += coords[i][0] * coords[j][1]
            area -= coords[j][0] * coords[i][1]

        return abs(area) / 2

    def compare_series(
        self, axes: List[str], series: List[Dict[str, Any]], **kwargs
    ) -> Dict[str, Any]:
        """
        시리즈 간 비교 분석

        Returns:
            비교 결과
        """
        result = self.calculate(axes, series, **kwargs)

        comparison = {}

        for name, coords in result["series_coordinates"].items():
            # 면적
            area = self.calculate_area(coords)

            # 평균 거리 (중심에서)
            distances = [math.sqrt(x**2 + y**2) for x, y in coords]
            avg_distance = sum(distances) / len(distances) if distances else 0

            # 최대/최소 축 찾기
            series_data = None
            for s in series:
                if s.get("name") == name:
                    series_data = s
                    break

            if series_data:
                values = series_data.get("values", [])
                if values:
                    max_idx = values.index(max(values))
                    min_idx = values.index(min(values))
                    max_axis = axes[max_idx] if max_idx < len(axes) else None
                    min_axis = axes[min_idx] if min_idx < len(axes) else None
                else:
                    max_axis = min_axis = None
            else:
                max_axis = min_axis = None

            comparison[name] = {
                "area": area,
                "avg_distance": avg_distance,
                "max_axis": max_axis,
                "min_axis": min_axis,
                "color": result["series_colors"][name],
            }

        return comparison
