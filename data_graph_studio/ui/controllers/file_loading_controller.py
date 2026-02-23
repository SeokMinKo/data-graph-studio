"""File Loading Controller - extracted from MainWindow.

Handles file open/save, parsing preview, recent files, clipboard import,
sample data, drag-and-drop file handling, and async loading threads.
"""

from __future__ import annotations

import gc
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List

from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QProgressDialog, QApplication, QDialog,
)
from PySide6.QtCore import Qt, QThread, Signal

from ...core.data_engine import DataEngine, LoadingProgress
from ..clipboard_manager import ClipboardManager
from ...core.parsing import ParsingSettings
from ...utils.memory import MemoryMonitor

if TYPE_CHECKING:
    from ..main_window import MainWindow

logger = logging.getLogger(__name__)


class DataLoaderThread(QThread):
    """비동기 데이터 로딩 스레드"""
    progress_updated = Signal(object)  # LoadingProgress
    finished_loading = Signal(bool)  # success

    def __init__(self, engine: DataEngine, file_path: str):
        super().__init__()
        self.engine = engine
        self.file_path = file_path

    def run(self):
        """Load the file in the background and emit finished_loading when done."""
        self.engine.set_progress_callback(self._on_progress)
        success = self.engine.load_file(self.file_path, optimize_memory=True)
        self.finished_loading.emit(success)

    def _on_progress(self, progress: LoadingProgress):
        self.progress_updated.emit(progress)


class DataLoaderThreadWithSettings(QThread):
    """비동기 데이터 로딩 스레드 (파싱 설정 적용)"""
    progress_updated = Signal(object)  # LoadingProgress
    finished_loading = Signal(bool)  # success

    def __init__(self, engine: DataEngine, file_path: str, settings: ParsingSettings):
        super().__init__()
        self.engine = engine
        self.file_path = file_path
        self.settings = settings

    def run(self):
        """Load the file with parsing settings in the background and emit finished_loading."""
        self.engine.set_progress_callback(self._on_progress)

        # Get process filter for ETL files
        process_filter = None
        if hasattr(self.settings, 'etl_selected_processes') and self.settings.etl_selected_processes:
            process_filter = self.settings.etl_selected_processes

        success = self.engine.load_file(
            self.file_path,
            file_type=self.settings.file_type,
            encoding=self.settings.encoding,
            delimiter=self.settings.delimiter,
            delimiter_type=self.settings.delimiter_type,
            regex_pattern=self.settings.regex_pattern if self.settings.regex_pattern else None,
            has_header=self.settings.has_header,
            skip_rows=self.settings.skip_rows,
            comment_char=self.settings.comment_char if self.settings.comment_char else None,
            excluded_columns=self.settings.excluded_columns if self.settings.excluded_columns else None,
            process_filter=process_filter,
            optimize_memory=True
        )
        self.finished_loading.emit(success)

    def _on_progress(self, progress: LoadingProgress):
        self.progress_updated.emit(progress)


