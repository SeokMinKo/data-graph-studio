"""
Chart-related Report Types
차트 관련 레포트 타입 정의
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import base64

from data_graph_studio.core.report_enums import (
    ChartType,
    StatisticType,
)

__all__ = [
    "ChartStatisticsConfig",
    "ChartStatistics",
    "DEFAULT_CHART_STATISTICS",
    "get_default_statistics_for_chart",
    "ChartData",
]


@dataclass
class ChartStatisticsConfig:
    """차트 통계 설정 - 사용자가 선택 가능한 통계 옵션"""
    enabled_statistics: List[StatisticType] = field(default_factory=list)
    show_in_report: bool = True
    decimal_places: int = 2

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this statistics config to a JSON-compatible dictionary.

        Output: Dict[str, Any] — dict with enabled_statistics (list of str values),
                                   show_in_report (bool), decimal_places (int)
        """
        return {
            "enabled_statistics": [s.value for s in self.enabled_statistics],
            "show_in_report": self.show_in_report,
            "decimal_places": self.decimal_places,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChartStatisticsConfig":
        """Deserialize a ChartStatisticsConfig from a dictionary produced by to_dict.

        Input: data — Dict[str, Any], dict with keys enabled_statistics, show_in_report,
                      decimal_places; missing keys fall back to defaults
        Output: ChartStatisticsConfig — reconstructed instance
        """
        return cls(
            enabled_statistics=[StatisticType(s) for s in data.get("enabled_statistics", [])],
            show_in_report=data.get("show_in_report", True),
            decimal_places=data.get("decimal_places", 2),
        )


@dataclass
class ChartStatistics:
    """그래프별 통계 정보"""
    chart_type: str
    statistics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize these chart statistics to a JSON-compatible dictionary.

        Output: Dict[str, Any] — dict with chart_type (str) and statistics (dict of key→value)
        """
        return {
            "chart_type": self.chart_type,
            "statistics": self.statistics,
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Return the statistic value for key, or default if not present.

        Input: key — str, statistic name to look up
               default — Any, value to return when key is absent (default None)
        Output: Any — stored statistic value or the provided default
        """
        return self.statistics.get(key, default)

    def set(self, key: str, value: Any):
        """Set or overwrite a statistic value by key.

        Input: key — str, statistic name to store
               value — Any, the value to associate with key
        Output: None
        """
        self.statistics[key] = value


# 차트 타입별 기본 통계 설정
DEFAULT_CHART_STATISTICS: Dict[str, List[StatisticType]] = {
    "bar": [StatisticType.TOTAL, StatisticType.MEAN, StatisticType.MAX, StatisticType.MIN, StatisticType.COUNT],
    "horizontal_bar": [StatisticType.TOTAL, StatisticType.MEAN, StatisticType.MAX, StatisticType.MIN, StatisticType.COUNT],
    "stacked_bar": [StatisticType.TOTAL, StatisticType.MEAN, StatisticType.MAX, StatisticType.MIN, StatisticType.COUNT],
    "pie": [StatisticType.PERCENTAGE, StatisticType.TOTAL, StatisticType.COUNT],
    "donut": [StatisticType.PERCENTAGE, StatisticType.TOTAL, StatisticType.COUNT],
    "line": [
        StatisticType.START_VALUE, StatisticType.END_VALUE, StatisticType.CHANGE_PERCENT,
        StatisticType.MIN, StatisticType.MAX, StatisticType.MEAN, StatisticType.TREND_DIRECTION
    ],
    "area": [
        StatisticType.START_VALUE, StatisticType.END_VALUE, StatisticType.CHANGE_PERCENT,
        StatisticType.MIN, StatisticType.MAX, StatisticType.MEAN, StatisticType.TREND_DIRECTION
    ],
    "scatter": [
        StatisticType.CORRELATION, StatisticType.R_SQUARED, StatisticType.COUNT,
        StatisticType.X_RANGE, StatisticType.Y_RANGE],
    "bubble": [
        StatisticType.CORRELATION, StatisticType.R_SQUARED, StatisticType.COUNT,
        StatisticType.X_RANGE, StatisticType.Y_RANGE],
    "heatmap": [
        StatisticType.MAX, StatisticType.MIN, StatisticType.MEAN,
        StatisticType.MAX_CELL_LOCATION],
    "box": [
        StatisticType.MEDIAN, StatisticType.Q1, StatisticType.Q3, StatisticType.IQR,
        StatisticType.MIN, StatisticType.MAX, StatisticType.OUTLIER_COUNT
    ],
    "violin": [
        StatisticType.MEDIAN, StatisticType.Q1, StatisticType.Q3, StatisticType.IQR,
        StatisticType.MIN, StatisticType.MAX
    ],
    "histogram": [
        StatisticType.MEAN, StatisticType.MEDIAN, StatisticType.STD,
        StatisticType.SKEWNESS, StatisticType.MODE, StatisticType.BIN_COUNT
    ],
    "radar": [StatisticType.MEAN, StatisticType.MAX, StatisticType.MIN],
    "treemap": [StatisticType.TOTAL, StatisticType.COUNT, StatisticType.MAX, StatisticType.MIN],
    "funnel": [StatisticType.TOTAL, StatisticType.COUNT],
    "waterfall": [StatisticType.TOTAL, StatisticType.CHANGE_PERCENT],
    "candlestick": [StatisticType.MIN, StatisticType.MAX, StatisticType.MEAN],
}


def get_default_statistics_for_chart(chart_type: str) -> List[StatisticType]:
    """Return the default list of statistics for the given chart type.

    Input: chart_type — str, chart type name (e.g. "bar", "line", "scatter"); case-insensitive
    Output: List[StatisticType] — ordered list of default statistics for the chart type;
                                   falls back to [COUNT, MEAN, MIN, MAX] for unknown types
    """
    return DEFAULT_CHART_STATISTICS.get(chart_type.lower(), [
        StatisticType.COUNT, StatisticType.MEAN, StatisticType.MIN, StatisticType.MAX
    ])


@dataclass
class ChartData:
    """차트 데이터"""
    id: str
    chart_type: str
    title: str
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    group_column: Optional[str] = None
    aggregation: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    image_bytes: Optional[bytes] = None
    image_base64: Optional[str] = None
    image_format: str = "png"
    width: int = 800
    height: int = 600
    description: Optional[str] = None
    statistics: Optional[ChartStatistics] = None
    statistics_config: Optional[ChartStatisticsConfig] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this ChartData to a JSON-compatible dictionary, excluding raw image bytes.

        Output: Dict[str, Any] — all scalar fields plus image_base64 (str | None) and nested
                                   to_dict results for statistics and statistics_config when present
        """
        return {
            "id": self.id,
            "chart_type": self.chart_type,
            "title": self.title,
            "x_column": self.x_column,
            "y_column": self.y_column,
            "group_column": self.group_column,
            "aggregation": self.aggregation,
            "image_format": self.image_format,
            "width": self.width,
            "height": self.height,
            "description": self.description,
            "image_base64": self.image_base64,
            "statistics": self.statistics.to_dict() if self.statistics else None,
            "statistics_config": self.statistics_config.to_dict() if self.statistics_config else None,
        }

    def set_image(self, image_bytes: bytes, format: str = "png"):
        """Store raw image bytes and compute their Base64 representation.

        Input: image_bytes — bytes, raw image data (e.g. PNG or SVG content)
               format — str, image format label stored in image_format (default "png")
        Output: None
        Invariants: after this call image_bytes, image_format, and image_base64 are all set
        """
        self.image_bytes = image_bytes
        self.image_format = format
        self.image_base64 = base64.b64encode(image_bytes).decode('utf-8')

    def set_statistics(self, statistics: ChartStatistics):
        """Attach a ChartStatistics object to this chart data.

        Input: statistics — ChartStatistics, computed statistics to associate with this chart
        Output: None
        """
        self.statistics = statistics

    def get_statistics_for_display(self) -> Dict[str, Any]:
        """Return the statistics subset appropriate for display, respecting user configuration.

        When statistics_config.enabled_statistics is set, only those statistics are included.
        When not configured, falls back to the chart type's default statistic list.
        Only statistics with non-None values are included in the result.

        Output: Dict[str, Any] — mapping of statistic value string to computed value;
                                   empty dict when no statistics are attached
        """
        if not self.statistics:
            return {}

        if self.statistics_config and self.statistics_config.enabled_statistics:
            # 사용자가 선택한 통계만 반환
            return {
                stat.value: self.statistics.get(stat.value)
                for stat in self.statistics_config.enabled_statistics
                if self.statistics.get(stat.value) is not None
            }
        else:
            # 기본 통계 반환
            default_stats = get_default_statistics_for_chart(self.chart_type)
            return {
                stat.value: self.statistics.get(stat.value)
                for stat in default_stats
                if self.statistics.get(stat.value) is not None
            }
