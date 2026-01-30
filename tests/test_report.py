"""
Tests for Report Generation Module
레포트 생성 모듈 테스트
"""

import pytest
from datetime import datetime
from pathlib import Path
import json

import polars as pl

from data_graph_studio.core.report import (
    ReportFormat,
    ReportTheme,
    PageSize,
    PageOrientation,
    ReportMetadata,
    ReportOptions,
    ReportData,
    ReportTemplate,
    ReportManager,
    DatasetSummary,
    StatisticalSummary,
    ComparisonResult,
    DifferenceAnalysis,
    ChartData,
    TableData,
    collect_statistics_from_dataframe,
    create_comparison_table,
)

from data_graph_studio.report.html_generator import HTMLReportGenerator


class TestReportMetadata:
    """ReportMetadata 테스트"""

    def test_create_metadata(self):
        """메타데이터 생성 테스트"""
        meta = ReportMetadata(
            title="Test Report",
            subtitle="Test Subtitle",
            author="Test Author"
        )

        assert meta.title == "Test Report"
        assert meta.subtitle == "Test Subtitle"
        assert meta.author == "Test Author"
        assert meta.version == "1.0"
        assert isinstance(meta.created_at, datetime)

    def test_metadata_to_dict(self):
        """메타데이터 딕셔너리 변환 테스트"""
        meta = ReportMetadata(title="Test")
        d = meta.to_dict()

        assert d["title"] == "Test"
        assert "created_at" in d
        assert "version" in d


class TestDatasetSummary:
    """DatasetSummary 테스트"""

    @pytest.fixture
    def sample_df(self):
        """샘플 DataFrame"""
        return pl.DataFrame({
            "name": ["Alice", "Bob", "Charlie", None],
            "age": [25, 30, 35, 40],
            "salary": [50000.0, 60000.0, 70000.0, 80000.0],
            "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
        })

    def test_from_dataframe(self, sample_df):
        """DataFrame에서 생성 테스트"""
        summary = DatasetSummary.from_dataframe(
            sample_df,
            id="test_id",
            name="Test Dataset"
        )

        assert summary.id == "test_id"
        assert summary.name == "Test Dataset"
        assert summary.row_count == 4
        assert summary.column_count == 4
        assert "name" in summary.columns
        assert summary.missing_values.get("name") == 1

    def test_to_dict(self):
        """딕셔너리 변환 테스트"""
        summary = DatasetSummary(
            id="test",
            name="Test",
            row_count=100,
            column_count=10
        )

        d = summary.to_dict()
        assert d["id"] == "test"
        assert d["row_count"] == 100


class TestStatisticalSummary:
    """StatisticalSummary 테스트"""

    def test_from_series(self):
        """Series에서 생성 테스트"""
        series = pl.Series("values", [1, 2, 3, 4, 5, None])

        stat = StatisticalSummary.from_series(series, "values")

        assert stat.column == "values"
        assert stat.count == 6
        assert stat.null_count == 1
        assert stat.mean == pytest.approx(3.0, rel=0.01)
        assert stat.min == 1.0
        assert stat.max == 5.0

    def test_non_numeric_series(self):
        """비수치 Series 테스트"""
        series = pl.Series("names", ["a", "b", "c"])

        stat = StatisticalSummary.from_series(series, "names")

        assert stat.count == 3
        assert stat.mean is None
        assert stat.std is None


