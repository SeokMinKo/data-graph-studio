"""
Multi-File Selection Dialog - 다중 파일 선택 다이얼로그

여러 파일을 선택하여 동시에 데이터셋으로 로드하기 위한 다이얼로그
"""

from typing import Optional, List, Tuple
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QGroupBox,
    QCheckBox, QComboBox, QFrame, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QColor

from ...core.data_engine import DataEngine


class FileItem(QListWidgetItem):
    """파일 리스트 아이템"""

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

        name = Path(file_path).name
        size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
        size_str = self._format_size(size)

        self.setText(f"{name} ({size_str})")
        self.setToolTip(file_path)
        self.setCheckState(Qt.Checked)

    def _format_size(self, size: int) -> str:
        """파일 크기 포맷팅"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"


class MultiFileDialog(QDialog):
    """
    다중 파일 선택 다이얼로그

    Features:
    - 여러 파일 동시 선택
    - 선택한 파일 미리보기 (이름, 크기)
    - 개별 파일 제외/포함 토글
    - 자동 데이터셋 명명 옵션
    """

    files_selected = Signal(list)  # List of file paths

    def __init__(self, parent=None, engine: DataEngine = None):
        super().__init__(parent)
        self.engine = engine
        self._selected_files: List[str] = []

        self.setWindowTitle("Open Multiple Files")
        self.setMinimumSize(500, 400)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Header
        header = QLabel(
            "Select multiple data files to open as separate datasets.\n"
            "You can then compare them using the comparison features."
        )
        header.setWordWrap(True)
        header.setStyleSheet("color: #666;")
        layout.addWidget(header)

        # File selection area
        file_group = QGroupBox("Selected Files")
        file_layout = QVBoxLayout(file_group)

        # File list
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setMinimumHeight(150)
        file_layout.addWidget(self.file_list)

        # File buttons
        btn_layout = QHBoxLayout()

        self.add_btn = QPushButton("Add Files...")
        self.add_btn.clicked.connect(self._add_files)
        btn_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._clear_all)
        btn_layout.addWidget(self.clear_btn)

        btn_layout.addStretch()
        file_layout.addLayout(btn_layout)

        layout.addWidget(file_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.auto_compare_cb = QCheckBox("Automatically start comparison after loading")
        self.auto_compare_cb.setChecked(True)
        options_layout.addWidget(self.auto_compare_cb)

        naming_layout = QHBoxLayout()
        naming_layout.addWidget(QLabel("Naming:"))
        self.naming_combo = QComboBox()
        self.naming_combo.addItem("Use file name", "filename")
        self.naming_combo.addItem("Use file name (without extension)", "filename_no_ext")
        self.naming_combo.addItem("Use sequential numbers (Data 1, Data 2, ...)", "sequential")
        naming_layout.addWidget(self.naming_combo, 1)
        options_layout.addLayout(naming_layout)

        layout.addWidget(options_group)

        # Summary
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.summary_label)

        # Memory warning
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #f57c00; padding: 8px; background: #fff3e0; border-radius: 4px;")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        layout.addWidget(self.warning_label)

        # Dialog buttons
        btn_frame = QFrame()
        btn_frame_layout = QHBoxLayout(btn_frame)
        btn_frame_layout.setContentsMargins(0, 0, 0, 0)

        btn_frame_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_frame_layout.addWidget(self.cancel_btn)

        self.open_btn = QPushButton("Open Files")
        self.open_btn.setDefault(True)
        self.open_btn.clicked.connect(self._accept)
        self.open_btn.setEnabled(False)
        btn_frame_layout.addWidget(self.open_btn)

        layout.addWidget(btn_frame)

        self._update_summary()

    def _add_files(self):
        """파일 추가"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Data Files",
            "",
            "Data Files (*.csv *.xlsx *.xls *.parquet *.json *.tsv *.txt);;"
            "CSV Files (*.csv);;"
            "Excel Files (*.xlsx *.xls);;"
            "Parquet Files (*.parquet);;"
            "All Files (*)"
        )

        for path in file_paths:
            if path not in self._selected_files:
                self._selected_files.append(path)
                item = FileItem(path)
                self.file_list.addItem(item)

        self._update_summary()

    def _remove_selected(self):
        """선택된 파일 제거"""
        for item in self.file_list.selectedItems():
            row = self.file_list.row(item)
            self._selected_files.remove(item.file_path)
            self.file_list.takeItem(row)

        self._update_summary()

    def _clear_all(self):
        """모든 파일 제거"""
        self.file_list.clear()
        self._selected_files.clear()
        self._update_summary()

    def _update_summary(self):
        """요약 정보 업데이트"""
        checked_count = sum(
            1 for i in range(self.file_list.count())
            if self.file_list.item(i).checkState() == Qt.Checked
        )
        total_count = self.file_list.count()

        self.summary_label.setText(f"{checked_count} of {total_count} files will be opened")
        self.open_btn.setEnabled(checked_count > 0)

        # Calculate total size
        total_size = 0
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.Checked:
                path = item.file_path
                if Path(path).exists():
                    total_size += Path(path).stat().st_size

        # Memory warning
        if total_size > 500 * 1024 * 1024:  # 500MB
            self.warning_label.setText(
                f"⚠️ Total file size: {total_size / (1024*1024):.1f} MB. "
                "Loading large files may affect performance."
            )
            self.warning_label.show()
        else:
            self.warning_label.hide()

    def _accept(self):
        """확인"""
        files_to_open = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.Checked:
                files_to_open.append(item.file_path)

        if not files_to_open:
            return

        self.files_selected.emit(files_to_open)
        self.accept()

    def get_selected_files(self) -> List[str]:
        """선택된 파일 목록 반환"""
        files = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.Checked:
                files.append(item.file_path)
        return files

    def get_naming_option(self) -> str:
        """명명 옵션 반환"""
        return self.naming_combo.currentData()

    def should_auto_compare(self) -> bool:
        """자동 비교 시작 여부"""
        return self.auto_compare_cb.isChecked()

    def generate_dataset_name(self, file_path: str, index: int) -> str:
        """데이터셋 이름 생성"""
        naming = self.get_naming_option()

        if naming == "filename":
            return Path(file_path).name
        elif naming == "filename_no_ext":
            return Path(file_path).stem
        elif naming == "sequential":
            return f"Data {index + 1}"
        else:
            return Path(file_path).name


def open_multi_file_dialog(parent=None, engine: DataEngine = None) -> Optional[Tuple[List[str], str, bool]]:
    """
    다중 파일 선택 다이얼로그 열기

    Returns:
        (file_paths, naming_option, auto_compare) or None if cancelled
    """
    dialog = MultiFileDialog(parent, engine)
    if dialog.exec() == QDialog.Accepted:
        return (
            dialog.get_selected_files(),
            dialog.get_naming_option(),
            dialog.should_auto_compare()
        )
    return None
