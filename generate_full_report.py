"""그래프 포함 풀 레포트 생성"""
import sys
sys.path.insert(0, '.')

from datetime import datetime
from pathlib import Path
import polars as pl
import base64
import io

# Matplotlib for chart generation
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 한글 폰트 설정
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

from data_graph_studio.core.report import (
    ReportMetadata,
    ReportData,
    ReportOptions,
    ReportTemplate,
    ReportTheme,
    DatasetSummary,
    StatisticalSummary,
    TableData,
    ChartData,
)
from data_graph_studio.report.html_generator import HTMLReportGenerator

# 샘플 데이터 로드
df = pl.read_csv('test_data/01_sales_simple.csv')

def create_chart_base64(fig) -> str:
    """Figure를 base64로 인코딩"""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

# === 차트 1: 지역별 총 매출 막대 그래프 ===
fig1, ax1 = plt.subplots(figsize=(10, 6))
region_sales = df.group_by('region').agg(pl.col('sales').sum()).sort('sales', descending=True)
colors = ['#3b82f6', '#8b5cf6', '#10b981']
bars = ax1.bar(region_sales['region'].to_list(), region_sales['sales'].to_list(), color=colors)
ax1.set_title('Region Sales Performance', fontsize=16, fontweight='bold', pad=20)
ax1.set_xlabel('Region', fontsize=12)
ax1.set_ylabel('Total Sales ($)', fontsize=12)
ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1000:.0f}K'))
for bar, val in zip(bars, region_sales['sales'].to_list()):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1000, 
             f'${val/1000:.1f}K', ha='center', va='bottom', fontsize=11, fontweight='bold')
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
plt.tight_layout()
chart1_b64 = create_chart_base64(fig1)
plt.close(fig1)

# === 차트 2: 제품별 매출 파이 차트 ===
fig2, ax2 = plt.subplots(figsize=(8, 8))
product_sales = df.group_by('product').agg(pl.col('sales').sum())
colors2 = ['#f59e0b', '#6366f1']
wedges, texts, autotexts = ax2.pie(
    product_sales['sales'].to_list(), 
    labels=product_sales['product'].to_list(),
    autopct='%1.1f%%',
    colors=colors2,
    explode=(0.02, 0.02),
    shadow=True,
    startangle=90
)
ax2.set_title('Sales by Product Category', fontsize=16, fontweight='bold', pad=20)
for autotext in autotexts:
    autotext.set_fontsize(14)
    autotext.set_fontweight('bold')
plt.tight_layout()
chart2_b64 = create_chart_base64(fig2)
plt.close(fig2)

# === 차트 3: 일별 매출 추이 라인 차트 ===
fig3, ax3 = plt.subplots(figsize=(12, 6))
daily_sales = df.group_by('date').agg(pl.col('sales').sum()).sort('date')
ax3.plot(daily_sales['date'].to_list(), daily_sales['sales'].to_list(), 
         marker='o', linewidth=2.5, markersize=8, color='#3b82f6')
ax3.fill_between(daily_sales['date'].to_list(), daily_sales['sales'].to_list(), 
                  alpha=0.3, color='#3b82f6')
ax3.set_title('Daily Sales Trend', fontsize=16, fontweight='bold', pad=20)
ax3.set_xlabel('Date', fontsize=12)
ax3.set_ylabel('Total Sales ($)', fontsize=12)
ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1000:.0f}K'))
ax3.grid(True, alpha=0.3)
ax3.spines['top'].set_visible(False)
ax3.spines['right'].set_visible(False)
plt.xticks(rotation=45)
plt.tight_layout()
chart3_b64 = create_chart_base64(fig3)
plt.close(fig3)

# === 차트 4: 지역-제품별 히트맵 ===
fig4, ax4 = plt.subplots(figsize=(10, 6))
pivot_data = df.pivot(values='sales', index='region', on='product', aggregate_function='sum')
regions = pivot_data['region'].to_list()
products = [c for c in pivot_data.columns if c != 'region']
values = [[pivot_data.filter(pl.col('region') == r)[p].item() for p in products] for r in regions]

im = ax4.imshow(values, cmap='Blues', aspect='auto')
ax4.set_xticks(range(len(products)))
ax4.set_yticks(range(len(regions)))
ax4.set_xticklabels(products, fontsize=12)
ax4.set_yticklabels(regions, fontsize=12)
ax4.set_title('Sales Heatmap: Region vs Product', fontsize=16, fontweight='bold', pad=20)