class TestComparisonResult:
    """ComparisonResult 테스트"""

    def test_significance_levels(self):
        """유의수준 기호 테스트"""
        comp_high = ComparisonResult(
            dataset_a_id="a", dataset_a_name="A",
            dataset_b_id="b", dataset_b_name="B",
            column="value",
            test_type="t-test",
            test_statistic=3.5,
            p_value=0.0005
        )
        assert comp_high.get_significance_symbol() == "***"

        comp_medium = ComparisonResult(
            dataset_a_id="a", dataset_a_name="A",
            dataset_b_id="b", dataset_b_name="B",
            column="value",
            test_type="t-test",
            test_statistic=2.5,
            p_value=0.005
        )
        assert comp_medium.get_significance_symbol() == "**"

        comp_low = ComparisonResult(
            dataset_a_id="a", dataset_a_name="A",
            dataset_b_id="b", dataset_b_name="B",
            column="value",
            test_type="t-test",
            test_statistic=2.0,
            p_value=0.03
        )
        assert comp_low.get_significance_symbol() == "*"

        comp_none = ComparisonResult(
            dataset_a_id="a", dataset_a_name="A",
            dataset_b_id="b", dataset_b_name="B",
            column="value",
            test_type="t-test",
            test_statistic=1.0,
            p_value=0.1
        )
        assert comp_none.get_significance_symbol() == ""


class TestTableData:
    """TableData 테스트"""

    def test_from_dataframe(self):
        """DataFrame에서 생성 테스트"""
        df = pl.DataFrame({
            "col1": [1, 2, 3],
            "col2": ["a", "b", "c"]
        })

        table = TableData.from_dataframe(df, "test", "Test Table")

        assert table.id == "test"
        assert table.title == "Test Table"
        assert len(table.columns) == 2
        assert len(table.rows) == 3
        assert table.column_formats["col1"] == "integer"
        assert table.column_formats["col2"] == "text"

    def test_max_rows_limit(self):
        """최대 행 수 제한 테스트"""
        df = pl.DataFrame({"value": list(range(200))})

        table = TableData.from_dataframe(df, "test", "Test", max_rows=50)

        assert table.total_rows == 200
        assert table.shown_rows == 50
        assert len(table.rows) == 50


class TestReportData:
    """ReportData 테스트"""

    @pytest.fixture
    def sample_report_data(self):
        """샘플 레포트 데이터"""
        return ReportData(
            metadata=ReportMetadata(title="Test Report"),
            datasets=[
                DatasetSummary(id="d1", name="Dataset 1", row_count=100, column_count=10),
                DatasetSummary(id="d2", name="Dataset 2", row_count=200, column_count=10),
            ]
        )

    def test_total_rows(self, sample_report_data):
        """전체 행 수 테스트"""
        assert sample_report_data.get_total_rows() == 300

    def test_is_multi_dataset(self, sample_report_data):
        """멀티 데이터셋 여부 테스트"""
        assert sample_report_data.is_multi_dataset() is True

        single = ReportData(
            metadata=ReportMetadata(title="Test"),
            datasets=[DatasetSummary(id="d1", name="Dataset 1", row_count=100, column_count=10)]
        )
        assert single.is_multi_dataset() is False

    def test_to_json(self, sample_report_data):
        """JSON 변환 테스트"""
        json_str = sample_report_data.to_json()
        data = json.loads(json_str)

        assert data["metadata"]["title"] == "Test Report"
        assert len(data["datasets"]) == 2


class TestReportOptions:
    """ReportOptions 테스트"""

    def test_default_values(self):
        """기본값 테스트"""
        options = ReportOptions()

        assert options.format == ReportFormat.HTML
        assert options.theme == ReportTheme.LIGHT
        assert options.page_size == PageSize.A4
        assert options.include_executive_summary is True
        assert options.chart_dpi == 150
        assert options.table_max_rows == 100

    def test_to_dict(self):
        """딕셔너리 변환 테스트"""
        options = ReportOptions(
            format=ReportFormat.PDF,
            language="ko"
        )

        d = options.to_dict()
        assert d["format"] == "pdf"
        assert d["language"] == "ko"


class TestReportTemplate:
    """ReportTemplate 테스트"""

    def test_create_template(self):
        """템플릿 생성 테스트"""
        template = ReportTemplate(
            id="custom",
            name="Custom Template",
            primary_color="#ff0000"
        )

        assert template.id == "custom"
        assert template.primary_color == "#ff0000"

    def test_to_dict(self):
        """딕셔너리 변환 테스트"""
        template = ReportTemplate(id="test", name="Test")
        d = template.to_dict()

        assert d["id"] == "test"
        assert d["name"] == "Test"


