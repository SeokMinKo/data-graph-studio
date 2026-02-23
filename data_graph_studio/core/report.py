"""
Report Generation Core Module
레포트 생성 핵심 모듈

Supports: HTML, PDF, DOCX, PPTX, JSON, Markdown
"""

from typing import Optional, List, Dict, Union
from pathlib import Path
from abc import ABC, abstractmethod

from data_graph_studio.core.exceptions import ExportError

import polars as pl

from data_graph_studio.core.report_types import (
    ReportFormat, ReportTheme, PageSize, PageOrientation,
    ChartImageFormat, ChartType, StatisticType,
    ChartStatisticsConfig, ChartStatistics, ReportMetadata,
    DatasetSummary, StatisticalSummary, ComparisonResult,
    DifferenceAnalysis, ChartData, TableData, ReportSection,
    ReportOptions, ReportData, ReportTemplate,
    DEFAULT_CHART_STATISTICS, get_default_statistics_for_chart,
)

__all__ = [
    "ReportFormat", "ReportTheme", "PageSize", "PageOrientation",
    "ChartImageFormat", "ChartType", "StatisticType",
    "ChartStatisticsConfig", "ChartStatistics", "ReportMetadata",
    "DatasetSummary", "StatisticalSummary", "ComparisonResult",
    "DifferenceAnalysis", "ChartData", "TableData", "ReportSection",
    "ReportOptions", "ReportData", "ReportTemplate",
    "DEFAULT_CHART_STATISTICS", "get_default_statistics_for_chart",
    "ReportGenerator", "ReportManager",
    "collect_statistics_from_dataframe", "create_comparison_table",
]


class ReportGenerator(ABC):
    """레포트 생성기 추상 클래스"""

    def __init__(self, template: Optional[ReportTemplate] = None):
        """Initialise the generator with an optional custom template.

        Input: template — Optional[ReportTemplate], template to use; defaults to _get_default_template()
        Output: None
        Invariants: self.template is always a valid ReportTemplate instance
        """
        self.template = template or self._get_default_template()

    @abstractmethod
    def generate(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> bytes:
        """Generate report bytes in the format implemented by the subclass.

        Input: report_data — ReportData, structured report content
               options — ReportOptions, formatting and output options
        Output: bytes — serialised report content
        """
        pass

    def save(
        self,
        report_data: ReportData,
        options: ReportOptions,
        output_path: Union[str, Path]
    ) -> Path:
        """Generate a report and write it to disk.

        Input: report_data — ReportData, structured report content
               options — ReportOptions, formatting and output options
               output_path — Union[str, Path], destination file path
        Output: Path — resolved path of the written file
        Raises: OSError — if the file cannot be opened or written
        """
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
        """Generate a preview of the report (delegates to generate by default).

        Input: report_data — ReportData, structured report content
               options — ReportOptions, formatting and output options
               max_pages — int, maximum pages to include in the preview (hint for subclasses)
        Output: bytes — preview report content
        """
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
        """Format a numeric value as a human-readable string with K/M suffix.

        Input: value — Optional[float], value to format; None returns "-"
               decimals — int, decimal places in the formatted output
        Output: str — formatted number string, e.g. "1.23K", "4.56M", or "-"
        """
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
        """Format a float as a percentage string.

        Input: value — Optional[float], percentage value; None returns "-"
               decimals — int, decimal places in the formatted output
        Output: str — formatted string, e.g. "12.3%", or "-"
        """
        if value is None:
            return "-"
        return f"{value:.{decimals}f}%"

    @staticmethod
    def format_bytes(bytes_value: int) -> str:
        """Format a byte count as a human-readable size string.

        Input: bytes_value — int, size in bytes
        Output: str — formatted string with unit, e.g. "1.5 MB", "3.2 GB"
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_value < 1024:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f} TB"


class ReportManager:
    """레포트 관리자"""

    def __init__(self):
        """Initialise the manager with empty generator registry and default templates.

        Output: None
        Invariants: self.templates contains at least "default", "corporate", "modern", and "minimal" after init
        """
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
        """Register a generator for a specific report format, replacing any prior registration.

        Input: format — ReportFormat, the output format this generator handles
               generator — ReportGenerator, the generator instance to register
        Output: None
        """
        self.generators[format] = generator

    def get_generator(self, format: ReportFormat) -> Optional[ReportGenerator]:
        """Return the registered generator for the given format, or None if not registered.

        Input: format — ReportFormat, the format to look up
        Output: Optional[ReportGenerator] — registered generator, or None
        """
        return self.generators.get(format)

    def generate_report(
        self,
        report_data: ReportData,
        options: ReportOptions,
        output_path: Optional[Union[str, Path]] = None
    ) -> Union[bytes, Path]:
        """Generate a report, optionally saving it to disk.

        Input: report_data — ReportData, structured report content
               options — ReportOptions, formatting options including format and template_id
               output_path — Optional[Union[str, Path]], if provided the report is saved here
        Output: Union[bytes, Path] — raw bytes when no output_path; resolved Path when saved
        Raises: ExportError — when no generator is registered for the requested format
        """
        generator = self.generators.get(options.format)
        if not generator:
            raise ExportError(
                f"Unsupported format: {options.format}",
                operation="generate_report",
                context={"format": str(options.format)},
            )

        # 템플릿 적용
        if options.template_id and options.template_id in self.templates:
            generator.template = self.templates[options.template_id]

        if output_path:
            return generator.save(report_data, options, output_path)
        return generator.generate(report_data, options)

    def add_template(self, template: ReportTemplate):
        """Register a custom template, keyed by template.id.

        Input: template — ReportTemplate, the template to add; replaces any existing template with the same id
        Output: None
        """
        self.templates[template.id] = template

    def get_template(self, template_id: str) -> Optional[ReportTemplate]:
        """Return the template with the given id, or None if not found.

        Input: template_id — str, the id of the template to retrieve
        Output: Optional[ReportTemplate] — the matching template, or None
        """
        return self.templates.get(template_id)

    def list_templates(self) -> List[ReportTemplate]:
        """Return all registered templates as a list.

        Output: List[ReportTemplate] — all templates in registration order
        """
        return list(self.templates.values())

    def list_formats(self) -> List[ReportFormat]:
        """Return all report formats that have a registered generator.

        Output: List[ReportFormat] — formats with an active generator
        """
        return list(self.generators.keys())


# Utility functions for report data collection
def collect_statistics_from_dataframe(
    df: pl.DataFrame,
    dataset_id: str,
    dataset_name: str
) -> List[StatisticalSummary]:
    """Compute per-column statistics for all numeric columns in a DataFrame.

    Input: df — pl.DataFrame, the source data
           dataset_id — str, identifier for the originating dataset
           dataset_name — str, display name for the originating dataset
    Output: List[StatisticalSummary] — one entry per numeric column; empty if no numeric columns
    """
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
    """Build a cross-dataset comparison TableData for a single statistical metric.

    Input: statistics — Dict[str, List[StatisticalSummary]], mapping dataset_id to its column stats
           metric — str, attribute name on StatisticalSummary to compare (default "mean")
    Output: TableData — table with columns [Column, dataset_id1, dataset_id2, ...] sorted by column name
    """
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
