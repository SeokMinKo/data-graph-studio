"""
Report Generation Core Module
레포트 생성 핵심 모듈

Supports: HTML, PDF, DOCX, PPTX, JSON, Markdown
"""

from typing import Optional, List, Dict, Any, Union
from pathlib import Path
from abc import ABC, abstractmethod
import json

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
