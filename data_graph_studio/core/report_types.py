"""
Report Value Objects, Enums, and Dataclasses
레포트 타입 정의 모듈
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import polars as pl

from data_graph_studio.core.report_enums import (
    ReportFormat,
    ReportTheme,
    PageSize,
    PageOrientation,
    ChartImageFormat,
    ChartType,
    StatisticType,
)
# Re-export chart types
from data_graph_studio.core.chart_report_types import (
    ChartStatisticsConfig, ChartStatistics, DEFAULT_CHART_STATISTICS,
    get_default_statistics_for_chart, ChartData,
)
# Re-export comparison types
from data_graph_studio.core.comparison_report_types import (
    ReportMetadata, DatasetSummary, StatisticalSummary,
    ComparisonResult, DifferenceAnalysis,
)

__all__ = [
    "ReportFormat", "ReportTheme", "PageSize", "PageOrientation",
    "ChartImageFormat", "ChartType", "StatisticType",
    "ChartStatisticsConfig", "ChartStatistics", "DEFAULT_CHART_STATISTICS",
    "get_default_statistics_for_chart", "ReportMetadata", "DatasetSummary",
    "StatisticalSummary", "ComparisonResult", "DifferenceAnalysis",
    "ChartData", "TableData", "ReportSection", "ReportOptions",
    "ReportData", "ReportTemplate",
]


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
