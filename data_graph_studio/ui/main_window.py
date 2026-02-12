"""
Main Window - 메인 윈도우 및 레이아웃
"""

import os
import gc
import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional, List, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QMenu, QToolBar, QStatusBar, QFileDialog, QMessageBox,
    QProgressDialog, QApplication, QLabel, QDialog, QFrame,
    QInputDialog, QTabWidget, QColorDialog, QPushButton, QDockWidget
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QColor

from ..core.data_engine import DataEngine, LoadingProgress, FileType, DelimiterType
from ..core.state import AppState, ToolMode, ChartType, ComparisonMode, AggregationType
from ..core.comparison_report import ComparisonReport
from ..core.ipc_server import IPCServer
from ..core.clipboard_manager import ClipboardManager, DragDropHandler
from ..core.streaming_controller import StreamingController
from ..core.io_abstract import RealFileSystem, ITimerFactory
from ..core.undo_manager import UndoStack
from .panels.history_panel import HistoryPanel
from ..core.dashboard_controller import DashboardController
from ..core.annotation_controller import AnnotationController
from ..core.shortcut_controller import ShortcutController
from ..core.export_controller import ExportController, ExportFormat
from ..utils.memory import MemoryMonitor
from ..core.updater import (
    get_current_version,
    check_github_latest,
    is_update_available,
    download_asset,
    read_sha256_file,
    sha256sum,
    run_windows_installer,
)

# 에러 로깅 설정
logger = logging.getLogger(__name__)

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
from .dialogs.parsing_preview_dialog import ParsingPreviewDialog
from .dialogs.computed_column_dialog import ComputedColumnDialog
from ..core.parsing import ParsingSettings
from .dialogs.save_setting_dialog import SaveSettingDialog
from .dialogs.streaming_dialog import StreamingDialog
from .dialogs.command_palette_dialog import CommandPaletteDialog
from .dialogs.profile_manager_dialog import ProfileManagerDialog
from .dialogs.multi_file_dialog import open_multi_file_dialog
from .floatable import FloatWindow
from .floating_graph import FloatingGraphWindow, FloatingGraphManager
from ..core.profile import Profile, GraphSetting, ProfileManager
from ..core.profile_store import ProfileStore
from ..core.profile_controller import ProfileController
from ..core.profile_comparison_controller import ProfileComparisonController
from .models.profile_model import ProfileModel
from .panels.profile_side_by_side import ProfileSideBySideLayout
from .panels.profile_overlay import ProfileOverlayRenderer
from .panels.profile_difference import ProfileDifferenceRenderer
from .toolbars.compare_toolbar import CompareToolbar
from .views.project_tree_view import ProjectTreeView
from .wizards.new_project_wizard import NewProjectWizard

