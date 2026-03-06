"""
Tests for Report Generation Module
레포트 생성 모듈 테스트
"""

import pytest
from datetime import datetime
import json

import polars as pl

from data_graph_studio.core.report import (
    ReportFormat,
    ReportTheme,
    PageSize,
    ReportMetadata,
    ReportOptions,
    ReportData,
    ReportTemplate,
    ReportManager,
    DatasetSummary,
    StatisticalSummary,
    ComparisonResult,
    ChartData,
    TableData,
    ChartStatistics,
    ChartStatisticsConfig,
    StatisticType,
    get_default_statistics_for_chart,
    collect_statistics_from_dataframe,
    create_comparison_table,
)

from data_graph_studio.report.html_generator import HTMLReportGenerator


class TestReportMetadata:
    """ReportMetadata 테스트"""

    def test_create_metadata(self):
        """메타데이터 생성 테스트"""
        meta = ReportMetadata(
            title="Test Report", subtitle="Test Subtitle", author="Test Author"
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
        return pl.DataFrame(
            {
                "name": ["Alice", "Bob", "Charlie", None],
                "age": [25, 30, 35, 40],
                "salary": [50000.0, 60000.0, 70000.0, 80000.0],
                "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
            }
        )

    def test_from_dataframe(self, sample_df):
        """DataFrame에서 생성 테스트"""
        summary = DatasetSummary.from_dataframe(
            sample_df, id="test_id", name="Test Dataset"
        )

        assert summary.id == "test_id"
        assert summary.name == "Test Dataset"
        assert summary.row_count == 4
        assert summary.column_count == 4
        assert "name" in summary.columns
        assert summary.missing_values.get("name") == 1

    def test_to_dict(self):
        """딕셔너리 변환 테스트"""
        summary = DatasetSummary(id="test", name="Test", row_count=100, column_count=10)

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
            dataset_a_id="a",
            dataset_a_name="A",
            dataset_b_id="b",
            dataset_b_name="B",
            column="value",
            test_type="t-test",
            test_statistic=3.5,
            p_value=0.0005,
        )
        assert comp_high.get_significance_symbol() == "***"

        comp_medium = ComparisonResult(
            dataset_a_id="a",
            dataset_a_name="A",
            dataset_b_id="b",
            dataset_b_name="B",
            column="value",
            test_type="t-test",
            test_statistic=2.5,
            p_value=0.005,
        )
        assert comp_medium.get_significance_symbol() == "**"

        comp_low = ComparisonResult(
            dataset_a_id="a",
            dataset_a_name="A",
            dataset_b_id="b",
            dataset_b_name="B",
            column="value",
            test_type="t-test",
            test_statistic=2.0,
            p_value=0.03,
        )
        assert comp_low.get_significance_symbol() == "*"

        comp_none = ComparisonResult(
            dataset_a_id="a",
            dataset_a_name="A",
            dataset_b_id="b",
            dataset_b_name="B",
            column="value",
            test_type="t-test",
            test_statistic=1.0,
            p_value=0.1,
        )
        assert comp_none.get_significance_symbol() == ""