class TestReportManager:
    """ReportManager 테스트"""

    def test_default_templates(self):
        """기본 템플릿 테스트"""
        manager = ReportManager()

        assert "default" in manager.templates
        assert "corporate" in manager.templates
        assert "modern" in manager.templates

    def test_add_template(self):
        """템플릿 추가 테스트"""
        manager = ReportManager()
        custom = ReportTemplate(id="custom", name="Custom")

        manager.add_template(custom)

        assert manager.get_template("custom") is not None
        assert manager.get_template("custom").name == "Custom"

    def test_list_templates(self):
        """템플릿 목록 테스트"""
        manager = ReportManager()
        templates = manager.list_templates()

        assert len(templates) >= 3  # default, corporate, modern


class TestHTMLReportGenerator:
    """HTMLReportGenerator 테스트"""

    @pytest.fixture
    def sample_report_data(self):
        """샘플 레포트 데이터"""
        return ReportData(
            metadata=ReportMetadata(
                title="Test Report",
                subtitle="Test Subtitle",
                author="Test Author"
            ),
            datasets=[
                DatasetSummary(
                    id="d1",
                    name="Dataset 1",
                    row_count=1000,
                    column_count=10,
                    columns=["col1", "col2", "col3"],
                    column_types={"col1": "Int64", "col2": "Float64", "col3": "String"},
                    color="#1f77b4"
                )
            ],
            statistics={
                "d1": [
                    StatisticalSummary(
                        column="col1",
                        dataset_id="d1",
                        dataset_name="Dataset 1",
                        count=1000,
                        mean=50.0,
                        median=48.0,
                        std=15.0,
                        min=0.0,
                        max=100.0
                    )
                ]
            },
            key_findings=["Finding 1", "Finding 2"],
            recommendations=["Recommendation 1"]
        )

    def test_generate_html(self, sample_report_data):
        """HTML 생성 테스트"""
        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(sample_report_data, options)

        assert isinstance(html_bytes, bytes)
        html_content = html_bytes.decode('utf-8')

        # 기본 구조 확인
        assert "<!DOCTYPE html>" in html_content
        assert "Test Report" in html_content
        assert "Test Subtitle" in html_content
        assert "Test Author" in html_content

    def test_generate_html_korean(self, sample_report_data):
        """한국어 HTML 생성 테스트"""
        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML, language="ko")

        html_bytes = generator.generate(sample_report_data, options)
        html_content = html_bytes.decode('utf-8')

        assert "목차" in html_content

    def test_generate_html_dark_theme(self, sample_report_data):
        """다크 테마 HTML 생성 테스트"""
        generator = HTMLReportGenerator()
        options = ReportOptions(
            format=ReportFormat.HTML,
            theme=ReportTheme.DARK
        )

        html_bytes = generator.generate(sample_report_data, options)
        html_content = html_bytes.decode('utf-8')

        assert "theme-dark" in html_content

    def test_generate_with_charts(self, sample_report_data):
        """차트 포함 HTML 생성 테스트"""
        # 차트 추가
        sample_report_data.charts.append(
            ChartData(
                id="chart1",
                chart_type="line",
                title="Test Chart",
                image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                image_format="png"
            )
        )

        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(sample_report_data, options)
        html_content = html_bytes.decode('utf-8')

        assert "Test Chart" in html_content
        assert "data:image/png;base64" in html_content

    def test_generate_with_comparison(self, sample_report_data):
        """비교 분석 포함 HTML 생성 테스트"""
        # 두 번째 데이터셋 추가
        sample_report_data.datasets.append(
            DatasetSummary(
                id="d2",
                name="Dataset 2",
                row_count=1500,
                column_count=10,
                columns=["col1", "col2", "col3"],
                color="#ff7f0e"
            )
        )

        # 비교 결과 추가
        sample_report_data.comparisons.append(
            ComparisonResult(
                dataset_a_id="d1",
                dataset_a_name="Dataset 1",
                dataset_b_id="d2",
                dataset_b_name="Dataset 2",
                column="col1",
                test_type="t-test",
                test_statistic=2.5,
                p_value=0.015,
                effect_size=0.45,
                effect_size_interpretation="Small-Medium",
                significant=True
            )
        )

        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(sample_report_data, options)
        html_content = html_bytes.decode('utf-8')

        assert "Dataset 1 vs Dataset 2" in html_content
        assert "t-test" in html_content
        assert "Significant" in html_content

    def test_generate_with_tables(self, sample_report_data):
        """테이블 포함 HTML 생성 테스트"""
        sample_report_data.tables.append(
            TableData(
                id="table1",
                title="Test Table",
                table_type="raw",
                columns=["A", "B", "C"],
                rows=[[1, 2, 3], [4, 5, 6]],
                total_rows=2,
                shown_rows=2
            )
        )

        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(sample_report_data, options)
        html_content = html_bytes.decode('utf-8')

        assert "Test Table" in html_content

    def test_save_to_file(self, sample_report_data, tmp_path):
        """파일 저장 테스트"""
        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)
        output_path = tmp_path / "test_report.html"

        result_path = generator.save(sample_report_data, options, output_path)

        assert result_path.exists()
        assert result_path.suffix == ".html"

        # 파일 내용 확인
        content = result_path.read_text(encoding='utf-8')
        assert "Test Report" in content


