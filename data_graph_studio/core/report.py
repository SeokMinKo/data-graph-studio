"""
Report Generation Core Module
레포트 생성 핵심 모듈

Supports: HTML, PDF, DOCX, PPTX, JSON, Markdown
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from datetime import datetime
from pathlib import Path
from abc import ABC, abstractmethod
import json
import base64

import polars as pl


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
    "bar": [
        StatisticType.TOTAL, StatisticType.MEAN, StatisticType.MAX, 
        StatisticType.MIN, StatisticType.COUNT
    ],
    "horizontal_bar": [
        StatisticType.TOTAL, StatisticType.MEAN, StatisticType.MAX, 
        StatisticType.MIN, StatisticType.COUNT
    ],
    "stacked_bar": [
        StatisticType.TOTAL, StatisticType.MEAN, StatisticType.MAX, 
        StatisticType.MIN, StatisticType.COUNT
    ],
    "pie": [
        StatisticType.PERCENTAGE, StatisticType.TOTAL, StatisticType.COUNT
    ],
    "donut": [
        StatisticType.PERCENTAGE, StatisticType.TOTAL, StatisticType.COUNT
    ],
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
        StatisticType.X_RANGE, StatisticType.Y_RANGE
    ],
    "bubble": [
        StatisticType.CORRELATION, StatisticType.R_SQUARED, StatisticType.COUNT,
        StatisticType.X_RANGE, StatisticType.Y_RANGE
    ],
    "heatmap": [
        StatisticType.MAX, StatisticType.MIN, StatisticType.MEAN, 
        StatisticType.MAX_CELL_LOCATION
    ],
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
    "radar": [
        StatisticType.MEAN, StatisticType.MAX, StatisticType.MIN
    ],
    "treemap": [
        StatisticType.TOTAL, StatisticType.COUNT, StatisticType.MAX, StatisticType.MIN
    ],
    "funnel": [
        StatisticType.TOTAL, StatisticType.COUNT
    ],
    "waterfall": [
        StatisticType.TOTAL, StatisticType.CHANGE_PERCENT
    ],
    "candlestick": [
        StatisticType.MIN, StatisticType.MAX, StatisticType.MEAN
    ],
}


def get_default_statistics_for_chart(chart_type: str) -> List[StatisticType]:
    """차트 타입에 대한 기본 통계 목록 반환"""
    return DEFAULT_CHART_STATISTICS.get(chart_type.lower(), [
        StatisticType.COUNT, StatisticType.MEAN, StatisticType.MIN, StatisticType.MAX
    ])


@dataclass
class ReportMetadata:
    """레포트 메타데이터"""
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0"
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    logo_path: Optional[str] = None
    logo_base64: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
            "description": self.description,
            "tags": self.tags,
            "logo_path": self.logo_path,
        }


@dataclass
class DatasetSummary:
    """데이터셋 요약 정보"""
    id: str
    name: str
    file_path: Optional[str] = None
    row_count: int = 0
    column_count: int = 0
    columns: List[str] = field(default_factory=list)
    column_types: Dict[str, str] = field(default_factory=dict)
    date_range: Optional[Dict[str, str]] = None
    memory_bytes: int = 0
    color: str = "#1f77b4"
    missing_values: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return asdict(self)

    @classmethod
    def from_dataframe(
        cls,
        df: pl.DataFrame,
        id: str,
        name: str,
        file_path: Optional[str] = None,
        color: str = "#1f77b4"
    ) -> "DatasetSummary":
        """Polars DataFrame에서 생성"""
        columns = df.columns
        column_types = {col: str(df[col].dtype) for col in columns}

        # 결측값 계산
        missing_values = {}
        for col in columns:
            null_count = df[col].null_count()
            if null_count > 0:
                missing_values[col] = null_count

        # 날짜 범위 계산 (날짜 컬럼이 있는 경우)
        date_range = None
        for col in columns:
            if df[col].dtype in [pl.Date, pl.Datetime]:
                try:
                    min_date = df[col].min()
                    max_date = df[col].max()
                    if min_date and max_date:
                        date_range = {
                            "column": col,
                            "min": str(min_date),
                            "max": str(max_date)
                        }
                        break
                except Exception:
                    pass

        return cls(
            id=id,
            name=name,
            file_path=file_path,
            row_count=len(df),
            column_count=len(columns),
            columns=columns,
            column_types=column_types,
            date_range=date_range,
            memory_bytes=df.estimated_size(),
            color=color,
            missing_values=missing_values
        )


@dataclass
class StatisticalSummary:
    """통계 요약"""
    column: str
    dataset_id: str = ""
    dataset_name: str = ""
    count: int = 0
    null_count: int = 0
    sum: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    variance: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    q1: Optional[float] = None
    q3: Optional[float] = None
    iqr: Optional[float] = None
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return asdict(self)

    @classmethod
    def from_series(
        cls,
        series: pl.Series,
        column: str,
        dataset_id: str = "",
        dataset_name: str = ""
    ) -> "StatisticalSummary":
        """Polars Series에서 생성"""
        stats = StatisticalSummary(
            column=column,
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            count=len(series),
            null_count=series.null_count()
        )

        # 수치형 컬럼인 경우 통계 계산
        if series.dtype.is_numeric():
            try:
                stats.sum = float(series.sum()) if series.sum() is not None else None
                stats.mean = float(series.mean()) if series.mean() is not None else None
                stats.median = float(series.median()) if series.median() is not None else None
                stats.std = float(series.std()) if series.std() is not None else None
                stats.variance = float(series.var()) if series.var() is not None else None
                stats.min = float(series.min()) if series.min() is not None else None
                stats.max = float(series.max()) if series.max() is not None else None

                # Quantiles
                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                stats.q1 = float(q1) if q1 is not None else None
                stats.q3 = float(q3) if q3 is not None else None
                if stats.q1 is not None and stats.q3 is not None:
                    stats.iqr = stats.q3 - stats.q1

                # Skewness & Kurtosis
                try:
                    stats.skewness = float(series.skew()) if hasattr(series, 'skew') else None
                    stats.kurtosis = float(series.kurtosis()) if hasattr(series, 'kurtosis') else None
                except Exception:
                    pass

            except Exception:
                pass

        return stats


@dataclass
class ComparisonResult:
    """비교 분석 결과"""
    dataset_a_id: str
    dataset_a_name: str
    dataset_b_id: str
    dataset_b_name: str
    column: str
    test_type: str
    test_statistic: float
    p_value: float
    effect_size: Optional[float] = None
    effect_size_interpretation: str = ""
    significant: bool = False
    significance_level: str = ""  # "", "*", "**", "***"
    interpretation: str = ""
    confidence_interval: Optional[tuple] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        result = asdict(self)
        if self.confidence_interval:
            result["confidence_interval"] = list(self.confidence_interval)
        return result

    def get_significance_symbol(self) -> str:
        """유의수준 기호 반환"""
        if self.p_value < 0.001:
            return "***"
        elif self.p_value < 0.01:
            return "**"
        elif self.p_value < 0.05:
            return "*"
        return ""


@dataclass
class DifferenceAnalysis:
    """차이 분석 결과"""
    dataset_a_id: str
    dataset_a_name: str
    dataset_b_id: str
    dataset_b_name: str
    key_column: str
    value_column: str
    total_records: int = 0
    matched_records: int = 0
    positive_count: int = 0  # A > B
    negative_count: int = 0  # A < B
    neutral_count: int = 0   # A == B
    positive_percentage: float = 0.0
    negative_percentage: float = 0.0
    neutral_percentage: float = 0.0
    total_difference: float = 0.0
    mean_difference: float = 0.0
    top_differences: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return asdict(self)


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


@dataclass
class TableData:
    """테이블 데이터"""
    id: str
    title: str
    table_type: str  # "raw", "grouped", "pivot", "top_n", "comparison"
    columns: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    column_formats: Dict[str, str] = field(default_factory=dict)
    highlight_rules: List[Dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0
    shown_rows: int = 0
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return asdict(self)

    @classmethod
    def from_dataframe(
        cls,
        df: pl.DataFrame,
        id: str,
        title: str,
        table_type: str = "raw",
        max_rows: Optional[int] = 100
    ) -> "TableData":
        """DataFrame에서 생성"""
        total_rows = len(df)

        if max_rows and total_rows > max_rows:
            df_display = df.head(max_rows)
            shown_rows = max_rows
        else:
            df_display = df
            shown_rows = total_rows

        columns = df_display.columns
        rows = df_display.to_numpy().tolist()

        # 컬럼 형식 추정
        column_formats = {}
        for col in columns:
            dtype = df[col].dtype
            if dtype.is_numeric():
                if dtype.is_integer():
                    column_formats[col] = "integer"
                else:
                    column_formats[col] = "float"
            elif dtype == pl.Date or dtype == pl.Datetime:
                column_formats[col] = "date"
            else:
                column_formats[col] = "text"

        return cls(
            id=id,
            title=title,
            table_type=table_type,
            columns=columns,
            rows=rows,
            column_formats=column_formats,
            total_rows=total_rows,
            shown_rows=shown_rows
        )


@dataclass
class ReportSection:
    """레포트 섹션"""
    id: str
    title: str
    section_type: str  # "summary", "overview", "statistics", "charts", "comparison", "tables", "appendix"
    enabled: bool = True
    content: Optional[Any] = None
    order: int = 0
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "title": self.title,
            "section_type": self.section_type,
            "enabled": self.enabled,
            "order": self.order,
            "description": self.description
        }


@dataclass
class ReportOptions:
    """레포트 생성 옵션"""
    format: ReportFormat = ReportFormat.HTML
    theme: ReportTheme = ReportTheme.LIGHT
    page_size: PageSize = PageSize.A4
    orientation: PageOrientation = PageOrientation.PORTRAIT

    # 섹션 포함 여부
    include_executive_summary: bool = True
    include_data_overview: bool = True
    include_statistics: bool = True
    include_visualizations: bool = True
    include_comparison: bool = True  # 멀티데이터 시
    include_tables: bool = True
    include_appendix: bool = False

    # 차트 옵션
    chart_format: ChartImageFormat = ChartImageFormat.PNG
    interactive_charts: bool = False  # HTML만
    chart_dpi: int = 150
    chart_width: int = 800
    chart_height: int = 600
    include_chart_statistics: bool = True  # 차트별 통계 포함 여부

    # 테이블 옵션
    table_max_rows: int = 100
    include_raw_data: bool = False

    # PDF/DOCX 옵션
    margins: Dict[str, float] = field(default_factory=lambda: {
        "top": 2.54, "bottom": 2.54, "left": 2.54, "right": 2.54
    })
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    watermark: Optional[str] = None

    # PPTX 옵션
    slide_size: str = "16:9"  # "16:9", "4:3"
    one_chart_per_slide: bool = True
    include_speaker_notes: bool = False

    # 템플릿
    template_id: Optional[str] = None
    template_path: Optional[str] = None

    # 언어
    language: str = "ko"  # "ko", "en"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "format": self.format.value,
            "theme": self.theme.value,
            "page_size": self.page_size.value,
            "orientation": self.orientation.value,
            "include_executive_summary": self.include_executive_summary,
            "include_data_overview": self.include_data_overview,
            "include_statistics": self.include_statistics,
            "include_visualizations": self.include_visualizations,
            "include_comparison": self.include_comparison,
            "include_tables": self.include_tables,
            "include_appendix": self.include_appendix,
            "chart_format": self.chart_format.value,
            "interactive_charts": self.interactive_charts,
            "chart_dpi": self.chart_dpi,
            "include_chart_statistics": self.include_chart_statistics,
            "table_max_rows": self.table_max_rows,
            "language": self.language
        }


@dataclass
class ReportData:
    """레포트 전체 데이터"""
    metadata: ReportMetadata
    datasets: List[DatasetSummary] = field(default_factory=list)
    statistics: Dict[str, List[StatisticalSummary]] = field(default_factory=dict)
    comparisons: List[ComparisonResult] = field(default_factory=list)
    differences: List[DifferenceAnalysis] = field(default_factory=list)
    charts: List[ChartData] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)
    sections: List[ReportSection] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    methodology_notes: List[str] = field(default_factory=list)
    data_quality_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "metadata": self.metadata.to_dict(),
            "datasets": [d.to_dict() for d in self.datasets],
            "statistics": {
                k: [s.to_dict() for s in v]
                for k, v in self.statistics.items()
            },
            "comparisons": [c.to_dict() for c in self.comparisons],
            "differences": [d.to_dict() for d in self.differences],
            "charts": [c.to_dict() for c in self.charts],
            "tables": [t.to_dict() for t in self.tables],
            "sections": [s.to_dict() for s in self.sections],
            "key_findings": self.key_findings,
            "recommendations": self.recommendations,
            "methodology_notes": self.methodology_notes,
            "data_quality_notes": self.data_quality_notes
        }

    def to_json(self, indent: int = 2) -> str:
        """JSON 문자열로 변환"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)

    def add_dataset(self, dataset: DatasetSummary):
        """데이터셋 추가"""
        self.datasets.append(dataset)

    def add_statistics(self, dataset_id: str, stats: List[StatisticalSummary]):
        """통계 추가"""
        self.statistics[dataset_id] = stats

    def add_chart(self, chart: ChartData):
        """차트 추가"""
        self.charts.append(chart)

    def add_table(self, table: TableData):
        """테이블 추가"""
        self.tables.append(table)

    def add_comparison(self, comparison: ComparisonResult):
        """비교 결과 추가"""
        self.comparisons.append(comparison)

    def get_total_rows(self) -> int:
        """전체 행 수 반환"""
        return sum(d.row_count for d in self.datasets)

    def is_multi_dataset(self) -> bool:
        """멀티 데이터셋 여부"""
        return len(self.datasets) > 1


