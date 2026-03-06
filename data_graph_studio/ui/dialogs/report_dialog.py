"""
Report Generation Dialog
레포트 생성 다이얼로그

Provides UI for configuring and generating reports.
"""

from pathlib import Path
import logging
import tempfile


from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QTabWidget,
    QWidget,
    QFileDialog,
    QProgressDialog,
    QMessageBox,
    QSpinBox,
    QButtonGroup,
    QRadioButton,
)
from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QDesktopServices

from data_graph_studio.core.report import (
    ReportFormat,
    ReportTheme,
    PageSize,
    PageOrientation,
    ReportOptions,
    ReportData,
)

logger = logging.getLogger(__name__)


class ReportGeneratorThread(QThread):
    """레포트 생성 작업 스레드"""

    finished = Signal(bool, str)  # success, message/path
    progress = Signal(int, str)  # percentage, status

    def __init__(
        self,
        report_data: ReportData,
        options: ReportOptions,
        output_path: str,
        parent=None,
    ):
        super().__init__(parent)
        self.report_data = report_data
        self.options = options
        self.output_path = output_path

    def run(self):
        try:
            self.progress.emit(10, "Initializing report generator...")

            # 생성기 임포트 및 초기화
            from data_graph_studio.report import create_report_manager

            manager = create_report_manager()

            self.progress.emit(30, "Preparing report data...")

            self.progress.emit(
                50, f"Generating {self.options.format.value.upper()} report..."
            )

            # 레포트 생성
            output_path = manager.generate_report(
                self.report_data, self.options, self.output_path
            )

            self.progress.emit(100, "Report generated successfully!")
            self.finished.emit(True, str(output_path))

        except Exception as e:
            logger.exception("Failed to generate report")
            self.finished.emit(False, str(e))


