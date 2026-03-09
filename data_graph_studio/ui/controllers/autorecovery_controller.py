"""AutorecoveryController - extracted from MainWindow."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from PySide6.QtWidgets import QMessageBox, QProgressDialog
from PySide6.QtCore import Qt, QTimer

from ...core.state import AggregationType, ChartType
from ...core.profile import GraphSetting

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..main_window import MainWindow


class AutorecoveryController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: "MainWindow"):
        self.w = main_window

    def _setup_autorecovery(self):
        """Setup autosave + recovery prompt"""
        self.w._autosave_path = os.path.expanduser("~/.data_graph_studio/autosave.json")
        os.makedirs(os.path.dirname(self.w._autosave_path), exist_ok=True)

        # Prompt recovery if autosave exists
        # Skip if autosave is stale (>24h) to avoid blocking on repeated crashes
        if os.path.exists(self.w._autosave_path):
            try:
                import time as _time

                age = _time.time() - os.path.getmtime(self.w._autosave_path)
                if age > 86400:  # >24h → discard silently
                    os.remove(self.w._autosave_path)
                else:
                    # Use QTimer.singleShot to show dialog AFTER event loop starts
                    # so IPC server is already running and accessible
                    from PySide6.QtCore import QTimer as _QTimer

                    _QTimer.singleShot(500, self.w._prompt_recovery)
            except Exception as e:
                logger.debug("Autorecovery setup check failed: %s", e)

        # Autosave timer
        self.w._autosave_timer = QTimer(self.w)
        self.w._autosave_timer.setInterval(60 * 1000)  # 1 minute
        self.w._autosave_timer.timeout.connect(self.w._autosave_session)
        self.w._autosave_timer.start()

    def _prompt_recovery(self):
        """Show recovery dialog (deferred via QTimer so IPC is already up).

        Features:
        - "Don't show again" checkbox (persisted in QSettings)
        - On restore failure: backs up to .bak, deletes original, shows toast
        """
        if not os.path.exists(self.w._autosave_path):
            return

        from PySide6.QtCore import QSettings

        settings = QSettings("Godol", "DataGraphStudio")
        if settings.value("recovery/skip_prompt", False, type=bool):
            # User opted out — silently discard
            try:
                os.remove(self.w._autosave_path)
            except OSError:
                pass
            return

        try:
            from PySide6.QtWidgets import QCheckBox

            msg = QMessageBox(self.w)
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle("Recovery")
            msg.setText(
                "A previous session was not closed properly.\n"
                "Recover the last autosave?"
            )
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

            cb = QCheckBox("Don't show again")
            msg.setCheckBox(cb)

            result = msg.exec()

            if cb.isChecked():
                settings.setValue("recovery/skip_prompt", True)

            if result == QMessageBox.Yes:
                try:
                    self.w._restore_autosave()
                except Exception as exc:
                    # Backup failed autosave then remove
                    bak_path = self.w._autosave_path + ".bak"
                    try:
                        import shutil

                        shutil.copy2(self.w._autosave_path, bak_path)
                    except OSError:
                        pass
                    try:
                        os.remove(self.w._autosave_path)
                    except OSError:
                        pass
                    if hasattr(self.w, "statusBar"):
                        self.w.statusBar().showMessage(
                            f"Recovery failed: {exc}. "
                            "Backup saved to autosave.json.bak",
                            8000,
                        )
            else:
                try:
                    os.remove(self.w._autosave_path)
                except OSError:
                    pass
        except Exception as e:
            logger.warning("Recovery prompt failed: %s", e)

    def _autosave_session(self):
        """Autosave datasets + graph settings + drawings"""
        try:
            if not self.w.state.is_data_loaded:
                return

            datasets = []
            for did, meta in self.w.state._dataset_metadata.items():
                datasets.append(
                    {"id": did, "name": meta.name, "file_path": meta.file_path}
                )

            # Serialize all profiles from ProfileStore
            profiles = []
            for did in self.w.state._dataset_metadata:
                for gs in self.w.profile_store.get_by_dataset(did):
                    try:
                        profiles.append(gs.to_dict())
                    except Exception as e:
                        logger.debug("Failed to serialize profile for autosave: %s", e)

            payload = {
                "version": 2,
                "datasets": datasets,
                "active_dataset_id": self.w.state.active_dataset_id,
                "graph_state": self.w.state.get_current_graph_state(),
                "profiles": profiles,
                "drawings": self.w.graph_panel.get_drawings_data()
                if hasattr(self.w, "graph_panel")
                else {},
                "ts": time.time(),
            }

            with open(self.w._autosave_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Autosave failed: %s", e)

    def _restore_autosave(self):
        """Restore from autosave file"""
        try:
            with open(self.w._autosave_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Failed to read autosave file: %s", e)
            return

        datasets = data.get("datasets", [])
        if not datasets:
            return

        self.w._restore_data = data
        self.w._restore_datasets = datasets
        self.w._restore_queue = list(enumerate(datasets))
        self.w._restore_loaded_dataset_ids = set()

        self.w._restore_progress = QProgressDialog(
            "Restoring session...", "Cancel", 0, len(datasets), self.w
        )
        self.w._restore_progress.setWindowModality(Qt.WindowModal)
        self.w._restore_progress.setMinimumDuration(0)
        self.w._restore_progress.show()

        self.w._restore_next()

    def _restore_next(self):
        """Restore one dataset per event-loop tick to keep UI responsive."""
        if not getattr(self.w, "_restore_queue", None):
            self.w._restore_finalize()
            return

        if self.w._restore_progress and self.w._restore_progress.wasCanceled():
            self.w._restore_finalize()
            return

        i, ds = self.w._restore_queue.pop(0)
        if self.w._restore_progress:
            self.w._restore_progress.setValue(i)
            self.w._restore_progress.setLabelText(
                f"Loading: {Path(ds.get('file_path', '')).name}"
            )

        path = ds.get("file_path")
        if path and os.path.exists(path):
            dataset_id = ds.get("id")
            name = ds.get("name")
            new_id = self.w.engine.load_dataset(path, name=name, dataset_id=dataset_id)
            if new_id:
                self.w._restore_loaded_dataset_ids.add(new_id)
                dataset = self.w.engine.get_dataset(new_id)
                memory_bytes = (
                    dataset.df.estimated_size()
                    if dataset and dataset.df is not None
                    else 0
                )
                self.w.state.add_dataset(
                    dataset_id=new_id,
                    name=dataset.name if dataset else name,
                    file_path=path,
                    row_count=self.w.engine.row_count,
                    column_count=self.w.engine.column_count,
                    memory_bytes=memory_bytes,
                )
        else:
            logger.warning(
                "Skipping dataset '%s': file not found at %s",
                ds.get("name", "unknown"),
                path,
            )

        QTimer.singleShot(0, self.w._restore_next)

    def _restore_finalize(self):
        """Finalize autosave restore after queued dataset loading."""
        data = getattr(self.w, "_restore_data", {}) or {}
        datasets = getattr(self.w, "_restore_datasets", []) or []

        if self.w._restore_progress:
            self.w._restore_progress.setValue(len(datasets))
            self.w._restore_progress.close()
            self.w._restore_progress = None

        # Activate dataset
        active_id = data.get("active_dataset_id")
        if active_id and self.w.engine.activate_dataset(active_id):
            self.w._on_dataset_activated(active_id)
        elif self.w.engine.active_dataset_id:
            self.w._on_dataset_activated(self.w.engine.active_dataset_id)

        # Restore profiles into ProfileStore
        profiles_data = data.get("profiles", [])
        loaded_ids = getattr(self.w, "_restore_loaded_dataset_ids", set())
        for p_data in profiles_data:
            try:
                gs = GraphSetting.from_dict(p_data)
                if gs.dataset_id in loaded_ids:
                    self.w.profile_store.add(gs)
            except Exception as e:
                logger.debug("Failed to restore profile from autosave: %s", e)

        # Restore graph settings
        graph_state = data.get("graph_state", {})
        if graph_state:
            self.w._apply_graph_state(graph_state)

        # Restore drawings
        drawings = data.get("drawings", {})
        if drawings and hasattr(self.w, "graph_panel"):
            self.w.graph_panel.load_drawings_data(drawings)

        # Refresh profile tree + graph
        self.w.profile_model.refresh()
        self.w.graph_panel.refresh()
        self.w.summary_panel.refresh()

        self.w._restore_queue = []
        self.w._restore_data = {}
        self.w._restore_datasets = []
        self.w._restore_loaded_dataset_ids = set()

    def _apply_graph_state(self, gs: Dict[str, Any]):
        """Apply graph state dict to current session"""
        try:
            # Chart type
            if gs.get("chart_type"):
                self.w.state.set_chart_type(ChartType(gs["chart_type"]))

            # X column
            self.w.state.set_x_column(gs.get("x_column"))

            # Group columns
            self.w.state.clear_group_zone()
            for g in gs.get("group_columns", []):
                name = g.get("name")
                if name:
                    self.w.state.add_group_column(name)
                    # Set selected values
                    for gc in self.w.state.group_columns:
                        if gc.name == name:
                            gc.selected_values = set(g.get("selected_values", []))

            # Value columns
            self.w.state.clear_value_zone()
            for v in gs.get("value_columns", []):
                name = v.get("name")
                if not name:
                    continue
                agg = AggregationType(v.get("aggregation", "sum"))
                self.w.state.add_value_column(name, aggregation=agg)
                idx = len(self.w.state.value_columns) - 1
                self.w.state.update_value_column(
                    idx,
                    color=v.get("color"),
                    use_secondary_axis=v.get("use_secondary_axis"),
                    formula=v.get("formula"),
                )

            # Group lock
            if 'group_locked' in gs:
                self.w.state.group_locked = gs['group_locked']

            # Hover columns
            self.w.state.clear_hover_columns()
            for h in gs.get("hover_columns", []):
                self.w.state.add_hover_column(h)

            # Chart settings
            cs = gs.get("chart_settings", {})
            if cs:
                self.w.state.update_chart_settings(
                    line_width=cs.get(
                        "line_width", self.w.state.chart_settings.line_width
                    ),
                    marker_size=cs.get(
                        "marker_size", self.w.state.chart_settings.marker_size
                    ),
                    fill_opacity=cs.get(
                        "fill_opacity", self.w.state.chart_settings.fill_opacity
                    ),
                    show_data_labels=cs.get(
                        "show_data_labels", self.w.state.chart_settings.show_data_labels
                    ),
                    x_log_scale=cs.get(
                        "x_log_scale", self.w.state.chart_settings.x_log_scale
                    ),
                    y_log_scale=cs.get(
                        "y_log_scale", self.w.state.chart_settings.y_log_scale
                    ),
                    y_min=cs.get("y_min", self.w.state.chart_settings.y_min),
                    y_max=cs.get("y_max", self.w.state.chart_settings.y_max),
                    y_label=cs.get("y_label", self.w.state.chart_settings.y_label),
                    secondary_y_log_scale=cs.get(
                        "secondary_y_log_scale",
                        self.w.state.chart_settings.secondary_y_log_scale,
                    ),
                    secondary_y_min=cs.get(
                        "secondary_y_min", self.w.state.chart_settings.secondary_y_min
                    ),
                    secondary_y_max=cs.get(
                        "secondary_y_max", self.w.state.chart_settings.secondary_y_max
                    ),
                    secondary_y_label=cs.get(
                        "secondary_y_label",
                        self.w.state.chart_settings.secondary_y_label,
                    ),
                )
        except Exception as e:
            logger.warning("Failed to apply graph state from autosave: %s", e)