# Controllers (extracted from MainWindow)
from .controllers.ipc_controller import IPCController
from .controllers.file_loading_controller import (
    FileLoadingController, DataLoaderThread, DataLoaderThreadWithSettings,
)
from .controllers.dataset_controller import DatasetController
from .controllers.profile_ui_controller import ProfileUIController


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
        
        # Profile management (Project Explorer)
        self.profile_store = ProfileStore()
        self.profile_controller = ProfileController(self.profile_store, self.state)
        self.profile_comparison_controller = ProfileComparisonController(
            self.profile_store, self.profile_controller, self.state,
        )

        # Streaming controller
        self._streaming_controller = StreamingController(
            fs=RealFileSystem(),
            timer_factory=_QtTimerFactory(),
            parent=self,
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
        self._export_controller = ExportController(parent=self)

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

        # Restore saved theme or default to midnight
        self._restore_saved_theme()

        # Apply initial state
        self._update_ui_state()

        # Auto-update (Windows)
        QTimer.singleShot(2000, self._auto_check_updates)
    
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
    
    def _setup_menubar(self):
        """메뉴바 설정 - 새 구조"""
        menubar = self.menuBar()
        # Style handled by global theme stylesheet

        # ============================================================
        # File Menu
        # ============================================================
        file_menu = menubar.addMenu("&File")

        # Open Data (with wizard)
        open_data_action = QAction("Open &Data...", self)
        open_data_action.setShortcut(QKeySequence.Open)
        open_data_action.setStatusTip("Open data file with New Project Wizard (Ctrl+O)")
        open_data_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_data_action)

        # Open Data Without Wizard
        open_no_wizard_action = QAction("Open Without &Wizard...", self)
        open_no_wizard_action.setShortcut("Ctrl+Shift+O")
        open_no_wizard_action.setStatusTip("Open data file without wizard - quick mode (Ctrl+Shift+O)")
        open_no_wizard_action.triggered.connect(self._on_open_file_without_wizard)
        file_menu.addAction(open_no_wizard_action)

        # Open Profile
        open_profile_action = QAction("Open &Profile...", self)
        open_profile_action.setShortcut("Ctrl+Alt+O")
        open_profile_action.setStatusTip("Load a saved profile file (Ctrl+Alt+O)")
        open_profile_action.triggered.connect(self._on_open_profile)
        file_menu.addAction(open_profile_action)

        # Open Project
        open_project_action = QAction("Open Pro&ject...", self)
        open_project_action.setShortcut("Ctrl+Alt+P")
        open_project_action.setStatusTip("Load a DGS project file (Ctrl+Alt+P)")
        open_project_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_project_action)

        file_menu.addSeparator()

        # Save Data
        save_data_action = QAction("Save Data", self)
        save_data_action.setShortcut(QKeySequence.Save)
        save_data_action.setStatusTip("Save current data (Ctrl+S)")
        save_data_action.triggered.connect(self._on_save_data)
        file_menu.addAction(save_data_action)

        # Save Data As
        save_data_as_action = QAction("Save Data As...", self)
        save_data_as_action.setShortcut("Ctrl+Shift+S")
        save_data_as_action.setStatusTip("Save current data to a new file")
        save_data_as_action.triggered.connect(self._on_save_data_as)
        file_menu.addAction(save_data_as_action)

        # Save Profile
        save_profile_action = QAction("Save Profile", self)
        save_profile_action.setStatusTip("Save active profile to last path")
        save_profile_action.triggered.connect(self._on_save_profile_file)
        file_menu.addAction(save_profile_action)

        # Save Profile As
        save_profile_as_action = QAction("Save Profile As...", self)
        save_profile_as_action.setStatusTip("Save active profile to a new file")
        save_profile_as_action.triggered.connect(self._on_save_profile_file_as)
        file_menu.addAction(save_profile_as_action)

        # Save Project
        save_project_action = QAction("Save Project", self)
        save_project_action.setShortcut("Ctrl+Alt+S")
        save_project_action.setStatusTip("Save project with profiles (Ctrl+Alt+S)")
        save_project_action.triggered.connect(self._on_save_project_file)
        file_menu.addAction(save_project_action)

        # Save Project As
        save_project_as_action = QAction("Save Project As...", self)
        save_project_as_action.setStatusTip("Save project with profiles to a new file")
        save_project_as_action.triggered.connect(self._on_save_project_file_as)
        file_menu.addAction(save_project_as_action)

        file_menu.addSeparator()

        # Save Profile Bundle As
        save_bundle_as_action = QAction("Save Profile Bundle As...", self)
        save_bundle_as_action.setStatusTip("Save all profiles as a bundle file")
        save_bundle_as_action.triggered.connect(self._on_save_profile_bundle_as)
        file_menu.addAction(save_bundle_as_action)

        file_menu.addSeparator()

        # Export submenu
        export_menu = file_menu.addMenu("&Export")

        # Export Image (PNG/SVG)
        self._export_image_png_action = QAction("Image (PNG)...", self)
        self._export_image_png_action.setStatusTip("Export chart as PNG image")
        self._export_image_png_action.triggered.connect(lambda: self._on_export_image(ExportFormat.PNG))
        export_menu.addAction(self._export_image_png_action)

        self._export_image_svg_action = QAction("Image (SVG)...", self)
        self._export_image_svg_action.setStatusTip("Export chart as SVG image")
        self._export_image_svg_action.triggered.connect(lambda: self._on_export_image(ExportFormat.SVG))
        export_menu.addAction(self._export_image_svg_action)

        export_menu.addSeparator()

        # Export Data
        self._export_data_csv_action = QAction("Data (CSV)...", self)
        self._export_data_csv_action.setStatusTip("Export data as CSV")
        self._export_data_csv_action.triggered.connect(lambda: self._on_export_data(ExportFormat.CSV))
        export_menu.addAction(self._export_data_csv_action)

        self._export_data_excel_action = QAction("Data (Excel)...", self)
        self._export_data_excel_action.setStatusTip("Export data as Excel")
        self._export_data_excel_action.triggered.connect(lambda: self._on_export_data(ExportFormat.EXCEL))
        export_menu.addAction(self._export_data_excel_action)

        self._export_data_parquet_action = QAction("Data (Parquet)...", self)
        self._export_data_parquet_action.setStatusTip("Export data as Parquet")
        self._export_data_parquet_action.triggered.connect(lambda: self._on_export_data(ExportFormat.PARQUET))
        export_menu.addAction(self._export_data_parquet_action)

        export_menu.addSeparator()

        # Export Report
        self._export_report_html_action = QAction("Report (HTML)...", self)
        self._export_report_html_action.setStatusTip("Export report as HTML")
        self._export_report_html_action.triggered.connect(self._on_export_report)
        export_menu.addAction(self._export_report_html_action)

        self._export_report_pptx_action = QAction("Report (PPTX)...", self)
        self._export_report_pptx_action.setStatusTip("Export report as PowerPoint")
        self._export_report_pptx_action.triggered.connect(self._on_export_report)
        export_menu.addAction(self._export_report_pptx_action)

        export_menu.addSeparator()

        # Quick Export (Ctrl+E)
        self._export_quick_action = QAction("Export...", self)
        self._export_quick_action.setShortcut("Ctrl+E")
        self._export_quick_action.setStatusTip("Open export dialog (Ctrl+E)")
        self._export_quick_action.triggered.connect(self._on_export_dialog)
        export_menu.addAction(self._export_quick_action)

        # Keep legacy report action for backward compat
        export_report_action = QAction("Export &Report (Legacy)...", self)
        export_report_action.setShortcut("Ctrl+R")
        export_report_action.setStatusTip("Export data and charts as a report")
        export_report_action.triggered.connect(self._on_export_report)
        file_menu.addAction(export_report_action)

        # Import
        import_action = QAction("&Import...", self)
        import_action.setShortcut("Ctrl+I")
        import_action.setStatusTip("Import data from various sources")
        import_action.triggered.connect(self._on_import_data)
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        # Recent Files submenu
        self._recent_files_menu = file_menu.addMenu("Recent Files")
        self._recent_files_menu.setStatusTip("Recently opened files")
        self._update_recent_files_menu()

        file_menu.addSeparator()

        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.setStatusTip("Exit application (Ctrl+Q)")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ============================================================
        # View Menu
        # ============================================================
        view_menu = menubar.addMenu("&View")

        # View actions dict (for settings apply compatibility)
        self._view_actions = {}

        # Graph Elements submenu
        graph_elements_menu = view_menu.addMenu("&Graph Elements")
        
        self._graph_element_actions = {}
        
        float_graph_action = QAction("Float Graph Panel", self)
        float_graph_action.setStatusTip("Float the graph panel into a separate window")
        float_graph_action.triggered.connect(lambda: self._float_main_panel("graph"))
        graph_elements_menu.addAction(float_graph_action)
        graph_elements_menu.addSeparator()
        
        legend_action = QAction("Legend", self)
        legend_action.setToolTip("Toggle chart legend visibility")
        legend_action.setCheckable(True)
        legend_action.setChecked(True)
        legend_action.triggered.connect(self._on_toggle_legend)
        graph_elements_menu.addAction(legend_action)
        self._graph_element_actions["legend"] = legend_action
        self._show_legend_action = legend_action
        
        grid_action = QAction("Grid", self)
        grid_action.setToolTip("Toggle chart grid lines")
        grid_action.setCheckable(True)
        grid_action.setChecked(True)
        grid_action.triggered.connect(self._on_toggle_grid)
        graph_elements_menu.addAction(grid_action)
        self._graph_element_actions["grid"] = grid_action
        self._show_grid_action = grid_action
        
        statistics_overlay_action = QAction("Statistics Overlay", self)
        statistics_overlay_action.setToolTip("Show statistics overlay on chart")
        statistics_overlay_action.setCheckable(True)
        statistics_overlay_action.setChecked(False)
        statistics_overlay_action.triggered.connect(self._on_toggle_statistics_overlay)
        graph_elements_menu.addAction(statistics_overlay_action)
        self._graph_element_actions["statistics_overlay"] = statistics_overlay_action
        
        axis_labels_action = QAction("Axis Labels", self)
        axis_labels_action.setToolTip("Toggle axis labels on chart")
        axis_labels_action.setCheckable(True)
        axis_labels_action.setChecked(True)
        axis_labels_action.triggered.connect(self._on_toggle_axis_labels)
        graph_elements_menu.addAction(axis_labels_action)
        self._graph_element_actions["axis_labels"] = axis_labels_action

        graph_elements_menu.addSeparator()
        drawing_style_action = QAction("Drawing Style...", self)
        drawing_style_action.setToolTip("Configure drawing tool style")
        drawing_style_action.triggered.connect(self._on_drawing_style)
        graph_elements_menu.addAction(drawing_style_action)

        delete_drawing_action = QAction("Delete Selected Drawing", self)
        delete_drawing_action.setToolTip("Delete the currently selected drawing (Delete)")
        # Shortcut handled in keyPressEvent to avoid text input conflicts
        delete_drawing_action.triggered.connect(self._on_delete_drawing)
        graph_elements_menu.addAction(delete_drawing_action)
        self._delete_drawing_action = delete_drawing_action

        clear_drawings_action = QAction("Clear All Drawings", self)
        clear_drawings_action.setToolTip("Remove all drawings from the chart")
        clear_drawings_action.triggered.connect(self._on_clear_drawings)
        graph_elements_menu.addAction(clear_drawings_action)

        # Table Elements submenu
        table_elements_menu = view_menu.addMenu("&Table Elements")
        
        self._table_element_actions = {}
        
        float_table_action = QAction("Float Table Panel", self)
        float_table_action.setStatusTip("Float the table panel into a separate window")
        float_table_action.triggered.connect(lambda: self._float_main_panel("table"))
        table_elements_menu.addAction(float_table_action)
        table_elements_menu.addSeparator()
        
        row_numbers_action = QAction("Row Numbers", self)
        row_numbers_action.setToolTip("Show or hide row numbers in table")
        row_numbers_action.setCheckable(True)
        row_numbers_action.setChecked(True)
        row_numbers_action.triggered.connect(self._on_toggle_row_numbers)
        table_elements_menu.addAction(row_numbers_action)
        self._table_element_actions["row_numbers"] = row_numbers_action
        
        column_headers_action = QAction("Column Headers", self)
        column_headers_action.setToolTip("Show or hide column headers in table")
        column_headers_action.setCheckable(True)
        column_headers_action.setChecked(True)
        column_headers_action.triggered.connect(self._on_toggle_column_headers)
        table_elements_menu.addAction(column_headers_action)
        self._table_element_actions["column_headers"] = column_headers_action
        
        filter_bar_action = QAction("Filter Bar", self)
        filter_bar_action.setToolTip("Show or hide table filter bar")
        filter_bar_action.setCheckable(True)
        filter_bar_action.setChecked(False)
        filter_bar_action.triggered.connect(self._on_toggle_filter_bar)
        table_elements_menu.addAction(filter_bar_action)
        self._table_element_actions["filter_bar"] = filter_bar_action

        view_menu.addSeparator()

        # Multi-Grid View
        multi_grid_action = QAction("&Multi-Grid View", self)
        multi_grid_action.setShortcut("Ctrl+M")
        multi_grid_action.setStatusTip("Display multiple graphs in a grid layout")
        multi_grid_action.triggered.connect(self._on_multi_grid_view)
        view_menu.addAction(multi_grid_action)

        view_menu.addSeparator()

        # ===== v2 Feature Menu Items =====

        # Feature 1: Dashboard Mode
        self._dashboard_mode_action = QAction("&Dashboard Mode", self)
        self._dashboard_mode_action.setShortcut("Ctrl+D")
        self._dashboard_mode_action.setStatusTip("Toggle dashboard mode with multiple chart cells (Ctrl+D)")
        self._dashboard_mode_action.setCheckable(True)
        self._dashboard_mode_action.triggered.connect(self._on_toggle_dashboard_mode)
        view_menu.addAction(self._dashboard_mode_action)

        # Feature 5: Annotation Panel
        self._annotation_panel_action = QAction("&Annotations Panel", self)
        self._annotation_panel_action.setShortcut("Ctrl+Shift+A")
        self._annotation_panel_action.setStatusTip("Toggle annotations side panel (Ctrl+Shift+A)")
        self._annotation_panel_action.setCheckable(True)
        self._annotation_panel_action.triggered.connect(self._on_toggle_annotation_panel)
        view_menu.addAction(self._annotation_panel_action)

        # Add Annotation
        self._add_annotation_action = QAction("Add A&nnotation", self)
        self._add_annotation_action.setShortcut("Ctrl+Shift+N")
        self._add_annotation_action.setStatusTip("Add a new annotation to the chart (Ctrl+Shift+N)")
        self._add_annotation_action.triggered.connect(self._on_add_annotation)
        view_menu.addAction(self._add_annotation_action)

        view_menu.addSeparator()

        # Theme submenu
        theme_menu = view_menu.addMenu("&Theme")
        self._theme_actions = {}

        light_theme_action = QAction("Light", self)
        light_theme_action.setToolTip("Switch to light theme")
        light_theme_action.setCheckable(True)
        light_theme_action.setChecked(False)
        light_theme_action.triggered.connect(lambda: self._on_theme_changed("light"))
        theme_menu.addAction(light_theme_action)
        self._theme_actions["light"] = light_theme_action

        dark_theme_action = QAction("Dark", self)
        dark_theme_action.setToolTip("Switch to dark theme")
        dark_theme_action.setCheckable(True)
        dark_theme_action.triggered.connect(lambda: self._on_theme_changed("dark"))
        theme_menu.addAction(dark_theme_action)
        self._theme_actions["dark"] = dark_theme_action

        midnight_theme_action = QAction("Midnight", self)
        midnight_theme_action.setToolTip("Switch to midnight theme")
        midnight_theme_action.setCheckable(True)
        midnight_theme_action.setChecked(True)
        midnight_theme_action.triggered.connect(lambda: self._on_theme_changed("midnight"))
        theme_menu.addAction(midnight_theme_action)
        self._theme_actions["midnight"] = midnight_theme_action

        theme_menu.addSeparator()

        # Cycle theme shortcut
        cycle_theme_action = QAction("Cycle Theme", self)
        cycle_theme_action.setShortcut("Ctrl+T")
        cycle_theme_action.setStatusTip("Cycle through themes (Ctrl+T)")
        cycle_theme_action.triggered.connect(self._on_cycle_theme)
        theme_menu.addAction(cycle_theme_action)

        view_menu.addSeparator()

        # Streaming menu items
        self._start_streaming_action = QAction("Start &Streaming...", self)
        self._start_streaming_action.setStatusTip("Open streaming configuration dialog")
        self._start_streaming_action.triggered.connect(self._on_start_streaming_dialog)
        view_menu.addAction(self._start_streaming_action)

        self._stop_streaming_action = QAction("Sto&p Streaming", self)
        self._stop_streaming_action.setStatusTip("Stop the active streaming session")
        self._stop_streaming_action.setEnabled(False)
        self._stop_streaming_action.triggered.connect(self._on_stop_streaming)
        view_menu.addAction(self._stop_streaming_action)

        # ============================================================
        # Data Menu
        # ============================================================
        data_menu = menubar.addMenu("&Data")

        # Add Calculated Field
        add_calc_field_action = QAction("&Add Calculated Field...", self)
        add_calc_field_action.setShortcut("Ctrl+Alt+F")
        add_calc_field_action.setStatusTip("Add a new calculated column based on expression")
        add_calc_field_action.triggered.connect(self._on_add_calculated_field)
        data_menu.addAction(add_calc_field_action)

        # Remove Field
        remove_field_action = QAction("&Remove Field...", self)
        remove_field_action.setStatusTip("Remove a field/column from the data")
        remove_field_action.triggered.connect(self._on_remove_field)
        data_menu.addAction(remove_field_action)

        # ============================================================
        # Logger Menu
        # ============================================================
        logger_menu = menubar.addMenu("&Logger")

        start_trace_action = QAction("&Start Trace...", self)
        start_trace_action.setStatusTip("Start block layer tracing (uses saved config or opens Configure)")
        start_trace_action.triggered.connect(self._on_start_trace)
        logger_menu.addAction(start_trace_action)

        logger_menu.addSeparator()

        configure_action = QAction("&Configure...", self)
        configure_action.setStatusTip("Open the Trace Configuration dialog")
        configure_action.triggered.connect(self._on_configure_trace)
        logger_menu.addAction(configure_action)

        # ============================================================
        # Parser Menu
        # ============================================================
        parser_menu = menubar.addMenu("&Parser")

        ftrace_action = QAction("&Ftrace Parser...", self)
        ftrace_action.setStatusTip("Parse ftrace log file and load into table")
        ftrace_action.triggered.connect(lambda: self._on_run_parser("ftrace"))
        parser_menu.addAction(ftrace_action)

        parser_menu.addSeparator()

        manage_profiles_action = QAction("Manage &Profiles...", self)
        manage_profiles_action.setStatusTip("Manage parser profiles")
        manage_profiles_action.triggered.connect(self._on_manage_parser_profiles)
        parser_menu.addAction(manage_profiles_action)

        # ============================================================
        # Graph Menu
        # ============================================================
        graph_menu = menubar.addMenu("&Graph")

        # Statistics submenu
        statistics_menu = graph_menu.addMenu("&Statistics")

        histogram_bins_action = QAction("&Histogram Bins...", self)
        histogram_bins_action.setStatusTip("Set the number of bins for histograms")
        histogram_bins_action.triggered.connect(self._on_set_both_bins)
        statistics_menu.addAction(histogram_bins_action)

        # Options submenu
        options_menu = graph_menu.addMenu("&Options")

        # Chart Type submenu within Options
        chart_type_menu = options_menu.addMenu("Chart &Type")
        for chart_type in ChartType:
            action = QAction(chart_type.value.title(), self)
            action.triggered.connect(lambda checked, ct=chart_type: self.state.set_chart_type(ct))
            chart_type_menu.addAction(action)

        options_menu.addSeparator()

        # Axis settings
        axis_settings_action = QAction("&Axis Settings...", self)
        axis_settings_action.setStatusTip("Configure axis range, labels, and scale")
        axis_settings_action.triggered.connect(self._on_axis_settings)
        options_menu.addAction(axis_settings_action)

        # Curve fitting
        curve_fitting_action = QAction("&Curve Fitting...", self)
        curve_fitting_action.setStatusTip("Configure curve fitting options")
        curve_fitting_action.triggered.connect(self._on_curve_fitting)
        options_menu.addAction(curve_fitting_action)

        # Trend line
        trend_line_action = QAction("Add &Trend Line...", self)
        trend_line_action.setStatusTip("Add a trend line to the current graph")
        trend_line_action.triggered.connect(self._on_add_trend_line)
        options_menu.addAction(trend_line_action)

        # ============================================================
        # Help Menu
        # ============================================================
        help_menu = menubar.addMenu("&Help")

        search_features_action = QAction("&Search Features...", self)
        search_features_action.setShortcut("Ctrl+Shift+P")
        search_features_action.setStatusTip("Open Command Palette to search and execute features (Ctrl+Shift+P)")
        search_features_action.triggered.connect(self._on_open_command_palette)
        help_menu.addAction(search_features_action)

        # Also bind F1 as alternative shortcut
        search_features_f1_action = QAction("Search Features (F1)", self)
        search_features_f1_action.setShortcut("F1")
        search_features_f1_action.triggered.connect(self._on_open_command_palette)
        self.addAction(search_features_f1_action)  # Window-level shortcut

        help_menu.addSeparator()

        shortcuts_action = QAction("&Keyboard Shortcuts...", self)
        shortcuts_action.setShortcut("Ctrl+/")
        shortcuts_action.setStatusTip("Show keyboard shortcuts reference")
        shortcuts_action.triggered.connect(self._show_shortcuts_dialog)
        help_menu.addAction(shortcuts_action)

        edit_shortcuts_action = QAction("&Customize Shortcuts...", self)
        edit_shortcuts_action.setStatusTip("Customize keyboard shortcuts")
        edit_shortcuts_action.triggered.connect(self._show_edit_shortcuts_dialog)
        help_menu.addAction(edit_shortcuts_action)

        help_menu.addSeparator()

        check_updates_action = QAction("Check for &Updates...", self)
        check_updates_action.setStatusTip("Check GitHub Releases and update (Windows)")
        check_updates_action.triggered.connect(lambda: self._auto_check_updates(force_ui=True))
        help_menu.addAction(check_updates_action)

        about_action = QAction("&About", self)
        about_action.setStatusTip("About Data Graph Studio")
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        """Main toolbar setup (Line 1)"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)

        # === Project/Profile I/O Section ===
        open_project_btn = QAction("📂 Open Project", self)
        open_project_btn.setToolTip(self._format_tooltip("Open Project (.dgs)", "Ctrl+O"))
        open_project_btn.triggered.connect(self._on_open_file)
        toolbar.addAction(open_project_btn)

        open_profile_btn = QAction("📂 Open Profile", self)
        open_profile_btn.setToolTip(self._format_tooltip("Load Graph Profile", ""))
        open_profile_btn.triggered.connect(lambda: self.dataset_manager._on_load_profile())
        toolbar.addAction(open_profile_btn)

        save_project_btn = QAction("💾 Save Project", self)
        save_project_btn.setToolTip(self._format_tooltip("Save Project", "Ctrl+Alt+S"))
        save_project_btn.triggered.connect(self._on_save_project_file)
        toolbar.addAction(save_project_btn)

        save_profile_btn = QAction("💾 Save Profile", self)
        save_profile_btn.setToolTip(self._format_tooltip("Save Graph Profile", ""))
        save_profile_btn.triggered.connect(lambda: self.dataset_manager._on_save_profile())
        toolbar.addAction(save_profile_btn)

        toolbar.addSeparator()

        # === Navigation/Selection Tools ===
        self._tool_actions = {}

        tools = [
            (ToolMode.ZOOM, "🔍", "Zoom Mode", "Z"),
            (ToolMode.PAN, "✋", "Pan Mode", "H"),
            (ToolMode.RECT_SELECT, "⬚", "Rectangle Select", "R"),
            (ToolMode.LASSO_SELECT, "✏️", "Lasso Select", "L"),
        ]

        for mode, icon, name, shortcut in tools:
            action = QAction(f"{icon}", self)
            action.setToolTip(self._format_tooltip(name, shortcut))
            action.setCheckable(True)
            action.triggered.connect(lambda checked, m=mode: self.state.set_tool_mode(m))
            toolbar.addAction(action)
            self._tool_actions[mode] = action

        self._tool_actions[ToolMode.PAN].setChecked(True)

        toolbar.addSeparator()

        # === Drawing Tools ===
        draw_tools = [
            (ToolMode.LINE_DRAW, "🖊️", "Line Draw", "Shift+L"),
            (ToolMode.ARROW_DRAW, "➡", "Arrow Draw", "Shift+A"),
            (ToolMode.CIRCLE_DRAW, "⭕", "Circle Draw", "Shift+C"),
            (ToolMode.RECT_DRAW, "▢", "Rectangle Draw", "Shift+R"),
            (ToolMode.TEXT_DRAW, "📝", "Text Draw", "Shift+T"),
        ]

        for mode, icon, name, shortcut in draw_tools:
            action = QAction(f"{icon}", self)
            action.setToolTip(self._format_tooltip(name, shortcut))
            action.setCheckable(True)
            action.triggered.connect(lambda checked, m=mode: self.state.set_tool_mode(m))
            toolbar.addAction(action)
            self._tool_actions[mode] = action

        # Draw color picker
        self._draw_color = QColor("#FF0000")
        self._draw_color_btn = QPushButton()
        self._draw_color_btn.setFixedSize(24, 24)
        self._draw_color_btn.setCursor(Qt.PointingHandCursor)
        self._draw_color_btn.setToolTip("Draw Color — click to change")
        self._draw_color_btn.clicked.connect(self._on_draw_color_pick)
        self._update_draw_color_btn()
        toolbar.addWidget(self._draw_color_btn)

        clear_drawing_btn = QAction("🗑️", self)
        clear_drawing_btn.setToolTip(self._format_tooltip("Clear All Drawings", "Del"))
        clear_drawing_btn.triggered.connect(self._on_clear_drawings)
        toolbar.addAction(clear_drawing_btn)

        toolbar.addSeparator()

        # === Chart Type Selector ===
        chart_types = [
            (ChartType.LINE, "📈", "<b>Line Chart</b><br>Best for: Time series, trends<br>Shortcut: 1"),
            (ChartType.BAR, "📊", "<b>Bar Chart</b><br>Best for: Comparing categories<br>Shortcut: 2"),
            (ChartType.SCATTER, "⚬", "<b>Scatter Plot</b><br>Best for: Correlations, distributions<br>Shortcut: 3"),
            (ChartType.AREA, "▤", "<b>Area Chart</b><br>Best for: Cumulative values, stacked data<br>Shortcut: 5"),
        ]

        for ct, icon, tooltip in chart_types:
            action = QAction(icon, self)
            action.setToolTip(tooltip)
            action.triggered.connect(lambda checked, c=ct: self.state.set_chart_type(c))
            toolbar.addAction(action)

        # Store references for view actions
        self._reset_btn_action = None
        self._autofit_btn_action = None

    def _setup_streaming_toolbar(self):
        """Secondary toolbar setup (Line 2) - Streaming + Compare"""
        self.addToolBarBreak(Qt.TopToolBarArea)  # Force new line after main toolbar

        toolbar = QToolBar("Secondary Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # === Streaming Controls ===
        streaming_label = QLabel(" Streaming: ")
        streaming_label.setObjectName("toolbarLabel")
        toolbar.addWidget(streaming_label)

        # Play/Pause
        self._streaming_play_action = QAction("▶", self)
        self._streaming_play_action.setToolTip("Play Streaming")
        self._streaming_play_action.setCheckable(True)
        self._streaming_play_action.triggered.connect(self._on_streaming_play)
        toolbar.addAction(self._streaming_play_action)

        self._streaming_pause_action = QAction("⏸", self)
        self._streaming_pause_action.setToolTip("Pause Streaming")
        self._streaming_pause_action.triggered.connect(self._on_streaming_pause)
        toolbar.addAction(self._streaming_pause_action)

        self._streaming_stop_action = QAction("⏹", self)
        self._streaming_stop_action.setToolTip("Stop Streaming")
        self._streaming_stop_action.triggered.connect(self._on_streaming_stop)
        toolbar.addAction(self._streaming_stop_action)

        # Speed control
        from PySide6.QtWidgets import QComboBox
        speed_label = QLabel(" Speed: ")
        speed_label.setObjectName("toolbarLabel")
        toolbar.addWidget(speed_label)

        self._streaming_speed_combo = QComboBox()
        self._streaming_speed_combo.addItems(["0.5x", "1x", "2x", "5x", "10x"])
        self._streaming_speed_combo.setCurrentIndex(1)  # Default 1x
        self._streaming_speed_combo.currentTextChanged.connect(self._on_streaming_speed_changed)
        self._streaming_speed_combo.setFixedWidth(60)
        toolbar.addWidget(self._streaming_speed_combo)

        # Window size
        window_label = QLabel(" Window: ")
        window_label.setObjectName("toolbarLabel")
        toolbar.addWidget(window_label)

        self._streaming_window_combo = QComboBox()
        self._streaming_window_combo.addItems(["100", "500", "1000", "5000", "All"])
        self._streaming_window_combo.setCurrentIndex(2)  # Default 1000
        self._streaming_window_combo.currentTextChanged.connect(self._on_streaming_window_changed)
        self._streaming_window_combo.setFixedWidth(70)
        toolbar.addWidget(self._streaming_window_combo)

        toolbar.addSeparator()

        # === View Controls ===
        view_label = QLabel(" View: ")
        view_label.setObjectName("toolbarLabel")
        toolbar.addWidget(view_label)

        deselect_btn = QAction("✕ Clear", self)
        deselect_btn.setToolTip(self._format_tooltip("Clear Selection", "Esc"))
        deselect_btn.triggered.connect(self._on_clear_selection)
        toolbar.addAction(deselect_btn)

        reset_btn = QAction("↺ Reset", self)
        reset_btn.setToolTip(self._format_tooltip("Reset View", "Home"))
        reset_btn.triggered.connect(self._reset_graph_view)
        toolbar.addAction(reset_btn)
        self._reset_btn_action = reset_btn

        autofit_btn = QAction("⊡ Fit", self)
        autofit_btn.setToolTip(self._format_tooltip("Auto Fit to Data", "F"))
        autofit_btn.triggered.connect(self._autofit_graph)
        toolbar.addAction(autofit_btn)
        self._autofit_btn_action = autofit_btn

    # Streaming toolbar event handlers
    def _on_streaming_play(self, checked: bool = False):
        """Start/resume streaming — Play 연속 클릭 방어 (FR-B2.6)."""
        if self._streaming_controller.state == "live":
            return  # already playing
        if not self.state.is_data_loaded:
            self.statusbar.showMessage("⚠ No data loaded — cannot start streaming", 4000)
            self._streaming_play_action.setChecked(False)
            return
        if self._streaming_controller.state == "paused":
            self._streaming_controller.resume()
        else:
            # Open config dialog for fresh start
            self._on_start_streaming_dialog()

    def _on_streaming_pause(self):
        """Pause/resume streaming playback"""
        if self._streaming_controller.state == "live":
            self._streaming_controller.pause()
        elif self._streaming_controller.state == "paused":
            self._streaming_controller.resume()

    def _on_streaming_stop(self):
        """Stop streaming — current data is kept (FR-B2.7)."""
        self._streaming_controller.stop()

    def _on_streaming_speed_changed(self, text: str):
        """Change streaming speed"""
        try:
            speed = float(text.replace('x', ''))
            self._streaming_controller.set_poll_interval(
                max(500, int(self._streaming_controller.poll_interval_ms / speed))
            )
        except (ValueError, ZeroDivisionError):
            pass

    def _on_streaming_window_changed(self, text: str):
        """Change streaming window size"""
        pass  # Window size is a display-level concept; no-op for now

    def _setup_compare_toolbar(self):
        """Setup the Compare Toolbar (hidden by default, auto-shown during comparison)."""
        self._compare_toolbar = CompareToolbar(self)
        self.addToolBar(Qt.TopToolBarArea, self._compare_toolbar)
        self._compare_toolbar.hide()

        # View menu: "Compare Toolbar" toggle action
        # Find View menu
        view_menu = None
        for action in self.menuBar().actions():
            if action.text().replace("&", "") == "View":
                view_menu = action.menu()
                break

        if view_menu is not None:
            view_menu.addSeparator()
            self._compare_toolbar_action = self._compare_toolbar.toggleViewAction()
            self._compare_toolbar_action.setText("Compare Toolbar")
            self._compare_toolbar_action.setToolTip("Show/hide the compare toolbar")
            view_menu.addAction(self._compare_toolbar_action)

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
        
        # Project Explorer (새로운 트리 뷰)
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
        self._sidebar_tabs.addTab(self.project_tree, "Projects")
        
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

    def _setup_autorecovery(self):
        """Setup autosave + recovery prompt"""
        self._autosave_path = os.path.expanduser("~/.data_graph_studio/autosave.json")
        os.makedirs(os.path.dirname(self._autosave_path), exist_ok=True)

        # Prompt recovery if autosave exists
        # Skip if autosave is stale (>24h) to avoid blocking on repeated crashes
        if os.path.exists(self._autosave_path):
            try:
                import time as _time
                age = _time.time() - os.path.getmtime(self._autosave_path)
                if age > 86400:  # >24h → discard silently
                    os.remove(self._autosave_path)
                else:
                    # Use QTimer.singleShot to show dialog AFTER event loop starts
                    # so IPC server is already running and accessible
                    from PySide6.QtCore import QTimer as _QTimer
                    _QTimer.singleShot(500, self._prompt_recovery)
            except Exception:
                pass

        # Autosave timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60 * 1000)  # 1 minute
        self._autosave_timer.timeout.connect(self._autosave_session)
        self._autosave_timer.start()

    def _prompt_recovery(self):
        """Show recovery dialog (deferred via QTimer so IPC is already up).

        Features:
        - "Don't show again" checkbox (persisted in QSettings)
        - On restore failure: backs up to .bak, deletes original, shows toast
        """
        if not os.path.exists(self._autosave_path):
            return

        from PySide6.QtCore import QSettings
        settings = QSettings("Godol", "DataGraphStudio")
        if settings.value("recovery/skip_prompt", False, type=bool):
            # User opted out — silently discard
            try:
                os.remove(self._autosave_path)
            except OSError:
                pass
            return

        try:
            from PySide6.QtWidgets import QCheckBox
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle("Recovery")
            msg.setText("A previous session was not closed properly.\nRecover the last autosave?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

            cb = QCheckBox("Don't show again")
            msg.setCheckBox(cb)

            result = msg.exec()

            if cb.isChecked():
                settings.setValue("recovery/skip_prompt", True)

            if result == QMessageBox.Yes:
                try:
                    self._restore_autosave()
                except Exception as exc:
                    # Backup failed autosave then remove
                    bak_path = self._autosave_path + ".bak"
                    try:
                        import shutil
                        shutil.copy2(self._autosave_path, bak_path)
                    except OSError:
                        pass
                    try:
                        os.remove(self._autosave_path)
                    except OSError:
                        pass
                    if hasattr(self, 'statusBar'):
                        self.statusBar().showMessage(
                            f"Recovery failed: {exc}. Backup saved to autosave.json.bak",
                            8000,
                        )
            else:
                try:
                    os.remove(self._autosave_path)
                except OSError:
                    pass
        except Exception:
            pass

    def _autosave_session(self):
        """Autosave datasets + graph settings + drawings"""
        try:
            if not self.state.is_data_loaded:
                return

            datasets = []
            for did, meta in self.state._dataset_metadata.items():
                datasets.append({
                    "id": did,
                    "name": meta.name,
                    "file_path": meta.file_path
                })

            # Serialize all profiles from ProfileStore
            profiles = []
            for did in self.state._dataset_metadata:
                for gs in self.profile_store.get_by_dataset(did):
                    try:
                        profiles.append(gs.to_dict())
                    except Exception:
                        pass

            payload = {
                "version": 2,
                "datasets": datasets,
                "active_dataset_id": self.state.active_dataset_id,
                "graph_state": self.state.get_current_graph_state(),
                "profiles": profiles,
                "drawings": self.graph_panel.get_drawings_data() if hasattr(self, 'graph_panel') else {},
                "ts": time.time()
            }

            with open(self._autosave_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _restore_autosave(self):
        """Restore from autosave file"""
        try:
            with open(self._autosave_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        datasets = data.get("datasets", [])
        if not datasets:
            return

        progress = QProgressDialog("Restoring session...", "Cancel", 0, len(datasets), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        for i, ds in enumerate(datasets):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"Loading: {Path(ds.get('file_path','')).name}")
            QApplication.processEvents()

            path = ds.get("file_path")
            if not path or not os.path.exists(path):
                continue

            dataset_id = ds.get("id")
            name = ds.get("name")
            new_id = self.engine.load_dataset(path, name=name, dataset_id=dataset_id)
            if new_id:
                dataset = self.engine.get_dataset(new_id)
                memory_bytes = dataset.df.estimated_size() if dataset and dataset.df is not None else 0
                self.state.add_dataset(
                    dataset_id=new_id,
                    name=dataset.name if dataset else name,
                    file_path=path,
                    row_count=self.engine.row_count,
                    column_count=self.engine.column_count,
                    memory_bytes=memory_bytes
                )

        progress.setValue(len(datasets))

        # Activate dataset
        active_id = data.get("active_dataset_id")
        if active_id and self.engine.activate_dataset(active_id):
            self._on_dataset_activated(active_id)
        elif self.engine.active_dataset_id:
            self._on_dataset_activated(self.engine.active_dataset_id)

        # Restore profiles into ProfileStore
        profiles_data = data.get("profiles", [])
        for p_data in profiles_data:
            try:
                gs = GraphSetting.from_dict(p_data)
                # Only add if dataset exists
                if gs.dataset_id in [ds.get("id") for ds in datasets]:
                    self.profile_store.add(gs)
            except Exception:
                pass

        # Restore graph settings
        graph_state = data.get("graph_state", {})
        if graph_state:
            self._apply_graph_state(graph_state)

        # Restore drawings
        drawings = data.get("drawings", {})
        if drawings and hasattr(self, 'graph_panel'):
            self.graph_panel.load_drawings_data(drawings)

        # Refresh profile tree + graph
        self.profile_model.refresh()
        self.graph_panel.refresh()
        self.summary_panel.refresh()

    def _apply_graph_state(self, gs: Dict[str, Any]):
        """Apply graph state dict to current session"""
        try:
            # Chart type
            if gs.get('chart_type'):
                self.state.set_chart_type(ChartType(gs['chart_type']))

            # X column
            self.state.set_x_column(gs.get('x_column'))

            # Group columns
            self.state.clear_group_zone()
            for g in gs.get('group_columns', []):
                name = g.get('name')
                if name:
                    self.state.add_group_column(name)
                    # Set selected values
                    for gc in self.state.group_columns:
                        if gc.name == name:
                            gc.selected_values = set(g.get('selected_values', []))

            # Value columns
            self.state.clear_value_zone()
            for v in gs.get('value_columns', []):
                name = v.get('name')
                if not name:
                    continue
                agg = AggregationType(v.get('aggregation', 'sum'))
                self.state.add_value_column(name, aggregation=agg)
                idx = len(self.state.value_columns) - 1
                self.state.update_value_column(
                    idx,
                    color=v.get('color'),
                    use_secondary_axis=v.get('use_secondary_axis'),
                    formula=v.get('formula')
                )

            # Hover columns
            self.state.clear_hover_columns()
            for h in gs.get('hover_columns', []):
                self.state.add_hover_column(h)

            # Chart settings
            cs = gs.get('chart_settings', {})
            if cs:
                self.state.update_chart_settings(
                    line_width=cs.get('line_width', self.state.chart_settings.line_width),
                    marker_size=cs.get('marker_size', self.state.chart_settings.marker_size),
                    fill_opacity=cs.get('fill_opacity', self.state.chart_settings.fill_opacity),
                    show_data_labels=cs.get('show_data_labels', self.state.chart_settings.show_data_labels),
                    x_log_scale=cs.get('x_log_scale', self.state.chart_settings.x_log_scale),
                    y_log_scale=cs.get('y_log_scale', self.state.chart_settings.y_log_scale),
                    y_min=cs.get('y_min', self.state.chart_settings.y_min),
                    y_max=cs.get('y_max', self.state.chart_settings.y_max),
                    y_label=cs.get('y_label', self.state.chart_settings.y_label),
                    secondary_y_log_scale=cs.get('secondary_y_log_scale', self.state.chart_settings.secondary_y_log_scale),
                    secondary_y_min=cs.get('secondary_y_min', self.state.chart_settings.secondary_y_min),
                    secondary_y_max=cs.get('secondary_y_max', self.state.chart_settings.secondary_y_max),
                    secondary_y_label=cs.get('secondary_y_label', self.state.chart_settings.secondary_y_label),
                )
        except Exception:
            pass

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
                color = "#EF4444"  # 빨강 - 위험
                emoji = "🔴"
            elif sys_pct > 70:
                color = "#F59E0B"  # 노랑 - 경고
                emoji = "🟡"
            else:
                color = "#10B981"  # 녹색 - 정상
                emoji = "🟢"

            self._status_memory_label.setText(f"{emoji} {proc_str} ({sys_pct:.0f}%)")
            # Memory status color is dynamic, keep minimal styling
            self._status_memory_label.setToolTip(
                f"Process Memory: {proc_str}\n"
                f"System Memory: {sys_pct:.1f}% used\n"
                f"Available: {sys_mem['available_gb']:.1f} GB"
            )
        except Exception as e:
            logger.debug(f"Memory status update failed: {e}")
    
    def _connect_signals(self):
        """시그널 연결"""
        # State signals
        self.state.data_loaded.connect(self._on_data_loaded)
        self.state.data_cleared.connect(self._on_data_cleared)
        self.state.selection_changed.connect(self._update_selection_status)
        self.state.tool_mode_changed.connect(self._on_tool_mode_changed)

        # Auto-save active profile on state changes (debounced)
        self._profile_autosave_timer = QTimer(self)
        self._profile_autosave_timer.setSingleShot(True)
        self._profile_autosave_timer.setInterval(500)  # 500ms debounce
        self._profile_autosave_timer.timeout.connect(self._autosave_active_profile)
        self.state.chart_settings_changed.connect(self._schedule_profile_autosave)
        self.state.value_zone_changed.connect(self._schedule_profile_autosave)
        self.state.group_zone_changed.connect(self._schedule_profile_autosave)

        # Panel signals - route through preview dialog
        self.table_panel.file_dropped.connect(self._show_parsing_preview)
        self.table_panel.window_changed.connect(self._on_window_changed)

        # Profile comparison controller signals
        self.profile_comparison_controller.comparison_started.connect(
            self._on_profile_comparison_started
        )
        self.profile_comparison_controller.comparison_ended.connect(
            self._on_profile_comparison_ended
        )

        # Streaming controller signals
        self._streaming_controller.streaming_state_changed.connect(
            self._on_streaming_state_changed
        )
        self._streaming_controller.data_updated.connect(
            self._on_streaming_data_updated
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

    def _float_main_panel(self, panel_key: str):
        """메인 패널을 독립 창으로 분리"""
        if panel_key in self._float_windows:
            self._float_windows[panel_key].raise_()
            self._float_windows[panel_key].activateWindow()
            return

        panel_map = {
            "summary": (self.summary_panel, "📊 Overview", 0),
            "graph": (self.graph_panel, "📈 Graph Panel", 1),
            "table": (self.table_panel, "📋 Table Panel", 2),
        }

        if panel_key not in panel_map:
            return

        widget, title, splitter_index = panel_map[panel_key]

        # Save current sizes before modification
        current_sizes = self.main_splitter.sizes()

        # Float window 생성
        float_window = FloatWindow(title, widget, self)
        float_window.dock_requested.connect(lambda: self._dock_main_panel(panel_key))
        self._float_windows[panel_key] = float_window

        # Find the actual current index of the widget in splitter
        actual_index = -1
        for i in range(self.main_splitter.count()):
            if self.main_splitter.widget(i) is widget:
                actual_index = i
                break

        if actual_index >= 0:
            # 플레이스홀더로 교체
            placeholder = self._placeholders[panel_key]
            self.main_splitter.replaceWidget(actual_index, placeholder)
            placeholder.show()

            # Restore sizes
            self.main_splitter.setSizes(current_sizes)

        # Float 버튼 비활성화
        if hasattr(widget, 'float_btn'):
            widget.float_btn.setEnabled(False)

        float_window.show()

    def _dock_main_panel(self, panel_key: str):
        """메인 패널을 메인 창으로 복귀"""
        if panel_key not in self._float_windows:
            return

        float_window = self._float_windows[panel_key]
        widget = float_window.get_content_widget()

        panel_map = {
            "summary": (self.summary_panel, 0),
            "graph": (self.graph_panel, 1),
            "table": (self.table_panel, 2),
        }

        expected_widget, target_index = panel_map.get(panel_key, (None, 0))
        placeholder = self._placeholders[panel_key]

        # Save current sizes before modification
        current_sizes = self.main_splitter.sizes()

        # Find the actual current index of the placeholder in splitter
        actual_index = -1
        for i in range(self.main_splitter.count()):
            if self.main_splitter.widget(i) is placeholder:
                actual_index = i
                break

        if actual_index >= 0:
            # 플레이스홀더를 원래 위젯으로 교체
            self.main_splitter.replaceWidget(actual_index, widget)
            placeholder.hide()
            widget.show()

            # Restore sizes
            self.main_splitter.setSizes(current_sizes)
        else:
            # Placeholder not found, need to insert at correct position
            # Remove widget from float window's layout first
            widget.setParent(None)

            # Insert at target index
            self.main_splitter.insertWidget(target_index, widget)
            widget.show()

        # Float 버튼 활성화
        if hasattr(widget, 'float_btn'):
            widget.float_btn.setEnabled(True)

        # Float window 정리
        float_window.close()
        float_window.deleteLater()
        del self._float_windows[panel_key]
    
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
        from data_graph_studio.parsers import FtraceParser, ParserProfileStore

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

    def _on_configure_trace(self) -> None:
        """Open the Trace Configuration dialog (always)."""
        from data_graph_studio.ui.dialogs.trace_config_dialog import TraceConfigDialog

        logger.debug("[Logger] opening TraceConfigDialog")
        dialog = TraceConfigDialog(self)
        result = dialog.exec()
        logger.debug("[Logger] TraceConfigDialog result=%s, start_requested=%s",
                     result, dialog.start_requested)

        if result == QDialog.DialogCode.Accepted and dialog.start_requested:
            self._run_trace(dialog.get_config())

    # ================================================================
    # Logger — ADB + Perfetto block layer tracing
    # ================================================================

    def _on_start_trace(self) -> None:
        """Start trace using saved config, or open Configure if none."""
        import shutil

        from data_graph_studio.ui.dialogs.trace_config_dialog import (
            load_logger_config,
            TraceConfigDialog,
        )

        logger_cfg = load_logger_config()

        # If config looks valid, start directly; otherwise open configure
        has_device = bool(logger_cfg.get("device_serial"))
        has_events = bool(logger_cfg.get("events"))
        has_adb = bool(shutil.which("adb"))
        has_save_path = bool(logger_cfg.get("save_path"))
        logger.debug("[Logger] start_trace check: adb=%s, device=%s, events=%s, save=%s",
                     has_adb, has_device, has_events, has_save_path)

        if has_device and has_events and has_adb and has_save_path:
            # Bug fix: verify capture mode prerequisites before starting
            capture_mode = logger_cfg.get("capture_mode", "perfetto")
            serial = logger_cfg["device_serial"]
            if not self._verify_capture_mode(serial, capture_mode):
                self._on_configure_trace()
                return
            self._run_trace(logger_cfg)
        else:
            self._on_configure_trace()

    @staticmethod
    def _verify_capture_mode(serial: str, capture_mode: str) -> bool:
        """Check if device supports the capture mode (perfetto/root).

        Returns True if check passes or is inconclusive (timeout).
        """
        import subprocess

        try:
            if capture_mode == "perfetto":
                result = subprocess.run(
                    ["adb", "-s", serial, "shell", "which", "perfetto"],
                    capture_output=True, text=True, timeout=5,
                )
                return result.returncode == 0 and bool(result.stdout.strip())
            else:
                # Try both su variants (some devices need 'su 0 id')
                for cmd in [["su", "-c", "id"], ["su", "0", "id"]]:
                    result = subprocess.run(
                        ["adb", "-s", serial, "shell", *cmd],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.returncode == 0 and "uid=0" in result.stdout:
                        return True
                return False
        except (subprocess.TimeoutExpired, OSError):
            return True  # Inconclusive — let it proceed

    def _run_trace(self, logger_cfg: dict) -> None:
        """Execute trace with given config (Perfetto/Raw Ftrace)."""
        import shutil
        import datetime

        from data_graph_studio.ui.dialogs.trace_progress_dialog import (
            AdbTraceController,
            PerfettoTraceController,
            TraceProgressDialog,
        )

        logger.info("[Logger] _run_trace: mode=%s, device=%s, events=%d",
                     logger_cfg.get("capture_mode", "?"),
                     logger_cfg.get("device_serial", "?"),
                     len(logger_cfg.get("events", [])))

        if not shutil.which("adb"):
            QMessageBox.warning(
                self, "Logger",
                "adb not found in PATH.\n\n"
                "Install Android SDK Platform Tools and ensure 'adb' is in your PATH.\n"
                "Or use Logger → Configure... to set up.",
            )
            return

        serial = logger_cfg.get("device_serial", "")
        if not serial:
            QMessageBox.warning(
                self, "Logger",
                "No device configured.\n\n"
                "Use Logger → Configure... to select a device.",
            )
            return

        capture_mode = logger_cfg.get("capture_mode", "perfetto")
        is_perfetto = capture_mode == "perfetto"

        # 저장 경로 결정
        save_path = logger_cfg.get("save_path", "")
        if not save_path:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            if is_perfetto:
                default_name = f"trace_{ts}.csv"
                file_filter = "CSV (*.csv);;All Files (*)"
            else:
                default_name = f"ftrace_{ts}.txt"
                file_filter = "Ftrace Text (*.txt);;All Files (*)"
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Trace File", default_name, file_filter,
            )
            if not save_path:
                return

        # 컨트롤러 생성 (캡처 모드에 따라)
        if is_perfetto:
            try:
                PerfettoTraceController.find_trace_processor()
            except FileNotFoundError as e:
                QMessageBox.warning(self, "Logger", str(e))
                return
            controller = PerfettoTraceController(self)
        else:
            controller = AdbTraceController(self)

        try:
            logger.debug("[Logger] starting %s trace on %s", capture_mode, serial)
            controller.start_trace(serial, logger_cfg)
        except Exception as e:
            logger.error("[Logger] start_trace failed: %s", e, exc_info=True)
            QMessageBox.warning(self, "Logger", f"Failed to start trace:\n{e}")
            controller.cleanup()
            return

        dialog = TraceProgressDialog(controller, save_path, self)
        result = dialog.exec()

        logger.debug("[Logger] TraceProgressDialog result=%s", result)
        if result == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage(f"Trace saved: {save_path}", 5000)

            if is_perfetto:
                # PerfettoTraceController saves CSV with .csv suffix
                csv_path = str(Path(save_path).with_suffix(".csv"))
                logger.info("[Logger] loading perfetto CSV: %s", csv_path)
                self._load_csv_async(csv_path)
            else:
                reply = QMessageBox.question(
                    self, "Logger",
                    f"Trace saved to:\n{save_path}\n\n"
                    "Open with Ftrace Parser now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._parse_ftrace_async(save_path)

    def _load_csv_async(self, csv_path: str) -> None:
        """Load a CSV file (from trace_processor_shell) in a background thread.

        Args:
            csv_path: Path to the CSV file.
        """
        from pathlib import Path
        from PySide6.QtCore import QThread, Signal as QtSignal

        import polars as pl

        class _CsvWorker(QThread):
            finished = QtSignal(object)
            error = QtSignal(str)

            def run(self_w):
                try:
                    df = pl.read_csv(csv_path)
                    # ts is in nanoseconds, convert to seconds
                    if "ts" in df.columns:
                        df = df.with_columns(
                            (pl.col("ts").cast(pl.Float64) / 1e9).alias("timestamp")
                        ).drop("ts")
                    self_w.finished.emit(df)
                except Exception as e:
                    self_w.error.emit(str(e))

        logger.debug("[Logger] _load_csv_async: %s", csv_path)
        self.statusBar().showMessage("Loading CSV...", 0)
        worker = _CsvWorker(self)

        def on_finished(df):
            logger.info("[Logger] CSV loaded: %d rows, %d cols, columns=%s",
                        len(df), len(df.columns), list(df.columns)[:10])
            name = Path(csv_path).stem
            did = self.engine.load_dataset_from_dataframe(
                df, name=name, source_path=csv_path
            )
            if did:
                logger.info("[Logger] dataset created: id=%s, name=%s", did, name)
                self._on_data_loaded()
                self._apply_graph_presets(df, converter="blocklayer")
                self.statusBar().showMessage(
                    f"Perfetto trace: loaded {len(df)} rows", 5000,
                )
            else:
                logger.error("[Logger] load_dataset_from_dataframe returned None for %s", csv_path)
                QMessageBox.warning(self, "Logger", "Failed to load CSV data.")
                self.statusBar().clearMessage()

        def on_error(msg):
            logger.error("[Logger] CSV load failed: %s", msg)
            QMessageBox.critical(self, "Logger", f"CSV load failed:\n{msg}")
            self.statusBar().clearMessage()

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._csv_worker = worker
        worker.start()

    def _parse_ftrace_async(self, file_path: str, converter: str = "blocklayer") -> None:
        """Parse an ftrace text file in a background thread.

        Avoids blocking the UI during large file parsing.

        Args:
            file_path: Path to the ftrace text file.
            converter: Converter to apply (default: "blocklayer").
        """
        from pathlib import Path
        from PySide6.QtCore import QThread, Signal as QtSignal

        from data_graph_studio.parsers import FtraceParser

        parser = FtraceParser()
        settings = parser.default_settings()
        settings["converter"] = converter

        class _ParseWorker(QThread):
            finished = QtSignal(object)
            error = QtSignal(str)

            def run(self_w):
                try:
                    df = parser.parse_raw(file_path, settings)
                    self_w.finished.emit(df)
                except Exception as e:
                    self_w.error.emit(str(e))

        logger.debug("[Logger] _parse_ftrace_async: %s, converter=%s", file_path, converter)
        self.statusBar().showMessage("Parsing ftrace file...", 0)
        worker = _ParseWorker(self)

        def on_finished(df):
            logger.info("[Logger] ftrace parsed: %d rows, %d cols, columns=%s",
                        len(df), len(df.columns), list(df.columns)[:10])
            dataset_name = Path(file_path).stem
            dataset_id = self.engine.load_dataset_from_dataframe(
                df, name=dataset_name, source_path=file_path
            )
            if dataset_id:
                logger.info("[Logger] ftrace dataset created: id=%s", dataset_id)
                self._on_data_loaded()
                self._apply_graph_presets(df, converter)
                self.statusBar().showMessage(
                    f"Ftrace: loaded {len(df)} rows from {Path(file_path).name}",
                    5000,
                )
            else:
                logger.error("[Logger] ftrace load_dataset_from_dataframe returned None")
                QMessageBox.warning(self, "Ftrace Parser", "Failed to load parsed data.")
                self.statusBar().clearMessage()

        def on_error(msg):
            logger.error("[Logger] ftrace parse failed: %s", msg)
            QMessageBox.critical(self, "Ftrace Parser", f"Parse failed:\n{msg}")
            self.statusBar().clearMessage()

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        # prevent GC
        self._parse_worker = worker
        worker.start()

    def _apply_graph_presets(self, df, converter: str = "") -> None:
        """Create DGS profiles from graph presets and apply the first one.

        Each GraphPreset becomes a real GraphSetting (profile) in the
        project's profile_store, visible in the Project Explorer sidebar.
        The first matching preset is auto-applied.

        Args:
            df: The loaded polars DataFrame.
            converter: Converter name (e.g. "blocklayer").
        """
        from data_graph_studio.parsers.graph_preset import BUILTIN_PRESETS
        from data_graph_studio.core.profile import GraphSetting
        from data_graph_studio.core.state import ChartType, AggregationType

        presets = BUILTIN_PRESETS.get(converter, [])
        if not presets:
            logger.debug("[Logger] no presets for converter=%s", converter)
            return

        dataset_id = self.state.active_dataset_id
        if not dataset_id:
            logger.warning("[Logger] no active dataset, cannot create profiles")
            return

        # Skip if profiles already exist for this dataset (avoid duplicates on re-parse)
        existing = self.profile_store.get_by_dataset(dataset_id)
        existing_names = {s.name for s in existing}

        first_profile_id = None
        created_count = 0

        for preset in presets:
            if not preset.columns_present(df):
                logger.debug("[Logger] preset '%s' skipped: columns missing", preset.name)
                continue
            if preset.name in existing_names:
                logger.debug("[Logger] preset '%s' already exists, skipping", preset.name)
                # Use existing profile as first if none yet
                if first_profile_id is None:
                    for s in existing:
                        if s.name == preset.name:
                            first_profile_id = s.id
                            break
                continue

            # Build value_columns as dicts (GraphSettingMapper format)
            value_cols = []
            for col_name in preset.y_columns:
                value_cols.append({
                    "name": col_name,
                    "aggregation": "sum",
                    "color": "#1f77b4",
                    "use_secondary_axis": False,
                    "order": len(value_cols),
                    "formula": "",
                })

            # Build group_columns
            group_cols = []
            if preset.group_column:
                group_cols.append({
                    "name": preset.group_column,
                    "selected_values": [],
                    "order": 0,
                })

            import uuid
            profile_id = str(uuid.uuid4())
            gs = GraphSetting(
                id=profile_id,
                name=preset.name,
                dataset_id=dataset_id,
                chart_type=preset.chart_type,
                x_column=preset.x_column,
                value_columns=tuple(value_cols),
                group_columns=tuple(group_cols),
                icon="📈" if preset.chart_type in ("line", "area") else "📊",
                description=preset.description,
            )
            self.profile_store.add(gs)
            created_count += 1
            logger.info("[Logger] created profile '%s' (id=%s, chart=%s, x=%s, y=%s)",
                        preset.name, profile_id, preset.chart_type,
                        preset.x_column, preset.y_columns)

            if first_profile_id is None:
                first_profile_id = profile_id

        # Refresh project tree to show new profiles
        if created_count > 0 and hasattr(self, 'profile_model'):
            self.profile_model.refresh()
            logger.info("[Logger] %d profiles created for dataset %s", created_count, dataset_id)

        # Apply the first profile
        if first_profile_id:
            try:
                ok = self.profile_controller.apply_profile(first_profile_id)
                if ok:
                    self.graph_panel.refresh()
                    self.graph_panel.autofit()
                    logger.info("[Logger] auto-applied profile: %s", first_profile_id)
                else:
                    logger.warning("[Logger] failed to apply profile: %s", first_profile_id)
            except Exception as e:
                logger.warning("[Logger] error applying profile: %s", e, exc_info=True)

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
        project_name = result.get('project_name')
        
        if graph_setting:
            active_id = self.engine.active_dataset_id
            logger.debug(f"[DEBUG-CRASH] active_id={active_id}, graph_setting={graph_setting}")
            if active_id:
                # 프로젝트 탐색창에 추가
                from dataclasses import replace
                graph_setting = replace(graph_setting, dataset_id=active_id)
                logger.debug(f"[DEBUG-CRASH] profile_store.add() start")
                self.profile_store.add(graph_setting)
                logger.debug(f"[DEBUG-CRASH] profile_store.add() done, profile_model update start")
                self.profile_model.add_profile_incremental(active_id, graph_setting)
                logger.debug(f"[DEBUG-CRASH] profile_model update done")
                
                # 그래프 설정 적용
                try:
                    logger.debug(f"[DEBUG-CRASH] apply_profile() start, id={graph_setting.id}")
                    self.profile_controller.apply_profile(graph_setting.id)
                    logger.debug(f"[DEBUG-CRASH] apply_profile() done")
                    self._schedule_autofit()
                except Exception as e:
                    logger.warning(f"Failed to apply profile: {e}", exc_info=True)
                
                logger.info(f"Wizard result applied: {graph_setting.name}")
                logger.debug(f"[DEBUG-CRASH] after wizard result applied, returning from _apply_pending_wizard_result")

    def _schedule_autofit(self):
        """프로파일 전환/생성 후 그래프를 자동으로 Fit (데이터에 맞춤)."""
        QTimer.singleShot(50, self._do_autofit)

    def _do_autofit(self):
        """실제 autofit 수행."""
        try:
            if hasattr(self, 'graph_panel') and self.engine.is_loaded:
                self.graph_panel.autofit()
        except Exception as e:
            logger.debug(f"Auto-fit after profile switch failed: {e}")

    def _cancel_loading(self):
        self._file_controller._cancel_loading()
    
    def _on_data_loaded(self):
        """데이터 로드 완료"""
        self._update_ui_state()
        
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
    
    def _on_export(self, format: str):
        """내보내기"""
        if not self.state.is_data_loaded:
            return
        
        if format == "csv":
            path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
            if path:
                self.engine.export_csv(path)
        elif format == "excel":
            path, _ = QFileDialog.getSaveFileName(self, "Export Excel", "", "Excel (*.xlsx)")
            if path:
                self.engine.export_excel(path)
        elif format == "png":
            path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG (*.png)")
            if path:
                self.graph_panel.export_image(path)
    
    def _show_about(self):
        """About 다이얼로그"""
        QMessageBox.about(
            self,
            "About Data Graph Studio",
            """<h2>Data Graph Studio</h2>
            <p><b>Version 0.2.0</b></p>
            <p>Big Data Visualization & Analysis Tool</p>
            <hr>
            <p>Features:</p>
            <ul>
                <li>📊 Multiple chart types (Line, Bar, Scatter, Pie, Area, Histogram)</li>
                <li>📁 Support for CSV, Excel, Parquet, JSON</li>
                <li>🔄 Drag & Drop file loading</li>
                <li>📋 Clipboard paste from Excel/Google Sheets</li>
                <li>💾 Profile save/load</li>
                <li>🖥️ CLI & Python API</li>
            </ul>
            <hr>
            <p>© 2026 Godol</p>
            <p><a href='https://github.com/SeokMinKo/data-graph-studio'>GitHub</a></p>
            """
        )
    
    def _show_quick_start(self):
        """Quick Start Guide 다이얼로그"""
        guide = """
        <h2>🚀 Quick Start Guide</h2>
        
        <h3>1. Load Data</h3>
        <ul>
            <li><b>File > Open</b> (Ctrl+O) - Open CSV, Excel, Parquet, JSON</li>
            <li><b>Drag & Drop</b> - Drag files directly into the window</li>
            <li><b>Paste</b> (Ctrl+V) - Paste data from Excel or Google Sheets</li>
        </ul>
        
        <h3>2. Create Chart</h3>
        <ul>
            <li>Select <b>X-axis column</b> from dropdown</li>
            <li>Select <b>Y-axis column(s)</b> from dropdown</li>
            <li>Choose <b>Chart Type</b> from toolbar</li>
        </ul>
        
        <h3>3. Customize</h3>
        <ul>
            <li>Zoom: Mouse wheel or drag to select area</li>
            <li>Pan: Hold right mouse button and drag</li>
            <li>Reset: Double-click on chart</li>
        </ul>
        
        <h3>4. Export</h3>
        <ul>
            <li><b>File > Export</b> - Save as PNG, CSV</li>
            <li><b>Ctrl+Shift+C</b> - Copy chart to clipboard</li>
        </ul>
        
        <h3>5. CLI Usage</h3>
        <pre>dgs plot data.csv -x Time -y Value -o chart.png</pre>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Quick Start Guide")
        msg.setTextFormat(Qt.RichText)
        msg.setText(guide)
        msg.setIcon(QMessageBox.Information)
        msg.exec()
    
    def _on_open_command_palette(self):
        """Open the Command Palette dialog for feature search."""
        dialog = CommandPaletteDialog(self)
        dialog.exec()

    def _show_shortcuts(self):
        """키보드 단축키 다이얼로그"""
        shortcuts = """
        <h2>⌨️ Keyboard Shortcuts</h2>
        
        <h3>📁 File</h3>
        <table>
            <tr><td><b>Ctrl+O</b></td><td>Open file</td></tr>
            <tr><td><b>Ctrl+Shift+O</b></td><td>Open multiple files</td></tr>
            <tr><td><b>Ctrl+S</b></td><td>Save project</td></tr>
            <tr><td><b>Ctrl+E</b></td><td>Export as CSV</td></tr>
        </table>
        
        <h3>✏️ Edit</h3>
        <table>
            <tr><td><b>Ctrl+V</b></td><td>Paste data from clipboard</td></tr>
            <tr><td><b>Ctrl+C</b></td><td>Copy selected cells</td></tr>
            <tr><td><b>Ctrl+Shift+C</b></td><td>Copy chart as image</td></tr>
            <tr><td><b>Ctrl+A</b></td><td>Select all</td></tr>
            <tr><td><b>Escape</b></td><td>Clear selection</td></tr>
        </table>
        
        <h3>📊 Chart</h3>
        <table>
            <tr><td><b>1</b></td><td>Line chart</td></tr>
            <tr><td><b>2</b></td><td>Bar chart</td></tr>
            <tr><td><b>3</b></td><td>Scatter plot</td></tr>
            <tr><td><b>4</b></td><td>Pie chart</td></tr>
            <tr><td><b>5</b></td><td>Area chart</td></tr>
            <tr><td><b>6</b></td><td>Histogram</td></tr>
        </table>
        
        <h3>🔍 Navigation</h3>
        <table>
            <tr><td><b>Mouse Wheel</b></td><td>Zoom in/out</td></tr>
            <tr><td><b>Right Drag</b></td><td>Pan</td></tr>
            <tr><td><b>Double Click</b></td><td>Reset zoom</td></tr>
        </table>
        
        <h3>❓ Help</h3>
        <table>
            <tr><td><b>F1</b></td><td>Quick Start Guide</td></tr>
            <tr><td><b>Ctrl+/</b></td><td>Keyboard Shortcuts</td></tr>
        </table>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Keyboard Shortcuts")
        msg.setTextFormat(Qt.RichText)
        msg.setText(shortcuts)
        msg.setIcon(QMessageBox.Information)
        msg.exec()
    
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
    
    def _show_tips(self):
        """Tips & Tricks 다이얼로그"""
        tips = """
        <h2>💡 Tips & Tricks</h2>
        
        <h3>🚀 Performance</h3>
        <ul>
            <li>Large files? Use <b>Parquet format</b> for 10x faster loading</li>
            <li>Sampling is automatic for datasets > 100K rows</li>
            <li>Use <b>dgs convert</b> CLI to pre-convert large files</li>
        </ul>
        
        <h3>📋 Clipboard Magic</h3>
        <ul>
            <li>Copy data from <b>Excel</b> or <b>Google Sheets</b>, then Ctrl+V</li>
            <li>Data types are auto-detected (numbers, dates, text)</li>
            <li>Ctrl+Shift+C copies chart as image for pasting into docs</li>
        </ul>
        
        <h3>📊 Chart Tips</h3>
        <ul>
            <li>Click on legend items to toggle series visibility</li>
            <li>Select multiple Y columns for comparison charts</li>
            <li>Use Bar chart for categorical X-axis data</li>
        </ul>
        
        <h3>🔧 CLI Power</h3>
        <ul>
            <li><code>dgs info file.csv</code> - Quick data summary</li>
            <li><code>dgs batch ./data/ -o ./charts/</code> - Process all files</li>
            <li><code>dgs watch file.csv -o live.png</code> - Auto-update chart</li>
        </ul>
        
        <h3>🐍 Python API</h3>
        <pre>
