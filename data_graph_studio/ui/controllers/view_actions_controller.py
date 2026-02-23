"""ViewActionsController - extracted from MainWindow."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QApplication, QColorDialog, QInputDialog, QMessageBox
)
from PySide6.QtGui import QAction

from ..panels.annotation_panel import AnnotationPanel
from ..panels.dashboard_panel import DashboardPanel
from ..floatable import FloatWindow

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..main_window import MainWindow

class ViewActionsController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    def _float_main_panel(self, panel_key: str):
        """메인 패널을 독립 창으로 분리"""
        if panel_key in self.w._float_windows:
            self.w._float_windows[panel_key].raise_()
            self.w._float_windows[panel_key].activateWindow()
            return

        panel_map = {
            "summary": (self.w.summary_panel, "📊 Overview", 0),
            "graph": (self.w.graph_panel, "📈 Graph Panel", 1),
            "table": (self.w.table_panel, "📋 Table Panel", 2),
        }

        if panel_key not in panel_map:
            return

        widget, title, splitter_index = panel_map[panel_key]

        # Save current sizes before modification
        current_sizes = self.w.main_splitter.sizes()

        # Float window 생성
        float_window = FloatWindow(title, widget, self.w)
        float_window.dock_requested.connect(lambda: self.w._dock_main_panel(panel_key))
        self.w._float_windows[panel_key] = float_window

        # Find the actual current index of the widget in splitter
        actual_index = -1
        for i in range(self.w.main_splitter.count()):
            if self.w.main_splitter.widget(i) is widget:
                actual_index = i
                break

        if actual_index >= 0:
            # 플레이스홀더로 교체
            placeholder = self.w._placeholders[panel_key]
            self.w.main_splitter.replaceWidget(actual_index, placeholder)
            placeholder.show()

            # Restore sizes
            self.w.main_splitter.setSizes(current_sizes)

        # Float 버튼 비활성화
        if hasattr(widget, 'float_btn'):
            widget.float_btn.setEnabled(False)

        float_window.show()


    def _dock_main_panel(self, panel_key: str):
        """메인 패널을 메인 창으로 복귀"""
        if panel_key not in self.w._float_windows:
            return

        float_window = self.w._float_windows[panel_key]
        widget = float_window.get_content_widget()

        panel_map = {
            "summary": (self.w.summary_panel, 0),
            "graph": (self.w.graph_panel, 1),
            "table": (self.w.table_panel, 2),
        }

        expected_widget, target_index = panel_map.get(panel_key, (None, 0))
        placeholder = self.w._placeholders[panel_key]

        # Save current sizes before modification
        current_sizes = self.w.main_splitter.sizes()

        # Find the actual current index of the placeholder in splitter
        actual_index = -1
        for i in range(self.w.main_splitter.count()):
            if self.w.main_splitter.widget(i) is placeholder:
                actual_index = i
                break

        if actual_index >= 0:
            # 플레이스홀더를 원래 위젯으로 교체
            self.w.main_splitter.replaceWidget(actual_index, widget)
            placeholder.hide()
            widget.show()

            # Restore sizes
            self.w.main_splitter.setSizes(current_sizes)
        else:
            # Placeholder not found, need to insert at correct position
            # Remove widget from float window's layout first
            widget.setParent(None)

            # Insert at target index
            self.w.main_splitter.insertWidget(target_index, widget)
            widget.show()

        # Float 버튼 활성화
        if hasattr(widget, 'float_btn'):
            widget.float_btn.setEnabled(True)

        # Float window 정리
        float_window.close()
        float_window.deleteLater()
        del self.w._float_windows[panel_key]
    

    def _on_zoom_in(self):
        """줌 인"""
        if hasattr(self.w.graph_panel, 'zoom_in'):
            self.w.graph_panel.zoom_in()
        else:
            self.w.statusbar.showMessage("Zoom in", 2000)


    def _on_zoom_out(self):
        """줌 아웃"""
        if hasattr(self.w.graph_panel, 'zoom_out'):
            self.w.graph_panel.zoom_out()
        else:
            self.w.statusbar.showMessage("Zoom out", 2000)


    def _on_toggle_fullscreen(self):
        """전체 화면 토글"""
        if self.w.isFullScreen():
            self.w.showNormal()
            self.w._fullscreen_action.setChecked(False)
        else:
            self.w.showFullScreen()
            self.w._fullscreen_action.setChecked(True)


    def _on_theme_changed(self, theme_id: str):
        """테마 변경 + QSettings 저장"""
        from ..theme import ThemeManager
        
        # 테마 액션 상태 업데이트
        for tid, action in self.w._theme_actions.items():
            action.setChecked(tid == theme_id)
        
        # 테마 적용
        if not hasattr(self, '_theme_manager'):
            self.w._theme_manager = ThemeManager()
        
        self.w._theme_manager.set_theme(theme_id)
        self.w._current_theme = theme_id
        stylesheet = self.w._theme_manager.generate_stylesheet()
        QApplication.instance().setStyleSheet(stylesheet)
        
        # Apply theme to graph panel components
        is_light = self.w._theme_manager.current_theme.is_light()
        if hasattr(self, 'graph_panel'):
            # Main graph
            if hasattr(self.w.graph_panel, 'main_graph'):
                self.w.graph_panel.main_graph.apply_theme(is_light)
            # Stat panel mini-graphs
            if hasattr(self.w.graph_panel, 'stat_panel'):
                self.w.graph_panel.stat_panel.apply_theme(is_light)
            # Minimap
            if hasattr(self.w.graph_panel, 'minimap'):
                self.w.graph_panel.minimap.apply_theme(is_light)

        # Apply theme to compare widgets
        for attr in ('_overlay_stats_widget', '_comparison_stats_panel',
                     '_compare_toolbar', '_profile_overlay_renderer',
                     '_profile_difference_renderer'):
            widget = getattr(self.w, attr, None)
            if widget is not None and hasattr(widget, 'apply_theme'):
                widget.apply_theme(is_light)

        # Persist to QSettings (B-6)
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings("Godol", "DataGraphStudio")
            settings.setValue("appearance/theme", theme_id)
        except Exception:
            logger.warning("view_actions_controller.persist_theme.error", exc_info=True)

        self.w.statusbar.showMessage(f"Theme changed to {theme_id.title()}", 3000)


    def _on_toggle_grid(self, checked: bool = None):
        """그리드 표시 토글"""
        if hasattr(self.w.graph_panel, 'set_grid_visible'):
            self.w.graph_panel.set_grid_visible(checked)
        self.w.statusbar.showMessage(f"Grid {'shown' if checked else 'hidden'}", 2000)


    def _on_toggle_legend(self, checked: bool = None):
        """범례 표시 토글"""
        if hasattr(self.w.graph_panel, 'set_legend_visible'):
            self.w.graph_panel.set_legend_visible(checked)
        self.w.statusbar.showMessage(f"Legend {'shown' if checked else 'hidden'}", 2000)


    def _on_toggle_statistics_overlay(self, checked: bool = None):
        """통계 오버레이 표시 토글"""
        if checked is None:
            checked = self.w._graph_element_actions.get("statistics_overlay", QAction()).isChecked()
        
        if hasattr(self.w.graph_panel, 'set_statistics_overlay_visible'):
            self.w.graph_panel.set_statistics_overlay_visible(checked)
        self.w.statusbar.showMessage(f"Statistics overlay {'shown' if checked else 'hidden'}", 2000)


    def _on_toggle_axis_labels(self, checked: bool = None):
        """축 레이블 표시 토글"""
        if checked is None:
            checked = self.w._graph_element_actions.get("axis_labels", QAction()).isChecked()
        
        if hasattr(self.w.graph_panel, 'set_axis_labels_visible'):
            self.w.graph_panel.set_axis_labels_visible(checked)
        self.w.statusbar.showMessage(f"Axis labels {'shown' if checked else 'hidden'}", 2000)


    def _on_drawing_style(self):
        if hasattr(self, 'graph_panel') and self.w.graph_panel is not None:
            self.w.graph_panel.show_drawing_style_dialog()


    def _on_delete_drawing(self):
        if hasattr(self, 'graph_panel') and self.w.graph_panel is not None:
            self.w.graph_panel.delete_selected_drawing()


    def _on_clear_drawings(self):
        if hasattr(self, 'graph_panel') and self.w.graph_panel is not None:
            self.w.graph_panel.clear_drawings()


    def _on_draw_color_pick(self):
        """Open color picker for draw color"""
        color = QColorDialog.getColor(
            self.w._draw_color, self.w, "Draw Color"
        )
        if color.isValid():
            self.w._draw_color = color
            self.w._update_draw_color_btn()
            # Apply to graph panel's current drawing style
            if hasattr(self, 'graph_panel') and self.w.graph_panel is not None:
                self.w.graph_panel.set_drawing_color(color.name())


    def _update_draw_color_btn(self):
        """Update draw color button appearance"""
        self.w._draw_color_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.w._draw_color.name()};
                border: 2px solid #3E4A59;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: #59B8E3;
            }}
        """)

    # ============================================================
    # New Menu Action Methods (View Menu - Table Elements)
    # ============================================================


    def _on_toggle_row_numbers(self, checked: bool = None):
        """행 번호 표시 토글"""
        if checked is None:
            checked = self.w._table_element_actions.get("row_numbers", QAction()).isChecked()
        
        if hasattr(self.w.table_panel, 'set_row_numbers_visible'):
            self.w.table_panel.set_row_numbers_visible(checked)
        else:
            # 대안: 테이블 뷰의 행 헤더 숨기기/보이기
            if hasattr(self.w.table_panel, 'table_view'):
                self.w.table_panel.table_view.verticalHeader().setVisible(checked)
        self.w.statusbar.showMessage(f"Row numbers {'shown' if checked else 'hidden'}", 2000)


    def _on_toggle_column_headers(self, checked: bool = None):
        """열 헤더 표시 토글"""
        if checked is None:
            checked = self.w._table_element_actions.get("column_headers", QAction()).isChecked()
        
        if hasattr(self.w.table_panel, 'set_column_headers_visible'):
            self.w.table_panel.set_column_headers_visible(checked)
        else:
            # 대안: 테이블 뷰의 열 헤더 숨기기/보이기
            if hasattr(self.w.table_panel, 'table_view'):
                self.w.table_panel.table_view.horizontalHeader().setVisible(checked)
        self.w.statusbar.showMessage(f"Column headers {'shown' if checked else 'hidden'}", 2000)


    def _on_toggle_filter_bar(self, checked: bool = None):
        """필터 바 표시 토글"""
        if checked is None:
            checked = self.w._table_element_actions.get("filter_bar", QAction()).isChecked()
        
        if hasattr(self.w.table_panel, 'set_filter_bar_visible'):
            self.w.table_panel.set_filter_bar_visible(checked)
        self.w.statusbar.showMessage(f"Filter bar {'shown' if checked else 'hidden'}", 2000)

    # ============================================================
    # New Menu Action Methods (View Menu - Multi-Grid)
    # ============================================================


    def _on_multi_grid_view(self):
        """Multi-Grid View - 여러 그래프를 그리드로 표시"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self.w, "Multi-Grid View", "No data loaded.")
            return
        
        # 그리드 설정 다이얼로그
        layouts = ["2x1 (Horizontal)", "1x2 (Vertical)", "2x2 (Grid)", "3x2 (Wide Grid)", "Custom..."]
        layout, ok = QInputDialog.getItem(
            self.w, "Multi-Grid View", "Select grid layout:",
            layouts, 2, False
        )
        if ok:
            if layout == "Custom...":
                # 커스텀 그리드 설정
                rows, rows_ok = QInputDialog.getInt(self.w, "Custom Grid", "Number of rows:", 2, 1, 10)
                if rows_ok:
                    cols, cols_ok = QInputDialog.getInt(self.w, "Custom Grid", "Number of columns:", 2, 1, 10)
                    if cols_ok:
                        self.w.statusbar.showMessage(f"Multi-grid view: {rows}x{cols}", 3000)
            else:
                self.w.statusbar.showMessage(f"Multi-grid view: {layout}", 3000)
            
            # TODO: 실제 멀티 그리드 뷰 구현
            # self.w._floating_graph_manager.create_grid_view(rows, cols)

    # ============================================================
    # New Menu Action Methods (Data Menu)
    # ============================================================


    def _on_axis_settings(self):
        """Axis Settings - 축 설정 다이얼로그"""
        if not self.w.state.is_data_loaded:
            QMessageBox.information(self.w, "Axis Settings", "No data loaded.")
            return
        
        QMessageBox.information(
            self.w, "Axis Settings",
            "Axis settings dialog will be implemented.\n\n"
            "Configure:\n"
            "• X/Y axis range (min/max)\n"
            "• Axis labels\n"
            "• Scale type (linear/log)\n"
            "• Tick marks and intervals"
        )

    # ============================================================
    # v2 Feature Methods
    # ============================================================


    def _on_toggle_dashboard_mode(self):
        """Toggle dashboard mode (FR-B1.1) with guard flag (FR-B1.8)."""
        if self.w._dashboard_toggling:
            return
        self.w._dashboard_toggling = True
        try:
            if not self.w.state.is_data_loaded:
                QMessageBox.information(self.w, "Dashboard Mode", "No datasets loaded.")
                self.w._dashboard_mode_action.setChecked(False)
                return

            if self.w._dashboard_mode_active:
                self.w._deactivate_dashboard_mode()
            else:
                self.w._activate_dashboard_mode()
        finally:
            self.w._dashboard_toggling = False


    def _activate_dashboard_mode(self):
        """Activate dashboard mode — show DashboardPanel (FR-B1.1, FR-B1.7)."""
        if not self.w._dashboard_controller.activate():
            QMessageBox.warning(
            self.w, "Dashboard Mode",
                "Cannot activate dashboard mode. No datasets loaded."
            )
            self.w._dashboard_mode_action.setChecked(False)
            return

        # Lazy create once (FR-B1.7)
        if self.w._dashboard_panel is None:
            self.w._dashboard_panel = DashboardPanel(
                controller=self.w._dashboard_controller,
                parent=self.w,
            )
            self.w._dashboard_panel.exit_requested.connect(self.w._deactivate_dashboard_mode)
            self.w._dashboard_panel.cell_clicked.connect(self.w._on_dashboard_cell_clicked)
            self.w._dashboard_panel.preset_changed.connect(self.w._on_dashboard_preset_changed)
            self.w._dashboard_panel.cell_swap_requested.connect(self._on_dashboard_cell_swap)
            self.w._dashboard_panel.grid_size_changed.connect(self._on_dashboard_grid_size_changed)
            self.w._dashboard_panel.name_changed.connect(self._on_dashboard_name_changed)
            # Populate initial layout
            layout = self.w._dashboard_controller.current_layout
            if layout:
                self.w._dashboard_panel.populate(layout)

        # Hide normal panels, show dashboard (visibility toggle only)
        self.w.graph_panel.hide()
        if self.w._dashboard_panel.parent() != self.w.main_splitter:
            self.w.main_splitter.insertWidget(0, self.w._dashboard_panel)
        self.w._dashboard_panel.show()

        self.w._dashboard_mode_active = True
        self.w._dashboard_mode_action.setChecked(True)
        self.w.statusbar.showMessage("Dashboard mode activated — Esc to exit", 3000)


    def _deactivate_dashboard_mode(self):
        """Deactivate dashboard mode — restore normal view (FR-B1.5: state kept)."""
        self.w._dashboard_controller.deactivate()

        if self.w._dashboard_panel is not None:
            self.w._dashboard_panel.hide()
        self.w.graph_panel.show()

        self.w._dashboard_mode_active = False
        self.w._dashboard_mode_action.setChecked(False)
        self.w.statusbar.showMessage("Dashboard mode deactivated", 3000)


    def _on_dashboard_cell_clicked(self, row: int, col: int):
        """Handle empty cell click — show profile selection dialog (FR-B1.2).

        After assignment, renders a MiniGraphWidget immediately.
        """
        profiles = self.w.profile_store.get_all()
        if not profiles:
            QMessageBox.information(self.w, "Dashboard", "No profiles available. Create a profile first.")
            return

        names = [p.name for p in profiles]
        name, ok = QInputDialog.getItem(
            self.w, "Select Profile", f"Profile for cell ({row}, {col}):", names, 0, False
        )
        if ok and name:
            idx = names.index(name)
            profile = profiles[idx]
            # Ensure cell exists, then assign
            cell = self.w._dashboard_controller.get_cell(row, col)
            if cell is None:
                self.w._dashboard_controller.add_cell(row, col, profile_id=profile.id)
            else:
                self.w._dashboard_controller.assign_profile(row, col, profile.id)

            # Real-time chart rendering: create MiniGraphWidget and replace spinner
            self._render_dashboard_cell(row, col, profile)

    def _render_dashboard_cell(self, row: int, col: int, profile):
        """Render a MiniGraphWidget for a dashboard cell."""
        if self.w._dashboard_panel is None:
            return
        try:
            from ..panels.mini_graph_widget import MiniGraphWidget
            df = self.w.engine.df
            if df is None:
                return
            mini = MiniGraphWidget(parent=self.w._dashboard_panel)
            mini.set_data(df, profile)
            cell = self.w._dashboard_controller.get_cell(row, col)
            rs = cell.row_span if cell else 1
            cs = cell.col_span if cell else 1
            self.w._dashboard_panel.replace_spinner(row, col, mini, rs, cs)
        except Exception as e:
            logger.debug("view_actions_controller.mini_graph_render_failed", extra={"error": e}, exc_info=True)
            # Fallback: just refresh the panel
            layout = self.w._dashboard_controller.current_layout
            if layout and self.w._dashboard_panel:
                self.w._dashboard_panel.populate(layout)

    def _on_dashboard_cell_swap(self, src_row: int, src_col: int,
                                 dst_row: int, dst_col: int):
        """Handle drag-and-drop cell swap."""
        ctrl = self.w._dashboard_controller
        layout = ctrl.current_layout
        if layout is None:
            return
        src_cell = ctrl.get_cell(src_row, src_col)
        dst_cell = ctrl.get_cell(dst_row, dst_col)
        src_pid = src_cell.profile_id if src_cell else ""
        dst_pid = dst_cell.profile_id if dst_cell else ""
        # Swap profiles
        if src_cell:
            ctrl.assign_profile(src_row, src_col, dst_pid)
        if dst_cell:
            ctrl.assign_profile(dst_row, dst_col, src_pid)
        # Refresh
        if self.w._dashboard_panel:
            self.w._dashboard_panel.populate(layout)

    def _on_dashboard_grid_size_changed(self, rows: int, cols: int):
        """Handle custom grid size change from gear button."""
        ctrl = self.w._dashboard_controller
        before = ctrl.current_layout
        ctrl.create_layout(before.name if before else "Dashboard", rows, cols)
        layout = ctrl.current_layout
        if layout and self.w._dashboard_panel:
            self.w._dashboard_panel.populate(layout)

    def _on_dashboard_name_changed(self, new_name: str):
        """Handle dashboard name change from header double-click."""
        layout = self.w._dashboard_controller.current_layout
        if layout:
            layout.name = new_name


    def _on_dashboard_preset_changed(self, preset_name: str):
        """Handle layout preset change (FR-B1.3)."""
        layout = self.w._dashboard_controller.apply_preset(preset_name)
        if layout and self.w._dashboard_panel:
            self.w._dashboard_panel.populate(layout)


    def _on_toggle_annotation_panel(self):
        """Toggle annotation side panel (v2 Feature 5)"""
        if self.w._annotation_panel is None:
            # Create annotation panel
            self.w._annotation_panel = AnnotationPanel(
                controller=self.w._annotation_controller,
                parent=self.w,
            )
            # Connect signals
            self.w._annotation_panel.navigate_requested.connect(self.w._on_annotation_navigate)
            self.w._annotation_panel.edit_requested.connect(self.w._on_annotation_edit)
            self.w._annotation_panel.delete_requested.connect(self.w._on_annotation_delete)

        if self.w._annotation_panel.isVisible():
            self.w._annotation_panel.hide()
            self.w._annotation_panel_action.setChecked(False)
            self.w.statusbar.showMessage("Annotations panel hidden", 2000)
        else:
            # Add to right side of root splitter (horizontal)
            if self.w._annotation_panel.parent() != self.w.root_splitter:
                self.w.root_splitter.addWidget(self.w._annotation_panel)
            self.w._annotation_panel.show()
            self.w._annotation_panel_action.setChecked(True)
            self.w.statusbar.showMessage("Annotations panel shown", 2000)


    def _on_annotation_navigate(self, annotation_id: str):
        """Navigate to annotation location on chart"""
        annotation = self.w._annotation_controller.get(annotation_id)
        if annotation and hasattr(self.w.graph_panel, 'navigate_to_point'):
            self.w.graph_panel.navigate_to_point(annotation.x, annotation.y)


    def _on_annotation_edit(self, annotation_id: str):
        """Edit annotation via dialog"""
        annotation = self.w._annotation_controller.get(annotation_id)
        if annotation:
            text, ok = QInputDialog.getText(
            self.w, "Edit Annotation", "Text:", text=annotation.text
            )
            if ok and text:
                self.w._annotation_controller.edit(annotation_id, text=text)
                if self.w._annotation_panel:
                    self.w._annotation_panel.refresh()


    def _on_annotation_delete(self, annotation_id: str):
        """Delete annotation"""
        reply = QMessageBox.question(
            self.w, "Delete Annotation",
            "Are you sure you want to delete this annotation?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.w._annotation_controller.delete(annotation_id)
            if self.w._annotation_panel:
                self.w._annotation_panel.refresh()


    def _on_add_annotation(self):
        """Add a new annotation (Ctrl+Shift+N or context menu)"""
        # Check if graph is displayed
        if not self.w.state.is_data_loaded:
            self.w.statusbar.showMessage("⚠ Load data and display a graph first", 3000)
            return
        if not self.w.state.value_columns and not self.w.state.x_column:
            self.w.statusbar.showMessage("⚠ Display a graph first before adding annotations", 3000)
            return

        text, ok = QInputDialog.getText(self.w, "Add Annotation", "Annotation text:")
        if ok and text:
            import uuid
            from ..core.annotation import Annotation
            ann = Annotation(
                id=uuid.uuid4().hex[:12],
                kind="point",
                x=0.0,
                y=0.0,
                text=text,
                dataset_id=self.w.state.active_dataset_id or "",
                profile_id=self.w.profile_controller.active_profile_id if hasattr(self.w.profile_controller, 'active_profile_id') else "",
            )
            try:
                self.w._annotation_controller.add(ann)
                # Ensure panel is visible
                if self.w._annotation_panel is None or not self.w._annotation_panel.isVisible():
                    self.w._on_toggle_annotation_panel()
                if self.w._annotation_panel:
                    self.w._annotation_panel.refresh()
                self.w.statusbar.showMessage(f"Annotation added: {text[:30]}", 3000)
            except ValueError as e:
                self.w.statusbar.showMessage(f"⚠ {e}", 3000)

    # ============================================================
    # B-4: Export Wiring
    # ============================================================


    def _restore_saved_theme(self):
        """Restore theme from QSettings, default to midnight"""
        from PySide6.QtCore import QSettings
        settings = QSettings("Godol", "DataGraphStudio")
        theme_id = settings.value("appearance/theme", "midnight", type=str)
        if theme_id not in ("light", "dark", "midnight"):
            theme_id = "midnight"
        self.w._on_theme_changed(theme_id)


    def _on_cycle_theme(self):
        """Cycle through themes: light → dark → midnight → light (Ctrl+T)"""
        cycle = ["light", "dark", "midnight"]
        current = getattr(self, '_current_theme', 'midnight')
        try:
            idx = cycle.index(current)
        except ValueError:
            idx = -1
        next_theme = cycle[(idx + 1) % len(cycle)]
        self.w._on_theme_changed(next_theme)

    # ============================================================
    # B-7: Shortcut Wiring
    # ============================================================


