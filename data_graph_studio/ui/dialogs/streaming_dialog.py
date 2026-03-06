"""
Streaming Configuration Dialog - 스트리밍 설정 다이얼로그

Allows user to configure:
- File path to watch
- Update interval (polling)
- Mode: tail (append) vs reload (full)
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPushButton,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QFileDialog,
)


class StreamingDialog(QDialog):
    """Streaming configuration dialog."""

    def __init__(
        self,
        parent=None,
        initial_path: str = "",
        initial_interval_ms: int = 1000,
        initial_mode: str = "tail",
    ):
        super().__init__(parent)
        self._file_path: Optional[str] = None
        self._interval_ms: int = initial_interval_ms
        self._mode: str = initial_mode

        self.setWindowTitle("Start Streaming")
        self.setMinimumWidth(480)
        self.setModal(True)

        self._setup_ui(initial_path, initial_interval_ms, initial_mode)

    def _setup_ui(self, initial_path: str, initial_interval_ms: int, initial_mode: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header
        header = QLabel("📡 Start Streaming")
        header.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: 600;
                color: #E6E9EF;
                padding: 8px 0;
            }
        """)
        layout.addWidget(header)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("QFrame { color: #3D4351; }")
        layout.addWidget(line)

        # Form grid
        grid = QGridLayout()
        grid.setSpacing(12)

        # File path
        file_label = QLabel("File to watch:")
        file_label.setStyleSheet("QLabel { color: #C2C8D1; font-weight: 500; }")
        grid.addWidget(file_label, 0, 0)

        file_row = QHBoxLayout()
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("Select a file to stream...")
        self._file_edit.setText(initial_path)
        self._file_edit.setMinimumWidth(280)
        file_row.addWidget(self._file_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        file_row.addWidget(browse_btn)

        grid.addLayout(file_row, 0, 1)

        # Update interval
        interval_label = QLabel("Poll interval (ms):")
        interval_label.setStyleSheet("QLabel { color: #C2C8D1; font-weight: 500; }")
        grid.addWidget(interval_label, 1, 0)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(500, 60000)
        self._interval_spin.setSingleStep(500)
        self._interval_spin.setValue(initial_interval_ms)
        self._interval_spin.setSuffix(" ms")
        grid.addWidget(self._interval_spin, 1, 1)

        # Mode
        mode_label = QLabel("Mode:")
        mode_label.setStyleSheet("QLabel { color: #C2C8D1; font-weight: 500; }")
        grid.addWidget(mode_label, 2, 0)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Tail (append only)", "tail")
        self._mode_combo.addItem("Reload (full file)", "reload")
        if initial_mode == "reload":
            self._mode_combo.setCurrentIndex(1)
        grid.addWidget(self._mode_combo, 2, 1)

        layout.addLayout(grid)

        # Description
        desc = QLabel(
            "💡 <b>Tail</b> mode watches for new rows appended to the file. "
            "<b>Reload</b> mode re-reads the entire file on any change."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            "QLabel { color: #8B919A; font-size: 12px; padding: 4px 0; }"
        )
        layout.addWidget(desc)

        layout.addStretch()

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = btn_box.button(QDialogButtonBox.Ok)
        ok_btn.setText("▶ Start Streaming")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File to Stream",
            "",
            "All Files (*);;CSV Files (*.csv);;TSV Files (*.tsv);;Text Files (*.txt *.log)",
        )
        if path:
            self._file_edit.setText(path)

    def _on_accept(self):
        path = self._file_edit.text().strip()
        if not path:
            return
        self._file_path = path
        self._interval_ms = self._interval_spin.value()
        self._mode = self._mode_combo.currentData()
        self.accept()

    @property
    def file_path(self) -> Optional[str]:
        return self._file_path

    @property
    def interval_ms(self) -> int:
        return self._interval_ms

    @property
    def mode(self) -> str:
        return self._mode