# 값 표시
for i in range(len(regions)):
    for j in range(len(products)):
        text = ax4.text(j, i, f'${values[i][j]/1000:.1f}K',
                       ha='center', va='center', color='white' if values[i][j] > 40000 else 'black',
                       fontsize=12, fontweight='bold')

cbar = plt.colorbar(im, ax=ax4)
cbar.set_label('Sales ($)', fontsize=12)
plt.tight_layout()
chart4_b64 = create_chart_base64(fig4)
plt.close(fig4)

# === 레포트 데이터 구성 ===
metadata = ReportMetadata(
    title="Sales Performance Analysis",
    subtitle="2024 Q1 Regional Sales Report",
    author="Data Graph Studio",
    version="1.0.0",
    created_at=datetime.now()
)

dataset_summary = DatasetSummary.from_dataframe(
    df=df,
    id="sales_data",
    name="Sales Data Q1 2024",
    color="#3b82f6"
)

# 통계
stats = {}
numeric_cols = ['sales', 'quantity', 'price']
stats["sales_data"] = [
    StatisticalSummary.from_series(df[col], col)
    for col in numeric_cols
]

# 테이블
table = TableData.from_dataframe(
    df=df,
    id="sales_table",
    title="Sales Data Overview",
    max_rows=16
)

# 차트 데이터
charts = [
    ChartData(
        id="region_sales",
        title="Regional Sales Performance",
        description="Asia region leads with highest total sales, followed by America showing strong growth momentum.",
        chart_type="bar",
        image_base64=chart1_b64,
        image_format="png"
    ),
    ChartData(
        id="product_pie",
        title="Product Category Distribution",
        description="Laptop sales dominate the revenue stream with 75% share, indicating premium product preference.",
        chart_type="pie",
        image_base64=chart2_b64,
        image_format="png"
    ),
    ChartData(
        id="daily_trend",
        title="Daily Sales Trend",
        description="Sales show steady growth pattern with notable peaks on Jan 4-5 driven by American market entry.",
        chart_type="line",
        image_base64=chart3_b64,
        image_format="png"
    ),
    ChartData(
        id="heatmap",
        title="Sales Heatmap by Region and Product",
        description="Visualization of sales distribution across regions and product categories.",
        chart_type="heatmap",
        image_base64=chart4_b64,
        image_format="png"
    ),
]

# 주요 발견
key_findings = [
    "Asia region leads with $243K total sales (38% of total)",
    "Laptop products generate 75% of total revenue despite lower unit sales",
    "American market shows highest growth rate at +15% day-over-day",
    "Average order value for Laptops ($900) is 6x higher than Phones ($150)",
    "Europe maintains stable performance across all product categories"
]

recommendations = [
    "Expand marketing investment in Asia region to capitalize on strong performance",
    "Increase Laptop inventory to meet growing demand",
    "Accelerate American market expansion through strategic partnerships",
    "Consider premium Phone variants to increase Phone segment revenue",
    "Implement cross-selling strategies between Laptop and Phone products"
]

# 레포트 데이터 생성
report_data = ReportData(
    metadata=metadata,
    datasets=[dataset_summary],
    statistics=stats,
    tables=[table],
    charts=charts,
    key_findings=key_findings,
    recommendations=recommendations,
    methodology_notes=[
        "Data collected from Q1 2024 sales transactions",
        "Statistical analysis performed using Polars library",
        "Visualizations created with Matplotlib"
    ]
)

# 레포트 옵션
options = ReportOptions(
    language='en',
    theme=ReportTheme.LIGHT,
    include_executive_summary=True,
    include_data_overview=True,
    include_statistics=True,
    include_visualizations=True,
    include_tables=True,
    include_appendix=True
)

# 템플릿
template = ReportTemplate(
    id="professional",
    name="Professional Template",
    primary_color="#3b82f6",
    secondary_color="#8b5cf6",
    accent_color="#10b981",
    font_family="'Segoe UI', 'Noto Sans KR', sans-serif"
)

# HTML 레포트 생성
html_gen = HTMLReportGenerator(template)
html_bytes = html_gen.generate(report_data, options)

# 저장
output_path = Path("sales_report_with_charts.html")
output_path.write_bytes(html_bytes)
print(f"Report generated: {output_path.absolute()}")
print(f"  - Charts: {len(charts)}")
print(f"  - Key Findings: {len(key_findings)}")
print(f"  - Recommendations: {len(recommendations)}")
