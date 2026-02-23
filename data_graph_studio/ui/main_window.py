"""
Main Window - 메인 윈도우 및 레이아웃
"""

import logging
from typing import Optional

from PySide6.QtWidgets import QMainWindow
from PySide6.QtCore import QTimer

from ..core.data_engine import DataEngine
from ..core.state import AppState
from ..core.streaming_controller import StreamingController
from ..core.io_abstract import RealFileSystem
from .adapters.streaming_adapter import StreamingControllerAdapter
from .adapters.profile_comparison_adapter import ProfileComparisonControllerAdapter
from .adapters.app_state_adapter import AppStateAdapter
from ..core.undo_manager import UndoStack
from ..core.dashboard_controller import DashboardController
from ..core.annotation_controller import AnnotationController
from .controllers.shortcut_controller import ShortcutController
from ..core.export_controller import ExportController
from .adapters.export_controller_adapter import ExportControllerAdapter
from .renderers.qt_export_renderer import QtExportRenderer
from ..core.parsing import ParsingSettings
from ..core.profile_store import ProfileStore
from ..core.profile_controller import ProfileController
from ..core.profile_comparison_controller import ProfileComparisonController
from .panels.comparison_stats_panel import ComparisonStatsPanel
from .panels.overlay_stats_widget import OverlayStatsWidget
from .panels.side_by_side_layout import SideBySideLayout
from .panels.dashboard_panel import DashboardPanel
from .panels.annotation_panel import AnnotationPanel

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


from ._qt_timer_factory import _QtTimerFactory  # noqa: F401
from ._main_window_ipc_mixin import _MainWindowIpcMixin
from ._main_window_actions_mixin import _MainWindowActionsMixin
from ._main_window_events_mixin import _MainWindowEventsMixin
from ._main_window_layout_mixin import _MainWindowLayoutMixin


class MainWindow(_MainWindowIpcMixin, _MainWindowActionsMixin, _MainWindowEventsMixin, _MainWindowLayoutMixin, QMainWindow):
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

        self._history_panel = None
        self._history_dock = None

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
        self._export_controller = ExportController(renderer=QtExportRenderer())
        self._export_controller_adapter = ExportControllerAdapter(self._export_controller, parent=self)

        # Loading thread
        self._loader_thread: Optional[DataLoaderThread] = None

        # Float windows tracking
        self._float_windows: dict = {}
        self._placeholders: dict = {}

        # Comparison view panels
        self._side_by_side_layout: Optional[SideBySideLayout] = None
        self._comparison_stats_panel: Optional[ComparisonStatsPanel] = None
        self._current_comparison_view = None
        self._overlay_stats_widget: Optional[OverlayStatsWidget] = None
        self._profile_comparison_view = None

        # Floating graph manager (set during _setup_main_layout)
        self._floating_graph_manager = None

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

    # ================================================================
    # Delegating facades — controller dispatch
    # ================================================================

    def _setup_menubar(self, *a, **kw):
        return self._menu_setup_ctrl._setup_menubar(*a, **kw)

    def _setup_toolbar(self, *a, **kw):
        return self._toolbar_ctrl._setup_toolbar(*a, **kw)

    def _setup_streaming_toolbar(self, *a, **kw):
        return self._toolbar_ctrl._setup_streaming_toolbar(*a, **kw)

    def _setup_compare_toolbar(self, *a, **kw):
        return self._toolbar_ctrl._setup_compare_toolbar(*a, **kw)

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

    def _float_main_panel(self, *a, **kw):
        return self._view_actions_ctrl._float_main_panel(*a, **kw)

    def _dock_main_panel(self, *a, **kw):
        return self._view_actions_ctrl._dock_main_panel(*a, **kw)

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

    def _cancel_loading(self):
        self._file_controller._cancel_loading()

    def _update_summary_from_profile(self):
        self._profile_ui_controller._update_summary_from_profile()

    def _schedule_profile_autosave(self):
        self._profile_ui_controller._schedule_profile_autosave()

    def _autosave_active_profile(self):
        self._profile_ui_controller._autosave_active_profile()

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