@dataclass
class ReportTemplate:
    """레포트 템플릿"""
    id: str
    name: str
    description: str = ""
    author: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    # 스타일
    primary_color: str = "#1f77b4"
    secondary_color: str = "#ff7f0e"
    accent_color: str = "#2ca02c"
    font_family: str = "Arial, sans-serif"
    heading_font: str = "Arial, sans-serif"

    # 레이아웃
    header_html: Optional[str] = None
    footer_html: Optional[str] = None
    css_styles: Optional[str] = None
    logo_path: Optional[str] = None

    # 기본 옵션
    default_sections: List[str] = field(default_factory=lambda: [
        "executive_summary", "data_overview", "statistics",
        "visualizations", "comparison", "tables"
    ])

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "accent_color": self.accent_color,
            "font_family": self.font_family,
            "default_sections": self.default_sections
        }


class ReportGenerator(ABC):
    """레포트 생성기 추상 클래스"""

    def __init__(self, template: Optional[ReportTemplate] = None):
        self.template = template or self._get_default_template()

    @abstractmethod
    def generate(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> bytes:
        """레포트 생성"""
        pass

    def save(
        self,
        report_data: ReportData,
        options: ReportOptions,
        output_path: Union[str, Path]
    ) -> Path:
        """레포트 파일 저장"""
        output_path = Path(output_path)
        content = self.generate(report_data, options)

        mode = 'wb' if isinstance(content, bytes) else 'w'
        encoding = None if mode == 'wb' else 'utf-8'

        with open(output_path, mode, encoding=encoding) as f:
            f.write(content)

        return output_path

    def preview(
        self,
        report_data: ReportData,
        options: ReportOptions,
        max_pages: int = 2
    ) -> bytes:
        """미리보기 생성"""
        return self.generate(report_data, options)

    def _get_default_template(self) -> ReportTemplate:
        """기본 템플릿 반환"""
        return ReportTemplate(
            id="default",
            name="Default Template",
            description="Standard report template"
        )

    @staticmethod
    def format_number(value: Optional[float], decimals: int = 2) -> str:
        """숫자 포맷팅"""
        if value is None:
            return "-"
        if abs(value) >= 1_000_000:
            return f"{value/1_000_000:,.{decimals}f}M"
        elif abs(value) >= 1_000:
            return f"{value/1_000:,.{decimals}f}K"
        else:
            return f"{value:,.{decimals}f}"

    @staticmethod
    def format_percentage(value: Optional[float], decimals: int = 1) -> str:
        """퍼센트 포맷팅"""
        if value is None:
            return "-"
        return f"{value:.{decimals}f}%"

    @staticmethod
    def format_bytes(bytes_value: int) -> str:
        """바이트 크기 포맷팅"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_value < 1024:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f} TB"


class ReportManager:
    """레포트 관리자"""

    def __init__(self):
        self.generators: Dict[ReportFormat, ReportGenerator] = {}
        self.templates: Dict[str, ReportTemplate] = {}
        self._init_default_templates()

    def _init_default_templates(self):
        """기본 템플릿 초기화"""
        # Default template
        self.templates["default"] = ReportTemplate(
            id="default",
            name="Default",
            description="Standard report layout"
        )

        # Corporate template
        self.templates["corporate"] = ReportTemplate(
            id="corporate",
            name="Corporate",
            description="Professional corporate style",
            primary_color="#003366",
            secondary_color="#666666",
            accent_color="#0066cc"
        )

        # Modern template
        self.templates["modern"] = ReportTemplate(
            id="modern",
            name="Modern",
            description="Clean, modern design",
            primary_color="#6366f1",
            secondary_color="#ec4899",
            accent_color="#14b8a6"
        )

        # Minimal template
        self.templates["minimal"] = ReportTemplate(
            id="minimal",
            name="Minimal",
            description="Minimalist style",
            primary_color="#171717",
            secondary_color="#737373",
            accent_color="#3b82f6"
        )

    def register_generator(
        self,
        format: ReportFormat,
        generator: ReportGenerator
    ):
        """생성기 등록"""
        self.generators[format] = generator

    def get_generator(self, format: ReportFormat) -> Optional[ReportGenerator]:
        """생성기 조회"""
        return self.generators.get(format)

    def generate_report(
        self,
        report_data: ReportData,
        options: ReportOptions,
        output_path: Optional[Union[str, Path]] = None
    ) -> Union[bytes, Path]:
        """레포트 생성"""
        generator = self.generators.get(options.format)
        if not generator:
            raise ValueError(f"Unsupported format: {options.format}")

        # 템플릿 적용
        if options.template_id and options.template_id in self.templates:
            generator.template = self.templates[options.template_id]

        if output_path:
            return generator.save(report_data, options, output_path)
        return generator.generate(report_data, options)

    def add_template(self, template: ReportTemplate):
        """템플릿 추가"""
        self.templates[template.id] = template

    def get_template(self, template_id: str) -> Optional[ReportTemplate]:
        """템플릿 조회"""
        return self.templates.get(template_id)

    def list_templates(self) -> List[ReportTemplate]:
        """템플릿 목록 조회"""
        return list(self.templates.values())

    def list_formats(self) -> List[ReportFormat]:
        """지원 형식 목록"""
        return list(self.generators.keys())


# Utility functions for report data collection
def collect_statistics_from_dataframe(
    df: pl.DataFrame,
    dataset_id: str,
    dataset_name: str
) -> List[StatisticalSummary]:
    """DataFrame에서 통계 수집"""
    stats = []
    for col in df.columns:
        if df[col].dtype.is_numeric():
            stat = StatisticalSummary.from_series(
                df[col],
                column=col,
                dataset_id=dataset_id,
                dataset_name=dataset_name
            )
            stats.append(stat)
    return stats


def create_comparison_table(
    statistics: Dict[str, List[StatisticalSummary]],
    metric: str = "mean"
) -> TableData:
    """비교 테이블 생성"""
    # 공통 컬럼 찾기
    all_columns = set()
    for dataset_stats in statistics.values():
        for stat in dataset_stats:
            all_columns.add(stat.column)

    columns = ["Column"] + [list(statistics.keys())[i] for i in range(len(statistics))]
    rows = []

    for col in sorted(all_columns):
        row = [col]
        for dataset_id, dataset_stats in statistics.items():
            value = None
            for stat in dataset_stats:
                if stat.column == col:
                    value = getattr(stat, metric, None)
                    break
            row.append(ReportGenerator.format_number(value))
        rows.append(row)

    return TableData(
        id="comparison_table",
        title=f"Comparison Table ({metric.title()})",
        table_type="comparison",
        columns=columns,
        rows=rows,
        total_rows=len(rows),
        shown_rows=len(rows)
    )