class ReportDialog(QDialog):
    """레포트 생성 다이얼로그"""

    # 파일 확장자 매핑
    FORMAT_EXTENSIONS = {
        ReportFormat.HTML: ".html",
        ReportFormat.PDF: ".pdf",
        ReportFormat.DOCX: ".docx",
        ReportFormat.PPTX: ".pptx",
        ReportFormat.JSON: ".json",
        ReportFormat.MARKDOWN: ".md",
    }

    def __init__(self, report_data: ReportData, parent=None):
        super().__init__(parent)
        self.report_data = report_data
        self.selected_format = ReportFormat.HTML
        self.generator_thread = None

        self._setup_ui()
        self._connect_signals()
        self._load_defaults()

    def _setup_ui(self):
        """UI 설정"""
        self.setWindowTitle("Generate Report")
        self.setMinimumSize(700, 600)
        self.resize(750, 700)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 탭 위젯
        tabs = QTabWidget()

        # 기본 설정 탭
        basic_tab = self._create_basic_tab()
        tabs.addTab(basic_tab, "Basic")

        # 섹션 설정 탭
        sections_tab = self._create_sections_tab()
        tabs.addTab(sections_tab, "Sections")

        # 고급 설정 탭
        advanced_tab = self._create_advanced_tab()
        tabs.addTab(advanced_tab, "Advanced")

        layout.addWidget(tabs)

        # 출력 경로
        output_group = QGroupBox("Output")
        output_layout = QHBoxLayout(output_group)

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output file path...")
        output_layout.addWidget(self.output_path_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Choose output file location")
        browse_btn.clicked.connect(self._browse_output)
        output_layout.addWidget(browse_btn)

        layout.addWidget(output_group)

        # 버튼
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel and close dialog")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        preview_btn = QPushButton("Preview")
        preview_btn.setToolTip("Preview report before generating")
        preview_btn.clicked.connect(self._preview_report)
        button_layout.addWidget(preview_btn)

        self.generate_btn = QPushButton("Generate Report")
        self.generate_btn.setToolTip("Generate and save the report")
        self.generate_btn.setDefault(True)
        self.generate_btn.clicked.connect(self._generate_report)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #1f77b4;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1a5f8f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        button_layout.addWidget(self.generate_btn)

        layout.addLayout(button_layout)

    def _create_basic_tab(self) -> QWidget:
        """기본 설정 탭 생성"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # 레포트 정보
        info_group = QGroupBox("Report Information")
        info_layout = QGridLayout(info_group)

        # 제목
        info_layout.addWidget(QLabel("Title:"), 0, 0)
        self.title_edit = QLineEdit()
        self.title_edit.setText(self.report_data.metadata.title)
        info_layout.addWidget(self.title_edit, 0, 1)

        # 부제목
        info_layout.addWidget(QLabel("Subtitle:"), 1, 0)
        self.subtitle_edit = QLineEdit()
        if self.report_data.metadata.subtitle:
            self.subtitle_edit.setText(self.report_data.metadata.subtitle)
        info_layout.addWidget(self.subtitle_edit, 1, 1)

        # 작성자
        info_layout.addWidget(QLabel("Author:"), 2, 0)
        self.author_edit = QLineEdit()
        if self.report_data.metadata.author:
            self.author_edit.setText(self.report_data.metadata.author)
        info_layout.addWidget(self.author_edit, 2, 1)

        layout.addWidget(info_group)

        # 출력 형식
        format_group = QGroupBox("Output Format")
        format_layout = QHBoxLayout(format_group)

        self.format_buttons = {}
        format_btn_group = QButtonGroup(self)

        formats = [
            (ReportFormat.HTML, "HTML", "Interactive web page"),
            (ReportFormat.PDF, "PDF", "Print-ready document"),
            (ReportFormat.DOCX, "Word", "Editable document"),
            (ReportFormat.PPTX, "PowerPoint", "Presentation"),
            (ReportFormat.JSON, "JSON", "Data format"),
        ]

        for fmt, label, tooltip in formats:
            btn = QRadioButton(label)
            btn.setToolTip(tooltip)
            if fmt == ReportFormat.HTML:
                btn.setChecked(True)
            format_btn_group.addButton(btn)
            self.format_buttons[fmt] = btn
            format_layout.addWidget(btn)

        format_layout.addStretch()
        layout.addWidget(format_group)

        # 테마
        theme_group = QGroupBox("Theme")
        theme_layout = QHBoxLayout(theme_group)

        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip("Select report visual theme")
        self.theme_combo.addItem("Light", ReportTheme.LIGHT)
        self.theme_combo.addItem("Dark", ReportTheme.DARK)
        self.theme_combo.addItem("Corporate", ReportTheme.CORPORATE)
        theme_layout.addWidget(self.theme_combo)

        theme_layout.addWidget(QLabel("Language:"))
        self.language_combo = QComboBox()
        self.language_combo.setToolTip("Select report language")
        self.language_combo.addItem("Korean", "ko")
        self.language_combo.addItem("English", "en")
        theme_layout.addWidget(self.language_combo)

        theme_layout.addStretch()
        layout.addWidget(theme_group)

        layout.addStretch()
        return widget

    def _create_sections_tab(self) -> QWidget:
        """섹션 설정 탭 생성"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        sections_group = QGroupBox("Include Sections")
        sections_layout = QVBoxLayout(sections_group)

        self.section_checks = {}

        sections = [
            ("executive_summary", "Executive Summary", True),
            ("data_overview", "Data Overview", True),
            ("statistics", "Statistical Summary", True),
            ("visualizations", "Visualizations", True),
            ("comparison", "Comparison Analysis (Multi-data)", True),
            ("tables", "Data Tables", True),
            ("appendix", "Appendix (Methodology)", False),
        ]

        for key, label, default in sections:
            check = QCheckBox(label)
            check.setChecked(default)
            self.section_checks[key] = check
            sections_layout.addWidget(check)

        layout.addWidget(sections_group)

        # Key Findings
        findings_group = QGroupBox("Key Findings (Optional)")
        findings_layout = QVBoxLayout(findings_group)

        self.findings_edit = QTextEdit()
        self.findings_edit.setPlaceholderText(
            "Enter key findings, one per line...\ne.g., Sales increased by 15% in Q3"
        )
        self.findings_edit.setMaximumHeight(100)

        if self.report_data.key_findings:
            self.findings_edit.setText("\n".join(self.report_data.key_findings))

        findings_layout.addWidget(self.findings_edit)
        layout.addWidget(findings_group)

        # Recommendations
        recommendations_group = QGroupBox("Recommendations (Optional)")
        recommendations_layout = QVBoxLayout(recommendations_group)

        self.recommendations_edit = QTextEdit()
        self.recommendations_edit.setPlaceholderText(
            "Enter recommendations, one per line...\n"
            "e.g., Focus on Region A for growth opportunities"
        )
        self.recommendations_edit.setMaximumHeight(100)

        if self.report_data.recommendations:
            self.recommendations_edit.setText(
                "\n".join(self.report_data.recommendations)
            )

        recommendations_layout.addWidget(self.recommendations_edit)
        layout.addWidget(recommendations_group)

        layout.addStretch()
        return widget

    def _create_advanced_tab(self) -> QWidget:
        """고급 설정 탭 생성"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 페이지 설정 (PDF/DOCX)
        page_group = QGroupBox("Page Settings (PDF/Word)")
        page_layout = QGridLayout(page_group)

        page_layout.addWidget(QLabel("Page Size:"), 0, 0)
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItem("A4", PageSize.A4)
        self.page_size_combo.addItem("Letter", PageSize.LETTER)
        self.page_size_combo.addItem("Legal", PageSize.LEGAL)
        page_layout.addWidget(self.page_size_combo, 0, 1)

        page_layout.addWidget(QLabel("Orientation:"), 0, 2)
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItem("Portrait", PageOrientation.PORTRAIT)
        self.orientation_combo.addItem("Landscape", PageOrientation.LANDSCAPE)
        page_layout.addWidget(self.orientation_combo, 0, 3)

        layout.addWidget(page_group)

        # 차트 설정
        chart_group = QGroupBox("Chart Settings")
        chart_layout = QGridLayout(chart_group)

        self.interactive_charts_check = QCheckBox("Interactive Charts (HTML only)")
        self.interactive_charts_check.setToolTip(
            "Enable hover/zoom interactions in HTML reports"
        )
        chart_layout.addWidget(self.interactive_charts_check, 0, 0, 1, 2)

        chart_layout.addWidget(QLabel("Chart DPI:"), 1, 0)
        self.chart_dpi_spin = QSpinBox()
        self.chart_dpi_spin.setToolTip("Chart resolution in dots per inch")
        self.chart_dpi_spin.setRange(72, 300)
        self.chart_dpi_spin.setValue(150)
        chart_layout.addWidget(self.chart_dpi_spin, 1, 1)

        layout.addWidget(chart_group)

        # 테이블 설정
        table_group = QGroupBox("Table Settings")
        table_layout = QGridLayout(table_group)

        table_layout.addWidget(QLabel("Max Rows per Table:"), 0, 0)
        self.table_max_rows_spin = QSpinBox()
        self.table_max_rows_spin.setRange(10, 1000)
        self.table_max_rows_spin.setValue(100)
        table_layout.addWidget(self.table_max_rows_spin, 0, 1)

        layout.addWidget(table_group)

        # 슬라이드 설정 (PPTX)
        slide_group = QGroupBox("Slide Settings (PowerPoint)")
        slide_layout = QGridLayout(slide_group)

        slide_layout.addWidget(QLabel("Slide Size:"), 0, 0)
        self.slide_size_combo = QComboBox()
        self.slide_size_combo.addItem("16:9 (Widescreen)", "16:9")
        self.slide_size_combo.addItem("4:3 (Standard)", "4:3")
        slide_layout.addWidget(self.slide_size_combo, 0, 1)

        self.one_chart_per_slide_check = QCheckBox("One Chart per Slide")
        self.one_chart_per_slide_check.setToolTip(
            "Place each chart on a separate slide"
        )
        self.one_chart_per_slide_check.setChecked(True)
        slide_layout.addWidget(self.one_chart_per_slide_check, 1, 0, 1, 2)

        layout.addWidget(slide_group)

        # 헤더/푸터
        header_group = QGroupBox("Header/Footer")
        header_layout = QGridLayout(header_group)

        header_layout.addWidget(QLabel("Header Text:"), 0, 0)
        self.header_text_edit = QLineEdit()
        self.header_text_edit.setPlaceholderText("Optional header text...")
        header_layout.addWidget(self.header_text_edit, 0, 1)

        header_layout.addWidget(QLabel("Footer Text:"), 1, 0)
        self.footer_text_edit = QLineEdit()
        self.footer_text_edit.setPlaceholderText("Optional footer text...")
        header_layout.addWidget(self.footer_text_edit, 1, 1)

        layout.addWidget(header_group)

        layout.addStretch()
        return widget

    def _connect_signals(self):
        """시그널 연결"""
        for fmt, btn in self.format_buttons.items():
            btn.toggled.connect(
                lambda checked, f=fmt: self._on_format_changed(f, checked)
            )

        self.title_edit.textChanged.connect(self._update_output_filename)

    def _load_defaults(self):
        """기본값 로드"""
        # 기본 출력 경로 설정
        default_filename = self._sanitize_filename(self.report_data.metadata.title)
        self.output_path_edit.setText(f"{default_filename}.html")

    def _on_format_changed(self, format: ReportFormat, checked: bool):
        """형식 변경 시"""
        if checked:
            self.selected_format = format
            self._update_output_filename()

            # 형식별 옵션 활성화/비활성화
            is_html = format == ReportFormat.HTML
            self.interactive_charts_check.setEnabled(is_html)

    def _update_output_filename(self):
        """출력 파일명 업데이트"""
        current_path = self.output_path_edit.text()
        if current_path:
            # 확장자 변경
            path = Path(current_path)
            new_ext = self.FORMAT_EXTENSIONS.get(self.selected_format, ".html")
            new_path = path.with_suffix(new_ext)
            self.output_path_edit.setText(str(new_path))

    def _sanitize_filename(self, name: str) -> str:
        """파일명에 사용할 수 없는 문자 제거"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")
        return name[:100]  # 최대 100자

    def _browse_output(self):
        """출력 경로 선택"""
        ext = self.FORMAT_EXTENSIONS.get(self.selected_format, ".html")
        filter_map = {
            ".html": "HTML Files (*.html)",
            ".pdf": "PDF Files (*.pdf)",
            ".docx": "Word Documents (*.docx)",
            ".pptx": "PowerPoint Files (*.pptx)",
            ".json": "JSON Files (*.json)",
            ".md": "Markdown Files (*.md)",
        }

        file_filter = filter_map.get(ext, "All Files (*.*)")
        default_name = self._sanitize_filename(self.title_edit.text() or "report")

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", f"{default_name}{ext}", file_filter
        )

        if path:
            self.output_path_edit.setText(path)

    def _get_options(self) -> ReportOptions:
        """현재 설정에서 ReportOptions 생성"""
        options = ReportOptions()

        # 기본 설정
        options.format = self.selected_format
        options.theme = self.theme_combo.currentData()
        options.language = self.language_combo.currentData()

        # 섹션
        options.include_executive_summary = self.section_checks[
            "executive_summary"
        ].isChecked()
        options.include_data_overview = self.section_checks["data_overview"].isChecked()
        options.include_statistics = self.section_checks["statistics"].isChecked()
        options.include_visualizations = self.section_checks[
            "visualizations"
        ].isChecked()
        options.include_comparison = self.section_checks["comparison"].isChecked()
        options.include_tables = self.section_checks["tables"].isChecked()
        options.include_appendix = self.section_checks["appendix"].isChecked()

        # 고급 설정
        options.page_size = self.page_size_combo.currentData()
        options.orientation = self.orientation_combo.currentData()
        options.interactive_charts = self.interactive_charts_check.isChecked()
        options.chart_dpi = self.chart_dpi_spin.value()
        options.table_max_rows = self.table_max_rows_spin.value()
        options.slide_size = self.slide_size_combo.currentData()
        options.one_chart_per_slide = self.one_chart_per_slide_check.isChecked()

        # 헤더/푸터
        header = self.header_text_edit.text().strip()
        footer = self.footer_text_edit.text().strip()
        if header:
            options.header_text = header
        if footer:
            options.footer_text = footer

        return options

    def _update_report_data(self):
        """레포트 데이터 업데이트"""
        # 메타데이터 업데이트
        self.report_data.metadata.title = self.title_edit.text()
        self.report_data.metadata.subtitle = self.subtitle_edit.text() or None
        self.report_data.metadata.author = self.author_edit.text() or None

        # Key Findings
        findings_text = self.findings_edit.toPlainText().strip()
        if findings_text:
            self.report_data.key_findings = [
                line.strip() for line in findings_text.split("\n") if line.strip()
            ]

        # Recommendations
        recommendations_text = self.recommendations_edit.toPlainText().strip()
        if recommendations_text:
            self.report_data.recommendations = [
                line.strip()
                for line in recommendations_text.split("\n")
                if line.strip()
            ]

    def _preview_report(self):
        """레포트 미리보기"""
        try:
            # 최신 UI 값 반영
            self._update_report_data()
            options = self._get_options()

            from data_graph_studio.report import create_report_manager

            manager = create_report_manager()

            # 미리보기는 빠른 확인을 위해 HTML 우선
            preview_format = options.format
            if preview_format in {
                ReportFormat.PDF,
                ReportFormat.DOCX,
                ReportFormat.PPTX,
            }:
                preview_format = ReportFormat.HTML

            preview_options = ReportOptions(**vars(options))
            preview_options.format = preview_format

            ext = self.FORMAT_EXTENSIONS.get(preview_format, ".html")
            with tempfile.NamedTemporaryFile(
                prefix="dgs_report_preview_", suffix=ext, delete=False
            ) as f:
                preview_path = f.name

            manager.generate_report(self.report_data, preview_options, preview_path)

            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(preview_path))
            if not opened:
                QMessageBox.warning(
                    self,
                    "Preview",
                    f"Preview created but could not be opened automatically:\n{preview_path}",
                )

        except Exception as e:
            logger.exception("Failed to preview report")
            QMessageBox.critical(self, "Preview Error", str(e))

    def _generate_report(self):
        """레포트 생성"""
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(
                self, "Missing Output Path", "Please specify an output file path."
            )
            return

        # 데이터 업데이트
        self._update_report_data()

        # 옵션 가져오기
        options = self._get_options()

        # 진행률 다이얼로그
        progress = QProgressDialog("Generating report...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setAutoClose(True)
        progress.show()

        # 생성 스레드 시작
        self.generator_thread = ReportGeneratorThread(
            self.report_data, options, output_path, self
        )

        self.generator_thread.progress.connect(
            lambda val, msg: self._on_progress(progress, val, msg)
        )
        self.generator_thread.finished.connect(
            lambda success, msg: self._on_finished(progress, success, msg)
        )

        self.generator_thread.start()

    def _on_progress(self, dialog: QProgressDialog, value: int, message: str):
        """진행률 업데이트"""
        dialog.setValue(value)
        dialog.setLabelText(message)

    def _on_finished(self, dialog: QProgressDialog, success: bool, message: str):
        """생성 완료"""
        dialog.close()

        if success:
            reply = QMessageBox.information(
                self,
                "Report Generated",
                f"Report has been saved to:\n{message}\n\nWould you like to open it?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                import subprocess
                import sys

                if sys.platform == "darwin":
                    subprocess.run(["open", message])
                elif sys.platform == "win32":
                    subprocess.run(["start", "", message], shell=True)
                else:
                    subprocess.run(["xdg-open", message])

            self.accept()
        else:
            QMessageBox.critical(
                self,
                "Report Generation Failed",
                f"Failed to generate report:\n{message}",
            )


def show_report_dialog(report_data: ReportData, parent=None) -> bool:
    """
    레포트 생성 다이얼로그 표시

    Args:
        report_data: 레포트 데이터
        parent: 부모 위젯

    Returns:
        생성 성공 여부
    """
    dialog = ReportDialog(report_data, parent)
    return dialog.exec() == QDialog.Accepted
