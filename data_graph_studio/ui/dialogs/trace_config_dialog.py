"""Perfetto-style Trace Configuration Dialog.

Single-page dialog with left category sidebar + right settings panel.
Replaces the old multi-page AndroidLoggerWizard.
"""

from __future__ import annotations

import datetime
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from PySide6.QtCore import QProcess, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ── Config paths ──────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".data_graph_studio"
CONFIG_PATH = CONFIG_DIR / "logger_config.json"

# ── Default events ────────────────────────────────────────────
DEFAULT_EVENTS: list[tuple[str, bool]] = [
    ("block/block_rq_issue", True),
    ("block/block_rq_complete", True),
    ("ufs/ufshcd_command", True),
    ("block/block_bio_complete", False),
    ("block/block_bio_queue", False),
    ("block/block_rq_requeue", False),
]

_DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "device_serial": "",
    "capture_mode": "perfetto",
    "sysfs_path": "/sys/kernel/tracing",
    "buffer_size_mb": 64,
    "events": [name for name, on in DEFAULT_EVENTS if on],
    "save_path": "",
}

ADB_SCAN_TIMEOUT_MS = 5000


# ── Config utilities ──────────────────────────────────────────

def migrate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Migrate config from v0 (no version key) to v1.

    Returns a new dict — does not mutate the input.
    """
    config = dict(config)  # Shallow copy to avoid mutating caller's dict
    version = config.get("version", 0)
    if version < 1:
        config.setdefault("capture_mode", "perfetto")
        config.setdefault("sysfs_path", "/sys/kernel/tracing")
        config["version"] = 1
    return config


def load_logger_config() -> dict[str, Any]:
    """Load saved logger config. Returns defaults on missing/corrupt file."""
    if CONFIG_PATH.exists():
        try:
            raw = CONFIG_PATH.read_text(encoding="utf-8")
            config = json.loads(raw)
            if not isinstance(config, dict):
                raise ValueError("Config root is not a dict")
            return migrate_config(config)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Failed to load logger config: %s", exc)
    return migrate_config(dict(_DEFAULT_CONFIG))


def save_logger_config(config: dict[str, Any]) -> None:
    """Save logger config to JSON file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Panels ────────────────────────────────────────────────────

