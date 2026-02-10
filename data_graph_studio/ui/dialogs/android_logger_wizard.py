"""
Android Logger Setup Wizard

ADB/Perfetto 기반 블록 레이어 트레이스 설정을 위한 단계별 위자드.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QProcess
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

# 설정 파일 경로
CONFIG_DIR = Path.home() / ".data_graph_studio"
CONFIG_PATH = CONFIG_DIR / "logger_config.json"

# 기본 이벤트 목록
DEFAULT_EVENTS = [
    ("block/block_rq_issue", True),
    ("block/block_rq_complete", True),
    ("ufs/ufshcd_command", True),
    ("block/block_bio_complete", False),
    ("block/block_bio_queue", False),
    ("block/block_rq_requeue", False),
]


def load_logger_config() -> dict[str, Any]:
    """저장된 logger 설정을 로드한다. 없으면 기본값 반환."""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_logger_config(config: dict[str, Any]) -> None:
    """logger 설정을 JSON으로 저장한다."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ============================================================
# Page 1: ADB Check
# ============================================================
class AdbCheckPage(QWizardPage):
    """ADB 설치 여부를 확인하는 페이지."""

    def __init__(self, parent: QWizard | None = None) -> None:
        super().__init__(parent)
        self.setTitle("ADB Check")
        self.setSubTitle("Check that Android Debug Bridge (adb) is available.")

        layout = QVBoxLayout(self)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        self._info_label.setTextFormat(Qt.TextFormat.RichText)
        self._info_label.setOpenExternalLinks(True)
        layout.addWidget(self._info_label)

        check_btn = QPushButton("Re-check")
        check_btn.clicked.connect(self._check_adb)
        layout.addWidget(check_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

        self._adb_found = False

    def initializePage(self) -> None:  # noqa: N802
        self._check_adb()

    def _check_adb(self) -> None:
        adb_path = shutil.which("adb")
        if adb_path:
            self._adb_found = True
            self._status_label.setText(f"✅ adb found: {adb_path}")
            self._info_label.setText("")
        else:
            self._adb_found = False
            self._status_label.setText("❌ adb not found in PATH.")
            self._info_label.setText(
                "<b>Install Android SDK Platform Tools:</b><br>"
                "<code>brew install android-platform-tools</code><br><br>"
                "Or download from: "
                '<a href="https://developer.android.com/tools/releases/platform-tools">'
                "Android Platform Tools</a>"
            )
        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        return self._adb_found


# ============================================================
# Page 2: Device Connection
# ============================================================
class DeviceConnectionPage(QWizardPage):
    """연결된 Android 기기를 선택하는 페이지."""

    def __init__(self, parent: QWizard | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Device Connection")
        self.setSubTitle("Select a connected Android device.")

        layout = QVBoxLayout(self)

        self._device_list = QListWidget()
        self._device_list.currentItemChanged.connect(lambda *_: self.completeChanged.emit())
        layout.addWidget(self._device_list)

        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_devices)
        layout.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

    def initializePage(self) -> None:  # noqa: N802
        self._refresh_devices()

    def _refresh_devices(self) -> None:
        self._device_list.clear()
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().split("\n")[1:]:
                line = line.strip()
                if not line or "offline" in line:
                    continue
                parts = line.split()
                serial = parts[0]
                status = parts[1] if len(parts) > 1 else "unknown"
                desc = " ".join(parts[2:]) if len(parts) > 2 else ""
                if status == "device":
                    item = QListWidgetItem(f"{serial}  {desc}")
                    item.setData(Qt.ItemDataRole.UserRole, serial)
                    self._device_list.addItem(item)
        except Exception as e:
            self._info_label.setText(f"Error: {e}")
            return

        if self._device_list.count() == 0:
            self._info_label.setText(
                "No devices found.\n\n"
                "1. Connect your device via USB\n"
                "2. Enable USB Debugging in Developer Options\n"
                "3. Accept the RSA key prompt on the device"
            )
        else:
            self._info_label.setText("")
            self._device_list.setCurrentRow(0)

        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        return self._device_list.currentItem() is not None

    def selected_serial(self) -> str:
        """선택된 기기의 시리얼 번호를 반환한다."""
        item = self._device_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""


# ============================================================
# Page 3: Perfetto Check
# ============================================================
class PerfettoCheckPage(QWizardPage):
    """선택된 기기에 Perfetto가 있는지 확인하는 페이지."""

    def __init__(self, parent: QWizard | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Perfetto Check")
        self.setSubTitle("Verify that Perfetto is available on the device.")

        layout = QVBoxLayout(self)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        check_btn = QPushButton("Re-check")
        check_btn.clicked.connect(self._check_perfetto)
        layout.addWidget(check_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

        self._perfetto_found = False

    def initializePage(self) -> None:  # noqa: N802
        self._check_perfetto()

    def _check_perfetto(self) -> None:
        wizard: AndroidLoggerWizard = self.wizard()  # type: ignore[assignment]
        serial = wizard.device_page.selected_serial()
        if not serial:
            self._status_label.setText("❌ No device selected.")
            self._perfetto_found = False
            self.completeChanged.emit()
            return

        try:
            result = subprocess.run(
                ["adb", "-s", serial, "shell", "which", "perfetto"],
                capture_output=True, text=True, timeout=5,
            )
            path = result.stdout.strip()
            if path and result.returncode == 0:
                self._perfetto_found = True
                self._status_label.setText(f"✅ perfetto found: {path}")
                self._info_label.setText("")
            else:
                self._perfetto_found = False
                self._status_label.setText("❌ perfetto not found on device.")
                self._info_label.setText(
                    "Perfetto is included in Android 9 (Pie) and later.\n"
                    "Make sure your device runs Android 9+ or install Perfetto manually."
                )
        except Exception as e:
            self._perfetto_found = False
            self._status_label.setText(f"❌ Check failed: {e}")
            self._info_label.setText("")

        self.completeChanged.emit()

    def isComplete(self) -> bool:  # noqa: N802
        return self._perfetto_found


# ============================================================
# Page 4: Trace Config
# ============================================================
class TraceConfigPage(QWizardPage):
    """트레이스 설정 페이지: 버퍼 크기, 이벤트, 저장 경로."""

    def __init__(self, parent: QWizard | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Trace Configuration")
        self.setSubTitle("Configure the trace parameters.")

        layout = QVBoxLayout(self)

        # Buffer size
        buf_group = QGroupBox("Buffer Size")
        buf_layout = QHBoxLayout(buf_group)
        self._buffer_spin = QSpinBox()
        self._buffer_spin.setRange(4, 512)
        self._buffer_spin.setValue(64)
        self._buffer_spin.setSuffix(" MB")
        buf_layout.addWidget(QLabel("Ring buffer:"))
        buf_layout.addWidget(self._buffer_spin)
        buf_layout.addStretch()
        layout.addWidget(buf_group)

        # Events
        evt_group = QGroupBox("Ftrace Events")
        evt_layout = QVBoxLayout(evt_group)
        self._event_checks: list[tuple[str, QCheckBox]] = []
        for event_name, default_on in DEFAULT_EVENTS:
            cb = QCheckBox(event_name)
            cb.setChecked(default_on)
            evt_layout.addWidget(cb)
            self._event_checks.append((event_name, cb))
        layout.addWidget(evt_group)

        # Save path
        path_group = QGroupBox("Output")
        path_layout = QHBoxLayout(path_group)
        self._save_path_edit = QLineEdit()
        self._save_path_edit.setPlaceholderText("Trace file save location...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_save_path)
        path_layout.addWidget(self._save_path_edit, stretch=1)
        path_layout.addWidget(browse_btn)
        layout.addWidget(path_group)

        layout.addStretch()

    def initializePage(self) -> None:  # noqa: N802
        # 기존 config에서 로드
        config = load_logger_config()
        if "buffer_size_mb" in config:
            self._buffer_spin.setValue(config["buffer_size_mb"])
        if "events" in config:
            enabled = set(config["events"])
            for name, cb in self._event_checks:
                cb.setChecked(name in enabled)
        if "save_path" in config:
            self._save_path_edit.setText(config["save_path"])

        if not self._save_path_edit.text():
            import datetime
            default = f"blktrace_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.perfetto-trace"
            self._save_path_edit.setText(
                str(Path.home() / "Downloads" / default)
            )

    def _browse_save_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Trace File",
            self._save_path_edit.text(),
            "Perfetto Trace (*.perfetto-trace);;All Files (*)",
        )
        if path:
            self._save_path_edit.setText(path)

    def buffer_size_mb(self) -> int:
        return self._buffer_spin.value()

    def selected_events(self) -> list[str]:
        return [name for name, cb in self._event_checks if cb.isChecked()]

    def save_path(self) -> str:
        return self._save_path_edit.text()


# ============================================================
# Page 5: Summary & Finish
# ============================================================
class SummaryPage(QWizardPage):
    """설정 요약 및 완료 페이지."""

    def __init__(self, parent: QWizard | None = None) -> None:
        super().__init__(parent)
        self.setTitle("Summary")
        self.setSubTitle("Review your configuration.")

        layout = QVBoxLayout(self)

        self._summary_text = QTextEdit()
        self._summary_text.setReadOnly(True)
        layout.addWidget(self._summary_text)

        btn_layout = QHBoxLayout()
        self._start_btn = QPushButton("Start Trace")
        self._start_btn.clicked.connect(self._on_start_trace)
        btn_layout.addWidget(self._start_btn)

        self._save_btn = QPushButton("Save Config")
        self._save_btn.clicked.connect(self._on_save_config)
        btn_layout.addWidget(self._save_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._config_saved = False
        self._start_requested = False

    def initializePage(self) -> None:  # noqa: N802
        wizard: AndroidLoggerWizard = self.wizard()  # type: ignore[assignment]
        serial = wizard.device_page.selected_serial()
        cfg = wizard.config_page
        events = cfg.selected_events()

        summary = (
            f"Device:       {serial}\n"
            f"Buffer size:  {cfg.buffer_size_mb()} MB\n"
            f"Events:       {', '.join(events)}\n"
            f"Save path:    {cfg.save_path()}\n"
        )
        self._summary_text.setPlainText(summary)
        self._config_saved = False
        self._start_requested = False

    def _build_config(self) -> dict[str, Any]:
        wizard: AndroidLoggerWizard = self.wizard()  # type: ignore[assignment]
        cfg = wizard.config_page
        return {
            "device_serial": wizard.device_page.selected_serial(),
            "buffer_size_mb": cfg.buffer_size_mb(),
            "events": cfg.selected_events(),
            "save_path": cfg.save_path(),
        }

    def _on_save_config(self) -> None:
        config = self._build_config()
        save_logger_config(config)
        self._config_saved = True
        QMessageBox.information(
            self, "Config Saved",
            f"Configuration saved to:\n{CONFIG_PATH}",
        )

    def _on_start_trace(self) -> None:
        # 먼저 config 저장
        config = self._build_config()
        save_logger_config(config)
        self._config_saved = True
        self._start_requested = True
        # Wizard 닫기 — 호출자가 start_requested를 확인
        self.wizard().accept()

    @property
    def start_requested(self) -> bool:
        return self._start_requested


# ============================================================
# Wizard
# ============================================================
class AndroidLoggerWizard(QWizard):
    """Android Logger Setup Wizard.

    Perfetto 기반 블록 레이어 트레이스를 설정하는 5단계 위자드.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Android Logger Setup")
        self.setMinimumSize(560, 420)

        # Pages
        self.adb_page = AdbCheckPage(self)
        self.device_page = DeviceConnectionPage(self)
        self.perfetto_page = PerfettoCheckPage(self)
        self.config_page = TraceConfigPage(self)
        self.summary_page = SummaryPage(self)

        self.addPage(self.adb_page)
        self.addPage(self.device_page)
        self.addPage(self.perfetto_page)
        self.addPage(self.config_page)
        self.addPage(self.summary_page)

    @property
    def start_requested(self) -> bool:
        """Wizard 완료 후 바로 트레이스를 시작할지 여부."""
        return self.summary_page.start_requested
