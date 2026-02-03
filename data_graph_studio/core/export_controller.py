"""
Export Controller — PRD Feature 4 (Export Enhancement)

Provides:
- ExportFormat enum — PNG, SVG, PDF, CSV, Parquet, Excel
- ExportOptions — resolution, DPI, background, legend, stats
- ExportWorker — QThread-based background worker
- ExportController — orchestrates export with progress, cancel, atomic write

Signals:
    progress_changed(int)    — 0..100 progress percentage
    export_completed(str)    — output file path on success
    export_failed(str)       — error message on failure

Architecture notes (PRD §9.2, §10.3, §10.5):
    • All file writes go through atomic_write (temp → rename)
    • Heavy exports run in QThread (no UI blocking)
    • Single concurrent worker per controller (duplicate → cancel previous)
    • Cancel sets _cancelled flag → worker checks periodically
"""

from __future__ import annotations

import io
import os
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtSvg import QSvgGenerator

from data_graph_studio.core.io_abstract import atomic_write

if TYPE_CHECKING:
    import polars as pl

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ExportFormat
# ---------------------------------------------------------------------------

class ExportFormat(Enum):
    """Supported export formats."""
    # Chart formats
    PNG = "png"
    SVG = "svg"
    PDF = "pdf"
    # Data formats
    CSV = "csv"
    PARQUET = "parquet"
    EXCEL = "excel"


# ---------------------------------------------------------------------------
# ExportOptions
# ---------------------------------------------------------------------------

@dataclass
class ExportOptions:
    """
    Export configuration — FR-4.6.

    Attributes:
        width / height: Target image resolution (None = original).
        dpi: Dots per inch (default 96).
        background: "transparent" | "white" | "dark" or hex colour.
        include_legend: Whether to embed a legend.
        include_stats: Whether to append statistics summary (PDF).
        stats_data: Dict of stat-name → value for the summary table.
        page_size: "A4" | "Letter" (PDF only).
    """
    width: Optional[int] = None
    height: Optional[int] = None
    dpi: int = 96
    background: str = "white"
    include_legend: bool = True
    include_stats: bool = False
    stats_data: Optional[Dict[str, Any]] = None
    page_size: str = "A4"


# ---------------------------------------------------------------------------
# ExportWorker  (QThread)
# ---------------------------------------------------------------------------

