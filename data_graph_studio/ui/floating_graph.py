"""
Floating Graph Window - 독립된 그래프 창
"""

import uuid
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QToolButton, QCheckBox, QWidget, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent

from ..core.state import AppState
from ..core.data_engine import DataEngine
from ..core.profile import GraphSetting


class FloatingGraphWindow(QDialog):
    """
    독립적인 그래프 창
    - 메인 창과 동일한 데이터를 공유
    - 개별 그래프 설정 유지
    - Selection Sync 옵션
    """

    closed = Signal(str)  # window_id
    sync_selection_changed = Signal(bool)

    def __init__(
        self,
        window_id: str,
        setting: GraphSetting,
        state: AppState,
        engine: DataEngine,
        parent=None
    ):
        super().__init__(parent)
        self._window_id = window_id
        self._setting = setting
        self._state = state
        self._engine = engine
        self._sync_selection = True
        self._graph_panel = None

        self.setWindowTitle(f"{setting.icon} {setting.name}")
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.setMinimumSize(600, 400)
        self.resize(800, 600)

        self._setup_ui()
        self._connect_signals()

        # 초기 그래프 렌더링
        self._apply_setting()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 헤더 바
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: linear-gradient(180deg, #F8FAFC 0%, #F1F5F9 100%);
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(12)

        # 설정 이름
        title_label = QLabel(f"{self._setting.icon} {self._setting.name}")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: 600;
                color: #E6E9EF;
                background: transparent;
            }
        """)
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # Selection Sync 체크박스
        self._sync_cb = QCheckBox("🔗 Sync Selection")
        self._sync_cb.setChecked(True)
        self._sync_cb.setToolTip("Synchronize selection with main window")
        self._sync_cb.setStyleSheet("""
            QCheckBox {
                color: #C2C8D1;
                font-size: 12px;
                background: transparent;
            }
        """)
        self._sync_cb.stateChanged.connect(self._on_sync_changed)
        header_layout.addWidget(self._sync_cb)

        # 구분선
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background: #D1D5DB;")
        header_layout.addWidget(sep)

        # 액션 버튼들
        copy_btn = QToolButton()
        copy_btn.setText("📋")
        copy_btn.setToolTip("Copy to clipboard")
        copy_btn.setStyleSheet(self._btn_style())
        copy_btn.clicked.connect(self._on_copy)
        header_layout.addWidget(copy_btn)

        export_btn = QToolButton()
        export_btn.setText("💾")
        export_btn.setToolTip("Export as image")
        export_btn.setStyleSheet(self._btn_style())
        export_btn.clicked.connect(self._on_export)
        header_layout.addWidget(export_btn)

        layout.addWidget(header)

        # 그래프 영역
        self._graph_container = QWidget()
        self._graph_container.setStyleSheet("background: white;")
        self._graph_layout = QVBoxLayout(self._graph_container)
        self._graph_layout.setContentsMargins(0, 0, 0, 0)

        # GraphPanel 생성 (지연 로딩)
        self._create_graph_panel()

        layout.addWidget(self._graph_container, 1)

        # 푸터 상태바
        footer = QFrame()
        footer.setStyleSheet("""
            QFrame {
                background: #2B3440;
                border-top: 1px solid #3E4A59;
            }
        """)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 6, 12, 6)

        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet("color: #C2C8D1; font-size: 11px; background: transparent;")
        footer_layout.addWidget(self._status_label)

        footer_layout.addStretch()

        layout.addWidget(footer)

    def _btn_style(self) -> str:
        return """
            QToolButton {
                background: transparent;
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
            }
            QToolButton:hover {
                background: #3A4654;
                border-color: #9CA3AF;
            }
            QToolButton:pressed {
                background: #3E4A59;
            }
        """

    def _create_graph_panel(self):
        """그래프 패널 생성"""
        try:
            # GraphPanel을 동적으로 import (순환 참조 방지)
            from .panels.graph_panel import GraphPanel

            # 새로운 독립적인 상태 생성 (setting 기반)
            self._graph_panel = GraphPanel(self._state, self._engine)
            self._graph_panel.set_columns(self._engine.columns)
            self._graph_layout.addWidget(self._graph_panel)

        except Exception as e:
            # 그래프 패널 생성 실패 시 플레이스홀더 표시
            placeholder = QLabel(f"Failed to create graph: {e}")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #EF4444;")
            self._graph_layout.addWidget(placeholder)

    def _connect_signals(self):
        """시그널 연결"""
        # Selection sync
        if self._sync_selection:
            self._state.selection_changed.connect(self._on_main_selection_changed)

    def _apply_setting(self):
        """설정 적용"""
        if self._graph_panel:
            # GraphSetting을 기반으로 그래프 설정
            self._state.apply_graph_setting(self._setting)
            self._graph_panel.refresh()

    def _on_sync_changed(self, state: int):
        """Selection Sync 변경"""
        self._sync_selection = state == Qt.Checked
        self.sync_selection_changed.emit(self._sync_selection)

    def _on_main_selection_changed(self):
        """메인 창 선택 변경 (Sync ON인 경우)"""
        if self._sync_selection and self._graph_panel:
            self._graph_panel.highlight_selection()

    def _on_copy(self):
        """클립보드에 복사"""
        if self._graph_panel:
            self._graph_panel.copy_to_clipboard()
            self._status_label.setText("Copied to clipboard")

    def _on_export(self):
        """이미지로 내보내기"""
        if self._graph_panel:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Graph",
                f"{self._setting.name}.png",
                "PNG Image (*.png);;SVG Vector (*.svg)"
            )
            if path:
                self._graph_panel.export_image(path)
                self._status_label.setText(f"Exported to {path}")

    @property
    def window_id(self) -> str:
        return self._window_id

    @property
    def setting(self) -> GraphSetting:
        return self._setting

    @property
    def sync_selection(self) -> bool:
        return self._sync_selection

    def closeEvent(self, event: QCloseEvent):
        """창 닫기 이벤트"""
        self.closed.emit(self._window_id)
        event.accept()

    def refresh(self):
        """그래프 새로고침"""
        if self._graph_panel:
            self._graph_panel.refresh()


class FloatingGraphManager:
    """플로팅 그래프 창 관리자"""

    def __init__(self, state: AppState, engine: DataEngine):
        self._state = state
        self._engine = engine
        self._windows: Dict[str, FloatingGraphWindow] = {}

    def open_floating_graph(
        self,
        setting: GraphSetting,
        parent=None
    ) -> FloatingGraphWindow:
        """
        새 플로팅 그래프 창 열기

        Args:
            setting: 그래프 설정
            parent: 부모 위젯

        Returns:
            생성된 FloatingGraphWindow
        """
        window_id = str(uuid.uuid4())

        window = FloatingGraphWindow(
            window_id=window_id,
            setting=setting,
            state=self._state,
            engine=self._engine,
            parent=parent
        )

        window.closed.connect(self._on_window_closed)

        self._windows[window_id] = window
        self._state.register_floating_window(window_id, window)

        window.show()
        return window

    def _on_window_closed(self, window_id: str):
        """창 닫힘 처리"""
        if window_id in self._windows:
            del self._windows[window_id]
            self._state.unregister_floating_window(window_id)

    def close_all(self):
        """모든 플로팅 창 닫기"""
        for window in list(self._windows.values()):
            window.close()
        self._windows.clear()

    def get_window(self, window_id: str) -> Optional[FloatingGraphWindow]:
        """창 가져오기"""
        return self._windows.get(window_id)

    def get_all_windows(self) -> Dict[str, FloatingGraphWindow]:
        """모든 창 가져오기"""
        return self._windows.copy()

    def tile_windows(self, mode: str = "horizontal"):
        """창 정렬"""
        if not self._windows:
            return

        screen = QApplication.primaryScreen().availableGeometry()
        windows = list(self._windows.values())
        n = len(windows)

        if mode == "horizontal":
            width = screen.width() // n
            for i, window in enumerate(windows):
                window.setGeometry(
                    screen.x() + i * width,
                    screen.y(),
                    width,
                    screen.height()
                )
        elif mode == "vertical":
            height = screen.height() // n
            for i, window in enumerate(windows):
                window.setGeometry(
                    screen.x(),
                    screen.y() + i * height,
                    screen.width(),
                    height
                )
        elif mode == "cascade":
            offset = 30
            for i, window in enumerate(windows):
                window.move(
                    screen.x() + i * offset,
                    screen.y() + i * offset
                )
                window.resize(800, 600)

    def sync_all_selections(self, sync: bool):
        """모든 창의 Selection Sync 설정"""
        for window in self._windows.values():
            window._sync_cb.setChecked(sync)