class ConnectionPanel(QWidget):
    """ADB status + device selection panel."""

    device_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # ADB status
        self._adb_status = QLabel()
        self._adb_status.setWordWrap(True)
        layout.addWidget(self._adb_status)

        self._adb_info = QLabel()
        self._adb_info.setWordWrap(True)
        self._adb_info.setTextFormat(Qt.TextFormat.RichText)
        self._adb_info.setOpenExternalLinks(True)
        layout.addWidget(self._adb_info)

        # Device list
        layout.addWidget(QLabel("Connected Devices:"))
        self._device_list = QListWidget()
        self._device_list.currentItemChanged.connect(
            lambda *_: self.device_changed.emit()
        )
        layout.addWidget(self._device_list)

        # Spinner label (hidden by default)
        self._spinner_label = QLabel("⏳ Scanning devices...")
        self._spinner_label.setVisible(False)
        layout.addWidget(self._spinner_label)

        # Refresh button
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_devices)
        layout.addWidget(self._refresh_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

        # QProcess for async ADB scan
        self._scan_process: QProcess | None = None
        self._scan_timer: QTimer | None = None
        self._adb_found = False

    def initialize(self) -> None:
        """Check ADB and scan devices."""
        logger.debug("[TraceConfig] ConnectionPanel.initialize()")
        self._check_adb()
        if self._adb_found:
            self.refresh_devices()

    def _check_adb(self) -> None:
        adb_path = shutil.which("adb")
        if adb_path:
            self._adb_found = True
            self._adb_status.setText(f"✅ adb found: {adb_path}")
            self._adb_info.setText("")
        else:
            self._adb_found = False
            self._adb_status.setText("❌ adb not found in PATH.")
            self._adb_info.setText(
                "<b>Install Android SDK Platform Tools:</b><br>"
                "<code>brew install android-platform-tools</code><br><br>"
                "Or download from: "
                '<a href="https://developer.android.com/tools/releases/'
                'platform-tools">Android Platform Tools</a>'
            )

    def refresh_devices(self) -> None:
        """Start async ADB device scan."""
        if not self._adb_found:
            return
        self._kill_scan()
        self._device_list.clear()
        self._spinner_label.setVisible(True)
        self._refresh_btn.setEnabled(False)

        proc = QProcess(self)
        proc.setProgram("adb")
        proc.setArguments(["devices", "-l"])
        proc.finished.connect(self._on_scan_finished)
        self._scan_process = proc

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(ADB_SCAN_TIMEOUT_MS)
        timer.timeout.connect(self._on_scan_timeout)
        self._scan_timer = timer

        proc.start()
        timer.start()

    def _on_scan_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self._stop_timer()
        self._spinner_label.setVisible(False)
        self._refresh_btn.setEnabled(True)

        if self._scan_process is None:
            return

        stdout = bytes(self._scan_process.readAllStandardOutput()).decode(errors="replace")
        stderr = bytes(self._scan_process.readAllStandardError()).decode(errors="replace")
        self._scan_process = None

        if exit_code != 0:
            msg = stderr.strip() or f"adb exited with code {exit_code}"
            self._adb_info.setText(f"⚠️ ADB error: {msg}")
            logger.warning("ADB device scan failed (exit %d): %s", exit_code, msg)
            return

        self._parse_device_output(stdout)

    def _parse_device_output(self, stdout: str) -> None:
        """Parse `adb devices -l` output into list items."""
        logger.debug("[TraceConfig] parsing device output:\n%s", stdout[:500])
        for line in stdout.strip().split("\n")[1:]:
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

        if self._device_list.count() == 0:
            self._adb_info.setText(
                "No devices found. Connect via USB and enable USB Debugging."
            )
        else:
            self._adb_info.setText("")
            self._device_list.setCurrentRow(0)

    def _on_scan_timeout(self) -> None:
        self._kill_scan()
        self._spinner_label.setVisible(False)
        self._refresh_btn.setEnabled(True)
        self._adb_info.setText("⚠️ Scan timed out. Click Refresh to retry.")
        logger.warning("ADB device scan timed out after %d ms", ADB_SCAN_TIMEOUT_MS)

    def _kill_scan(self) -> None:
        """Kill any running scan process and timer."""
        self._stop_timer()
        if self._scan_process is not None:
            try:
                self._scan_process.kill()
                self._scan_process.waitForFinished(1000)
            except RuntimeError:
                pass
            self._scan_process = None

    def _stop_timer(self) -> None:
        if self._scan_timer is not None:
            self._scan_timer.stop()
            self._scan_timer = None

    @property
    def adb_found(self) -> bool:
        return self._adb_found

    def selected_serial(self) -> str:
        item = self._device_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def set_device_serial(self, serial: str) -> None:
        """Select device by serial. No-op if not found."""
        for i in range(self._device_list.count()):
            item = self._device_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == serial:
                self._device_list.setCurrentRow(i)
                return

    def cleanup(self) -> None:
        """Kill running processes — called on dialog close."""
        self._kill_scan()


class CaptureModePanel(QWidget):
    """Perfetto / Raw Ftrace mode selection + validity checks."""

    mode_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        mode_group = QGroupBox("Capture Mode")
        mode_layout = QVBoxLayout(mode_group)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Perfetto (no root needed)", "perfetto")
        self._mode_combo.addItem("Raw Ftrace (requires root)", "raw_ftrace")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_index_changed)
        mode_layout.addWidget(self._mode_combo)

        self._mode_desc = QLabel()
        self._mode_desc.setWordWrap(True)
        mode_layout.addWidget(self._mode_desc)
        layout.addWidget(mode_group)

        # Check status
        self._check_label = QLabel()
        self._check_label.setWordWrap(True)
        layout.addWidget(self._check_label)

        self._check_spinner = QLabel("⏳ Checking...")
        self._check_spinner.setVisible(False)
        layout.addWidget(self._check_spinner)

        recheck_btn = QPushButton("Re-check")
        recheck_btn.clicked.connect(self.run_check)
        layout.addWidget(recheck_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

        self._check_process: QProcess | None = None
        self._check_timer: QTimer | None = None
        self._check_passed = False
        self._root_fallback_tried = False
        self._serial_getter: Any = None  # callable returning serial

        self._update_description()

    def set_serial_getter(self, getter: Any) -> None:
        """Provide a callable that returns the current device serial."""
        self._serial_getter = getter

    def _on_mode_index_changed(self, _index: int) -> None:
        self._update_description()
        self._check_passed = False
        self._check_label.setText("")
        self.mode_changed.emit(self.capture_mode())

    def _update_description(self) -> None:
        mode = self.capture_mode()
        if mode == "perfetto":
            self._mode_desc.setText(
                "Uses Perfetto tracing system (Android 9+). "
                "No root required. Recommended."
            )
        else:
            self._mode_desc.setText(
                "Reads raw ftrace buffer via sysfs. "
                "Requires root (su) access on device."
            )

    def capture_mode(self) -> str:
        return self._mode_combo.currentData() or "perfetto"

    def set_capture_mode(self, mode: str) -> None:
        idx = self._mode_combo.findData(mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)

    @property
    def check_passed(self) -> bool:
        return self._check_passed

    def run_check(self) -> None:
        """Run perfetto/root check for current mode + device."""
        self._kill_check()
        serial = self._serial_getter() if self._serial_getter else ""
        if not serial:
            self._check_label.setText("⚠️ No device selected.")
            self._check_passed = False
            return

        self._check_spinner.setVisible(True)
        mode = self.capture_mode()

        proc = QProcess(self)
        proc.setProgram("adb")
        if mode == "perfetto":
            proc.setArguments(["-s", serial, "shell", "which", "perfetto"])
        else:
            # Try 'su -c id' first; fallback to 'su 0 id' in _on_check_finished
            proc.setArguments(["-s", serial, "shell", "su", "-c", "id"])
        proc.finished.connect(self._on_check_finished)
        self._check_process = proc
        self._root_fallback_tried = False

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(ADB_SCAN_TIMEOUT_MS)
        timer.timeout.connect(self._on_check_timeout)
        self._check_timer = timer

        proc.start()
        timer.start()

    def _on_check_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self._stop_check_timer()
        self._check_spinner.setVisible(False)
        if self._check_process is None:
            return

        stdout = bytes(self._check_process.readAllStandardOutput()).decode(errors="replace")
        self._check_process = None
        mode = self.capture_mode()

        if mode == "perfetto":
            if exit_code == 0 and stdout.strip():
                self._check_passed = True
                self._check_label.setText(f"✅ perfetto found: {stdout.strip()}")
            else:
                self._check_passed = False
                self._check_label.setText(
                    "❌ perfetto not found. Requires Android 9+."
                )
        else:
            if exit_code == 0 and "uid=0" in stdout:
                self._check_passed = True
                self._check_label.setText("✅ Root access confirmed.")
            elif not self._root_fallback_tried:
                # Fallback: try 'su 0 id' for older Magisk/SuperSU
                self._root_fallback_tried = True
                serial = self._serial_getter() if self._serial_getter else ""
                if serial:
                    proc = QProcess(self)
                    proc.setProgram("adb")
                    proc.setArguments(["-s", serial, "shell", "su", "0", "id"])
                    proc.finished.connect(self._on_check_finished)
                    self._check_process = proc
                    proc.start()
                    return  # Wait for fallback result
                else:
                    self._check_passed = False
                    self._check_label.setText(
                        "❌ Root access not available. Install Magisk or SuperSU."
                    )
            else:
                self._check_passed = False
                self._check_label.setText(
                    "❌ Root access not available. Install Magisk or SuperSU."
                )

    def _on_check_timeout(self) -> None:
        self._kill_check()
        self._check_spinner.setVisible(False)
        self._check_passed = False
        self._check_label.setText("⚠️ Check timed out.")

    def _kill_check(self) -> None:
        self._stop_check_timer()
        if self._check_process is not None:
            try:
                self._check_process.kill()
                self._check_process.waitForFinished(1000)
            except RuntimeError:
                pass
            self._check_process = None

    def _stop_check_timer(self) -> None:
        if self._check_timer is not None:
            self._check_timer.stop()
            self._check_timer = None

    def cleanup(self) -> None:
        self._kill_check()


class EventsPanel(QWidget):
    """Ftrace event selection panel."""

    events_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select ftrace events to capture:"))

        self._event_checks: list[tuple[str, QCheckBox]] = []
        for name, default_on in DEFAULT_EVENTS:
            cb = QCheckBox(name)
            cb.setChecked(default_on)
            cb.stateChanged.connect(lambda *_: self.events_changed.emit())
            layout.addWidget(cb)
            self._event_checks.append((name, cb))

        self._warning_label = QLabel()
        self._warning_label.setStyleSheet("color: red;")
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

        layout.addStretch()

    def selected_events(self) -> list[str]:
        return [name for name, cb in self._event_checks if cb.isChecked()]

    def set_events(self, events: list[str]) -> None:
        enabled = set(events)
        for name, cb in self._event_checks:
            cb.setChecked(name in enabled)

    def show_warning(self, msg: str) -> None:
        self._warning_label.setText(msg)
        self._warning_label.setVisible(True)

    def hide_warning(self) -> None:
        self._warning_label.setVisible(False)

    @property
    def has_events(self) -> bool:
        return len(self.selected_events()) > 0


class OutputPanel(QWidget):
    """Buffer size + save path panel."""

    output_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Buffer size
        buf_group = QGroupBox("Buffer Size")
        buf_layout = QHBoxLayout(buf_group)
        buf_layout.addWidget(QLabel("Ring buffer:"))
        self._buffer_spin = QSpinBox()
        self._buffer_spin.setRange(4, 512)
        self._buffer_spin.setValue(64)
        self._buffer_spin.setSuffix(" MB")
        self._buffer_spin.valueChanged.connect(lambda *_: self.output_changed.emit())
        buf_layout.addWidget(self._buffer_spin)
        buf_layout.addStretch()
        layout.addWidget(buf_group)

        # Save path
        path_group = QGroupBox("Output File")
        path_layout = QHBoxLayout(path_group)
        self._save_path_edit = QLineEdit()
        self._save_path_edit.setPlaceholderText("Trace file save location...")
        self._save_path_edit.textChanged.connect(lambda *_: self.output_changed.emit())
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self._save_path_edit, stretch=1)
        path_layout.addWidget(browse_btn)
        layout.addWidget(path_group)

        layout.addStretch()

    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Trace File",
            self._save_path_edit.text(),
            "CSV (*.csv);;Perfetto Trace (*.perfetto-trace);;Ftrace Text (*.txt);;All Files (*)",
        )
        if path:
            self._save_path_edit.setText(path)

    def buffer_size_mb(self) -> int:
        return self._buffer_spin.value()

    def set_buffer_size_mb(self, val: int) -> None:
        self._buffer_spin.setValue(max(4, min(512, val)))

    def save_path(self) -> str:
        return self._save_path_edit.text()

    def set_save_path(self, path: str) -> None:
        self._save_path_edit.setText(path)


