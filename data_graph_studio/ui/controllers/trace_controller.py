"""TraceController - extracted from MainWindow."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QProgressDialog
from PySide6.QtCore import Qt, QThread

from ...core.state import ComparisonMode



logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..main_window import MainWindow

class TraceController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    def _on_configure_trace(self) -> None:
        """Open the Trace Configuration dialog (always)."""
        from data_graph_studio.ui.dialogs.trace_config_dialog import TraceConfigDialog

        logger.debug("[Logger] opening TraceConfigDialog")
        dialog = TraceConfigDialog(self.w)
        result = dialog.exec()
        logger.debug("trace_controller.config_dialog.result", extra={"result": result, "start_requested": dialog.start_requested})

        if result == QDialog.DialogCode.Accepted and dialog.start_requested:
            self.w._run_trace(dialog.get_config())

    # ================================================================
    # Logger — ADB + Perfetto block layer tracing
    # ================================================================


    def _on_start_trace(self) -> None:
        """Start trace using saved config, or open Configure if none."""
        import shutil

        from data_graph_studio.ui.dialogs.trace_config_dialog import (
            load_logger_config,
        )

        logger_cfg = load_logger_config()

        # If config looks valid, start directly; otherwise open configure
        has_device = bool(logger_cfg.get("device_serial"))
        has_events = bool(logger_cfg.get("events"))
        has_adb = bool(shutil.which("adb"))
        has_save_path = bool(logger_cfg.get("save_path"))
        logger.debug("trace_controller.start_trace.check", extra={
            "adb": has_adb, "device": has_device, "events": has_events, "save": has_save_path,
        })

        if has_device and has_events and has_adb and has_save_path:
            # Bug fix: verify capture mode prerequisites before starting
            capture_mode = logger_cfg.get("capture_mode", "perfetto")
            serial = logger_cfg["device_serial"]
            if not self.w._verify_capture_mode(serial, capture_mode):
                self.w._on_configure_trace()
                return
            self.w._run_trace(logger_cfg)
        else:
            self.w._on_configure_trace()

    @staticmethod

    def _verify_capture_mode(serial: str, capture_mode: str) -> bool:
        """Check if device supports the capture mode (perfetto/root).

        Returns True if check passes or is inconclusive (timeout).
        """
        import subprocess

        try:
            if capture_mode == "perfetto":
                result = subprocess.run(
                    ["adb", "-s", serial, "shell", "which", "perfetto"],
                    capture_output=True, text=True, timeout=5,
                )
                return result.returncode == 0 and bool(result.stdout.strip())
            else:
                # Try both su variants (some devices need 'su 0 id')
                for cmd in [["su", "-c", "id"], ["su", "0", "id"]]:
                    result = subprocess.run(
                        ["adb", "-s", serial, "shell", *cmd],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.returncode == 0 and "uid=0" in result.stdout:
                        return True
                return False
        except (subprocess.TimeoutExpired, OSError):
            return True  # Inconclusive — let it proceed


    def _run_trace(self, logger_cfg: dict) -> None:
        """Execute trace with given config (Perfetto/Raw Ftrace)."""
        import shutil
        import datetime

        from data_graph_studio.ui.dialogs.trace_progress_dialog import (
            AdbTraceController,
            PerfettoTraceController,
            TraceProgressDialog,
        )

        logger.info("trace_controller.run_trace", extra={
            "mode": logger_cfg.get("capture_mode", "?"),
            "device": logger_cfg.get("device_serial", "?"),
            "events": len(logger_cfg.get("events", [])),
        })

        if not shutil.which("adb"):
            QMessageBox.warning(
                self, "Logger",
                "adb not found in PATH.\n\n"
                "Install Android SDK Platform Tools and ensure 'adb' is in your PATH.\n"
                "Or use Logger → Configure... to set up.",
            )
            return

        serial = logger_cfg.get("device_serial", "")
        if not serial:
            QMessageBox.warning(
                self, "Logger",
                "No device configured.\n\n"
                "Use Logger → Configure... to select a device.",
            )
            return

        capture_mode = logger_cfg.get("capture_mode", "perfetto")
        is_perfetto = capture_mode == "perfetto"

        # 저장 경로 결정
        save_path = logger_cfg.get("save_path", "")
        if not save_path:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            if is_perfetto:
                default_name = f"trace_{ts}.csv"
                file_filter = "CSV (*.csv);;All Files (*)"
            else:
                default_name = f"ftrace_{ts}.txt"
                file_filter = "Ftrace Text (*.txt);;All Files (*)"
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Trace File", default_name, file_filter,
            )
            if not save_path:
                return

        # 컨트롤러 생성 (캡처 모드에 따라)
        if is_perfetto:
            try:
                PerfettoTraceController.find_trace_processor()
            except FileNotFoundError as e:
                QMessageBox.warning(self.w, "Logger", str(e))
                return
            controller = PerfettoTraceController(self.w)
        else:
            controller = AdbTraceController(self.w)

        try:
            logger.debug("trace_controller.start_trace.begin", extra={"mode": capture_mode, "serial": serial})
            controller.start_trace(serial, logger_cfg)
        except Exception as e:
            logger.error("trace_controller.start_trace.failed", extra={"error": str(e)}, exc_info=True)
            QMessageBox.warning(self.w, "Logger", f"Failed to start trace:\n{e}")
            controller.cleanup()
            return

        dialog = TraceProgressDialog(controller, save_path, self.w)
        result = dialog.exec()

        logger.debug("trace_controller.progress_dialog.result", extra={"result": result})
        if result == QDialog.DialogCode.Accepted:
            self.w.statusBar().showMessage(f"Trace saved: {save_path}", 5000)

            if is_perfetto:
                # PerfettoTraceController saves CSV with .csv suffix
                csv_path = str(Path(save_path).with_suffix(".csv"))
                logger.info("trace_controller.load_csv.start", extra={"csv_path": csv_path})
                self.w._load_csv_async(csv_path)
            else:
                reply = QMessageBox.question(
                    self, "Logger",
                    f"Trace saved to:\n{save_path}\n\n"
                    "Open with Ftrace Parser now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.w._parse_ftrace_async(save_path)


    def _load_csv_async(self, csv_path: str) -> None:
        """Load a CSV file (from trace_processor_shell) in a background thread.

        Args:
            csv_path: Path to the CSV file.
        """
        from pathlib import Path
        from PySide6.QtCore import QThread, Signal as QtSignal

        import polars as pl

        class _CsvWorker(QThread):
            finished = QtSignal(object)
            error = QtSignal(str)

            def run(self_w):
                """Read the CSV file and emit finished or error signal."""
                try:
                    df = pl.read_csv(csv_path)
                    # ts is in nanoseconds, convert to seconds
                    if "ts" in df.columns:
                        df = df.with_columns(
                            (pl.col("ts").cast(pl.Float64) / 1e9).alias("timestamp")
                        ).drop("ts")
                    self_w.finished.emit(df)
                except Exception as e:
                    logger.exception("trace_controller.csv_worker.error")
                    self_w.error.emit(str(e))

        logger.debug("trace_controller.load_csv_async", extra={"csv_path": csv_path})
        self.w.statusBar().showMessage("Loading CSV...", 0)
        worker = _CsvWorker(self.w)

        def on_finished(df):
            """Handle successful CSV load and create a dataset from the result."""
            logger.info("trace_controller.csv.loaded", extra={"rows": len(df), "cols": len(df.columns), "columns": list(df.columns)[:10]})
            name = Path(csv_path).stem
            did = self.w.engine.load_dataset_from_dataframe(
                df, name=name, source_path=csv_path
            )
            if did:
                logger.info("trace_controller.dataset.created", extra={"id": did, "name": name})
                self.w._on_data_loaded()
                self.w._apply_graph_presets(df, converter="blocklayer")
                self.w.statusBar().showMessage(
                    f"Perfetto trace: loaded {len(df)} rows", 5000,
                )
            else:
                logger.error("trace_controller.load_dataset.none", extra={"csv_path": csv_path})
                QMessageBox.warning(self.w, "Logger", "Failed to load CSV data.")
                self.w.statusBar().clearMessage()

        def on_error(msg):
            """Handle CSV load failure by showing an error dialog."""
            logger.error("trace_controller.csv.load_failed", extra={"msg": msg})
            QMessageBox.critical(self.w, "Logger", f"CSV load failed:\n{msg}")
            self.w.statusBar().clearMessage()

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self.w._csv_worker = worker
        worker.start()


    def _parse_ftrace_async(self, file_path: str, converter: str = "blocklayer") -> None:
        """Parse an ftrace text file in a background thread.

        Avoids blocking the UI during large file parsing.

        Args:
            file_path: Path to the ftrace text file.
            converter: Converter to apply (default: "blocklayer").
        """
        from pathlib import Path
        from PySide6.QtCore import QThread, Signal as QtSignal

        from data_graph_studio.parsers import FtraceParser

        parser = FtraceParser()
        settings = parser.default_settings()
        settings["converter"] = converter

        class _ParseWorker(QThread):
            finished = QtSignal(object)
            error = QtSignal(str)

            def run(self_w):
                """Parse the ftrace file and emit finished or error signal."""
                try:
                    df = parser.parse(file_path, settings)
                    self_w.finished.emit(df)
                except Exception as e:
                    logger.exception("trace_controller.parse_worker.ftrace.error")
                    self_w.error.emit(str(e))

        logger.debug("trace_controller.parse_ftrace_async", extra={"file_path": file_path, "converter": converter})
        self.w.statusBar().showMessage("Parsing ftrace file...", 0)
        worker = _ParseWorker(self.w)

        def on_finished(df):
            """Handle successful ftrace parse and create a dataset from the result."""
            logger.info("trace_controller.ftrace.parsed", extra={"rows": len(df), "cols": len(df.columns), "columns": list(df.columns)[:10]})
            dataset_name = Path(file_path).stem
            dataset_id = self.w.engine.load_dataset_from_dataframe(
                df, name=dataset_name, source_path=file_path
            )
            if dataset_id:
                logger.info("trace_controller.ftrace.dataset_created", extra={"id": dataset_id})
                dataset = self.w.engine.get_dataset(dataset_id)
                if dataset:
                    self.w.state.add_dataset(
                        dataset_id=dataset_id,
                        name=dataset_name,
                        file_path=file_path,
                        row_count=len(df),
                        column_count=len(df.columns),
                        memory_bytes=df.estimated_size(),
                    )
                self.w._on_dataset_activated(dataset_id)
                self.w._apply_graph_presets(df, converter)
                self.w.statusBar().showMessage(
                    f"Ftrace: loaded {len(df)} rows from {Path(file_path).name}",
                    5000,
                )
            else:
                logger.error("[Logger] ftrace load_dataset_from_dataframe returned None")
                QMessageBox.warning(self.w, "Ftrace Parser", "Failed to load parsed data.")
                self.w.statusBar().clearMessage()

        def on_error(msg):
            """Handle ftrace parse failure by showing an error dialog."""
            logger.error("trace_controller.ftrace.parse_failed", extra={"msg": msg})
            QMessageBox.critical(self.w, "Ftrace Parser", f"Parse failed:\n{msg}")
            self.w.statusBar().clearMessage()

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        # prevent GC
        self.w._parse_worker = worker
        worker.start()


    def _on_compare_traces(self) -> None:
        """Open the Compare Traces dialog and run comparison."""
        from ..dialogs.trace_compare_dialog import TraceCompareDialog

        dialog = TraceCompareDialog(self.w)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        path_a = dialog.path_a
        path_b = dialog.path_b
        converter = dialog.converter
        compare_mode = dialog.compare_mode

        self._compare_traces_async(path_a, path_b, converter, compare_mode)

    def _compare_traces_async(
        self, path_a: str, path_b: str, converter: str, compare_mode: ComparisonMode
    ) -> None:
        """Parse two ftrace files in background and start comparison."""
        from data_graph_studio.parsers import FtraceParser

        parser = FtraceParser()
        settings = parser.default_settings()
        settings["converter"] = converter

        class _CompareWorker(QThread):
            from PySide6.QtCore import Signal as QtSignal
            finished = QtSignal(object, object)  # (df_a, df_b)
            error = QtSignal(str)
            progress = QtSignal(str)

            def run(self_w):
                """Parse both trace files and emit finished or error signal."""
                try:
                    self_w.progress.emit("Parsing Trace A...")
                    df_a = parser.parse(path_a, settings)
                    self_w.progress.emit("Parsing Trace B...")
                    df_b = parser.parse(path_b, settings)
                    self_w.finished.emit(df_a, df_b)
                except Exception as e:
                    logger.exception("trace_controller.parse_worker.compare.error")
                    self_w.error.emit(str(e))

        progress_dlg = QProgressDialog("Parsing trace files...", "Cancel", 0, 0, self.w)
        progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.show()

        worker = _CompareWorker(self.w)

        def on_progress(msg):
            """Update the progress dialog label with the current status message."""
            progress_dlg.setLabelText(msg)

        def on_finished(df_a, df_b):
            """Close the progress dialog and trigger the comparison view."""
            progress_dlg.close()
            self._finish_compare(df_a, df_b, path_a, path_b, converter, compare_mode)

        def on_error(msg):
            """Close the progress dialog and display a parse-failure error."""
            progress_dlg.close()
            QMessageBox.critical(self.w, "Compare Traces", f"Parse failed:\n{msg}")

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self.w._compare_worker = worker  # prevent GC
        worker.start()

    def _finish_compare(
        self, df_a, df_b, path_a: str, path_b: str,
        converter: str, compare_mode: ComparisonMode
    ) -> None:
        """Load both DataFrames as datasets and activate comparison mode."""
        name_a = Path(path_a).stem + " (Before)"
        name_b = Path(path_b).stem + " (After)"

        id_a = self.w.engine.load_dataset_from_dataframe(
            df_a, name=name_a, source_path=path_a
        )
        if not id_a:
            QMessageBox.warning(self.w, "Compare Traces", "Failed to load Trace A.")
            return

        # Register in state
        memory_a = df_a.estimated_size() if hasattr(df_a, 'estimated_size') else 0
        self.w.state.add_dataset(
            dataset_id=id_a, name=name_a, file_path=path_a,
            row_count=len(df_a), column_count=len(df_a.columns),
            memory_bytes=memory_a,
        )

        id_b = self.w.engine.load_dataset_from_dataframe(
            df_b, name=name_b, source_path=path_b
        )
        if not id_b:
            QMessageBox.warning(self.w, "Compare Traces", "Failed to load Trace B.")
            return

        memory_b = df_b.estimated_size() if hasattr(df_b, 'estimated_size') else 0
        self.w.state.add_dataset(
            dataset_id=id_b, name=name_b, file_path=path_b,
            row_count=len(df_b), column_count=len(df_b.columns),
            memory_bytes=memory_b,
        )

        # Refresh UI
        self.w._on_data_loaded()

        # Set comparison mode and start comparison
        self.w.state.set_comparison_mode(compare_mode)
        self.w._dataset_controller._on_comparison_mode_changed(compare_mode.value)
        self.w._dataset_controller._on_comparison_started([id_a, id_b])

        # Apply graph presets for the converter
        self._apply_graph_presets(df_a, converter)

        self.w.statusBar().showMessage(
            f"Comparing: {name_a} vs {name_b} ({compare_mode.value})", 5000
        )
        logger.info(
            "Compare traces: %s (%d rows) vs %s (%d rows), mode=%s",
            name_a, len(df_a), name_b, len(df_b), compare_mode.value,
        )

    def _apply_graph_presets(self, df, converter: str = "") -> None:
        """Create DGS profiles from graph presets and apply the first one.

        Each GraphPreset becomes a real GraphSetting (profile) in the
        project's profile_store, visible in the Project Explorer sidebar.
        The first matching preset is auto-applied.

        Args:
            df: The loaded polars DataFrame.
            converter: Converter name (e.g. "blocklayer").
        """
        from data_graph_studio.parsers.graph_preset import BUILTIN_PRESETS
        from data_graph_studio.core.profile import GraphSetting

        presets = BUILTIN_PRESETS.get(converter, [])
        if not presets:
            logger.debug("trace_controller.presets.none", extra={"converter": converter})
            return

        dataset_id = self.w.state.active_dataset_id
        if not dataset_id:
            logger.warning("[Logger] no active dataset, cannot create profiles")
            return

        # Skip if profiles already exist for this dataset (avoid duplicates on re-parse)
        existing = self.w.profile_store.get_by_dataset(dataset_id)
        existing_names = {s.name for s in existing}

        first_profile_id = None
        created_count = 0

        for preset in presets:
            if not preset.columns_present(df):
                logger.debug("trace_controller.preset.skipped.columns_missing", extra={"preset": preset.name})
                continue
            if preset.name in existing_names:
                logger.debug("trace_controller.preset.skipped.exists", extra={"preset": preset.name})
                # Use existing profile as first if none yet
                if first_profile_id is None:
                    for s in existing:
                        if s.name == preset.name:
                            first_profile_id = s.id
                            break
                continue

            # Build value_columns as dicts (GraphSettingMapper format)
            value_cols = []
            for col_name in preset.y_columns:
                value_cols.append({
                    "name": col_name,
                    "aggregation": "sum",
                    "color": "#1f77b4",
                    "use_secondary_axis": False,
                    "order": len(value_cols),
                    "formula": "",
                })

            # Build group_columns
            group_cols = []
            if preset.group_column:
                group_cols.append({
                    "name": preset.group_column,
                    "selected_values": [],
                    "order": 0,
                })

            import uuid
            profile_id = str(uuid.uuid4())
            gs = GraphSetting(
                id=profile_id,
                name=preset.name,
                dataset_id=dataset_id,
                chart_type=preset.chart_type,
                x_column=preset.x_column,
                value_columns=tuple(value_cols),
                group_columns=tuple(group_cols),
                icon="📈" if preset.chart_type in ("line", "area") else "📊",
                description=preset.description,
            )
            self.w.profile_store.add(gs)
            created_count += 1
            logger.info("trace_controller.profile.created", extra={
                "name": preset.name,
                "id": profile_id,
                "chart": preset.chart_type,
                "x": preset.x_column,
                "y": preset.y_columns,
            })

            if first_profile_id is None:
                first_profile_id = profile_id

        # Refresh project tree to show new profiles
        if created_count > 0 and hasattr(self, 'profile_model'):
            self.w.profile_model.refresh()
            logger.info("trace_controller.profiles.created", extra={"count": created_count, "dataset_id": dataset_id})

        # Apply the first profile
        if first_profile_id:
            try:
                ok = self.w.profile_controller.apply_profile(first_profile_id)
                if ok:
                    self.w.graph_panel.refresh()
                    self.w.graph_panel.autofit()
                    logger.info("trace_controller.profile.auto_applied", extra={"profile_id": first_profile_id})
                else:
                    logger.warning("trace_controller.profile.apply_failed", extra={"profile_id": first_profile_id})
            except Exception as e:
                logger.warning("trace_controller.profile.apply_error", extra={"error": str(e)}, exc_info=True)