class FileLoadingController:
    """파일 로딩/저장/최근파일/클립보드/샘플 데이터 관리 컨트롤러"""

    def __init__(self, window: 'MainWindow'):
        self._w = window
        self._file_watcher = None
        self._watch_enabled = False

    # ==================== File Open ====================

    def _on_open_file(self):
        """파일 열기 다이얼로그 - 새 프로젝트 마법사 사용"""
        file_path, _ = QFileDialog.getOpenFileName(
            self._w,
            "Open Data File",
            "",
            "All Supported (*.csv *.tsv *.txt *.log *.dat *.etl *.xlsx *.xls *.parquet *.json *.dgs);;"
            "Project Files (*.dgs);;"
            "CSV/TSV (*.csv *.tsv);;"
            "Text Files (*.txt *.log *.dat);;"
            "ETL Files (*.etl);;"
            "Excel (*.xlsx *.xls);;"
            "Parquet (*.parquet);;"
            "JSON (*.json);;"
            "All Files (*.*)"
        )

        if file_path:
            ext = Path(file_path).suffix.lower()
            if ext == '.dgs':
                self._load_project_file(file_path)
                return
            self._show_new_project_wizard(file_path)

    def _on_open_file_without_wizard(self):
        """파일 열기 (마법사 없이) - Ctrl+Shift+O"""
        file_path, _ = QFileDialog.getOpenFileName(
            self._w,
            "Open Data File (Without Wizard)",
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

        if file_path:
            self._show_parsing_preview(file_path)

    def _on_open_multiple_files(self):
        """다중 파일 열기 다이얼로그"""
        from ..dialogs.multi_file_dialog import open_multi_file_dialog
        from ...core.state import ComparisonMode

        w = self._w
        result = open_multi_file_dialog(w, w.engine)

        if result is None:
            return

        file_paths, naming_option, auto_compare = result

        if not file_paths:
            return

        progress = QProgressDialog(
            "Loading files...", "Cancel", 0, len(file_paths), w
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        loaded_ids = []

        for i, file_path in enumerate(file_paths):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            progress.setLabelText(f"Loading: {Path(file_path).name}")
            QApplication.processEvents()

            if naming_option == "filename":
                name = Path(file_path).name
            elif naming_option == "filename_no_ext":
                name = Path(file_path).stem
            elif naming_option == "sequential":
                name = f"Data {len(w.engine.datasets) + 1}"
            else:
                name = Path(file_path).name

            dataset_id = w.engine.load_dataset(file_path, name=name)

            if dataset_id:
                loaded_ids.append(dataset_id)
                dataset = w.engine.get_dataset(dataset_id)
                if dataset:
                    w.state.add_dataset(
                        dataset_id=dataset_id,
                        name=name,
                        row_count=dataset.row_count,
                        column_count=dataset.column_count,
                        memory_bytes=dataset.memory_bytes
                    )

        progress.setValue(len(file_paths))
        progress.close()

        if loaded_ids:
            w.statusbar.showMessage(
                f"Loaded {len(loaded_ids)} datasets successfully", 3000
            )

            if loaded_ids:
                w.engine.activate_dataset(loaded_ids[0])
                w._on_data_loaded()

            if auto_compare and len(loaded_ids) >= 2:
                w.state.set_comparison_datasets(loaded_ids[:4])
                w.state.set_comparison_mode(ComparisonMode.OVERLAY)
                w._on_comparison_started(loaded_ids[:4])

    def _on_open_multiple_files_with_paths(self, file_paths: List[str]):
        """드롭된 여러 파일을 멀티 데이터셋으로 로드"""
        from ...core.state import ComparisonMode
        w = self._w

        progress = QProgressDialog(
            "Loading files...", "Cancel", 0, len(file_paths), w
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        loaded_ids = []
        for i, file_path in enumerate(file_paths):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"Loading: {Path(file_path).name}")
            QApplication.processEvents()

            name = Path(file_path).name
            dataset_id = w.engine.load_dataset(file_path, name=name)
            if dataset_id:
                loaded_ids.append(dataset_id)
                dataset = w.engine.get_dataset(dataset_id)
                if dataset:
                    w.state.add_dataset(
                        dataset_id=dataset_id,
                        name=name,
                        row_count=dataset.row_count,
                        column_count=dataset.column_count,
                        memory_bytes=dataset.memory_bytes,
                    )

        progress.setValue(len(file_paths))
        progress.close()

        if loaded_ids:
            w.engine.activate_dataset(loaded_ids[0])
            w._on_data_loaded()
            w.statusbar.showMessage(f"Loaded {len(loaded_ids)} datasets", 3000)

            if len(loaded_ids) >= 2:
                w.state.set_comparison_datasets(loaded_ids[:4])
                w.state.set_comparison_mode(ComparisonMode.OVERLAY)
                w._on_comparison_started(loaded_ids[:4])

    # ==================== Wizard / Preview ====================

    def _show_new_project_wizard(self, file_path: str):
        """새 프로젝트 마법사 표시"""
        if not self._check_large_file_warning(file_path):
            return

        from ..wizards.new_project_wizard import NewProjectWizard
        wizard = NewProjectWizard(file_path, self._w)
        wizard.project_created.connect(self._on_wizard_project_created)
        wizard.exec()

    def _on_wizard_project_created(self, result: dict):
        """마법사에서 프로젝트 생성 완료 시 호출"""
        parsing_settings = result.get('parsing_settings')
        graph_setting = result.get('graph_setting')
        project_name = result.get('project_name')

        if parsing_settings is None:
            return

        self._w._pending_wizard_result = {
            'graph_setting': graph_setting,
            'project_name': project_name,
        }

        self._load_file_with_settings(parsing_settings.file_path, parsing_settings)

    def _show_parsing_preview(self, file_path: str):
        """파싱 미리보기 다이얼로그 표시 (모든 포맷 지원)"""
        if not self._check_large_file_warning(file_path):
            return

        ext = Path(file_path).suffix.lower()

        if ext in ['.parquet', '.xlsx', '.xls', '.json']:
            # Show quick preview for binary formats before loading
            self._show_binary_format_preview(file_path, ext)
            return

        from ..dialogs.parsing_preview_dialog import ParsingPreviewDialog
        dialog = ParsingPreviewDialog(file_path, self._w)
        if dialog.exec() == QDialog.Accepted:
            settings = dialog.get_settings()
            self._load_file_with_settings(file_path, settings)

    def _show_binary_format_preview(self, file_path: str, ext: str):
        """Parquet/Excel/JSON 파일 미리보기 후 로드"""
        import polars as pl
        w = self._w
        try:
            if ext == '.parquet':
                preview_df = pl.read_parquet(file_path, n_rows=20)
            elif ext in ('.xlsx', '.xls'):
                preview_df = pl.read_excel(file_path).head(20)
            elif ext == '.json':
                preview_df = pl.read_json(file_path).head(20)
            else:
                self._load_file(file_path)
                return

            # Show preview dialog
            info = (
                f"File: {Path(file_path).name}\n"
                f"Format: {ext.upper().lstrip('.')}\n"
                f"Preview: {len(preview_df)} rows × {len(preview_df.columns)} columns\n\n"
                f"Columns: {', '.join(preview_df.columns[:20])}"
                f"{'...' if len(preview_df.columns) > 20 else ''}"
            )
            reply = QMessageBox.question(
                w, "File Preview",
                f"{info}\n\nLoad this file?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._load_file(file_path)
        except Exception as e:
            # If preview fails, just load directly
            logger.warning("file_loading_controller.preview_failed", extra={"path": file_path, "error": e}, exc_info=True)
            self._load_file(file_path)

    def _check_large_file_warning(self, file_path: str) -> bool:
        """대용량 파일 경고 다이얼로그 표시. 계속 진행하면 True 반환"""
        w = self._w
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        except OSError:
            return True

        if file_size_mb >= w.HUGE_FILE_WARNING_MB:
            sys_mem = MemoryMonitor.get_system_memory()
            reply = QMessageBox.warning(
                w,
                "Very Large File Warning",
                f"⚠️ This file is very large ({file_size_mb:.0f} MB).\n\n"
                f"Loading may:\n"
                f"  • Take a long time\n"
                f"  • Use significant memory (estimated {file_size_mb * 2:.0f}+ MB)\n"
                f"  • Cause system slowdown\n\n"
                f"Current available memory: {sys_mem['available_gb']:.1f} GB\n\n"
                f"Do you want to continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return False
        elif file_size_mb >= w.LARGE_FILE_WARNING_MB:
            reply = QMessageBox.question(
                w,
                "Large File",
                f"This file is {file_size_mb:.0f} MB.\n"
                f"Loading may take some time.\n\n"
                f"Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return False

        return True

    # ==================== Loading ====================

    def _cleanup_loader_thread(self):
        """기존 로더 스레드 정리"""
        w = self._w
        if w._loader_thread is not None:
            # Disconnect all signals before stopping to prevent stale signal
            # delivery after a new load has already started.
            try:
                w._loader_thread.finished_loading.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected or no connections
            try:
                w._loader_thread.progress_updated.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected or no connections

            if w._loader_thread.isRunning():
                logger.debug("Waiting for previous loader thread to finish...")
                w.engine.cancel_loading()
                if not w._loader_thread.wait(2000):
                    logger.warning("Loader thread did not finish in time, terminating...")
                    w._loader_thread.terminate()
                    w._loader_thread.wait(1000)
            w._loader_thread = None
            gc.collect()

    def _load_file(self, file_path: str, settings: Optional[ParsingSettings] = None):
        """파일 로드 (설정 없이 - 바이너리 포맷용)"""
        w = self._w
        self._cleanup_loader_thread()

        self._progress_dialog = QProgressDialog(
            f"Loading {Path(file_path).name}...",
            "Cancel",
            0, 100,
            w
        )
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setAutoClose(True)
        self._progress_dialog.setMinimumDuration(500)
        self._progress_dialog.setMinimumWidth(400)
        self._progress_dialog.canceled.connect(self._cancel_loading)
        # Keep w._progress_dialog in sync for any code that checks it
        w._progress_dialog = self._progress_dialog

        w._loader_thread = DataLoaderThread(w.engine, file_path)
        w._loader_thread.progress_updated.connect(self._on_loading_progress)
        w._loader_thread.finished_loading.connect(self._on_loading_finished)
        w._loader_thread.start()

    def _load_file_with_settings(self, file_path: str, settings: ParsingSettings):
        """파일 로드 (파싱 설정 적용)"""
        w = self._w
        self._cleanup_loader_thread()

        self._progress_dialog = QProgressDialog(
            f"Loading {Path(file_path).name}...",
            "Cancel",
            0, 100,
            w
        )
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setAutoClose(True)
        self._progress_dialog.setMinimumDuration(500)
        self._progress_dialog.setMinimumWidth(400)
        self._progress_dialog.canceled.connect(self._cancel_loading)
        # Keep w._progress_dialog in sync for any code that checks it
        w._progress_dialog = self._progress_dialog

        w._loader_thread = DataLoaderThreadWithSettings(w.engine, file_path, settings)
        w._loader_thread.progress_updated.connect(self._on_loading_progress)
        w._loader_thread.finished_loading.connect(self._on_loading_finished)
        w._loader_thread.start()

    def _on_loading_progress(self, progress: LoadingProgress):
        """로딩 진행률 업데이트"""
        dlg = getattr(self, '_progress_dialog', None) or self._w._progress_dialog
        if dlg:
            dlg.setValue(int(progress.progress_percent))

            try:
                proc_mem = MemoryMonitor.get_process_memory()
                mem_str = MemoryMonitor.format_memory(proc_mem['rss_mb'])
            except Exception:
                logger.warning("file_loading_controller.progress.memory_check.error", exc_info=True)
                mem_str = "--"

            eta_str = ""
            if progress.eta_seconds > 0:
                eta_str = f"\nETA: {progress.eta_seconds:.0f}s"

            dlg.setLabelText(
                f"Loading... {progress.status}\n"
                f"{progress.loaded_rows:,} rows loaded\n"
                f"Memory: {mem_str}{eta_str}"
            )

    def _on_loading_finished(self, success: bool):
        """로딩 완료"""
        w = self._w
        dlg = getattr(self, '_progress_dialog', None) or w._progress_dialog
        if dlg:
            dlg.close()
        self._progress_dialog = None
        w._progress_dialog = None

        if success:
            w.state.set_data_loaded(True, w.engine.row_count)
            w.state.set_column_order(w.engine.columns)

            if w.engine.dataset_count == 0:
                import uuid
                dataset_id = str(uuid.uuid4())[:8]
                name = Path(w.engine._source.path).name if w.engine._source and w.engine._source.path else "Dataset"
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
                    file_path=w.engine._source.path if w.engine._source else None,
                    row_count=w.engine.row_count,
                    column_count=w.engine.column_count,
                    memory_bytes=memory_bytes
                )

            if w.engine.profile:
                w._update_summary_from_profile()

            w.profile_model.refresh()

            gc.collect()
            logger.info("file_loading_controller.data_loaded", extra={"row_count": w.engine.row_count, "column_count": w.engine.column_count})

            # Add to recent files
            source_path = w.engine._source.path if w.engine._source and w.engine._source.path else None
            if source_path and source_path != "clipboard":
                self._add_to_recent_files(source_path)

            w._apply_pending_wizard_result()
        else:
            error_msg = w.engine.progress.error_message or "Unknown error"
            logger.error("file_loading_controller.file_load_failed", extra={"error_msg": error_msg})
            QMessageBox.critical(
                w,
                "Error",
                f"Failed to load file:\n{error_msg}"
            )

    def _cancel_loading(self):
        """로딩 취소"""
        w = self._w
        if w._loader_thread and w._loader_thread.isRunning():
            logger.info("Loading cancelled by user")
            w.engine.cancel_loading()
            w._loader_thread.wait(2000)
            w._loader_thread = None
            gc.collect()
            w.statusbar.showMessage("Loading cancelled", 3000)

    # ==================== Project File ====================

    def _load_project_file(self, file_path: str):
        """프로젝트 파일 (.dgs) 로드"""
        from ...core.project import Project
        from ...core.profile import GraphSetting
        w = self._w
        try:
            project = Project.load(file_path)
            project_dir = Path(file_path).parent

            errors = project.validate()
            if errors:
                QMessageBox.warning(
                    w, "Load Project",
                    "Some data files not found:\n" + "\n".join(errors)
                )

            loaded_count = 0
            active_dataset_id = None
            for ds in project.get_all_data_sources():
                resolved_path = ds.resolve(str(project_dir))
                if os.path.exists(resolved_path):
                    dataset_id = w.engine.load_dataset(resolved_path, name=ds.name)
                    if dataset_id:
                        loaded_count += 1
                        dataset = w.engine.get_dataset(dataset_id)
                        if dataset:
                            w.state.add_dataset(
                                dataset_id=dataset_id,
                                name=ds.name or Path(resolved_path).name,
                                row_count=dataset.row_count,
                                column_count=dataset.column_count,
                                memory_bytes=dataset.memory_bytes
                            )
                        if ds.is_active:
                            active_dataset_id = dataset_id

            if active_dataset_id:
                w.engine.activate_dataset(active_dataset_id)
            elif loaded_count > 0:
                ids = w.engine.get_dataset_ids() if hasattr(w.engine, 'get_dataset_ids') else []
                if ids:
                    w.engine.activate_dataset(ids[0])

            for profile_dict in project.profiles:
                try:
                    gs = GraphSetting.from_dict(profile_dict)
                    w.profile_store.add(gs)
                except Exception as e:
                    logger.warning("file_loading_controller.restore_profile_failed", extra={"error": e}, exc_info=True)

            w._last_project_path = file_path
            w.statusbar.showMessage(f"Project loaded: {file_path} ({loaded_count} datasets, {len(project.profiles)} profiles)", 3000)

            if loaded_count > 0:
                w._on_data_loaded()

        except Exception as e:
            logger.exception("file_loading_controller.load_project_file.error")
            QMessageBox.critical(
                w, "Load Project Error",
                f"Failed to load project file:\n{e}"
            )

    # ==================== Sample Data ====================

    def _on_load_sample_data(self):
        """샘플 데이터 생성 및 로드"""
        import tempfile
        import polars as pl
        import numpy as np
        from datetime import datetime, timedelta

        np.random.seed(42)
        n_rows = 500

        base_date = datetime(2024, 1, 1)
        dates = [base_date + timedelta(days=i % 365) for i in range(n_rows)]

        regions = np.random.choice(['서울', '부산', '대구', '인천', '광주'], n_rows)
        products = np.random.choice(['노트북', '스마트폰', '태블릿', '모니터', '키보드'], n_rows)

        base_sales = 10000 + np.random.normal(0, 2000, n_rows)
        seasonal = 3000 * np.sin(np.arange(n_rows) * 2 * np.pi / 365)
        sales = np.maximum(base_sales + seasonal, 1000).astype(int)

        quantity = np.random.randint(1, 50, n_rows)
        price = np.random.choice([150, 300, 500, 900, 1200], n_rows)

        df = pl.DataFrame({
            'date': dates,
            'region': regions,
            'product': products,
            'sales': sales,
            'quantity': quantity,
            'price': price,
        })

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            df.write_csv(f.name)
            temp_path = f.name

        self._show_parsing_preview(temp_path)

    # ==================== Clipboard ====================

    def _on_import_from_clipboard(self):
        """클립보드에서 데이터 직접 임포트"""
        self._paste_from_clipboard()

    def _paste_from_clipboard(self):
        """클립보드에서 데이터 붙여넣기"""
        w = self._w
        if not ClipboardManager.has_table_data():
            w.statusBar().showMessage("No valid table data in clipboard", 3000)
            return

        df, message = ClipboardManager.paste_as_dataframe()

        if df is not None and len(df) > 0:
            try:
                # Use official DatasetManager API instead of direct _df assignment
                dataset_id = w.engine.load_dataset_from_dataframe(
                    df, name="Clipboard Data", source_path="clipboard"
                )
                if dataset_id:
                    w.engine.activate_dataset(dataset_id)
                    memory_bytes = df.estimated_size()
                    w.state.add_dataset(
                        dataset_id=dataset_id,
                        name="Clipboard Data",
                        row_count=len(df),
                        column_count=len(df.columns),
                        memory_bytes=memory_bytes,
                    )
                    w.state.set_data_loaded(True, len(df))
                    w.state.set_column_order(df.columns)
                    w._on_data_loaded()
                    w.statusBar().showMessage(f"✓ {message}", 5000)
                else:
                    w.statusBar().showMessage("Failed to load clipboard data", 5000)
            except Exception as e:
                logger.exception("file_loading_controller.paste_clipboard.error")
                w.statusBar().showMessage(f"Paste error: {e}", 5000)
        else:
            w.statusBar().showMessage(message, 3000)

    # ==================== Recent Files ====================

    def _update_recent_files_menu(self):
        """최근 파일 메뉴 업데이트 (Enhanced UX: parent folder, pin, gray missing)"""
        from PySide6.QtGui import QAction
        w = self._w
        w._recent_files_menu.clear()

        recent_data = self._get_recent_files_data()
        pinned = recent_data.get('pinned', [])
        files = recent_data.get('files', [])

        # Show pinned first
        all_entries = [(f, True) for f in pinned if f not in files[:0]] + [(f, False) for f in files]
        # Deduplicate
        seen = set()
        unique_entries = []
        for fp, is_pinned in all_entries:
            if fp not in seen:
                seen.add(fp)
                unique_entries.append((fp, fp in pinned))

        if not unique_entries:
            no_files_action = QAction("(No recent files)", w)
            no_files_action.setEnabled(False)
            w._recent_files_menu.addAction(no_files_action)
        else:
            for file_path, is_pinned in unique_entries[:15]:
                p = Path(file_path)
                parent = str(p.parent).replace(str(Path.home()), '~')
                prefix = "📌 " if is_pinned else ""
                label = f"{prefix}{p.name}  ({parent})"
                action = QAction(label, w)
                action.setToolTip(file_path)
                action.setStatusTip(file_path)
                exists = p.exists()
                if not exists:
                    action.setEnabled(False)
                action.triggered.connect(lambda checked, fp=file_path: self._open_recent_file(fp))
                w._recent_files_menu.addAction(action)

            w._recent_files_menu.addSeparator()
            clear_action = QAction("Clear Recent Files", w)
            clear_action.triggered.connect(self._clear_recent_files)
            w._recent_files_menu.addAction(clear_action)

    def _get_recent_files_data(self) -> dict:
        """최근 파일 데이터 (files + pinned) 가져오기"""
        try:
            recent_file_path = Path.home() / ".data_graph_studio" / "recent_files.json"
            if recent_file_path.exists():
                with open(recent_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            logger.warning("file_loading_controller.get_recent_files.error", exc_info=True)
        return {'files': [], 'pinned': []}

    def _get_recent_files(self) -> List[str]:
        """최근 파일 목록 가져오기 (existing files only)"""
        data = self._get_recent_files_data()
        return [f for f in data.get('files', []) if Path(f).exists()]

    def _pin_recent_file(self, file_path: str):
        """최근 파일 핀 토글"""
        try:
            data = self._get_recent_files_data()
            pinned = data.get('pinned', [])
            if file_path in pinned:
                pinned.remove(file_path)
            else:
                pinned.insert(0, file_path)
            data['pinned'] = pinned
            recent_file_path = Path.home() / ".data_graph_studio" / "recent_files.json"
            with open(recent_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._update_recent_files_menu()
        except Exception as e:
            logger.debug("file_loading_controller.pin_recent_file_failed", extra={"error": e}, exc_info=True)

    def _add_to_recent_files(self, file_path: str):
        """최근 파일에 추가"""
        try:
            recent_dir = Path.home() / ".data_graph_studio"
            recent_dir.mkdir(parents=True, exist_ok=True)
            recent_file_path = recent_dir / "recent_files.json"

            data = self._get_recent_files_data()
            recent_files = data.get('files', [])
            if file_path in recent_files:
                recent_files.remove(file_path)
            recent_files.insert(0, file_path)
            recent_files = recent_files[:20]
            data['files'] = recent_files

            with open(recent_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self._update_recent_files_menu()
        except Exception as e:
            logger.debug("file_loading_controller.add_recent_file_failed", extra={"error": e}, exc_info=True)

    def _open_recent_file(self, file_path: str):
        """최근 파일 열기"""
        if Path(file_path).exists():
            self._show_parsing_preview(file_path)
        else:
            QMessageBox.warning(self._w, "File Not Found", f"File no longer exists:\n{file_path}")
            self._update_recent_files_menu()

    def _clear_recent_files(self):
        """최근 파일 목록 지우기"""
        try:
            recent_file_path = Path.home() / ".data_graph_studio" / "recent_files.json"
            if recent_file_path.exists():
                recent_file_path.unlink()
            self._update_recent_files_menu()
            self._w.statusbar.showMessage("Recent files cleared", 3000)
        except Exception as e:
            logger.debug("file_loading_controller.clear_recent_files_failed", extra={"error": e}, exc_info=True)

    # ==================== File Watch ====================

    def _toggle_file_watch(self, enabled: bool):
        """파일 감시 토글"""
        from PySide6.QtCore import QFileSystemWatcher
        w = self._w
        self._watch_enabled = enabled

        if enabled:
            source_path = w.engine._source.path if w.engine._source else None
            if source_path and Path(source_path).exists():
                if self._file_watcher is None:
                    self._file_watcher = QFileSystemWatcher(w)
                    self._file_watcher.fileChanged.connect(self._on_watched_file_changed)
                self._file_watcher.addPath(source_path)
                w.statusbar.showMessage(f"Watching: {Path(source_path).name}", 3000)
            else:
                w.statusbar.showMessage("No file to watch", 3000)
        else:
            if self._file_watcher is not None:
                paths = self._file_watcher.files()
                if paths:
                    self._file_watcher.removePaths(paths)
                w.statusbar.showMessage("File watch disabled", 3000)

    def _on_watched_file_changed(self, path: str):
        """감시 중인 파일이 변경되었을 때"""
        w = self._w
        reply = QMessageBox.question(
            w, "File Changed",
            f"The file has been modified externally:\n{Path(path).name}\n\nReload?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._load_file(path)
        # Re-add to watcher (some OS remove after change)
        if self._file_watcher and Path(path).exists():
            self._file_watcher.addPath(path)

    # ==================== URL Import ====================

    def _import_from_url(self):
        """URL에서 데이터 임포트"""
        from PySide6.QtWidgets import QInputDialog
        import polars as pl

        w = self._w
        url, ok = QInputDialog.getText(
            w, "Import from URL",
            "Enter data URL (CSV, Parquet, or JSON):"
        )
        if not ok or not url.strip():
            return

        url = url.strip()
        w.statusbar.showMessage(f"Importing from {url}...", 0)
        QApplication.processEvents()

        try:
            url_lower = url.lower()
            if url_lower.endswith('.parquet'):
                df = pl.read_parquet(url)
            elif url_lower.endswith('.json'):
                df = pl.read_json(url)
            else:
                df = pl.read_csv(url)

            dataset_id = w.engine.load_dataset_from_dataframe(
                df, name=Path(url).name or "URL Data", source_path=url
            )
            if dataset_id:
                w.engine.activate_dataset(dataset_id)
                memory_bytes = df.estimated_size()
                w.state.add_dataset(
                    dataset_id=dataset_id,
                    name=Path(url).name or "URL Data",
                    row_count=len(df),
                    column_count=len(df.columns),
                    memory_bytes=memory_bytes,
                )
                w._on_data_loaded()
                w.statusbar.showMessage(f"✓ Loaded {len(df):,} rows from URL", 5000)
            else:
                w.statusbar.showMessage("Failed to load URL data", 5000)
        except Exception as e:
            logger.exception("file_loading_controller.import_url.error")
            QMessageBox.warning(w, "URL Import Error", f"Failed to import from URL:\n{e}")
            w.statusbar.showMessage("URL import failed", 3000)

    # ==================== Loading Profiles ====================

    def _save_loading_profile(self):
        """현재 파싱 설정을 프로필로 저장"""
        from PySide6.QtWidgets import QInputDialog
        w = self._w

        name, ok = QInputDialog.getText(w, "Save Loading Profile", "Profile name:")
        if not ok or not name.strip():
            return

        source = w.engine._source
        if not source:
            w.statusbar.showMessage("No loading settings to save", 3000)
            return

        profile = {
            'name': name.strip(),
            'encoding': source.encoding if source.encoding else 'utf-8',
            'delimiter': source.delimiter if source.delimiter else ',',
            'has_header': source.has_header,
            'skip_rows': source.skip_rows,
            'comment_char': source.comment_char,
        }

        profiles_dir = Path.home() / ".data_graph_studio" / "loading_profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        profile_path = profiles_dir / f"{name.strip().replace(' ', '_')}.json"

        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

        w.statusbar.showMessage(f"Loading profile saved: {name}", 3000)

    def _load_loading_profile(self):
        """저장된 파싱 프로필 로드"""
        from PySide6.QtWidgets import QInputDialog
        w = self._w

        profiles_dir = Path.home() / ".data_graph_studio" / "loading_profiles"
        if not profiles_dir.exists():
            w.statusbar.showMessage("No saved loading profiles", 3000)
            return

        profile_files = list(profiles_dir.glob("*.json"))
        if not profile_files:
            w.statusbar.showMessage("No saved loading profiles", 3000)
            return

        names = [p.stem.replace('_', ' ') for p in profile_files]
        name, ok = QInputDialog.getItem(
            w, "Load Profile", "Select loading profile:", names, 0, False
        )
        if not ok:
            return

        idx = names.index(name)
        with open(profile_files[idx], 'r', encoding='utf-8') as f:
            profile = json.load(f)

        w.statusbar.showMessage(f"Loading profile loaded: {profile.get('name', name)}", 3000)
        return profile

    # ==================== Data Save ====================

    def _on_save_data(self):
        """Save Data - 현재 데이터 저장"""
        w = self._w
        if not w.state.is_data_loaded:
            QMessageBox.information(w, "Save Data", "No data loaded.")
            return

        current_path = getattr(w.engine, '_current_file_path', None)
        if current_path:
            try:
                ext = Path(current_path).suffix.lower()
                if ext == '.parquet':
                    w.engine.df.write_parquet(current_path)
                elif ext in ('.xlsx', '.xls'):
                    w.engine.df.write_excel(current_path)
                elif ext == '.json':
                    w.engine.df.write_json(current_path)
                else:
                    w.engine.df.write_csv(current_path)
                w.statusbar.showMessage(f"Data saved to {current_path}", 3000)
            except Exception as e:
                logger.exception("file_loading_controller.save_data.error")
                QMessageBox.warning(w, "Save Data", f"Failed to save: {e}")
        else:
            self._on_save_data_as()

    def _on_save_data_as(self):
        """Save Data As - 다른 이름으로 데이터 저장"""
        w = self._w
        if not w.state.is_data_loaded:
            QMessageBox.information(w, "Save Data As", "No data loaded.")
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            w, "Save Data As", "data",
            "CSV Files (*.csv);;Excel Files (*.xlsx);;Parquet Files (*.parquet);;All Files (*.*)"
        )
        if file_path:
            try:
                if file_path.endswith('.xlsx'):
                    w.engine.df.write_excel(file_path)
                elif file_path.endswith('.parquet'):
                    w.engine.df.write_parquet(file_path)
                else:
                    w.engine.df.write_csv(file_path)
                w.engine._current_file_path = file_path
                w.statusbar.showMessage(f"Data saved to {file_path}", 3000)
            except Exception as e:
                logger.exception("file_loading_controller.save_data_as.error")
                QMessageBox.warning(w, "Save Data As", f"Failed to save: {e}")

    def _on_import_data(self):
        """Import - 데이터 임포트"""
        from PySide6.QtWidgets import QInputDialog
        w = self._w
        sources = ["From File...", "From Clipboard", "From URL...", "From Database (Coming Soon)"]
        source, ok = QInputDialog.getItem(
            w, "Import Data", "Select import source:",
            sources, 0, False
        )
        if ok:
            if source == "From File...":
                self._on_open_file()
            elif source == "From Clipboard":
                self._on_import_from_clipboard()
            elif source == "From URL...":
                self._import_from_url()
            elif source == "From Database (Coming Soon)":
                pass  # disabled
