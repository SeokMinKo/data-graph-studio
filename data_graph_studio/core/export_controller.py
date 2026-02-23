"""
Export Controller — PRD Feature 4 (Export Enhancement)

Provides:
- ExportFormat enum — PNG, SVG, PDF, CSV, Parquet, Excel  (re-exported from export_workers)
- ExportOptions — resolution, DPI, background, legend, stats  (re-exported from export_workers)
- ExportWorker — threading.Thread-based background worker  (re-exported from export_workers)
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

import logging
import threading
from typing import Any, Dict, Optional, TYPE_CHECKING

from data_graph_studio.core.io_abstract import IExportRenderer
from data_graph_studio.core.metrics import get_metrics
from data_graph_studio.core.observable import Observable
from data_graph_studio.core.exceptions import ExportError
from data_graph_studio.core.export_workers import (
    ExportFormat,
    ExportOptions,
    ExportWorker,
)

if TYPE_CHECKING:
    import polars as pl

logger = logging.getLogger(__name__)


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
        """Initialize with an optional chart renderer.

        Input: renderer — IExportRenderer | None, injected for chart export;
               when None, ExportWorker falls back to its own default renderer
        Invariants: _cancelled starts False; no background thread is running
        """
        super().__init__()
        self._worker: Optional[ExportWorker] = None
        self._thread: Optional[threading.Thread] = None
        self._cancelled = False
        self._renderer = renderer

    # -- cancel / reset --------------------------------------------------------

    def cancel(self) -> None:
        """Request cancellation of the current export.

        Invariants: _cancelled is True after return; worker.cancel() called if one exists
        """
        self._cancelled = True
        if self._worker is not None:
            self._worker.cancel()

    def reset(self) -> None:
        """Reset the cancellation flag so a new export can proceed.

        Invariants: _cancelled is False after return
        """
        self._cancelled = False

    # -- synchronous helpers (for tests & simple uses) -------------------------

    def export_chart_sync(
        self,
        image,
        path: str,
        fmt: ExportFormat,
        options: Optional[ExportOptions] = None,
    ) -> None:
        """Export a chart image synchronously, blocking the caller until done.

        Input: image — QImage or compatible image object to export
               path — str, destination file path (must be writable)
               fmt — ExportFormat, one of PNG/SVG/PDF
               options — ExportOptions | None, resolution/DPI overrides
        Raises: ExportError — if the write fails
        Invariants: emits progress_changed, then export_completed or export_failed
        """
        with get_metrics().timed_operation("export.dispatch"):
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
        """Export a DataFrame synchronously, blocking the caller until done.

        Input: df — pl.DataFrame, data to export
               path — str, destination file path (must be writable)
               fmt — ExportFormat, one of CSV/EXCEL/PARQUET
               options — ExportOptions | None, format-specific overrides
        Raises: ExportError — if the write fails
        Invariants: emits progress_changed, then export_completed or export_failed
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
        """Export a chart on a daemon background thread (non-blocking).

        Cancels any in-progress export before starting the new one.
        Input: image — QImage or compatible image object to export
               path — str, destination file path
               fmt — ExportFormat, one of PNG/SVG/PDF
               options — ExportOptions | None, resolution/DPI overrides
        Invariants: exactly one background thread running after return;
                    emits progress_changed, then export_completed or export_failed
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
        """Export a DataFrame on a daemon background thread (non-blocking).

        Cancels any in-progress export before starting the new one.
        Input: df — pl.DataFrame, data to export
               path — str, destination file path
               fmt — ExportFormat, one of CSV/EXCEL/PARQUET
               options — ExportOptions | None, format-specific overrides
        Invariants: exactly one background thread running after return;
                    emits progress_changed, then export_completed or export_failed
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
        """Handle an IPC export_chart command (FR-4.8).

        Input: params — dict with keys: path (str, required), format (str, default "png"),
               width (int | None), height (int | None), dpi (int, default 96)
        Output: Dict[str, str] — {"status": "ok", "message": ...} on success
                                  {"status": "error", "message": ...} on failure
        Raises: nothing — all errors are caught and returned as {"status": "error"}
        Invariants: requires set_image_provider() to have been called beforehand
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
        except ExportError as e:
            logger.error("export_controller.ipc_chart.failed", extra={"path": path}, exc_info=True)
            return {"status": "error", "message": str(e)}
        except (ValueError, TypeError, RuntimeError) as e:
            logger.error("export_controller.ipc_chart.unexpected", extra={"path": path}, exc_info=True)
            return {"status": "error", "message": str(e)}

    def handle_ipc_export_data(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Handle an IPC export_data command (FR-4.8).

        Input: params — dict with keys: path (str, required), format (str, default "csv")
        Output: Dict[str, str] — {"status": "ok", "message": ...} on success
                                  {"status": "error", "message": ...} on failure
        Raises: nothing — all errors are caught and returned as {"status": "error"}
        Invariants: requires set_dataframe_provider() to have been called beforehand
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
        except ExportError as e:
            logger.error("export_controller.ipc_data.failed", extra={"path": path}, exc_info=True)
            return {"status": "error", "message": str(e)}
        except (ValueError, TypeError, RuntimeError) as e:
            logger.error("export_controller.ipc_data.unexpected", extra={"path": path}, exc_info=True)
            return {"status": "error", "message": str(e)}

    def handle_ipc_export_dashboard(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Handle an IPC export_dashboard command (stub, not yet implemented).

        Raises: NotImplementedError — dashboard export requires multi-chart capture
                and is not yet supported via IPC
        """
        raise NotImplementedError(
            "Dashboard export via IPC is not yet implemented. "
            "Use the GUI Export menu instead."
        )

    def set_image_provider(self, provider) -> None:
        """Register a zero-argument callable that returns the current chart image.

        Input: provider — callable() -> QImage, called by IPC chart export handlers
        Invariants: stored as self._image_provider; replaces any previous provider
        """
        self._image_provider = provider

    def set_dataframe_provider(self, provider) -> None:
        """Register a zero-argument callable that returns the current Polars DataFrame.

        Input: provider — callable() -> pl.DataFrame | None, called by IPC data export handlers
        Invariants: stored as self._dataframe_provider; replaces any previous provider
        """
        self._dataframe_provider = provider

    # -- internals -------------------------------------------------------------

    def _run_worker(self) -> None:
        """Thread target: execute the current worker and clear references on completion.

        Invariants: _worker and _thread are both None after this returns
        """
        if self._worker is not None:
            self._worker.run()
        self._worker = None
        self._thread = None

    def _on_worker_completed(self, path: str) -> None:
        self.emit("export_completed", path)

    def _on_worker_failed(self, error: str) -> None:
        self.emit("export_failed", error)

    def _stop_current_worker(self) -> None:
        """Cancel the running worker and join its thread with a 3-second timeout.

        Invariants: _worker and _thread are both None after return
        """
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            self._thread = None

    def shutdown(self) -> None:
        """Gracefully stop any running export worker during application close.

        Invariants: no background thread is running after return (PRD §10.6)
        """
        self._stop_current_worker()
