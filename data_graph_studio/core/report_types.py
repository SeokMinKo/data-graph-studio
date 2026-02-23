"""
Report Value Objects, Enums, and Dataclasses

Defines all data-transfer types used by the report generation pipeline:
TableData, ReportSection, ReportOptions, ReportData, ReportTemplate.
Re-exports enums and chart/comparison sub-types from their respective modules.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import polars as pl

from data_graph_studio.core.constants import DEFAULT_CHART_DPI
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
    """Tabular data snapshot ready for report rendering.

    Stores column names, row values, per-column format hints, and
    optional highlight rules. Captures both total and displayed row
    counts so templates can render truncation notices.
    """

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
        """Serialize this instance to a plain dictionary.

        Output: Dict[str, Any] — all fields via dataclasses.asdict
        """
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
        """Construct a TableData from a Polars DataFrame.

        Input: df — pl.DataFrame, source data
               id — str, unique identifier for this table
               title — str, display title
               table_type — str, one of "raw"/"grouped"/"pivot"/"top_n"/"comparison"
               max_rows — int | None, row cap for display (None = unlimited)
        Output: TableData — populated with columns, rows, and inferred column_formats
        Invariants: shown_rows <= total_rows; column_formats keyed by every column name
        """
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
    """A single logical section within a generated report.

    section_type controls which renderer handles the section content.
    Disabled sections (enabled=False) are skipped by report builders
    without removing them from the options UI.
    """

    id: str
    title: str
    section_type: str  # "summary", "overview", "statistics", "charts", "comparison", "tables", "appendix"
    enabled: bool = True
    content: Optional[Any] = None
    order: int = 0
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this section to a plain dictionary (content excluded).

        Output: Dict[str, Any] — id, title, section_type, enabled, order, description
        """
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
    """Configuration knobs for a single report generation run.

    Controls output format, theme, page layout, which sections to include,
    chart rendering parameters, table size caps, and template overrides.
    HTML interactive charts are only valid when format == ReportFormat.HTML.
    """
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
    chart_dpi: int = DEFAULT_CHART_DPI
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
        """Serialize report options to a JSON-safe dictionary.

        Output: Dict[str, Any] — enum fields serialized as their .value strings
        """
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
    """Aggregated payload passed to a report renderer.

    Holds all datasets, statistics, comparisons, charts, tables, and
    sections assembled by the report builder.  Helper methods provide
    a clean append API so builders don't reach into the lists directly.
    """
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
        """Recursively serialize all report data to a JSON-safe dictionary.

        Output: Dict[str, Any] — all nested objects serialized via their to_dict()
        """
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
        """Serialize to a pretty-printed JSON string.

        Input: indent — int, spaces per indentation level (default 2)
        Output: str — UTF-8 safe JSON with non-ASCII characters preserved
        """
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)

    def add_dataset(self, dataset: DatasetSummary) -> None:
        """Append a dataset summary to this report's dataset list.

        Input: dataset — DatasetSummary, the summary to append
        Invariants: self.datasets grows by exactly one entry
        """
        self.datasets.append(dataset)

    def add_statistics(self, dataset_id: str, stats: List[StatisticalSummary]) -> None:
        """Associate a list of statistical summaries with a dataset ID.

        Input: dataset_id — str, key for the statistics dict
               stats — List[StatisticalSummary], replaces any existing entry for that key
        Invariants: self.statistics[dataset_id] == stats after call
        """
        self.statistics[dataset_id] = stats

    def add_chart(self, chart: ChartData) -> None:
        """Append a chart data object to this report.

        Input: chart — ChartData, the chart to append
        Invariants: self.charts grows by exactly one entry
        """
        self.charts.append(chart)

    def add_table(self, table: TableData) -> None:
        """Append a table data object to this report.

        Input: table — TableData, the table to append
        Invariants: self.tables grows by exactly one entry
        """
        self.tables.append(table)

    def add_comparison(self, comparison: ComparisonResult) -> None:
        """Append a comparison result to this report.

        Input: comparison — ComparisonResult, the result to append
        Invariants: self.comparisons grows by exactly one entry
        """
        self.comparisons.append(comparison)

    def get_total_rows(self) -> int:
        """Return the sum of row_count across all datasets.

        Output: int — total row count; 0 if no datasets are present
        """
        return sum(d.row_count for d in self.datasets)

    def is_multi_dataset(self) -> bool:
        """Return True if more than one dataset is present in this report.

        Output: bool — True when len(self.datasets) > 1
        """
        return len(self.datasets) > 1


@dataclass
class ReportTemplate:
    """Visual and structural template applied during report rendering.

    Stores branding colors, fonts, optional header/footer HTML, and the
    ordered list of sections that should be included by default when this
    template is selected.
    """
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
        """Serialize this template to a JSON-safe dictionary.

        Output: Dict[str, Any] — id, name, description, author, created_at (ISO 8601),
                colors, font_family, and default_sections
        """
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
