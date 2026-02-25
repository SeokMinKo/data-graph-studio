"""TraceController - extracted from MainWindow."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QProgressDialog
from PySide6.QtCore import Qt, QThread

from ...core.state import ComparisonMode

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    import polars as pl
    from ..main_window import MainWindow


class TraceContext:
    """Holds raw ftrace data for re-conversion."""

    def __init__(self, raw_df: "pl.DataFrame", settings: dict, dataset_id: str):
        self.raw_df = raw_df
        self.settings = dict(settings)
        self.dataset_id = dataset_id


class TraceController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    @staticmethod
    def _normalize_event_name(event_name: Any) -> str:
        """Normalize Perfetto event names to ftrace-style names.

        Examples:
            - "block_rq_issue" -> "block_rq_issue"
            - "block/block_rq_issue" -> "block_rq_issue"
        """
        if not isinstance(event_name, str):
            return ""
        event = event_name.strip()
        if "/" in event:
            event = event.split("/", 1)[1]
        return event

    @staticmethod
    def _parse_perfetto_kv_details(details: Any) -> Dict[str, str]:
        """Parse Perfetto `key=value` detail string into a dict."""
        if not isinstance(details, str):
            return {}

        result: Dict[str, str] = {}
        for token in details.split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            key = key.strip()
            value = value.strip().strip(",")
            if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                value = value[1:-1]
            if key:
                result[key] = value
        return result

    @classmethod
    def _coerce_perfetto_details_for_blocklayer(
        cls, event_name: str, details: Any
    ) -> str:
        """Convert Perfetto args into blocklayer converter-compatible details.

        Blocklayer converter expects legacy ftrace-like details format:
            issue/insert: <dev> <rwbs> <bytes> () <sector> + <nr_sectors>
            complete:     <dev> <rwbs> () <sector> + <nr_sectors>
        """
        event = cls._normalize_event_name(event_name)
        if not isinstance(details, str):
            return ""

        if event not in {"block_rq_insert", "block_rq_issue", "block_rq_complete"}:
            return details

        kv = cls._parse_perfetto_kv_details(details)

        dev = kv.get("dev")
        if not dev:
            major = kv.get("major")
            minor = kv.get("minor") or kv.get("first_minor")
            if major is not None and minor is not None:
                dev = f"{major},{minor}"

        rwbs = kv.get("rwbs") or kv.get("rw_bs") or "R"
        sector = kv.get("sector")
        nr_sectors = kv.get("nr_sector") or kv.get("nr_sectors")

        if not dev or sector is None or nr_sectors is None:
            # If we cannot build legacy format safely, keep original details.
            return details

        if event in {"block_rq_insert", "block_rq_issue"}:
            size_bytes = kv.get("bytes") or kv.get("nr_bytes")
            if size_bytes is None:
                try:
                    size_bytes = str(int(nr_sectors) * 512)
                except Exception:
                    size_bytes = "0"
            return f"{dev} {rwbs} {size_bytes} () {sector} + {nr_sectors}"

        return f"{dev} {rwbs} () {sector} + {nr_sectors}"

    @classmethod
    def _normalize_perfetto_csv_for_ftrace_converter(cls, df: "pl.DataFrame") -> "pl.DataFrame":
        """Normalize Perfetto CSV rows into FtraceParser raw schema.

        Output columns are aligned to parse_raw schema:
            timestamp, cpu, task, pid, flags, event, details
        """
        import polars as pl

        schema = {
            "timestamp": pl.Float64,
            "cpu": pl.Int32,
            "task": pl.Utf8,
            "pid": pl.Int32,
            "flags": pl.Utf8,
            "event": pl.Utf8,
            "details": pl.Utf8,
        }

        if df is None or len(df) == 0:
            return pl.DataFrame(schema=schema)

        work = df

        if "timestamp" not in work.columns:
            if "ts" in work.columns:
                work = work.with_columns(
                    (pl.col("ts").cast(pl.Float64) / 1e9).alias("timestamp")
                )
            else:
                work = work.with_columns(pl.lit(0.0).alias("timestamp"))

        event_source = "event" if "event" in work.columns else ("name" if "name" in work.columns else None)
        if event_source is None:
            work = work.with_columns(pl.lit("").alias("__event_raw"))
        else:
            work = work.with_columns(pl.col(event_source).cast(pl.Utf8).alias("__event_raw"))

        if "details" not in work.columns:
            work = work.with_columns(pl.lit("").alias("details"))
        if "cpu" not in work.columns:
            work = work.with_columns(pl.lit(0).alias("cpu"))
        if "task" not in work.columns:
            work = work.with_columns(pl.lit("").alias("task"))
        if "pid" not in work.columns:
            work = work.with_columns(pl.lit(-1).alias("pid"))

        work = work.with_columns([
            pl.col("__event_raw")
            .map_elements(cls._normalize_event_name, return_dtype=pl.Utf8)
            .alias("event"),
            pl.struct(["__event_raw", "details"])
            .map_elements(
                lambda row: cls._coerce_perfetto_details_for_blocklayer(
                    row["__event_raw"], row["details"]
                ),
                return_dtype=pl.Utf8,
            )
            .alias("details_norm"),
        ])

        return work.select([
            pl.col("timestamp").cast(pl.Float64).fill_null(0.0).alias("timestamp"),
            pl.col("cpu").cast(pl.Int32, strict=False).fill_null(0).alias("cpu"),
            pl.col("task").cast(pl.Utf8).fill_null("").alias("task"),
            pl.col("pid").cast(pl.Int32, strict=False).fill_null(-1).alias("pid"),
            pl.lit("....").alias("flags"),
            pl.col("event").cast(pl.Utf8).fill_null("").alias("event"),
            pl.col("details_norm").cast(pl.Utf8).fill_null("").alias("details"),
        ])

    def _on_configure_trace(self) -> None:
        """Open the Trace Configuration dialog (always)."""
        from data_graph_studio.ui.dialogs.trace_config_dialog import TraceConfigDialog

        logger.debug("[Logger] opening TraceConfigDialog")
        dialog = TraceConfigDialog(self.w)
        result = dialog.exec()
        logger.debug("[Logger] TraceConfigDialog result=%s, start_requested=%s",
                     result, dialog.start_requested)

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
            TraceConfigDialog,
        )

        logger_cfg = load_logger_config()

        # If config looks valid, start directly; otherwise open configure
        has_device = bool(logger_cfg.get("device_serial"))
        has_events = bool(logger_cfg.get("events"))
        has_adb = bool(shutil.which("adb"))
        has_save_path = bool(logger_cfg.get("save_path"))
        logger.debug("[Logger] start_trace check: adb=%s, device=%s, events=%s, save=%s",
                     has_adb, has_device, has_events, has_save_path)

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

        logger.info("[Logger] _run_trace: mode=%s, device=%s, events=%d",
                     logger_cfg.get("capture_mode", "?"),
                     logger_cfg.get("device_serial", "?"),
                     len(logger_cfg.get("events", [])))

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
            logger.debug("[Logger] starting %s trace on %s", capture_mode, serial)
            controller.start_trace(serial, logger_cfg)
        except Exception as e:
            logger.error("[Logger] start_trace failed: %s", e, exc_info=True)
            QMessageBox.warning(self.w, "Logger", f"Failed to start trace:\n{e}")
            controller.cleanup()
            return

        dialog = TraceProgressDialog(controller, save_path, self.w)
        result = dialog.exec()

        logger.debug("[Logger] TraceProgressDialog result=%s", result)
        if result == QDialog.DialogCode.Accepted:
            self.w.statusBar().showMessage(f"Trace saved: {save_path}", 5000)

            if is_perfetto:
                # PerfettoTraceController saves CSV with .csv suffix
                csv_path = str(Path(save_path).with_suffix(".csv"))
                logger.info("[Logger] loading perfetto CSV: %s", csv_path)
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
            # Emits (raw_df_for_converter, converted_df, settings)
            finished = QtSignal(object, object, object)
            error = QtSignal(str)

            def run(self_w):
                try:
                    perfetto_df = pl.read_csv(csv_path)
                    raw_df = TraceController._normalize_perfetto_csv_for_ftrace_converter(perfetto_df)

                    from data_graph_studio.parsers import FtraceParser

                    parser = FtraceParser()
                    settings = parser.default_settings()
                    settings["converter"] = "blocklayer"
                    converted_df = parser.convert(raw_df, settings)

                    self_w.finished.emit(raw_df, converted_df, settings)
                except Exception as e:
                    self_w.error.emit(str(e))

        logger.debug("[Logger] _load_csv_async: %s", csv_path)
        self.w.statusBar().showMessage("Loading CSV...", 0)
        worker = _CsvWorker(self.w)

        def on_finished(raw_df, df, settings):
            logger.info(
                "[Logger] Perfetto converted: raw=%d rows, converted=%d rows, columns=%s",
                len(raw_df), len(df), list(df.columns)[:10],
            )
            name = Path(csv_path).stem
            did = self.w.engine.load_dataset_from_dataframe(
                df, name=name, source_path=csv_path
            )
            if did:
                logger.info("trace_controller.dataset.created", extra={"id": did, "dataset_name": name})
                # Store TraceContext for re-conversion (same as ftrace path)
                self.w._trace_context = TraceContext(raw_df, settings, did)
                self.w._on_data_loaded()
                self.w._apply_graph_presets(df, converter="blocklayer")
                if hasattr(self.w, '_converter_options_panel'):
                    self.w._converter_options_panel.set_converter("blocklayer")
                self.w.statusBar().showMessage(
                    f"Perfetto trace: converted {len(raw_df)} events → {len(df)} rows", 5000,
                )
            else:
                logger.error("[Logger] load_dataset_from_dataframe returned None for %s", csv_path)
                QMessageBox.warning(self.w, "Logger", "Failed to load converted trace data.")
                self.w.statusBar().clearMessage()

        def on_error(msg):
            """Handle CSV load failure by showing an error dialog."""
            logger.error("trace_controller.csv.load_failed", extra={"error_message": msg})
            QMessageBox.critical(self.w, "Logger", f"CSV load failed:\n{msg}")
            self.w.statusBar().clearMessage()

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self.w._csv_worker = worker
        worker.start()


    def reconvert(self, converter_options: dict) -> None:
        """Re-run converter with new options, replace dataset, refresh graph."""
        ctx: Optional[TraceContext] = getattr(self.w, '_trace_context', None)
        if ctx is None:
            return

        ctx.settings["converter_options"] = converter_options

        from data_graph_studio.parsers import FtraceParser

        parser = FtraceParser()
        new_df = parser.convert(ctx.raw_df, ctx.settings)

        self.w.engine.replace_dataset_df(ctx.dataset_id, new_df)
        # Refresh all panels
        self.w.graph_panel.refresh()
        self.w.statusBar().showMessage(
            f"Re-converted with new options ({len(new_df)} rows)", 3000,
        )

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
            # Emits (raw_df, converted_df)
            finished = QtSignal(object, object)
            error = QtSignal(str)

            def run(self_w):
                try:
                    raw_df = parser.parse_raw(file_path, settings)
                    converted_df = parser.convert(raw_df, settings)
                    self_w.finished.emit(raw_df, converted_df)
                except Exception as e:
                    self_w.error.emit(str(e))

        logger.debug("[Logger] _parse_ftrace_async: %s, converter=%s", file_path, converter)
        self.w.statusBar().showMessage("Parsing ftrace file...", 0)
        worker = _ParseWorker(self.w)

        def on_finished(raw_df, df):
            logger.info("[Logger] ftrace parsed: %d rows, %d cols, columns=%s",
                        len(df), len(df.columns), list(df.columns)[:10])
            dataset_name = Path(file_path).stem
            dataset_id = self.w.engine.load_dataset_from_dataframe(
                df, name=dataset_name, source_path=file_path
            )
            if dataset_id:
                logger.info("[Logger] ftrace dataset created: id=%s", dataset_id)
                # Store TraceContext for re-conversion
                self.w._trace_context = TraceContext(raw_df, settings, dataset_id)
                self.w._on_data_loaded()
                self.w._apply_graph_presets(df, converter)
                # Configure converter options panel if present
                if hasattr(self.w, '_converter_options_panel'):
                    self.w._converter_options_panel.set_converter(converter)
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
            logger.error("trace_controller.ftrace.parse_failed", extra={"error_message": msg})
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
                try:
                    self_w.progress.emit("Parsing Trace A...")
                    df_a = parser.parse(path_a, settings)
                    self_w.progress.emit("Parsing Trace B...")
                    df_b = parser.parse(path_b, settings)
                    self_w.finished.emit(df_a, df_b)
                except Exception as e:
                    self_w.error.emit(str(e))

        progress_dlg = QProgressDialog("Parsing trace files...", "Cancel", 0, 0, self.w)
        progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.show()

        worker = _CompareWorker(self.w)

        def on_progress(msg):
            progress_dlg.setLabelText(msg)

        def on_finished(df_a, df_b):
            progress_dlg.close()
            self._finish_compare(df_a, df_b, path_a, path_b, converter, compare_mode)

        def on_error(msg):
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
        from data_graph_studio.core.state import ChartType, AggregationType

        presets = BUILTIN_PRESETS.get(converter, [])
        if not presets:
            logger.debug("[Logger] no presets for converter=%s", converter)
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
                logger.debug("[Logger] preset '%s' skipped: columns missing", preset.name)
                continue
            if preset.name in existing_names:
                logger.debug("[Logger] preset '%s' already exists, skipping", preset.name)
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
            logger.info("[Logger] created profile '%s' (id=%s, chart=%s, x=%s, y=%s)",
                        preset.name, profile_id, preset.chart_type,
                        preset.x_column, preset.y_columns)

            if first_profile_id is None:
                first_profile_id = profile_id

        # Refresh project tree to show new profiles
        if created_count > 0 and hasattr(self, 'profile_model'):
            self.w.profile_model.refresh()
            logger.info("[Logger] %d profiles created for dataset %s", created_count, dataset_id)

        # Apply the first profile
        if first_profile_id:
            try:
                ok = self.w.profile_controller.apply_profile(first_profile_id)
                if ok:
                    self.w.graph_panel.refresh()
                    self.w.graph_panel.autofit()
                    logger.info("[Logger] auto-applied profile: %s", first_profile_id)
                else:
                    logger.warning("[Logger] failed to apply profile: %s", first_profile_id)
            except Exception as e:
                logger.warning("[Logger] error applying profile: %s", e, exc_info=True)


