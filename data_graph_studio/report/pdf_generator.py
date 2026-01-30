"""
PDF Report Generator
PDF 레포트 생성기

Uses WeasyPrint (preferred) or FPDF2 as fallback.
Supports page headers/footers, table of contents, and Korean fonts.
"""

from typing import Optional, List, Dict, Any, Union
from pathlib import Path
from datetime import datetime
import io
import base64
import logging

from data_graph_studio.core.report import (
    ReportGenerator,
    ReportData,
    ReportOptions,
    ReportTemplate,
    ReportTheme,
    PageSize,
    PageOrientation,
)

logger = logging.getLogger(__name__)


# Check available PDF libraries
WEASYPRINT_AVAILABLE = False
FPDF_AVAILABLE = False

try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    WEASYPRINT_AVAILABLE = True
except ImportError:
    pass

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    pass


class PDFReportGenerator(ReportGenerator):
    """PDF 레포트 생성기"""

    # Page sizes in mm
    PAGE_SIZES = {
        PageSize.A4: (210, 297),
        PageSize.LETTER: (216, 279),
        PageSize.LEGAL: (216, 356),
        PageSize.A3: (297, 420),
    }

    def generate(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> bytes:
        """PDF 레포트 생성"""
        if WEASYPRINT_AVAILABLE:
            return self._generate_with_weasyprint(report_data, options)
        elif FPDF_AVAILABLE:
            return self._generate_with_fpdf(report_data, options)
        else:
            raise ImportError(
                "No PDF library available. Install 'weasyprint' or 'fpdf2':\n"
                "  pip install weasyprint  # Recommended, requires system dependencies\n"
                "  pip install fpdf2       # Pure Python alternative"
            )

    def _generate_with_weasyprint(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> bytes:
        """WeasyPrint로 PDF 생성"""
        # HTML 레포트 생성기 사용
        from data_graph_studio.report.html_generator import HTMLReportGenerator

        html_generator = HTMLReportGenerator(self.template)
        html_content = html_generator._build_html(report_data, options)

        # PDF 특화 CSS 추가
        pdf_css = self._get_pdf_css(options)

        # Font configuration
        font_config = FontConfiguration()

        # HTML to PDF
        html_doc = HTML(string=html_content)
        css_doc = CSS(string=pdf_css, font_config=font_config)

        pdf_bytes = html_doc.write_pdf(
            stylesheets=[css_doc],
            font_config=font_config
        )

        return pdf_bytes

    def _generate_with_fpdf(
        self,
        report_data: ReportData,
        options: ReportOptions
    ) -> bytes:
        """FPDF2로 PDF 생성"""
        # 페이지 설정
        page_size = self.PAGE_SIZES.get(options.page_size, (210, 297))
        orientation = 'P' if options.orientation == PageOrientation.PORTRAIT else 'L'

        pdf = FPDF(orientation=orientation, unit='mm', format=page_size)
        pdf.set_auto_page_break(auto=True, margin=15)

        # 마진 설정
        margins = options.margins
        pdf.set_margins(
            margins.get('left', 20),
            margins.get('top', 20),
            margins.get('right', 20)
        )

        # 폰트 설정 (기본 폰트 사용, 한글 지원을 위해서는 폰트 추가 필요)
        pdf.add_page()

        # 컬러 설정
        primary_color = self._hex_to_rgb(self.template.primary_color)

        # 헤더
        self._add_fpdf_header(pdf, report_data, options, primary_color)

        # Executive Summary
        if options.include_executive_summary:
            self._add_fpdf_executive_summary(pdf, report_data, options, primary_color)

        # Data Overview
        if options.include_data_overview:
            self._add_fpdf_data_overview(pdf, report_data, options, primary_color)

        # Statistics
        if options.include_statistics:
            self._add_fpdf_statistics(pdf, report_data, options, primary_color)

        # Visualizations
        if options.include_visualizations and report_data.charts:
            self._add_fpdf_visualizations(pdf, report_data, options, primary_color)

        # Comparison
        if options.include_comparison and report_data.is_multi_dataset():
            self._add_fpdf_comparison(pdf, report_data, options, primary_color)

        # Tables
        if options.include_tables and report_data.tables:
            self._add_fpdf_tables(pdf, report_data, options, primary_color)

        # 바이트로 반환
        return bytes(pdf.output())

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """HEX를 RGB 튜플로 변환"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _add_fpdf_header(
        self,
        pdf: "FPDF",
        report_data: ReportData,
        options: ReportOptions,
        primary_color: tuple
    ):
        """FPDF 헤더 추가"""
        # 배경 박스
        pdf.set_fill_color(*primary_color)
        pdf.rect(10, 10, pdf.w - 20, 50, 'F')

        # 제목
        pdf.set_font('Helvetica', 'B', 24)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 20)
        pdf.cell(pdf.w - 20, 10, report_data.metadata.title, align='C')

        # 부제목
        if report_data.metadata.subtitle:
            pdf.set_font('Helvetica', '', 14)
            pdf.set_xy(10, 32)
            pdf.cell(pdf.w - 20, 8, report_data.metadata.subtitle, align='C')

        # 메타 정보
        pdf.set_font('Helvetica', '', 10)
        pdf.set_xy(10, 45)
        meta_text = f"Generated: {report_data.metadata.created_at.strftime('%Y-%m-%d %H:%M')}"
        if report_data.metadata.author:
            meta_text += f" | Author: {report_data.metadata.author}"
        pdf.cell(pdf.w - 20, 8, meta_text, align='C')

        # 본문 시작 위치로 이동
        pdf.set_text_color(0, 0, 0)
        pdf.set_y(70)

    def _add_fpdf_section_title(
        self,
        pdf: "FPDF",
        title: str,
        primary_color: tuple
    ):
        """섹션 제목 추가"""
        pdf.ln(10)
        pdf.set_font('Helvetica', 'B', 16)
        pdf.set_text_color(*primary_color)
        pdf.cell(0, 10, title, ln=True)
        pdf.set_draw_color(*primary_color)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 60, pdf.get_y())
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

    def _add_fpdf_executive_summary(
        self,
        pdf: "FPDF",
        report_data: ReportData,
        options: ReportOptions,
        primary_color: tuple
    ):
        """Executive Summary 추가"""
        is_ko = options.language == 'ko'
        title = "Executive Summary" if not is_ko else "Executive Summary"
        self._add_fpdf_section_title(pdf, title, primary_color)

        # 메트릭 카드
        pdf.set_font('Helvetica', '', 11)
        metrics = [
            ("Total Rows", self.format_number(report_data.get_total_rows(), 0)),
            ("Datasets", str(len(report_data.datasets))),
        ]
        if report_data.datasets:
            metrics.append(("Columns", str(report_data.datasets[0].column_count)))
        if report_data.charts:
            metrics.append(("Charts", str(len(report_data.charts))))

        # 메트릭 박스 그리기
        box_width = 40
        box_height = 20
        x_start = 20
        y_start = pdf.get_y()

        for i, (label, value) in enumerate(metrics):
            x = x_start + (i * (box_width + 10))
            if x + box_width > pdf.w - 20:
                y_start += box_height + 5
                x = x_start
                i = 0

            pdf.set_fill_color(245, 247, 250)
            pdf.rect(x, y_start, box_width, box_height, 'F')

            pdf.set_font('Helvetica', '', 8)
            pdf.set_xy(x, y_start + 2)
            pdf.cell(box_width, 5, label, align='C')

            pdf.set_font('Helvetica', 'B', 12)
            pdf.set_text_color(*primary_color)
            pdf.set_xy(x, y_start + 9)
            pdf.cell(box_width, 8, value, align='C')
            pdf.set_text_color(0, 0, 0)

        pdf.set_y(y_start + box_height + 10)

        # Key Findings
        if report_data.key_findings:
            pdf.set_font('Helvetica', 'B', 12)
            pdf.cell(0, 8, "Key Findings:", ln=True)
            pdf.set_font('Helvetica', '', 10)
            for finding in report_data.key_findings:
                pdf.cell(5)
                pdf.cell(0, 6, f"- {finding}", ln=True)

    def _add_fpdf_data_overview(
        self,
        pdf: "FPDF",
        report_data: ReportData,
        options: ReportOptions,
        primary_color: tuple
    ):
        """Data Overview 추가"""
        is_ko = options.language == 'ko'
        title = "Data Overview" if not is_ko else "Data Overview"
        self._add_fpdf_section_title(pdf, title, primary_color)

        for ds in report_data.datasets:
            pdf.set_font('Helvetica', 'B', 11)
            pdf.cell(0, 8, ds.name, ln=True)

            pdf.set_font('Helvetica', '', 10)
            info_lines = [
                f"Rows: {self.format_number(ds.row_count, 0)}",
                f"Columns: {ds.column_count}",
                f"Memory: {self.format_bytes(ds.memory_bytes)}",
            ]
            for line in info_lines:
                pdf.cell(10)
                pdf.cell(0, 5, line, ln=True)
            pdf.ln(3)

    def _add_fpdf_statistics(
        self,
        pdf: "FPDF",
        report_data: ReportData,
        options: ReportOptions,
        primary_color: tuple
    ):
        """Statistics 추가"""
        is_ko = options.language == 'ko'
        title = "Statistical Summary" if not is_ko else "Statistical Summary"
        self._add_fpdf_section_title(pdf, title, primary_color)

        for dataset_id, stats_list in report_data.statistics.items():
            if not stats_list:
                continue

            # 데이터셋 이름 찾기
            dataset_name = dataset_id
            for ds in report_data.datasets:
                if ds.id == dataset_id:
                    dataset_name = ds.name
                    break

            pdf.set_font('Helvetica', 'B', 11)
            pdf.cell(0, 8, dataset_name, ln=True)

            # 테이블 헤더
            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_fill_color(*primary_color)
            pdf.set_text_color(255, 255, 255)

            headers = ['Column', 'Count', 'Mean', 'Median', 'Std', 'Min', 'Max']
            col_widths = [35, 20, 25, 25, 25, 25, 25]

            for i, header in enumerate(headers):
                pdf.cell(col_widths[i], 7, header, border=1, fill=True, align='C')
            pdf.ln()

            # 테이블 데이터
            pdf.set_font('Helvetica', '', 8)
            pdf.set_text_color(0, 0, 0)

            for stat in stats_list[:20]:  # 최대 20행
                pdf.cell(col_widths[0], 6, stat.column[:15], border=1)
                pdf.cell(col_widths[1], 6, str(stat.count), border=1, align='R')
                pdf.cell(col_widths[2], 6, self.format_number(stat.mean, 2), border=1, align='R')
                pdf.cell(col_widths[3], 6, self.format_number(stat.median, 2), border=1, align='R')
                pdf.cell(col_widths[4], 6, self.format_number(stat.std, 2), border=1, align='R')
                pdf.cell(col_widths[5], 6, self.format_number(stat.min, 2), border=1, align='R')
                pdf.cell(col_widths[6], 6, self.format_number(stat.max, 2), border=1, align='R')
                pdf.ln()

            pdf.ln(5)

    def _add_fpdf_visualizations(
        self,
        pdf: "FPDF",
        report_data: ReportData,
        options: ReportOptions,
        primary_color: tuple
    ):
        """Visualizations 추가"""
        is_ko = options.language == 'ko'
        title = "Visualizations" if not is_ko else "Visualizations"
        self._add_fpdf_section_title(pdf, title, primary_color)

        for chart in report_data.charts:
            # 새 페이지 확인
            if pdf.get_y() > pdf.h - 100:
                pdf.add_page()

            pdf.set_font('Helvetica', 'B', 11)
            pdf.cell(0, 8, chart.title, ln=True)

            # 이미지 삽입
            if chart.image_bytes:
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=f'.{chart.image_format}', delete=False) as tmp:
                        tmp.write(chart.image_bytes)
                        tmp_path = tmp.name

                    # 이미지 크기 계산 (페이지 폭의 80%)
                    img_width = (pdf.w - 40) * 0.8
                    pdf.image(tmp_path, x=(pdf.w - img_width) / 2, w=img_width)

                    # 임시 파일 삭제
                    import os
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to add chart image: {e}")
                    pdf.set_font('Helvetica', 'I', 10)
                    pdf.cell(0, 8, "[Chart image not available]", ln=True)

            pdf.ln(5)

    def _add_fpdf_comparison(
        self,
        pdf: "FPDF",
        report_data: ReportData,
        options: ReportOptions,
        primary_color: tuple
    ):
        """Comparison Analysis 추가"""
        is_ko = options.language == 'ko'
        title = "Comparison Analysis" if not is_ko else "Comparison Analysis"
        self._add_fpdf_section_title(pdf, title, primary_color)

        # Statistical Test Results
        if report_data.comparisons:
            pdf.set_font('Helvetica', 'B', 11)
            pdf.cell(0, 8, "Statistical Test Results", ln=True)

            for comp in report_data.comparisons:
                pdf.set_font('Helvetica', '', 10)
                pdf.cell(0, 6, f"{comp.test_type}: {comp.dataset_a_name} vs {comp.dataset_b_name}", ln=True)
                pdf.cell(10)
                pdf.cell(0, 5, f"Column: {comp.column}", ln=True)
                pdf.cell(10)
                pdf.cell(0, 5, f"t-statistic: {comp.test_statistic:.4f}, p-value: {comp.p_value:.4f}", ln=True)

                sig_text = "Not Significant"
                if comp.p_value < 0.001:
                    sig_text = "*** Highly Significant"
                elif comp.p_value < 0.01:
                    sig_text = "** Very Significant"
                elif comp.p_value < 0.05:
                    sig_text = "* Significant"

                pdf.cell(10)
                pdf.set_font('Helvetica', 'B', 10)
                pdf.cell(0, 5, sig_text, ln=True)
                pdf.ln(3)

        # Difference Analysis
        for diff in report_data.differences:
            pdf.set_font('Helvetica', 'B', 11)
            pdf.cell(0, 8, f"Difference: {diff.dataset_a_name} vs {diff.dataset_b_name}", ln=True)

            pdf.set_font('Helvetica', '', 10)
            pdf.cell(10)
            pdf.cell(0, 5, f"Positive (A > B): {diff.positive_count} ({diff.positive_percentage:.1f}%)", ln=True)
            pdf.cell(10)
            pdf.cell(0, 5, f"Negative (A < B): {diff.negative_count} ({diff.negative_percentage:.1f}%)", ln=True)
            pdf.cell(10)
            pdf.cell(0, 5, f"No Change: {diff.neutral_count} ({diff.neutral_percentage:.1f}%)", ln=True)
            pdf.ln(3)

    def _add_fpdf_tables(
        self,
        pdf: "FPDF",
        report_data: ReportData,
        options: ReportOptions,
        primary_color: tuple
    ):
        """Data Tables 추가"""
        is_ko = options.language == 'ko'
        title = "Data Tables" if not is_ko else "Data Tables"
        self._add_fpdf_section_title(pdf, title, primary_color)

        for table in report_data.tables:
            if pdf.get_y() > pdf.h - 60:
                pdf.add_page()

            pdf.set_font('Helvetica', 'B', 11)
            pdf.cell(0, 8, table.title, ln=True)

            # 테이블 헤더
            pdf.set_font('Helvetica', 'B', 7)
            pdf.set_fill_color(*primary_color)
            pdf.set_text_color(255, 255, 255)

            num_cols = len(table.columns)
            col_width = min(30, (pdf.w - 40) / num_cols)

            for col in table.columns[:6]:  # 최대 6컬럼
                pdf.cell(col_width, 6, col[:10], border=1, fill=True, align='C')
            pdf.ln()

            # 테이블 데이터
            pdf.set_font('Helvetica', '', 7)
            pdf.set_text_color(0, 0, 0)

            for row in table.rows[:15]:  # 최대 15행
                for i, cell in enumerate(row[:6]):
                    cell_text = str(cell) if cell is not None else "-"
                    if len(cell_text) > 10:
                        cell_text = cell_text[:8] + ".."
                    pdf.cell(col_width, 5, cell_text, border=1, align='C')
                pdf.ln()

            if table.total_rows > table.shown_rows:
                pdf.set_font('Helvetica', 'I', 8)
                pdf.cell(0, 5, f"Showing {min(15, table.shown_rows)} of {table.total_rows} rows", ln=True)

            pdf.ln(5)

    def _get_pdf_css(self, options: ReportOptions) -> str:
        """PDF 전용 CSS"""
        page_size = options.page_size.value
        orientation = options.orientation.value

        margins = options.margins
        margin_top = margins.get('top', 2.54)
        margin_bottom = margins.get('bottom', 2.54)
        margin_left = margins.get('left', 2.54)
        margin_right = margins.get('right', 2.54)

        return f'''
@page {{
    size: {page_size} {orientation};
    margin: {margin_top}cm {margin_right}cm {margin_bottom}cm {margin_left}cm;

    @top-center {{
        content: "{options.header_text or ''}";
        font-size: 9pt;
        color: #666;
    }}

    @bottom-center {{
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: #666;
    }}

    @bottom-right {{
        content: "{options.footer_text or 'Data Graph Studio'}";
        font-size: 9pt;
        color: #666;
    }}
}}

body {{
    font-size: 10pt;
}}

.report-container {{
    max-width: none;
    padding: 0;
}}

.section {{
    page-break-inside: avoid;
}}

.chart-container {{
    page-break-inside: avoid;
}}

.data-table {{
    font-size: 8pt;
}}

/* Watermark */
''' + (f'''
body::before {{
    content: "{options.watermark}";
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(-45deg);
    font-size: 72pt;
    color: rgba(0, 0, 0, 0.05);
    pointer-events: none;
    z-index: 1000;
}}
''' if options.watermark else '') + '''
'''
