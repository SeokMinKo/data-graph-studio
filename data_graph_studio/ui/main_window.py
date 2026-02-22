"""
Main Window - 메인 윈도우 및 레이아웃
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional, List

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QFileDialog, QMessageBox,
    QApplication, QLabel, QFrame,
    QInputDialog, QTabWidget, QDockWidget,
    QLineEdit
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut

from ..core.data_engine import DataEngine
from ..core.state import AppState, ChartType
from .clipboard_manager import ClipboardManager, DragDropHandler
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


class _QtTimerWrapper:
    """Wraps QTimer to match the start/stop interface expected by FileWatcher."""
    def __init__(self, interval_ms: int, callback):
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(callback)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()


class _QtTimerFactory(ITimerFactory):
    """Production timer factory using PySide6 QTimer."""
    def create_timer(self, interval_ms: int, callback):
        return _QtTimerWrapper(interval_ms, callback)


class MainWindow(QMainWindow):
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
            pass

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
    
    # ==================== IPC Delegates (-> IPCController) ====================
    # These delegate methods maintain backward compatibility for tests that
    # call _ipc_* methods directly on MainWindow / mock stand-ins.

    def _ipc_get_state(self, *a, **kw):
        return self._ipc_controller._ipc_get_state(*a, **kw)

    def _ipc_get_data_info(self, *a, **kw):
        return self._ipc_controller._ipc_get_data_info(*a, **kw)

    def _ipc_set_chart_type(self, *a, **kw):
        return self._ipc_controller._ipc_set_chart_type(*a, **kw)

    def _ipc_set_columns(self, *a, **kw):
        return self._ipc_controller._ipc_set_columns(*a, **kw)

    def _ipc_load_file(self, *a, **kw):
        return self._ipc_controller._ipc_load_file(*a, **kw)

    def _ipc_get_panels(self, *a, **kw):
        return self._ipc_controller._ipc_get_panels(*a, **kw)

    def _ipc_get_summary(self, *a, **kw):
        return self._ipc_controller._ipc_get_summary(*a, **kw)

    def _ipc_execute(self, *a, **kw):
        return self._ipc_controller._ipc_execute(*a, **kw)

    def _ipc_set_x_column(self, *a, **kw):
        return self._ipc_controller._ipc_set_x_column(*a, **kw)

    def _ipc_set_value_columns(self, *a, **kw):
        return self._ipc_controller._ipc_set_value_columns(*a, **kw)

    def _ipc_set_group_columns(self, *a, **kw):
        return self._ipc_controller._ipc_set_group_columns(*a, **kw)

    def _ipc_set_hover_columns(self, *a, **kw):
        return self._ipc_controller._ipc_set_hover_columns(*a, **kw)

    def _ipc_clear_all_zones(self, *a, **kw):
        return self._ipc_controller._ipc_clear_all_zones(*a, **kw)

    def _ipc_get_zones(self, *a, **kw):
        return self._ipc_controller._ipc_get_zones(*a, **kw)

    def _ipc_set_theme(self, *a, **kw):
        return self._ipc_controller._ipc_set_theme(*a, **kw)

    def _ipc_refresh(self, *a, **kw):
        return self._ipc_controller._ipc_refresh(*a, **kw)

    def _ipc_get_screenshot(self, *a, **kw):
        return self._ipc_controller._ipc_get_screenshot(*a, **kw)

    def _ipc_set_agg(self, *a, **kw):
        return self._ipc_controller._ipc_set_agg(*a, **kw)

    def _ipc_list_profiles(self, *a, **kw):
        return self._ipc_controller._ipc_list_profiles(*a, **kw)

    def _ipc_create_profile(self, *a, **kw):
        return self._ipc_controller._ipc_create_profile(*a, **kw)

    def _ipc_apply_profile(self, *a, **kw):
        return self._ipc_controller._ipc_apply_profile(*a, **kw)

    def _ipc_delete_profile(self, *a, **kw):
        return self._ipc_controller._ipc_delete_profile(*a, **kw)

    def _ipc_duplicate_profile(self, *a, **kw):
        return self._ipc_controller._ipc_duplicate_profile(*a, **kw)

    def _ipc_start_profile_comparison(self, *a, **kw):
        return self._ipc_controller._ipc_start_profile_comparison(*a, **kw)

    def _ipc_stop_profile_comparison(self, *a, **kw):
        return self._ipc_controller._ipc_stop_profile_comparison(*a, **kw)

    def _ipc_get_profile_comparison_state(self, *a, **kw):
        return self._ipc_controller._ipc_get_profile_comparison_state(*a, **kw)

    def _ipc_set_comparison_sync(self, *a, **kw):
        return self._ipc_controller._ipc_set_comparison_sync(*a, **kw)

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
            logger.debug("main_window.memory_status_update_failed", extra={"error": e})
    
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
    
    # ==================== Actions ====================
    
    # ==================== File Loading Delegates (-> FileLoadingController) ====================

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
        from pathlib import Path
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

    # ================================================================
    # Logger — Android Logger Setup Wizard
    # ================================================================

    def _on_configure_trace(self, *a, **kw):
        return self._trace_ctrl._on_configure_trace(*a, **kw)

    def _on_start_trace(self, *a, **kw):
        return self._trace_ctrl._on_start_trace(*a, **kw)

    def _on_compare_traces(self, *a, **kw):
        return self._trace_ctrl._on_compare_traces(*a, **kw)

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

    def _on_open_file(self):
        self._file_controller._on_open_file()

    def _on_load_sample_data(self):
        self._file_controller._on_load_sample_data()

    def _on_open_file_without_wizard(self):
        self._file_controller._on_open_file_without_wizard()

    def _show_new_project_wizard(self, file_path: str):
        self._file_controller._show_new_project_wizard(file_path)

    def _on_wizard_project_created(self, result: dict):
        self._file_controller._on_wizard_project_created(result)

    def _load_project_file(self, file_path: str):
        self._file_controller._load_project_file(file_path)

    def _on_open_multiple_files(self):
        self._file_controller._on_open_multiple_files()

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

    def _on_loading_progress(self, progress):
        self._file_controller._on_loading_progress(progress)

    def _on_loading_finished(self, success: bool):
        self._file_controller._on_loading_finished(success)
    
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
                
                logger.info("main_window.wizard_result_applied", extra={"name": graph_setting.name})

    def _schedule_autofit(self):
        """프로파일 전환/생성 후 그래프를 자동으로 Fit (데이터에 맞춤)."""
        QTimer.singleShot(50, self._do_autofit)

    def _do_autofit(self):
        """실제 autofit 수행."""
        try:
            if hasattr(self, 'graph_panel') and self.engine.is_loaded:
                self.graph_panel.autofit()
        except Exception as e:
            logger.debug("main_window.autofit_failed", extra={"error": e})

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
    
    def _update_summary_from_profile(self):
        self._profile_ui_controller._update_summary_from_profile()

    def _schedule_profile_autosave(self):
        self._profile_ui_controller._schedule_profile_autosave()

    def _autosave_active_profile(self):
        self._profile_ui_controller._autosave_active_profile()

    def _on_tool_mode_changed(self):
        """툴 모드 변경"""
        mode = self.state.tool_mode
        for m, action in self._tool_actions.items():
            action.setChecked(m == mode)

        # Delegate tool mode to Compare view panels
        if self._profile_comparison_view is not None:
            if hasattr(self._profile_comparison_view, 'set_tool_mode'):
                self._profile_comparison_view.set_tool_mode(mode)
    
    def _reset_graph_view(self):
        """그래프 뷰 리셋 — Compare 뷰 활성 시 위임"""
        if self._profile_comparison_view is not None:
            if hasattr(self._profile_comparison_view, 'reset_all_views'):
                self._profile_comparison_view.reset_all_views()
                return
        self.graph_panel.reset_view()

    def _on_clear_selection(self):
        """Clear selection and highlight"""
        self.state.clear_selection()
        if hasattr(self, 'graph_panel') and self.graph_panel is not None:
            self.graph_panel.main_graph.highlight_selection([])
    
    def _autofit_graph(self):
        """그래프 자동 맞춤 — Compare 뷰 활성 시 위임"""
        if self._profile_comparison_view is not None:
            if hasattr(self._profile_comparison_view, 'autofit'):
                self._profile_comparison_view.autofit()
                return
        self.graph_panel.autofit()
    
    def _on_export(self, *a, **kw):
        return self._export_ui_ctrl._on_export(*a, **kw)

    def _show_about(self, *a, **kw):
        return self._help_ctrl._show_about(*a, **kw)

    def _show_quick_start(self, *a, **kw):
        return self._help_ctrl._show_quick_start(*a, **kw)

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
    
    def _show_tips(self, *a, **kw):
        return self._help_ctrl._show_tips(*a, **kw)

    def _show_whats_new(self, *a, **kw):
        return self._help_ctrl._show_whats_new(*a, **kw)

    def _open_url(self, *a, **kw):
        return self._help_ctrl._open_url(*a, **kw)

    def _on_new_profile_menu(self):
        self._profile_ui_controller._on_new_profile_menu()


    def _on_load_profile_menu(self):
        self._profile_ui_controller._on_load_profile_menu()


    def _on_save_profile_menu(self):
        self._profile_ui_controller._on_save_profile_menu()


    # ==================== Profile Actions ====================

    def _on_profile_setting_clicked(self, setting_id: str):
        self._profile_ui_controller._on_profile_setting_clicked(setting_id)


    def _on_profile_setting_double_clicked(self, setting_id: str):
        self._profile_ui_controller._on_profile_setting_double_clicked(setting_id)


    def _on_add_setting_requested(self):
        self._profile_ui_controller._on_add_setting_requested()


    def _on_compare_profiles_requested(self):
        self._profile_ui_controller._on_compare_profiles_requested()


    def _show_profile_manager(self):
        self._profile_ui_controller._show_profile_manager()


    # ==================== Project Explorer Actions ====================

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


    # ==================== Multi-Dataset Operations ====================

    def _on_add_dataset(self):
        self._dataset_controller._on_add_dataset()


    def _add_dataset_from_file(self, file_path: str):
        self._dataset_controller._add_dataset_from_file(file_path)


    def _load_dataset(self, file_path: str, settings: Optional[ParsingSettings] = None):
        self._dataset_controller._load_dataset(file_path, settings)


    def _load_dataset_with_settings(self, file_path: str, settings: ParsingSettings):
        self._dataset_controller._load_dataset_with_settings(file_path, settings)


    def _on_dataset_loading_finished(self, success: bool):
        self._dataset_controller._on_dataset_loading_finished(success)


    def _on_dataset_activated(self, dataset_id: str):
        self._dataset_controller._on_dataset_activated(dataset_id)


    def _on_dataset_remove_requested(self, dataset_id: str):
        self._dataset_controller._on_dataset_remove_requested(dataset_id)


    def _set_comparison_mode(self, *a, **kw):
        return self._comparison_ui_ctrl._set_comparison_mode(*a, **kw)

    def _update_comparison_mode_actions(self, *a, **kw):
        return self._comparison_ui_ctrl._update_comparison_mode_actions(*a, **kw)

    def _on_comparison_mode_changed(self, *a, **kw):
        return self._comparison_ui_ctrl._on_comparison_mode_changed(*a, **kw)

    def _on_comparison_started(self, *a, **kw):
        return self._comparison_ui_ctrl._on_comparison_started(*a, **kw)

    def _start_overlay_comparison(self, *a, **kw):
        return self._comparison_ui_ctrl._start_overlay_comparison(*a, **kw)

    def _show_overlay_stats_widget(self, *a, **kw):
        return self._comparison_ui_ctrl._show_overlay_stats_widget(*a, **kw)

    def _hide_overlay_stats_widget(self, *a, **kw):
        return self._comparison_ui_ctrl._hide_overlay_stats_widget(*a, **kw)

    def _show_comparison_stats_panel(self, *a, **kw):
        return self._comparison_ui_ctrl._show_comparison_stats_panel(*a, **kw)

    def _on_export_comparison_report(self, *a, **kw):
        return self._comparison_ui_ctrl._on_export_comparison_report(*a, **kw)

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
                    self.statusBar().showMessage(f"Export error: {e}", 3000)
        except Exception as e:
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
            self.statusBar().showMessage(f"Copy error: {e}", 3000)

    # ==================== New Menu Actions ====================

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
            pass

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

    # ============================================================
    # New Menu Action Methods (File Menu)
    # ============================================================

    # ------ Profile / Project file actions (File menu) ------

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
                QMessageBox.warning(self, "Save Data As", f"Failed to save: {e}")

    def _on_import_data(self):
        """Import - 데이터 임포트"""
        # 다양한 소스에서 데이터 가져오기
        self._file_controller._on_import_data()

    # ============================================================
    # New Menu Action Methods (View Menu - Graph Elements)
    # ============================================================

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

    def _update_draw_color_btn(self, *a, **kw):
        return self._view_actions_ctrl._update_draw_color_btn(*a, **kw)

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
                    QMessageBox.warning(self, "Remove Field", f"Failed to remove column: {e}")

    # ============================================================
    # New Menu Action Methods (Graph Menu - Options)
    # ============================================================

    def _on_axis_settings(self, *a, **kw):
        return self._view_actions_ctrl._on_axis_settings(*a, **kw)

    def _on_toggle_dashboard_mode(self, *a, **kw):
        return self._view_actions_ctrl._on_toggle_dashboard_mode(*a, **kw)

    def _activate_dashboard_mode(self, *a, **kw):
        return self._view_actions_ctrl._activate_dashboard_mode(*a, **kw)

    def _deactivate_dashboard_mode(self, *a, **kw):
        return self._view_actions_ctrl._deactivate_dashboard_mode(*a, **kw)

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

    def _update_export_menu_state(self, *a, **kw):
        return self._menu_setup_ctrl._update_export_menu_state(*a, **kw)

    def _on_export_dialog(self, *a, **kw):
        return self._export_ui_ctrl._on_export_dialog(*a, **kw)

    def _on_export_image(self, *a, **kw):
        return self._export_ui_ctrl._on_export_image(*a, **kw)

    def _on_export_data(self, *a, **kw):
        return self._export_ui_ctrl._on_export_data(*a, **kw)

    def _capture_graph_image(self, *a, **kw):
        return self._export_ui_ctrl._capture_graph_image(*a, **kw)

    def _auto_check_updates(self, *a, **kw):
        return self._help_ctrl._auto_check_updates(*a, **kw)

    def _restore_saved_theme(self, *a, **kw):
        return self._view_actions_ctrl._restore_saved_theme(*a, **kw)

    def _on_cycle_theme(self, *a, **kw):
        return self._view_actions_ctrl._on_cycle_theme(*a, **kw)

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