class TestTableData:
    """TableData 테스트"""

    def test_from_dataframe(self):
        """DataFrame에서 생성 테스트"""
        df = pl.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

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
                DatasetSummary(
                    id="d1", name="Dataset 1", row_count=100, column_count=10
                ),
                DatasetSummary(
                    id="d2", name="Dataset 2", row_count=200, column_count=10
                ),
            ],
        )

    def test_total_rows(self, sample_report_data):
        """전체 행 수 테스트"""
        assert sample_report_data.get_total_rows() == 300

    def test_is_multi_dataset(self, sample_report_data):
        """멀티 데이터셋 여부 테스트"""
        assert sample_report_data.is_multi_dataset() is True

        single = ReportData(
            metadata=ReportMetadata(title="Test"),
            datasets=[
                DatasetSummary(
                    id="d1", name="Dataset 1", row_count=100, column_count=10
                )
            ],
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
        options = ReportOptions(format=ReportFormat.PDF, language="ko")

        d = options.to_dict()
        assert d["format"] == "pdf"
        assert d["language"] == "ko"


class TestReportTemplate:
    """ReportTemplate 테스트"""

    def test_create_template(self):
        """템플릿 생성 테스트"""
        template = ReportTemplate(
            id="custom", name="Custom Template", primary_color="#ff0000"
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
                title="Test Report", subtitle="Test Subtitle", author="Test Author"
            ),
            datasets=[
                DatasetSummary(
                    id="d1",
                    name="Dataset 1",
                    row_count=1000,
                    column_count=10,
                    columns=["col1", "col2", "col3"],
                    column_types={"col1": "Int64", "col2": "Float64", "col3": "String"},
                    color="#1f77b4",
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
                        max=100.0,
                    )
                ]
            },
            key_findings=["Finding 1", "Finding 2"],
            recommendations=["Recommendation 1"],
        )

    def test_generate_html(self, sample_report_data):
        """HTML 생성 테스트"""
        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(sample_report_data, options)

        assert isinstance(html_bytes, bytes)
        html_content = html_bytes.decode("utf-8")

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
        html_content = html_bytes.decode("utf-8")

        assert "목차" in html_content

    def test_generate_html_dark_theme(self, sample_report_data):
        """다크 테마 HTML 생성 테스트"""
        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML, theme=ReportTheme.DARK)

        html_bytes = generator.generate(sample_report_data, options)
        html_content = html_bytes.decode("utf-8")

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
                image_format="png",
            )
        )

        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(sample_report_data, options)
        html_content = html_bytes.decode("utf-8")

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
                color="#ff7f0e",
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
                significant=True,
            )
        )

        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(sample_report_data, options)
        html_content = html_bytes.decode("utf-8")

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
                shown_rows=2,
            )
        )

        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(sample_report_data, options)
        html_content = html_bytes.decode("utf-8")

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
        content = result_path.read_text(encoding="utf-8")
        assert "Test Report" in content


class TestUtilityFunctions:
    """유틸리티 함수 테스트"""

    def test_collect_statistics_from_dataframe(self):
        """DataFrame 통계 수집 테스트"""
        df = pl.DataFrame(
            {"numeric_col": [1, 2, 3, 4, 5], "string_col": ["a", "b", "c", "d", "e"]}
        )

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
            ],
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


class TestChartStatistics:
    """ChartStatistics 테스트"""

    def test_create_chart_statistics(self):
        """차트 통계 생성 테스트"""
        stats = ChartStatistics(
            chart_type="bar",
            statistics={
                "total": 1000,
                "mean": 50.0,
                "max": 100,
                "min": 10,
                "count": 20,
            },
        )

        assert stats.chart_type == "bar"
        assert stats.get("total") == 1000
        assert stats.get("mean") == 50.0
        assert stats.get("nonexistent") is None
        assert stats.get("nonexistent", "default") == "default"

    def test_chart_statistics_to_dict(self):
        """차트 통계 딕셔너리 변환 테스트"""
        stats = ChartStatistics(
            chart_type="line", statistics={"start_value": 10, "end_value": 100}
        )

        d = stats.to_dict()
        assert d["chart_type"] == "line"
        assert d["statistics"]["start_value"] == 10

    def test_chart_statistics_set(self):
        """차트 통계 값 설정 테스트"""
        stats = ChartStatistics(chart_type="pie")
        stats.set("total", 500)
        stats.set("count", 10)

        assert stats.get("total") == 500
        assert stats.get("count") == 10


class TestChartStatisticsConfig:
    """ChartStatisticsConfig 테스트"""

    def test_create_config(self):
        """설정 생성 테스트"""
        config = ChartStatisticsConfig(
            enabled_statistics=[
                StatisticType.MEAN,
                StatisticType.MAX,
                StatisticType.MIN,
            ],
            show_in_report=True,
            decimal_places=3,
        )

        assert len(config.enabled_statistics) == 3
        assert StatisticType.MEAN in config.enabled_statistics
        assert config.show_in_report is True
        assert config.decimal_places == 3

    def test_config_to_dict(self):
        """설정 딕셔너리 변환 테스트"""
        config = ChartStatisticsConfig(
            enabled_statistics=[StatisticType.COUNT, StatisticType.TOTAL]
        )

        d = config.to_dict()
        assert "count" in d["enabled_statistics"]
        assert "total" in d["enabled_statistics"]

    def test_config_from_dict(self):
        """딕셔너리에서 설정 생성 테스트"""
        data = {
            "enabled_statistics": ["mean", "median", "std"],
            "show_in_report": False,
            "decimal_places": 4,
        }

        config = ChartStatisticsConfig.from_dict(data)

        assert len(config.enabled_statistics) == 3
        assert StatisticType.MEAN in config.enabled_statistics
        assert config.show_in_report is False
        assert config.decimal_places == 4


class TestDefaultChartStatistics:
    """DEFAULT_CHART_STATISTICS 테스트"""

    def test_bar_chart_defaults(self):
        """Bar chart 기본 통계 테스트"""
        stats = get_default_statistics_for_chart("bar")

        assert StatisticType.TOTAL in stats
        assert StatisticType.MEAN in stats
        assert StatisticType.MAX in stats
        assert StatisticType.MIN in stats
        assert StatisticType.COUNT in stats

    def test_pie_chart_defaults(self):
        """Pie chart 기본 통계 테스트"""
        stats = get_default_statistics_for_chart("pie")

        assert StatisticType.PERCENTAGE in stats
        assert StatisticType.TOTAL in stats
        assert StatisticType.COUNT in stats

    def test_line_chart_defaults(self):
        """Line chart 기본 통계 테스트"""
        stats = get_default_statistics_for_chart("line")

        assert StatisticType.START_VALUE in stats
        assert StatisticType.END_VALUE in stats
        assert StatisticType.CHANGE_PERCENT in stats
        assert StatisticType.TREND_DIRECTION in stats

    def test_scatter_chart_defaults(self):
        """Scatter plot 기본 통계 테스트"""
        stats = get_default_statistics_for_chart("scatter")

        assert StatisticType.CORRELATION in stats
        assert StatisticType.R_SQUARED in stats
        assert StatisticType.X_RANGE in stats
        assert StatisticType.Y_RANGE in stats

    def test_heatmap_defaults(self):
        """Heatmap 기본 통계 테스트"""
        stats = get_default_statistics_for_chart("heatmap")

        assert StatisticType.MAX in stats
        assert StatisticType.MIN in stats
        assert StatisticType.MEAN in stats
        assert StatisticType.MAX_CELL_LOCATION in stats

    def test_box_chart_defaults(self):
        """Box plot 기본 통계 테스트"""
        stats = get_default_statistics_for_chart("box")

        assert StatisticType.MEDIAN in stats
        assert StatisticType.Q1 in stats
        assert StatisticType.Q3 in stats
        assert StatisticType.IQR in stats
        assert StatisticType.OUTLIER_COUNT in stats

    def test_histogram_defaults(self):
        """Histogram 기본 통계 테스트"""
        stats = get_default_statistics_for_chart("histogram")

        assert StatisticType.MEAN in stats
        assert StatisticType.MEDIAN in stats
        assert StatisticType.STD in stats
        assert StatisticType.SKEWNESS in stats
        assert StatisticType.MODE in stats
        assert StatisticType.BIN_COUNT in stats

    def test_unknown_chart_type(self):
        """알 수 없는 차트 타입 기본 통계 테스트"""
        stats = get_default_statistics_for_chart("unknown_type")

        # 기본값 반환
        assert StatisticType.COUNT in stats
        assert StatisticType.MEAN in stats


class TestChartDataWithStatistics:
    """ChartData 통계 기능 테스트"""

    def test_chart_data_with_statistics(self):
        """통계 포함 ChartData 테스트"""
        stats = ChartStatistics(
            chart_type="bar",
            statistics={
                "total": 1000,
                "mean": 50.0,
                "max": 100,
                "min": 10,
                "count": 20,
            },
        )

        chart = ChartData(
            id="chart1", chart_type="bar", title="Test Chart", statistics=stats
        )

        assert chart.statistics is not None
        assert chart.statistics.get("total") == 1000

    def test_chart_data_set_statistics(self):
        """ChartData 통계 설정 테스트"""
        chart = ChartData(id="chart1", chart_type="line", title="Test Chart")

        stats = ChartStatistics(
            chart_type="line", statistics={"start_value": 10, "end_value": 100}
        )

        chart.set_statistics(stats)

        assert chart.statistics is not None
        assert chart.statistics.get("start_value") == 10

    def test_get_statistics_for_display_default(self):
        """기본 통계 표시 테스트"""
        stats = ChartStatistics(
            chart_type="bar",
            statistics={
                "total": 1000,
                "mean": 50.0,
                "max": 100,
                "min": 10,
                "count": 20,
                "extra": "should_not_appear",  # not in default
            },
        )

        chart = ChartData(
            id="chart1", chart_type="bar", title="Test Chart", statistics=stats
        )

        display_stats = chart.get_statistics_for_display()

        assert "total" in display_stats
        assert "mean" in display_stats
        assert display_stats["total"] == 1000

    def test_get_statistics_for_display_custom_config(self):
        """커스텀 설정 통계 표시 테스트"""
        stats = ChartStatistics(
            chart_type="bar",
            statistics={
                "total": 1000,
                "mean": 50.0,
                "max": 100,
                "min": 10,
                "count": 20,
            },
        )

        config = ChartStatisticsConfig(
            enabled_statistics=[StatisticType.TOTAL, StatisticType.COUNT]
        )

        chart = ChartData(
            id="chart1",
            chart_type="bar",
            title="Test Chart",
            statistics=stats,
            statistics_config=config,
        )

        display_stats = chart.get_statistics_for_display()

        assert "total" in display_stats
        assert "count" in display_stats
        assert "mean" not in display_stats  # not in config


