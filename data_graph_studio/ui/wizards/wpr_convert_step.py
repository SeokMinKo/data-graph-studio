"""WPR conversion step for Import Wizard."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QMessageBox,
)


def is_wpr_file(file_path: str) -> bool:
    ext = Path(file_path).suffix.lower()
    return ext in {".etl", ".wpr"}


def build_wpr_output_path(file_path: str, output_dir: Optional[str] = None) -> str:
    src = Path(file_path)
    out_dir = Path(output_dir) if output_dir else src.parent
    return str(out_dir / f"{src.stem}_wpr.parquet")


class _ConvertWorker(QThread):
    finished_signal = Signal(bool, str)

    def __init__(self, command: str, parent=None) -> None:
        super().__init__(parent)
        self._command = command

    def run(self) -> None:
        try:
            result = subprocess.run(
                shlex.split(self._command),
                shell=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                msg = result.stderr.strip() or result.stdout.strip() or "conversion failed"
                self.finished_signal.emit(False, msg)
                return
            self.finished_signal.emit(True, "")
        except Exception as e:  # pragma: no cover - subprocess failure
            logger.exception("wpr_convert_step.run.error")
            self.finished_signal.emit(False, str(e))


class WprConvertStep(QWizardPage):
    """Wizard step to convert WPR/ETL to Parquet using WPAExporter."""

    def __init__(self, file_path: str, parent=None) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.output_path = build_wpr_output_path(file_path)
        self._converted = False
        self._worker: Optional[_ConvertWorker] = None

        self.setTitle("WPR 변환")
        self.setSubTitle("WPAExporter로 WPR/ETL 파일을 Parquet으로 변환합니다.")

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        self._file_label = QLabel(f"입력 파일: {self.file_path}")
        self._output_label = QLabel(f"출력 파일: {self.output_path}")
        layout.addWidget(self._file_label)
        layout.addWidget(self._output_label)

        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(QLabel("WPAExporter 경로:"))
        self._wpa_path = QLineEdit()
        self._wpa_path.setPlaceholderText("wpaexporter (PATH) 또는 전체 경로")
        cmd_layout.addWidget(self._wpa_path)
        layout.addLayout(cmd_layout)

        self._command = QLineEdit()
        self._command.setPlaceholderText("명령어 템플릿")
        layout.addWidget(self._command)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignLeft)
        layout.addWidget(self._status)

        self._convert_btn = QPushButton("변환 시작")
        self._convert_btn.clicked.connect(self._on_convert)
        layout.addWidget(self._convert_btn)

        self.setLayout(layout)

    def initializePage(self) -> None:
        self._converted = False
        self._status.setText("")
        self._progress.setVisible(False)

        wpa = self._detect_wpaexporter()
        if wpa:
            self._wpa_path.setText(wpa)
        self._command.setText(self._default_command())

    def validatePage(self) -> bool:
        return self._converted

    def _detect_wpaexporter(self) -> str | None:
        if self._wpa_path.text().strip():
            return self._wpa_path.text().strip()
        return shutil.which("wpaexporter") or shutil.which("wpaexporter.exe")

    def _default_command(self) -> str:
        wpa = self._detect_wpaexporter() or "wpaexporter"
        return f'"{wpa}" -i "{self.file_path}" -o "{self.output_path}" -format parquet'

    def _on_convert(self) -> None:
        wpa = self._detect_wpaexporter()
        if not wpa:
            QMessageBox.warning(self, "WPAExporter 없음", "WPAExporter를 찾을 수 없습니다. 경로를 입력하세요.")
            return

        self.output_path = build_wpr_output_path(self.file_path)
        self._output_label.setText(f"출력 파일: {self.output_path}")

        cmd = self._command.text().strip() or self._default_command()
        cmd = cmd.replace("{input}", self.file_path).replace("{output}", self.output_path)

        self._progress.setVisible(True)
        self._status.setText("변환 중...")
        self._convert_btn.setEnabled(False)

        self._worker = _ConvertWorker(cmd)
        self._worker.finished_signal.connect(self._on_convert_done)
        self._worker.start()

    def _on_convert_done(self, success: bool, message: str) -> None:
        self._progress.setVisible(False)
        self._convert_btn.setEnabled(True)
        if success:
            self._converted = True
            self._status.setText("변환 완료")
            if hasattr(self.wizard(), "set_current_file_path"):
                self.wizard().set_current_file_path(self.output_path)
            self.completeChanged.emit()
        else:
            self._status.setText(f"변환 실패: {message}")
            QMessageBox.warning(self, "변환 실패", message)
            self._converted = False
            self.completeChanged.emit()
