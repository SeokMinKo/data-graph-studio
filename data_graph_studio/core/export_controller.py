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
from data_graph_studio.core.observable import Observable
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
