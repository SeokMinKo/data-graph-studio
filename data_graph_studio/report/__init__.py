"""
Report Generation Module
레포트 생성 모듈

Exports:
    - ReportManager: 레포트 관리자
    - HTMLReportGenerator: HTML 레포트 생성기
    - PDFReportGenerator: PDF 레포트 생성기
    - DOCXReportGenerator: Word 문서 생성기
    - PPTXReportGenerator: PowerPoint 생성기
    - MarkdownReportGenerator: Markdown 레포트 생성기
"""

from data_graph_studio.core.report import (
    ReportFormat,
    ReportTheme,
    PageSize,
    PageOrientation,
    ChartImageFormat,
    ChartType,
    StatisticType,
    ChartStatisticsConfig,
    ChartStatistics,
    DEFAULT_CHART_STATISTICS,
    get_default_statistics_for_chart,
    ReportMetadata,
    DatasetSummary,
    StatisticalSummary,
    ComparisonResult,
    DifferenceAnalysis,
    ChartData,
    TableData,
    ReportSection,
    ReportOptions,
    ReportData,
    ReportTemplate,
    ReportGenerator,
    ReportManager,
    collect_statistics_from_dataframe,
    create_comparison_table,
)

from data_graph_studio.report.html_generator import HTMLReportGenerator
from data_graph_studio.report.pdf_generator import PDFReportGenerator
from data_graph_studio.report.docx_generator import DOCXReportGenerator
from data_graph_studio.report.pptx_generator import PPTXReportGenerator
from data_graph_studio.report.markdown_generator import MarkdownReportGenerator

__all__ = [
    # Enums
    "ReportFormat",
    "ReportTheme",
    "PageSize",
    "PageOrientation",
    "ChartImageFormat",
    "ChartType",
    "StatisticType",
    # Chart Statistics
    "ChartStatisticsConfig",
    "ChartStatistics",
    "DEFAULT_CHART_STATISTICS",
    "get_default_statistics_for_chart",
    # Data classes
    "ReportMetadata",
    "DatasetSummary",
    "StatisticalSummary",
    "ComparisonResult",
    "DifferenceAnalysis",
    "ChartData",
    "TableData",
    "ReportSection",
    "ReportOptions",
    "ReportData",
    "ReportTemplate",
    # Generators
    "ReportGenerator",
    "HTMLReportGenerator",
    "PDFReportGenerator",
    "DOCXReportGenerator",
    "PPTXReportGenerator",
    "MarkdownReportGenerator",
    # Manager
    "ReportManager",
    # Utilities
    "collect_statistics_from_dataframe",
    "create_comparison_table",
]


def create_report_manager() -> ReportManager:
    """
    기본 설정된 ReportManager 생성

    Returns:
        모든 생성기가 등록된 ReportManager
    """
    manager = ReportManager()

    # 생성기 등록
    manager.register_generator(ReportFormat.HTML, HTMLReportGenerator())
    manager.register_generator(ReportFormat.PDF, PDFReportGenerator())
    manager.register_generator(ReportFormat.DOCX, DOCXReportGenerator())
    manager.register_generator(ReportFormat.PPTX, PPTXReportGenerator())
    manager.register_generator(ReportFormat.MARKDOWN, MarkdownReportGenerator())

    return manager
