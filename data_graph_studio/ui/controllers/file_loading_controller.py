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
from PySide6.QtCore import Qt, QThread, Signal, QTimer

from ...core.data_engine import DataEngine, LoadingProgress
from ...core.clipboard_manager import ClipboardManager
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
        """파싱 미리보기 다이얼로그 표시"""
        if not self._check_large_file_warning(file_path):
            return

        ext = Path(file_path).suffix.lower()

        if ext in ['.parquet', '.xlsx', '.xls', '.json']:
            self._load_file(file_path)
            return

        from ..dialogs.parsing_preview_dialog import ParsingPreviewDialog
        dialog = ParsingPreviewDialog(file_path, self._w)
        if dialog.exec() == QDialog.Accepted:
            settings = dialog.get_settings()
            self._load_file_with_settings(file_path, settings)

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

        w._progress_dialog = QProgressDialog(
            f"Loading {Path(file_path).name}...",
            "Cancel",
            0, 100,
            w
        )
        w._progress_dialog.setWindowModality(Qt.WindowModal)
        w._progress_dialog.setAutoClose(True)
        w._progress_dialog.setMinimumWidth(400)
        w._progress_dialog.canceled.connect(self._cancel_loading)

        w._loader_thread = DataLoaderThread(w.engine, file_path)
        w._loader_thread.progress_updated.connect(self._on_loading_progress)
        w._loader_thread.finished_loading.connect(self._on_loading_finished)
        w._loader_thread.start()

        w._progress_dialog.show()

    def _load_file_with_settings(self, file_path: str, settings: ParsingSettings):
        """파일 로드 (파싱 설정 적용)"""
        w = self._w
        self._cleanup_loader_thread()

        w._progress_dialog = QProgressDialog(
            f"Loading {Path(file_path).name}...",
            "Cancel",
            0, 100,
            w
        )
        w._progress_dialog.setWindowModality(Qt.WindowModal)
        w._progress_dialog.setAutoClose(True)
        w._progress_dialog.setMinimumWidth(400)
        w._progress_dialog.canceled.connect(self._cancel_loading)

        w._loader_thread = DataLoaderThreadWithSettings(w.engine, file_path, settings)
        w._loader_thread.progress_updated.connect(self._on_loading_progress)
        w._loader_thread.finished_loading.connect(self._on_loading_finished)
        w._loader_thread.start()

        w._progress_dialog.show()

    def _on_loading_progress(self, progress: LoadingProgress):
        """로딩 진행률 업데이트"""
        w = self._w
        if w._progress_dialog:
            w._progress_dialog.setValue(int(progress.progress_percent))

            try:
                proc_mem = MemoryMonitor.get_process_memory()
                mem_str = MemoryMonitor.format_memory(proc_mem['rss_mb'])
            except Exception:
                mem_str = "--"

            eta_str = ""
            if progress.eta_seconds > 0:
                eta_str = f"\nETA: {progress.eta_seconds:.0f}s"

            w._progress_dialog.setLabelText(
                f"Loading... {progress.status}\n"
                f"{progress.loaded_rows:,} rows loaded\n"
                f"Memory: {mem_str}{eta_str}"
            )

    def _on_loading_finished(self, success: bool):
        """로딩 완료"""
        w = self._w
        if w._progress_dialog:
            w._progress_dialog.close()

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
            logger.info(f"Data loaded: {w.engine.row_count:,} rows, {w.engine.column_count} columns")

            w._apply_pending_wizard_result()
        else:
            error_msg = w.engine.progress.error_message or "Unknown error"
            logger.error(f"Failed to load file: {error_msg}")
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
                    f"Some data files not found:\n" + "\n".join(errors)
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
                    logger.warning(f"Failed to restore profile: {e}")

            w._last_project_path = file_path
            w.statusbar.showMessage(f"Project loaded: {file_path} ({loaded_count} datasets, {len(project.profiles)} profiles)", 3000)

            if loaded_count > 0:
                w._on_data_loaded()

        except Exception as e:
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
                import uuid
                dataset_id = f"clipboard_{uuid.uuid4().hex[:8]}"

                w.engine._df = df

                w.state.set_data_loaded(True, len(df))
                w.state.set_column_order(df.columns)

                w.table_panel.set_data(df)
                w.graph_panel.set_columns(df.columns)

                if hasattr(w.graph_panel.options_panel, 'data_tab'):
                    w.graph_panel.options_panel.data_tab.set_columns(
                        df.columns, w.engine
                    )

                w.statusBar().showMessage(f"✓ {message}", 5000)

            except Exception as e:
                w.statusBar().showMessage(f"Paste error: {e}", 5000)
        else:
            w.statusBar().showMessage(message, 3000)

    # ==================== Recent Files ====================

    def _update_recent_files_menu(self):
        """최근 파일 메뉴 업데이트"""
        from PySide6.QtGui import QAction
        w = self._w
        w._recent_files_menu.clear()

        recent_files = self._get_recent_files()

        if not recent_files:
            no_files_action = QAction("(No recent files)", w)
            no_files_action.setEnabled(False)
            w._recent_files_menu.addAction(no_files_action)
        else:
            for file_path in recent_files[:10]:
                action = QAction(Path(file_path).name, w)
                action.setToolTip(file_path)
                action.setStatusTip(file_path)
                action.triggered.connect(lambda checked, fp=file_path: self._open_recent_file(fp))
                w._recent_files_menu.addAction(action)

            w._recent_files_menu.addSeparator()
            clear_action = QAction("Clear Recent Files", w)
            clear_action.triggered.connect(self._clear_recent_files)
            w._recent_files_menu.addAction(clear_action)

    def _get_recent_files(self) -> List[str]:
        """최근 파일 목록 가져오기"""
        try:
            recent_file_path = Path.home() / ".data_graph_studio" / "recent_files.json"
            if recent_file_path.exists():
                with open(recent_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [f for f in data.get('files', []) if Path(f).exists()]
        except Exception:
            pass
        return []

    def _add_to_recent_files(self, file_path: str):
        """최근 파일에 추가"""
        try:
            recent_dir = Path.home() / ".data_graph_studio"
            recent_dir.mkdir(parents=True, exist_ok=True)
            recent_file_path = recent_dir / "recent_files.json"

            recent_files = self._get_recent_files()
            if file_path in recent_files:
                recent_files.remove(file_path)
            recent_files.insert(0, file_path)
            recent_files = recent_files[:20]

            with open(recent_file_path, 'w', encoding='utf-8') as f:
                json.dump({'files': recent_files}, f, ensure_ascii=False, indent=2)

            self._update_recent_files_menu()
        except Exception as e:
            logger.debug(f"Failed to add to recent files: {e}")

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
            logger.debug(f"Failed to clear recent files: {e}")

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
                w.engine.df.write_csv(current_path)
                w.statusbar.showMessage(f"Data saved to {current_path}", 3000)
            except Exception as e:
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
                QMessageBox.warning(w, "Save Data As", f"Failed to save: {e}")

    def _on_import_data(self):
        """Import - 데이터 임포트"""
        from PySide6.QtWidgets import QInputDialog
        w = self._w
        sources = ["From File...", "From Clipboard", "From URL...", "From Database..."]
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
                url, url_ok = QInputDialog.getText(
                    w, "Import from URL", "Enter URL:"
                )
                if url_ok and url:
                    w.statusbar.showMessage(f"Importing from {url}...", 3000)
            elif source == "From Database...":
                QMessageBox.information(
                    w, "Import from Database",
                    "Database import will be implemented.\n\n"
                    "Supported: PostgreSQL, MySQL, SQLite, etc."
                )
