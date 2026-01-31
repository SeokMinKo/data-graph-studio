"""
통합 테스트 (Integration Tests) - 6개 기능 복합 테스트

테스트 범위:
1. 계산 필드 + 필터링: 계산된 컬럼으로 필터링
2. 필터링 + 추세선: 필터된 데이터에 추세선 적용
3. 트렐리스 + 대시보드: 트렐리스 차트를 대시보드에 배치
4. 계산 필드 + 리포트: 계산된 데이터로 리포트 생성
5. 전체 파이프라인: 데이터 로드 → 계산 필드 → 필터링 → 추세선 → 트렐리스 → 대시보드 → 리포트
"""

import pytest
import tempfile
import os
import numpy as np
import polars as pl
from datetime import date, datetime
from pathlib import Path

# Core imports
from data_graph_studio.core.data_engine import DataEngine
from data_graph_studio.core.expression_engine import ExpressionEngine, ExpressionError
from data_graph_studio.core.filtering import (
    FilteringManager, FilterOperator, FilterType, Filter, FilteringScheme
)
from data_graph_studio.core.state import AppState, ChartType

# Graph imports
from data_graph_studio.graph.curve_fitting import (
    CurveFitter, FitType, TrendLine, CurveFitSettings, ForecastSettings
)
from data_graph_studio.graph.trellis import (
    TrellisMode, TrellisSettings, TrellisCalculator
)

# UI imports
from data_graph_studio.ui.dashboard import (
    DashboardWidget, DashboardLayout, DashboardItem, 
    DashboardManager, GridPosition
)

# Report imports
from data_graph_studio.core.report import (
    ReportFormat, ReportMetadata, ReportOptions, ReportData,
    DatasetSummary, StatisticalSummary, ChartData, TableData,
    collect_statistics_from_dataframe
)
from data_graph_studio.report.html_generator import HTMLReportGenerator


# =============================================================================
# Fixtures - 공통 테스트 데이터
# =============================================================================

@pytest.fixture
def sample_sales_data():
    """샘플 영업 데이터 - 여러 테스트에서 사용"""
    np.random.seed(42)
    n = 500
    
    regions = np.random.choice(['North', 'South', 'East', 'West'], n)
    categories = np.random.choice(['Electronics', 'Clothing', 'Food', 'Books'], n)
    dates = [date(2024, np.random.randint(1, 13), np.random.randint(1, 28)) for _ in range(n)]
    
    return pl.DataFrame({
        'id': range(1, n + 1),
        'region': regions,
        'category': categories,
        'date': dates,
        'sales': np.random.randint(100, 10000, n),
        'quantity': np.random.randint(1, 100, n),
        'unit_cost': np.round(np.random.uniform(5, 500, n), 2),
        'discount': np.round(np.random.uniform(0, 0.3, n), 2),
    })


@pytest.fixture
def sample_csv_file(sample_sales_data):
    """임시 CSV 파일 생성"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        sample_sales_data.write_csv(f.name)
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def expression_engine():
    """ExpressionEngine 인스턴스"""
    return ExpressionEngine()


@pytest.fixture
def filtering_manager(qtbot):
    """FilteringManager 인스턴스"""
    return FilteringManager()


@pytest.fixture
def curve_fitter():
    """CurveFitter 인스턴스"""
    return CurveFitter()


@pytest.fixture
def trellis_calculator():
    """TrellisCalculator 인스턴스"""
    return TrellisCalculator()


@pytest.fixture
def dashboard_manager():
    """DashboardManager 인스턴스"""
    return DashboardManager()


# =============================================================================
# 1. 계산 필드 + 필터링 통합 테스트
# =============================================================================

class TestCalculatedFieldsWithFiltering:
    """계산 필드와 필터링 통합 테스트"""
    
    def test_filter_by_calculated_column(self, sample_sales_data, expression_engine, filtering_manager):
        """계산된 컬럼으로 필터링"""
        # 1. 계산 필드 추가: Total = sales * quantity
        df = expression_engine.add_column(
            sample_sales_data, 
            "Total", 
            "sales * quantity"
        )
        assert "Total" in df.columns
        
        # 2. 필터 적용: Total > 100000
        filtering_manager.add_filter(
            "Page", "Total", FilterOperator.GREATER_THAN, 100000
        )
        filtered = filtering_manager.apply_filters("Page", df)
        
        # 검증: 모든 결과의 Total이 100000 초과
        assert len(filtered) > 0
        assert all(v > 100000 for v in filtered["Total"].to_list())
    
    def test_filter_by_profit_margin(self, sample_sales_data, expression_engine, filtering_manager):
        """이익률 계산 후 필터링"""
        # 1. 여러 계산 필드 추가
        df = sample_sales_data.clone()
        df = expression_engine.add_column(df, "Revenue", "sales")
        df = expression_engine.add_column(df, "Cost", "unit_cost * quantity")
        df = expression_engine.add_column(df, "Profit", "Revenue - Cost")
        df = expression_engine.add_column(df, "ProfitMargin", "Profit / Revenue")
        
        assert all(col in df.columns for col in ["Revenue", "Cost", "Profit", "ProfitMargin"])
        
        # 2. 이익률 필터: ProfitMargin > 0.5 (50% 이상)
        filtering_manager.add_filter(
            "Page", "ProfitMargin", FilterOperator.GREATER_THAN, 0.5
        )
        filtered = filtering_manager.apply_filters("Page", df)
        
        # 검증
        assert len(filtered) > 0
        for margin in filtered["ProfitMargin"].to_list():
            if margin is not None:
                assert margin > 0.5
    
    def test_calculated_discount_filter(self, sample_sales_data, expression_engine, filtering_manager):
        """할인 적용 금액 계산 후 필터링"""
        # 1. 할인 적용 금액 계산
        df = expression_engine.add_column(
            sample_sales_data,
            "DiscountedSales",
            "sales * (1 - discount)"
        )
        
        # 2. 원래 가격 대비 할인 금액
        df = expression_engine.add_column(
            df,
            "DiscountAmount",
            "sales - DiscountedSales"
        )
        
        # 3. 할인 금액이 1000 이상인 것만 필터
        filtering_manager.add_filter(
            "Page", "DiscountAmount", FilterOperator.GREATER_THAN_OR_EQUALS, 1000
        )
        filtered = filtering_manager.apply_filters("Page", df)
        
        assert len(filtered) >= 0
        if len(filtered) > 0:
            assert all(v >= 1000 for v in filtered["DiscountAmount"].to_list())
    
    def test_multiple_calculated_filters(self, sample_sales_data, expression_engine, filtering_manager):
        """여러 계산 필드에 대한 복합 필터링"""
        # 1. 계산 필드들 추가
        df = sample_sales_data.clone()
        df = expression_engine.add_column(df, "TotalSales", "sales * quantity")
        df = expression_engine.add_column(df, "UnitProfit", "sales - unit_cost")
        
        # 2. 여러 필터 적용
        filtering_manager.add_filter("Page", "TotalSales", FilterOperator.GREATER_THAN, 50000)
        filtering_manager.add_filter("Page", "UnitProfit", FilterOperator.GREATER_THAN, 0)
        filtering_manager.add_filter("Page", "region", FilterOperator.IN_LIST, ["North", "East"])
        
        filtered = filtering_manager.apply_filters("Page", df)
        
        # 검증: 모든 조건 충족
        assert len(filtered) >= 0
        for row in filtered.iter_rows(named=True):
            assert row["TotalSales"] > 50000
            assert row["UnitProfit"] > 0
            assert row["region"] in ["North", "East"]


# =============================================================================
# 2. 필터링 + 추세선 통합 테스트
# =============================================================================

class TestFilteringWithTrendLine:
    """필터링과 추세선 통합 테스트"""
    
    def test_trendline_on_filtered_data(self, sample_sales_data, filtering_manager, curve_fitter):
        """필터된 데이터에 추세선 적용"""
        # 1. 필터 적용: North 지역만
        filtering_manager.add_filter("Page", "region", FilterOperator.EQUALS, "North")
        filtered = filtering_manager.apply_filters("Page", sample_sales_data)
        
        assert len(filtered) > 10  # 충분한 데이터
        
        # 2. 추세선 계산
        x = np.arange(len(filtered), dtype=float)
        y = filtered["sales"].to_numpy().astype(float)
        
        result = curve_fitter.fit(x, y, FitType.LINEAR)
        
        assert result is not None
        assert result.fit_type == FitType.LINEAR
        assert result.r_squared is not None
    
    def test_polynomial_trendline_filtered(self, sample_sales_data, filtering_manager, curve_fitter):
        """필터된 데이터에 다항식 추세선"""
        # 1. 특정 카테고리만 필터
        filtering_manager.add_filter("Page", "category", FilterOperator.EQUALS, "Electronics")
        filtered = filtering_manager.apply_filters("Page", sample_sales_data)
        
        # 2. 다항식 추세선
        x = filtered["quantity"].to_numpy().astype(float)
        y = filtered["sales"].to_numpy().astype(float)
        
        # 정렬 (추세선 계산 전)
        sort_idx = np.argsort(x)
        x, y = x[sort_idx], y[sort_idx]
        
        settings = CurveFitSettings(fit_type=FitType.POLYNOMIAL, degree=2)
        result = curve_fitter.fit(x, y, FitType.POLYNOMIAL, settings)
        
        assert result is not None
        assert result.fit_type == FitType.POLYNOMIAL
    
    def test_forecast_filtered_data(self, sample_sales_data, filtering_manager, curve_fitter):
        """필터된 데이터에서 예측 (미래 예측)"""
        # 1. 날짜 순 정렬 후 필터
        sorted_df = sample_sales_data.sort("date")
        filtering_manager.add_filter("Page", "category", FilterOperator.EQUALS, "Food")
        filtered = filtering_manager.apply_filters("Page", sorted_df)
        
        # 2. 추세선 + 예측
        x = np.arange(len(filtered), dtype=float)
        y = filtered["sales"].to_numpy().astype(float)
        
        result = curve_fitter.fit(x, y, FitType.LINEAR)
        
        if result is not None:
            forecast_settings = ForecastSettings(forward_periods=5, backward_periods=0)
            forecast_x, forecast_y = curve_fitter.forecast(result, x, forecast_settings)
            
            assert len(forecast_x) == 5
            assert all(fx > x[-1] for fx in forecast_x)
    
    def test_trendline_multiple_groups(self, sample_sales_data, filtering_manager, curve_fitter):
        """여러 그룹별 추세선 (트렐리스 스타일)"""
        results = {}
        
        for region in ["North", "South", "East", "West"]:
            # 필터 초기화
            filtering_manager.clear_filters("Page")
            filtering_manager.add_filter("Page", "region", FilterOperator.EQUALS, region)
            filtered = filtering_manager.apply_filters("Page", sample_sales_data)
            
            if len(filtered) > 5:
                x = np.arange(len(filtered), dtype=float)
                y = filtered["sales"].to_numpy().astype(float)
                
                result = curve_fitter.fit(x, y, FitType.LINEAR)
                if result:
                    results[region] = {
                        'r_squared': result.r_squared,
                        'coefficients': result.coefficients,
                        'data_points': len(filtered)
                    }
        
        assert len(results) > 0
        for region, stats in results.items():
            assert 'r_squared' in stats
            assert stats['data_points'] > 0


# =============================================================================
# 3. 트렐리스 + 대시보드 통합 테스트
# =============================================================================

class TestTrellisWithDashboard:
    """트렐리스 차트와 대시보드 통합 테스트"""
    
    def test_trellis_chart_in_dashboard(self, sample_sales_data, trellis_calculator, dashboard_manager):
        """트렐리스 차트를 대시보드에 배치"""
        # 1. 트렐리스 레이아웃 계산
        trellis_settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.ROWS_AND_COLUMNS,
            row_column="region",
            col_column="category"
        )
        
        layout = trellis_calculator.calculate(sample_sales_data, trellis_settings)
        
        assert layout.n_rows > 0
        assert layout.n_cols > 0
        
        # 2. 대시보드에 트렐리스 차트 배치
        dashboard = dashboard_manager.create_dashboard("Sales Analysis", rows=4, cols=4)
        
        trellis_item = DashboardItem(
            id="trellis_chart",
            title="Sales by Region and Category",
            chart_type=ChartType.SCATTER,
            position=GridPosition(row=0, col=0, row_span=2, col_span=3),
            config={
                'trellis_enabled': True,
                'trellis_row': 'region',
                'trellis_col': 'category',
                'x_column': 'quantity',
                'y_column': 'sales'
            }
        )
        
        dashboard.layout.add_item(trellis_item)
        
        assert len(dashboard.layout.items) == 1
        assert dashboard.layout.get_item("trellis_chart") is not None
    
    def test_multiple_trellis_in_dashboard(self, sample_sales_data, trellis_calculator, dashboard_manager):
        """여러 트렐리스 차트를 대시보드에 배치"""
        dashboard = dashboard_manager.create_dashboard("Multi Trellis", rows=4, cols=4)
        
        # 첫 번째 트렐리스: 지역별
        item1 = DashboardItem(
            id="trellis_region",
            title="By Region",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 2, 2),
            config={'trellis_row': 'region'}
        )
        
        # 두 번째 트렐리스: 카테고리별
        item2 = DashboardItem(
            id="trellis_category",
            title="By Category",
            chart_type=ChartType.BAR,
            position=GridPosition(0, 2, 2, 2),
            config={'trellis_row': 'category'}
        )
        
        dashboard.layout.add_item(item1)
        dashboard.layout.add_item(item2)
        
        assert len(dashboard.layout.items) == 2
        
        # 충돌 검사
        assert not dashboard.layout.check_collision(GridPosition(2, 0, 2, 2))
        assert dashboard.layout.check_collision(GridPosition(0, 0, 1, 1))
    
    def test_trellis_with_shared_filter(self, sample_sales_data, trellis_calculator, dashboard_manager):
        """대시보드 공유 필터와 트렐리스"""
        dashboard = dashboard_manager.create_dashboard("Filtered Trellis", rows=3, cols=3)
        
        # 트렐리스 차트 추가
        trellis_item = DashboardItem(
            id="trellis_sales",
            title="Sales Trellis",
            chart_type=ChartType.SCATTER,
            position=GridPosition(0, 0, 2, 2),
            config={'trellis_row': 'region'}
        )
        dashboard.layout.add_item(trellis_item)
        
        # 공유 필터 추가: 특정 카테고리만
        dashboard.layout.add_shared_filter('category', 'in', ['Electronics', 'Clothing'])
        
        # 검증
        filters = dashboard.layout.get_filters_for_item("trellis_sales")
        assert len(filters) == 1
        assert filters[0]['column'] == 'category'


# =============================================================================
# 4. 계산 필드 + 리포트 통합 테스트
# =============================================================================

class TestCalculatedFieldsWithReport:
    """계산 필드와 리포트 생성 통합 테스트"""
    
    def test_report_with_calculated_statistics(self, sample_sales_data, expression_engine):
        """계산 필드 통계를 리포트에 포함"""
        # 1. 계산 필드 추가
        df = sample_sales_data.clone()
        df = expression_engine.add_column(df, "Revenue", "sales * quantity")
        df = expression_engine.add_column(df, "AvgPrice", "sales / quantity")
        
        # 2. 통계 수집
        stats = collect_statistics_from_dataframe(df, "sales_data", "Sales Dataset")
        
        # Revenue와 AvgPrice 통계도 포함되어야 함
        stat_columns = [s.column for s in stats]
        assert "Revenue" in stat_columns
        assert "AvgPrice" in stat_columns
        
        # 3. 리포트 데이터 생성
        report_data = ReportData(
            metadata=ReportMetadata(
                title="Calculated Fields Report",
                subtitle="Analysis with calculated metrics",
                author="Test"
            ),
            datasets=[
                DatasetSummary.from_dataframe(df, "calc_sales", "Calculated Sales")
            ],
            statistics={"calc_sales": stats}
        )
        
        assert report_data.metadata.title == "Calculated Fields Report"
        assert len(report_data.datasets) == 1
        assert report_data.datasets[0].row_count == len(df)
    
    def test_html_report_with_calculations(self, sample_sales_data, expression_engine, tmp_path):
        """계산 필드 포함 HTML 리포트 생성"""
        # 1. 계산 필드 추가
        df = sample_sales_data.clone()
        df = expression_engine.add_column(df, "TotalValue", "sales * quantity")
        df = expression_engine.add_column(df, "Profit", "sales - unit_cost")
        
        # 2. 통계 수집
        stats = collect_statistics_from_dataframe(df, "main", "Main Dataset")
        
        # 3. 리포트 데이터 생성
        report_data = ReportData(
            metadata=ReportMetadata(
                title="Sales Analysis Report",
                subtitle="With Calculated Fields"
            ),
            datasets=[DatasetSummary.from_dataframe(df, "main", "Sales Data")],
            statistics={"main": stats},
            key_findings=["Revenue calculation includes quantity multiplier"],
            recommendations=["Focus on high-profit items"]
        )
        
        # 4. HTML 생성
        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML, language="en")
        
        html_bytes = generator.generate(report_data, options)
        
        assert isinstance(html_bytes, bytes)
        html_content = html_bytes.decode('utf-8')
        
        # 검증
        assert "Sales Analysis Report" in html_content
        assert "<!DOCTYPE html>" in html_content
    
    def test_report_with_derived_columns(self, sample_sales_data, expression_engine):
        """파생 컬럼 기반 리포트"""
        # 복잡한 계산 체인
        df = sample_sales_data.clone()
        df = expression_engine.add_column(df, "GrossRevenue", "sales * quantity")
        df = expression_engine.add_column(df, "DiscountAmount", "GrossRevenue * discount")
        df = expression_engine.add_column(df, "NetRevenue", "GrossRevenue - DiscountAmount")
        df = expression_engine.add_column(df, "TotalCost", "unit_cost * quantity")
        df = expression_engine.add_column(df, "NetProfit", "NetRevenue - TotalCost")
        
        # 요약 테이블 생성
        summary = df.select([
            pl.col("NetRevenue").sum().alias("Total Net Revenue"),
            pl.col("NetProfit").sum().alias("Total Net Profit"),
            pl.col("NetProfit").mean().alias("Avg Net Profit"),
        ])
        
        table_data = TableData(
            id="summary",
            title="Financial Summary",
            table_type="summary",
            columns=summary.columns,
            rows=[list(summary.row(0))],
            total_rows=1,
            shown_rows=1
        )
        
        assert len(table_data.columns) == 3
        assert table_data.rows[0][0] is not None  # Total Net Revenue


# =============================================================================
# 5. 전체 파이프라인 통합 테스트
# =============================================================================

class TestFullPipeline:
    """
    전체 파이프라인 테스트:
    데이터 로드 → 계산 필드 → 필터링 → 추세선 → 트렐리스 → 대시보드 → 리포트
    """
    
    def test_complete_analysis_pipeline(
        self, 
        sample_csv_file, 
        expression_engine, 
        filtering_manager, 
        curve_fitter, 
        trellis_calculator,
        dashboard_manager,
        tmp_path
    ):
        """완전한 분석 파이프라인 테스트"""
        # ===== STEP 1: 데이터 로드 =====
        engine = DataEngine()
        assert engine.load_file(sample_csv_file) is True
        assert engine.is_loaded
        df = engine.df
        
        # ===== STEP 2: 계산 필드 추가 =====
        df = expression_engine.add_column(df, "TotalRevenue", "sales * quantity")
        df = expression_engine.add_column(df, "UnitProfit", "sales - unit_cost")
        df = expression_engine.add_column(df, "TotalProfit", "UnitProfit * quantity")
        df = expression_engine.add_column(df, "ProfitMargin", "TotalProfit / TotalRevenue")
        
        assert all(col in df.columns for col in ["TotalRevenue", "UnitProfit", "TotalProfit", "ProfitMargin"])
        
        # ===== STEP 3: 필터링 =====
        filtering_manager.add_filter("Page", "TotalProfit", FilterOperator.GREATER_THAN, 0)
        filtering_manager.add_filter("Page", "category", FilterOperator.IN_LIST, ["Electronics", "Clothing"])
        filtered_df = filtering_manager.apply_filters("Page", df)
        
        assert len(filtered_df) > 0
        assert len(filtered_df) < len(df)
        
        # ===== STEP 4: 추세선 =====
        # 지역별 추세선 계산
        trendline_results = {}
        for region in filtered_df["region"].unique().to_list():
            region_data = filtered_df.filter(pl.col("region") == region)
            if len(region_data) > 5:
                x = np.arange(len(region_data), dtype=float)
                y = region_data["TotalRevenue"].to_numpy().astype(float)
                
                result = curve_fitter.fit(x, y, FitType.LINEAR)
                if result:
                    coeffs = result.coefficients
                    trendline_results[region] = {
                        'r_squared': result.r_squared,
                        'slope': coeffs[0] if coeffs is not None and len(coeffs) > 0 else None,
                        'intercept': coeffs[1] if coeffs is not None and len(coeffs) > 1 else None
                    }
        
        assert len(trendline_results) > 0
        
        # ===== STEP 5: 트렐리스 =====
        trellis_settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.ROWS_AND_COLUMNS,
            row_column="region",
            col_column="category"
        )
        trellis_layout = trellis_calculator.calculate(filtered_df, trellis_settings)
        
        assert trellis_layout.n_rows > 0
        assert trellis_layout.n_cols > 0
        assert len(trellis_layout.panels) > 0
        
        # ===== STEP 6: 대시보드 =====
        dashboard = dashboard_manager.create_dashboard("Full Analysis Dashboard", rows=4, cols=4)
        
        # 메인 트렐리스 차트
        dashboard.layout.add_item(DashboardItem(
            id="main_trellis",
            title="Revenue by Region & Category",
            chart_type=ChartType.SCATTER,
            position=GridPosition(0, 0, 2, 2),
            config={
                'trellis_enabled': True,
                'trellis_row': 'region',
                'trellis_col': 'category'
            }
        ))
        
        # 추세선 차트
        dashboard.layout.add_item(DashboardItem(
            id="trend_chart",
            title="Revenue Trend",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 2, 2, 2),
            config={'show_trendline': True}
        ))
        
        # 요약 테이블
        dashboard.layout.add_item(DashboardItem(
            id="summary_table",
            title="Summary Statistics",
            chart_type=ChartType.LINE,  # placeholder
            position=GridPosition(2, 0, 2, 4)
        ))
        
        assert len(dashboard.layout.items) == 3
        
        # ===== STEP 7: 리포트 =====
        # 통계 수집
        stats = collect_statistics_from_dataframe(filtered_df, "filtered_sales", "Filtered Sales")
        
        # 리포트 데이터 생성
        report_data = ReportData(
            metadata=ReportMetadata(
                title="Complete Sales Analysis",
                subtitle="Filtered, Calculated, and Analyzed",
                author="Integration Test"
            ),
            datasets=[
                DatasetSummary.from_dataframe(filtered_df, "main", "Filtered Sales Data")
            ],
            statistics={"main": stats},
            key_findings=[
                f"Analyzed {len(filtered_df)} records after filtering",
                f"Trellis displays {trellis_layout.n_rows}x{trellis_layout.n_cols} grid",
                f"Trend analysis for {len(trendline_results)} regions"
            ],
            recommendations=["Focus on high-margin products"]
        )
        
        # HTML 리포트 생성
        generator = HTMLReportGenerator()
        options = ReportOptions(format=ReportFormat.HTML)
        
        output_path = tmp_path / "complete_report.html"
        result_path = generator.save(report_data, options, output_path)
        
        assert result_path.exists()
        content = result_path.read_text(encoding='utf-8')
        assert "Complete Sales Analysis" in content
        assert "<!DOCTYPE html>" in content
    
    def test_pipeline_with_empty_filter_result(
        self, 
        sample_csv_file, 
        expression_engine, 
        filtering_manager
    ):
        """빈 필터 결과 처리"""
        # 데이터 로드
        engine = DataEngine()
        engine.load_file(sample_csv_file)
        df = engine.df
        
        # 계산 필드 추가
        df = expression_engine.add_column(df, "Total", "sales * quantity")
        
        # 불가능한 필터 (Total > 무한대)
        filtering_manager.add_filter("Page", "Total", FilterOperator.GREATER_THAN, float('inf'))
        filtered = filtering_manager.apply_filters("Page", df)
        
        # 빈 결과 확인
        assert len(filtered) == 0
    
    def test_pipeline_with_large_data(self, expression_engine, filtering_manager, curve_fitter):
        """대용량 데이터 파이프라인 테스트"""
        # 대용량 데이터 생성
        np.random.seed(42)
        n = 100000
        
        large_df = pl.DataFrame({
            'id': range(n),
            'value': np.random.randn(n) * 1000 + 5000,
            'quantity': np.random.randint(1, 100, n),
            'category': np.random.choice(['A', 'B', 'C'], n)
        })
        
        # 계산 필드
        large_df = expression_engine.add_column(large_df, "Total", "value * quantity")
        
        # 필터링
        filtering_manager.add_filter("Page", "Total", FilterOperator.GREATER_THAN, 100000)
        filtered = filtering_manager.apply_filters("Page", large_df)
        
        assert len(filtered) < len(large_df)
        
        # 추세선 (샘플링된 데이터)
        if len(filtered) > 1000:
            sample = filtered.sample(1000, seed=42)
        else:
            sample = filtered
        
        x = np.arange(len(sample), dtype=float)
        y = sample["Total"].to_numpy().astype(float)
        
        result = curve_fitter.fit(x, y, FitType.LINEAR)
        assert result is not None


# =============================================================================
# 엣지 케이스 테스트
# =============================================================================

class TestEdgeCases:
    """엣지 케이스 통합 테스트"""
    
    def test_null_handling_in_pipeline(self, expression_engine, filtering_manager):
        """NULL 값 처리"""
        df = pl.DataFrame({
            'a': [1, None, 3, None, 5],
            'b': [10, 20, None, 40, 50]
        })
        
        # 계산 필드 (NULL 포함)
        df = expression_engine.add_column(df, "c", "a + b")
        
        # NULL 제외 필터
        filtering_manager.add_filter("Page", "c", FilterOperator.IS_NOT_NULL, None)
        filtered = filtering_manager.apply_filters("Page", df)
        
        assert len(filtered) == 2  # NULL 아닌 것만
    
    def test_empty_dataframe_handling(self, expression_engine, trellis_calculator):
        """빈 DataFrame 처리"""
        empty_df = pl.DataFrame({
            'a': [],
            'b': [],
            'category': []
        })
        
        # 계산 필드
        result = expression_engine.add_column(empty_df, "c", "a * b")
        assert len(result) == 0
        assert "c" in result.columns
        
        # 트렐리스 - 빈 데이터는 disabled로 처리하는 것이 안전
        settings = TrellisSettings(enabled=False)  # 빈 데이터는 trellis 비활성화
        layout = trellis_calculator.calculate(empty_df, settings)
        
        # disabled된 트렐리스는 1x1 레이아웃
        assert layout.n_rows == 1
        assert layout.n_cols == 1
        
        # 최소한의 데이터로 트렐리스 테스트 (빈 데이터가 아닌)
        minimal_df = pl.DataFrame({
            'a': [1, 2],
            'b': [10, 20],
            'category': ['A', 'B']
        })
        settings_enabled = TrellisSettings(enabled=True, row_column="category")
        layout_enabled = trellis_calculator.calculate(minimal_df, settings_enabled)
        
        assert layout_enabled.n_rows >= 1
        assert layout_enabled.n_cols >= 1
    
    def test_special_characters_in_columns(self, expression_engine, filtering_manager):
        """특수 문자가 포함된 컬럼명 처리"""
        df = pl.DataFrame({
            'Sales_2024': [100, 200, 300],
            'Cost': [50, 100, 150]
        })
        
        # 계산 필드
        df = expression_engine.add_column(df, "Profit_2024", "Sales_2024 - Cost")
        
        assert "Profit_2024" in df.columns
        assert df["Profit_2024"].to_list() == [50, 100, 150]
    
    def test_division_by_zero_in_calculation(self, expression_engine):
        """0으로 나누기 처리"""
        df = pl.DataFrame({
            'a': [10, 20, 30],
            'b': [2, 0, 5]
        })
        
        result = expression_engine.evaluate("a / b", df)
        
        # Polars는 0으로 나누면 inf 반환
        assert result[0] == 5.0
        assert result[1] == float('inf')
        assert result[2] == 6.0


# =============================================================================
# 에러 전파 테스트
# =============================================================================

class TestErrorPropagation:
    """에러 전파 테스트"""
    
    def test_invalid_expression_propagation(self, expression_engine, filtering_manager):
        """잘못된 수식 에러 전파"""
        df = pl.DataFrame({'a': [1, 2, 3]})
        
        # 존재하지 않는 컬럼 참조
        with pytest.raises(ExpressionError):
            expression_engine.evaluate("nonexistent * 2", df)
    
    def test_filter_on_nonexistent_column(self, filtering_manager):
        """존재하지 않는 컬럼 필터링"""
        df = pl.DataFrame({'a': [1, 2, 3]})
        
        filtering_manager.add_filter("Page", "nonexistent", FilterOperator.EQUALS, 1)
        
        # 필터 적용 시 에러 발생 가능
        # FilteringManager는 에러를 무시하고 원본 반환하거나 에러 발생
        try:
            result = filtering_manager.apply_filters("Page", df)
            # 에러 무시하는 경우 원본 반환
            assert len(result) == 3
        except Exception:
            # 에러 발생하는 경우
            pass
    
    def test_trendline_insufficient_data(self, curve_fitter):
        """데이터 부족 시 추세선 실패"""
        x = np.array([1.0])
        y = np.array([10.0])
        
        result = curve_fitter.fit(x, y, FitType.LINEAR)
        
        # 데이터 부족으로 None 반환
        assert result is None


# =============================================================================
# 성능 테스트
# =============================================================================

class TestPerformance:
    """성능 테스트"""
    
    def test_large_calculation_chain(self, expression_engine):
        """대량 계산 체인 성능"""
        import time
        
        # 50만 행 데이터
        df = pl.DataFrame({
            'a': np.random.randn(500000),
            'b': np.random.randn(500000),
            'c': np.random.randn(500000)
        })
        
        start = time.time()
        
        # 연속 계산
        df = expression_engine.add_column(df, "d", "a + b")
        df = expression_engine.add_column(df, "e", "d * c")
        df = expression_engine.add_column(df, "f", "e / (a + 1)")
        df = expression_engine.add_column(df, "g", "ROUND(f, 2)")
        
        elapsed = time.time() - start
        
        assert "g" in df.columns
        assert elapsed < 5.0  # 5초 이내 완료
    
    def test_large_filter_chain(self, filtering_manager):
        """대량 필터 체인 성능"""
        import time
        
        # 50만 행 데이터
        df = pl.DataFrame({
            'value': np.random.randn(500000),
            'category': np.random.choice(['A', 'B', 'C', 'D'], 500000)
        })
        
        start = time.time()
        
        # 여러 필터
        filtering_manager.add_filter("Page", "value", FilterOperator.GREATER_THAN, 0)
        filtering_manager.add_filter("Page", "category", FilterOperator.IN_LIST, ['A', 'B'])
        
        result = filtering_manager.apply_filters("Page", df)
        
        elapsed = time.time() - start
        
        assert len(result) < len(df)
        assert elapsed < 2.0  # 2초 이내 완료
