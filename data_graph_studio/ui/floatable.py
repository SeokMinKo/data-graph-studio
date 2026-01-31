"""
Floatable Section - 섹션을 독립 창으로 분리하는 기능
"""

from typing import Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QDialog, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon


class FloatWindow(QDialog):
    """독립 창으로 분리된 섹션을 위한 윈도우 (Non-modal)"""

    dock_requested = Signal()  # 다시 메인 창으로 복귀 요청

    def __init__(self, title: str, content_widget: QWidget, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # Non-modal window with standard window controls
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.setModal(False)  # Non-modal: main window remains interactive
        self.setMinimumSize(400, 300)

        self._content_widget = content_widget
        self._setup_ui()

        # 기본 크기 설정
        self.resize(600, 500)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: linear-gradient(180deg, #F8FAFC 0%, #F1F5F9 100%);
                border-bottom: 1px solid #E2E8F0;
                padding: 4px 8px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(8)

        # Dock button
        dock_btn = QPushButton("⬅ Dock")
        dock_btn.setToolTip("Return to main window")
        dock_btn.setStyleSheet("""
            QPushButton {
                background: #4F46E5;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #4338CA;
            }
            QPushButton:pressed {
                background: #3730A3;
            }
        """)
        dock_btn.clicked.connect(self._on_dock_clicked)
        header_layout.addWidget(dock_btn)

        header_layout.addStretch()

        layout.addWidget(header)

        # Content
        layout.addWidget(self._content_widget, 1)

    def _on_dock_clicked(self):
        self.dock_requested.emit()
        self.hide()

    def closeEvent(self, event):
        """창 닫기 시 Dock 요청"""
        self.dock_requested.emit()
        event.accept()

    def get_content_widget(self) -> QWidget:
        return self._content_widget


class FloatableSectionHeader(QFrame):
    """Float 버튼이 포함된 섹션 헤더"""

    float_clicked = Signal()

    def __init__(self, title: str, icon: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._icon = icon
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QFrame {
                background: transparent;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(6)

        # Title with icon
        title_text = f"{self._icon} {self._title}" if self._icon else self._title
        self.title_label = QLabel(title_text)
        self.title_label.setStyleSheet("""
            QLabel {
                font-weight: 600;
                font-size: 13px;
                color: #111827;
                padding: 4px;
                background: transparent;
            }
        """)
        layout.addWidget(self.title_label)

        layout.addStretch()

        # Float button
        self.float_btn = QPushButton("⬈")
        self.float_btn.setToolTip("Float as separate window")
        self.float_btn.setFixedSize(24, 24)
        self.float_btn.setCursor(Qt.PointingHandCursor)
        self.float_btn.setStyleSheet("""
            QPushButton {
                background: #F3F4F6;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 12px;
                color: #6B7280;
            }
            QPushButton:hover {
                background: #E5E7EB;
                border-color: #D1D5DB;
                color: #374151;
            }
            QPushButton:pressed {
                background: #D1D5DB;
            }
        """)
        self.float_btn.clicked.connect(self.float_clicked.emit)
        layout.addWidget(self.float_btn)

    def set_title(self, title: str):
        self._title = title
        title_text = f"{self._icon} {self._title}" if self._icon else self._title
        self.title_label.setText(title_text)


class FloatableSection(QFrame):
    """
    Float 기능이 포함된 섹션 컨테이너

    사용법:
    1. content_widget을 생성하여 FloatableSection에 전달
    2. float 버튼 클릭 시 content_widget이 별도 창으로 분리됨
    3. dock 버튼 클릭 시 다시 원래 위치로 복귀
    """

    floated = Signal()  # 섹션이 float됨
    docked = Signal()   # 섹션이 다시 dock됨

    def __init__(
        self,
        title: str,
        content_widget: QWidget,
        icon: str = "",
        show_header: bool = True,
        parent=None
    ):
        super().__init__(parent)
        self._title = title
        self._icon = icon
        self._content_widget = content_widget
        self._show_header = show_header
        self._float_window: Optional[FloatWindow] = None
        self._is_floating = False

        # Placeholder widget shown when content is floating
        self._placeholder = self._create_placeholder()

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        if self._show_header:
            self._header = FloatableSectionHeader(self._title, self._icon, self)
            self._header.float_clicked.connect(self._on_float_clicked)
            layout.addWidget(self._header)

        # Content area
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._content_layout.addWidget(self._content_widget)

        layout.addLayout(self._content_layout, 1)

    def _create_placeholder(self) -> QWidget:
        """Float 상태일 때 보여줄 플레이스홀더"""
        placeholder = QFrame()
        placeholder.setStyleSheet("""
            QFrame {
                background: #F9FAFB;
                border: 2px dashed #D1D5DB;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel(f"📤 {self._title}\n\nFloating as separate window\n\nClick 'Dock' to return")
        label.setStyleSheet("""
            QLabel {
                color: #9CA3AF;
                font-size: 12px;
                text-align: center;
                background: transparent;
            }
        """)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        return placeholder

    def _on_float_clicked(self):
        """Float 버튼 클릭 처리"""
        if self._is_floating:
            return

        # Create float window
        main_window = self._find_main_window()
        self._float_window = FloatWindow(self._title, self._content_widget, main_window)
        self._float_window.dock_requested.connect(self._on_dock_requested)

        # Show placeholder
        self._content_layout.replaceWidget(self._content_widget, self._placeholder)
        self._placeholder.show()

        # Show float window
        self._float_window.show()
        self._is_floating = True

        # Update header
        if self._show_header:
            self._header.float_btn.setEnabled(False)
            self._header.float_btn.setText("⬈")
            self._header.float_btn.setToolTip("Section is floating")

        self.floated.emit()

    def _on_dock_requested(self):
        """Dock 요청 처리"""
        if not self._is_floating:
            return

        # Get content back from float window
        content = self._float_window.get_content_widget()

        # Replace placeholder with content
        self._content_layout.replaceWidget(self._placeholder, content)
        self._placeholder.hide()
        content.show()

        # Clean up float window
        self._float_window.close()
        self._float_window.deleteLater()
        self._float_window = None
        self._is_floating = False

        # Update header
        if self._show_header:
            self._header.float_btn.setEnabled(True)
            self._header.float_btn.setText("⬈")
            self._header.float_btn.setToolTip("Float as separate window")

        self.docked.emit()

    def _find_main_window(self):
        """메인 윈도우 찾기"""
        widget = self
        while widget:
            if widget.inherits("QMainWindow"):
                return widget
            widget = widget.parentWidget()
        return None

    def is_floating(self) -> bool:
        return self._is_floating

    def dock(self):
        """프로그래밍적으로 dock 요청"""
        if self._is_floating:
            self._on_dock_requested()

    def float_out(self):
        """프로그래밍적으로 float 요청"""
        if not self._is_floating:
            self._on_float_clicked()

    def get_content_widget(self) -> QWidget:
        return self._content_widget

    def set_header_visible(self, visible: bool):
        """헤더 표시/숨김"""
        if self._show_header and hasattr(self, '_header'):
            self._header.setVisible(visible)


class FloatButton(QPushButton):
    """간단한 Float 버튼 (기존 패널에 추가용)"""

    def __init__(self, parent=None):
        super().__init__("⬈", parent)
        self.setToolTip("Float as separate window")
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                font-size: 11px;
                color: #9CA3AF;
            }
            QPushButton:hover {
                background: #F3F4F6;
                border-color: #D1D5DB;
                color: #6B7280;
            }
            QPushButton:pressed {
                background: #E5E7EB;
            }
        """)
