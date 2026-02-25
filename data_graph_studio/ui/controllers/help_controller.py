"""HelpController - extracted from MainWindow."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt

from ...core.updater import (
    get_current_version, check_github_latest, is_update_available,
    download_asset, read_sha256_file, sha256sum, run_windows_installer,
)
from ..dialogs.command_palette_dialog import CommandPaletteDialog



logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..main_window import MainWindow

class HelpController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    def _show_about(self):
        """About 다이얼로그"""
        QMessageBox.about(
            self,
            "About Data Graph Studio",
            """<h2>Data Graph Studio</h2>
            <p><b>Version 0.2.0</b></p>
            <p>Big Data Visualization & Analysis Tool</p>
            <hr>
            <p>Features:</p>
            <ul>
                <li>📊 Multiple chart types (Line, Bar, Scatter, Pie, Area, Histogram)</li>
                <li>📁 Support for CSV, Excel, Parquet, JSON</li>
                <li>🔄 Drag & Drop file loading</li>
                <li>📋 Clipboard paste from Excel/Google Sheets</li>
                <li>💾 Profile save/load</li>
                <li>🖥️ CLI & Python API</li>
            </ul>
            <hr>
            <p>© 2026 Godol</p>
            <p><a href='https://github.com/SeokMinKo/data-graph-studio'>GitHub</a></p>
            """
        )
    

    def _show_quick_start(self):
        """Quick Start Guide 다이얼로그"""
        guide = """
        <h2>🚀 Quick Start Guide</h2>
        
        <h3>1. Load Data</h3>
        <ul>
            <li><b>File > Open</b> (Ctrl+O) - Open CSV, Excel, Parquet, JSON</li>
            <li><b>Drag & Drop</b> - Drag files directly into the window</li>
            <li><b>Paste</b> (Ctrl+V) - Paste data from Excel or Google Sheets</li>
        </ul>
        
        <h3>2. Create Chart</h3>
        <ul>
            <li>Select <b>X-axis column</b> from dropdown</li>
            <li>Select <b>Y-axis column(s)</b> from dropdown</li>
            <li>Choose <b>Chart Type</b> from toolbar</li>
        </ul>
        
        <h3>3. Customize</h3>
        <ul>
            <li>Zoom: Mouse wheel or drag to select area</li>
            <li>Pan: Hold right mouse button and drag</li>
            <li>Reset: Double-click on chart</li>
        </ul>
        
        <h3>4. Export</h3>
        <ul>
            <li><b>File > Export</b> - Save as PNG, CSV</li>
            <li><b>Ctrl+Shift+C</b> - Copy chart to clipboard</li>
        </ul>
        
        <h3>5. CLI Usage</h3>
        <pre>dgs plot data.csv -x Time -y Value -o chart.png</pre>
        """
        
        msg = QMessageBox(self.w)
        msg.setWindowTitle("Quick Start Guide")
        msg.setTextFormat(Qt.RichText)
        msg.setText(guide)
        msg.setIcon(QMessageBox.Information)
        msg.exec()
    

    def _on_open_command_palette(self):
        """Open the Command Palette dialog for feature search."""
        dialog = CommandPaletteDialog(self.w)
        dialog.exec()


    def _show_shortcuts(self):
        """키보드 단축키 다이얼로그"""
        shortcuts = """
        <h2>⌨️ Keyboard Shortcuts</h2>
        
        <h3>📁 File</h3>
        <table>
            <tr><td><b>Ctrl+O</b></td><td>Open file</td></tr>
            <tr><td><b>Ctrl+Shift+O</b></td><td>Open multiple files</td></tr>
            <tr><td><b>Ctrl+S</b></td><td>Save project</td></tr>
            <tr><td><b>Ctrl+E</b></td><td>Export as CSV</td></tr>
        </table>
        
        <h3>✏️ Edit</h3>
        <table>
            <tr><td><b>Ctrl+V</b></td><td>Paste data from clipboard</td></tr>
            <tr><td><b>Ctrl+C</b></td><td>Copy selected cells</td></tr>
            <tr><td><b>Ctrl+Shift+C</b></td><td>Copy chart as image</td></tr>
            <tr><td><b>Ctrl+A</b></td><td>Select all</td></tr>
            <tr><td><b>Escape</b></td><td>Clear selection</td></tr>
        </table>
        
        <h3>📊 Chart</h3>
        <table>
            <tr><td><b>1</b></td><td>Line chart</td></tr>
            <tr><td><b>2</b></td><td>Bar chart</td></tr>
            <tr><td><b>3</b></td><td>Scatter plot</td></tr>
            <tr><td><b>4</b></td><td>Pie chart</td></tr>
            <tr><td><b>5</b></td><td>Area chart</td></tr>
            <tr><td><b>6</b></td><td>Histogram</td></tr>
        </table>
        
        <h3>🔍 Navigation</h3>
        <table>
            <tr><td><b>Mouse Wheel</b></td><td>Zoom in/out</td></tr>
            <tr><td><b>Right Drag</b></td><td>Pan</td></tr>
            <tr><td><b>Double Click</b></td><td>Reset zoom</td></tr>
        </table>
        
        <h3>❓ Help</h3>
        <table>
            <tr><td><b>F1</b></td><td>Quick Start Guide</td></tr>
            <tr><td><b>Ctrl+/</b></td><td>Keyboard Shortcuts</td></tr>
        </table>
        """
        
        msg = QMessageBox(self.w)
        msg.setWindowTitle("Keyboard Shortcuts")
        msg.setTextFormat(Qt.RichText)
        msg.setText(shortcuts)
        msg.setIcon(QMessageBox.Information)
        msg.exec()
    

    def _show_tips(self):
        """Tips & Tricks 다이얼로그"""
        tips = """
        <h2>💡 Tips & Tricks</h2>
        
        <h3>🚀 Performance</h3>
        <ul>
            <li>Large files? Use <b>Parquet format</b> for 10x faster loading</li>
            <li>Sampling is automatic for datasets > 100K rows</li>
            <li>Use <b>dgs convert</b> CLI to pre-convert large files</li>
        </ul>
        
        <h3>📋 Clipboard Magic</h3>
        <ul>
            <li>Copy data from <b>Excel</b> or <b>Google Sheets</b>, then Ctrl+V</li>
            <li>Data types are auto-detected (numbers, dates, text)</li>
            <li>Ctrl+Shift+C copies chart as image for pasting into docs</li>
        </ul>
        
        <h3>📊 Chart Tips</h3>
        <ul>
            <li>Click on legend items to toggle series visibility</li>
            <li>Select multiple Y columns for comparison charts</li>
            <li>Use Bar chart for categorical X-axis data</li>
        </ul>
        
        <h3>🔧 CLI Power</h3>
        <ul>
            <li><code>dgs info file.csv</code> - Quick data summary</li>
            <li><code>dgs batch ./data/ -o ./charts/</code> - Process all files</li>
            <li><code>dgs watch file.csv -o live.png</code> - Auto-update chart</li>
        </ul>
        
        <h3>🐍 Python API</h3>
        <pre>
from data_graph_studio import plot
plot("data.csv", x="Time", y="Value", output="chart.png")
        </pre>
        """
        
        msg = QMessageBox(self.w)
        msg.setWindowTitle("Tips & Tricks")
        msg.setTextFormat(Qt.RichText)
        msg.setText(tips)
        msg.setIcon(QMessageBox.Information)
        msg.exec()
    

    def _show_whats_new(self):
        """What's New 다이얼로그"""
        whats_new = """
        <h2>🆕 What's New in v0.2</h2>
        
        <h3>✨ New Features</h3>
        <ul>
            <li><b>CLI Tool</b> - Command line interface for automation
                <br><code>dgs plot data.csv -x Time -y Value</code></li>
            <li><b>Python API</b> - Programmatic chart generation
                <br><code>from data_graph_studio import plot</code></li>
            <li><b>REST API Server</b> - HTTP endpoints for integration
                <br><code>dgs server --port 8080</code></li>
            <li><b>Clipboard Support</b> - Paste from Excel/Google Sheets</li>
            <li><b>Drag & Drop</b> - Drop files to load instantly</li>
        </ul>
        
        <h3>🔧 Improvements</h3>
        <ul>
            <li>Better performance with large datasets</li>
            <li>Improved chart rendering</li>
            <li>Enhanced tooltips and help documentation</li>
        </ul>
        
        <h3>📁 Supported Formats</h3>
        <ul>
            <li>CSV, TSV, TXT</li>
            <li>Excel (XLSX, XLS)</li>
            <li>Parquet</li>
            <li>JSON</li>
        </ul>
        """
        
        msg = QMessageBox(self.w)
        msg.setWindowTitle("What's New")
        msg.setTextFormat(Qt.RichText)
        msg.setText(whats_new)
        msg.setIcon(QMessageBox.Information)
        msg.exec()
    

    def _open_url(self, url: str):
        """URL 열기"""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    # ==================== Profile / Project File I/O ====================

    # ==================== Profile Menu Actions ====================


    def _auto_check_updates(self, force_ui: bool = False):
        """Installer-based auto-update for Windows.

        - Checks GitHub latest release for an installer asset
        - If newer version: optionally downloads and launches installer

        NOTE: This is a pragmatic approach. True background patching is out of scope.
        """
        import sys
        from PySide6.QtCore import QSettings

        if sys.platform != "win32":
            return

        settings = QSettings("Godol", "DataGraphStudio")
        update_checks_enabled = settings.value("updates/enabled", False, type=bool)
        if not update_checks_enabled:
            if force_ui:
                QMessageBox.information(
                    self.w,
                    "Updates",
                    "Update checking is currently disabled.",
                )
            return

        auto = settings.value("updates/auto", True, type=bool)
        if not auto and not force_ui:
            return

        current = get_current_version()
        try:
            info = check_github_latest()
        except Exception as e:
            logger.warning("help_controller.check_update.error", exc_info=True)
            if force_ui:
                QMessageBox.information(self, "Updates", f"Update check failed:\n{e}")
            return

        if not info:
            if force_ui:
                QMessageBox.information(self, "Updates", "No installer asset found in the latest release.")
            return

        if not is_update_available(current, info.latest_version):
            if force_ui:
                QMessageBox.information(self, "Updates", f"You're up to date.\nCurrent: {current}")
            return

        # Update available
        msg = (
            f"Update available: {current} → {info.latest_version}\n\n"
            "Download and install now?\n"
            "(The app may close and reopen after installation.)"
        )
        if not auto or force_ui:
            res = QMessageBox.question(self, "Updates", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if res != QMessageBox.StandardButton.Yes:
                return

        try:
            self.w.statusbar.showMessage(f"Downloading update {info.latest_version}...", 5000)
            installer_path = download_asset(info.asset_url, info.asset_name)
            sha_path = download_asset(info.sha256_url, info.sha256_name)

            expected = read_sha256_file(sha_path)
            actual = sha256sum(installer_path)
            if not expected or expected != actual:
                raise RuntimeError(
                    "Checksum verification failed.\n"
                    f"Expected: {expected}\n"
                    f"Actual:   {actual}"
                )

            self.w.statusbar.showMessage("Launching installer...", 5000)
            run_windows_installer(installer_path, silent=True)
            self.w.close()
        except Exception as e:
            logger.exception("help_controller.run_installer.error")
            QMessageBox.warning(self, "Updates", f"Update failed:\n{e}")

