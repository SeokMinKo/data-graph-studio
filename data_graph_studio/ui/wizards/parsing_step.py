"""
Parsing Step - New Project Wizard Step 1
"""

import os
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QSplitter,
    QWidget,
    QScrollArea,
    QHeaderView,
    QProgressBar,
)

from ...core.data_engine import FileType, DelimiterType, DataEngine, HAS_ETL_PARSER
from ...core.parsing import ParsingSettings


class ParsingStep(QWizardPage):
    """Step 1: 파싱 설정"""

    PREVIEW_ROWS = 100

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.file_name = Path(file_path).name

        self._raw_lines: List[str] = []
        self._preview_df: Optional[pd.DataFrame] = None
        self._parsing_success = False
        self._raw_load_error = False
        self._is_binary_etl = False  # 바이너리 ETL 파일 여부

        self._excluded_columns: set[int] = set()
        self._column_checkboxes: List[QCheckBox] = []

        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(300)
        self._update_timer.timeout.connect(self._update_preview)

        self._setup_ui()
        self._detect_settings()

    def initializePage(self):
        """페이지 진입 시 초기화"""
        self._load_raw_preview()
        self._update_preview()

    def validatePage(self) -> bool:
        """다음 스텝 진행 가능 여부"""
        return self._parsing_success

    def get_parsing_settings(self) -> ParsingSettings:
        """현재 파싱 설정 반환"""
        delimiter, delimiter_type = self._get_delimiter()

        # Auto detect actual delimiter if needed
        if delimiter_type == DelimiterType.AUTO:
            delimiter = self._detect_delimiter_auto()
            type_map = {
                ',': DelimiterType.COMMA,
                '\t': DelimiterType.TAB,
                ';': DelimiterType.SEMICOLON,
                '|': DelimiterType.PIPE,
                ' ': DelimiterType.SPACE,
            }
            delimiter_type = type_map.get(delimiter, DelimiterType.COMMA)

        # Detect file type
        ext = Path(self.file_path).suffix.lower()
        type_map = {
            '.csv': FileType.CSV,
            '.tsv': FileType.TSV,
            '.txt': FileType.TXT,
            '.log': FileType.TXT,
            '.dat': FileType.TXT,
            '.etl': FileType.ETL,
            '.xlsx': FileType.EXCEL,
            '.xls': FileType.EXCEL,
            '.parquet': FileType.PARQUET,
            '.json': FileType.JSON,
        }
        file_type = type_map.get(ext, FileType.TXT)

        # Excluded column names
        excluded_names = []
        if self._column_checkboxes:
            for i in self._excluded_columns:
                if i < len(self._column_checkboxes):
                    excluded_names.append(self._column_checkboxes[i].toolTip())

        return ParsingSettings(
            file_path=self.file_path,
            file_type=file_type,
            encoding=self.encoding_combo.currentText(),
            delimiter=delimiter,
            delimiter_type=delimiter_type,
            regex_pattern=self.regex_edit.text() if delimiter_type == DelimiterType.REGEX else "",
            has_header=self.header_checkbox.isChecked(),
            skip_rows=self.skip_rows_spin.value(),
            comment_char=self.comment_edit.text().strip(),
            excluded_columns=excluded_names,
        )

    def get_preview_df(self) -> pd.DataFrame:
        """미리보기 데이터 반환"""
        if self._preview_df is None:
            return pd.DataFrame()
        if not self._excluded_columns:
            return self._preview_df
        excluded_names = [
            self._preview_df.columns[i]
            for i in sorted(self._excluded_columns)
            if i < len(self._preview_df.columns)
        ]
        return self._preview_df.drop(columns=excluded_names, errors="ignore")

    def _setup_ui(self):
        self.setTitle("Step 1: Parsing Settings")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # File info
        info_label = QLabel(self._build_file_info_text())
        info_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(info_label)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._create_settings_panel())
        splitter.addWidget(self._create_preview_panel())
        splitter.setSizes([320, 680])
        layout.addWidget(splitter, 1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Parsing... %p%")
        layout.addWidget(self.progress_bar)

    def _build_file_info_text(self) -> str:
        size = 0
        if os.path.exists(self.file_path):
            try:
                size = os.path.getsize(self.file_path)
            except OSError:
                size = 0
        size_kb = size / 1024 if size else 0
        ext = Path(self.file_path).suffix.lower().lstrip('.')
        ext = ext.upper() if ext else "UNKNOWN"
        return f"📁 {self.file_name} ({size_kb:.1f} KB, {ext})"

    def _create_settings_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Encoding
        encoding_group = QGroupBox("Encoding")
        encoding_layout = QGridLayout(encoding_group)
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems([
            "utf8",
            "utf8-lossy",
            "cp949",
            "euc-kr",
            "latin-1",
            "utf16",
            "ascii",
        ])
        self.encoding_combo.currentTextChanged.connect(self._on_encoding_changed)
        encoding_layout.addWidget(self.encoding_combo, 0, 0)
        layout.addWidget(encoding_group)

        # Delimiter
        delimiter_group = QGroupBox("Delimiter")
        delimiter_layout = QGridLayout(delimiter_group)
        delimiter_layout.addWidget(QLabel("Type:"), 0, 0)
        self.delimiter_combo = QComboBox()
        self.delimiter_combo.addItems([
            "Auto Detect",
            "Comma (,)",
            "Tab (\\t)",
            "Space",
            "Semicolon (;) ",
            "Pipe (|)",
            "Custom Regex",
        ])
        self.delimiter_combo.currentIndexChanged.connect(self._on_delimiter_changed)
        delimiter_layout.addWidget(self.delimiter_combo, 0, 1)

        delimiter_layout.addWidget(QLabel("Regex Pattern:"), 1, 0)
        self.regex_edit = QLineEdit()
        self.regex_edit.setPlaceholderText("e.g. \\s+ for multiple spaces")
        self.regex_edit.setEnabled(False)
        self.regex_edit.textChanged.connect(self._schedule_update)
        delimiter_layout.addWidget(self.regex_edit, 1, 1)
        layout.addWidget(delimiter_group)

        # Structure
        structure_group = QGroupBox("Structure")
        structure_layout = QGridLayout(structure_group)
        self.header_checkbox = QCheckBox("First row is header")
        self.header_checkbox.setChecked(True)
        self.header_checkbox.stateChanged.connect(self._schedule_update)
        structure_layout.addWidget(self.header_checkbox, 0, 0, 1, 2)

        structure_layout.addWidget(QLabel("Skip rows:"), 1, 0)
        self.skip_rows_spin = QSpinBox()
        self.skip_rows_spin.setRange(0, 1000)
        self.skip_rows_spin.setValue(0)
        self.skip_rows_spin.valueChanged.connect(self._schedule_update)
        structure_layout.addWidget(self.skip_rows_spin, 1, 1)

        structure_layout.addWidget(QLabel("Comment char:"), 2, 0)
        self.comment_edit = QLineEdit()
        self.comment_edit.setMaxLength(1)
        self.comment_edit.setPlaceholderText("e.g. #")
        self.comment_edit.textChanged.connect(self._schedule_update)
        structure_layout.addWidget(self.comment_edit, 2, 1)
        layout.addWidget(structure_group)

        layout.addStretch()
        return widget

    def _create_preview_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        preview_group = QGroupBox("Preview (First 100 rows)")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(8, 8, 8, 8)

        self.preview_table = QTableWidget()
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        preview_layout.addWidget(self.preview_table)
        layout.addWidget(preview_group)

        column_group = QGroupBox("Column Selection (Uncheck to exclude)")
        column_layout = QVBoxLayout(column_group)
        column_layout.setContentsMargins(8, 8, 8, 8)

        btn_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setStyleSheet("font-size: 10px; padding: 4px 8px;")
        select_all_btn.clicked.connect(self._select_all_columns)
        btn_row.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.setStyleSheet("font-size: 10px; padding: 4px 8px;")
        deselect_all_btn.clicked.connect(self._deselect_all_columns)
        btn_row.addWidget(deselect_all_btn)

        btn_row.addStretch()
        self.column_count_label = QLabel("")
        self.column_count_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        btn_row.addWidget(self.column_count_label)
        column_layout.addLayout(btn_row)

        column_scroll = QScrollArea()
        column_scroll.setWidgetResizable(True)
        column_scroll.setMaximumHeight(100)
        column_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.column_checkbox_container = QWidget()
        self.column_checkbox_layout = QHBoxLayout(self.column_checkbox_container)
        self.column_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.column_checkbox_layout.setSpacing(8)
        column_scroll.setWidget(self.column_checkbox_container)
        column_layout.addWidget(column_scroll)

        layout.addWidget(column_group)
        return widget

    def _detect_settings(self):
        ext = Path(self.file_path).suffix.lower()
        if ext == '.tsv':
            self.delimiter_combo.setCurrentIndex(2)
        elif ext == '.csv':
            self.delimiter_combo.setCurrentIndex(1)
        else:
            self.delimiter_combo.setCurrentIndex(0)

    def _on_delimiter_changed(self, index: int):
        self.regex_edit.setEnabled(index == 6)
        self._schedule_update()

    def _on_encoding_changed(self, _encoding: str):
        self._load_raw_preview()
        self._schedule_update()

    def _schedule_update(self):
        self._update_timer.start()

    def _load_raw_preview(self):
        encoding = self.encoding_combo.currentText() if hasattr(self, 'encoding_combo') else "utf8"
        self._raw_load_error = False
        self._is_binary_etl = False

        # ETL 확장자이고 바이너리인 경우 특별 처리
        ext = Path(self.file_path).suffix.lower()
        if ext == '.etl' and DataEngine.is_binary_etl(self.file_path):
            self._is_binary_etl = True
            self._raw_lines = self._load_binary_etl_preview()
            return

        try:
            self._raw_lines = []
            with open(self.file_path, 'r', encoding=encoding, errors='replace') as f:
                for i, line in enumerate(f):
                    if i >= self.PREVIEW_ROWS:
                        break
                    self._raw_lines.append(line.rstrip('\n\r'))
        except Exception as e:
            self._raw_lines = [f"Error reading file: {e}"]
            self._raw_load_error = True

    def _load_binary_etl_preview(self) -> List[str]:
        """
        바이너리 ETL 파일의 프리뷰를 etl-parser로 파싱하여 CSV 문자열로 반환

        etl-parser가 없거나 파싱 실패 시 안내 메시지를 반환.
        """
        if not HAS_ETL_PARSER:
            return [
                "# Binary ETL (Event Trace Log) file detected",
                "# etl-parser 라이브러리가 설치되지 않아 미리보기를 표시할 수 없습니다.",
                "# 설치: pip install etl-parser",
                "#",
                "# 또는 Windows에서 CSV로 변환 후 열기:",
                f"#   tracerpt \"{self.file_name}\" -o output.csv -of CSV",
            ]

        try:
            import polars as pl
            df = DataEngine.parse_etl_binary(self.file_path)

            if df is None or len(df) == 0:
                return [
                    "# Binary ETL file parsed but no events found",
                    "# 파싱 가능한 이벤트가 없습니다.",
                ]

            # DataFrame을 CSV 문자열로 변환하여 _raw_lines로 제공
            # → 기존 프리뷰 로직(delimiter=',' 파싱)으로 자연스럽게 처리됨
            csv_lines = []

            # 헤더
            csv_lines.append(",".join(df.columns))

            # 데이터 (최대 PREVIEW_ROWS 행)
            preview_count = min(len(df), self.PREVIEW_ROWS)
            for i in range(preview_count):
                row_values = []
                for col in df.columns:
                    val = df[col][i]
                    if val is None:
                        row_values.append("")
                    else:
                        # CSV 안전하게: 쉼표나 따옴표가 포함된 값은 따옴표로 감싸기
                        s = str(val)
                        if ',' in s or '"' in s or '\n' in s:
                            s = '"' + s.replace('"', '""') + '"'
                        row_values.append(s)
                csv_lines.append(",".join(row_values))

            return csv_lines

        except Exception as e:
            return [
                "# Binary ETL file - parsing failed",
                f"# 파싱 오류: {e}",
                "#",
                "# 대안: Windows에서 CSV로 변환 후 열기:",
                f"#   tracerpt \"{self.file_name}\" -o output.csv -of CSV",
            ]

    def _detect_delimiter_auto(self) -> str:
        if not self._raw_lines:
            return ","
        delimiters = [',', '\t', ';', '|']
        counts = {d: 0 for d in delimiters}
        for line in self._raw_lines[:10]:
            for d in delimiters:
                counts[d] += line.count(d)
        best = max(counts, key=counts.get)
        if counts[best] == 0:
            return " "
        return best

    def _get_delimiter(self) -> tuple[Optional[str], DelimiterType]:
        index = self.delimiter_combo.currentIndex()
        delimiters = [
            (None, DelimiterType.AUTO),
            (",", DelimiterType.COMMA),
            ("\t", DelimiterType.TAB),
            (" ", DelimiterType.SPACE),
            (";", DelimiterType.SEMICOLON),
            ("|", DelimiterType.PIPE),
            (self.regex_edit.text(), DelimiterType.REGEX),
        ]
        return delimiters[index]

    def _parse_preview(self) -> List[List[str]]:
        if not self._raw_lines:
            return []

        # 바이너리 ETL은 이미 CSV 형태로 변환되어 있으므로 comma 강제
        if self._is_binary_etl:
            delimiter = ","
            delimiter_type = DelimiterType.COMMA
            skip_rows = 0
            comment_char = ""
        else:
            delimiter, delimiter_type = self._get_delimiter()
            skip_rows = self.skip_rows_spin.value()
            comment_char = self.comment_edit.text().strip()

        if delimiter_type == DelimiterType.AUTO:
            delimiter = self._detect_delimiter_auto()

        rows = []
        lines = self._raw_lines[skip_rows:]

        for line in lines:
            if comment_char and line.strip().startswith(comment_char):
                continue
            if not line.strip():
                continue

            if delimiter_type == DelimiterType.REGEX and delimiter:
                try:
                    fields = re.split(delimiter, line)
                except re.error:
                    fields = [line]
            elif delimiter_type == DelimiterType.SPACE or delimiter == " ":
                fields = line.split()
            else:
                fields = line.split(delimiter)

            rows.append([f.strip() for f in fields])

        return rows

    def _update_preview(self):
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Parsing...")
        QApplication.processEvents()
        if self._raw_load_error:
            self.preview_table.clear()
            self.preview_table.setRowCount(0)
            self.preview_table.setColumnCount(0)
            self._preview_df = pd.DataFrame()
            self._parsing_success = False
            self._update_column_checkboxes([])
            self.progress_bar.setValue(0)
            return

        # 바이너리 ETL의 경우: delimiter/encoding 설정 비활성화, comma 강제
        if self._is_binary_etl:
            self.delimiter_combo.setEnabled(False)
            self.regex_edit.setEnabled(False)
            self.encoding_combo.setEnabled(False)
            self.header_checkbox.setChecked(True)
            self.header_checkbox.setEnabled(False)
            self.skip_rows_spin.setValue(0)
            self.skip_rows_spin.setEnabled(False)
            self.comment_edit.setEnabled(False)
        else:
            self.delimiter_combo.setEnabled(True)
            self.encoding_combo.setEnabled(True)
            self.header_checkbox.setEnabled(True)
            self.skip_rows_spin.setEnabled(True)
            self.comment_edit.setEnabled(True)

        self.progress_bar.setValue(20)
        self.progress_bar.setFormat("Parsing columns...")
        QApplication.processEvents()

        parsed = self._parse_preview()

        self.progress_bar.setValue(50)
        self.progress_bar.setFormat("Building preview...")
        QApplication.processEvents()

        if not parsed:
            self.preview_table.clear()
            self.preview_table.setRowCount(0)
            self.preview_table.setColumnCount(0)
            self._preview_df = pd.DataFrame()
            self._parsing_success = False
            self._update_column_checkboxes([])
            self.progress_bar.setValue(0)
            return

        has_header = self.header_checkbox.isChecked()
        if has_header:
            headers = parsed[0]
            data = parsed[1:]
        else:
            max_cols = max(len(row) for row in parsed)
            headers = [f"Column {i+1}" for i in range(max_cols)]
            data = parsed

        max_cols = len(headers)
        for i, row in enumerate(data):
            if len(row) < max_cols:
                data[i] = row + [''] * (max_cols - len(row))
            elif len(row) > max_cols:
                data[i] = row[:max_cols]

        self.progress_bar.setValue(70)
        self.progress_bar.setFormat("Loading table...")
        QApplication.processEvents()

        self._update_column_checkboxes(headers)

        row_count = min(len(data), self.PREVIEW_ROWS)
        self.preview_table.setUpdatesEnabled(False)
        try:
            self.preview_table.setRowCount(row_count)
            self.preview_table.setColumnCount(max_cols)
            self.preview_table.setHorizontalHeaderLabels(headers)

            excluded_bg = QColor("#E5E7EB")
            excluded_fg = QColor("#6B7280")
            for i, row in enumerate(data[:self.PREVIEW_ROWS]):
                for j, val in enumerate(row[:max_cols]):
                    item = QTableWidgetItem(val)
                    if j in self._excluded_columns:
                        item.setBackground(excluded_bg)
                        item.setForeground(excluded_fg)
                    self.preview_table.setItem(i, j, item)

        finally:
            self.preview_table.setUpdatesEnabled(True)

        # 컬럼 너비를 내용 기준으로 한 번만 조정 후 Interactive 모드 유지
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.preview_table.resizeColumnsToContents()

        try:
            self._preview_df = pd.DataFrame(data, columns=headers)
        except Exception:
            self._preview_df = pd.DataFrame()
        self._parsing_success = True
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Ready (%p%)")

    def _update_column_checkboxes(self, headers: List[str]):
        for cb in self._column_checkboxes:
            self.column_checkbox_layout.removeWidget(cb)
            cb.deleteLater()
        self._column_checkboxes.clear()

        self._excluded_columns = {i for i in self._excluded_columns if i < len(headers)}

        for i, header in enumerate(headers):
            label = header[:15] + "..." if len(header) > 15 else header
            cb = QCheckBox(label)
            cb.setToolTip(header)
            cb.setChecked(i not in self._excluded_columns)
            cb.stateChanged.connect(lambda state, idx=i: self._on_column_toggled(idx, state == Qt.Checked))
            self.column_checkbox_layout.addWidget(cb)
            self._column_checkboxes.append(cb)

        self._update_column_count()

    def _on_column_toggled(self, index: int, checked: bool):
        if checked:
            self._excluded_columns.discard(index)
        else:
            self._excluded_columns.add(index)
        self._update_column_count()
        self._apply_column_exclusion_styles()

    def _update_column_count(self):
        total = len(self._column_checkboxes)
        selected = total - len(self._excluded_columns)
        self.column_count_label.setText(f"Loading {selected} of {total} columns")

    def _apply_column_exclusion_styles(self):
        self.preview_table.setUpdatesEnabled(False)
        try:
            excluded_bg = QColor("#E5E7EB")
            excluded_fg = QColor("#6B7280")
            normal_bg = QColor("#FFFFFF")
            normal_fg = QColor("#111827")
            for row in range(self.preview_table.rowCount()):
                for col in range(self.preview_table.columnCount()):
                    item = self.preview_table.item(row, col)
                    if not item:
                        continue
                    if col in self._excluded_columns:
                        item.setBackground(excluded_bg)
                        item.setForeground(excluded_fg)
                    else:
                        item.setBackground(normal_bg)
                        item.setForeground(normal_fg)
        finally:
            self.preview_table.setUpdatesEnabled(True)

    def _select_all_columns(self):
        for cb in self._column_checkboxes:
            cb.setChecked(True)
        self._excluded_columns.clear()
        self._update_column_count()
        self._apply_column_exclusion_styles()

    def _deselect_all_columns(self):
        for i, cb in enumerate(self._column_checkboxes):
            cb.setChecked(False)
            self._excluded_columns.add(i)
        self._update_column_count()
        self._apply_column_exclusion_styles()