from data_graph_studio import plot
plot("data.csv", x="Time", y="Value", output="chart.png")
        </pre>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Tips & Tricks")
        msg.setTextFormat(Qt.RichText)
        msg.setText(tips)
        msg.setIcon(QMessageBox.Information)
        msg.exec()
    
    def _show_whats_new(self):
        """What's New 다이얼로그"""
        whats_new = """
        <h2>🆕 What's New in v0.2</h2>
        
        <h3>✨ New Features</h3>
        <ul>
            <li><b>CLI Tool</b> - Command line interface for automation
                <br><code>dgs plot data.csv -x Time -y Value</code></li>
            <li><b>Python API</b> - Programmatic chart generation
                <br><code>from data_graph_studio import plot</code></li>
            <li><b>REST API Server</b> - HTTP endpoints for integration
                <br><code>dgs server --port 8080</code></li>
            <li><b>Clipboard Support</b> - Paste from Excel/Google Sheets</li>
            <li><b>Drag & Drop</b> - Drop files to load instantly</li>
        </ul>
        
        <h3>🔧 Improvements</h3>
        <ul>
            <li>Better performance with large datasets</li>
            <li>Improved chart rendering</li>
            <li>Enhanced tooltips and help documentation</li>
        </ul>
        
        <h3>📁 Supported Formats</h3>
        <ul>
            <li>CSV, TSV, TXT</li>
            <li>Excel (XLSX, XLS)</li>
            <li>Parquet</li>
            <li>JSON</li>
        </ul>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle("What's New")
        msg.setTextFormat(Qt.RichText)
        msg.setText(whats_new)
        msg.setIcon(QMessageBox.Information)
        msg.exec()
    
    def _open_url(self, url: str):
        """URL 열기"""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    # ==================== Profile / Project File I/O ====================

    # ==================== Profile Menu Actions ====================

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


    def _set_comparison_mode(self, mode: ComparisonMode):
        self._dataset_controller._set_comparison_mode(mode)


    def _update_comparison_mode_actions(self, mode: ComparisonMode):
        self._dataset_controller._update_comparison_mode_actions(mode)


    def _on_comparison_mode_changed(self, mode_value: str):
        self._dataset_controller._on_comparison_mode_changed(mode_value)


    def _on_comparison_started(self, dataset_ids: List[str]):
        self._dataset_controller._on_comparison_started(dataset_ids)


    def _start_overlay_comparison(self, dataset_ids: List[str]):
        self._dataset_controller._start_overlay_comparison(dataset_ids)


    def _show_overlay_stats_widget(self):
        self._dataset_controller._show_overlay_stats_widget()


    def _hide_overlay_stats_widget(self):
        self._dataset_controller._hide_overlay_stats_widget()


    def _show_comparison_stats_panel(self):
        self._dataset_controller._show_comparison_stats_panel()


    def _on_export_comparison_report(self):
        self._dataset_controller._on_export_comparison_report()


    def _start_side_by_side_comparison(self, dataset_ids: List[str]):
        self._dataset_controller._start_side_by_side_comparison(dataset_ids)


    def _start_difference_analysis(self, dataset_ids: List[str]):
        self._dataset_controller._start_difference_analysis(dataset_ids)


    def _show_comparison_view(self, view_widget: QWidget):
        self._dataset_controller._show_comparison_view(view_widget)


    def _remove_comparison_view(self):
        self._dataset_controller._remove_comparison_view()


    def _restore_single_view(self):
        self._dataset_controller._restore_single_view()


    # ==================== Profile Comparison Views ====================

    def _on_profile_comparison_started(self, mode_value: str, profile_ids: list):
        self._dataset_controller._on_profile_comparison_started(mode_value, profile_ids)


    def _on_profile_comparison_ended(self):
        self._dataset_controller._on_profile_comparison_ended()


    # ==================== Streaming ====================

    def _on_start_streaming_dialog(self):
        """Open the streaming configuration dialog and start streaming (FR-B2.1)."""
        if not self.state.is_data_loaded:
            self.statusbar.showMessage("⚠ No data loaded — load data first", 4000)
            return
        initial_path = self._streaming_controller.current_path or ""
        dlg = StreamingDialog(
            self,
            initial_path=initial_path,
            initial_interval_ms=self._streaming_controller.poll_interval_ms,
            initial_mode="tail",
        )
        if dlg.exec() != QDialog.Accepted:
            return

        file_path = dlg.file_path
        if not file_path:
            return

        # Configure and start
        self._streaming_controller.set_poll_interval(dlg.interval_ms)
        ok = self._streaming_controller.start(file_path, mode=dlg.mode)
        if not ok:
            QMessageBox.warning(
                self, "Streaming Error",
                f"Could not start streaming for:\n{file_path}\n\n"
                "The file may not exist or is not accessible.",
            )

    def _on_pause_streaming(self):
        """Toggle pause/resume for streaming."""
        if self._streaming_controller.state == "live":
            self._streaming_controller.pause()
        elif self._streaming_controller.state == "paused":
            self._streaming_controller.resume()

    def _on_stop_streaming(self):
        """Stop the active streaming session."""
        self._streaming_controller.stop()

    @Slot(str)
    def _on_streaming_state_changed(self, new_state: str):
        """Handle streaming state transitions — update toolbar and status bar (FR-B2.4)."""
        is_active = new_state in ("live", "paused")

        # Toolbar buttons
        self._streaming_play_action.setEnabled(new_state != "live")
        self._streaming_play_action.setChecked(new_state == "live")
        self._streaming_pause_action.setEnabled(is_active)
        self._streaming_stop_action.setEnabled(is_active)

        # Pause button label
        if new_state == "paused":
            self._streaming_pause_action.setText("▶")
            self._streaming_pause_action.setToolTip("Resume Streaming")
        else:
            self._streaming_pause_action.setText("⏸")
            self._streaming_pause_action.setToolTip("Pause Streaming")

        # Menu actions
        self._start_streaming_action.setEnabled(new_state == "off")
        self._stop_streaming_action.setEnabled(is_active)

        # Status bar (FR-B2.4)
        if new_state == "live":
            self.statusbar.showMessage("Streaming: 🟢 active", 3000)
        elif new_state == "paused":
            self.statusbar.showMessage("Streaming: ⏸ paused", 3000)
        elif new_state == "off":
            self.statusbar.showMessage("Streaming stopped", 3000)

    @Slot(str, int)
    def _on_streaming_data_updated(self, file_path: str, new_row_count: int):
        """Handle incoming streaming data — reload file and refresh graph."""
        try:
            if not self.engine.is_loaded:
                # First load via engine
                dataset_id = self.engine.load_dataset(file_path)
                if dataset_id:
                    dataset = self.engine.get_dataset(dataset_id)
                    if dataset:
                        memory_bytes = (
                            dataset.df.estimated_size()
                            if dataset and dataset.df is not None
                            else 0
                        )
                        self.state.add_dataset(
                            dataset_id=dataset_id,
                            name=dataset.name if dataset.name else Path(file_path).stem,
                            file_path=file_path,
                            row_count=self.engine.row_count,
                            column_count=self.engine.column_count,
                            memory_bytes=memory_bytes,
                        )
                    self._on_dataset_activated(dataset_id)
                return

            # Re-load the active dataset from disk
            success = self.engine.load_file(file_path, optimize_memory=True)
            if success:
                self.state.set_data_loaded(True, self.engine.row_count)
                self.table_panel.set_data(self.engine.df)
                self.graph_panel.refresh()
                if new_row_count > 0:
                    self.statusbar.showMessage(
                        f"Streaming: +{new_row_count} rows", 2000
                    )
        except Exception as e:
            logger.error(f"Streaming data update error: {e}", exc_info=True)
            self.statusbar.showMessage(f"Streaming error: {e}", 5000)

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
            # 여러 파일 - 첫 번째 파일만 로드 (또는 다중 로드 다이얼로그)
            self._show_new_project_wizard(files[0])
            self.statusBar().showMessage(f"Loaded first file. {len(files)-1} more files ignored.")
    
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
    
    def _paste_from_clipboard(self):
        """클립보드에서 데이터 붙여넣기"""
        if not ClipboardManager.has_table_data():
            self.statusBar().showMessage("No valid table data in clipboard", 3000)
            return
        
        df, message = ClipboardManager.paste_as_dataframe()
        
        if df is not None and len(df) > 0:
            # 데이터 로드
            try:
                # 임시 데이터셋으로 추가
                import uuid
                dataset_id = f"clipboard_{uuid.uuid4().hex[:8]}"
                
                # 엔진에 직접 설정
                self.engine._df = df
                
                # 상태 업데이트
                self.state.set_data_loaded(True, len(df))
                self.state.set_column_order(df.columns)
                
                # UI 업데이트
                self.table_panel.set_data(df)
                self.graph_panel.set_columns(df.columns)
                
                # Data 탭에 컬럼 목록 전달
                if hasattr(self.graph_panel.options_panel, 'data_tab'):
                    self.graph_panel.options_panel.data_tab.set_columns(
                        df.columns, self.engine
                    )
                
                self.statusBar().showMessage(f"✓ {message}", 5000)
                
            except Exception as e:
                self.statusBar().showMessage(f"Paste error: {e}", 5000)
        else:
            self.statusBar().showMessage(message, 3000)
    
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
                        msg = ClipboardManager.copy_text(text)
                        self.statusBar().showMessage(f"✓ Copied {len(rows)} rows", 3000)
                        return
            
            self.statusBar().showMessage("No selection to copy", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"Copy error: {e}", 3000)

    # ==================== New Menu Actions ====================

    def _update_recent_files_menu(self):
        """최근 파일 메뉴 업데이트"""
        self._recent_files_menu.clear()
        
        # 최근 파일 목록 로드 (최대 10개)
        recent_files = self._get_recent_files()
        
        if not recent_files:
            no_files_action = QAction("(No recent files)", self)
            no_files_action.setEnabled(False)
            self._recent_files_menu.addAction(no_files_action)
        else:
            for file_path in recent_files[:10]:
                action = QAction(Path(file_path).name, self)
                action.setToolTip(file_path)
                action.setStatusTip(file_path)
                action.triggered.connect(lambda checked, fp=file_path: self._open_recent_file(fp))
                self._recent_files_menu.addAction(action)
            
            self._recent_files_menu.addSeparator()
            clear_action = QAction("Clear Recent Files", self)
            clear_action.triggered.connect(self._clear_recent_files)
            self._recent_files_menu.addAction(clear_action)

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
            # 중복 제거 후 맨 앞에 추가
            if file_path in recent_files:
                recent_files.remove(file_path)
            recent_files.insert(0, file_path)
            # 최대 20개 유지
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
            QMessageBox.warning(self, "File Not Found", f"File no longer exists:\n{file_path}")
            self._update_recent_files_menu()

    def _clear_recent_files(self):
        """최근 파일 목록 지우기"""
        try:
            recent_file_path = Path.home() / ".data_graph_studio" / "recent_files.json"
            if recent_file_path.exists():
                recent_file_path.unlink()
            self._update_recent_files_menu()
            self.statusbar.showMessage("Recent files cleared", 3000)
        except Exception as e:
            logger.debug(f"Failed to clear recent files: {e}")

    def _on_import_from_clipboard(self):
        """클립보드에서 데이터 직접 임포트"""
        self._paste_from_clipboard()

    def _on_find_data(self):
        """데이터 검색 다이얼로그"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Find", "No data loaded.")
            return
        
        text, ok = QInputDialog.getText(
            self, "Find Data", "Search for:",
            text=""
        )
        if ok and text.strip():
            # 테이블 패널에 검색 요청
            if hasattr(self.table_panel, 'find_text'):
                found = self.table_panel.find_text(text.strip())
                if found:
                    self.statusbar.showMessage(f"Found matches for '{text}'", 3000)
                else:
                    self.statusbar.showMessage(f"No matches found for '{text}'", 3000)
            else:
                self.statusbar.showMessage("Search functionality not available", 3000)

    def _on_goto_row(self):
        """특정 행으로 이동"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Go to Row", "No data loaded.")
            return
        
        max_row = self.engine.row_count
        row, ok = QInputDialog.getInt(
            self, "Go to Row", f"Enter row number (1-{max_row}):",
            value=1, min=1, max=max_row
        )
        if ok:
            if hasattr(self.table_panel, 'goto_row'):
                self.table_panel.goto_row(row - 1)  # 0-indexed
                self.statusbar.showMessage(f"Jumped to row {row}", 3000)
            else:
                self.statusbar.showMessage("Go to row functionality not available", 3000)

    def _on_filter_data(self):
        """필터 패널 토글"""
        # 필터 패널이 있으면 토글, 없으면 생성
        if hasattr(self, 'filter_panel') and self.filter_panel:
            self.filter_panel.setVisible(not self.filter_panel.isVisible())
        else:
            self.statusbar.showMessage("Filter panel toggled", 3000)
            # 필터 패널이 없는 경우 그래프 패널의 필터 기능 활성화
            if hasattr(self.graph_panel, 'toggle_filter'):
                self.graph_panel.toggle_filter()

    def _on_sort_data(self):
        """정렬 다이얼로그"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Sort", "No data loaded.")
            return
        
        columns = self.engine.columns
        column, ok = QInputDialog.getItem(
            self, "Sort Data", "Select column to sort by:",
            columns, 0, False
        )
        if ok and column:
            # 정렬 순서 선택
            orders = ["Ascending", "Descending"]
            order, ok2 = QInputDialog.getItem(
                self, "Sort Order", "Select sort order:",
                orders, 0, False
            )
            if ok2:
                ascending = (order == "Ascending")
                self.statusbar.showMessage(f"Sorted by '{column}' ({order})", 3000)
                # TODO: 실제 정렬 구현
                # self.engine.sort_data(column, ascending)
                # self._on_data_loaded()

    def _on_add_calculated_field(self):
        """계산 필드 추가 다이얼로그 (FR-B3.1, FR-B3.5)."""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Add Calculated Field", "데이터를 먼저 로드하세요.")
            return

        df = self.engine.df
        if df is None or df.is_empty():
            QMessageBox.warning(self, "Add Calculated Field", "No data available.")
            return

        dialog = ComputedColumnDialog(df, parent=self)
        dialog.column_created.connect(self._on_computed_column_created)
        dialog.exec()

    def _on_computed_column_created(self, defn, series):
        """Handle computed column result — add to engine and refresh UI (FR-B3.2)."""
        from ..core.undo_manager import UndoCommand, UndoActionType

        try:
            col_name = defn.name if hasattr(defn, 'name') else str(defn)
            before_df = self.engine.df
            if before_df is None:
                return

            after_df = before_df.with_columns(series.alias(col_name))

            def _apply_df(df):
                # Update engine
                self.engine._df = df

                # Sync state/UI
                try:
                    self.state.set_column_order(self.engine.columns)
                except Exception:
                    pass

                self.table_panel.set_data(df)

                try:
                    self.graph_panel.set_columns(self.engine.columns)
                    if hasattr(self.graph_panel.options_panel, 'data_tab'):
                        self.graph_panel.options_panel.data_tab.set_columns(
                            self.engine.columns, self.engine
                        )
                except Exception:
                    pass

                self.graph_panel.refresh()

            # Apply
            _apply_df(after_df)

            # Record undo/redo
            self._undo_stack.record(
                UndoCommand(
                    action_type=UndoActionType.COLUMN_ADD,
                    description=f"Add computed column '{col_name}'",
                    do=lambda: _apply_df(after_df),
                    undo=lambda: _apply_df(before_df),
                    timestamp=time.time(),
                )
            )

            self.statusbar.showMessage(f"Computed column '{col_name}' added", 3000)
        except Exception as e:
            logger.error(f"Failed to add computed column: {e}", exc_info=True)
            QMessageBox.warning(self, "Add Calculated Field", f"Failed to add column:\n{e}")

    def _on_remove_duplicates(self):
        """중복 제거"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Remove Duplicates", "No data loaded.")
            return
        
        reply = QMessageBox.question(
            self, "Remove Duplicates",
            f"This will remove duplicate rows from the data.\n"
            f"Current rows: {self.engine.row_count:,}\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # TODO: 실제 중복 제거 구현
            self.statusbar.showMessage("Duplicate removal feature coming soon", 3000)

    def _on_data_summary(self):
        """데이터 요약 다이얼로그"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Data Summary", "No data loaded.")
            return
        
        # 간단한 요약 정보 표시
        summary = f"""
        <h2>Data Summary</h2>
        <table>
            <tr><td><b>Rows:</b></td><td>{self.engine.row_count:,}</td></tr>
            <tr><td><b>Columns:</b></td><td>{self.engine.column_count}</td></tr>
        </table>
        <h3>Columns:</h3>
        <ul>
        """
        for col in self.engine.columns[:20]:  # 최대 20개만 표시
            summary += f"<li>{col}</li>"
        if len(self.engine.columns) > 20:
            summary += f"<li>... and {len(self.engine.columns) - 20} more</li>"
        summary += "</ul>"
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Data Summary")
        msg.setTextFormat(Qt.RichText)
        msg.setText(summary)
        msg.setIcon(QMessageBox.Information)
        msg.exec()

    def _on_zoom_in(self):
        """줌 인"""
        if hasattr(self.graph_panel, 'zoom_in'):
            self.graph_panel.zoom_in()
        else:
            self.statusbar.showMessage("Zoom in", 2000)

    def _on_zoom_out(self):
        """줌 아웃"""
        if hasattr(self.graph_panel, 'zoom_out'):
            self.graph_panel.zoom_out()
        else:
            self.statusbar.showMessage("Zoom out", 2000)

    def _on_toggle_fullscreen(self):
        """전체 화면 토글"""
        if self.isFullScreen():
            self.showNormal()
            self._fullscreen_action.setChecked(False)
        else:
            self.showFullScreen()
            self._fullscreen_action.setChecked(True)

    def _on_theme_changed(self, theme_id: str):
        """테마 변경 + QSettings 저장"""
        from .theme import ThemeManager
        
        # 테마 액션 상태 업데이트
        for tid, action in self._theme_actions.items():
            action.setChecked(tid == theme_id)
        
        # 테마 적용
        if not hasattr(self, '_theme_manager'):
            self._theme_manager = ThemeManager()
        
        self._theme_manager.set_theme(theme_id)
        self._current_theme = theme_id
        stylesheet = self._theme_manager.generate_stylesheet()
        QApplication.instance().setStyleSheet(stylesheet)
        
        # Apply theme to graph panel components
        is_light = self._theme_manager.current_theme.is_light()
        if hasattr(self, 'graph_panel'):
            # Main graph
            if hasattr(self.graph_panel, 'main_graph'):
                self.graph_panel.main_graph.apply_theme(is_light)
            # Stat panel mini-graphs
            if hasattr(self.graph_panel, 'stat_panel'):
                self.graph_panel.stat_panel.apply_theme(is_light)

        # Persist to QSettings (B-6)
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings("Godol", "DataGraphStudio")
            settings.setValue("appearance/theme", theme_id)
        except Exception:
            pass
        
        self.statusbar.showMessage(f"Theme changed to {theme_id.title()}", 3000)

    def _on_toggle_grid(self, checked: bool):
        """그리드 표시 토글"""
        if hasattr(self.graph_panel, 'set_grid_visible'):
            self.graph_panel.set_grid_visible(checked)
        self.statusbar.showMessage(f"Grid {'shown' if checked else 'hidden'}", 2000)

    def _on_toggle_legend(self, checked: bool):
        """범례 표시 토글"""
        if hasattr(self.graph_panel, 'set_legend_visible'):
            self.graph_panel.set_legend_visible(checked)
        self.statusbar.showMessage(f"Legend {'shown' if checked else 'hidden'}", 2000)

    def _on_add_trend_line(self):
        """추세선 추가"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Add Trend Line", "No data loaded.")
            return
        
        types = ["Linear", "Polynomial (2nd)", "Polynomial (3rd)", "Exponential", "Logarithmic"]
        trend_type, ok = QInputDialog.getItem(
            self, "Add Trend Line", "Select trend line type:",
            types, 0, False
        )
        if ok:
            self.statusbar.showMessage(f"Adding {trend_type} trend line...", 3000)
            # TODO: 실제 추세선 추가 구현
            # self.graph_panel.add_trend_line(trend_type)

    def _on_curve_fitting(self):
        """곡선 피팅 설정"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Curve Fitting", "No data loaded.")
            return
        
        QMessageBox.information(
            self, "Curve Fitting",
            "Curve fitting dialog will be implemented.\n\n"
            "This feature allows you to fit various curves to your data."
        )

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
        """Save Data - 현재 데이터 저장"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Save Data", "No data loaded.")
            return
        
        # 현재 로드된 파일 경로가 있으면 그대로 저장
        current_path = getattr(self.engine, '_current_file_path', None)
        if current_path:
            try:
                self.engine.df.write_csv(current_path)
                self.statusbar.showMessage(f"Data saved to {current_path}", 3000)
            except Exception as e:
                QMessageBox.warning(self, "Save Data", f"Failed to save: {e}")
        else:
            # 경로가 없으면 Save As로 전환
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
        sources = ["From File...", "From Clipboard", "From URL...", "From Database..."]
        source, ok = QInputDialog.getItem(
            self, "Import Data", "Select import source:",
            sources, 0, False
        )
        if ok:
            if source == "From File...":
                self._on_open_file()
            elif source == "From Clipboard":
                self._on_import_from_clipboard()
            elif source == "From URL...":
                url, url_ok = QInputDialog.getText(
                    self, "Import from URL", "Enter URL:"
                )
                if url_ok and url:
                    self.statusbar.showMessage(f"Importing from {url}...", 3000)
                    # TODO: URL에서 데이터 로드 구현
            elif source == "From Database...":
                QMessageBox.information(
                    self, "Import from Database",
                    "Database import will be implemented.\n\n"
                    "Supported: PostgreSQL, MySQL, SQLite, etc."
                )

    # ============================================================
    # New Menu Action Methods (View Menu - Graph Elements)
    # ============================================================

    def _on_toggle_statistics_overlay(self, checked: bool = None):
        """통계 오버레이 표시 토글"""
        if checked is None:
            checked = self._graph_element_actions.get("statistics_overlay", QAction()).isChecked()
        
        if hasattr(self.graph_panel, 'set_statistics_overlay_visible'):
            self.graph_panel.set_statistics_overlay_visible(checked)
        self.statusbar.showMessage(f"Statistics overlay {'shown' if checked else 'hidden'}", 2000)

    def _on_toggle_axis_labels(self, checked: bool = None):
        """축 레이블 표시 토글"""
        if checked is None:
            checked = self._graph_element_actions.get("axis_labels", QAction()).isChecked()
        
        if hasattr(self.graph_panel, 'set_axis_labels_visible'):
            self.graph_panel.set_axis_labels_visible(checked)
        self.statusbar.showMessage(f"Axis labels {'shown' if checked else 'hidden'}", 2000)

    def _on_drawing_style(self):
        if hasattr(self, 'graph_panel') and self.graph_panel is not None:
            self.graph_panel.show_drawing_style_dialog()

    def _on_delete_drawing(self):
        if hasattr(self, 'graph_panel') and self.graph_panel is not None:
            self.graph_panel.delete_selected_drawing()

    def _on_clear_drawings(self):
        if hasattr(self, 'graph_panel') and self.graph_panel is not None:
            self.graph_panel.clear_drawings()

    def _on_draw_color_pick(self):
        """Open color picker for draw color"""
        color = QColorDialog.getColor(
            self._draw_color, self, "Draw Color"
        )
        if color.isValid():
            self._draw_color = color
            self._update_draw_color_btn()
            # Apply to graph panel's current drawing style
            if hasattr(self, 'graph_panel') and self.graph_panel is not None:
                self.graph_panel.set_drawing_color(color.name())

    def _update_draw_color_btn(self):
        """Update draw color button appearance"""
        self._draw_color_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self._draw_color.name()};
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
            checked = self._table_element_actions.get("row_numbers", QAction()).isChecked()
        
        if hasattr(self.table_panel, 'set_row_numbers_visible'):
            self.table_panel.set_row_numbers_visible(checked)
        else:
            # 대안: 테이블 뷰의 행 헤더 숨기기/보이기
            if hasattr(self.table_panel, 'table_view'):
                self.table_panel.table_view.verticalHeader().setVisible(checked)
        self.statusbar.showMessage(f"Row numbers {'shown' if checked else 'hidden'}", 2000)

    def _on_toggle_column_headers(self, checked: bool = None):
        """열 헤더 표시 토글"""
        if checked is None:
            checked = self._table_element_actions.get("column_headers", QAction()).isChecked()
        
        if hasattr(self.table_panel, 'set_column_headers_visible'):
            self.table_panel.set_column_headers_visible(checked)
        else:
            # 대안: 테이블 뷰의 열 헤더 숨기기/보이기
            if hasattr(self.table_panel, 'table_view'):
                self.table_panel.table_view.horizontalHeader().setVisible(checked)
        self.statusbar.showMessage(f"Column headers {'shown' if checked else 'hidden'}", 2000)

    def _on_toggle_filter_bar(self, checked: bool = None):
        """필터 바 표시 토글"""
        if checked is None:
            checked = self._table_element_actions.get("filter_bar", QAction()).isChecked()
        
        if hasattr(self.table_panel, 'set_filter_bar_visible'):
            self.table_panel.set_filter_bar_visible(checked)
        self.statusbar.showMessage(f"Filter bar {'shown' if checked else 'hidden'}", 2000)

    # ============================================================
    # New Menu Action Methods (View Menu - Multi-Grid)
    # ============================================================

    def _on_multi_grid_view(self):
        """Multi-Grid View - 여러 그래프를 그리드로 표시"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Multi-Grid View", "No data loaded.")
            return
        
        # 그리드 설정 다이얼로그
        layouts = ["2x1 (Horizontal)", "1x2 (Vertical)", "2x2 (Grid)", "3x2 (Wide Grid)", "Custom..."]
        layout, ok = QInputDialog.getItem(
            self, "Multi-Grid View", "Select grid layout:",
            layouts, 2, False
        )
        if ok:
            if layout == "Custom...":
                # 커스텀 그리드 설정
                rows, rows_ok = QInputDialog.getInt(self, "Custom Grid", "Number of rows:", 2, 1, 10)
                if rows_ok:
                    cols, cols_ok = QInputDialog.getInt(self, "Custom Grid", "Number of columns:", 2, 1, 10)
                    if cols_ok:
                        self.statusbar.showMessage(f"Multi-grid view: {rows}x{cols}", 3000)
            else:
                self.statusbar.showMessage(f"Multi-grid view: {layout}", 3000)
            
            # TODO: 실제 멀티 그리드 뷰 구현
            # self._floating_graph_manager.create_grid_view(rows, cols)

    # ============================================================
    # New Menu Action Methods (Data Menu)
    # ============================================================

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
                    self.engine._df = self.engine.df.drop(column)
                    self.table_panel.set_data(self.engine.df)
                    self.graph_panel.refresh()
                    self.statusbar.showMessage(f"Column '{column}' removed", 3000)
                except Exception as e:
                    QMessageBox.warning(self, "Remove Field", f"Failed to remove column: {e}")

    # ============================================================
    # New Menu Action Methods (Graph Menu - Options)
    # ============================================================

    def _on_axis_settings(self):
        """Axis Settings - 축 설정 다이얼로그"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Axis Settings", "No data loaded.")
            return
        
        QMessageBox.information(
            self, "Axis Settings",
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
        if self._dashboard_toggling:
            return
        self._dashboard_toggling = True
        try:
            if not self.state.is_data_loaded:
                QMessageBox.information(self, "Dashboard Mode", "No datasets loaded.")
                self._dashboard_mode_action.setChecked(False)
                return

            if self._dashboard_mode_active:
                self._deactivate_dashboard_mode()
            else:
                self._activate_dashboard_mode()
        finally:
            self._dashboard_toggling = False

    def _activate_dashboard_mode(self):
        """Activate dashboard mode — show DashboardPanel (FR-B1.1, FR-B1.7)."""
        if not self._dashboard_controller.activate():
            QMessageBox.warning(
                self, "Dashboard Mode",
                "Cannot activate dashboard mode. No datasets loaded."
            )
            self._dashboard_mode_action.setChecked(False)
            return

        # Lazy create once (FR-B1.7)
        if self._dashboard_panel is None:
            self._dashboard_panel = DashboardPanel(
                controller=self._dashboard_controller,
                parent=self,
            )
            self._dashboard_panel.exit_requested.connect(self._deactivate_dashboard_mode)
            self._dashboard_panel.cell_clicked.connect(self._on_dashboard_cell_clicked)
            self._dashboard_panel.preset_changed.connect(self._on_dashboard_preset_changed)
            # Populate initial layout
            layout = self._dashboard_controller.current_layout
            if layout:
                self._dashboard_panel.populate(layout)

        # Hide normal panels, show dashboard (visibility toggle only)
        self.graph_panel.hide()
        if self._dashboard_panel.parent() != self.main_splitter:
            self.main_splitter.insertWidget(0, self._dashboard_panel)
        self._dashboard_panel.show()

        self._dashboard_mode_active = True
        self._dashboard_mode_action.setChecked(True)
        self.statusbar.showMessage("Dashboard mode activated — Esc to exit", 3000)

    def _deactivate_dashboard_mode(self):
        """Deactivate dashboard mode — restore normal view (FR-B1.5: state kept)."""
        self._dashboard_controller.deactivate()

        if self._dashboard_panel is not None:
            self._dashboard_panel.hide()
        self.graph_panel.show()

        self._dashboard_mode_active = False
        self._dashboard_mode_action.setChecked(False)
        self.statusbar.showMessage("Dashboard mode deactivated", 3000)

    def _on_dashboard_cell_clicked(self, row: int, col: int):
        """Handle empty cell click — show profile selection dialog (FR-B1.2)."""
        profiles = self.profile_store.get_all()
        if not profiles:
            QMessageBox.information(self, "Dashboard", "No profiles available. Create a profile first.")
            return

        names = [p.name for p in profiles]
        name, ok = QInputDialog.getItem(
            self, "Select Profile", f"Profile for cell ({row}, {col}):", names, 0, False
        )
        if ok and name:
            idx = names.index(name)
            profile = profiles[idx]
            # Ensure cell exists, then assign
            cell = self._dashboard_controller.get_cell(row, col)
            if cell is None:
                self._dashboard_controller.add_cell(row, col, profile_id=profile.id)
            else:
                self._dashboard_controller.assign_profile(row, col, profile.id)
            # Refresh the panel
            layout = self._dashboard_controller.current_layout
            if layout and self._dashboard_panel:
                self._dashboard_panel.populate(layout)

    def _on_dashboard_preset_changed(self, preset_name: str):
        """Handle layout preset change (FR-B1.3)."""
        layout = self._dashboard_controller.apply_preset(preset_name)
        if layout and self._dashboard_panel:
            self._dashboard_panel.populate(layout)

    def _on_toggle_annotation_panel(self):
        """Toggle annotation side panel (v2 Feature 5)"""
        if self._annotation_panel is None:
            # Create annotation panel
            self._annotation_panel = AnnotationPanel(
                controller=self._annotation_controller,
                parent=self,
            )
            # Connect signals
            self._annotation_panel.navigate_requested.connect(self._on_annotation_navigate)
            self._annotation_panel.edit_requested.connect(self._on_annotation_edit)
            self._annotation_panel.delete_requested.connect(self._on_annotation_delete)

        if self._annotation_panel.isVisible():
            self._annotation_panel.hide()
            self._annotation_panel_action.setChecked(False)
            self.statusbar.showMessage("Annotations panel hidden", 2000)
        else:
            # Add to right side of root splitter (horizontal)
            if self._annotation_panel.parent() != self.root_splitter:
                self.root_splitter.addWidget(self._annotation_panel)
            self._annotation_panel.show()
            self._annotation_panel_action.setChecked(True)
            self.statusbar.showMessage("Annotations panel shown", 2000)

    def _on_annotation_navigate(self, annotation_id: str):
        """Navigate to annotation location on chart"""
        annotation = self._annotation_controller.get(annotation_id)
        if annotation and hasattr(self.graph_panel, 'navigate_to_point'):
            self.graph_panel.navigate_to_point(annotation.x, annotation.y)

    def _on_annotation_edit(self, annotation_id: str):
        """Edit annotation via dialog"""
        annotation = self._annotation_controller.get(annotation_id)
        if annotation:
            text, ok = QInputDialog.getText(
                self, "Edit Annotation", "Text:", text=annotation.text
            )
            if ok and text:
                self._annotation_controller.edit(annotation_id, text=text)
                if self._annotation_panel:
                    self._annotation_panel.refresh()

    def _on_annotation_delete(self, annotation_id: str):
        """Delete annotation"""
        reply = QMessageBox.question(
            self, "Delete Annotation",
            "Are you sure you want to delete this annotation?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._annotation_controller.delete(annotation_id)
            if self._annotation_panel:
                self._annotation_panel.refresh()

    def _on_add_annotation(self):
        """Add a new annotation (Ctrl+Shift+N or context menu)"""
        # Check if graph is displayed
        if not self.state.is_data_loaded:
            self.statusbar.showMessage("⚠ Load data and display a graph first", 3000)
            return
        if not self.state.value_columns and not self.state.x_column:
            self.statusbar.showMessage("⚠ Display a graph first before adding annotations", 3000)
            return

        text, ok = QInputDialog.getText(self, "Add Annotation", "Annotation text:")
        if ok and text:
            import uuid
            from ..core.annotation import Annotation
            ann = Annotation(
                id=uuid.uuid4().hex[:12],
                kind="point",
                x=0.0,
                y=0.0,
                text=text,
                dataset_id=self.state.active_dataset_id or "",
                profile_id=self.profile_controller.active_profile_id if hasattr(self.profile_controller, 'active_profile_id') else "",
            )
            try:
                self._annotation_controller.add(ann)
                # Ensure panel is visible
                if self._annotation_panel is None or not self._annotation_panel.isVisible():
                    self._on_toggle_annotation_panel()
                if self._annotation_panel:
                    self._annotation_panel.refresh()
                self.statusbar.showMessage(f"Annotation added: {text[:30]}", 3000)
            except ValueError as e:
                self.statusbar.showMessage(f"⚠ {e}", 3000)

    # ============================================================
    # B-4: Export Wiring
    # ============================================================

    def _update_export_menu_state(self):
        """Enable/disable export menu items based on data/graph state"""
        has_data = self.state.is_data_loaded
        has_graph = has_data and (bool(self.state.value_columns) or bool(self.state.x_column))

        # Image export requires a graph
        for action in (self._export_image_png_action, self._export_image_svg_action):
            action.setEnabled(has_graph)

        # Data export requires data
        for action in (self._export_data_csv_action, self._export_data_excel_action,
                       self._export_data_parquet_action):
            action.setEnabled(has_data)

        # Report export requires data
        for action in (self._export_report_html_action, self._export_report_pptx_action):
            action.setEnabled(has_data)

        # Quick export
        self._export_quick_action.setEnabled(has_data)

    def _on_export_dialog(self):
        """Open ExportDialog (Ctrl+E)"""
        if not self.state.is_data_loaded:
            self.statusbar.showMessage("⚠ No data loaded", 3000)
            return

        from .dialogs.export_dialog import ExportDialog
        mode = "chart" if (self.state.value_columns or self.state.x_column) else "data"
        dlg = ExportDialog(self, mode=mode)

        # Connect dialog signals to controller
        def _handle_export(fmt, path, opts):
            if mode == "chart":
                image = self._capture_graph_image()
                if image and not image.isNull():
                    self._export_controller.export_chart_async(image, path, fmt, opts)
                else:
                    dlg.on_export_failed("No chart image available")
            else:
                df = self.engine.df
                if df is not None:
                    self._export_controller.export_data_async(df, path, fmt, opts)
                else:
                    dlg.on_export_failed("No data available")

        dlg.export_requested.connect(_handle_export)
        self._export_controller.progress_changed.connect(dlg.update_progress)
        self._export_controller.export_completed.connect(dlg.on_export_completed)
        self._export_controller.export_failed.connect(dlg.on_export_failed)

        dlg.exec()

    def _on_export_image(self, fmt: "ExportFormat"):
        """Export chart as image (PNG/SVG)"""
        if not self.state.is_data_loaded:
            return

        ext_map = {ExportFormat.PNG: ("PNG Files (*.png)", ".png"),
                   ExportFormat.SVG: ("SVG Files (*.svg)", ".svg")}
        filter_str, ext = ext_map.get(fmt, ("All Files (*)", ""))
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.value.upper()}", f"chart{ext}", filter_str)
        if not path:
            return

        image = self._capture_graph_image()
        if image is None or image.isNull():
            self.statusbar.showMessage("⚠ No chart to export", 3000)
            return

        self._export_controller.export_completed.connect(
            lambda p: self.statusbar.showMessage(f"✓ Exported to {p}", 3000))
        self._export_controller.export_failed.connect(
            lambda e: self.statusbar.showMessage(f"⚠ Export failed: {e}", 5000))
        self._export_controller.export_chart_async(image, path, fmt)

    def _on_export_data(self, fmt: "ExportFormat"):
        """Export data (CSV/Excel/Parquet)"""
        if not self.state.is_data_loaded or self.engine.df is None:
            return

        ext_map = {ExportFormat.CSV: ("CSV Files (*.csv)", ".csv"),
                   ExportFormat.EXCEL: ("Excel Files (*.xlsx)", ".xlsx"),
                   ExportFormat.PARQUET: ("Parquet Files (*.parquet)", ".parquet")}
        filter_str, ext = ext_map.get(fmt, ("All Files (*)", ""))
        path, _ = QFileDialog.getSaveFileName(self, f"Export {fmt.value.upper()}", f"data{ext}", filter_str)
        if not path:
            return

        self._export_controller.export_completed.connect(
            lambda p: self.statusbar.showMessage(f"✓ Exported to {p}", 3000))
        self._export_controller.export_failed.connect(
            lambda e: self.statusbar.showMessage(f"⚠ Export failed: {e}", 5000))
        self._export_controller.export_data_async(self.engine.df, path, fmt)

    def _capture_graph_image(self):
        """Capture the current graph panel as QImage"""
        try:
            if hasattr(self.graph_panel, 'main_graph') and self.graph_panel.main_graph:
                from pyqtgraph.exporters import ImageExporter
                from PySide6.QtGui import QImage
                import tempfile, os
                exporter = ImageExporter(self.graph_panel.main_graph.plotItem)
                exporter.parameters()['width'] = 1920
                temp_path = os.path.join(tempfile.gettempdir(), 'dgs_export_temp.png')
                exporter.export(temp_path)
                image = QImage(temp_path)
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                return image
        except Exception as e:
            logger.warning(f"Failed to capture graph image: {e}")
        return None

    # ============================================================
    # B-6: Theme Persistence
    # ============================================================

    def _auto_check_updates(self, force_ui: bool = False):
        """Installer-based auto-update for Windows.

        - Checks GitHub latest release for an installer asset
        - If newer version: optionally downloads and launches installer

        NOTE: This is a pragmatic approach. True background patching is out of scope.
        """
        import sys
        from PySide6.QtCore import QSettings

        if sys.platform != "win32":
            return

        settings = QSettings("Godol", "DataGraphStudio")
        auto = settings.value("updates/auto", True, type=bool)
        if not auto and not force_ui:
            return

        current = get_current_version()
        try:
            info = check_github_latest()
        except Exception as e:
            if force_ui:
                QMessageBox.information(self, "Updates", f"Update check failed:\n{e}")
            return

        if not info:
            if force_ui:
                QMessageBox.information(self, "Updates", "No installer asset found in the latest release.")
            return

        if not is_update_available(current, info.latest_version):
            if force_ui:
                QMessageBox.information(self, "Updates", f"You're up to date.\nCurrent: {current}")
            return

        # Update available
        msg = (
            f"Update available: {current} → {info.latest_version}\n\n"
            "Download and install now?\n"
            "(The app may close and reopen after installation.)"
        )
        if not auto or force_ui:
            res = QMessageBox.question(self, "Updates", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if res != QMessageBox.StandardButton.Yes:
                return

        try:
            self.statusbar.showMessage(f"Downloading update {info.latest_version}...", 5000)
            installer_path = download_asset(info.asset_url, info.asset_name)
            sha_path = download_asset(info.sha256_url, info.sha256_name)

            expected = read_sha256_file(sha_path)
            actual = sha256sum(installer_path)
            if not expected or expected != actual:
                raise RuntimeError(
                    "Checksum verification failed.\n"
                    f"Expected: {expected}\n"
                    f"Actual:   {actual}"
                )

            self.statusbar.showMessage("Launching installer...", 5000)
            run_windows_installer(installer_path, silent=True)
            self.close()
        except Exception as e:
            QMessageBox.warning(self, "Updates", f"Update failed:\n{e}")

    def _restore_saved_theme(self):
        """Restore theme from QSettings, default to midnight"""
        from PySide6.QtCore import QSettings
        settings = QSettings("Godol", "DataGraphStudio")
        theme_id = settings.value("appearance/theme", "midnight", type=str)
        if theme_id not in ("light", "dark", "midnight"):
            theme_id = "midnight"
        self._on_theme_changed(theme_id)

    def _on_cycle_theme(self):
        """Cycle through themes: light → dark → midnight → light (Ctrl+T)"""
        cycle = ["light", "dark", "midnight"]
        current = getattr(self, '_current_theme', 'midnight')
        try:
            idx = cycle.index(current)
        except ValueError:
            idx = -1
        next_theme = cycle[(idx + 1) % len(cycle)]
        self._on_theme_changed(next_theme)

    # ============================================================
    # B-7: Shortcut Wiring
    # ============================================================

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
        logger.info(f"Shortcut '{shortcut_id}' changed to '{new_keys}'")
