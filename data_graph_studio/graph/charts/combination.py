"""
Combination Chart - 결합 차트 (Bar + Line)
"""

from typing import List, Dict, Any


class CombinationChart:
    """
    결합 차트

    막대 차트와 라인 차트를 하나의 차트에 결합합니다.
    주로 실적과 추세를 함께 보여줄 때 사용합니다.
    """

    def calculate(
        self,
        x: List[Any],
        bar_series: List[Dict[str, Any]],
        line_series: List[Dict[str, Any]],
        bar_on_secondary: bool = False,
    ) -> Dict[str, Any]:
        """
        결합 차트 데이터 계산

        Args:
            x: X축 값 목록
            bar_series: 막대 시리즈 목록 [{"name": str, "values": list, "color": str}]
            line_series: 라인 시리즈 목록 [{"name": str, "values": list, "color": str}]
            bar_on_secondary: 막대를 보조 축에 표시

        Returns:
            결합 차트 데이터
        """
        n = len(x)

        # 막대 데이터 처리
        bar_data = []
        for series in bar_series:
            values = series.get("values", [])
            if len(values) < n:
                values = values + [0] * (n - len(values))
            elif len(values) > n:
                values = values[:n]

            bar_data.append(
                {
                    "name": series.get("name", "Bar"),
                    "values": values,
                    "color": series.get("color", "#1f77b4"),
                    "use_secondary": series.get("use_secondary", bar_on_secondary),
                }
            )

        # 라인 데이터 처리
        line_data = []
        for series in line_series:
            values = series.get("values", [])
            if len(values) < n:
                values = values + [None] * (n - len(values))
            elif len(values) > n:
                values = values[:n]

            line_data.append(
                {
                    "name": series.get("name", "Line"),
                    "values": values,
                    "color": series.get("color", "#ff7f0e"),
                    "use_secondary": series.get("use_secondary", not bar_on_secondary),
                    "line_style": series.get("line_style", "solid"),
                    "marker": series.get("marker", True),
                }
            )

        # Y축 범위 계산
        primary_values = []
        secondary_values = []

        for s in bar_data:
            if s["use_secondary"]:
                secondary_values.extend([v for v in s["values"] if v is not None])
            else:
                primary_values.extend([v for v in s["values"] if v is not None])

        for s in line_data:
            if s["use_secondary"]:
                secondary_values.extend([v for v in s["values"] if v is not None])
            else:
                primary_values.extend([v for v in s["values"] if v is not None])

        return {
            "x": list(x),
            "bar_data": bar_data,
            "line_data": line_data,
            "primary_y_range": (
                min(primary_values) if primary_values else 0,
                max(primary_values) if primary_values else 1,
            ),
            "secondary_y_range": (
                min(secondary_values) if secondary_values else 0,
                max(secondary_values) if secondary_values else 1,
            ),
        }

    def get_render_data(
        self,
        x: List[Any],
        bar_series: List[Dict[str, Any]],
        line_series: List[Dict[str, Any]],
        width: float,
        height: float,
        margin: float = 0.1,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        실제 렌더링용 데이터 계산

        Returns:
            렌더링 데이터
        """
        result = self.calculate(x, bar_series, line_series, **kwargs)

        n = len(x)
        if n == 0:
            return {"bars": [], "lines": []}

        # 여백
        m = margin
        usable_width = width * (1 - 2 * m)
        usable_height = height * (1 - 2 * m)

        # X 위치
        bar_total_width = usable_width / n
        bar_width = bar_total_width * 0.8 / max(len(result["bar_data"]), 1)

        # Y 스케일 함수
        def scale_primary(v):
            y_min, y_max = result["primary_y_range"]
            if y_max == y_min:
                return height / 2
            return height - m * height - ((v - y_min) / (y_max - y_min)) * usable_height

        def scale_secondary(v):
            y_min, y_max = result["secondary_y_range"]
            if y_max == y_min:
                return height / 2
            return height - m * height - ((v - y_min) / (y_max - y_min)) * usable_height

        # 막대 렌더링 데이터
        bars = []
        for s_idx, series in enumerate(result["bar_data"]):
            scale_fn = scale_secondary if series["use_secondary"] else scale_primary
            y_min = (
                result["secondary_y_range"][0]
                if series["use_secondary"]
                else result["primary_y_range"][0]
            )

            for i, v in enumerate(series["values"]):
                if v is None:
                    continue

                x_pos = (
                    width * m
                    + i * bar_total_width
                    + (bar_total_width - bar_width * len(result["bar_data"])) / 2
                )
                x_pos += s_idx * bar_width

                y_top = scale_fn(v)
                y_bottom = scale_fn(y_min)

                bars.append(
                    {
                        "x": x_pos,
                        "y": min(y_top, y_bottom),
                        "width": bar_width,
                        "height": abs(y_bottom - y_top),
                        "value": v,
                        "series": series["name"],
                        "color": series["color"],
                        "index": i,
                    }
                )

        # 라인 렌더링 데이터
        lines = []
        for series in result["line_data"]:
            scale_fn = scale_secondary if series["use_secondary"] else scale_primary

            points = []
            for i, v in enumerate(series["values"]):
                if v is None:
                    continue

                x_pos = width * m + i * bar_total_width + bar_total_width / 2
                y_pos = scale_fn(v)

                points.append({"x": x_pos, "y": y_pos, "value": v, "index": i})

            lines.append(
                {
                    "name": series["name"],
                    "color": series["color"],
                    "points": points,
                    "line_style": series["line_style"],
                    "marker": series["marker"],
                }
            )

        return {
            "bars": bars,
            "lines": lines,
            "x_labels": result["x"],
            "primary_y_range": result["primary_y_range"],
            "secondary_y_range": result["secondary_y_range"],
        }
