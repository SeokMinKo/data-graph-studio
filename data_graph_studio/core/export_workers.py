"""
Export Workers — extracted from export_controller.py

Contains:
- ExportFormat enum
- ExportOptions dataclass
- ExportWorker background worker class

See export_controller.py for the Observable ExportController that orchestrates
workers on background threads.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from data_graph_studio.core.io_abstract import atomic_write, IExportRenderer
from data_graph_studio.core.metrics import get_metrics

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
# ExportWorker  (plain class, runs in threading.Thread)
# ---------------------------------------------------------------------------

class ExportWorker:
    """
    Background worker — PRD §10.5.

    Runs the actual rendering / file-writing off the main thread.
    Callbacks (on_progress, on_completed, on_failed) are invoked from the
    worker thread; callers are responsible for thread-safe dispatch if needed.
    """

    def __init__(
        self,
        task: str,          # "chart" | "data"
        image=None,
        df: Optional["pl.DataFrame"] = None,
        path: str = "",
        fmt: ExportFormat = ExportFormat.PNG,
        options: Optional[ExportOptions] = None,
        renderer: Optional[IExportRenderer] = None,
        on_progress: Optional[Callable[[int], None]] = None,
        on_completed: Optional[Callable[[str], None]] = None,
        on_failed: Optional[Callable[[str], None]] = None,
    ):
        self.task = task
        self.image = image
        self.df = df
        self.path = path
        self.fmt = fmt
        self.options = options or ExportOptions()
        self._renderer = renderer
        self._cancelled = False
        self._on_progress = on_progress or (lambda _: None)
        self._on_completed = on_completed or (lambda _: None)
        self._on_failed = on_failed or (lambda _: None)

    # -- cancel support --
    def cancel(self) -> None:
        """Signal that the export operation should be cancelled."""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        """Return True if cancellation has been requested."""
        return self._cancelled

    # -- entry point --
    def run(self) -> None:
        """Execute the export task (chart or data) on the current thread."""
        try:
            if self.task == "chart":
                self._export_chart()
            elif self.task == "data":
                self._export_data()
            else:
                raise ValueError(f"Unknown export task: {self.task}")
        except Exception as exc:
            self._on_failed(str(exc))

    # -- chart export ----------------------------------------------------------

    def _export_chart(self) -> None:
        if self._cancelled:
            self._cleanup()
            return

        if self.image is None or self.image.isNull():
            self._on_failed("Cannot export: image is null or empty.")
            return

        self._on_progress(10)  # Rendering chart...

        if self.fmt == ExportFormat.PNG:
            self._export_png()
        elif self.fmt == ExportFormat.SVG:
            self._export_svg()
        elif self.fmt == ExportFormat.PDF:
            self._export_pdf()
        else:
            self._on_failed(f"Unsupported chart format: {self.fmt.value}")
            return

        if not self._cancelled:
            self._on_progress(100)
            get_metrics().increment("export.completed")
            self._on_completed(self.path)

    def _export_png(self) -> None:
        """Render image to PNG and write atomically."""
        opts = self.options
        img = self.image

        if self._cancelled:
            self._cleanup()
            return

        self._on_progress(50)  # Writing file...

        renderer = self._get_renderer()
        data = renderer.render_to_png_with_background(
            img,
            width=opts.width or 0,
            height=opts.height or 0,
            background=opts.background,
            dpi=opts.dpi,
        )

        if self._cancelled:
            self._cleanup()
            return

        atomic_write(self.path, data)

    def _export_svg(self) -> None:
        """Render image to SVG."""
        opts = self.options
        img = self.image
        width = opts.width or img.width()
        height = opts.height or img.height()

        self._on_progress(30)

        renderer = self._get_renderer()
        data = renderer.render_to_svg(img, width, height)

        if self._cancelled:
            self._cleanup()
            return

        self._on_progress(70)
        atomic_write(self.path, data)

    def _export_pdf(self) -> None:
        """Render chart + optional stats to PDF via the renderer."""
        opts = self.options
        img = self.image

        self._on_progress(20)

        if self._cancelled:
            self._cleanup()
            return

        self._on_progress(40)

        renderer = self._get_renderer()
        width = opts.width or (img.width() if img is not None else 0)
        height = opts.height or (img.height() if img is not None else 0)
        data = renderer.render_to_pdf(img, width, height, opts)

        self._on_progress(80)

        if self._cancelled:
            self._cleanup()
            return

        atomic_write(self.path, data)

    # -- data export -----------------------------------------------------------

    def _export_data(self) -> None:
        """Export Polars DataFrame to file (CSV/Parquet/Excel)."""
        if self._cancelled:
            self._cleanup()
            return

        if self.df is None:
            self._on_failed("Cannot export: no DataFrame provided.")
            return

        self._on_progress(10)

        if self.fmt == ExportFormat.CSV:
            self._export_csv()
        elif self.fmt == ExportFormat.PARQUET:
            self._export_parquet()
        elif self.fmt == ExportFormat.EXCEL:
            self._export_excel()
        else:
            self._on_failed(f"Unsupported data format: {self.fmt.value}")
            return

        if not self._cancelled:
            self._on_progress(100)
            get_metrics().increment("export.completed")
            self._on_completed(self.path)

    def _export_csv(self) -> None:
        data = self.df.write_csv().encode("utf-8")  # type: ignore[union-attr]
        if self._cancelled:
            self._cleanup()
            return
        self._on_progress(50)
        atomic_write(self.path, data)

    def _export_parquet(self) -> None:

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
            self._on_progress(50)
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
            self._on_progress(50)
            os.rename(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

    # -- helpers ---------------------------------------------------------------

    def _get_renderer(self) -> "IExportRenderer":
        """Return the injected renderer or a default QtExportRenderer."""
        if self._renderer is not None:
            return self._renderer
        from data_graph_studio.ui.renderers.qt_export_renderer import QtExportRenderer
        return QtExportRenderer()

    def _cleanup(self) -> None:
        """Remove partial / temp files after cancel — ERR-4.2."""
        for p in (self.path, self.path + ".tmp"):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass
