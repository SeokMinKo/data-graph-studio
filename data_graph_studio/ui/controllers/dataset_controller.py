"""Dataset Controller - extracted from MainWindow.

Handles dataset add/remove/activate, comparison modes, comparison views,
overlay stats, side-by-side/difference analysis, and comparison reports.
"""

from __future__ import annotations

import gc
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List

from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QProgressDialog, QApplication, QDialog, QWidget,
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from ...core.state import ComparisonMode
from ...core.undo_manager import UndoCommand, UndoActionType
from ...core.comparison_report import ComparisonReport
from ...core.parsing import ParsingSettings

if TYPE_CHECKING:
    from ..main_window import MainWindow

logger = logging.getLogger(__name__)


class DatasetController:
    """데이터셋 추가/관리/비교 컨트롤러"""

    def __init__(self, window: 'MainWindow'):
        self._w = window

    # ==================== Dataset Add/Manage ====================

    def _on_add_dataset(self):
        """새 데이터셋 추가 (멀티 파일 지원)"""
        w = self._w
        file_paths, _ = QFileDialog.getOpenFileNames(
            w,
            "Add Dataset",
            "",
            "All Supported (*.csv *.tsv *.txt *.log *.dat *.etl *.xlsx *.xls *.parquet *.json);;"
            "CSV/TSV (*.csv *.tsv);;"
            "Text Files (*.txt *.log *.dat);;"
            "ETL Files (*.etl);;"
            "Excel (*.xlsx *.xls);;"
            "Parquet (*.parquet);;"
            "JSON (*.json);;"
            "All Files (*.*)"
        )

        if not file_paths:
            return

        if len(file_paths) == 1:
            self._add_dataset_from_file(file_paths[0])
            return

        progress = QProgressDialog(
            "Loading datasets...", "Cancel", 0, len(file_paths), w
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        for i, file_path in enumerate(file_paths):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"Loading: {Path(file_path).name}")
            QApplication.processEvents()
            self._add_dataset_from_file(file_path)

        progress.setValue(len(file_paths))

    def _add_dataset_from_file(self, file_path: str):
        """파일에서 데이터셋 추가"""
        w = self._w
        try:
            file_size = os.path.getsize(file_path)
            can_load, message = w.engine.can_load_dataset(file_size * 2)
            if not can_load:
                QMessageBox.warning(w, "Memory Limit", message)
                return
            elif message:
                w.statusbar.showMessage(message, 5000)
        except OSError:
            pass

        if not w._file_controller._check_large_file_warning(file_path):
            return

        ext = Path(file_path).suffix.lower()

        if ext in ['.parquet', '.xlsx', '.xls', '.json']:
            self._load_dataset(file_path)
            return

        from ..dialogs.parsing_preview_dialog import ParsingPreviewDialog
        dialog = ParsingPreviewDialog(file_path, w)
        if dialog.exec() == QDialog.Accepted:
            settings = dialog.get_settings()
            self._load_dataset_with_settings(file_path, settings)

    def _load_dataset(self, file_path: str, settings: Optional[ParsingSettings] = None):
        """데이터셋 로드 (새 데이터셋으로 추가)"""
        import uuid
        w = self._w

        dataset_id = str(uuid.uuid4())[:8]
        name = Path(file_path).name

        w._progress_dialog = QProgressDialog(
            f"Loading {name}...",
            "Cancel",
            0, 100,
            w
        )
        w._progress_dialog.setWindowModality(Qt.WindowModal)
        w._progress_dialog.setMinimumDuration(500)
        w._progress_dialog.canceled.connect(w._file_controller._cancel_loading)
        w._progress_dialog.show()

        w._pending_dataset_id = dataset_id
        w._pending_dataset_name = name
        w._pending_dataset_path = file_path

        w._file_controller._cleanup_loader_thread()
        from .file_loading_controller import DataLoaderThread
        w._loader_thread = DataLoaderThread(w.engine, file_path)
        w._loader_thread.progress_updated.connect(w._file_controller._on_loading_progress)
        w._loader_thread.finished_loading.connect(self._on_dataset_loading_finished)
        w._loader_thread.start()

    def _load_dataset_with_settings(self, file_path: str, settings: ParsingSettings):
        """설정을 적용하여 데이터셋 로드"""
        import uuid
        w = self._w

        dataset_id = str(uuid.uuid4())[:8]
        name = Path(file_path).name

        w._progress_dialog = QProgressDialog(
            f"Loading {name}...",
            "Cancel",
            0, 100,
            w
        )
        w._progress_dialog.setWindowModality(Qt.WindowModal)
        w._progress_dialog.setMinimumDuration(500)
        w._progress_dialog.canceled.connect(w._file_controller._cancel_loading)
        w._progress_dialog.show()

        w._pending_dataset_id = dataset_id
        w._pending_dataset_name = name
        w._pending_dataset_path = file_path

        w._file_controller._cleanup_loader_thread()
        from .file_loading_controller import DataLoaderThreadWithSettings
        w._loader_thread = DataLoaderThreadWithSettings(w.engine, file_path, settings)
        w._loader_thread.progress_updated.connect(w._file_controller._on_loading_progress)
        w._loader_thread.finished_loading.connect(self._on_dataset_loading_finished)
        w._loader_thread.start()

    def _on_dataset_loading_finished(self, success: bool):
        """데이터셋 로딩 완료"""
        w = self._w
        if w._progress_dialog:
            w._progress_dialog.close()

        if success:
            dataset_id = getattr(w, '_pending_dataset_id', None)
            name = getattr(w, '_pending_dataset_name', 'Dataset')
            file_path = getattr(w, '_pending_dataset_path', None)

            if dataset_id:
                from ...core.data_engine import DatasetInfo
                dataset_info = DatasetInfo(
                    id=dataset_id,
                    name=name,
                    df=w.engine.df,
                    lazy_df=w.engine._lazy_df,
                    source=w.engine._source,
                    profile=w.engine.profile
                )
                w.engine._datasets[dataset_id] = dataset_info
                w.engine._active_dataset_id = dataset_id

                memory_bytes = w.engine.df.estimated_size() if w.engine.df is not None else 0
                w.state.add_dataset(
                    dataset_id=dataset_id,
                    name=name,
                    file_path=file_path,
                    row_count=w.engine.row_count,
                    column_count=w.engine.column_count,
                    memory_bytes=memory_bytes
                )

                w.state.set_data_loaded(True, w.engine.row_count)
                w.state.set_column_order(w.engine.columns)

                if w.engine.profile:
                    w._update_summary_from_profile()

                w.profile_model.refresh()

                gc.collect()
                logger.info("dataset_controller.dataset_added", extra={"dataset_id": dataset_id, "dataset_name": name, "row_count": w.engine.row_count})

            w._pending_dataset_id = None
            w._pending_dataset_name = None
            w._pending_dataset_path = None
        else:
            error_msg = w.engine.progress.error_message or "Unknown error"
            logger.error("dataset_controller.dataset_load_failed", extra={"error_msg": error_msg})
            QMessageBox.critical(
                w,
                "Error",
                f"Failed to load dataset:\n{error_msg}"
            )

    def _on_dataset_activated(self, dataset_id: str):
        """데이터셋 활성화 요청"""
        w = self._w
        prev_id = w.state.active_dataset_id

        def _activate(target_id: str):
            try:
                if w.state.active_dataset_id:
                    w.state._sync_to_dataset_state(w.state.active_dataset_id)
            except Exception:
                pass

            if w.engine.activate_dataset(target_id):
                w.state.activate_dataset(target_id)

                w.state.set_data_loaded(True, w.engine.row_count)
                w.state.set_column_order(w.engine.columns)

                w.table_panel.set_data(w.engine.df)
                w.graph_panel.set_columns(w.engine.columns)

                if hasattr(w.graph_panel.options_panel, 'data_tab'):
                    w.graph_panel.options_panel.data_tab.set_columns(
                        w.engine.columns, w.engine
                    )

                w.graph_panel.refresh()
                w.summary_panel.refresh()

                if w.engine.profile:
                    w._update_summary_from_profile()

                w.profile_model.refresh()

                metadata = w.state.get_dataset_metadata(target_id)
                if metadata:
                    w.statusbar.showMessage(
                        f"Activated: {metadata.name} ({w.engine.row_count:,} rows)",
                        3000
                    )

        if prev_id == dataset_id:
            _activate(dataset_id)
            return

        # Record as undoable
        w._undo_stack.push(
            UndoCommand(
                action_type=UndoActionType.DATASET_ACTIVATE,
                description=f"Dataset: Activate {dataset_id}",
                do=lambda: _activate(dataset_id),
                undo=(lambda: _activate(prev_id)) if prev_id else (lambda: None),
            )
        )

    def _on_dataset_remove_requested(self, dataset_id: str):
        """데이터셋 제거 요청 (Undo 가능)"""
        w = self._w
        metadata = w.state.get_dataset_metadata(dataset_id)
        name = metadata.name if metadata else dataset_id

        # Capture for undo
        try:
            dataset_info = w.engine.get_dataset(dataset_id)
        except Exception:
            dataset_info = None

        # Memory safety: for large datasets, prefer reload-based undo (no DF snapshot)
        LARGE_UNDO_BYTES = 300 * 1024 * 1024  # 300MB
        can_reload = bool(getattr(metadata, "file_path", None))
        is_large = bool(metadata and getattr(metadata, "memory_bytes", 0) and metadata.memory_bytes > LARGE_UNDO_BYTES)
        use_reload_undo = bool(is_large and can_reload)
        if use_reload_undo:
            dataset_info = None

        state_snapshot = None
        meta_snapshot = None
        try:
            ds_state = w.state.get_dataset_state(dataset_id)
            if ds_state is not None:
                import copy
                state_snapshot = copy.deepcopy(ds_state)
            if metadata is not None:
                import copy
                meta_snapshot = copy.deepcopy(metadata)
        except Exception:
            pass

        prev_active = w.engine.active_dataset_id

        def _remove():
            if w.engine.remove_dataset(dataset_id):
                w.state.remove_dataset(dataset_id)

                if w.engine.dataset_count > 0:
                    self._on_dataset_activated(w.engine.active_dataset_id)
                else:
                    w.state.set_data_loaded(False, 0)
                    w._on_data_cleared()

                w.statusbar.showMessage(f"Removed: {name}", 3000)

        def _restore():
            if meta_snapshot is None:
                return

            # If we have a full snapshot, restore it.
            if dataset_info is not None:
                try:
                    w.engine._datasets[dataset_id] = dataset_info
                except Exception:
                    return
            else:
                # Reload-based undo (large dataset)
                file_path = getattr(meta_snapshot, "file_path", None)
                if not file_path:
                    return
                try:
                    w.engine.load_dataset(file_path, name=getattr(meta_snapshot, "name", name), dataset_id=dataset_id)
                except Exception:
                    return

            # Restore AppState dataset entries
            try:
                if state_snapshot is not None:
                    w.state._dataset_states[dataset_id] = state_snapshot
                w.state._dataset_metadata[dataset_id] = meta_snapshot
                if getattr(meta_snapshot, "compare_enabled", True):
                    if dataset_id not in w.state._comparison_settings.comparison_datasets:
                        w.state._comparison_settings.comparison_datasets.append(dataset_id)
                w.state.dataset_added.emit(dataset_id)
                w.state.dataset_updated.emit(dataset_id)
            except Exception:
                pass

            # Activate previous dataset (or restored one)
            target = prev_active or dataset_id
            self._on_dataset_activated(target)
            w.statusbar.showMessage(f"Restored: {name}", 3000)

        w._undo_stack.push(
            UndoCommand(
                action_type=UndoActionType.DATASET_REMOVE,
                description=f"Dataset: Remove {name}",
                do=_remove,
                undo=_restore,
            )
        )

    # ==================== Comparison Mode ====================

    def _set_comparison_mode(self, mode: ComparisonMode):
        """비교 모드 설정 (메뉴에서 호출, Undo 가능)"""
        w = self._w
        prev = w.state.comparison_mode

        def _apply(m: ComparisonMode):
            w.state.set_comparison_mode(m)
            self._on_comparison_mode_changed(m.value)
            self._update_comparison_mode_actions(m)

        if prev == mode:
            _apply(mode)
            return

        w._undo_stack.push(
            UndoCommand(
                action_type=UndoActionType.COMPARISON_SETTINGS,
                description=f"Compare: Mode → {mode.value}",
                do=lambda: _apply(mode),
                undo=lambda: _apply(prev),
            )
        )

    def _update_comparison_mode_actions(self, mode: ComparisonMode):
        """비교 모드 메뉴 액션 상태 업데이트"""
        w = self._w
        if not hasattr(w, '_comparison_mode_actions'):
            return

        for action_mode, action in w._comparison_mode_actions.items():
            action.setChecked(action_mode == mode)

    def _on_comparison_mode_changed(self, mode_value: str):
        """비교 모드 변경"""
        w = self._w
        try:
            mode = ComparisonMode(mode_value)
            w.state.set_comparison_mode(mode)

            self._update_comparison_mode_actions(mode)

            if mode != ComparisonMode.OVERLAY:
                self._hide_overlay_stats_widget()

            if mode == ComparisonMode.SINGLE:
                w.statusbar.showMessage("Single dataset mode", 2000)
                self._restore_single_view()
            elif mode == ComparisonMode.OVERLAY:
                w.statusbar.showMessage("Overlay comparison mode", 2000)
                self._remove_comparison_view()
                w.graph_panel.refresh()
            elif mode == ComparisonMode.SIDE_BY_SIDE:
                w.statusbar.showMessage("Side-by-side comparison mode", 2000)
            elif mode == ComparisonMode.DIFFERENCE:
                w.statusbar.showMessage("Difference analysis mode", 2000)
        except ValueError:
            pass

    def _on_comparison_started(self, dataset_ids: List[str]):
        """비교 시작"""
        w = self._w
        mode = w.state.comparison_mode

        if len(dataset_ids) < 2:
            QMessageBox.warning(
                w,
                "Comparison",
                "Please select at least 2 datasets for comparison."
            )
            return

        prev_ids = list(w.state.comparison_dataset_ids)

        def _apply(ids: List[str]):
            w.state.set_comparison_datasets(ids)

        w._undo_stack.push(
            UndoCommand(
                action_type=UndoActionType.COMPARISON_SETTINGS,
                description=f"Compare: Datasets → {len(dataset_ids)} selected",
                do=lambda: _apply(dataset_ids),
                undo=lambda: _apply(prev_ids),
            )
        )

        if mode == ComparisonMode.OVERLAY:
            self._start_overlay_comparison(dataset_ids)
        elif mode == ComparisonMode.SIDE_BY_SIDE:
            self._start_side_by_side_comparison(dataset_ids)
        elif mode == ComparisonMode.DIFFERENCE:
            self._start_difference_analysis(dataset_ids)

    # ==================== Comparison Views ====================

    def _start_overlay_comparison(self, dataset_ids: List[str]):
        """오버레이 비교 시작"""
        w = self._w
        w.statusbar.showMessage(
            f"Overlay comparison: {len(dataset_ids)} datasets",
            3000
        )
        w.graph_panel.refresh()
        self._show_overlay_stats_widget()

    def _show_overlay_stats_widget(self):
        """오버레이 통계 위젯 표시"""
        w = self._w
        from ..panels.overlay_stats_widget import OverlayStatsWidget
        if w._overlay_stats_widget is None:
            w._overlay_stats_widget = OverlayStatsWidget(
                w.engine, w.state, w.graph_panel
            )
            w._overlay_stats_widget.close_requested.connect(self._hide_overlay_stats_widget)
            w._overlay_stats_widget.expand_requested.connect(self._show_comparison_stats_panel)

        is_light = bool(getattr(getattr(w, '_theme_manager', None), 'current_theme', None).is_light()) if hasattr(getattr(w, '_theme_manager', None), 'current_theme') else False
        if hasattr(w._overlay_stats_widget, 'apply_theme'):
            w._overlay_stats_widget.apply_theme(is_light)

        w._overlay_stats_widget.set_position("top-right")
        w._overlay_stats_widget.show_animated()

    def _hide_overlay_stats_widget(self):
        """오버레이 통계 위젯 숨기기"""
        w = self._w
        if w._overlay_stats_widget:
            w._overlay_stats_widget.hide_animated()

    def _show_comparison_stats_panel(self):
        """전체 비교 통계 패널 표시 (다이얼로그)"""
        w = self._w
        from ..panels.comparison_stats_panel import ComparisonStatsPanel

        if w._comparison_stats_panel is None:
            w._comparison_stats_panel = ComparisonStatsPanel(
                w.engine, w.state
            )

        is_light = bool(getattr(getattr(w, '_theme_manager', None), 'current_theme', None).is_light()) if hasattr(getattr(w, '_theme_manager', None), 'current_theme') else False
        if hasattr(w._comparison_stats_panel, 'apply_theme'):
            w._comparison_stats_panel.apply_theme(is_light)

        dialog = QDialog(w)
        dialog.setWindowTitle("Comparison Statistics")
        dialog.setMinimumSize(600, 500)

        layout = QVBoxLayout(dialog)
        layout.addWidget(w._comparison_stats_panel)

        w._comparison_stats_panel.refresh()
        dialog.exec()

    def _on_export_comparison_report(self):
        """비교 리포트 내보내기"""
        w = self._w
        dataset_ids = w.state.comparison_dataset_ids

        if len(dataset_ids) < 2:
            QMessageBox.information(
                w,
                "Export Report",
                "Please select at least 2 datasets for comparison first."
            )
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            w,
            "Export Comparison Report",
            "comparison_report",
            "HTML Report (*.html);;JSON Report (*.json);;CSV Report (*.csv)"
        )

        if not file_path:
            return

        if selected_filter.startswith("HTML") and not file_path.endswith('.html'):
            file_path += '.html'
        elif selected_filter.startswith("JSON") and not file_path.endswith('.json'):
            file_path += '.json'
        elif selected_filter.startswith("CSV") and not file_path.endswith('.csv'):
            file_path += '.csv'

        report_gen = ComparisonReport(w.engine, w.state)

        success = False
        if file_path.endswith('.html'):
            success = report_gen.export_html(file_path, dataset_ids)
        elif file_path.endswith('.json'):
            success = report_gen.export_json(file_path, dataset_ids)
        elif file_path.endswith('.csv'):
            success = report_gen.export_csv(file_path, dataset_ids)

        if success:
            QMessageBox.information(
                w,
                "Export Report",
                f"Report exported successfully:\n{file_path}"
            )
        else:
            QMessageBox.warning(
                w,
                "Export Report",
                "Failed to export report. Please check the file path and try again."
            )

    def _start_side_by_side_comparison(self, dataset_ids: List[str]):
        """병렬 비교 시작"""
        w = self._w
        w.statusbar.showMessage(
            f"Side-by-side comparison: {len(dataset_ids)} datasets",
            3000
        )

        self._remove_comparison_view()

        from ..panels.side_by_side_layout import SideBySideLayout
        if w._side_by_side_layout is None:
            w._side_by_side_layout = SideBySideLayout(w.engine, w.state)
            w._side_by_side_layout.dataset_activated.connect(self._on_dataset_activated)

        self._show_comparison_view(w._side_by_side_layout)
        w._side_by_side_layout.refresh()

    def _start_difference_analysis(self, dataset_ids: List[str]):
        """차이 분석 시작"""
        w = self._w
        if len(dataset_ids) != 2:
            QMessageBox.warning(
                w,
                "Difference Analysis",
                "Please select exactly 2 datasets for difference analysis."
            )
            return

        w.statusbar.showMessage(
            "Difference analysis: comparing 2 datasets",
            3000
        )

        self._remove_comparison_view()

        from ..panels.comparison_stats_panel import ComparisonStatsPanel
        if w._comparison_stats_panel is None:
            w._comparison_stats_panel = ComparisonStatsPanel(w.engine, w.state)

        self._show_comparison_view(w._comparison_stats_panel)
        w._comparison_stats_panel.refresh()

    def _show_comparison_view(self, view_widget: QWidget):
        """비교 뷰를 그래프 패널 위치에 표시"""
        w = self._w
        graph_index = -1
        for i in range(w.main_splitter.count()):
            if w.main_splitter.widget(i) is w.graph_panel:
                graph_index = i
                break

        if graph_index < 0:
            return

        current_sizes = w.main_splitter.sizes()

        w.graph_panel.hide()
        w.main_splitter.replaceWidget(graph_index, view_widget)
        view_widget.show()

        w.main_splitter.setSizes(current_sizes)

        w._current_comparison_view = view_widget

    def _remove_comparison_view(self):
        """비교 뷰를 제거하고 그래프 패널 복원"""
        w = self._w
        if w._current_comparison_view is None:
            return

        view_index = -1
        for i in range(w.main_splitter.count()):
            if w.main_splitter.widget(i) is w._current_comparison_view:
                view_index = i
                break

        if view_index < 0:
            return

        current_sizes = w.main_splitter.sizes()

        w._current_comparison_view.hide()
        w._current_comparison_view.setParent(None)
        w.main_splitter.insertWidget(view_index, w.graph_panel)
        w.graph_panel.show()

        w.main_splitter.setSizes(current_sizes)

        w._current_comparison_view = None

    def _restore_single_view(self):
        """단일 뷰 모드로 복귀"""
        self._remove_comparison_view()
        self._w.graph_panel.refresh()

    # ==================== Profile Comparison Views ====================

    def _on_profile_comparison_started(self, mode_value: str, profile_ids: list):
        """Handle profile comparison started — create appropriate renderer."""
        w = self._w
        self._remove_comparison_view()

        dataset_id = w.profile_comparison_controller.dataset_id

        try:
            mode = ComparisonMode(mode_value)
        except ValueError:
            mode = ComparisonMode.SIDE_BY_SIDE

        from ..panels.profile_side_by_side import ProfileSideBySideLayout
        from ..panels.profile_overlay import ProfileOverlayRenderer
        from ..panels.profile_difference import ProfileDifferenceRenderer

        if mode == ComparisonMode.SIDE_BY_SIDE:
            view = ProfileSideBySideLayout(
                dataset_id, w.engine, w.state, w.profile_store,
            )
            view.exit_requested.connect(w.profile_comparison_controller.stop_comparison)
            view.set_profiles(profile_ids)
            w._comparison_adapter.panel_removed.connect(view.on_profile_deleted)
            w.profile_controller.subscribe("profile_renamed", view.on_profile_renamed)

            w._compare_toolbar.grid_layout_changed.connect(view.set_grid_layout)
            w._compare_toolbar.sync_changed.connect(view.set_sync_option)
            w._compare_toolbar.exit_requested.connect(
                w.profile_comparison_controller.stop_comparison
            )
            w._compare_toolbar.reset_to_defaults()
            is_light = bool(getattr(getattr(w, '_theme_manager', None), 'current_theme', None).is_light()) if hasattr(getattr(w, '_theme_manager', None), 'current_theme') else False
            if hasattr(w._compare_toolbar, 'apply_theme'):
                w._compare_toolbar.apply_theme(is_light)
            w._compare_toolbar.show()

        elif mode == ComparisonMode.OVERLAY:
            view = ProfileOverlayRenderer(
                dataset_id, w.engine, w.state, w.profile_store,
            )
            view.exit_requested.connect(w.profile_comparison_controller.stop_comparison)
            view.set_profiles(profile_ids)

        elif mode == ComparisonMode.DIFFERENCE:
            if len(profile_ids) != 2:
                return
            view = ProfileDifferenceRenderer(
                dataset_id, w.engine, w.state, w.profile_store,
            )
            view.exit_requested.connect(w.profile_comparison_controller.stop_comparison)
            view.set_profiles(profile_ids[0], profile_ids[1])

        else:
            return

        is_light = bool(getattr(getattr(w, '_theme_manager', None), 'current_theme', None).is_light()) if hasattr(getattr(w, '_theme_manager', None), 'current_theme') else False
        if hasattr(view, 'apply_theme'):
            view.apply_theme(is_light)

        w._profile_comparison_view = view
        self._show_comparison_view(view)
        w.statusbar.showMessage(
            f"Profile comparison ({mode_value}): {len(profile_ids)} profiles", 3000,
        )

    def _on_profile_comparison_ended(self):
        """Handle profile comparison ended — restore graph panel."""
        w = self._w
        if w._profile_comparison_view is not None:
            try:
                w._compare_toolbar.grid_layout_changed.disconnect()
            except RuntimeError:
                pass
            try:
                w._compare_toolbar.sync_changed.disconnect()
            except RuntimeError:
                pass
            try:
                w._compare_toolbar.exit_requested.disconnect()
            except RuntimeError:
                pass

        w._compare_toolbar.hide()

        self._remove_comparison_view()
        w._profile_comparison_view = None
        w.graph_panel.refresh()
        w.statusbar.showMessage("Profile comparison ended", 2000)
