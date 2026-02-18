"""
Finish Step - 새 프로젝트 마법사 완료 페이지
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, Optional

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QGroupBox,
    QFormLayout,
    QWidget,
)


class FinishStep(QWizardPage):
    """Step 2: 완료"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setTitle("완료")
        self.setSubTitle("설정 요약을 확인하고 프로젝트 이름을 입력해주세요.")

        self._project_name_input = QLineEdit()
        self._file_info_label = QLabel("-")
        self._parsing_info_label = QLabel("-")
        self._columns_info_label = QLabel("-")

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        header = QLabel("✅ 설정 완료!")
        header.setStyleSheet("font-weight: 600; font-size: 16px;")
        layout.addWidget(header)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("프로젝트 이름:"))
        name_layout.addWidget(self._project_name_input, 1)
        layout.addLayout(name_layout)

        summary_group = QGroupBox("📋 설정 요약")
        summary_layout = QFormLayout(summary_group)
        summary_layout.addRow("📁 파일:", self._file_info_label)
        summary_layout.addRow("📊 파싱:", self._parsing_info_label)
        summary_layout.addRow("📈 컬럼:", self._columns_info_label)

        layout.addWidget(summary_group)
        layout.addStretch(1)
        self.setLayout(layout)

    def initializePage(self) -> None:
        wizard = self.wizard()
        parsing_settings = None
        preview_df = None

        if wizard is not None:
            # Use typed reference if available, fall back to page(0)
            parsing_page = getattr(wizard, "_parsing_step", None) or wizard.page(0)
            if parsing_page is not None and hasattr(parsing_page, "get_parsing_settings"):
                parsing_settings = parsing_page.get_parsing_settings()
            if parsing_page is not None and hasattr(parsing_page, "get_preview_df"):
                preview_df = parsing_page.get_preview_df()

        file_path = getattr(parsing_settings, "file_path", None)
        if file_path:
            file_name = Path(file_path).name
            file_size = self._format_size(self._safe_file_size(file_path))
            self._file_info_label.setText(f"{file_name} ({file_size})")

            if not self._project_name_input.text().strip():
                self._project_name_input.setText(Path(file_path).stem)
        else:
            self._file_info_label.setText("알 수 없음")

        encoding = getattr(parsing_settings, "encoding", "-")
        delimiter = getattr(parsing_settings, "delimiter", "-")
        has_header = getattr(parsing_settings, "has_header", None)
        header_text = "있음" if has_header else "없음" if has_header is not None else "-"

        delimiter_text = self._format_delimiter(delimiter)
        self._parsing_info_label.setText(
            f"인코딩: {encoding}, 구분자: {delimiter_text}, 헤더: {header_text}"
        )

        total_columns = self._get_total_columns(preview_df)
        excluded_columns = getattr(parsing_settings, "excluded_columns", []) or []
        excluded_count = len(excluded_columns)
        if total_columns is not None:
            self._columns_info_label.setText(
                f"{total_columns}개 ({excluded_count}개 제외)"
            )
        else:
            self._columns_info_label.setText(
                f"알 수 없음 ({excluded_count}개 제외)"
            )

    def get_project_name(self) -> str:
        return self._project_name_input.text().strip()

    @staticmethod
    def _format_columns(values: Iterable[Any]) -> str:
        if not values:
            return "없음"
        if isinstance(values, (str, bytes)):
            return str(values)
        names = []
        for value in values:
            if isinstance(value, dict):
                names.append(str(value.get("name", value)))
            else:
                name = getattr(value, "name", None)
                names.append(str(name if name is not None else value))
        return ", ".join(names) if names else "없음"

    @staticmethod
    def _format_delimiter(delimiter: Any) -> str:
        if delimiter == "\t":
            return "탭"
        if delimiter in (",", ";", "|"):
            return delimiter
        return str(delimiter)

    @staticmethod
    def _safe_file_size(file_path: str) -> int:
        try:
            return os.path.getsize(file_path)
        except OSError:
            return 0

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}"
            size /= 1024
        return f"{size:.0f} GB"

    @staticmethod
    def _get_total_columns(preview_df: Any) -> Optional[int]:
        if preview_df is None:
            return None
        columns = getattr(preview_df, "columns", None)
        if columns is None:
            return None
        try:
            return len(columns)
        except TypeError:
            return None
