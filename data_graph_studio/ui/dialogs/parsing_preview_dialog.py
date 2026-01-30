"""
Parsing Preview Dialog - 파일 파싱 미리보기 및 설정
"""

import os
import re
import subprocess
import tempfile
import platform
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QSpinBox, QLineEdit, QCheckBox,
    QPushButton, QTableWidget, QTableWidgetItem, QGroupBox,
    QSplitter, QTextEdit, QFrame, QSizePolicy, QHeaderView,
    QWidget, QScrollArea, QListWidget, QListWidgetItem, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtGui import QFont, QColor

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
    excluded_columns: List[str] = None  # 제외할 컬럼 목록
    # ETL specific settings
    etl_converted_path: Optional[str] = None  # Path to converted CSV from ETL
    etl_selected_processes: List[str] = field(default_factory=list)  # Selected processes

    def __post_init__(self):
        if self.excluded_columns is None:
            self.excluded_columns = []
        if self.etl_selected_processes is None:
            self.etl_selected_processes = []


class ETLConverterThread(QThread):
    """Background thread for converting ETL files using tracerpt"""
    finished = Signal(bool, str, str)  # success, csv_path, error_msg

    def __init__(self, etl_path: str):
        super().__init__()
        self.etl_path = etl_path
        self._csv_path = None

    def run(self):
        system = platform.system()
        if system != "Windows":
            self.finished.emit(False, "",
                "ETL files can only be converted on Windows.\n"
                "Please convert the file to CSV using Windows tools first.")
            return

        try:
            # Create temp file for output
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.csv', prefix='etl_preview_')
            os.close(tmp_fd)

            # Run tracerpt to convert ETL to CSV
            result = subprocess.run(
                ['tracerpt', self.etl_path, '-o', tmp_path, '-of', 'CSV', '-y'],
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if result.returncode == 0 and os.path.exists(tmp_path):
                # Check if output has content
                if os.path.getsize(tmp_path) > 0:
                    self._csv_path = tmp_path
                    self.finished.emit(True, tmp_path, "")
                else:
                    os.unlink(tmp_path)
                    self.finished.emit(False, "",
                        "ETL conversion produced empty output.\n"
                        "The file may be corrupted or unsupported.")
            else:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                error_msg = result.stderr if result.stderr else "Unknown error"
                self.finished.emit(False, "",
                    f"ETL conversion failed:\n{error_msg}")

        except subprocess.TimeoutExpired:
            self.finished.emit(False, "",
                "ETL conversion timed out (2 minutes).\n"
                "The file may be too large.")
        except FileNotFoundError:
            self.finished.emit(False, "",
                "tracerpt command not found.\n"
                "This command requires Windows and admin privileges.")
        except Exception as e:
            self.finished.emit(False, "", f"ETL conversion error: {e}")


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
        self._excluded_columns: set = set()  # 제외할 컬럼 인덱스
        self._column_checkboxes: List[QCheckBox] = []

        # ETL-specific state
        self._is_binary_etl = False
        self._etl_converted_path: Optional[str] = None
        self._etl_converter_thread: Optional[ETLConverterThread] = None
        self._etl_processes: List[str] = []  # Available processes
        self._etl_selected_processes: set = set()  # Selected processes

        # Check if it's a binary ETL file
        ext = Path(file_path).suffix.lower()
        if ext == '.etl':
            self._is_binary_etl = self._check_binary_etl(file_path)

        self._setup_ui()
        self._load_raw_preview()
        self._detect_settings()
        self._update_preview()

    def _check_binary_etl(self, path: str) -> bool:
        """Check if the ETL file is in binary format"""
        try:
            with open(path, 'rb') as f:
                header = f.read(512)

            # Binary ETL detection: null bytes or high ratio of non-printable chars
            null_count = header.count(b'\x00')
            non_printable = sum(1 for b in header if b < 32 and b not in (9, 10, 13))

            # If null bytes present or >5% non-printable, it's binary
            return null_count > 0 or (non_printable / max(len(header), 1)) > 0.05
        except Exception:
            return False
    
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

        # ETL Process Filter Group (only visible for binary ETL files)
        self.etl_group = QGroupBox("ETL Process Filter")
        etl_layout = QVBoxLayout(self.etl_group)
        etl_layout.setSpacing(8)

        # Status/progress for ETL conversion
        self.etl_status_label = QLabel("Converting ETL file...")
        self.etl_status_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        etl_layout.addWidget(self.etl_status_label)

        self.etl_progress = QProgressBar()
        self.etl_progress.setRange(0, 0)  # Indeterminate
        self.etl_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                height: 8px;
                background: #F3F4F6;
            }
            QProgressBar::chunk {
                background: #6366F1;
                border-radius: 4px;
            }
        """)
        etl_layout.addWidget(self.etl_progress)

        # Process list
        process_label = QLabel("Select processes to load:")
        process_label.setStyleSheet("font-weight: 500;")
        etl_layout.addWidget(process_label)

        self.etl_process_list = QListWidget()
        self.etl_process_list.setSelectionMode(QListWidget.MultiSelection)
        self.etl_process_list.setMaximumHeight(150)
        self.etl_process_list.itemSelectionChanged.connect(self._on_etl_process_selection_changed)
        etl_layout.addWidget(self.etl_process_list)

        # Select all/none buttons
        etl_btn_layout = QHBoxLayout()
        select_all_proc_btn = QPushButton("Select All")
        select_all_proc_btn.setStyleSheet("font-size: 10px; padding: 4px 8px;")
        select_all_proc_btn.clicked.connect(self._select_all_processes)
        etl_btn_layout.addWidget(select_all_proc_btn)

        deselect_all_proc_btn = QPushButton("Deselect All")
        deselect_all_proc_btn.setStyleSheet("font-size: 10px; padding: 4px 8px;")
        deselect_all_proc_btn.clicked.connect(self._deselect_all_processes)
        etl_btn_layout.addWidget(deselect_all_proc_btn)

        etl_btn_layout.addStretch()
        etl_layout.addLayout(etl_btn_layout)

        layout.addWidget(self.etl_group)

        # Hide ETL group initially - will be shown for binary ETL files
        self.etl_group.setVisible(self._is_binary_etl)

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
        self.raw_text.setMaximumHeight(120)
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

        # Column selection panel (for excluding columns)
        column_group = QGroupBox("Column Selection (Uncheck to exclude)")
        column_group_layout = QVBoxLayout(column_group)
        column_group_layout.setContentsMargins(8, 8, 8, 8)

        # Buttons row
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

        column_group_layout.addLayout(btn_row)

        # Scroll area for column checkboxes
        column_scroll = QScrollArea()
        column_scroll.setWidgetResizable(True)
        column_scroll.setMaximumHeight(100)
        column_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.column_checkbox_container = QWidget()
        self.column_checkbox_layout = QHBoxLayout(self.column_checkbox_container)
        self.column_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self.column_checkbox_layout.setSpacing(8)

        column_scroll.setWidget(self.column_checkbox_container)
        column_group_layout.addWidget(column_scroll)

        preview_splitter.addWidget(column_group)

        # Set initial sizes (20% raw, 50% parsed, 30% columns)
        preview_splitter.setSizes([100, 250, 150])

        layout.addWidget(preview_splitter)

        return widget

    def _select_all_columns(self):
        """Select all columns"""
        for cb in self._column_checkboxes:
            cb.setChecked(True)
        self._excluded_columns.clear()
        self._update_column_count()

    def _deselect_all_columns(self):
        """Deselect all columns"""
        for i, cb in enumerate(self._column_checkboxes):
            cb.setChecked(False)
            self._excluded_columns.add(i)
        self._update_column_count()

    def _on_column_toggled(self, index: int, checked: bool):
        """Handle column checkbox toggle"""
        if checked:
            self._excluded_columns.discard(index)
        else:
            self._excluded_columns.add(index)
        self._update_column_count()

    def _update_column_count(self):
        """Update the column count label"""
        total = len(self._column_checkboxes)
        selected = total - len(self._excluded_columns)
        self.column_count_label.setText(f"Loading {selected} of {total} columns")
    
    def _load_raw_preview(self):
        """원본 파일 미리보기 로드"""
        # Handle binary ETL files specially
        if self._is_binary_etl:
            self._load_binary_etl_preview()
            return

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

    def _load_binary_etl_preview(self):
        """Load binary ETL file preview by converting first"""
        if hasattr(self, 'raw_text'):
            self.raw_text.setText(
                "Binary ETL (Event Trace Log) file detected.\n\n"
                "Converting to CSV for preview...\n"
                "This may take a moment for large files."
            )

        # Show progress
        if hasattr(self, 'etl_progress'):
            self.etl_progress.setVisible(True)
            self.etl_status_label.setText("Converting ETL file...")

        # Start conversion in background
        self._etl_converter_thread = ETLConverterThread(self.file_path)
        self._etl_converter_thread.finished.connect(self._on_etl_conversion_finished)
        self._etl_converter_thread.start()

    def _on_etl_conversion_finished(self, success: bool, csv_path: str, error_msg: str):
        """Handle ETL conversion completion"""
        self.etl_progress.setVisible(False)

        if success:
            self._etl_converted_path = csv_path
            self.etl_status_label.setText("Conversion complete!")
            self.etl_status_label.setStyleSheet("color: #10B981; font-size: 11px;")

            # Load the converted CSV
            self._load_converted_etl_csv(csv_path)
        else:
            self.etl_status_label.setText("Conversion failed")
            self.etl_status_label.setStyleSheet("color: #EF4444; font-size: 11px;")
            if hasattr(self, 'raw_text'):
                self.raw_text.setText(
                    f"Failed to convert ETL file:\n\n{error_msg}\n\n"
                    "You can manually convert the ETL file using:\n"
                    "  tracerpt \"file.etl\" -o output.csv -of CSV\n\n"
                    "Or use Windows Performance Analyzer (WPA) to export as CSV."
                )

    def _load_converted_etl_csv(self, csv_path: str):
        """Load the converted ETL CSV and extract processes"""
        try:
            with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
                self._raw_lines = []
                for i, line in enumerate(f):
                    if i >= self.PREVIEW_LINES:
                        break
                    self._raw_lines.append(line.rstrip('\n\r'))

            # Update raw text display
            if hasattr(self, 'raw_text'):
                display_lines = self._raw_lines[:20]
                self.raw_text.setText('\n'.join(display_lines))

            # Extract process names from the data
            self._extract_etl_processes()

            # Update preview
            self._schedule_update()

        except Exception as e:
            if hasattr(self, 'raw_text'):
                self.raw_text.setText(f"Error reading converted ETL: {e}")

    def _extract_etl_processes(self):
        """Extract unique process names from ETL data"""
        processes = set()

        # Look for process column (common names: Process Name, ProcessName, Process, Image)
        if not self._raw_lines:
            return

        # Parse header to find process column
        header_line = self._raw_lines[0] if self._raw_lines else ""
        delimiter = ","  # CSV default
        headers = [h.strip().strip('"') for h in header_line.split(delimiter)]

        process_col_idx = -1
        process_col_names = ['Process Name', 'ProcessName', 'Process', 'Image', 'Image Name']
        for i, header in enumerate(headers):
            if header in process_col_names or 'process' in header.lower():
                process_col_idx = i
                break

        if process_col_idx < 0:
            self.etl_process_list.addItem("(No process column found)")
            return

        # Extract unique process names
        for line in self._raw_lines[1:]:  # Skip header
            fields = line.split(delimiter)
            if len(fields) > process_col_idx:
                process = fields[process_col_idx].strip().strip('"')
                if process:
                    processes.add(process)

        # Update process list
        self._etl_processes = sorted(processes)
        self.etl_process_list.clear()
        for proc in self._etl_processes:
            item = QListWidgetItem(proc)
            item.setSelected(True)  # Select all by default
            self.etl_process_list.addItem(item)
            self._etl_selected_processes.add(proc)

    def _on_etl_process_selection_changed(self):
        """Handle process selection change"""
        self._etl_selected_processes.clear()
        for item in self.etl_process_list.selectedItems():
            self._etl_selected_processes.add(item.text())
        self._schedule_update()

    def _select_all_processes(self):
        """Select all processes"""
        self.etl_process_list.selectAll()

    def _deselect_all_processes(self):
        """Deselect all processes"""
        self.etl_process_list.clearSelection()
    
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
                except re.error:
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
            self._update_column_checkboxes([])
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

        # Update column checkboxes
        self._update_column_checkboxes(headers)

        # Update table
        self.preview_table.setRowCount(min(len(data), 50))  # Show max 50 rows
        self.preview_table.setColumnCount(max_cols)
        self.preview_table.setHorizontalHeaderLabels(headers)

        for i, row in enumerate(data[:50]):
            for j, val in enumerate(row[:max_cols]):
                item = QTableWidgetItem(val)
                # Gray out excluded columns
                if j in self._excluded_columns:
                    item.setBackground(QColor("#F3F4F6"))
                    item.setForeground(QColor("#9CA3AF"))
                self.preview_table.setItem(i, j, item)

        # Resize columns to content
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # Update stats
        total_lines = len(self._raw_lines)
        parsed_rows = len(data)
        selected_cols = max_cols - len(self._excluded_columns)
        self.stats_label.setText(
            f"📊 {parsed_rows:,} rows × {selected_cols} columns "
            f"(previewing from {total_lines:,} lines)"
        )

    def _update_column_checkboxes(self, headers: List[str]):
        """Update column checkboxes based on headers"""
        # Clear existing checkboxes
        for cb in self._column_checkboxes:
            self.column_checkbox_layout.removeWidget(cb)
            cb.deleteLater()
        self._column_checkboxes.clear()

        # Keep valid excluded columns
        valid_excluded = {i for i in self._excluded_columns if i < len(headers)}
        self._excluded_columns = valid_excluded

        # Create new checkboxes
        for i, header in enumerate(headers):
            cb = QCheckBox(header[:15] + "..." if len(header) > 15 else header)
            cb.setToolTip(header)
            cb.setChecked(i not in self._excluded_columns)
            cb.setStyleSheet("""
                QCheckBox {
                    background: white;
                    border: 1px solid #E5E7EB;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                QCheckBox:hover {
                    border-color: #6366F1;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                }
            """)
            cb.stateChanged.connect(lambda state, idx=i: self._on_column_toggled(idx, state == Qt.Checked))
            self.column_checkbox_layout.addWidget(cb)
            self._column_checkboxes.append(cb)

        self._update_column_count()
    
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

        # Get excluded column names
        excluded_names = []
        if self._column_checkboxes:
            for i in self._excluded_columns:
                if i < len(self._column_checkboxes):
                    excluded_names.append(self._column_checkboxes[i].toolTip())

        # For binary ETL, use the converted path and selected processes
        actual_file_path = self.file_path
        etl_selected = []
        if self._is_binary_etl and self._etl_converted_path:
            actual_file_path = self._etl_converted_path
            etl_selected = list(self._etl_selected_processes)
            # Override to CSV since we converted it
            file_type = FileType.CSV
            delimiter = ","
            delimiter_type = DelimiterType.COMMA

        return ParsingSettings(
            file_path=actual_file_path,
            file_type=file_type,
            encoding=self.encoding_combo.currentText(),
            delimiter=delimiter,
            delimiter_type=delimiter_type,
            regex_pattern=self.regex_edit.text() if delimiter_type == DelimiterType.REGEX else "",
            has_header=self.header_checkbox.isChecked(),
            skip_rows=self.skip_rows_spin.value(),
            comment_char=self.comment_edit.text().strip(),
            excluded_columns=excluded_names,
            etl_converted_path=self._etl_converted_path,
            etl_selected_processes=etl_selected,
        )
