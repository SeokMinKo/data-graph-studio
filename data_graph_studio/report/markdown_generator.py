"""
Markdown Report Generator
마크다운 레포트 생성기

Generates clean, readable Markdown reports suitable for:
- GitHub/GitLab README
- Documentation systems (MkDocs, Docusaurus)
- Note-taking apps (Obsidian, Notion)
- Converting to other formats
"""

import base64

from data_graph_studio.core.report import (
    ReportGenerator,
    ReportData,
    ReportOptions,
)


class MarkdownReportGenerator(ReportGenerator):
    """Markdown 레포트 생성기"""

    def generate(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> bytes:
        """Markdown 레포트 생성"""
        md_content = self._build_markdown(report_data, options)
        return md_content.encode('utf-8')

    def _build_markdown(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """마크다운 문서 빌드"""
        sections = []

        # Header
        sections.append(self._render_header(report_data, options))

        # Table of Contents
        sections.append(self._render_toc(report_data, options))

        # Executive Summary
        if options.include_executive_summary:
            sections.append(self._render_executive_summary(report_data, options))

        # Data Overview
        if options.include_data_overview:
            sections.append(self._render_data_overview(report_data, options))

        # Statistics
        if options.include_statistics:
            sections.append(self._render_statistics(report_data, options))

        # Visualizations
        if options.include_visualizations and report_data.charts:
            sections.append(self._render_visualizations(report_data, options))

        # Comparison Analysis
        if options.include_comparison and report_data.is_multi_dataset():
            sections.append(self._render_comparison(report_data, options))

        # Data Tables
        if options.include_tables and report_data.tables:
            sections.append(self._render_tables(report_data, options))

        # Appendix
        if options.include_appendix:
            sections.append(self._render_appendix(report_data, options))

        # Footer
        sections.append(self._render_footer(report_data, options))

        return '\n\n'.join(filter(None, sections))

    def _render_header(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """헤더 렌더링"""
        meta = report_data.metadata
        lines = []

        # Title
        lines.append(f"# {meta.title}")

        # Subtitle
        if meta.subtitle:
            lines.append(f"*{meta.subtitle}*")

        lines.append("")

        # Metadata badge line
        badges = []
        badges.append(f"📅 {meta.created_at.strftime('%Y-%m-%d %H:%M')}")
        if meta.author:
            badges.append(f"👤 {meta.author}")
        badges.append(f"📊 Data Graph Studio v{meta.version}")

        lines.append(" | ".join(badges))

        # Tags
        if meta.tags:
            tags_str = " ".join([f"`{tag}`" for tag in meta.tags])
            lines.append(f"\n**Tags:** {tags_str}")

        lines.append("")
        lines.append("---")

        return '\n'.join(lines)

    def _render_toc(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """목차 렌더링"""
        is_ko = options.language == 'ko'
        lines = []

        toc_title = "## 목차" if is_ko else "## Table of Contents"
        lines.append(toc_title)
        lines.append("")

        toc_items = []

        if options.include_executive_summary:
            toc_items.append(("요약" if is_ko else "Executive Summary", "executive-summary"))

        if options.include_data_overview:
            toc_items.append(("데이터 개요" if is_ko else "Data Overview", "data-overview"))

        if options.include_statistics:
            toc_items.append(("통계 요약" if is_ko else "Statistical Summary", "statistical-summary"))

        if options.include_visualizations and report_data.charts:
            toc_items.append(("시각화" if is_ko else "Visualizations", "visualizations"))

        if options.include_comparison and report_data.is_multi_dataset():
            toc_items.append(("비교 분석" if is_ko else "Comparison Analysis", "comparison-analysis"))

        if options.include_tables and report_data.tables:
            toc_items.append(("데이터 테이블" if is_ko else "Data Tables", "data-tables"))

        if options.include_appendix:
            toc_items.append(("부록" if is_ko else "Appendix", "appendix"))

        for title, anchor in toc_items:
            lines.append(f"- [{title}](#{anchor})")

        return '\n'.join(lines)

    def _render_executive_summary(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """Executive Summary 렌더링"""
        is_ko = options.language == 'ko'
        lines = []

        title = "## 요약" if is_ko else "## Executive Summary"
        lines.append(title)
        lines.append("")

        # Key Metrics
        metrics = []
        metrics.append(f"| {'지표' if is_ko else 'Metric'} | {'값' if is_ko else 'Value'} |")
        metrics.append("|:---|---:|")
        metrics.append(f"| {'총 행 수' if is_ko else 'Total Rows'} | {self.format_number(report_data.get_total_rows(), 0)} |")
        metrics.append(f"| {'데이터셋' if is_ko else 'Datasets'} | {len(report_data.datasets)} |")

        if report_data.datasets:
            metrics.append(f"| {'컬럼 수' if is_ko else 'Columns'} | {report_data.datasets[0].column_count} |")

        if report_data.charts:
            metrics.append(f"| {'차트' if is_ko else 'Charts'} | {len(report_data.charts)} |")

        lines.extend(metrics)
        lines.append("")

        # Key Findings
        if report_data.key_findings:
            findings_title = "### 핵심 발견 사항" if is_ko else "### Key Findings"
            lines.append(findings_title)
            lines.append("")
            for finding in report_data.key_findings:
                lines.append(f"- ✅ {finding}")
            lines.append("")

        # Recommendations
        if report_data.recommendations:
            rec_title = "### 권장 사항" if is_ko else "### Recommendations"
            lines.append(rec_title)
            lines.append("")
            for rec in report_data.recommendations:
                lines.append(f"- 💡 {rec}")

        return '\n'.join(lines)

    def _render_data_overview(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """Data Overview 렌더링"""
        is_ko = options.language == 'ko'
        lines = []

        title = "## 데이터 개요" if is_ko else "## Data Overview"
        lines.append(title)
        lines.append("")

        for ds in report_data.datasets:
            lines.append(f"### {ds.name}")
            lines.append("")

            # Info table
            lines.append(f"| {'항목' if is_ko else 'Property'} | {'값' if is_ko else 'Value'} |")
            lines.append("|:---|:---|")

            if ds.file_path:
                lines.append(f"| {'파일' if is_ko else 'File'} | `{ds.file_path.split('/')[-1]}` |")

            lines.append(f"| {'행 수' if is_ko else 'Rows'} | {self.format_number(ds.row_count, 0)} |")
            lines.append(f"| {'컬럼 수' if is_ko else 'Columns'} | {ds.column_count} |")
            lines.append(f"| {'메모리' if is_ko else 'Memory'} | {self.format_bytes(ds.memory_bytes)} |")

            if ds.date_range:
                date_str = f"{ds.date_range['min']} ~ {ds.date_range['max']}"
                lines.append(f"| {'날짜 범위' if is_ko else 'Date Range'} | {date_str} |")

            lines.append("")

            # Column types summary
            if ds.column_types:
                type_counts = {}
                for col, dtype in ds.column_types.items():
                    type_counts[dtype] = type_counts.get(dtype, 0) + 1

                type_summary = ", ".join([f"{t}: {c}" for t, c in sorted(type_counts.items())])
                lines.append(f"**{'데이터 타입' if is_ko else 'Data Types'}:** {type_summary}")
                lines.append("")

            # Missing values
            if ds.missing_values:
                missing_title = "#### 결측값" if is_ko else "#### Missing Values"
                lines.append(missing_title)
                lines.append("")
                lines.append(f"| {'컬럼' if is_ko else 'Column'} | {'개수' if is_ko else 'Count'} |")
                lines.append("|:---|---:|")
                for col, count in list(ds.missing_values.items())[:10]:
                    lines.append(f"| {col} | {count} |")
                if len(ds.missing_values) > 10:
                    lines.append(f"| ... | ({len(ds.missing_values) - 10} more) |")
                lines.append("")

        return '\n'.join(lines)

    def _render_statistics(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """Statistics 렌더링"""
        is_ko = options.language == 'ko'
        lines = []

        title = "## 통계 요약" if is_ko else "## Statistical Summary"
        lines.append(title)
        lines.append("")

        for dataset_id, stats_list in report_data.statistics.items():
            if not stats_list:
                continue

            # Find dataset name
            dataset_name = dataset_id
            for ds in report_data.datasets:
                if ds.id == dataset_id:
                    dataset_name = ds.name
                    break

            lines.append(f"### {dataset_name}")
            lines.append("")

            # Statistics table
            headers = ["Column", "Count", "Mean", "Median", "Std", "Min", "Max", "Q1", "Q3"]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|:---|" + "|".join(["---:" for _ in range(len(headers) - 1)]) + "|")

            for stat in stats_list[:30]:
                row = [
                    stat.column[:20],
                    str(stat.count),
                    self.format_number(stat.mean, 2),
                    self.format_number(stat.median, 2),
                    self.format_number(stat.std, 2),
                    self.format_number(stat.min, 2),
                    self.format_number(stat.max, 2),
                    self.format_number(stat.q1, 2),
                    self.format_number(stat.q3, 2),
                ]
                lines.append("| " + " | ".join(row) + " |")

            if len(stats_list) > 30:
                lines.append(f"\n*... and {len(stats_list) - 30} more columns*")

            lines.append("")

        return '\n'.join(lines)

    def _render_visualizations(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """Visualizations 렌더링"""
        is_ko = options.language == 'ko'
        lines = []

        title = "## 시각화" if is_ko else "## Visualizations"
        lines.append(title)
        lines.append("")

        for chart in report_data.charts:
            lines.append(f"### {chart.title}")
            lines.append("")

            # Chart image (if base64, embed as data URL)
            if chart.image_base64:
                lines.append(f"![{chart.title}](data:image/{chart.image_format};base64,{chart.image_base64})")
            elif chart.image_bytes:
                b64 = base64.b64encode(chart.image_bytes).decode('utf-8')
                lines.append(f"![{chart.title}](data:image/{chart.image_format};base64,{b64})")
            else:
                lines.append(f"*[Chart image: {chart.title}]*")

            lines.append("")

            # Description
            if chart.description:
                lines.append(f"*{chart.description}*")
                lines.append("")

            # Chart metadata
            metadata = []
            if chart.chart_type:
                metadata.append(f"Type: {chart.chart_type}")
            if chart.x_column:
                metadata.append(f"X: {chart.x_column}")
            if chart.y_column:
                metadata.append(f"Y: {chart.y_column}")
            if chart.group_column:
                metadata.append(f"Group: {chart.group_column}")

            if metadata:
                lines.append(f"> {' | '.join(metadata)}")
                lines.append("")

        return '\n'.join(lines)

    def _render_comparison(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """Comparison Analysis 렌더링"""
        is_ko = options.language == 'ko'
        lines = []

        title = "## 비교 분석" if is_ko else "## Comparison Analysis"
        lines.append(title)
        lines.append("")

        # Statistical Test Results
        if report_data.comparisons:
            test_title = "### 통계 검정 결과" if is_ko else "### Statistical Test Results"
            lines.append(test_title)
            lines.append("")

            for comp in report_data.comparisons:
                lines.append(f"#### {comp.test_type}: {comp.dataset_a_name} vs {comp.dataset_b_name}")
                lines.append("")

                # Results table
                lines.append(f"| {'항목' if is_ko else 'Metric'} | {'값' if is_ko else 'Value'} |")
                lines.append("|:---|:---|")
                lines.append(f"| Column | {comp.column} |")
                lines.append(f"| Test Statistic | {comp.test_statistic:.4f} |")
                lines.append(f"| p-value | {comp.p_value:.4f} |")

                if comp.effect_size is not None:
                    lines.append(f"| Effect Size | {comp.effect_size:.3f} ({comp.effect_size_interpretation}) |")

                # Significance
                sig_emoji = "⚪"
                sig_text = "Not Significant"
                if comp.p_value < 0.001:
                    sig_emoji = "🔴"
                    sig_text = "*** Highly Significant (p < 0.001)"
                elif comp.p_value < 0.01:
                    sig_emoji = "🟠"
                    sig_text = "** Very Significant (p < 0.01)"
                elif comp.p_value < 0.05:
                    sig_emoji = "🟡"
                    sig_text = "* Significant (p < 0.05)"

                lines.append(f"| Significance | {sig_emoji} {sig_text} |")
                lines.append("")

                if comp.interpretation:
                    lines.append(f"> 💬 {comp.interpretation}")
                    lines.append("")

        # Difference Analysis
        if report_data.differences:
            diff_title = "### 차이 분석" if is_ko else "### Difference Analysis"
            lines.append(diff_title)
            lines.append("")

            for diff in report_data.differences:
                lines.append(f"#### {diff.dataset_a_name} vs {diff.dataset_b_name}")
                lines.append("")

                # Summary table
                lines.append(f"| {'구분' if is_ko else 'Category'} | {'개수' if is_ko else 'Count'} | {'비율' if is_ko else 'Percentage'} |")
                lines.append("|:---|---:|---:|")
                lines.append(f"| 🟢 {'증가 (A > B)' if is_ko else 'Positive (A > B)'} | {diff.positive_count} | {diff.positive_percentage:.1f}% |")
                lines.append(f"| 🔴 {'감소 (A < B)' if is_ko else 'Negative (A < B)'} | {diff.negative_count} | {diff.negative_percentage:.1f}% |")
                lines.append(f"| ⚪ {'변화없음' if is_ko else 'No Change'} | {diff.neutral_count} | {diff.neutral_percentage:.1f}% |")
                lines.append("")

                # Key metrics
                lines.append(f"- **{'총 차이' if is_ko else 'Total Difference'}:** {self.format_number(diff.total_difference)}")
                lines.append(f"- **{'평균 차이' if is_ko else 'Mean Difference'}:** {self.format_number(diff.mean_difference)}")
                lines.append(f"- **{'매칭 레코드' if is_ko else 'Matched Records'}:** {self.format_number(diff.matched_records, 0)}")
                lines.append("")

                # Top differences
                if diff.top_differences:
                    top_title = "**상위 차이:**" if is_ko else "**Top Differences:**"
                    lines.append(top_title)
                    lines.append("")
                    lines.append("| Key | Value (A) | Value (B) | Difference | Change % |")
                    lines.append("|:---|---:|---:|---:|---:|")

                    for item in diff.top_differences[:10]:
                        key = str(item.get('key', ''))[:20]
                        val_a = self.format_number(item.get('value_a'))
                        val_b = self.format_number(item.get('value_b'))
                        diff_val = self.format_number(item.get('difference'))
                        change_pct = self.format_percentage(item.get('change_percent'))
                        lines.append(f"| {key} | {val_a} | {val_b} | {diff_val} | {change_pct} |")

                    lines.append("")

        return '\n'.join(lines)

    def _render_tables(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """Data Tables 렌더링"""
        is_ko = options.language == 'ko'
        lines = []

        title = "## 데이터 테이블" if is_ko else "## Data Tables"
        lines.append(title)
        lines.append("")

        for table in report_data.tables:
            lines.append(f"### {table.title}")
            lines.append("")

            if table.description:
                lines.append(f"*{table.description}*")
                lines.append("")

            # Limit columns for readability
            max_cols = 8
            display_cols = table.columns[:max_cols]
            display_rows = table.rows[:20]

            # Table header
            lines.append("| " + " | ".join(display_cols) + " |")
            lines.append("|" + "|".join(["---" for _ in display_cols]) + "|")

            # Table rows
            for row in display_rows:
                formatted_cells = []
                for i, cell in enumerate(row[:max_cols]):
                    cell_str = str(cell) if cell is not None else "-"
                    if len(cell_str) > 25:
                        cell_str = cell_str[:22] + "..."
                    formatted_cells.append(cell_str)
                lines.append("| " + " | ".join(formatted_cells) + " |")

            # Pagination info
            truncated = []
            if len(table.columns) > max_cols:
                truncated.append(f"{len(table.columns) - max_cols} more columns")
            if table.total_rows > 20:
                truncated.append(f"{table.total_rows - 20} more rows")

            if truncated:
                lines.append(f"\n*({', '.join(truncated)} not shown)*")

            lines.append("")

        return '\n'.join(lines)

    def _render_appendix(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """Appendix 렌더링"""
        is_ko = options.language == 'ko'
        lines = []

        if not report_data.methodology_notes and not report_data.data_quality_notes:
            return ""

        title = "## 부록" if is_ko else "## Appendix"
        lines.append(title)
        lines.append("")

        # Methodology
        if report_data.methodology_notes:
            method_title = "### 분석 방법론" if is_ko else "### Methodology"
            lines.append(method_title)
            lines.append("")
            for note in report_data.methodology_notes:
                lines.append(f"- {note}")
            lines.append("")

        # Data Quality Notes
        if report_data.data_quality_notes:
            quality_title = "### 데이터 품질 노트" if is_ko else "### Data Quality Notes"
            lines.append(quality_title)
            lines.append("")
            for note in report_data.data_quality_notes:
                lines.append(f"- {note}")
            lines.append("")

        return '\n'.join(lines)

    def _render_footer(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> str:
        """Footer 렌더링"""
        is_ko = options.language == 'ko'
        lines = []

        lines.append("---")
        lines.append("")

        generated_text = "생성일시" if is_ko else "Generated"
        powered_text = "Powered by" if not is_ko else ""

        lines.append(f"*{generated_text}: {report_data.metadata.created_at.strftime('%Y-%m-%d %H:%M:%S')}*")
        if powered_text:
            lines.append(f"*{powered_text} [Data Graph Studio](https://github.com/SeokMinKo/data-graph-studio) v{report_data.metadata.version}*")
        else:
            lines.append(f"*[Data Graph Studio](https://github.com/SeokMinKo/data-graph-studio) v{report_data.metadata.version}*")

        return '\n'.join(lines)
