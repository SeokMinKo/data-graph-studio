"""
Export Controller — PRD Feature 4 (Export Enhancement)

Provides:
- ExportFormat enum — PNG, SVG, PDF, CSV, Parquet, Excel
- ExportOptions — resolution, DPI, background, legend, stats
- ExportWorker — threading.Thread-based background worker
- ExportController — orchestrates export with progress, cancel, atomic write

Events (Observable):
    progress_changed(int)    — 0..100 progress percentage
    export_completed(str)    — output file path on success
    export_failed(str)       — error message on failure

Architecture notes (PRD §9.2, §10.3, §10.5):
    • All file writes go through atomic_write (temp → rename)
    • Heavy exports run in a daemon threading.Thread (no UI blocking)
    • Single concurrent worker per controller (duplicate → cancel previous)
    • Cancel sets _cancelled flag → worker checks periodically
"""

from __future__ import annotations

import os
import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from data_graph_studio.core.io_abstract import atomic_write, IExportRenderer
from data_graph_studio.core.observable import Observable

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


# ---------------------------------------------------------------------------
# ExportController  (Observable, lives on main thread)
# ---------------------------------------------------------------------------

class ExportController(Observable):
    """
    High-level export orchestrator — PRD §9.2.

    Events:
        progress_changed(int)   — forwarded from worker
        export_completed(str)   — output file path
        export_failed(str)      — error description
    """

    def __init__(
        self,
        renderer: Optional[IExportRenderer] = None,
    ):
        super().__init__()
        self._worker: Optional[ExportWorker] = None
        self._thread: Optional[threading.Thread] = None
        self._cancelled = False
        self._renderer = renderer

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
        image,
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
            renderer=self._renderer,
            on_progress=lambda n: self.emit("progress_changed", n),
            on_completed=lambda p: self.emit("export_completed", p),
            on_failed=lambda e: self.emit("export_failed", e),
        )
        worker._cancelled = self._cancelled

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
            on_progress=lambda n: self.emit("progress_changed", n),
            on_completed=lambda p: self.emit("export_completed", p),
            on_failed=lambda e: self.emit("export_failed", e),
        )
        worker._cancelled = self._cancelled

        worker.run()

    # -- async (threaded) API --------------------------------------------------

    def export_chart_async(
        self,
        image,
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
            renderer=self._renderer,
            on_progress=lambda n: self.emit("progress_changed", n),
            on_completed=self._on_worker_completed,
            on_failed=self._on_worker_failed,
        )
        self._thread = threading.Thread(target=self._run_worker, daemon=True)
        self._thread.start()

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
            on_progress=lambda n: self.emit("progress_changed", n),
            on_completed=self._on_worker_completed,
            on_failed=self._on_worker_failed,
        )
        self._thread = threading.Thread(target=self._run_worker, daemon=True)
        self._thread.start()

    # -- IPC commands (FR-4.8) -------------------------------------------------

    def handle_ipc_export_chart(self, params: Dict[str, Any]) -> Dict[str, str]:
        """IPC: export_chart {path, format, width?, height?, dpi?}

        Requires ``set_image_provider(callable)`` to be called first so
        the controller can obtain the current chart image.
        """
        path = params.get("path")
        fmt_str = params.get("format", "png").lower()
        if not path:
            return {"status": "error", "message": "Missing 'path' parameter"}

        fmt_map = {"png": ExportFormat.PNG, "svg": ExportFormat.SVG, "pdf": ExportFormat.PDF}
        fmt = fmt_map.get(fmt_str)
        if fmt is None:
            return {"status": "error", "message": f"Unsupported chart format: {fmt_str}"}

        image_provider = getattr(self, "_image_provider", None)
        if image_provider is None:
            return {"status": "error", "message": "No image provider configured (call set_image_provider)"}

        image = image_provider()
        if image is None or image.isNull():
            return {"status": "error", "message": "No chart image available"}

        opts = ExportOptions(
            width=params.get("width"),
            height=params.get("height"),
            dpi=params.get("dpi", 96),
        )
        try:
            self.export_chart_sync(image, path, fmt, opts)
            return {"status": "ok", "message": f"Exported chart to {path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def handle_ipc_export_data(self, params: Dict[str, Any]) -> Dict[str, str]:
        """IPC: export_data {path, format}

        Requires ``set_dataframe_provider(callable)`` to be called first.
        """
        path = params.get("path")
        fmt_str = params.get("format", "csv").lower()
        if not path:
            return {"status": "error", "message": "Missing 'path' parameter"}

        fmt_map = {"csv": ExportFormat.CSV, "excel": ExportFormat.EXCEL,
                   "parquet": ExportFormat.PARQUET}
        fmt = fmt_map.get(fmt_str)
        if fmt is None:
            return {"status": "error", "message": f"Unsupported data format: {fmt_str}"}

        df_provider = getattr(self, "_dataframe_provider", None)
        if df_provider is None:
            return {"status": "error", "message": "No dataframe provider configured"}

        df = df_provider()
        if df is None:
            return {"status": "error", "message": "No data available"}

        try:
            self.export_data_sync(df, path, fmt)
            return {"status": "ok", "message": f"Exported data to {path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def handle_ipc_export_dashboard(self, params: Dict[str, Any]) -> Dict[str, str]:
        """IPC: export_dashboard {path, format}

        Not yet implemented — dashboard export requires multi-chart capture.
        """
        raise NotImplementedError(
            "Dashboard export via IPC is not yet implemented. "
            "Use the GUI Export menu instead."
        )

    def set_image_provider(self, provider) -> None:
        """Set a callable that returns the current chart image."""
        self._image_provider = provider

    def set_dataframe_provider(self, provider) -> None:
        """Set a callable that returns the current polars DataFrame."""
        self._dataframe_provider = provider

    # -- internals -------------------------------------------------------------

    def _run_worker(self) -> None:
        """Thread target: run worker then clear references."""
        if self._worker is not None:
            self._worker.run()
        self._worker = None
        self._thread = None

    def _on_worker_completed(self, path: str) -> None:
        self.emit("export_completed", path)

    def _on_worker_failed(self, error: str) -> None:
        self.emit("export_failed", error)

    def _stop_current_worker(self) -> None:
        """Cancel and wait for the current worker (PRD §10.5)."""
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            self._thread = None

    def shutdown(self) -> None:
        """Called during app close — PRD §10.6."""
        self._stop_current_worker()