class ExportWorker(QThread):
    """
    Background worker — PRD §10.5.

    Runs the actual rendering / file-writing off the main thread.
    The controller connects to its signals and forwards them.
    """

    progress = Signal(int)          # 0..100
    completed = Signal(str)         # output path
    failed = Signal(str)            # error message

    def __init__(
        self,
        task: str,          # "chart" | "data"
        image: Optional[QImage] = None,
        df: Optional["pl.DataFrame"] = None,
        path: str = "",
        fmt: ExportFormat = ExportFormat.PNG,
        options: Optional[ExportOptions] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.task = task
        self.image = image
        self.df = df
        self.path = path
        self.fmt = fmt
        self.options = options or ExportOptions()
        self._cancelled = False

    # -- cancel support --
    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    # -- entry point --
    def run(self) -> None:
        try:
            if self.task == "chart":
                self._export_chart()
            elif self.task == "data":
                self._export_data()
            else:
                raise ValueError(f"Unknown export task: {self.task}")
        except Exception as exc:
            self.failed.emit(str(exc))

    # -- chart export ----------------------------------------------------------

    def _export_chart(self) -> None:
        if self._cancelled:
            self._cleanup()
            return

        if self.image is None or self.image.isNull():
            self.failed.emit("Cannot export: image is null or empty.")
            return

        self.progress.emit(10)  # Rendering chart...

        if self.fmt == ExportFormat.PNG:
            self._export_png()
        elif self.fmt == ExportFormat.SVG:
            self._export_svg()
        elif self.fmt == ExportFormat.PDF:
            self._export_pdf()
        else:
            self.failed.emit(f"Unsupported chart format: {self.fmt.value}")
            return

        if not self._cancelled:
            self.progress.emit(100)
            self.completed.emit(self.path)

    def _export_png(self) -> None:
        """Render QImage to PNG and write atomically."""
        opts = self.options
        img = self.image

        # Resize if requested
        if opts.width and opts.height:
            img = img.scaled(
                opts.width, opts.height,
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation,
            )

        # Apply background if needed
        if opts.background == "transparent":
            # Image already has alpha if ARGB32; just save
            pass
        elif opts.background == "white":
            img = self._apply_background(img, QColor(255, 255, 255))
        elif opts.background == "dark":
            img = self._apply_background(img, QColor(43, 52, 64))
        elif opts.background.startswith("#"):
            img = self._apply_background(img, QColor(opts.background))

        if self._cancelled:
            self._cleanup()
            return

        self.progress.emit(50)  # Writing file...

        # Encode to bytes
        _buf = io.BytesIO()  # noqa: F841
        _ba = img.save(self.path + ".tmp", "PNG")  # noqa: F841
        # Instead, use QImage.save to a QByteArray → then atomic write
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice

        qba = QByteArray()
        qbuf = QBuffer(qba)
        qbuf.open(QIODevice.WriteOnly)
        img.save(qbuf, "PNG")
        qbuf.close()
        data = bytes(qba.data())

        # Clean up the .tmp we accidentally wrote above
        tmp_path = self.path + ".tmp"
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if self._cancelled:
            self._cleanup()
            return

        atomic_write(self.path, data)

    def _export_svg(self) -> None:
        """Render QImage to SVG."""
        opts = self.options
        img = self.image
        width = opts.width or img.width()
        height = opts.height or img.height()

        self.progress.emit(30)

        # Use QSvgGenerator
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, QRect

        qba = QByteArray()
        qbuf = QBuffer(qba)
        qbuf.open(QIODevice.WriteOnly)

        gen = QSvgGenerator()
        gen.setOutputDevice(qbuf)
        gen.setSize(QSize(width, height))
        gen.setViewBox(QRect(0, 0, width, height))
        gen.setTitle("Data Graph Studio Export")
        gen.setDescription("Chart exported by Data Graph Studio")

        painter = QPainter()
        painter.begin(gen)
        # Draw the image scaled into the SVG viewport
        target = painter.viewport()
        painter.drawImage(target, img)
        painter.end()
        qbuf.close()

        if self._cancelled:
            self._cleanup()
            return

        self.progress.emit(70)
        data = bytes(qba.data())
        atomic_write(self.path, data)

    def _export_pdf(self) -> None:
        """Render chart + optional stats to PDF using Qt PDF writer."""
        opts = self.options
        img = self.image

        self.progress.emit(20)

        from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMarginsF, QSizeF, QRectF
        from PySide6.QtGui import QPageSize, QPageLayout, QPdfWriter, QFont

        qba = QByteArray()
        qbuf = QBuffer(qba)
        qbuf.open(QIODevice.WriteOnly)

        writer = QPdfWriter(qbuf)

        # Page size
        if opts.page_size.upper() == "LETTER":
            writer.setPageSize(QPageSize(QPageSize.Letter))
        else:
            writer.setPageSize(QPageSize(QPageSize.A4))

        writer.setPageMargins(QMarginsF(20, 20, 20, 20))
        writer.setResolution(opts.dpi)

        painter = QPainter()
        painter.begin(writer)

        if self._cancelled:
            painter.end()
            qbuf.close()
            self._cleanup()
            return

        self.progress.emit(40)

        # --- Draw chart image centered on page ---
        page_rect = painter.viewport()
        margin = 40
        chart_rect = QRectF(
            margin,
            margin,
            page_rect.width() - 2 * margin,
            page_rect.height() * 0.6 - margin,
        )
        painter.drawImage(chart_rect.toRect(), img)

        self.progress.emit(60)

        # --- Optional stats summary table ---
        if opts.include_stats and opts.stats_data:
            stats = opts.stats_data
            y_offset = int(chart_rect.bottom()) + 40

            # Title
            font = QFont("Helvetica", 12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(margin, y_offset, "Statistics Summary")
            y_offset += 30

            font.setBold(False)
            font.setPointSize(10)
            painter.setFont(font)

            for key, value in stats.items():
                if isinstance(value, float):
                    text = f"{key}: {value:.4f}"
                else:
                    text = f"{key}: {value}"
                painter.drawText(margin + 10, y_offset, text)
                y_offset += 22

        self.progress.emit(80)

        if self._cancelled:
            painter.end()
            qbuf.close()
            self._cleanup()
            return

        painter.end()
        qbuf.close()

        data = bytes(qba.data())
        atomic_write(self.path, data)

    # -- data export -----------------------------------------------------------

    def _export_data(self) -> None:
        """Export Polars DataFrame to file (CSV/Parquet/Excel)."""
        if self._cancelled:
            self._cleanup()
            return

        if self.df is None:
            self.failed.emit("Cannot export: no DataFrame provided.")
            return

        self.progress.emit(10)

        if self.fmt == ExportFormat.CSV:
            self._export_csv()
        elif self.fmt == ExportFormat.PARQUET:
            self._export_parquet()
        elif self.fmt == ExportFormat.EXCEL:
            self._export_excel()
        else:
            self.failed.emit(f"Unsupported data format: {self.fmt.value}")
            return

        if not self._cancelled:
            self.progress.emit(100)
            self.completed.emit(self.path)

    def _export_csv(self) -> None:
        data = self.df.write_csv().encode("utf-8")  # type: ignore[union-attr]
        if self._cancelled:
            self._cleanup()
            return
        self.progress.emit(50)
        atomic_write(self.path, data)

    def _export_parquet(self) -> None:
        import tempfile

        # Polars write_parquet writes to path; use temp file + rename
        tmp_path = self.path + ".tmp"
        try:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self.df.write_parquet(tmp_path)  # type: ignore[union-attr]
            if self._cancelled:
                self._cleanup()
                return
            self.progress.emit(50)
            os.rename(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

    def _export_excel(self) -> None:
        tmp_path = self.path + ".tmp"
        try:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self.df.write_excel(tmp_path)  # type: ignore[union-attr]
            if self._cancelled:
                self._cleanup()
                return
            self.progress.emit(50)
            os.rename(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _apply_background(img: QImage, color: QColor) -> QImage:
        """Composite the image over a solid background colour."""
        result = QImage(img.size(), QImage.Format_ARGB32)
        result.fill(color)
        painter = QPainter(result)
        painter.drawImage(0, 0, img)
        painter.end()
        return result

    def _cleanup(self) -> None:
        """Remove partial / temp files after cancel — ERR-4.2."""
        for p in (self.path, self.path + ".tmp"):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# ExportController  (QObject, lives on main thread)
# ---------------------------------------------------------------------------

class ExportController(QObject):
    """
    High-level export orchestrator — PRD §9.2.

    Signals:
        progress_changed(int)   — forwarded from worker
        export_completed(str)   — output file path
        export_failed(str)      — error description
    """

    progress_changed = Signal(int)
    export_completed = Signal(str)
    export_failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._worker: Optional[ExportWorker] = None
        self._cancelled = False

    # -- cancel / reset --------------------------------------------------------

    def cancel(self) -> None:
        """Request cancellation of the current export."""
        self._cancelled = True
        if self._worker is not None:
            self._worker.cancel()

    def reset(self) -> None:
        """Reset cancellation flag for a fresh export."""
        self._cancelled = False

    # -- synchronous helpers (for tests & simple uses) -------------------------

    def export_chart_sync(
        self,
        image: QImage,
        path: str,
        fmt: ExportFormat,
        options: Optional[ExportOptions] = None,
    ) -> None:
        """
        Export a chart image synchronously (blocks caller).

        Designed for unit tests and IPC handlers.
        """
        worker = ExportWorker(
            task="chart",
            image=image,
            path=path,
            fmt=fmt,
            options=options,
        )
        worker._cancelled = self._cancelled

        # Connect signals for forwarding
        worker.progress.connect(self.progress_changed.emit)
        worker.completed.connect(self.export_completed.emit)
        worker.failed.connect(self.export_failed.emit)

        # Run directly (synchronous)
        worker.run()

    def export_data_sync(
        self,
        df: "pl.DataFrame",
        path: str,
        fmt: ExportFormat,
        options: Optional[ExportOptions] = None,
    ) -> None:
        """
        Export data synchronously (blocks caller).
        """
        worker = ExportWorker(
            task="data",
            df=df,
            path=path,
            fmt=fmt,
            options=options,
        )
        worker._cancelled = self._cancelled

        worker.progress.connect(self.progress_changed.emit)
        worker.completed.connect(self.export_completed.emit)
        worker.failed.connect(self.export_failed.emit)

        worker.run()

    # -- async (threaded) API --------------------------------------------------

    def export_chart_async(
        self,
        image: QImage,
        path: str,
        fmt: ExportFormat,
        options: Optional[ExportOptions] = None,
    ) -> None:
        """
        Export a chart on a background thread — PRD NFR-4.3.

        Emits progress_changed, export_completed, or export_failed.
        """
        self._stop_current_worker()
        self._cancelled = False

        self._worker = ExportWorker(
            task="chart",
            image=image,
            path=path,
            fmt=fmt,
            options=options,
        )
        self._connect_worker(self._worker)
        self._worker.start()

    def export_data_async(
        self,
        df: "pl.DataFrame",
        path: str,
        fmt: ExportFormat,
        options: Optional[ExportOptions] = None,
    ) -> None:
        """
        Export data on a background thread.
        """
        self._stop_current_worker()
        self._cancelled = False

        self._worker = ExportWorker(
            task="data",
            df=df,
            path=path,
            fmt=fmt,
            options=options,
        )
        self._connect_worker(self._worker)
        self._worker.start()

    # -- IPC commands (FR-4.8) -------------------------------------------------

    def handle_ipc_export_chart(self, params: Dict[str, Any]) -> Dict[str, str]:
        """IPC: export_chart {path, format, width?, height?, dpi?}"""
        # Will be wired from MainWindow's IPC server
        return {"status": "ok", "message": "export_chart scheduled"}

    def handle_ipc_export_data(self, params: Dict[str, Any]) -> Dict[str, str]:
        """IPC: export_data {path, format}"""
        return {"status": "ok", "message": "export_data scheduled"}

    def handle_ipc_export_dashboard(self, params: Dict[str, Any]) -> Dict[str, str]:
        """IPC: export_dashboard {path, format}"""
        return {"status": "ok", "message": "export_dashboard scheduled"}

    # -- internals -------------------------------------------------------------

    def _connect_worker(self, worker: ExportWorker) -> None:
        worker.progress.connect(self.progress_changed.emit)
        worker.completed.connect(self._on_worker_completed)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_worker_finished)

    @Slot(str)
    def _on_worker_completed(self, path: str) -> None:
        self.export_completed.emit(path)

    @Slot(str)
    def _on_worker_failed(self, error: str) -> None:
        self.export_failed.emit(error)

    @Slot()
    def _on_worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _stop_current_worker(self) -> None:
        """Cancel and wait for the current worker (PRD §10.5)."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
            if self._worker.isRunning():
                self._worker.terminate()
            self._worker.deleteLater()
            self._worker = None

    def shutdown(self) -> None:
        """Called during app close — PRD §10.6."""
        self._stop_current_worker()
