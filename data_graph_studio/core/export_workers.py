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
from typing import Any, Callable, Dict, Optional

from data_graph_studio.core.io_abstract import atomic_write, IExportRenderer
from data_graph_studio.core.metrics import get_metrics
from data_graph_studio.core.exceptions import ExportError

import polars as pl

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Export progress checkpoints (passed to _on_progress; 0–100)
# ---------------------------------------------------------------------------
_PROGRESS_RENDER_START: int = 10    # format dispatch done, rendering begins
_PROGRESS_SVG_RENDER: int = 30      # SVG render complete, about to write
_PROGRESS_SVG_WRITE: int = 70       # SVG written
_PROGRESS_PDF_PHASE1: int = 20      # PDF setup complete
_PROGRESS_PDF_PHASE2: int = 40      # PDF render started
_PROGRESS_PDF_FINALIZE: int = 80    # PDF render done, about to write
_PROGRESS_WRITE_MIDPOINT: int = 50  # file write in progress (CSV/PNG/Parquet/Excel)
_PROGRESS_DONE: int = 100           # export complete


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
                raise ExportError(
                    f"Unknown export task: {self.task}",
                    operation="run",
                    context={"task": self.task},
                )
        except ExportError as exc:
            self._on_failed(str(exc))
        except (OSError, MemoryError, PermissionError, pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError) as exc:
            logger.error("export_worker.run.failed op=%s fmt=%s", self.task, getattr(self.fmt, "value", self.fmt), exc_info=True)
            self._on_failed(str(exc))

    # -- chart export ----------------------------------------------------------

    def _export_chart(self) -> None:
        if self._cancelled:
            self._cleanup()
            return

        if self.image is None or self.image.isNull():
            self._on_failed("Cannot export: image is null or empty.")
            return

        self._on_progress(_PROGRESS_RENDER_START)  # Rendering chart...

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
            self._on_progress(_PROGRESS_DONE)
            get_metrics().increment("export.completed")
            self._on_completed(self.path)

    def _export_png(self) -> None:
        """Render image to PNG and write atomically."""
        opts = self.options
        img = self.image

        if self._cancelled:
            self._cleanup()
            return

        self._on_progress(_PROGRESS_WRITE_MIDPOINT)  # Writing file...

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

        self._on_progress(_PROGRESS_SVG_RENDER)

        renderer = self._get_renderer()
        data = renderer.render_to_svg(img, width, height)

        if self._cancelled:
            self._cleanup()
            return

        self._on_progress(_PROGRESS_SVG_WRITE)
        atomic_write(self.path, data)

    def _export_pdf(self) -> None:
        """Render chart + optional stats to PDF via the renderer."""
        opts = self.options
        img = self.image

        self._on_progress(_PROGRESS_PDF_PHASE1)

        if self._cancelled:
            self._cleanup()
            return

        self._on_progress(_PROGRESS_PDF_PHASE2)

        renderer = self._get_renderer()
        width = opts.width or (img.width() if img is not None else 0)
        height = opts.height or (img.height() if img is not None else 0)
        data = renderer.render_to_pdf(img, width, height, opts)

        self._on_progress(_PROGRESS_PDF_FINALIZE)

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

        self._on_progress(_PROGRESS_RENDER_START)

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
            self._on_progress(_PROGRESS_DONE)
            get_metrics().increment("export.completed")
            self._on_completed(self.path)

    def _export_csv(self) -> None:
        data = self.df.write_csv().encode("utf-8")  # type: ignore[union-attr]
        if self._cancelled:
            self._cleanup()
            return
        self._on_progress(_PROGRESS_WRITE_MIDPOINT)
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
            self._on_progress(_PROGRESS_WRITE_MIDPOINT)
            os.rename(tmp_path, self.path)
        except (OSError, MemoryError, PermissionError, pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError):
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
            self._on_progress(_PROGRESS_WRITE_MIDPOINT)
            os.rename(tmp_path, self.path)
        except (OSError, MemoryError, PermissionError, pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError):
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

    # -- helpers ---------------------------------------------------------------

    def _get_renderer(self) -> "IExportRenderer":
        """Return the injected renderer.

        A renderer must be supplied via the constructor ``renderer`` parameter.
        The UI layer is responsible for injecting a concrete implementation
        (e.g. QtExportRenderer) when constructing this worker or its owning
        ExportController.  Core never imports from the UI layer.
        """
        if self._renderer is not None:
            return self._renderer
        raise ExportError(
            "No renderer provided to ExportWorker. "
            "Inject an IExportRenderer via the constructor (e.g. QtExportRenderer)."
        )

    def _cleanup(self) -> None:
        """Remove partial / temp files after cancel — ERR-4.2."""
        for p in (self.path, self.path + ".tmp"):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass
