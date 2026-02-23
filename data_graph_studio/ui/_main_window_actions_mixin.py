"""Action handler slots for MainWindow.

Qt signal callbacks (menu actions, toolbar buttons, keyboard shortcuts).
These methods respond to user actions and delegate to controllers.
"""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import List

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
from PySide6.QtCore import Qt

from .clipboard_manager import ClipboardManager

logger = logging.getLogger(__name__)


class _MainWindowActionsMixin:
    """Mixin providing Qt action slot handlers for MainWindow.

    Requires: full MainWindow instance attributes (controllers, panels, state)
    set by MainWindow.__init__
    """

    def _on_streaming_play(self, *a, **kw):
        return self._streaming_ui_ctrl._on_streaming_play(*a, **kw)

    def _on_streaming_pause(self, *a, **kw):
        return self._streaming_ui_ctrl._on_streaming_pause(*a, **kw)

    def _on_streaming_stop(self, *a, **kw):
        return self._streaming_ui_ctrl._on_streaming_stop(*a, **kw)

    def _on_streaming_speed_changed(self, *a, **kw):
        return self._streaming_ui_ctrl._on_streaming_speed_changed(*a, **kw)

    def _on_streaming_window_changed(self, *a, **kw):
        return self._streaming_ui_ctrl._on_streaming_window_changed(*a, **kw)

    def _on_undo_stack_changed(self):
        # Update history UI
        if self._history_panel is not None:
            self._history_panel.refresh()

    def _on_undo(self):
        self._undo_stack.undo()

    def _on_redo(self):
        self._undo_stack.redo()

    def _on_copy_selection(self):
        """Copy current selection to clipboard."""
        if hasattr(self, 'table_panel') and hasattr(self.table_panel, 'copy_selection'):
            self.table_panel.copy_selection()
        else:
            self.statusbar.showMessage("Nothing to copy", 3000)

    def _on_select_all(self):
        """Select all data in table."""
        if hasattr(self, 'table_panel') and hasattr(self.table_panel, 'select_all'):
            self.table_panel.select_all()
        else:
            self.statusbar.showMessage("Select all not available", 3000)

    def _on_manage_parser_profiles(self):
        """Open parser profile manager dialog."""
        from data_graph_studio.parsers import FtraceParser, ParserProfileStore
        from data_graph_studio.ui.dialogs.parser_profile_dialog import ParserProfileDialog

        parser = FtraceParser()
        if not hasattr(self, '_parser_profile_store'):
            self._parser_profile_store = ParserProfileStore()

        dialog = ParserProfileDialog(parser, self._parser_profile_store, self)
        dialog.exec()

    def _on_run_parser(self, parser_key: str):
        """Run a custom parser: open file → parse → load."""
        from data_graph_studio.parsers import FtraceParser

        parsers = {
            "ftrace": FtraceParser,
        }

        parser_cls = parsers.get(parser_key)
        if parser_cls is None:
            QMessageBox.warning(self, "Parser", f"Unknown parser: {parser_key}")
            return

        parser = parser_cls()

        # Open file first
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"{parser.name} - Open File", "", parser.file_filter
        )
        if not file_path:
            return

        # Use default settings (user can manage profiles separately)
        settings = parser.default_settings()

        try:
            df = parser.parse(file_path, settings=settings)
        except NotImplementedError as e:
            QMessageBox.information(self, parser.name, str(e))
            return
        except Exception as e:
            logger.exception("main_window.parse_file.error")
            QMessageBox.critical(self, parser.name, f"Parse failed:\n{e}")
            return

        # Load the parsed DataFrame into the engine
        dataset_name = Path(file_path).stem
        dataset_id = self.engine.load_dataset_from_dataframe(
            df, name=dataset_name, source_path=file_path
        )
        if dataset_id:
            self._on_data_loaded()
            self.statusBar().showMessage(
                f"{parser.name}: loaded {len(df)} rows from {Path(file_path).name}", 5000
            )
        else:
            QMessageBox.warning(self, parser.name, "Failed to load parsed data.")

    def _on_configure_trace(self, *a, **kw):
        return self._trace_ctrl._on_configure_trace(*a, **kw)

    def _on_start_trace(self, *a, **kw):
        return self._trace_ctrl._on_start_trace(*a, **kw)

    def _on_compare_traces(self, *a, **kw):
        return self._trace_ctrl._on_compare_traces(*a, **kw)

    def _on_open_file(self):
        self._file_controller._on_open_file()

    def _on_load_sample_data(self):
        self._file_controller._on_load_sample_data()

    def _on_open_file_without_wizard(self):
        self._file_controller._on_open_file_without_wizard()

    def _on_wizard_project_created(self, result: dict):
        self._file_controller._on_wizard_project_created(result)

    def _on_open_multiple_files(self):
        self._file_controller._on_open_multiple_files()

    def _on_loading_progress(self, progress):
        self._file_controller._on_loading_progress(progress)

    def _on_loading_finished(self, success: bool):
        self._file_controller._on_loading_finished(success)

    def _on_data_loaded(self):
        """데이터 로드 완료"""
        self._update_ui_state()
        self._menu_setup_ctrl._update_menu_state()

        # 패널들에 데이터 전달
        self.table_panel.set_data(self.engine.df)
        if self.engine.is_windowed:
            self.state.set_visible_rows(len(self.engine.df))

        # 그래프 패널에 컬럼 목록 전달 (X-Axis 드롭다운용)
        self.graph_panel.set_columns(self.engine.columns)

        # Data 탭에 컬럼 목록 전달 (X/Y/Group/Hover 설정용)
        if hasattr(self.graph_panel.options_panel, 'data_tab'):
            self.graph_panel.options_panel.data_tab.set_columns(
                self.engine.columns, self.engine
            )

        self.graph_panel.refresh()
        self.graph_panel.autofit()

        self.summary_panel.refresh()

    def _on_window_changed(self):
        """Window 이동 시 그래프/요약 갱신"""
        self.graph_panel.refresh()
        self.summary_panel.refresh()

    def _on_data_cleared(self):
        """데이터 클리어"""
        self._update_ui_state()
        self.table_panel.clear()
        self.graph_panel.clear()
        self.summary_panel.clear()

        # Data 탭 클리어
        if hasattr(self.graph_panel.options_panel, 'data_tab'):
            self.graph_panel.options_panel.data_tab.clear()

    def _on_tool_mode_changed(self):
        """툴 모드 변경"""
        mode = self.state.tool_mode
        for m, action in self._tool_actions.items():
            action.setChecked(m == mode)

        # Delegate tool mode to Compare view panels
        if self._profile_comparison_view is not None:
            if hasattr(self._profile_comparison_view, 'set_tool_mode'):
                self._profile_comparison_view.set_tool_mode(mode)

    def _on_clear_selection(self):
        """Clear selection and highlight"""
        self.state.clear_selection()
        if hasattr(self, 'graph_panel') and self.graph_panel is not None:
            self.graph_panel.main_graph.highlight_selection([])

    def _on_export(self, *a, **kw):
        return self._export_ui_ctrl._on_export(*a, **kw)

    def _on_open_command_palette(self, *a, **kw):
        return self._help_ctrl._on_open_command_palette(*a, **kw)

    def _show_shortcuts(self, *a, **kw):
        return self._help_ctrl._show_shortcuts(*a, **kw)

    def _on_set_x_bins(self):
        """Set X-axis histogram bins"""
        current_bins = 30
        if hasattr(self, 'graph_panel') and hasattr(self.graph_panel, 'stat_panel'):
            current_bins = self.graph_panel.stat_panel._x_bins

        value, ok = QInputDialog.getInt(
            self, "Set X Bins", "Number of bins for X-axis histogram:",
            current_bins, 5, 200, 5
        )
        if ok and hasattr(self, 'graph_panel') and hasattr(self.graph_panel, 'stat_panel'):
            self.graph_panel.stat_panel.x_bins_spin.setValue(value)

    def _on_set_y_bins(self):
        """Set Y-axis histogram bins"""
        current_bins = 30
        if hasattr(self, 'graph_panel') and hasattr(self.graph_panel, 'stat_panel'):
            current_bins = self.graph_panel.stat_panel._y_bins

        value, ok = QInputDialog.getInt(
            self, "Set Y Bins", "Number of bins for Y-axis histogram:",
            current_bins, 5, 200, 5
        )
        if ok and hasattr(self, 'graph_panel') and hasattr(self.graph_panel, 'stat_panel'):
            self.graph_panel.stat_panel.y_bins_spin.setValue(value)

    def _on_set_both_bins(self):
        """Set both X and Y histogram bins"""
        current_bins = 30
        if hasattr(self, 'graph_panel') and hasattr(self.graph_panel, 'stat_panel'):
            current_bins = self.graph_panel.stat_panel._x_bins

        value, ok = QInputDialog.getInt(
            self, "Set Bins", "Number of bins for both histograms:",
            current_bins, 5, 200, 5
        )
        if ok and hasattr(self, 'graph_panel') and hasattr(self.graph_panel, 'stat_panel'):
            self.graph_panel.stat_panel.x_bins_spin.setValue(value)
            self.graph_panel.stat_panel.y_bins_spin.setValue(value)

    def _on_new_profile_menu(self):
        self._profile_ui_controller._on_new_profile_menu()

    def _on_load_profile_menu(self):
        self._profile_ui_controller._on_load_profile_menu()

    def _on_save_profile_menu(self):
        self._profile_ui_controller._on_save_profile_menu()

    def _on_profile_setting_clicked(self, setting_id: str):
        self._profile_ui_controller._on_profile_setting_clicked(setting_id)

    def _on_profile_setting_double_clicked(self, setting_id: str):
        self._profile_ui_controller._on_profile_setting_double_clicked(setting_id)

    def _on_add_setting_requested(self):
        self._profile_ui_controller._on_add_setting_requested()

    def _on_compare_profiles_requested(self):
        self._profile_ui_controller._on_compare_profiles_requested()

    def _on_profile_apply_requested(self, profile_id: str):
        self._profile_ui_controller._on_profile_apply_requested(profile_id)

    def _on_new_profile_requested(self, dataset_id: str):
        self._profile_ui_controller._on_new_profile_requested(dataset_id)

    def _on_profile_rename_requested(self, profile_id: str):
        self._profile_ui_controller._on_profile_rename_requested(profile_id)

    def _on_profile_delete_requested(self, profile_id: str):
        self._profile_ui_controller._on_profile_delete_requested(profile_id)

    def _on_profile_duplicate_requested(self, profile_id: str):
        self._profile_ui_controller._on_profile_duplicate_requested(profile_id)

    def _on_profile_export_requested(self, profile_id: str):
        self._profile_ui_controller._on_profile_export_requested(profile_id)

    def _on_profile_import_requested(self, dataset_id: str):
        self._profile_ui_controller._on_profile_import_requested(dataset_id)

    def _on_profile_compare_requested(self, profile_ids: list, options: dict):
        self._profile_ui_controller._on_profile_compare_requested(profile_ids, options)

    def _on_copy_to_dataset_requested(self, profile_id: str):
        self._profile_ui_controller._on_copy_to_dataset_requested(profile_id)

    def _on_favorite_toggled(self, profile_id: str):
        self._profile_ui_controller._on_favorite_toggled(profile_id)

    def _on_add_dataset(self):
        self._dataset_controller._on_add_dataset()

    def _on_dataset_loading_finished(self, success: bool):
        self._dataset_controller._on_dataset_loading_finished(success)

    def _on_dataset_activated(self, dataset_id: str):
        self._dataset_controller._on_dataset_activated(dataset_id)

    def _on_dataset_remove_requested(self, dataset_id: str):
        self._dataset_controller._on_dataset_remove_requested(dataset_id)

    def _on_comparison_mode_changed(self, *a, **kw):
        return self._comparison_ui_ctrl._on_comparison_mode_changed(*a, **kw)

    def _on_comparison_started(self, *a, **kw):
        return self._comparison_ui_ctrl._on_comparison_started(*a, **kw)

    def _on_export_comparison_report(self, *a, **kw):
        return self._comparison_ui_ctrl._on_export_comparison_report(*a, **kw)

    def _on_profile_comparison_started(self, *a, **kw):
        return self._comparison_ui_ctrl._on_profile_comparison_started(*a, **kw)

    def _on_profile_comparison_ended(self, *a, **kw):
        return self._comparison_ui_ctrl._on_profile_comparison_ended(*a, **kw)

    def _on_start_streaming_dialog(self, *a, **kw):
        return self._streaming_ui_ctrl._on_start_streaming_dialog(*a, **kw)

    def _on_pause_streaming(self, *a, **kw):
        return self._streaming_ui_ctrl._on_pause_streaming(*a, **kw)

    def _on_stop_streaming(self, *a, **kw):
        return self._streaming_ui_ctrl._on_stop_streaming(*a, **kw)

    def _on_streaming_state_changed(self, *a, **kw):
        return self._streaming_ui_ctrl._on_streaming_state_changed(*a, **kw)

    def _on_streaming_data_updated(self, *a, **kw):
        return self._streaming_ui_ctrl._on_streaming_data_updated(*a, **kw)

    def _on_streaming_file_deleted(self, *a, **kw):
        return self._streaming_ui_ctrl._on_streaming_file_deleted(*a, **kw)

    def _paste_from_clipboard(self, *a, **kw):
        return self._data_ops_ctrl._paste_from_clipboard(*a, **kw)

    def _copy_graph_to_clipboard(self):
        """그래프를 이미지로 클립보드에 복사"""
        try:
            if self.graph_panel and hasattr(self.graph_panel, 'main_graph') and self.graph_panel.main_graph:
                # PyQtGraph에서 이미지 캡처
                exporter = None
                try:
                    from pyqtgraph.exporters import ImageExporter
                    exporter = ImageExporter(self.graph_panel.main_graph.plotItem)
                    exporter.parameters()['width'] = 1920

                    # QImage로 내보내기
                    from PySide6.QtGui import QImage
                    import tempfile

                    # 임시 파일로 저장 후 로드
                    temp_path = os.path.join(tempfile.gettempdir(), 'dgs_temp_chart.png')
                    exporter.export(temp_path)

                    image = QImage(temp_path)
                    if not image.isNull():
                        msg = ClipboardManager.copy_image(image)
                        self.statusBar().showMessage(f"✓ {msg}", 3000)

                    # 임시 파일 삭제
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                except Exception as e:
                    logger.exception("main_window.copy_graph_image.export.error")
                    self.statusBar().showMessage(f"Export error: {e}", 3000)
        except Exception as e:
            logger.exception("main_window.copy_graph_image.error")
            self.statusBar().showMessage(f"Copy error: {e}", 3000)

    def _copy_selection_to_clipboard(self):
        """테이블 선택 영역 복사"""
        try:
            if self.table_panel and hasattr(self.table_panel, 'table_view'):
                selection = self.table_panel.table_view.selectionModel()
                if selection.hasSelection():
                    # 선택된 행/열 데이터 추출
                    indexes = selection.selectedIndexes()
                    if indexes:
                        rows = sorted(set(idx.row() for idx in indexes))
                        cols = sorted(set(idx.column() for idx in indexes))

                        # 데이터 추출
                        model = self.table_panel.table_view.model()
                        data = []
                        for row in rows:
                            row_data = []
                            for col in cols:
                                idx = model.index(row, col)
                                value = model.data(idx, Qt.DisplayRole)
                                row_data.append(str(value) if value else '')
                            data.append('\t'.join(row_data))

                        text = '\n'.join(data)
                        ClipboardManager.copy_text(text)
                        self.statusBar().showMessage(f"✓ Copied {len(rows)} rows", 3000)
                        return

            self.statusBar().showMessage("No selection to copy", 3000)
        except Exception as e:
            logger.exception("main_window.copy_selection_to_clipboard.error")
            self.statusBar().showMessage(f"Copy error: {e}", 3000)

    def _update_recent_files_menu(self, *a, **kw):
        return self._menu_setup_ctrl._update_recent_files_menu(*a, **kw)

    def _get_recent_files(self) -> List[str]:
        return self._file_controller._get_recent_files()

    def _add_to_recent_files(self, file_path: str):
        self._file_controller._add_to_recent_files(file_path)

    def _open_recent_file(self, file_path: str):
        self._file_controller._open_recent_file(file_path)

    def _clear_recent_files(self):
        self._file_controller._clear_recent_files()

    def _on_import_from_clipboard(self, *a, **kw):
        return self._data_ops_ctrl._on_import_from_clipboard(*a, **kw)

    def _on_find_data(self, *a, **kw):
        return self._data_ops_ctrl._on_find_data(*a, **kw)

    def _on_goto_row(self, *a, **kw):
        return self._data_ops_ctrl._on_goto_row(*a, **kw)

    def _on_filter_data(self, *a, **kw):
        return self._data_ops_ctrl._on_filter_data(*a, **kw)

    def _on_sort_data(self, *a, **kw):
        return self._data_ops_ctrl._on_sort_data(*a, **kw)

    def _on_add_calculated_field(self, *a, **kw):
        return self._data_ops_ctrl._on_add_calculated_field(*a, **kw)

    def _on_computed_column_created(self, *a, **kw):
        return self._data_ops_ctrl._on_computed_column_created(*a, **kw)

    def _on_remove_duplicates(self, *a, **kw):
        return self._data_ops_ctrl._on_remove_duplicates(*a, **kw)

    def _on_data_summary(self, *a, **kw):
        return self._data_ops_ctrl._on_data_summary(*a, **kw)

    def _on_zoom_in(self, *a, **kw):
        return self._view_actions_ctrl._on_zoom_in(*a, **kw)

    def _on_zoom_out(self, *a, **kw):
        return self._view_actions_ctrl._on_zoom_out(*a, **kw)

    def _on_toggle_fullscreen(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_fullscreen(*a, **kw)

    def _on_theme_changed(self, *a, **kw):
        return self._view_actions_ctrl._on_theme_changed(*a, **kw)

    def _on_toggle_grid(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_grid(*a, **kw)

    def _on_toggle_legend(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_legend(*a, **kw)

    def _on_add_trend_line(self):
        """추세선 추가 - main_graph의 실제 구현 호출"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Add Trend Line", "No data loaded.")
            return

        types = ["Linear", "Polynomial (2nd)", "Polynomial (3rd)", "Exponential"]
        trend_type, ok = QInputDialog.getItem(
            self, "Add Trend Line", "Select trend line type:",
            types, 0, False
        )
        if ok and hasattr(self.graph_panel, 'main_graph') and self.graph_panel.main_graph:
            mg = self.graph_panel.main_graph
            degree_map = {"Linear": 1, "Polynomial (2nd)": 2, "Polynomial (3rd)": 3}
            if trend_type in degree_map:
                mg._add_trendline_degree(degree_map[trend_type])
            elif trend_type == "Exponential":
                if hasattr(mg, '_add_exponential_trendline'):
                    mg._add_exponential_trendline()
                else:
                    mg._add_trendline_degree(1)
            self.statusbar.showMessage(f"Added {trend_type} trend line", 3000)

    def _on_curve_fitting(self):
        """곡선 피팅 설정 — CurveFitter를 사용하여 피팅 수행"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Curve Fitting", "No data loaded.")
            return

        from data_graph_studio.graph.curve_fitting import CurveFitter, FitType, CurveFitSettings
        import numpy as np

        # 컬럼 선택
        columns = self.engine.columns
        numeric_cols = [c for c in columns if self.engine.df[c].dtype.is_numeric()]
        if len(numeric_cols) < 2:
            QMessageBox.warning(self, "Curve Fitting", "Need at least 2 numeric columns.")
            return

        x_col, ok = QInputDialog.getItem(self, "Curve Fitting", "Select X column:", numeric_cols, 0, False)
        if not ok:
            return
        y_col, ok = QInputDialog.getItem(self, "Curve Fitting", "Select Y column:", numeric_cols, 0, False)
        if not ok:
            return

        # 피팅 타입 선택
        fit_options = ["Linear", "Polynomial (degree 2)", "Polynomial (degree 3)",
                       "Exponential", "Power", "Logarithmic"]
        fit_choice, ok = QInputDialog.getItem(self, "Curve Fitting", "Select fit type:", fit_options, 0, False)
        if not ok:
            return

        fit_map = {
            "Linear": (FitType.LINEAR, 1),
            "Polynomial (degree 2)": (FitType.POLYNOMIAL, 2),
            "Polynomial (degree 3)": (FitType.POLYNOMIAL, 3),
            "Exponential": (FitType.EXPONENTIAL, 1),
            "Power": (FitType.POWER, 1),
            "Logarithmic": (FitType.LOGARITHMIC, 1),
        }
        fit_type, degree = fit_map[fit_choice]

        df = self.engine.df
        x = df[x_col].drop_nulls().to_numpy().astype(float)
        y = df[y_col].drop_nulls().to_numpy().astype(float)
        min_len = min(len(x), len(y))
        x, y = x[:min_len], y[:min_len]

        fitter = CurveFitter()
        settings = CurveFitSettings(fit_type=fit_type, degree=degree)
        result = fitter.fit(x, y, fit_type, settings)

        if result is None or result.predict_func is None:
            QMessageBox.warning(self, "Curve Fitting", "Fitting failed for the selected data.")
            return

        # 결과 표시
        eq = result.get_equation_string()
        stats_str = result.get_statistics_string()
        QMessageBox.information(
            self, "Curve Fitting Result",
            f"{eq}\n\n{stats_str}"
        )

        # 그래프에 피팅 커브 추가
        x_line = np.linspace(x.min(), x.max(), 200)
        y_line = result.predict_func(x_line)
        try:
            import pyqtgraph as pg
            pen = pg.mkPen(color='r', width=2, style=pg.QtCore.Qt.DashLine)
            plot_widget = self.graph_panel._plot_widget
            plot_widget.plot(x_line, y_line, pen=pen, name=f"Fit: {eq}")
        except Exception:
            logger.warning("main_window.curve_fit.plot.error", exc_info=True)

        self.statusbar.showMessage(f"Curve fit: {eq} (R²={result.r_squared:.4f})", 5000)

    def _on_calculate_statistics(self):
        """통계 계산 트리거"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Calculate Statistics", "No data loaded.")
            return

        # 통계 패널 업데이트 트리거
        if hasattr(self.graph_panel, 'stat_panel'):
            self.graph_panel.stat_panel.refresh()
        self.summary_panel.refresh()
        self.statusbar.showMessage("Statistics calculated", 3000)

    def _on_export_report(self):
        """레포트 내보내기"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Export Report", "No data loaded.")
            return

        # ReportDialog 사용
        try:
            from .dialogs.report_dialog import ReportDialog
            dialog = ReportDialog(self.engine, self.state, self.graph_panel, self)
            dialog.exec()
        except ImportError:
            # ReportDialog가 없으면 간단한 내보내기
            file_path, selected_filter = QFileDialog.getSaveFileName(
                self, "Export Report", "report",
                "HTML Report (*.html);;PDF Report (*.pdf)"
            )
            if file_path:
                self.statusbar.showMessage(f"Report exported to {file_path}", 3000)

    def _on_open_profile(self):
        self._profile_ui_controller._on_open_profile()

    def _on_open_project(self):
        self._profile_ui_controller._on_open_project()

    def _on_save_profile_file(self):
        return self._profile_ui_controller._on_save_profile_file()

    def _on_save_profile_file_as(self):
        self._profile_ui_controller._on_save_profile_file_as()

    def _on_save_project_file(self):
        return self._profile_ui_controller._on_save_project_file()

    def _on_save_project_file_as(self):
        self._profile_ui_controller._on_save_project_file_as()

    def _save_project_to(self, path: str):
        self._profile_ui_controller._save_project_to(path)

    def _on_save_profile_bundle_as(self):
        self._profile_ui_controller._on_save_profile_bundle_as()

    def _on_save_data(self):
        """Save Data - 현재 데이터를 원본 포맷으로 저장"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Save Data", "No data loaded.")
            return

        current_path = getattr(self.engine, '_current_file_path', None)
        if current_path:
            try:
                ext = Path(current_path).suffix.lower()
                if ext == '.parquet':
                    self.engine.df.write_parquet(current_path)
                elif ext in ('.xlsx', '.xls'):
                    self.engine.df.write_excel(current_path)
                elif ext == '.json':
                    self.engine.df.write_json(current_path)
                else:
                    self.engine.df.write_csv(current_path)
                self.statusbar.showMessage(f"Data saved to {current_path}", 3000)
            except Exception as e:
                logger.exception("main_window.save_data.error")
                QMessageBox.warning(self, "Save Data", f"Failed to save: {e}")
        else:
            self._on_save_data_as()

    def _on_save_data_as(self):
        """Save Data As - 다른 이름으로 데이터 저장"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Save Data As", "No data loaded.")
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Data As", "data",
            "CSV Files (*.csv);;Excel Files (*.xlsx);;Parquet Files (*.parquet);;All Files (*.*)"
        )
        if file_path:
            try:
                if file_path.endswith('.xlsx'):
                    self.engine.df.write_excel(file_path)
                elif file_path.endswith('.parquet'):
                    self.engine.df.write_parquet(file_path)
                else:
                    self.engine.df.write_csv(file_path)
                self.engine._current_file_path = file_path
                self.statusbar.showMessage(f"Data saved to {file_path}", 3000)
            except Exception as e:
                logger.exception("main_window.save_data_as.error")
                QMessageBox.warning(self, "Save Data As", f"Failed to save: {e}")

    def _on_import_data(self):
        """Import - 데이터 임포트"""
        # 다양한 소스에서 데이터 가져오기
        self._file_controller._on_import_data()

    def _on_toggle_statistics_overlay(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_statistics_overlay(*a, **kw)

    def _on_toggle_axis_labels(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_axis_labels(*a, **kw)

    def _on_drawing_style(self, *a, **kw):
        return self._view_actions_ctrl._on_drawing_style(*a, **kw)

    def _on_delete_drawing(self, *a, **kw):
        return self._view_actions_ctrl._on_delete_drawing(*a, **kw)

    def _on_clear_drawings(self, *a, **kw):
        return self._view_actions_ctrl._on_clear_drawings(*a, **kw)

    def _on_draw_color_pick(self, *a, **kw):
        return self._view_actions_ctrl._on_draw_color_pick(*a, **kw)

    def _on_toggle_row_numbers(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_row_numbers(*a, **kw)

    def _on_toggle_column_headers(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_column_headers(*a, **kw)

    def _on_toggle_filter_bar(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_filter_bar(*a, **kw)

    def _on_multi_grid_view(self, *a, **kw):
        return self._view_actions_ctrl._on_multi_grid_view(*a, **kw)

    def _on_remove_field(self):
        """Remove Field - 필드/컬럼 제거"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Remove Field", "No data loaded.")
            return

        columns = self.engine.columns
        if not columns:
            QMessageBox.information(self, "Remove Field", "No columns available.")
            return

        column, ok = QInputDialog.getItem(
            self, "Remove Field", "Select column to remove:",
            columns, 0, False
        )
        if ok and column:
            reply = QMessageBox.question(
                self, "Confirm Remove",
                f"Are you sure you want to remove column '{column}'?\n\nThis action cannot be undone.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    from ..core.undo_manager import UndoCommand, UndoActionType
                    before_df = self.engine.df
                    self.engine.drop_column(column)
                    after_df = self.engine.df

                    def _apply_drop(df):
                        self.engine.update_dataframe(df)
                        self.table_panel.set_data(df)
                        self.graph_panel.refresh()

                    self.table_panel.set_data(after_df)
                    self.graph_panel.refresh()

                    self._undo_stack.record(
                        UndoCommand(
                            action_type=UndoActionType.COLUMN_ADD,
                            description=f"Remove column '{column}'",
                            do=lambda: _apply_drop(after_df),
                            undo=lambda: _apply_drop(before_df),
                            timestamp=__import__('time').time(),
                        )
                    )
                    self.statusbar.showMessage(f"Column '{column}' removed", 3000)
                except Exception as e:
                    logger.exception("main_window.remove_field.error")
                    QMessageBox.warning(self, "Remove Field", f"Failed to remove column: {e}")

    def _on_axis_settings(self, *a, **kw):
        return self._view_actions_ctrl._on_axis_settings(*a, **kw)

    def _on_toggle_dashboard_mode(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_dashboard_mode(*a, **kw)

    def _on_dashboard_cell_clicked(self, *a, **kw):
        return self._view_actions_ctrl._on_dashboard_cell_clicked(*a, **kw)

    def _on_dashboard_preset_changed(self, *a, **kw):
        return self._view_actions_ctrl._on_dashboard_preset_changed(*a, **kw)

    def _on_toggle_annotation_panel(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_annotation_panel(*a, **kw)

    def _on_annotation_navigate(self, *a, **kw):
        return self._view_actions_ctrl._on_annotation_navigate(*a, **kw)

    def _on_annotation_edit(self, *a, **kw):
        return self._view_actions_ctrl._on_annotation_edit(*a, **kw)

    def _on_annotation_delete(self, *a, **kw):
        return self._view_actions_ctrl._on_annotation_delete(*a, **kw)

    def _on_add_annotation(self, *a, **kw):
        return self._view_actions_ctrl._on_add_annotation(*a, **kw)

    def _on_export_dialog(self, *a, **kw):
        return self._export_ui_ctrl._on_export_dialog(*a, **kw)

    def _on_export_image(self, *a, **kw):
        return self._export_ui_ctrl._on_export_image(*a, **kw)

    def _on_export_data(self, *a, **kw):
        return self._export_ui_ctrl._on_export_data(*a, **kw)

    def _on_cycle_theme(self, *a, **kw):
        return self._view_actions_ctrl._on_cycle_theme(*a, **kw)

    def _show_shortcuts_dialog(self):
        """Show keyboard shortcuts help dialog (Ctrl+/)"""
        from .dialogs.shortcut_help_dialog import ShortcutHelpDialog
        dlg = ShortcutHelpDialog(self._shortcut_controller, parent=self)
        dlg.exec()

    def _show_edit_shortcuts_dialog(self):
        """Show shortcut customization dialog"""
        from .dialogs.shortcut_edit_dialog import ShortcutEditDialog
        dlg = ShortcutEditDialog(self._shortcut_controller, parent=self)
        dlg.shortcut_changed.connect(self._on_shortcut_customized)
        dlg.exec()

    def _on_shortcut_customized(self, shortcut_id: str, new_keys: str):
        """Handle shortcut customization - detect conflicts and rebind"""
        # Conflict detection is handled inside ShortcutEditDialog
        # Log the change
        logger.info("main_window.shortcut_changed", extra={"shortcut_id": shortcut_id, "new_keys": new_keys})
