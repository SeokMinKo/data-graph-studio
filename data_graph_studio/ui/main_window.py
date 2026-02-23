"""
Main Window - 메인 윈도우 및 레이아웃
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QApplication, QLabel, QFrame,
    QTabWidget, QDockWidget, QLineEdit
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut

from ..core.data_engine import DataEngine
from ..core.state import AppState, ChartType
from .clipboard_manager import DragDropHandler
from ..core.streaming_controller import StreamingController
from ..core.io_abstract import RealFileSystem, ITimerFactory
from .adapters.streaming_adapter import StreamingControllerAdapter
from .adapters.profile_comparison_adapter import ProfileComparisonControllerAdapter
from .adapters.app_state_adapter import AppStateAdapter
from ..core.undo_manager import UndoStack
from .panels.history_panel import HistoryPanel
from ..core.dashboard_controller import DashboardController
from ..core.annotation_controller import AnnotationController
from .controllers.shortcut_controller import ShortcutController
from ..core.export_controller import ExportController
from .adapters.export_controller_adapter import ExportControllerAdapter
from ..utils.memory import MemoryMonitor
from .panels.summary_panel import SummaryPanel
from .panels.graph_panel import GraphPanel
from .panels.table_panel import TablePanel
from .panels.profile_bar import ProfileBar
from .panels.dataset_manager_panel import DatasetManagerPanel
from .panels.side_by_side_layout import SideBySideLayout
from .panels.comparison_stats_panel import ComparisonStatsPanel
from .panels.overlay_stats_widget import OverlayStatsWidget
from .panels.annotation_panel import AnnotationPanel
from .panels.dashboard_panel import DashboardPanel
from ..core.parsing import ParsingSettings
from .floatable import FloatWindow
from .floating_graph import FloatingGraphManager
from ..core.profile_store import ProfileStore
from ..core.profile_controller import ProfileController
from ..core.profile_comparison_controller import ProfileComparisonController
from .models.profile_model import ProfileModel
from .views.project_tree_view import ProjectTreeView

# Controllers (extracted from MainWindow)
from .controllers.ipc_controller import IPCController
from .controllers.file_loading_controller import (
    FileLoadingController, DataLoaderThread,
)
from .controllers.dataset_controller import DatasetController
from .controllers.profile_ui_controller import ProfileUIController
from .controllers.menu_setup_controller import MenuSetupController
from .controllers.toolbar_controller import ToolbarController
from .controllers.trace_controller import TraceController
from .controllers.streaming_ui_controller import StreamingUIController
from .controllers.comparison_ui_controller import ComparisonUIController
from .controllers.data_ops_controller import DataOpsController
from .controllers.view_actions_controller import ViewActionsController
from .controllers.help_controller import HelpController
from .controllers.export_ui_controller import ExportUIController
from .controllers.autorecovery_controller import AutorecoveryController

# 에러 로깅 설정
logger = logging.getLogger(__name__)


from ._qt_timer_factory import _QtTimerWrapper, _QtTimerFactory  # noqa: F401
from ._main_window_ipc_mixin import _MainWindowIpcMixin
from ._main_window_actions_mixin import _MainWindowActionsMixin


class MainWindow(_MainWindowIpcMixin, _MainWindowActionsMixin, QMainWindow):
    """
    Data Graph Studio 메인 윈도우

    Layout:
    ┌─────────────────────────────────┐
    │  Menu Bar                       │
    ├─────────────────────────────────┤
    │  Toolbar                        │
    ├─────────────────────────────────┤
    │  Summary Panel        (10%)     │
    ├─────────────────────────────────┤
    │  Graph Panel          (45%)     │
    ├─────────────────────────────────┤
    │  Table Panel          (45%)     │
    ├─────────────────────────────────┤
    │  Status Bar                     │
    └─────────────────────────────────┘
    """

    # 대용량 파일 경고 임계값
    LARGE_FILE_WARNING_MB = 500  # 500MB 이상 파일 경고
    HUGE_FILE_WARNING_MB = 2000  # 2GB 이상 파일 강력 경고

    def __init__(self):
        super().__init__()

        # Core components
        self.engine = DataEngine()
        self.state = AppState()
        # Adapter bridges AppState Observable events to Qt Signals for UI connections
        self._state_adapter = AppStateAdapter(self.state, parent=self)

        # Profile management (Project Explorer)
        self.profile_store = ProfileStore()
        self.profile_controller = ProfileController(self.profile_store, self.state)
        self.profile_comparison_controller = ProfileComparisonController(
            self.profile_store, self.profile_controller, self.state,
        )
        # Adapter translates Observable events to Qt Signals for UI connections
        self._comparison_adapter = ProfileComparisonControllerAdapter(
            self.profile_comparison_controller, parent=self
        )

        # Streaming controller (pure Observable — no Qt dependency)
        self._streaming_controller = StreamingController(
            fs=RealFileSystem(),
            timer_factory=_QtTimerFactory(),
        )
        # Adapter translates Observable events to Qt Signals for UI connections
        self._streaming_adapter = StreamingControllerAdapter(
            self._streaming_controller, parent=self
        )

        # ===== v2 Feature Controllers =====
        # Undo/Redo stack (session-only)
        self._undo_stack = UndoStack(max_depth=200, on_changed=self._on_undo_stack_changed)
        self.state.set_undo_stack(self._undo_stack)

        self._history_panel: Optional[HistoryPanel] = None
        self._history_dock: Optional[QDockWidget] = None

        # Feature 1: Dashboard Mode
        self._dashboard_controller = DashboardController(self.state, self._undo_stack)
        self._dashboard_panel: Optional[DashboardPanel] = None
        self._dashboard_mode_active = False
        self._dashboard_toggling = False  # FR-B1.8: guard flag

        # Feature 5: Annotations/Bookmarks
        self._annotation_controller = AnnotationController(undo_manager=self._undo_stack)
        self._annotation_panel: Optional[AnnotationPanel] = None

        # Feature 7: Keyboard Shortcuts
        self._shortcut_controller = ShortcutController()
        self._shortcut_controller.register_defaults()
        self._shortcut_controller.load_config()

        # Feature 4: Export
        self._export_controller = ExportController()
        self._export_controller_adapter = ExportControllerAdapter(self._export_controller, parent=self)

        # Loading thread
        self._loader_thread: Optional[DataLoaderThread] = None

        # Float windows tracking
        self._float_windows: Dict[str, FloatWindow] = {}
        self._placeholders: Dict[str, QWidget] = {}

        # Comparison view panels
        self._side_by_side_layout: Optional[SideBySideLayout] = None
        self._comparison_stats_panel: Optional[ComparisonStatsPanel] = None
        self._current_comparison_view: Optional[QWidget] = None
        self._overlay_stats_widget: Optional[OverlayStatsWidget] = None
        self._profile_comparison_view: Optional[QWidget] = None

        # Floating graph manager
        self._floating_graph_manager: Optional[FloatingGraphManager] = None

        # Last save/load paths for profile/project
        self._last_profile_path: Optional[str] = None
        self._last_project_path: Optional[str] = None

        # ===== Controllers (extracted from MainWindow) =====
        self._ipc_controller = IPCController(self)
        self._file_controller = FileLoadingController(self)
        self._dataset_controller = DatasetController(self)
        self._profile_ui_controller = ProfileUIController(self)
        self._menu_setup_ctrl = MenuSetupController(self)
        self._toolbar_ctrl = ToolbarController(self)
        self._trace_ctrl = TraceController(self)
        self._streaming_ui_ctrl = StreamingUIController(self)
        self._comparison_ui_ctrl = ComparisonUIController(self)
        self._data_ops_ctrl = DataOpsController(self)
        self._view_actions_ctrl = ViewActionsController(self)
        self._help_ctrl = HelpController(self)
        self._export_ui_ctrl = ExportUIController(self)
        self._autorecovery_ctrl = AutorecoveryController(self)

        # Setup UI
        self._setup_window()
        self._setup_menubar()
        self._setup_main_layout()  # Must be before toolbar (toolbar references dataset_manager)
        self._setup_toolbar()
        self._setup_streaming_toolbar()
        self._setup_compare_toolbar()
        self._setup_statusbar()

        # Connect signals
        self._connect_signals()

        # Setup float handlers for main panels
        self._setup_float_handlers()

        # Setup memory monitoring timer
        self._setup_memory_monitor()

        # Setup IPC server for external control
        self._setup_ipc_server()

        # Setup auto-recovery (autosave + restore prompt)
        self._setup_autorecovery()

        # Wire shortcut callbacks
        self._wire_shortcut_callbacks()

        # Quick Switch: Alt+1~9 로 프로파일 전환
        self._setup_quick_switch_shortcuts()

        # Restore saved theme or default to midnight
        self._restore_saved_theme()

        # Apply initial state
        self._update_ui_state()

        # Auto-update (Windows)
        QTimer.singleShot(2000, self._auto_check_updates)

        # Headless capture mode
        import sys as _sys
        if "--capture-mode" in _sys.argv:
            QTimer.singleShot(2000, self._run_capture_and_exit)

    def _run_capture_and_exit(self) -> None:
        """Headless capture mode: capture panels then exit. Called 2s after startup."""
        import argparse
        import dataclasses
        import json
        from pathlib import Path
        from PySide6.QtWidgets import QApplication
        from data_graph_studio.core.capture_protocol import CaptureRequest

        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--capture-target", default="all")
        parser.add_argument("--capture-output", default="/tmp/dgs_captures")
        parser.add_argument("--capture-result-file", default=None)
        args, _ = parser.parse_known_args()

        req = CaptureRequest(target=args.capture_target, output_dir=Path(args.capture_output))
        results = self._ipc_controller._capture_service.capture(req)

        output = {
            "status": "ok",
            "captures": [{**dataclasses.asdict(r), "file": str(r.file)} for r in results],
        }

        if args.capture_result_file:
            Path(args.capture_result_file).write_text(json.dumps(output, indent=2))

        QApplication.quit()

    def _setup_window(self):
        """윈도우 기본 설정"""
        self.setWindowTitle("Data Graph Studio")
        self.setMinimumSize(1200, 800)

        # 화면 크기의 80%로 시작
        screen = QApplication.primaryScreen().geometry()
        self.resize(int(screen.width() * 0.8), int(screen.height() * 0.8))

        # 중앙 정렬
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

        # 드래그 앤 드롭 활성화
        self.setAcceptDrops(True)

    @staticmethod
    def _format_tooltip(action_name: str, shortcut: str) -> str:
        """툴팁에 단축키를 보기 좋게 포맷팅"""
        return f"<b>{action_name}</b><br><span style='color: #C2C8D1;'>Shortcut: {shortcut}</span>"

    def _setup_menubar(self, *a, **kw):
        return self._menu_setup_ctrl._setup_menubar(*a, **kw)

    def _setup_toolbar(self, *a, **kw):
        return self._toolbar_ctrl._setup_toolbar(*a, **kw)

    def _setup_streaming_toolbar(self, *a, **kw):
        return self._toolbar_ctrl._setup_streaming_toolbar(*a, **kw)

    def _setup_compare_toolbar(self, *a, **kw):
        return self._toolbar_ctrl._setup_compare_toolbar(*a, **kw)

    def _setup_main_layout(self):
        """메인 레이아웃 설정 (사이드바 + 3단 스플리터)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 최상위 수평 스플리터 (사이드바 | 메인 영역)
        self.root_splitter = QSplitter(Qt.Horizontal)
        self.root_splitter.setHandleWidth(2)
        self.root_splitter.setObjectName("themeSplitter")

        # 좌측 사이드바 - 탭 구조 (Projects + Datasets)
        self._sidebar_tabs = QTabWidget()
        self._sidebar_tabs.setMinimumWidth(100)
        self._sidebar_tabs.setMaximumWidth(350)
        # Style handled by global theme stylesheet

        # Project Explorer (새로운 트리 뷰) + 검색바
        self.profile_model = ProfileModel(self.profile_store, self.state)
        self.project_tree = ProjectTreeView()
        self.project_tree.set_model(self.profile_model)
        self.project_tree.profile_activated.connect(self._on_profile_apply_requested)
        self.project_tree.project_activated.connect(self._on_dataset_activated)
        self.project_tree.new_profile_requested.connect(self._on_new_profile_requested)
        self.project_tree.rename_requested.connect(self._on_profile_rename_requested)
        self.project_tree.delete_requested.connect(self._on_profile_delete_requested)
        self.project_tree.duplicate_requested.connect(self._on_profile_duplicate_requested)
        self.project_tree.export_requested.connect(self._on_profile_export_requested)
        self.project_tree.import_requested.connect(self._on_profile_import_requested)
        self.project_tree.compare_requested.connect(self._on_profile_compare_requested)
        self.project_tree.copy_to_dataset_requested.connect(self._on_copy_to_dataset_requested)
        self.project_tree.favorite_toggled.connect(self._on_favorite_toggled)

        # 검색바 + 트리를 컨테이너로 감싸기
        project_container = QWidget()
        project_layout = QVBoxLayout(project_container)
        project_layout.setContentsMargins(0, 0, 0, 0)
        project_layout.setSpacing(0)

        self._project_search = QLineEdit()
        self._project_search.setPlaceholderText("🔍 Filter profiles...")
        self._project_search.setClearButtonEnabled(True)
        self._project_search.textChanged.connect(self.project_tree.set_filter_text)
        project_layout.addWidget(self._project_search)
        project_layout.addWidget(self.project_tree)

        self._sidebar_tabs.addTab(project_container, "Projects")

        # Dataset Manager (내부용 - 탭에서 제거됨, 기능은 유지)
        self.dataset_manager = DatasetManagerPanel(self.engine, self.state)
        self.dataset_manager.dataset_activated.connect(self._on_dataset_activated)
        self.dataset_manager.dataset_removed.connect(self._on_dataset_remove_requested)
        self.dataset_manager.add_dataset_requested.connect(self._on_add_dataset)
        self.dataset_manager.comparison_mode_changed.connect(self._on_comparison_mode_changed)
        self.dataset_manager.comparison_started.connect(self._on_comparison_started)
        # NOTE: Datasets 탭 제거됨 - Projects 탭만 사용
        # self._sidebar_tabs.addTab(self.dataset_manager, "Datasets")

        self.root_splitter.addWidget(self._sidebar_tabs)

        # 메인 스플리터 (수직)
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setHandleWidth(2)
        self.main_splitter.setObjectName("themeSplitter")

        # Summary panel (internal use only, not displayed)
        self.summary_panel = SummaryPanel(self.state)

        # Profile bar (internal use only, not displayed)
        self._profile_bar_container = QWidget()
        profile_bar_layout = QVBoxLayout(self._profile_bar_container)
        profile_bar_layout.setContentsMargins(8, 0, 8, 8)
        profile_bar_layout.setSpacing(0)

        self.profile_bar = ProfileBar(self.state)
        self.profile_bar.setting_clicked.connect(self._on_profile_setting_clicked)
        self.profile_bar.setting_double_clicked.connect(self._on_profile_setting_double_clicked)
        self.profile_bar.add_setting_requested.connect(self._on_add_setting_requested)
        self.profile_bar.compare_requested.connect(self._on_compare_profiles_requested)
        profile_bar_layout.addWidget(self.profile_bar)

        # Graph Panel (상단)
        self.graph_panel = GraphPanel(self.state, self.engine)
        self.main_splitter.addWidget(self.graph_panel)

        # Connect empty state signals
        self.graph_panel._empty_state.open_file_requested.connect(self._on_open_file)
        self.graph_panel._empty_state.load_sample_requested.connect(self._on_load_sample_data)

        # Table Panel (하단)
        self.table_panel = TablePanel(self.state, self.engine, self.graph_panel)
        self.main_splitter.addWidget(self.table_panel)

        # 메인 스플리터를 root_splitter에 추가
        self.root_splitter.addWidget(self.main_splitter)

        # root_splitter 비율 설정 (사이드바: 메인 = 150 : 나머지)
        self.root_splitter.setSizes([200, 1000])

        # 초기 비율 설정
        self._reset_layout()

        layout.addWidget(self.root_splitter)

        # Initialize floating graph manager
        self._floating_graph_manager = FloatingGraphManager(self.state, self.engine)

        # History (Undo/Redo) dock
        self._setup_history_dock()

    def _setup_history_dock(self):
        if self._history_dock is not None:
            return

        self._history_panel = HistoryPanel(self._undo_stack, parent=self)
        self._history_panel.request_undo.connect(self._on_undo)
        self._history_panel.request_redo.connect(self._on_redo)

        dock = QDockWidget("History", self)
        dock.setObjectName("HistoryDock")
        dock.setWidget(self._history_panel)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._history_dock = dock

        # Add toggle action to View menu
        try:
            for action in self.menuBar().actions():
                if action.text().replace("&", "") == "View":
                    view_menu = action.menu()
                    if view_menu:
                        view_menu.addSeparator()
                        toggle_action = dock.toggleViewAction()
                        toggle_action.setText("History Panel")
                        view_menu.addAction(toggle_action)
                    break
        except Exception:
            logger.warning("main_window.setup_history_panel_menu.error", exc_info=True)

    def _reset_layout(self):
        """레이아웃 비율 초기화 및 모든 Float 창 Dock"""
        # First, dock all floating panels back to main window
        float_keys = list(self._float_windows.keys())
        for panel_key in float_keys:
            self._dock_main_panel(panel_key)

        # Ensure all panels are visible and in correct order
        panel_widgets = [self.graph_panel, self.table_panel]

        # Verify all panels are in splitter, rebuild if necessary
        current_widgets = [self.main_splitter.widget(i) for i in range(self.main_splitter.count())]

        # Check if any panel is missing from the splitter
        needs_rebuild = False
        for panel in panel_widgets:
            if panel not in current_widgets and self._placeholders.get(
                self._get_panel_key(panel), panel) not in current_widgets:
                needs_rebuild = True
                break

        if needs_rebuild:
            # Remove all widgets from splitter
            while self.main_splitter.count() > 0:
                widget = self.main_splitter.widget(0)
                widget.setParent(None)

            # Re-add panels in correct order
            for panel in panel_widgets:
                self.main_splitter.addWidget(panel)
                panel.show()

        # Set sizes - Graph 40%, Table 60% (테이블에 더 많은 공간)
        total_height = self.main_splitter.height()
        if total_height == 0:
            total_height = 800  # 기본값

        sizes = [
            int(total_height * 0.4),   # Graph
            int(total_height * 0.6),   # Table
        ]
        self.main_splitter.setSizes(sizes)

    def _get_panel_key(self, panel: QWidget) -> Optional[str]:
        """Get the panel key for a widget"""
        if panel is self.graph_panel:
            return "graph"
        elif panel is self.table_panel:
            return "table"
        return None

    def _toggle_panel_visibility(self, panel_key: str, visible: bool):
        """Toggle visibility of a panel"""
        panel_map = {
            "graph": self.graph_panel,
            "table": self.table_panel,
        }

        panel = panel_map.get(panel_key)
        if panel is None:
            return

        # If panel is floating, handle differently
        if panel_key in self._float_windows:
            float_window = self._float_windows[panel_key]
            if visible:
                float_window.show()
            else:
                float_window.hide()
            return

        # Toggle visibility in splitter
        if visible:
            panel.show()
        else:
            panel.hide()

        # Redistribute sizes among visible panels
        self._redistribute_panel_sizes()

    def _redistribute_panel_sizes(self):
        """Redistribute sizes among visible panels"""
        visible_panels = []
        for i in range(self.main_splitter.count()):
            widget = self.main_splitter.widget(i)
            if widget and not widget.isHidden():
                visible_panels.append(i)

        if not visible_panels:
            return

        total_height = self.main_splitter.height()
        if total_height == 0:
            total_height = 800

        # Distribute equally among visible panels
        per_panel = total_height // len(visible_panels)
        sizes = []
        for i in range(self.main_splitter.count()):
            if i in visible_panels:
                sizes.append(per_panel)
            else:
                sizes.append(0)

        self.main_splitter.setSizes(sizes)

    def _setup_statusbar(self):
        """Modern status bar setup"""
        self.statusbar = QStatusBar()
        # Style handled by global theme stylesheet
        self.setStatusBar(self.statusbar)

        # Status labels with icons
        self._status_data_label = QLabel("📋 No data loaded")
        self._status_data_label.setObjectName("hintLabel")

        self._status_selection_label = QLabel("")
        self._status_memory_label = QLabel("💾 --")
        self._status_memory_label.setToolTip("Memory Usage (Process / System)")

        self.statusbar.addWidget(self._status_data_label)
        self.statusbar.addWidget(self._status_selection_label, 1)
        self.statusbar.addPermanentWidget(self._status_memory_label)

    def _setup_memory_monitor(self):
        """메모리 모니터링 타이머 설정"""
        self._memory_timer = QTimer(self)
        self._memory_timer.timeout.connect(self._update_memory_status)
        self._memory_timer.start(3000)  # 3초마다 업데이트
        self._update_memory_status()  # 초기값 설정

    def _setup_autorecovery(self, *a, **kw):
        return self._autorecovery_ctrl._setup_autorecovery(*a, **kw)

    def _prompt_recovery(self, *a, **kw):
        return self._autorecovery_ctrl._prompt_recovery(*a, **kw)

    def _autosave_session(self, *a, **kw):
        return self._autorecovery_ctrl._autosave_session(*a, **kw)

    def _restore_autosave(self, *a, **kw):
        return self._autorecovery_ctrl._restore_autosave(*a, **kw)

    def _restore_next(self, *a, **kw):
        return self._autorecovery_ctrl._restore_next(*a, **kw)

    def _restore_finalize(self, *a, **kw):
        return self._autorecovery_ctrl._restore_finalize(*a, **kw)

    def _apply_graph_state(self, *a, **kw):
        return self._autorecovery_ctrl._apply_graph_state(*a, **kw)

    def _setup_ipc_server(self):
        """IPC 서버 설정 - 외부 프로세스에서 앱 제어 가능"""
        self._ipc_controller.setup()

    def _update_memory_status(self):
        """상태바 메모리 사용량 업데이트"""
        try:
            proc_mem = MemoryMonitor.get_process_memory()
            sys_mem = MemoryMonitor.get_system_memory()

            proc_str = MemoryMonitor.format_memory(proc_mem['rss_mb'])
            sys_pct = sys_mem['percent']

            # 색상 결정 (메모리 사용량에 따라)
            if sys_pct > 85:
                emoji = "🔴"
            elif sys_pct > 70:
                emoji = "🟡"
            else:
                emoji = "🟢"

            self._status_memory_label.setText(f"{emoji} {proc_str} ({sys_pct:.0f}%)")
            # Memory status color is dynamic, keep minimal styling
            self._status_memory_label.setToolTip(
                f"Process Memory: {proc_str}\n"
                f"System Memory: {sys_pct:.1f}% used\n"
                f"Available: {sys_mem['available_gb']:.1f} GB"
            )
        except Exception as e:
            logger.debug("main_window.memory_status_update_failed", extra={"error": e}, exc_info=True)

    def _connect_signals(self):
        """시그널 연결"""
        # State signals (via adapter)
        self._state_adapter.data_loaded.connect(self._on_data_loaded)
        self._state_adapter.data_cleared.connect(self._on_data_cleared)
        self._state_adapter.selection_changed.connect(self._update_selection_status)
        self._state_adapter.tool_mode_changed.connect(self._on_tool_mode_changed)

        # Auto-save active profile on state changes (debounced)
        self._profile_autosave_timer = QTimer(self)
        self._profile_autosave_timer.setSingleShot(True)
        self._profile_autosave_timer.setInterval(500)  # 500ms debounce
        self._profile_autosave_timer.timeout.connect(self._autosave_active_profile)
        self._state_adapter.chart_settings_changed.connect(self._schedule_profile_autosave)
        self._state_adapter.value_zone_changed.connect(self._schedule_profile_autosave)
        self._state_adapter.group_zone_changed.connect(self._schedule_profile_autosave)

        # Panel signals - route through preview dialog
        self.table_panel.file_dropped.connect(self._show_parsing_preview)
        self.table_panel.window_changed.connect(self._on_window_changed)

        # Profile comparison controller signals (via adapter)
        self._comparison_adapter.comparison_started.connect(
            self._on_profile_comparison_started
        )
        self._comparison_adapter.comparison_ended.connect(
            self._on_profile_comparison_ended
        )

        # Streaming controller signals (routed through adapter for Qt compatibility)
        self._streaming_adapter.streaming_state_changed.connect(
            self._on_streaming_state_changed
        )
        self._streaming_adapter.data_updated.connect(
            self._on_streaming_data_updated
        )
        self._streaming_adapter.file_deleted.connect(
            self._on_streaming_file_deleted
        )

    def _setup_float_handlers(self):
        """메인 패널들의 Float 버튼 핸들러 설정"""
        # Connect float buttons for main panels
        self.summary_panel.float_btn.clicked.connect(lambda: self._float_main_panel("summary"))
        # GraphPanel은 내부적으로 float 처리
        # TablePanel도 내부적으로 float 처리

        # Create placeholders
        for key, title in [("summary", "📊 Overview"), ("graph", "📈 Graph"), ("table", "📋 Table")]:
            placeholder = QFrame()
            placeholder.setObjectName("floatPlaceholder")
            layout = QVBoxLayout(placeholder)
            layout.setAlignment(Qt.AlignCenter)
            label = QLabel(f"📤 {title}\n\nFloating as separate window\n\nClick 'Dock' to return")
            label.setObjectName("floatPlaceholderLabel")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            placeholder.hide()
            self._placeholders[key] = placeholder

    def _float_main_panel(self, *a, **kw):
        return self._view_actions_ctrl._float_main_panel(*a, **kw)

    def _dock_main_panel(self, *a, **kw):
        return self._view_actions_ctrl._dock_main_panel(*a, **kw)

    def _update_ui_state(self):
        """Update UI state with modern styling"""
        has_data = self.state.is_data_loaded

        # Update status bar
        if has_data:
            self._status_data_label.setText(f"📋 {self.state.total_rows:,} rows")
            self._status_data_label.setObjectName("successLabel")
        else:
            self._status_data_label.setText("📋 Drag & drop a file to start")
            self._status_data_label.setObjectName("hintLabel")
        self._status_data_label.style().unpolish(self._status_data_label)
        self._status_data_label.style().polish(self._status_data_label)

        # Export menu enable/disable based on data state
        self._update_export_menu_state()

    def _update_selection_status(self):
        """선택 상태 업데이트"""
        if self.state.selection.has_selection:
            count = self.state.selection.selection_count
            total = self.state.total_rows
            pct = (count / total * 100) if total > 0 else 0
            self._status_selection_label.setText(
                f"Selected: {count:,} / {total:,} ({pct:.1f}%)"
            )
        else:
            self._status_selection_label.setText("")

    # ================================================================
    # Logger — Android Logger Setup Wizard
    # ================================================================

    def _verify_capture_mode(self, *a, **kw):
        return self._trace_ctrl._verify_capture_mode(*a, **kw)

    def _run_trace(self, *a, **kw):
        return self._trace_ctrl._run_trace(*a, **kw)

    def _load_csv_async(self, *a, **kw):
        return self._trace_ctrl._load_csv_async(*a, **kw)

    def _parse_ftrace_async(self, *a, **kw):
        return self._trace_ctrl._parse_ftrace_async(*a, **kw)

    def _apply_graph_presets(self, *a, **kw):
        return self._trace_ctrl._apply_graph_presets(*a, **kw)

    def _show_new_project_wizard(self, file_path: str):
        self._file_controller._show_new_project_wizard(file_path)

    def _load_project_file(self, file_path: str):
        self._file_controller._load_project_file(file_path)

    def _show_parsing_preview(self, file_path: str):
        self._file_controller._show_parsing_preview(file_path)

    def _check_large_file_warning(self, file_path: str) -> bool:
        return self._file_controller._check_large_file_warning(file_path)

    def _cleanup_loader_thread(self):
        self._file_controller._cleanup_loader_thread()

    def _load_file(self, file_path: str, settings=None):
        self._file_controller._load_file(file_path, settings)

    def _load_file_with_settings(self, file_path: str, settings):
        self._file_controller._load_file_with_settings(file_path, settings)

    def _apply_pending_wizard_result(self):
        """마법사 결과 적용 (로딩 완료 후)"""
        if not hasattr(self, '_pending_wizard_result') or self._pending_wizard_result is None:
            return

        result = self._pending_wizard_result
        self._pending_wizard_result = None

        graph_setting = result.get('graph_setting')
        result.get('project_name')

        if graph_setting:
            active_id = self.engine.active_dataset_id
            logger.debug("active_id=%s, graph_setting=%s", active_id, graph_setting)
            if active_id:
                # 프로젝트 탐색창에 추가
                from dataclasses import replace
                graph_setting = replace(graph_setting, dataset_id=active_id)
                self.profile_store.add(graph_setting)
                self.profile_model.add_profile_incremental(active_id, graph_setting)

                # 그래프 설정 적용
                try:
                    self.profile_controller.apply_profile(graph_setting.id)
                    self._schedule_autofit()
                except Exception as e:
                    logger.warning("main_window.apply_profile_failed", extra={"error": e}, exc_info=True)

                logger.info("main_window.wizard_result_applied", extra={"graph_name": graph_setting.name})

    def _schedule_autofit(self):
        """프로파일 전환/생성 후 그래프를 자동으로 Fit (데이터에 맞춤)."""
        QTimer.singleShot(50, self._do_autofit)

    def _do_autofit(self):
        """실제 autofit 수행."""
        try:
            if hasattr(self, 'graph_panel') and self.engine.is_loaded:
                self.graph_panel.autofit()
        except Exception as e:
            logger.debug("main_window.autofit_failed", extra={"error": e}, exc_info=True)

    def _setup_quick_switch_shortcuts(self):
        """Alt+1~9로 현재 데이터셋의 n번째 프로파일로 즉시 전환"""
        for i in range(1, 10):
            shortcut = QShortcut(QKeySequence(f"Alt+{i}"), self)
            shortcut.activated.connect(lambda idx=i: self._quick_switch_profile(idx))

    def _quick_switch_profile(self, index: int):
        """Alt+N 으로 현재 데이터셋의 N번째 프로파일 적용"""
        dataset_id = self.engine.active_dataset_id if hasattr(self.engine, 'active_dataset_id') else None
        if not dataset_id:
            return
        profiles = list(self.profile_store.get_by_dataset(dataset_id)) if hasattr(self.profile_store, 'get_by_dataset') else []
        if index <= len(profiles):
            profile = profiles[index - 1]
            self.profile_controller.apply_profile(profile.id)
            self.graph_panel.refresh()
            self._schedule_autofit()
            self.statusbar.showMessage(f"[Alt+{index}] {profile.name}", 2000)

    def _cancel_loading(self):
        self._file_controller._cancel_loading()

    def _update_summary_from_profile(self):
        self._profile_ui_controller._update_summary_from_profile()

    def _schedule_profile_autosave(self):
        self._profile_ui_controller._schedule_profile_autosave()

    def _autosave_active_profile(self):
        self._profile_ui_controller._autosave_active_profile()

    def _reset_graph_view(self):
        """그래프 뷰 리셋 — Compare 뷰 활성 시 위임"""
        if self._profile_comparison_view is not None:
            if hasattr(self._profile_comparison_view, 'reset_all_views'):
                self._profile_comparison_view.reset_all_views()
                return
        self.graph_panel.reset_view()

    def _autofit_graph(self):
        """그래프 자동 맞춤 — Compare 뷰 활성 시 위임"""
        if self._profile_comparison_view is not None:
            if hasattr(self._profile_comparison_view, 'autofit'):
                self._profile_comparison_view.autofit()
                return
        self.graph_panel.autofit()

    def _show_about(self, *a, **kw):
        return self._help_ctrl._show_about(*a, **kw)

    def _show_quick_start(self, *a, **kw):
        return self._help_ctrl._show_quick_start(*a, **kw)

    def _show_tips(self, *a, **kw):
        return self._help_ctrl._show_tips(*a, **kw)

    def _show_whats_new(self, *a, **kw):
        return self._help_ctrl._show_whats_new(*a, **kw)

    def _open_url(self, *a, **kw):
        return self._help_ctrl._open_url(*a, **kw)

    def _show_profile_manager(self):
        self._profile_ui_controller._show_profile_manager()

    def _add_dataset_from_file(self, file_path: str):
        self._dataset_controller._add_dataset_from_file(file_path)

    def _load_dataset(self, file_path: str, settings: Optional[ParsingSettings] = None):
        self._dataset_controller._load_dataset(file_path, settings)

    def _load_dataset_with_settings(self, file_path: str, settings: ParsingSettings):
        self._dataset_controller._load_dataset_with_settings(file_path, settings)

    def _set_comparison_mode(self, *a, **kw):
        return self._comparison_ui_ctrl._set_comparison_mode(*a, **kw)

    def _update_comparison_mode_actions(self, *a, **kw):
        return self._comparison_ui_ctrl._update_comparison_mode_actions(*a, **kw)

    def _start_overlay_comparison(self, *a, **kw):
        return self._comparison_ui_ctrl._start_overlay_comparison(*a, **kw)

    def _show_overlay_stats_widget(self, *a, **kw):
        return self._comparison_ui_ctrl._show_overlay_stats_widget(*a, **kw)

    def _hide_overlay_stats_widget(self, *a, **kw):
        return self._comparison_ui_ctrl._hide_overlay_stats_widget(*a, **kw)

    def _show_comparison_stats_panel(self, *a, **kw):
        return self._comparison_ui_ctrl._show_comparison_stats_panel(*a, **kw)

    def _start_side_by_side_comparison(self, *a, **kw):
        return self._comparison_ui_ctrl._start_side_by_side_comparison(*a, **kw)

    def _start_difference_analysis(self, *a, **kw):
        return self._comparison_ui_ctrl._start_difference_analysis(*a, **kw)

    def _show_comparison_view(self, *a, **kw):
        return self._comparison_ui_ctrl._show_comparison_view(*a, **kw)

    def _remove_comparison_view(self, *a, **kw):
        return self._comparison_ui_ctrl._remove_comparison_view(*a, **kw)

    def _restore_single_view(self, *a, **kw):
        return self._comparison_ui_ctrl._restore_single_view(*a, **kw)

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
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox
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

    def _update_draw_color_btn(self, *a, **kw):
        return self._view_actions_ctrl._update_draw_color_btn(*a, **kw)

    def _activate_dashboard_mode(self, *a, **kw):
        return self._view_actions_ctrl._activate_dashboard_mode(*a, **kw)

    def _deactivate_dashboard_mode(self, *a, **kw):
        return self._view_actions_ctrl._deactivate_dashboard_mode(*a, **kw)

    def _update_export_menu_state(self, *a, **kw):
        return self._menu_setup_ctrl._update_export_menu_state(*a, **kw)

    def _capture_graph_image(self, *a, **kw):
        return self._export_ui_ctrl._capture_graph_image(*a, **kw)

    def _auto_check_updates(self, *a, **kw):
        return self._help_ctrl._auto_check_updates(*a, **kw)

    def _restore_saved_theme(self, *a, **kw):
        return self._view_actions_ctrl._restore_saved_theme(*a, **kw)

    def _wire_shortcut_callbacks(self):
        """Connect ShortcutController callbacks to MainWindow actions"""
        sc = self._shortcut_controller
        sc.connect("file.open", self._on_open_file)
        sc.connect("file.save", self._on_save_project_file)
        sc.connect("file.export", self._on_export_dialog)
        sc.connect("edit.undo", self._on_undo)
        sc.connect("edit.redo", self._on_redo)
        sc.connect("edit.annotation_mode", self._on_toggle_annotation_panel)
        sc.connect("view.dashboard_toggle", self._on_toggle_dashboard_mode)
        sc.connect("view.theme_toggle", self._on_cycle_theme)
        sc.connect("view.annotation_panel", self._on_toggle_annotation_panel)
        sc.connect("help.shortcuts", self._show_shortcuts_dialog)
