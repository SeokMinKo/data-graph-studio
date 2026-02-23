"""Qt event overrides for MainWindow.

Handles OS-level events: window close, drag-and-drop, keyboard.
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox
from PySide6.QtCore import Qt

from ..core.state import ChartType
from .clipboard_manager import DragDropHandler


class _MainWindowEventsMixin:
    """Mixin providing Qt event handler overrides for MainWindow.

    Requires: full MainWindow instance attributes set by MainWindow.__init__
    """

    def closeEvent(self, event):
        """창 닫기 이벤트"""
        # Stop streaming
        if hasattr(self, '_streaming_controller'):
            self._streaming_controller.shutdown()

        # Stop IPC server
        if hasattr(self, '_ipc_server'):
            self._ipc_server.stop()

        # Close all floating graph windows
        if self._floating_graph_manager:
            self._floating_graph_manager.close_all()

        # TODO: 저장 확인
        event.accept()

    # ==================== Drag & Drop ====================

    def dragEnterEvent(self, event):
        """드래그 진입 이벤트"""
        if event.mimeData().hasUrls():
            # 지원하는 파일인지 확인
            urls = event.mimeData().urls()
            supported = DragDropHandler.get_supported_files(urls)
            if supported:
                event.acceptProposedAction()
                self.statusBar().showMessage(f"Drop to load: {', '.join(os.path.basename(f) for f in supported)}")
                return

        # 텍스트 데이터 (클립보드에서 드래그)
        if event.mimeData().hasText() or event.mimeData().hasHtml():
            event.acceptProposedAction()
            self.statusBar().showMessage("Drop to paste data")
            return

        event.ignore()

    def dragLeaveEvent(self, event):
        """드래그 이탈 이벤트"""
        self.statusBar().clearMessage()

    def dropEvent(self, event):
        """드롭 이벤트"""
        mime = event.mimeData()

        # 파일 드롭
        if mime.hasUrls():
            files = DragDropHandler.get_supported_files(mime.urls())
            if files:
                event.acceptProposedAction()
                self._handle_dropped_files(files)
                return

        # 텍스트/HTML 데이터 드롭 (Excel에서 드래그 등)
        if mime.hasHtml() or mime.hasText():
            event.acceptProposedAction()
            self._paste_from_clipboard()
            return

        event.ignore()

    def _handle_dropped_files(self, files: list):
        """드롭된 파일 처리"""
        if not files:
            return

        if len(files) == 1:
            file_path = files[0]
            file_type = DragDropHandler.get_file_type(file_path)

            if file_type == 'project':
                # 프로젝트 파일 로드
                self._load_project_file(file_path)
            elif file_type == 'profile':
                # 프로필 적용
                self._on_load_profile_menu()
            else:
                # 데이터 파일 로드 (마법사 사용)
                self._show_new_project_wizard(file_path)
        else:
            # 여러 파일 → 멀티파일 다이얼로그 활용
            self._file_controller._on_open_multiple_files_with_paths(files)

    # ==================== Clipboard ====================

    def _is_text_input_focused(self) -> bool:
        """Check if a text input widget currently has focus."""
        fw = QApplication.focusWidget()
        if fw is None:
            return False
        return isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox))

    def keyPressEvent(self, event):
        """키보드 이벤트 - 클립보드 및 차트 단축키"""
        # Esc: exit dashboard mode (FR-B1.5)
        if event.key() == Qt.Key_Escape and self._dashboard_mode_active:
            self._deactivate_dashboard_mode()
            return

        # Ctrl+V: 붙여넣기
        if event.key() == Qt.Key_V and event.modifiers() == Qt.ControlModifier:
            self._paste_from_clipboard()
            return

        # Ctrl+Shift+C: 그래프 이미지 복사
        if event.key() == Qt.Key_C and event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
            self._copy_graph_to_clipboard()
            return

        # Ctrl+C: 선택된 데이터 복사 (테이블에 포커스 있을 때)
        if event.key() == Qt.Key_C and event.modifiers() == Qt.ControlModifier:
            if self.table_panel and self.table_panel.hasFocus():
                self._copy_selection_to_clipboard()
                return

        # Skip single-key shortcuts when a text input has focus
        if event.modifiers() == Qt.NoModifier and self._is_text_input_focused():
            super().keyPressEvent(event)
            return

        # Single-key shortcuts — only when text input is NOT focused
        if event.modifiers() == Qt.NoModifier:
            # Chart type shortcuts (1-6)
            chart_shortcuts = {
                Qt.Key_1: ChartType.LINE,
                Qt.Key_2: ChartType.BAR,
                Qt.Key_3: ChartType.SCATTER,
                Qt.Key_4: ChartType.PIE,
                Qt.Key_5: ChartType.AREA,
                Qt.Key_6: ChartType.HISTOGRAM,
            }

            if event.key() in chart_shortcuts:
                chart_type = chart_shortcuts[event.key()]
                self.state.set_chart_type(chart_type)
                self.statusBar().showMessage(f"Chart: {chart_type.name}", 2000)
                return

            # F → AutoFit
            if event.key() == Qt.Key_F:
                if hasattr(self, '_autofit_btn_action'):
                    self._autofit_btn_action.trigger()
                return

            # Home → Reset View
            if event.key() == Qt.Key_Home:
                if hasattr(self, '_reset_btn_action'):
                    self._reset_btn_action.trigger()
                return

            # Delete → Delete Drawing
            if event.key() == Qt.Key_Delete:
                if hasattr(self, '_delete_drawing_action'):
                    self._delete_drawing_action.trigger()
                return

        # 기본 처리
        super().keyPressEvent(event)
