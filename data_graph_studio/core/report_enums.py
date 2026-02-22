"""
Report Enum Definitions
레포트 열거형 정의 모듈
"""

from enum import Enum


class ReportFormat(Enum):
    """레포트 출력 형식"""
    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    JSON = "json"
    MARKDOWN = "markdown"


class ReportTheme(Enum):
    """레포트 테마"""
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"
    CORPORATE = "corporate"


class PageSize(Enum):
    """페이지 크기"""
    A4 = "a4"
    LETTER = "letter"
    LEGAL = "legal"
    A3 = "a3"


class PageOrientation(Enum):
    """페이지 방향"""
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class ChartImageFormat(Enum):
    """차트 이미지 형식"""
    PNG = "png"
    SVG = "svg"
    EMBEDDED = "embedded"  # Base64 embedded


class ChartType(Enum):
    """차트 타입"""
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    HEATMAP = "heatmap"
    BOX = "box"
    HISTOGRAM = "histogram"
    HORIZONTAL_BAR = "horizontal_bar"
    STACKED_BAR = "stacked_bar"
    DONUT = "donut"
    AREA = "area"
    BUBBLE = "bubble"
    RADAR = "radar"
    TREEMAP = "treemap"
    FUNNEL = "funnel"
    WATERFALL = "waterfall"
    CANDLESTICK = "candlestick"
    VIOLIN = "violin"


class StatisticType(Enum):
    """통계 타입"""
    # Common
    COUNT = "count"
    TOTAL = "total"
    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    STD = "std"

    # Bar/Line specific
    CHANGE_PERCENT = "change_percent"
    START_VALUE = "start_value"
    END_VALUE = "end_value"
    TREND_DIRECTION = "trend_direction"

    # Pie/Donut specific
    PERCENTAGE = "percentage"

    # Scatter specific
    CORRELATION = "correlation"
    R_SQUARED = "r_squared"
    X_RANGE = "x_range"
    Y_RANGE = "y_range"

    # Heatmap specific
    MAX_CELL_LOCATION = "max_cell_location"
    MIN_CELL_LOCATION = "min_cell_location"

    # Box plot specific
    Q1 = "q1"
    Q3 = "q3"
    IQR = "iqr"
    OUTLIER_COUNT = "outlier_count"

    # Histogram specific
    SKEWNESS = "skewness"
    MODE = "mode"
    BIN_COUNT = "bin_count"


__all__ = [
    "ReportFormat",
    "ReportTheme",
    "PageSize",
    "PageOrientation",
    "ChartImageFormat",
    "ChartType",
    "StatisticType",
]