class TestHTMLGeneratorWithChartStatistics:
    """HTML Generator 차트 통계 테스트"""

    @pytest.fixture
    def sample_report_with_chart_stats(self):
        """통계 포함 차트가 있는 레포트 데이터"""
        stats = ChartStatistics(
            chart_type="bar",
            statistics={
                "total": 5000,
                "mean": 250.0,
                "max": 500,
                "min": 100,
                "count": 20,
            },
        )

        return ReportData(
            metadata=ReportMetadata(title="Chart Stats Test"),
            datasets=[
                DatasetSummary(id="d1", name="Dataset 1", row_count=100, column_count=5)
            ],
            charts=[
                ChartData(
                    id="chart1",
                    chart_type="bar",
                    title="Bar Chart with Statistics",
                    image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                    statistics=stats,
                )
            ],
        )

    def test_html_includes_chart_statistics(self, sample_report_with_chart_stats):
        """HTML에 차트 통계가 포함되는지 테스트"""
        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML, include_chart_statistics=True)

        html_bytes = generator.generate(sample_report_with_chart_stats, options)
        html_content = html_bytes.decode("utf-8")

        assert "chart-statistics" in html_content
        assert "stats-table" in html_content

    def test_html_excludes_chart_statistics_when_disabled(
        self, sample_report_with_chart_stats
    ):
        """차트 통계 비활성화 테스트"""
        generator = HTMLReportGenerator()
        options = ReportOptions(
            format=ReportFormat.HTML, include_chart_statistics=False
        )

        html_bytes = generator.generate(sample_report_with_chart_stats, options)
        html_content = html_bytes.decode("utf-8")

        # CSS에는 chart-statistics가 있지만, 실제 div.chart-statistics는 없어야 함
        assert '<div class="chart-statistics">' not in html_content

    def test_html_excludes_key_findings(self):
        """key_findings가 제외되는지 테스트"""
        report_data = ReportData(
            metadata=ReportMetadata(title="Test"),
            datasets=[DatasetSummary(id="d1", name="D1", row_count=10, column_count=5)],
            key_findings=["Finding 1", "Finding 2"],  # Should be excluded
            recommendations=["Recommendation 1"],  # Should be excluded
        )

        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(report_data, options)
        html_content = html_bytes.decode("utf-8")

        # key_findings와 recommendations가 렌더링되지 않아야 함
        assert "Finding 1" not in html_content
        assert "Recommendation 1" not in html_content
        assert "핵심 발견 사항" not in html_content
        assert "권장 사항" not in html_content

    def test_html_excludes_chart_description(self):
        """차트 description이 제외되는지 테스트"""
        report_data = ReportData(
            metadata=ReportMetadata(title="Test"),
            datasets=[DatasetSummary(id="d1", name="D1", row_count=10, column_count=5)],
            charts=[
                ChartData(
                    id="chart1",
                    chart_type="bar",
                    title="Test Chart",
                    description="This description should not appear",  # Should be excluded
                    image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                )
            ],
        )

        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)

        html_bytes = generator.generate(report_data, options)
        html_content = html_bytes.decode("utf-8")

        # description 텍스트가 HTML에 나타나지 않아야 함
        assert "This description should not appear" not in html_content
        # CSS에는 chart-description이 있지만, 실제 p.chart-description은 없어야 함
        assert '<p class="chart-description">' not in html_content


class TestReportOptionsChartStatistics:
    """ReportOptions 차트 통계 옵션 테스트"""

    def test_default_include_chart_statistics(self):
        """기본 include_chart_statistics 값 테스트"""
        options = ReportOptions()
        assert options.include_chart_statistics is True

    def test_include_chart_statistics_in_to_dict(self):
        """to_dict에 include_chart_statistics 포함 테스트"""
        options = ReportOptions(include_chart_statistics=False)
        d = options.to_dict()
        assert d["include_chart_statistics"] is False
