"""ADB Trace Controller and Progress Dialog.

Raw ftrace 캡처를 위한 ADB 명령 컨트롤러와 진행 상황 다이얼로그.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class AdbTraceController(QObject):
    """ADB를 통한 ftrace 캡처 컨트롤러.

    Attributes:
        _serial: 대상 기기 시리얼.
        _sysfs_path: ftrace sysfs 경로.
        _enabled_events: 활성화된 이벤트 목록.
        _tracing: 트레이싱 진행 중 여부.
    """

    log_message = Signal(str)
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._serial: str = ""
        self._sysfs_path: str = ""
        self._enabled_events: list[str] = []
        self._tracing: bool = False

    def _run_adb_cmd(self, serial: str, shell_cmd: str) -> subprocess.CompletedProcess[str]:
        """ADB shell su 명령을 실행한다.

        Args:
            serial: 기기 시리얼 번호.
            shell_cmd: 실행할 셸 명령.

        Returns:
            CompletedProcess 결과.
        """
        quoted = shlex.quote(shell_cmd)
        cmd = ["adb", "-s", serial, "shell", "su", "-c", quoted]
        self.log_message.emit(f"$ {' '.join(cmd)}")
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )

    def _detect_sysfs_path(self, serial: str) -> str:
        """ftrace sysfs 경로를 탐지한다.

        Args:
            serial: 기기 시리얼 번호.

        Returns:
            발견된 sysfs 경로.

        Raises:
            RuntimeError: 두 경로 모두 접근 불가 시.
        """
        for path in ["/sys/kernel/tracing", "/sys/kernel/debug/tracing"]:
            result = self._run_adb_cmd(serial, f"ls {path}/trace")
            if result.returncode == 0:
                return path
        raise RuntimeError("ftrace sysfs path not found on device")

    def start_trace(self, serial: str, config: dict[str, Any]) -> None:
        """트레이스를 시작한다.

        Args:
            serial: 기기 시리얼 번호.
            config: 트레이스 설정 (buffer_size_mb, events, save_path).
        """
        self._serial = serial
        self._sysfs_path = self._detect_sysfs_path(serial)
        sysfs = self._sysfs_path

        self.progress.emit("Clearing buffer...")
        self._run_adb_cmd(serial, f"echo > {sysfs}/trace")

        kb = config.get("buffer_size_mb", 64) * 1024
        self.progress.emit(f"Setting buffer size to {kb} KB...")
        self._run_adb_cmd(serial, f"echo {kb} > {sysfs}/buffer_size_kb")

        events = config.get("events", [])
        self._enabled_events = list(events)
        for event in events:
            self.progress.emit(f"Enabling event: {event}")
            self._run_adb_cmd(serial, f"echo 1 > {sysfs}/events/{event}/enable")

        self.progress.emit("Starting trace...")
        self._run_adb_cmd(serial, f"echo 1 > {sysfs}/tracing_on")
        self._tracing = True
        self.log_message.emit("Tracing started.")

    def stop_trace(self, save_path: str) -> None:
        """트레이스를 중지하고 결과를 저장한다.

        Args:
            save_path: 트레이스 파일 저장 경로.
        """
        try:
            self.progress.emit("Stopping trace...")
            self._run_adb_cmd(self._serial, f"echo 0 > {self._sysfs_path}/tracing_on")
            self._tracing = False

            self.progress.emit("Pulling trace data...")
            result = self._run_adb_cmd(
                self._serial, f"cat {self._sysfs_path}/trace"
            )
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_text(result.stdout, encoding="utf-8")
            self.log_message.emit(f"Trace saved to {save_path}")

            self._disable_events()
            self.finished.emit(save_path)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.cleanup()

    def _disable_events(self) -> None:
        """활성화된 이벤트를 비활성화한다."""
        for event in self._enabled_events:
            try:
                self._run_adb_cmd(
                    self._serial,
                    f"echo 0 > {self._sysfs_path}/events/{event}/enable",
                )
            except Exception:
                pass

    def cleanup(self) -> None:
        """트레이싱 상태를 정리한다 (idempotent)."""
        if not self._serial or not self._sysfs_path:
            return
        try:
            if self._tracing:
                self._run_adb_cmd(
                    self._serial,
                    f"echo 0 > {self._sysfs_path}/tracing_on",
                )
                self._tracing = False
        except Exception:
            pass
        self._disable_events()


class _StopWorker(QThread):
    """stop_trace를 백그라운드에서 실행하는 워커 스레드."""

    def __init__(
        self, controller: AdbTraceController, save_path: str, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._save_path = save_path

    def run(self) -> None:
        """스레드에서 stop_trace를 실행한다."""
        self._controller.stop_trace(self._save_path)


class TraceProgressDialog(QDialog):
    """트레이스 진행 상황을 표시하는 다이얼로그.

    Attributes:
        _controller: AdbTraceController 참조.
        _start_time: 트레이스 시작 시간.
    """

    def __init__(
        self,
        controller: AdbTraceController,
        save_path: str = "",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trace Progress")
        self.setMinimumSize(480, 320)

        self._controller = controller
        self._save_path = save_path
        self._start_time = time.time()
        self._worker: _StopWorker | None = None

        layout = QVBoxLayout(self)

        self._elapsed_label = QLabel("Elapsed: 0s")
        layout.addWidget(self._elapsed_label)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setPlaceholderText("트레이스를 시작합니다...")
        layout.addWidget(self._log_text)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop)
        layout.addWidget(self._stop_btn)

        # Connect signals
        controller.log_message.connect(self._append_log)
        controller.progress.connect(self._append_log)
        controller.finished.connect(self._on_finished)
        controller.error.connect(self._on_error)

        # Timer for elapsed time
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_elapsed)
        self._timer.start(1000)

    def _append_log(self, msg: str) -> None:
        """로그 메시지를 추가한다."""
        self._log_text.append(msg)
        scrollbar = self._log_text.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def _update_elapsed(self) -> None:
        """경과 시간을 업데이트한다."""
        elapsed = int(time.time() - self._start_time)
        self._elapsed_label.setText(f"Elapsed: {elapsed}s")

    def _on_stop(self) -> None:
        """Stop 버튼 클릭 핸들러."""
        self._stop_btn.setEnabled(False)
        self._worker = _StopWorker(self._controller, self._save_path, self)
        self._worker.start()

    def _on_finished(self, path: str) -> None:
        """트레이스 완료 핸들러."""
        self._timer.stop()
        self.accept()

    def _on_error(self, msg: str) -> None:
        """에러 핸들러."""
        self._timer.stop()
        QMessageBox.critical(self, "Trace Error", msg)
        self.reject()

    def closeEvent(self, event: Any) -> None:
        """닫기 이벤트: 트레이스 중이면 확인 요청."""
        if self._controller._tracing:
            reply = QMessageBox.question(
                self,
                "Confirm",
                "트레이스가 진행 중입니다. 중지하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._controller.cleanup()
        super().closeEvent(event)