class TestUtilityFunctions:
    """유틸리티 함수 테스트"""

    def test_collect_statistics_from_dataframe(self):
        """DataFrame 통계 수집 테스트"""
        df = pl.DataFrame({
            "numeric_col": [1, 2, 3, 4, 5],
            "string_col": ["a", "b", "c", "d", "e"]
        })

        stats = collect_statistics_from_dataframe(df, "test_id", "Test")

        # 수치형 컬럼만 포함
        assert len(stats) == 1
        assert stats[0].column == "numeric_col"
        assert stats[0].dataset_id == "test_id"
        assert stats[0].mean == pytest.approx(3.0)

    def test_create_comparison_table(self):
        """비교 테이블 생성 테스트"""
        statistics = {
            "d1": [
                StatisticalSummary(column="col1", mean=10.0),
                StatisticalSummary(column="col2", mean=20.0),
            ],
            "d2": [
                StatisticalSummary(column="col1", mean=15.0),
                StatisticalSummary(column="col2", mean=25.0),
            ]
        }

        table = create_comparison_table(statistics, "mean")

        assert table.table_type == "comparison"
        assert len(table.rows) == 2  # col1, col2


class TestReportGeneratorFormatting:
    """ReportGenerator 포맷팅 테스트"""

    def test_format_number(self):
        """숫자 포맷팅 테스트"""
        from data_graph_studio.report.html_generator import HTMLReportGenerator

        gen = HTMLReportGenerator()

        assert gen.format_number(1234567) == "1.23M"
        assert gen.format_number(12345) == "12.35K"
        assert gen.format_number(123.456) == "123.46"
        assert gen.format_number(None) == "-"

    def test_format_percentage(self):
        """퍼센트 포맷팅 테스트"""
        from data_graph_studio.report.html_generator import HTMLReportGenerator

        gen = HTMLReportGenerator()

        assert gen.format_percentage(50.123) == "50.1%"
        assert gen.format_percentage(None) == "-"

    def test_format_bytes(self):
        """바이트 포맷팅 테스트"""
        from data_graph_studio.report.html_generator import HTMLReportGenerator

        gen = HTMLReportGenerator()

        assert "B" in gen.format_bytes(500)
        assert "KB" in gen.format_bytes(5000)
        assert "MB" in gen.format_bytes(5000000)
        assert "GB" in gen.format_bytes(5000000000)
