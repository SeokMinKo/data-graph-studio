"""
Parsing Preview Dialog - 파일 파싱 미리보기 및 설정
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QSpinBox, QLineEdit, QCheckBox,
    QPushButton, QTableWidget, QTableWidgetItem, QGroupBox,
    QSplitter, QTextEdit, QFrame, QSizePolicy, QHeaderView,
    QWidget, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

from ...core.data_engine import FileType, DelimiterType


@dataclass
class ParsingSettings:
    """파싱 설정"""
    file_path: str
    file_type: FileType
    encoding: str = "utf-8"
    delimiter: str = ","
    delimiter_type: DelimiterType = DelimiterType.COMMA
    regex_pattern: str = ""
    has_header: bool = True
    skip_rows: int = 0
    comment_char: str = ""
    sheet_name: Optional[str] = None


class ParsingPreviewDialog(QDialog):
    """
    파일 파싱 미리보기 다이얼로그
    
    Features:
    - 실시간 파싱 결과 미리보기
    - 구분자, 인코딩, 헤더 등 옵션 조절
    - 원본 텍스트와 파싱 결과 비교
    """
    
    # 미리보기에 로드할 최대 라인 수
    PREVIEW_LINES = 100
    
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.file_name = Path(file_path).name
        self._raw_lines: List[str] = []
        self._parsed_data: List[List[str]] = []
        self._settings: Optional[ParsingSettings] = None
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._do_update_preview)
        
        self._setup_ui()
        self._load_raw_preview()
        self._detect_settings()
        self._update_preview()
    
    def _setup_ui(self):
        """UI 설정"""
        self.setWindowTitle(f"Import: {self.file_name}")
        self.setMinimumSize(1000, 700)
        self.resize(1100, 750)
        
        # Modern style
        self.setStyleSheet("""
            QDialog {
                background: #FAFAFA;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #374151;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px;
                background: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
            }
            QLabel {
                color: #4B5563;
                font-size: 12px;
            }
            QComboBox, QSpinBox, QLineEdit {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 6px 10px;
                background: white;
                min-height: 28px;
            }
            QComboBox:focus, QSpinBox:focus, QLineEdit:focus {
                border-color: #6366F1;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QCheckBox {
                color: #374151;
                font-size: 12px;
            }
            QPushButton {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px 20px;
                background: white;
                font-weight: 500;
                min-width: 80px;
            }
            QPushButton:hover {
                background: #F9FAFB;
                border-color: #9CA3AF;
            }
            QPushButton:pressed {
                background: #F3F4F6;
            }
            QPushButton#primary {
                background: #4F46E5;
                color: white;
                border: none;
            }
            QPushButton#primary:hover {
                background: #4338CA;
            }
            QPushButton#primary:pressed {
                background: #3730A3;
            }
            QTableWidget {
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                gridline-color: #F3F4F6;
                background: white;
            }
            QTableWidget::item {
                padding: 4px 8px;
            }
            QTableWidget::item:selected {
                background: #EEF2FF;
                color: #1F2937;
            }
            QHeaderView::section {
                background: #F9FAFB;
                border: none;
                border-bottom: 1px solid #E5E7EB;
                border-right: 1px solid #E5E7EB;
                padding: 8px;
                font-weight: 500;
                color: #374151;
            }
            QTextEdit {
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                background: #1F2937;
                color: #D1D5DB;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                padding: 8px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # Header
        header = QLabel(f"📄 {self.file_name}")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F2937;")
        layout.addWidget(header)
        
        # Main content - settings on left, preview on right
        content_splitter = QSplitter(Qt.Horizontal)
        
        # Left side - Settings
        settings_widget = self._create_settings_panel()
        content_splitter.addWidget(settings_widget)
        
        # Right side - Preview
        preview_widget = self._create_preview_panel()
        content_splitter.addWidget(preview_widget)
        
        # Set initial sizes (30% settings, 70% preview)
        content_splitter.setSizes([300, 700])
        layout.addWidget(content_splitter, 1)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        import_btn = QPushButton("Import")
        import_btn.setObjectName("primary")
        import_btn.clicked.connect(self.accept)
        button_layout.addWidget(import_btn)
        
        layout.addLayout(button_layout)
    
    def _create_settings_panel(self) -> QWidget:
        """설정 패널 생성"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # Delimiter Group
        delimiter_group = QGroupBox("Delimiter")
        delimiter_layout = QGridLayout(delimiter_group)
        delimiter_layout.setSpacing(8)
        
        delimiter_layout.addWidget(QLabel("Type:"), 0, 0)
        self.delimiter_combo = QComboBox()
        self.delimiter_combo.addItems([
            "Auto Detect",
            "Comma (,)",
            "Tab (\\t)",
            "Space",
            "Semicolon (;)",
            "Pipe (|)",
            "Custom Regex"
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
        
        # Encoding Group
        encoding_group = QGroupBox("Encoding")
        encoding_layout = QGridLayout(encoding_group)
        encoding_layout.setSpacing(8)
        
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems([
            "utf-8",
            "utf-8-sig",
            "cp949",
            "euc-kr",
            "latin-1",
            "utf-16",
            "ascii"
        ])
        self.encoding_combo.currentTextChanged.connect(self._on_encoding_changed)
        encoding_layout.addWidget(self.encoding_combo, 0, 0)
        
        layout.addWidget(encoding_group)
        
        # Structure Group
        structure_group = QGroupBox("Structure")
        structure_layout = QGridLayout(structure_group)
        structure_layout.setSpacing(8)
        
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
        self.comment_edit.setPlaceholderText("e.g. #")
        self.comment_edit.setMaxLength(1)
        self.comment_edit.textChanged.connect(self._schedule_update)
        structure_layout.addWidget(self.comment_edit, 2, 1)
        
        layout.addWidget(structure_group)
        
        # Stats
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
        
        return widget
    
    def _create_preview_panel(self) -> QWidget:
        """미리보기 패널 생성"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Preview splitter (raw text above, parsed table below)
        preview_splitter = QSplitter(Qt.Vertical)
        
        # Raw text preview
        raw_group = QGroupBox("Raw Data (First 20 lines)")
        raw_layout = QVBoxLayout(raw_group)
        raw_layout.setContentsMargins(8, 8, 8, 8)
        
        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setMaximumHeight(150)
        raw_layout.addWidget(self.raw_text)
        
        preview_splitter.addWidget(raw_group)
        
        # Parsed table preview
        parsed_group = QGroupBox("Parsed Result")
        parsed_layout = QVBoxLayout(parsed_group)
        parsed_layout.setContentsMargins(8, 8, 8, 8)
        
        self.preview_table = QTableWidget()
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectRows)
        parsed_layout.addWidget(self.preview_table)
        
        preview_splitter.addWidget(parsed_group)
        
        # Set initial sizes (30% raw, 70% parsed)
        preview_splitter.setSizes([150, 350])
        
        layout.addWidget(preview_splitter)
        
        return widget
    
    def _load_raw_preview(self):
        """원본 파일 미리보기 로드"""
        encoding = self.encoding_combo.currentText() if hasattr(self, 'encoding_combo') else "utf-8"
        
        try:
            with open(self.file_path, 'r', encoding=encoding, errors='replace') as f:
                self._raw_lines = []
                for i, line in enumerate(f):
                    if i >= self.PREVIEW_LINES:
                        break
                    self._raw_lines.append(line.rstrip('\n\r'))
            
            # Update raw text display
            if hasattr(self, 'raw_text'):
                display_lines = self._raw_lines[:20]
                self.raw_text.setText('\n'.join(display_lines))
                
        except Exception as e:
            self._raw_lines = [f"Error reading file: {e}"]
            if hasattr(self, 'raw_text'):
                self.raw_text.setText(f"Error reading file: {e}")
    
    def _detect_settings(self):
        """파일 설정 자동 감지"""
        # File type detection
        ext = Path(self.file_path).suffix.lower()
        type_map = {
            '.csv': FileType.CSV,
            '.tsv': FileType.TSV,
            '.txt': FileType.TXT,
            '.log': FileType.TXT,
            '.dat': FileType.TXT,
            '.etl': FileType.ETL,
        }
        file_type = type_map.get(ext, FileType.TXT)
        
        # Delimiter detection
        if ext == '.tsv':
            self.delimiter_combo.setCurrentIndex(2)  # Tab
        elif ext == '.csv':
            self.delimiter_combo.setCurrentIndex(1)  # Comma
        else:
            # Auto-detect
            self.delimiter_combo.setCurrentIndex(0)
    
    def _on_delimiter_changed(self, index: int):
        """구분자 변경"""
        # Enable regex field only for custom regex
        self.regex_edit.setEnabled(index == 6)  # Custom Regex
        self._schedule_update()
    
    def _on_encoding_changed(self, encoding: str):
        """인코딩 변경"""
        self._load_raw_preview()
        self._schedule_update()
    
    def _schedule_update(self):
        """업데이트 예약 (디바운스)"""
        self._update_timer.start(150)  # 150ms 디바운스
    
    def _do_update_preview(self):
        """실제 미리보기 업데이트"""
        self._update_preview()
    
    def _get_delimiter(self) -> tuple[str, DelimiterType]:
        """현재 선택된 구분자 반환"""
        index = self.delimiter_combo.currentIndex()
        
        delimiters = [
            (None, DelimiterType.AUTO),      # Auto Detect
            (",", DelimiterType.COMMA),      # Comma
            ("\t", DelimiterType.TAB),       # Tab
            (" ", DelimiterType.SPACE),      # Space
            (";", DelimiterType.SEMICOLON),  # Semicolon
            ("|", DelimiterType.PIPE),       # Pipe
            (self.regex_edit.text(), DelimiterType.REGEX),  # Custom Regex
        ]
        
        return delimiters[index]
    
    def _detect_delimiter_auto(self) -> str:
        """구분자 자동 감지"""
        if not self._raw_lines:
            return ","
        
        delimiters = [',', '\t', ';', '|']
        counts = {d: 0 for d in delimiters}
        
        for line in self._raw_lines[:10]:
            for d in delimiters:
                counts[d] += line.count(d)
        
        # 가장 많이 등장하는 구분자
        best = max(counts, key=counts.get)
        
        # 공백은 다른 구분자가 없을 때만
        if counts[best] == 0:
            return " "
        
        return best
    
    def _parse_preview(self) -> List[List[str]]:
        """미리보기 파싱"""
        if not self._raw_lines:
            return []
        
        delimiter, delimiter_type = self._get_delimiter()
        skip_rows = self.skip_rows_spin.value()
        comment_char = self.comment_edit.text().strip()
        
        # Auto detect delimiter if needed
        if delimiter_type == DelimiterType.AUTO:
            delimiter = self._detect_delimiter_auto()
        
        rows = []
        lines = self._raw_lines[skip_rows:]
        
        for line in lines:
            # Skip comments
            if comment_char and line.strip().startswith(comment_char):
                continue
            
            # Skip empty lines
            if not line.strip():
                continue
            
            # Parse based on delimiter type
            if delimiter_type == DelimiterType.REGEX and delimiter:
                try:
                    fields = re.split(delimiter, line)
                except:
                    fields = [line]
            elif delimiter_type == DelimiterType.SPACE or delimiter == " ":
                fields = line.split()
            else:
                fields = line.split(delimiter)
            
            rows.append([f.strip() for f in fields])
        
        return rows
    
    def _update_preview(self):
        """미리보기 테이블 업데이트"""
        parsed = self._parse_preview()
        
        if not parsed:
            self.preview_table.clear()
            self.preview_table.setRowCount(0)
            self.preview_table.setColumnCount(0)
            self.stats_label.setText("No data to preview")
            return
        
        has_header = self.header_checkbox.isChecked()
        
        # Determine headers
        if has_header:
            headers = parsed[0]
            data = parsed[1:]
        else:
            max_cols = max(len(row) for row in parsed)
            headers = [f"Column {i+1}" for i in range(max_cols)]
            data = parsed
        
        # Normalize column count
        max_cols = len(headers)
        for row in data:
            while len(row) < max_cols:
                row.append("")
        
        # Update table
        self.preview_table.setRowCount(min(len(data), 50))  # Show max 50 rows
        self.preview_table.setColumnCount(max_cols)
        self.preview_table.setHorizontalHeaderLabels(headers)
        
        for i, row in enumerate(data[:50]):
            for j, val in enumerate(row[:max_cols]):
                item = QTableWidgetItem(val)
                self.preview_table.setItem(i, j, item)
        
        # Resize columns to content
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        # Update stats
        total_lines = len(self._raw_lines)
        parsed_rows = len(data)
        self.stats_label.setText(
            f"📊 {parsed_rows:,} rows × {max_cols} columns "
            f"(previewing from {total_lines:,} lines)"
        )
    
    def get_settings(self) -> ParsingSettings:
        """현재 설정 반환"""
        delimiter, delimiter_type = self._get_delimiter()
        
        # Auto detect if needed
        if delimiter_type == DelimiterType.AUTO:
            delimiter = self._detect_delimiter_auto()
            # Map back to actual type
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
        )
