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
        """Serialize this statistics config to a JSON-compatible dictionary."""
        return {
            "enabled_statistics": [s.value for s in self.enabled_statistics],
            "show_in_report": self.show_in_report,
            "decimal_places": self.decimal_places,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChartStatisticsConfig":
        """Deserialize a ChartStatisticsConfig from a dictionary produced by to_dict."""
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
        """Serialize these chart statistics to a JSON-compatible dictionary."""
        return {
            "chart_type": self.chart_type,
            "statistics": self.statistics,
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Return the statistic value for key, or default if not present."""
        return self.statistics.get(key, default)

    def set(self, key: str, value: Any):
        """Set a statistic value by key."""
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
    """차트 타입에 대한 기본 통계 목록 반환"""
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
        """딕셔너리로 변환 (이미지 바이트 제외)"""
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
        """이미지 설정 및 Base64 인코딩"""
        self.image_bytes = image_bytes
        self.image_format = format
        self.image_base64 = base64.b64encode(image_bytes).decode('utf-8')

    def set_statistics(self, statistics: ChartStatistics):
        """통계 설정"""
        self.statistics = statistics

    def get_statistics_for_display(self) -> Dict[str, Any]:
        """표시용 통계 반환 (설정된 통계만)"""
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