# ── Category indices ──────────────────────────────────────────
CAT_CONNECTION = 0
CAT_CAPTURE_MODE = 1
CAT_EVENTS = 2
CAT_OUTPUT = 3

_CATEGORIES = [
    ("🔌 Connection", CAT_CONNECTION),
    ("📡 Capture Mode", CAT_CAPTURE_MODE),
    ("📋 Events", CAT_EVENTS),
    ("💾 Output", CAT_OUTPUT),
]


# ── Main Dialog ───────────────────────────────────────────────

class TraceConfigDialog(QDialog):
    """Perfetto-style trace configuration dialog.

    Left category sidebar (180 px) + right settings panel + bottom buttons.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trace Configuration")
        self.setMinimumSize(700, 500)

        self._dirty = False
        self._start_requested = False
        self._saved_config: dict[str, Any] = {}

        self._build_ui()
        self._connect_signals()
        self._load_and_apply_config()

    # ── UI construction ───────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Main area: sidebar + stacked panels
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Left sidebar
        self._category_list = QListWidget()
        self._category_list.setFixedWidth(180)
        self._category_list.setStyleSheet(
            "QListWidget { background-color: palette(alternate-base); }"
        )
        for label, _idx in _CATEGORIES:
            self._category_list.addItem(label)
        self._category_list.setCurrentRow(0)
        main_layout.addWidget(self._category_list)

        # Right stacked panels
        self._stack = QStackedWidget()
        self.connection_panel = ConnectionPanel()
        self.capture_panel = CaptureModePanel()
        self.events_panel = EventsPanel()
        self.output_panel = OutputPanel()

        self._stack.addWidget(self.connection_panel)
        self._stack.addWidget(self.capture_panel)
        self._stack.addWidget(self.events_panel)
        self._stack.addWidget(self.output_panel)

        main_layout.addWidget(self._stack, stretch=1)
        root.addLayout(main_layout, stretch=1)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(8, 4, 8, 8)

        self._start_btn = QPushButton("Start Recording")
        self._start_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "padding: 6px 16px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #A5D6A7; }"
        )
        self._save_btn = QPushButton("Save Config")
        self._close_btn = QPushButton("Close")

        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._save_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._close_btn)
        root.addLayout(btn_layout)

    def _connect_signals(self) -> None:
        self._category_list.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._start_btn.clicked.connect(self._on_start)
        self._save_btn.clicked.connect(self._on_save)
        self._close_btn.clicked.connect(self.close)

        # Wire capture panel serial getter
        self.capture_panel.set_serial_getter(self.connection_panel.selected_serial)

        # Auto-run check on mode change
        self.capture_panel.mode_changed.connect(lambda _: self.capture_panel.run_check())

        # Dirty tracking (lambda wrappers to discard signal args safely)
        self.connection_panel.device_changed.connect(self._mark_dirty)
        self.capture_panel.mode_changed.connect(lambda _mode: self._mark_dirty())
        self.events_panel.events_changed.connect(self._mark_dirty)
        self.output_panel.output_changed.connect(self._mark_dirty)

    # ── Config management ─────────────────────────────────────

    def _load_and_apply_config(self) -> None:
        config = load_logger_config()
        self.set_config(config)
        self._saved_config = dict(config)
        self._dirty = False
        self.connection_panel.initialize()

    def get_config(self) -> dict[str, Any]:
        """Collect current config from all panels."""
        return {
            "version": 1,
            "device_serial": self.connection_panel.selected_serial(),
            "capture_mode": self.capture_panel.capture_mode(),
            "sysfs_path": "/sys/kernel/tracing",
            "buffer_size_mb": self.output_panel.buffer_size_mb(),
            "events": self.events_panel.selected_events(),
            "save_path": self.output_panel.save_path(),
        }

    def set_config(self, config: dict[str, Any]) -> None:
        """Apply config values to all panels."""
        config = migrate_config(dict(config))

        if config.get("device_serial"):
            self.connection_panel.set_device_serial(config["device_serial"])
        if config.get("capture_mode"):
            self.capture_panel.set_capture_mode(config["capture_mode"])
        if config.get("events"):
            self.events_panel.set_events(config["events"])
        if "buffer_size_mb" in config:
            self.output_panel.set_buffer_size_mb(config["buffer_size_mb"])
        if config.get("save_path"):
            self.output_panel.set_save_path(config["save_path"])

    def is_dirty(self) -> bool:
        return self._dirty

    def _mark_dirty(self, *_args: Any) -> None:
        self._dirty = True

    @property
    def start_requested(self) -> bool:
        return self._start_requested

    # ── Validation ────────────────────────────────────────────

    def _validate(self) -> bool:
        """Validate config. On failure, navigate to problem category."""
        logger.debug("[TraceConfig] validating: adb=%s, device=%s, events=%d, save=%s",
                     self.connection_panel.adb_found,
                     self.connection_panel.selected_serial(),
                     len(self.events_panel.selected_events()),
                     self.output_panel.save_path())
        # EC-1: ADB not installed
        if not self.connection_panel.adb_found:
            self._category_list.setCurrentRow(CAT_CONNECTION)
            QMessageBox.warning(
                self, "Validation",
                "ADB is not installed. Install it first.",
            )
            return False

        # EC-2: No device
        if not self.connection_panel.selected_serial():
            self._category_list.setCurrentRow(CAT_CONNECTION)
            QMessageBox.warning(
                self, "Validation",
                "No device selected. Connect a device and refresh.",
            )
            return False

        # EC-8: No events
        if not self.events_panel.has_events:
            self._category_list.setCurrentRow(CAT_EVENTS)
            self.events_panel.show_warning("Select at least one event.")
            QMessageBox.warning(
                self, "Validation",
                "Select at least one ftrace event.",
            )
            return False
        self.events_panel.hide_warning()

        # EC-5: Empty save path → auto file dialog
        if not self.output_panel.save_path():
            self._category_list.setCurrentRow(CAT_OUTPUT)
            is_perfetto = self.capture_panel.capture_mode() == "perfetto"
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            if is_perfetto:
                default_name = f"trace_{ts}.csv"
                filt = "CSV (*.csv);;All Files (*)"
            else:
                default_name = f"ftrace_{ts}.txt"
                filt = "Ftrace Text (*.txt);;All Files (*)"

            path, _ = QFileDialog.getSaveFileName(
                self, "Save Trace File", default_name, filt,
            )
            if not path:
                return False
            self.output_panel.set_save_path(path)

        return True

    # ── Button handlers ───────────────────────────────────────

    def _on_start(self) -> None:
        """Start Recording: validate → save → disable button → accept."""
        logger.debug("[TraceConfig] Start Recording clicked")
        if not self._validate():
            logger.debug("[TraceConfig] validation failed, aborting start")
            return
        # FR-14: immediate disable to prevent double-click
        self._start_btn.setEnabled(False)
        self._start_requested = True

        config = self.get_config()
        logger.info("[TraceConfig] starting with config: mode=%s, device=%s, events=%d, save=%s",
                    config.get("capture_mode"), config.get("device_serial"),
                    len(config.get("events", [])), config.get("save_path"))
        save_logger_config(config)
        self._saved_config = dict(config)
        self._dirty = False
        self.accept()

    def _on_save(self) -> None:
        config = self.get_config()
        save_logger_config(config)
        self._saved_config = dict(config)
        self._dirty = False
        QMessageBox.information(
            self, "Config Saved",
            f"Configuration saved to:\n{CONFIG_PATH}",
        )

    # ── Close handling (FR-15, NFR-7) ─────────────────────────

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Handle close: unsaved warning + process cleanup."""
        if self._dirty:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Save:
                self._on_save()

        # NFR-7: kill running processes
        self.connection_panel.cleanup()
        self.capture_panel.cleanup()
        super().closeEvent(event)
