"""
HTML Report Generator
HTML 레포트 생성기

Self-contained HTML with embedded CSS and images.
Supports light/dark themes and interactive charts.
"""

import html

from data_graph_studio.core.report import (
    ReportGenerator,
    ReportData,
    ReportOptions,
    ReportTemplate,
    ReportTheme,
    ChartData,
)


class HTMLReportGenerator(ReportGenerator):
    """HTML 레포트 생성기"""

    def generate(self, report_data: ReportData, options: ReportOptions) -> bytes:
        """HTML 레포트 생성"""
        html_content = self._build_html(report_data, options)
        return html_content.encode("utf-8")

    def _build_html(self, report_data: ReportData, options: ReportOptions) -> str:
        """HTML 문서 빌드"""
        theme = options.theme
        template = self.template

        # CSS 스타일
        css = self._get_css(theme, template)

        # 섹션별 HTML 생성
        sections_html = []

        # Executive Summary
        if options.include_executive_summary:
            sections_html.append(self._render_executive_summary(report_data, options))

        # Data Overview
        if options.include_data_overview:
            sections_html.append(self._render_data_overview(report_data, options))

        # Statistics
        if options.include_statistics:
            sections_html.append(self._render_statistics(report_data, options))

        # Visualizations
        if options.include_visualizations and report_data.charts:
            sections_html.append(self._render_visualizations(report_data, options))

        # Comparison Analysis (멀티데이터)
        if options.include_comparison and report_data.is_multi_dataset():
            sections_html.append(self._render_comparison(report_data, options))

        # Data Tables
        if options.include_tables and report_data.tables:
            sections_html.append(self._render_tables(report_data, options))

        # Appendix
        if options.include_appendix:
            sections_html.append(self._render_appendix(report_data, options))

        # 전체 HTML 조립
        body_content = "\n".join(sections_html)

        # Table of Contents
        toc = self._generate_toc(report_data, options)

        html_doc = f'''<!DOCTYPE html>
<html lang="{options.language}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="generator" content="Data Graph Studio">
    <meta name="author" content="{html.escape(report_data.metadata.author or "")}">
    <title>{html.escape(report_data.metadata.title)}</title>
    <style>
{css}
    </style>
</head>
<body class="theme-{theme.value}">
    <div class="report-container">
        {self._render_header(report_data, options)}
        {toc}
        <main class="report-content">
            {body_content}
        </main>
        {self._render_footer(report_data, options)}
    </div>
    {self._get_scripts(options)}
</body>
</html>'''

        return html_doc

    def _get_css(self, theme: ReportTheme, template: ReportTemplate) -> str:
        """CSS 스타일 반환"""
        primary = template.primary_color
        secondary = template.secondary_color
        accent = template.accent_color
        font = template.font_family

        # 테마별 색상
        if theme == ReportTheme.DARK:
            bg_color = "#1a1a2e"
            surface_color = "#16213e"
            text_color = "#e8e8e8"
            text_secondary = "#a0a0a0"
            border_color = "#2a2a4a"
            card_shadow = "0 4px 6px rgba(0, 0, 0, 0.3)"
        else:  # LIGHT or default
            bg_color = "#f8fafc"
            surface_color = "#ffffff"
            text_color = "#1e293b"
            text_secondary = "#64748b"
            border_color = "#e2e8f0"
            card_shadow = "0 4px 6px rgba(0, 0, 0, 0.05)"

        return f"""
/* Reset and base styles */
* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: {font};
    background-color: {bg_color};
    color: {text_color};
    line-height: 1.6;
    font-size: 14px;
}}

.report-container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}}

/* Header */
.report-header {{
    background: linear-gradient(135deg, {primary} 0%, {secondary} 100%);
    color: white;
    padding: 40px;
    border-radius: 12px;
    margin-bottom: 30px;
    text-align: center;
}}

.report-header h1 {{
    font-size: 2.5rem;
    margin-bottom: 10px;
    font-weight: 700;
}}

.report-header .subtitle {{
    font-size: 1.2rem;
    opacity: 0.9;
    margin-bottom: 20px;
}}

.report-meta {{
    display: flex;
    justify-content: center;
    gap: 30px;
    font-size: 0.9rem;
    opacity: 0.8;
}}

.report-meta span {{
    display: flex;
    align-items: center;
    gap: 5px;
}}

/* Logo */
.report-logo {{
    max-height: 60px;
    margin-bottom: 20px;
}}

/* Table of Contents */
.toc {{
    background: {surface_color};
    border: 1px solid {border_color};
    border-radius: 12px;
    padding: 25px;
    margin-bottom: 30px;
    box-shadow: {card_shadow};
}}

.toc h2 {{
    font-size: 1.3rem;
    margin-bottom: 15px;
    color: {primary};
}}

.toc ul {{
    list-style: none;
}}

.toc li {{
    padding: 8px 0;
    border-bottom: 1px solid {border_color};
}}

.toc li:last-child {{
    border-bottom: none;
}}

.toc a {{
    color: {text_color};
    text-decoration: none;
    display: flex;
    justify-content: space-between;
    transition: color 0.2s;
}}

.toc a:hover {{
    color: {primary};
}}

/* Sections */
.section {{
    background: {surface_color};
    border: 1px solid {border_color};
    border-radius: 12px;
    padding: 30px;
    margin-bottom: 30px;
    box-shadow: {card_shadow};
}}

.section h2 {{
    font-size: 1.5rem;
    color: {primary};
    margin-bottom: 20px;
    padding-bottom: 10px;
    border-bottom: 2px solid {primary};
}}

.section h3 {{
    font-size: 1.2rem;
    color: {text_color};
    margin: 20px 0 15px 0;
}}

/* Metric Cards */
.metrics-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 25px;
}}

.metric-card {{
    background: linear-gradient(135deg, {surface_color} 0%, {bg_color} 100%);
    border: 1px solid {border_color};
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s;
}}

.metric-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 15px rgba(0, 0, 0, 0.1);
}}

.metric-card .label {{
    font-size: 0.85rem;
    color: {text_secondary};
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

.metric-card .value {{
    font-size: 1.8rem;
    font-weight: 700;
    color: {primary};
}}

.metric-card .change {{
    font-size: 0.85rem;
    margin-top: 5px;
}}

.metric-card .change.positive {{
    color: #22c55e;
}}

.metric-card .change.negative {{
    color: #ef4444;
}}

/* Tables */
.data-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    font-size: 0.9rem;
}}

.data-table th,
.data-table td {{
    padding: 12px 15px;
    text-align: left;
    border-bottom: 1px solid {border_color};
}}

.data-table th {{
    background: {primary};
    color: white;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.8rem;
    letter-spacing: 0.5px;
}}

.data-table tbody tr:hover {{
    background: {bg_color};
}}

.data-table tbody tr:nth-child(even) {{
    background: rgba(0, 0, 0, 0.02);
}}

.data-table .numeric {{
    text-align: right;
    font-family: 'Consolas', 'Monaco', monospace;
}}

.data-table .highlight {{
    background: rgba({self._hex_to_rgb(primary)}, 0.1);
    font-weight: 600;
}}

/* Comparison specific */
.comparison-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 20px;
}}

.comparison-card {{
    background: {surface_color};
    border: 2px solid;
    border-radius: 10px;
    padding: 20px;
}}

.comparison-card h4 {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 15px;
}}

.comparison-card .color-dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
}}

/* Statistical Test Results */
.test-result {{
    background: {bg_color};
    border-left: 4px solid {primary};
    padding: 20px;
    margin: 15px 0;
    border-radius: 0 8px 8px 0;
}}

.test-result .test-name {{
    font-weight: 600;
    font-size: 1.1rem;
    margin-bottom: 10px;
}}

.test-result .stats-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    margin: 10px 0;
}}

.test-result .stat-item {{
    display: flex;
    gap: 5px;
}}

.test-result .stat-item .label {{
    color: {text_secondary};
}}

.test-result .stat-item .value {{
    font-weight: 600;
}}

.significance {{
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 600;
}}

.significance.sig-high {{
    background: #dcfce7;
    color: #166534;
}}

.significance.sig-medium {{
    background: #fef9c3;
    color: #854d0e;
}}

.significance.sig-low {{
    background: #fee2e2;
    color: #991b1b;
}}

.significance.sig-none {{
    background: #f1f5f9;
    color: #475569;
}}

/* Difference Analysis */
.diff-bar {{
    display: flex;
    height: 30px;
    border-radius: 5px;
    overflow: hidden;
    margin: 15px 0;
}}

.diff-bar .positive {{
    background: #22c55e;
}}

.diff-bar .negative {{
    background: #ef4444;
}}

.diff-bar .neutral {{
    background: #94a3b8;
}}

.diff-legend {{
    display: flex;
    justify-content: center;
    gap: 30px;
    margin-top: 10px;
    font-size: 0.9rem;
}}

.diff-legend span {{
    display: flex;
    align-items: center;
    gap: 8px;
}}

.diff-legend .dot {{
    width: 12px;
    height: 12px;
    border-radius: 3px;
}}

/* Charts */
.chart-container {{
    background: {surface_color};
    border: 1px solid {border_color};
    border-radius: 10px;
    padding: 20px;
    margin: 20px 0;
    text-align: center;
}}

.chart-container h4 {{
    margin-bottom: 15px;
    color: {text_color};
}}

.chart-container img {{
    max-width: 100%;
    height: auto;
    border-radius: 8px;
}}

.chart-description {{
    margin-top: 10px;
    font-size: 0.9rem;
    color: {text_secondary};
}}

/* Chart Statistics Table */
.chart-statistics {{
    margin-top: 15px;
    display: flex;
    justify-content: center;
}}

.chart-statistics .stats-table {{
    max-width: 350px;
    margin: 0;
    font-size: 0.85rem;
}}

.chart-statistics .stats-table th {{
    background: {secondary};
    padding: 8px 12px;
}}

.chart-statistics .stats-table td {{
    padding: 6px 12px;
}}

.chart-statistics .stats-table td:first-child {{
    font-weight: 500;
    color: {text_secondary};
}}

.charts-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
    gap: 20px;
}}

/* Key Findings */
.findings-list {{
    list-style: none;
    padding: 0;
}}

.findings-list li {{
    padding: 12px 15px;
    margin: 10px 0;
    background: {bg_color};
    border-left: 4px solid {accent};
    border-radius: 0 8px 8px 0;
}}

.findings-list li::before {{
    content: "\\2713";
    color: {accent};
    font-weight: bold;
    margin-right: 10px;
}}

/* Recommendations */
.recommendations-list {{
    list-style: none;
    padding: 0;
}}

.recommendations-list li {{
    padding: 12px 15px;
    margin: 10px 0;
    background: {bg_color};
    border-left: 4px solid {secondary};
    border-radius: 0 8px 8px 0;
}}

/* Footer */
.report-footer {{
    text-align: center;
    padding: 30px;
    color: {text_secondary};
    font-size: 0.85rem;
    border-top: 1px solid {border_color};
    margin-top: 40px;
}}

.report-footer a {{
    color: {primary};
    text-decoration: none;
}}

/* Collapsible sections */
.collapsible {{
    cursor: pointer;
}}

.collapsible::after {{
    content: " \\25BC";
    font-size: 0.8em;
}}

.collapsible.collapsed::after {{
    content: " \\25B6";
}}

.collapsible-content {{
    overflow: hidden;
    transition: max-height 0.3s ease-out;
}}

.collapsible-content.collapsed {{
    max-height: 0;
    padding: 0;
}}

/* Print styles */
@media print {{
    body {{
        background: white;
        font-size: 12px;
    }}

    .report-container {{
        max-width: none;
        padding: 0;
    }}

    .section {{
        break-inside: avoid;
        box-shadow: none;
        border: 1px solid #ddd;
    }}

    .chart-container {{
        break-inside: avoid;
    }}

    .toc {{
        break-after: page;
    }}

    .report-header {{
        background: {primary} !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }}
}}

/* Responsive */
@media (max-width: 768px) {{
    .report-header h1 {{
        font-size: 1.8rem;
    }}

    .report-meta {{
        flex-direction: column;
        gap: 10px;
    }}

    .metrics-grid {{
        grid-template-columns: repeat(2, 1fr);
    }}

    .comparison-grid {{
        grid-template-columns: 1fr;
    }}

    .charts-grid {{
        grid-template-columns: 1fr;
    }}

    .data-table {{
        font-size: 0.8rem;
    }}

    .data-table th,
    .data-table td {{
        padding: 8px 10px;
    }}
}}
"""

    def _hex_to_rgb(self, hex_color: str) -> str:
        """HEX 색상을 RGB로 변환"""
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"{r}, {g}, {b}"

    def _render_header(self, report_data: ReportData, options: ReportOptions) -> str:
        """헤더 렌더링"""
        meta = report_data.metadata

        logo_html = ""
        if meta.logo_base64:
            logo_html = f'<img src="data:image/png;base64,{meta.logo_base64}" class="report-logo" alt="Logo">'
        elif meta.logo_path:
            logo_html = f'<img src="{html.escape(meta.logo_path)}" class="report-logo" alt="Logo">'

        subtitle_html = ""
        if meta.subtitle:
            subtitle_html = f'<p class="subtitle">{html.escape(meta.subtitle)}</p>'

        return f"""
<header class="report-header">
    {logo_html}
    <h1>{html.escape(meta.title)}</h1>
    {subtitle_html}
    <div class="report-meta">
        <span>📅 {meta.created_at.strftime("%Y-%m-%d %H:%M")}</span>
        {f"<span>👤 {html.escape(meta.author)}</span>" if meta.author else ""}
        <span>📊 Data Graph Studio v{meta.version}</span>
    </div>
</header>"""

    def _generate_toc(self, report_data: ReportData, options: ReportOptions) -> str:
        """목차 생성"""
        items = []

        if options.include_executive_summary:
            items.append(("executive-summary", "Executive Summary", "요약"))

        if options.include_data_overview:
            items.append(("data-overview", "Data Overview", "데이터 개요"))

        if options.include_statistics:
            items.append(("statistics", "Statistical Summary", "통계 요약"))

        if options.include_visualizations and report_data.charts:
            items.append(("visualizations", "Visualizations", "시각화"))

        if options.include_comparison and report_data.is_multi_dataset():
            items.append(("comparison", "Comparison Analysis", "비교 분석"))

        if options.include_tables and report_data.tables:
            items.append(("data-tables", "Data Tables", "데이터 테이블"))

        if options.include_appendix:
            items.append(("appendix", "Appendix", "부록"))

        toc_items = []
        for id, en_title, ko_title in items:
            title = ko_title if options.language == "ko" else en_title
            toc_items.append(f'<li><a href="#{id}">{title}</a></li>')

        toc_title = "목차" if options.language == "ko" else "Table of Contents"

        return f"""
<nav class="toc">
    <h2>{toc_title}</h2>
    <ul>
        {"".join(toc_items)}
    </ul>
</nav>"""

    def _render_executive_summary(
        self, report_data: ReportData, options: ReportOptions
    ) -> str:
        """Executive Summary 렌더링 - 객관적 수치만 표시"""
        is_ko = options.language == "ko"

        # 주요 지표 카드
        metrics = []

        # 전체 행 수
        total_rows = report_data.get_total_rows()
        metrics.append(
            {
                "label": "총 행 수" if is_ko else "Total Rows",
                "value": self.format_number(total_rows, 0),
            }
        )

        # 데이터셋 수
        metrics.append(
            {
                "label": "데이터셋" if is_ko else "Datasets",
                "value": str(len(report_data.datasets)),
            }
        )

        # 컬럼 수 (첫 번째 데이터셋 기준)
        if report_data.datasets:
            metrics.append(
                {
                    "label": "컬럼 수" if is_ko else "Columns",
                    "value": str(report_data.datasets[0].column_count),
                }
            )

        # 차트 수
        if report_data.charts:
            metrics.append(
                {
                    "label": "차트" if is_ko else "Charts",
                    "value": str(len(report_data.charts)),
                }
            )

        metrics_html = "".join(
            [
                f"""
            <div class="metric-card">
                <div class="label">{m["label"]}</div>
                <div class="value">{m["value"]}</div>
            </div>"""
                for m in metrics
            ]
        )

        # key_findings와 recommendations는 주관적 의견이므로 제거됨

        section_title = "Executive Summary" if not is_ko else "요약"

        return f"""
<section id="executive-summary" class="section">
    <h2>{section_title}</h2>
    <div class="metrics-grid">
        {metrics_html}
    </div>
</section>"""

    def _render_data_overview(
        self, report_data: ReportData, options: ReportOptions
    ) -> str:
        """Data Overview 렌더링"""
        is_ko = options.language == "ko"

        datasets_html = []
        for ds in report_data.datasets:
            color_style = f"border-color: {ds.color};"

            # 기본 정보
            info_items = [
                (("행 수" if is_ko else "Rows"), self.format_number(ds.row_count, 0)),
                (("컬럼 수" if is_ko else "Columns"), str(ds.column_count)),
                (("메모리" if is_ko else "Memory"), self.format_bytes(ds.memory_bytes)),
            ]

            if ds.file_path:
                info_items.insert(
                    0, (("파일" if is_ko else "File"), ds.file_path.split("/")[-1])
                )

            if ds.date_range:
                date_str = f"{ds.date_range['min']} ~ {ds.date_range['max']}"
                info_items.append(("날짜 범위" if is_ko else "Date Range", date_str))

            info_html = "".join(
                [
                    f'<tr><td>{label}</td><td class="numeric">{value}</td></tr>'
                    for label, value in info_items
                ]
            )

            # 컬럼 타입 요약
            type_counts = {}
            for col, dtype in ds.column_types.items():
                type_counts[dtype] = type_counts.get(dtype, 0) + 1

            type_summary = ", ".join([f"{t}: {c}" for t, c in type_counts.items()])

            # 결측값 정보
            missing_html = ""
            if ds.missing_values:
                missing_title = "결측값" if is_ko else "Missing Values"
                missing_items = "".join(
                    [
                        f'<tr><td>{col}</td><td class="numeric">{count}</td></tr>'
                        for col, count in ds.missing_values.items()
                    ]
                )
                missing_html = f"""
                <h4>{missing_title}</h4>
                <table class="data-table" style="max-width: 300px;">
                    <thead><tr><th>{"컬럼" if is_ko else "Column"}</th><th>{"개수" if is_ko else "Count"}</th></tr></thead>
                    <tbody>{missing_items}</tbody>
                </table>"""

            datasets_html.append(f'''
            <div class="comparison-card" style="{color_style}">
                <h4>
                    <span class="color-dot" style="background: {ds.color};"></span>
                    {html.escape(ds.name)}
                </h4>
                <table class="data-table">
                    <tbody>{info_html}</tbody>
                </table>
                <p style="margin-top: 10px; font-size: 0.85rem; color: var(--text-secondary);">
                    <strong>{"데이터 타입" if is_ko else "Data Types"}:</strong> {type_summary}
                </p>
                {missing_html}
            </div>''')

        section_title = "데이터 개요" if is_ko else "Data Overview"

        return f"""
<section id="data-overview" class="section">
    <h2>{section_title}</h2>
    <div class="comparison-grid">
        {"".join(datasets_html)}
    </div>
</section>"""

    def _render_statistics(
        self, report_data: ReportData, options: ReportOptions
    ) -> str:
        """통계 요약 렌더링"""
        is_ko = options.language == "ko"

        if not report_data.statistics:
            return ""

        # 데이터셋별 통계 테이블
        tables_html = []

        for dataset_id, stats_list in report_data.statistics.items():
            if not stats_list:
                continue

            # 데이터셋 이름 찾기
            dataset_name = dataset_id
            for ds in report_data.datasets:
                if ds.id == dataset_id:
                    dataset_name = ds.name
                    break

            # 테이블 헤더
            headers = [
                "컬럼" if is_ko else "Column",
                "Count",
                "Mean",
                "Median",
                "Std",
                "Min",
                "Max",
                "Q1",
                "Q3",
            ]

            header_html = "".join([f"<th>{h}</th>" for h in headers])

            # 테이블 행
            rows_html = []
            for stat in stats_list:
                row = f"""
                <tr>
                    <td>{html.escape(stat.column)}</td>
                    <td class="numeric">{self.format_number(stat.count, 0)}</td>
                    <td class="numeric">{self.format_number(stat.mean)}</td>
                    <td class="numeric">{self.format_number(stat.median)}</td>
                    <td class="numeric">{self.format_number(stat.std)}</td>
                    <td class="numeric">{self.format_number(stat.min)}</td>
                    <td class="numeric">{self.format_number(stat.max)}</td>
                    <td class="numeric">{self.format_number(stat.q1)}</td>
                    <td class="numeric">{self.format_number(stat.q3)}</td>
                </tr>"""
                rows_html.append(row)

            tables_html.append(f"""
            <h3>{html.escape(dataset_name)}</h3>
            <table class="data-table">
                <thead><tr>{header_html}</tr></thead>
                <tbody>{"".join(rows_html)}</tbody>
            </table>""")

        section_title = "통계 요약" if is_ko else "Statistical Summary"

        return f"""
<section id="statistics" class="section">
    <h2>{section_title}</h2>
    {"".join(tables_html)}
</section>"""

    def _render_chart_statistics(self, chart: ChartData, options: ReportOptions) -> str:
        """차트 통계 테이블 렌더링"""
        if not options.include_chart_statistics:
            return ""

        # 표시할 통계 가져오기
        stats_to_display = chart.get_statistics_for_display()
        if not stats_to_display:
            return ""

        is_ko = options.language == "ko"

        # 통계 이름 번역
        stat_labels = {
            "count": ("개수", "Count"),
            "total": ("합계", "Total"),
            "mean": ("평균", "Mean"),
            "median": ("중앙값", "Median"),
            "min": ("최소", "Min"),
            "max": ("최대", "Max"),
            "std": ("표준편차", "Std"),
            "change_percent": ("변화율", "Change%"),
            "start_value": ("시작값", "Start"),
            "end_value": ("종료값", "End"),
            "trend_direction": ("추세", "Trend"),
            "percentage": ("비율", "%"),
            "correlation": ("상관계수", "r"),
            "r_squared": ("결정계수", "R²"),
            "x_range": ("X 범위", "X Range"),
            "y_range": ("Y 범위", "Y Range"),
            "max_cell_location": ("최대 위치", "Max Cell"),
            "min_cell_location": ("최소 위치", "Min Cell"),
            "q1": ("Q1", "Q1"),
            "q3": ("Q3", "Q3"),
            "iqr": ("IQR", "IQR"),
            "outlier_count": ("이상치 수", "Outliers"),
            "skewness": ("왜도", "Skewness"),
            "mode": ("최빈값", "Mode"),
            "bin_count": ("구간 수", "Bins"),
        }

        rows = []
        for stat_key, value in stats_to_display.items():
            label_ko, label_en = stat_labels.get(stat_key, (stat_key, stat_key))
            label = label_ko if is_ko else label_en

            # 값 포맷팅
            if isinstance(value, float):
                if stat_key == "change_percent":
                    formatted_value = self.format_percentage(value)
                elif stat_key in ("correlation", "r_squared"):
                    formatted_value = f"{value:.4f}"
                else:
                    formatted_value = self.format_number(value)
            elif isinstance(value, (list, tuple)):
                formatted_value = (
                    f"{self.format_number(value[0])} ~ {self.format_number(value[1])}"
                )
            elif isinstance(value, dict):
                # For percentage breakdown in pie charts
                formatted_items = [
                    f"{k}: {self.format_percentage(v)}" for k, v in value.items()
                ]
                formatted_value = ", ".join(formatted_items[:5])  # Limit display
                if len(value) > 5:
                    formatted_value += "..."
            else:
                formatted_value = str(value) if value is not None else "-"

            rows.append(
                f'<tr><td>{label}</td><td class="numeric">{formatted_value}</td></tr>'
            )

        stats_title = "통계" if is_ko else "Statistics"

        return f"""
            <div class="chart-statistics">
                <table class="data-table stats-table">
                    <thead><tr><th colspan="2">{stats_title}</th></tr></thead>
                    <tbody>{"".join(rows)}</tbody>
                </table>
            </div>"""

    def _render_visualizations(
        self, report_data: ReportData, options: ReportOptions
    ) -> str:
        """시각화 렌더링 - 통계 테이블 포함, description 제외"""
        is_ko = options.language == "ko"

        charts_html = []
        for chart in report_data.charts:
            img_html = ""
            if chart.image_base64:
                img_html = f'<img src="data:image/{chart.image_format};base64,{chart.image_base64}" alt="{html.escape(chart.title)}">'
            elif chart.image_bytes:
                import base64

                b64 = base64.b64encode(chart.image_bytes).decode("utf-8")
                img_html = f'<img src="data:image/{chart.image_format};base64,{b64}" alt="{html.escape(chart.title)}">'

            # 차트 통계 렌더링
            stats_html = self._render_chart_statistics(chart, options)

            charts_html.append(f"""
            <div class="chart-container">
                <h4>{html.escape(chart.title)}</h4>
                {img_html}
                {stats_html}
            </div>""")

        section_title = "시각화" if is_ko else "Visualizations"

        return f"""
<section id="visualizations" class="section">
    <h2>{section_title}</h2>
    <div class="charts-grid">
        {"".join(charts_html)}
    </div>
</section>"""

    def _render_comparison(
        self, report_data: ReportData, options: ReportOptions
    ) -> str:
        """비교 분석 렌더링"""
        is_ko = options.language == "ko"

        content_parts = []

        # Statistical Test Results
        if report_data.comparisons:
            tests_html = []
            for comp in report_data.comparisons:
                sig_class = "sig-none"
                sig_text = "Not Significant"
                if comp.p_value < 0.001:
                    sig_class = "sig-high"
                    sig_text = "*** Highly Significant"
                elif comp.p_value < 0.01:
                    sig_class = "sig-high"
                    sig_text = "** Very Significant"
                elif comp.p_value < 0.05:
                    sig_class = "sig-medium"
                    sig_text = "* Significant"

                effect_text = ""
                if comp.effect_size is not None:
                    effect_text = f'<span class="stat-item"><span class="label">Effect Size:</span><span class="value">{comp.effect_size:.3f} ({comp.effect_size_interpretation})</span></span>'

                tests_html.append(f"""
                <div class="test-result">
                    <div class="test-name">{html.escape(comp.test_type)}: {html.escape(comp.dataset_a_name)} vs {html.escape(comp.dataset_b_name)}</div>
                    <div class="stats-row">
                        <span class="stat-item"><span class="label">Column:</span><span class="value">{html.escape(comp.column)}</span></span>
                        <span class="stat-item"><span class="label">t-statistic:</span><span class="value">{comp.test_statistic:.4f}</span></span>
                        <span class="stat-item"><span class="label">p-value:</span><span class="value">{comp.p_value:.4f}</span></span>
                        {effect_text}
                    </div>
                    <p><span class="significance {sig_class}">{sig_text}</span></p>
                    {f'<p style="margin-top: 10px;">{html.escape(comp.interpretation)}</p>' if comp.interpretation else ""}
                </div>""")

            test_title = "통계 검정 결과" if is_ko else "Statistical Test Results"
            content_parts.append(f"""
            <h3>{test_title}</h3>
            {"".join(tests_html)}""")

        # Difference Analysis
        if report_data.differences:
            for diff in report_data.differences:
                pos_pct = diff.positive_percentage
                neg_pct = diff.negative_percentage
                neu_pct = diff.neutral_percentage

                diff_title = "차이 분석" if is_ko else "Difference Analysis"

                content_parts.append(f"""
            <h3>{diff_title}: {html.escape(diff.dataset_a_name)} vs {html.escape(diff.dataset_b_name)}</h3>
            <div class="diff-bar">
                <div class="positive" style="width: {pos_pct}%;" title="Positive: {pos_pct:.1f}%"></div>
                <div class="negative" style="width: {neg_pct}%;" title="Negative: {neg_pct:.1f}%"></div>
                <div class="neutral" style="width: {neu_pct}%;" title="Neutral: {neu_pct:.1f}%"></div>
            </div>
            <div class="diff-legend">
                <span><span class="dot" style="background: #22c55e;"></span> {"증가" if is_ko else "Positive"}: {pos_pct:.1f}% ({diff.positive_count})</span>
                <span><span class="dot" style="background: #ef4444;"></span> {"감소" if is_ko else "Negative"}: {neg_pct:.1f}% ({diff.negative_count})</span>
                <span><span class="dot" style="background: #94a3b8;"></span> {"변화없음" if is_ko else "No Change"}: {neu_pct:.1f}% ({diff.neutral_count})</span>
            </div>
            <div class="metrics-grid" style="margin-top: 20px;">
                <div class="metric-card">
                    <div class="label">{"총 차이" if is_ko else "Total Difference"}</div>
                    <div class="value">{self.format_number(diff.total_difference)}</div>
                </div>
                <div class="metric-card">
                    <div class="label">{"평균 차이" if is_ko else "Mean Difference"}</div>
                    <div class="value">{self.format_number(diff.mean_difference)}</div>
                </div>
                <div class="metric-card">
                    <div class="label">{"매칭 레코드" if is_ko else "Matched Records"}</div>
                    <div class="value">{self.format_number(diff.matched_records, 0)}</div>
                </div>
            </div>""")

                # Top differences table
                if diff.top_differences:
                    top_diff_title = "상위 차이" if is_ko else "Top Differences"
                    headers = [
                        "Key",
                        diff.value_column + " (A)",
                        diff.value_column + " (B)",
                        "Difference",
                        "Change %",
                    ]
                    header_html = "".join([f"<th>{h}</th>" for h in headers])

                    rows = []
                    for item in diff.top_differences[:10]:
                        change_class = (
                            "positive" if item.get("difference", 0) > 0 else "negative"
                        )
                        rows.append(f"""
                        <tr>
                            <td>{html.escape(str(item.get("key", "")))}</td>
                            <td class="numeric">{self.format_number(item.get("value_a"))}</td>
                            <td class="numeric">{self.format_number(item.get("value_b"))}</td>
                            <td class="numeric {change_class}">{self.format_number(item.get("difference"))}</td>
                            <td class="numeric {change_class}">{self.format_percentage(item.get("change_percent"))}</td>
                        </tr>""")

                    content_parts.append(f"""
            <h4>{top_diff_title}</h4>
            <table class="data-table">
                <thead><tr>{header_html}</tr></thead>
                <tbody>{"".join(rows)}</tbody>
            </table>""")

        section_title = "비교 분석" if is_ko else "Comparison Analysis"

        return f"""
<section id="comparison" class="section">
    <h2>{section_title}</h2>
    {"".join(content_parts)}
</section>"""

    def _render_tables(self, report_data: ReportData, options: ReportOptions) -> str:
        """데이터 테이블 렌더링"""
        is_ko = options.language == "ko"

        tables_html = []
        for table in report_data.tables:
            # 헤더
            header_html = "".join(
                [f"<th>{html.escape(col)}</th>" for col in table.columns]
            )

            # 행
            rows_html = []
            for row in table.rows:
                cells = []
                for i, cell in enumerate(row):
                    col_name = table.columns[i] if i < len(table.columns) else ""
                    col_format = table.column_formats.get(col_name, "text")

                    if col_format in ["integer", "float"]:
                        cell_html = f'<td class="numeric">{self.format_number(cell) if cell is not None else "-"}</td>'
                    else:
                        cell_html = f"<td>{html.escape(str(cell)) if cell is not None else '-'}</td>"
                    cells.append(cell_html)
                rows_html.append(f"<tr>{''.join(cells)}</tr>")

            # 페이지네이션 정보
            pagination = ""
            if table.total_rows > table.shown_rows:
                pagination = f'<p style="margin-top: 10px; font-size: 0.85rem; color: var(--text-secondary);">{"표시" if is_ko else "Showing"} {table.shown_rows} / {table.total_rows} {"행" if is_ko else "rows"}</p>'

            tables_html.append(f"""
            <div class="chart-container">
                <h4>{html.escape(table.title)}</h4>
                <table class="data-table">
                    <thead><tr>{header_html}</tr></thead>
                    <tbody>{"".join(rows_html)}</tbody>
                </table>
                {pagination}
            </div>""")

        section_title = "데이터 테이블" if is_ko else "Data Tables"

        return f"""
<section id="data-tables" class="section">
    <h2>{section_title}</h2>
    {"".join(tables_html)}
</section>"""

    def _render_appendix(self, report_data: ReportData, options: ReportOptions) -> str:
        """부록 렌더링"""
        is_ko = options.language == "ko"

        content_parts = []

        # Methodology
        if report_data.methodology_notes:
            method_title = "분석 방법론" if is_ko else "Methodology"
            items = "".join(
                [
                    f"<li>{html.escape(note)}</li>"
                    for note in report_data.methodology_notes
                ]
            )
            content_parts.append(f"""
            <h3>{method_title}</h3>
            <ul>{items}</ul>""")

        # Data Quality Notes
        if report_data.data_quality_notes:
            quality_title = "데이터 품질 노트" if is_ko else "Data Quality Notes"
            items = "".join(
                [
                    f"<li>{html.escape(note)}</li>"
                    for note in report_data.data_quality_notes
                ]
            )
            content_parts.append(f"""
            <h3>{quality_title}</h3>
            <ul>{items}</ul>""")

        if not content_parts:
            return ""

        section_title = "부록" if is_ko else "Appendix"

        return f"""
<section id="appendix" class="section">
    <h2>{section_title}</h2>
    {"".join(content_parts)}
</section>"""

    def _render_footer(self, report_data: ReportData, options: ReportOptions) -> str:
        """푸터 렌더링"""
        is_ko = options.language == "ko"

        generated_text = "생성일시" if is_ko else "Generated on"
        powered_text = "Powered by" if not is_ko else ""

        return f"""
<footer class="report-footer">
    <p>{generated_text}: {report_data.metadata.created_at.strftime("%Y-%m-%d %H:%M:%S")}</p>
    <p>{powered_text} <a href="#">Data Graph Studio</a> v{report_data.metadata.version}</p>
</footer>"""

    def _get_scripts(self, options: ReportOptions) -> str:
        """JavaScript 스크립트"""
        return """
<script>
// Collapsible sections
document.querySelectorAll('.collapsible').forEach(function(element) {
    element.addEventListener('click', function() {
        this.classList.toggle('collapsed');
        var content = this.nextElementSibling;
        if (content.classList.contains('collapsible-content')) {
            content.classList.toggle('collapsed');
        }
    });
});

// Print button (if needed)
function printReport() {
    window.print();
}
</script>"""
