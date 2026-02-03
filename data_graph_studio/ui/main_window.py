"""
Main Window - 메인 윈도우 및 레이아웃
"""

import os
import gc
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QMenu, QToolBar, QStatusBar, QFileDialog, QMessageBox,
    QProgressDialog, QApplication, QLabel, QDialog, QFrame, QComboBox,
    QInputDialog, QTabWidget
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence

from ..core.data_engine import DataEngine, LoadingProgress, FileType, DelimiterType
from ..core.state import AppState, ToolMode, ChartType, ComparisonMode, AggregationType
from ..core.comparison_report import ComparisonReport
from ..core.ipc_server import IPCServer
from ..core.clipboard_manager import ClipboardManager, DragDropHandler
from ..utils.memory import MemoryMonitor

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
from .dialogs.parsing_preview_dialog import ParsingPreviewDialog
from ..core.parsing import ParsingSettings
from .dialogs.save_setting_dialog import SaveSettingDialog
from .dialogs.profile_manager_dialog import ProfileManagerDialog
from .dialogs.multi_file_dialog import open_multi_file_dialog
from .floatable import FloatWindow
from .floating_graph import FloatingGraphWindow, FloatingGraphManager
from ..core.profile import Profile, GraphSetting, ProfileManager
from ..core.profile_store import ProfileStore
from ..core.profile_controller import ProfileController
from .models.profile_model import ProfileModel
from .views.project_tree_view import ProjectTreeView
from .wizards.new_project_wizard import NewProjectWizard


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

        # Floating graph manager
        self._floating_graph_manager: Optional[FloatingGraphManager] = None

        # Setup UI
        self._setup_window()
        self._setup_menubar()
        self._setup_main_layout()  # Must be before toolbar (toolbar references dataset_manager)
        self._setup_toolbar()
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

        # Apply initial theme (reduce glare, improve readability)
        self._on_theme_changed("midnight")

        # Apply initial state
        self._update_ui_state()
    
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

        # Open Settings
        open_settings_action = QAction("Open &Settings...", self)
        open_settings_action.setShortcut("Ctrl+Alt+O")
        open_settings_action.setStatusTip("Load a saved settings/profile file (Ctrl+Alt+O)")
        open_settings_action.triggered.connect(self._on_open_settings)
        file_menu.addAction(open_settings_action)

        # Open Settings Bundle
        open_bundle_action = QAction("Open Settings &Bundle...", self)
        open_bundle_action.setStatusTip("Load a settings bundle (multiple settings)")
        open_bundle_action.triggered.connect(self._on_open_settings_bundle)
        file_menu.addAction(open_bundle_action)

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

        # Save Settings
        save_settings_action = QAction("Save Settings", self)
        save_settings_action.setStatusTip("Save current settings/profile")
        save_settings_action.triggered.connect(self._on_save_settings)
        file_menu.addAction(save_settings_action)

        # Save Settings As
        save_settings_as_action = QAction("Save Settings As...", self)
        save_settings_as_action.setStatusTip("Save current settings to a new file")
        save_settings_as_action.triggered.connect(self._on_save_settings_as)
        file_menu.addAction(save_settings_as_action)

        # Save Settings Bundle
        save_bundle_action = QAction("Save Settings Bundle", self)
        save_bundle_action.setStatusTip("Save current settings bundle")
        save_bundle_action.triggered.connect(self._on_save_settings_bundle)
        file_menu.addAction(save_bundle_action)

        # Save Settings Bundle As
        save_bundle_as_action = QAction("Save Settings Bundle As...", self)
        save_bundle_as_action.setStatusTip("Save current settings bundle to a new file")
        save_bundle_as_action.triggered.connect(self._on_save_settings_bundle_as)
        file_menu.addAction(save_bundle_as_action)

        file_menu.addSeparator()

        # Export Report
        export_report_action = QAction("&Export Report...", self)
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
        legend_action.setCheckable(True)
        legend_action.setChecked(True)
        legend_action.triggered.connect(self._on_toggle_legend)
        graph_elements_menu.addAction(legend_action)
        self._graph_element_actions["legend"] = legend_action
        self._show_legend_action = legend_action
        
        grid_action = QAction("Grid", self)
        grid_action.setCheckable(True)
        grid_action.setChecked(True)
        grid_action.triggered.connect(self._on_toggle_grid)
        graph_elements_menu.addAction(grid_action)
        self._graph_element_actions["grid"] = grid_action
        self._show_grid_action = grid_action
        
        statistics_overlay_action = QAction("Statistics Overlay", self)
        statistics_overlay_action.setCheckable(True)
        statistics_overlay_action.setChecked(False)
        statistics_overlay_action.triggered.connect(self._on_toggle_statistics_overlay)
        graph_elements_menu.addAction(statistics_overlay_action)
        self._graph_element_actions["statistics_overlay"] = statistics_overlay_action
        
        axis_labels_action = QAction("Axis Labels", self)
        axis_labels_action.setCheckable(True)
        axis_labels_action.setChecked(True)
        axis_labels_action.triggered.connect(self._on_toggle_axis_labels)
        graph_elements_menu.addAction(axis_labels_action)
        self._graph_element_actions["axis_labels"] = axis_labels_action

        graph_elements_menu.addSeparator()
        drawing_style_action = QAction("Drawing Style...", self)
        drawing_style_action.triggered.connect(self._on_drawing_style)
        graph_elements_menu.addAction(drawing_style_action)

        delete_drawing_action = QAction("Delete Selected Drawing", self)
        delete_drawing_action.setShortcut("Delete")
        delete_drawing_action.triggered.connect(self._on_delete_drawing)
        graph_elements_menu.addAction(delete_drawing_action)

        clear_drawings_action = QAction("Clear All Drawings", self)
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
        row_numbers_action.setCheckable(True)
        row_numbers_action.setChecked(True)
        row_numbers_action.triggered.connect(self._on_toggle_row_numbers)
        table_elements_menu.addAction(row_numbers_action)
        self._table_element_actions["row_numbers"] = row_numbers_action
        
        column_headers_action = QAction("Column Headers", self)
        column_headers_action.setCheckable(True)
        column_headers_action.setChecked(True)
        column_headers_action.triggered.connect(self._on_toggle_column_headers)
        table_elements_menu.addAction(column_headers_action)
        self._table_element_actions["column_headers"] = column_headers_action
        
        filter_bar_action = QAction("Filter Bar", self)
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

        # Theme submenu
        theme_menu = view_menu.addMenu("&Theme")
        self._theme_actions = {}

        light_theme_action = QAction("Light", self)
        light_theme_action.setCheckable(True)
        light_theme_action.setChecked(False)
        light_theme_action.triggered.connect(lambda: self._on_theme_changed("light"))
        theme_menu.addAction(light_theme_action)
        self._theme_actions["light"] = light_theme_action

        dark_theme_action = QAction("Dark", self)
        dark_theme_action.setCheckable(True)
        dark_theme_action.triggered.connect(lambda: self._on_theme_changed("dark"))
        theme_menu.addAction(dark_theme_action)
        self._theme_actions["dark"] = dark_theme_action

        midnight_theme_action = QAction("Midnight", self)
        midnight_theme_action.setCheckable(True)
        midnight_theme_action.setChecked(True)
        midnight_theme_action.triggered.connect(lambda: self._on_theme_changed("midnight"))
        theme_menu.addAction(midnight_theme_action)
        self._theme_actions["midnight"] = midnight_theme_action

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
    
    def _setup_toolbar(self):
        """Compact toolbar setup"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        # Style handled by global theme stylesheet
        self.addToolBar(toolbar)
        
        # Open file button with modern style
        open_btn = QAction("📂  Open", self)
        open_btn.setToolTip(self._format_tooltip("Open File", "Ctrl+O"))
        open_btn.triggered.connect(self._on_open_file)
        toolbar.addAction(open_btn)

        save_profile_btn = QAction("💾  Save Profile", self)
        save_profile_btn.setToolTip(self._format_tooltip("Save Graph Profile", ""))
        save_profile_btn.triggered.connect(lambda: self.dataset_manager._on_save_profile())
        toolbar.addAction(save_profile_btn)

        load_profile_btn = QAction("📂  Load Profile", self)
        load_profile_btn.setToolTip(self._format_tooltip("Load Graph Profile", ""))
        load_profile_btn.triggered.connect(lambda: self.dataset_manager._on_load_profile())
        toolbar.addAction(load_profile_btn)

        toolbar.addSeparator()

        # Graph tools with modern icons
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
        
        # Default to Pan
        self._tool_actions[ToolMode.PAN].setChecked(True)

        toolbar.addSeparator()

        # Draw tools label
        draw_label = QLabel("  Draw: ")
        draw_label.setObjectName("toolbarLabel")
        toolbar.addWidget(draw_label)

        # Drawing tools
        draw_tools = [
            (ToolMode.LINE_DRAW, "🖊️", "Line Draw", "Shift+L"),
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

        toolbar.addSeparator()

        # Action buttons
        deselect_btn = QAction("✕  Clear", self)
        deselect_btn.setToolTip(self._format_tooltip("Clear Selection", "Esc"))
        deselect_btn.triggered.connect(self._on_clear_selection)
        toolbar.addAction(deselect_btn)

        delete_drawing_btn = QAction("🗑️  Del Draw", self)
        delete_drawing_btn.setToolTip(self._format_tooltip("Delete Selected Drawing", "Del"))
        delete_drawing_btn.triggered.connect(self._on_delete_drawing)
        toolbar.addAction(delete_drawing_btn)

        clear_drawing_btn = QAction("🧹  Clear Draw", self)
        clear_drawing_btn.setToolTip(self._format_tooltip("Clear All Drawings", ""))
        clear_drawing_btn.triggered.connect(self._on_clear_drawings)
        toolbar.addAction(clear_drawing_btn)

        reset_btn = QAction("↺  Reset", self)
        reset_btn.setToolTip(self._format_tooltip("Reset View", "Home"))
        reset_btn.triggered.connect(self._reset_graph_view)
        toolbar.addAction(reset_btn)

        autofit_btn = QAction("⊡  Fit", self)
        autofit_btn.setToolTip(self._format_tooltip("Auto Fit to Data", "F"))
        autofit_btn.triggered.connect(self._autofit_graph)
        toolbar.addAction(autofit_btn)
        
        toolbar.addSeparator()
        
        # Chart type selector
        self._chart_type_label = QLabel("  Chart: ")
        self._chart_type_label.setObjectName("toolbarLabel")
        toolbar.addWidget(self._chart_type_label)
        
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

        toolbar.addSeparator()

        # Preset management
        preset_label = QLabel("  Preset: ")
        preset_label.setObjectName("toolbarLabel")
        toolbar.addWidget(preset_label)

        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(120)
        self._preset_combo.setToolTip("Load saved preset")
        self._preset_combo.currentTextChanged.connect(self._on_preset_selected)
        toolbar.addWidget(self._preset_combo)

        save_preset_btn = QAction("💾", self)
        save_preset_btn.setToolTip("Save current settings as preset")
        save_preset_btn.triggered.connect(self._on_save_preset)
        toolbar.addAction(save_preset_btn)

        delete_preset_btn = QAction("🗑️", self)
        delete_preset_btn.setToolTip("Delete selected preset")
        delete_preset_btn.triggered.connect(self._on_delete_preset)
        toolbar.addAction(delete_preset_btn)

        # Initialize presets directory and load presets
        self._presets_dir = Path.home() / ".data_graph_studio" / "presets"
        self._presets_dir.mkdir(parents=True, exist_ok=True)
        self._refresh_presets()

    def _setup_main_layout(self):
        """메인 레이아웃 설정 (사이드바 + 3단 스플리터)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 최상위 수평 스플리터 (사이드바 | 메인 영역)
        self.root_splitter = QSplitter(Qt.Horizontal)
        self.root_splitter.setHandleWidth(1)
        self.root_splitter.setObjectName("themeSplitter")

        # 좌측 사이드바 - 탭 구조 (Projects + Datasets)
        self._sidebar_tabs = QTabWidget()
        self._sidebar_tabs.setMinimumWidth(100)
        self._sidebar_tabs.setMaximumWidth(250)
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
        self.main_splitter.setHandleWidth(1)
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
        profile_bar_layout.addWidget(self.profile_bar)

        # Graph Panel (상단)
        self.graph_panel = GraphPanel(self.state, self.engine)
        self.main_splitter.addWidget(self.graph_panel)

        # Table Panel (하단)
        self.table_panel = TablePanel(self.state, self.engine, self.graph_panel)
        self.main_splitter.addWidget(self.table_panel)

        # 메인 스플리터를 root_splitter에 추가
        self.root_splitter.addWidget(self.main_splitter)

        # root_splitter 비율 설정 (사이드바: 메인 = 150 : 나머지)
        self.root_splitter.setSizes([150, 1000])

        # 초기 비율 설정
        self._reset_layout()

        layout.addWidget(self.root_splitter)

        # Initialize floating graph manager
        self._floating_graph_manager = FloatingGraphManager(self.state, self.engine)
    
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

        # Set sizes - optimized ratios (50/50 split for graph and table)
        total_height = self.main_splitter.height()
        if total_height == 0:
            total_height = 800  # 기본값

        sizes = [
            int(total_height * 0.5),   # Graph
            int(total_height * 0.5),   # Table
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
        if os.path.exists(self._autosave_path):
            try:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Question)
                msg.setWindowTitle("Recovery")
                msg.setText("A previous session was not closed properly.\nRecover the last autosave?")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                if msg.exec() == QMessageBox.Yes:
                    self._restore_autosave()
                else:
                    os.remove(self._autosave_path)
            except Exception:
                pass

        # Autosave timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60 * 1000)  # 1 minute
        self._autosave_timer.timeout.connect(self._autosave_session)
        self._autosave_timer.start()

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

            payload = {
                "version": 1,
                "datasets": datasets,
                "active_dataset_id": self.state.active_dataset_id,
                "graph_state": self.state.get_current_graph_state(),
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

        # Restore graph settings
        graph_state = data.get("graph_state", {})
        if graph_state:
            self._apply_graph_state(graph_state)

        # Restore drawings
        drawings = data.get("drawings", {})
        if drawings and hasattr(self, 'graph_panel'):
            self.graph_panel.load_drawings_data(drawings)

        # Final refresh
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
        self._ipc_server = IPCServer(self)
        
        # 핸들러 등록
        self._ipc_server.register_handler('ping', lambda: 'pong')
        self._ipc_server.register_handler('get_state', self._ipc_get_state)
        self._ipc_server.register_handler('get_data_info', self._ipc_get_data_info)
        self._ipc_server.register_handler('set_chart_type', self._ipc_set_chart_type)
        self._ipc_server.register_handler('set_columns', self._ipc_set_columns)
        self._ipc_server.register_handler('load_file', self._ipc_load_file)
        self._ipc_server.register_handler('get_panels', self._ipc_get_panels)
        self._ipc_server.register_handler('get_summary', self._ipc_get_summary)
        self._ipc_server.register_handler('execute', self._ipc_execute)
        
        # 서버 시작
        self._ipc_server.start()
    
    def _ipc_get_state(self) -> dict:
        """현재 앱 상태 반환"""
        y_cols = list(self.state._y_columns) if hasattr(self.state, '_y_columns') and self.state._y_columns else []
        return {
            'data_loaded': self.state.is_data_loaded,
            'row_count': self.engine.row_count if self.state.is_data_loaded else 0,
            'columns': self.engine.columns if self.state.is_data_loaded else [],
            'chart_type': self.state._chart_settings.chart_type.name,
            'x_column': self.state.x_column,
            'y_columns': y_cols,
            'window_title': self.windowTitle(),
            'window_size': [self.width(), self.height()],
        }
    
    def _ipc_get_data_info(self) -> dict:
        """데이터 정보 반환"""
        if not self.state.is_data_loaded:
            return {'loaded': False}
        
        return {
            'loaded': True,
            'row_count': self.engine.row_count,
            'columns': self.engine.columns,
            'dtypes': {col: str(dtype) for col, dtype in zip(
                self.engine.columns, 
                self.engine.df.dtypes if self.engine.df is not None else []
            )},
        }
    
    def _ipc_set_chart_type(self, chart_type: str) -> bool:
        """차트 타입 설정"""
        try:
            ct = ChartType[chart_type.upper()]
            self.state.set_chart_type(ct)
            return True
        except KeyError:
            raise ValueError(f"Unknown chart type: {chart_type}")
    
    def _ipc_set_columns(self, x: str = None, y: list = None) -> bool:
        """X/Y 컬럼 설정"""
        if x:
            self.state.set_x_column(x)
        if y:
            self.state._y_columns = set(y)
            # Signal이 있으면 emit
            if hasattr(self.state, 'y_columns_changed'):
                self.state.y_columns_changed.emit(y)
        return True
    
    def _ipc_load_file(self, path: str) -> dict:
        """파일 로드"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        
        dataset_id = self.engine.load_dataset(path)
        if dataset_id:
            self.state.set_data_loaded(True, self.engine.row_count)
            self.table_panel.set_data(self.engine.df)
            # Summary 업데이트
            self._update_summary_from_profile()
            return {'success': True, 'dataset_id': dataset_id}
        return {'success': False}
    
    def _ipc_get_panels(self) -> dict:
        """패널 정보 반환"""
        panels = {}
        for name in ['table_panel', 'graph_panel', 'filter_panel', 'property_panel', 'summary_panel']:
            if hasattr(self, name):
                panel = getattr(self, name)
                panels[name] = {
                    'exists': panel is not None,
                    'visible': panel.isVisible() if panel else False,
                }
        return panels

    def _ipc_get_summary(self) -> dict:
        """Summary 통계 반환"""
        summary = self.engine.get_full_profile_summary()
        profile = self.engine.profile

        if summary is None and profile is None:
            return {}

        if summary is None and profile is not None:
            numeric_cols = sum(1 for c in profile.columns if c.is_numeric)
            text_cols = sum(1 for c in profile.columns if not c.is_numeric and not c.is_temporal)
            temporal_cols = sum(1 for c in profile.columns if c.is_temporal)

            total_cells = profile.total_rows * profile.total_columns
            total_nulls = sum(c.null_count for c in profile.columns)
            missing_percent = (total_nulls / total_cells * 100) if total_cells > 0 else 0

            summary = {
                'total_rows': profile.total_rows,
                'total_columns': profile.total_columns,
                'numeric_columns': numeric_cols,
                'text_columns': text_cols + temporal_cols,
                'missing_percent': missing_percent,
                'memory_bytes': profile.memory_bytes,
                'load_time_seconds': profile.load_time_seconds,
            }

        # file name
        if self.engine._source and self.engine._source.path:
            summary['file_name'] = Path(self.engine._source.path).name

        return summary
    
    def _ipc_execute(self, code: str) -> any:
        """Python 코드 실행 (디버깅용)"""
        # 보안 주의: 로컬 전용
        local_vars = {
            'window': self,
            'state': self.state,
            'engine': self.engine,
            'table_panel': self.table_panel,
            'graph_panel': self.graph_panel,
            'summary_panel': self.summary_panel,
        }
        return eval(code, {'__builtins__': {}}, local_vars)

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

        # Panel signals - route through preview dialog
        self.table_panel.file_dropped.connect(self._show_parsing_preview)
        self.table_panel.window_changed.connect(self._on_window_changed)

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
    
    def _on_open_file(self):
        """파일 열기 다이얼로그 - 새 프로젝트 마법사 사용"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
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
            
            # .dgs 프로젝트 파일은 바로 로드 (마법사 스킵)
            if ext == '.dgs':
                self._load_project_file(file_path)
                return
            
            # 새 프로젝트 마법사 실행
            self._show_new_project_wizard(file_path)
    
    def _on_open_file_without_wizard(self):
        """파일 열기 (마법사 없이) - Ctrl+Shift+O"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
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
            # 기존 파싱 미리보기 다이얼로그 사용
            self._show_parsing_preview(file_path)
    
    def _show_new_project_wizard(self, file_path: str):
        """새 프로젝트 마법사 표시"""
        # 대용량 파일 경고 체크
        if not self._check_large_file_warning(file_path):
            return
        
        wizard = NewProjectWizard(file_path, self)
        wizard.project_created.connect(self._on_wizard_project_created)
        wizard.exec()
    
    def _on_wizard_project_created(self, result: dict):
        """마법사에서 프로젝트 생성 완료 시 호출"""
        parsing_settings = result.get('parsing_settings')
        graph_setting = result.get('graph_setting')
        project_name = result.get('project_name')
        preview_df = result.get('preview_df')
        
        if parsing_settings is None:
            return
        
        # 마법사 결과 저장 (로딩 완료 후 적용)
        self._pending_wizard_result = {
            'graph_setting': graph_setting,
            'project_name': project_name,
        }
        
        # 파일 로드 (비동기)
        self._load_file_with_settings(parsing_settings.file_path, parsing_settings)
    
    def _load_project_file(self, file_path: str):
        """프로젝트 파일 (.dgs) 로드"""
        # 기존 프로젝트 로드 로직 사용
        self._load_project(file_path)

    def _on_open_multiple_files(self):
        """다중 파일 열기 다이얼로그"""
        result = open_multi_file_dialog(self, self.engine)

        if result is None:
            return

        file_paths, naming_option, auto_compare = result

        if not file_paths:
            return

        # Progress dialog for loading multiple files
        progress = QProgressDialog(
            "Loading files...", "Cancel", 0, len(file_paths), self
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

            # Generate dataset name
            if naming_option == "filename":
                name = Path(file_path).name
            elif naming_option == "filename_no_ext":
                name = Path(file_path).stem
            elif naming_option == "sequential":
                name = f"Data {len(self.engine.datasets) + 1}"
            else:
                name = Path(file_path).name

            # Load dataset
            dataset_id = self.engine.load_dataset(file_path, name=name)

            if dataset_id:
                loaded_ids.append(dataset_id)

                # Register in state
                dataset = self.engine.get_dataset(dataset_id)
                if dataset:
                    self.state.add_dataset(
                        dataset_id=dataset_id,
                        name=name,
                        row_count=dataset.row_count,
                        column_count=dataset.column_count,
                        memory_bytes=dataset.memory_bytes
                    )

        progress.setValue(len(file_paths))
        progress.close()

        if loaded_ids:
            self.statusbar.showMessage(
                f"Loaded {len(loaded_ids)} datasets successfully", 3000
            )

            # Update UI with first dataset
            if loaded_ids:
                self.engine.activate_dataset(loaded_ids[0])
                self._on_data_loaded()

            # Auto-start comparison if enabled
            if auto_compare and len(loaded_ids) >= 2:
                self.state.set_comparison_datasets(loaded_ids[:4])  # Max 4
                self.state.set_comparison_mode(ComparisonMode.OVERLAY)
                self._on_comparison_started(loaded_ids[:4])

    def _show_parsing_preview(self, file_path: str):
        """파싱 미리보기 다이얼로그 표시"""
        # 대용량 파일 경고 체크
        if not self._check_large_file_warning(file_path):
            return

        ext = Path(file_path).suffix.lower()

        # Binary formats don't need parsing preview
        if ext in ['.parquet', '.xlsx', '.xls', '.json']:
            self._load_file(file_path)
            return

        # Show parsing preview dialog
        dialog = ParsingPreviewDialog(file_path, self)
        if dialog.exec() == QDialog.Accepted:
            settings = dialog.get_settings()
            self._load_file_with_settings(file_path, settings)

    def _check_large_file_warning(self, file_path: str) -> bool:
        """대용량 파일 경고 다이얼로그 표시. 계속 진행하면 True 반환"""
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        except OSError:
            return True  # 파일 크기 확인 실패 시 계속 진행

        if file_size_mb >= self.HUGE_FILE_WARNING_MB:
            # 2GB 이상 - 강력 경고
            sys_mem = MemoryMonitor.get_system_memory()
            reply = QMessageBox.warning(
                self,
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
        elif file_size_mb >= self.LARGE_FILE_WARNING_MB:
            # 500MB 이상 - 일반 경고
            reply = QMessageBox.question(
                self,
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

    def _cleanup_loader_thread(self):
        """기존 로더 스레드 정리"""
        if self._loader_thread is not None:
            if self._loader_thread.isRunning():
                logger.debug("Waiting for previous loader thread to finish...")
                self.engine.cancel_loading()
                # 최대 2초 대기
                if not self._loader_thread.wait(2000):
                    logger.warning("Loader thread did not finish in time, terminating...")
                    self._loader_thread.terminate()
                    self._loader_thread.wait(1000)
            self._loader_thread = None
            gc.collect()  # 메모리 정리
    
    def _load_file(self, file_path: str, settings: Optional[ParsingSettings] = None):
        """파일 로드 (설정 없이 - 바이너리 포맷용)"""
        # 기존 스레드 정리
        self._cleanup_loader_thread()

        # 프로그레스 다이얼로그
        self._progress_dialog = QProgressDialog(
            f"Loading {Path(file_path).name}...",
            "Cancel",
            0, 100,
            self
        )
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setAutoClose(True)
        self._progress_dialog.setMinimumWidth(400)
        self._progress_dialog.canceled.connect(self._cancel_loading)

        # 로더 스레드 시작
        self._loader_thread = DataLoaderThread(self.engine, file_path)
        self._loader_thread.progress_updated.connect(self._on_loading_progress)
        self._loader_thread.finished_loading.connect(self._on_loading_finished)
        self._loader_thread.start()

        self._progress_dialog.show()
    
    def _load_file_with_settings(self, file_path: str, settings: ParsingSettings):
        """파일 로드 (파싱 설정 적용)"""
        # 기존 스레드 정리
        self._cleanup_loader_thread()

        # 프로그레스 다이얼로그
        self._progress_dialog = QProgressDialog(
            f"Loading {Path(file_path).name}...",
            "Cancel",
            0, 100,
            self
        )
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setAutoClose(True)
        self._progress_dialog.setMinimumWidth(400)
        self._progress_dialog.canceled.connect(self._cancel_loading)

        # 로더 스레드 시작 (설정 적용)
        self._loader_thread = DataLoaderThreadWithSettings(self.engine, file_path, settings)
        self._loader_thread.progress_updated.connect(self._on_loading_progress)
        self._loader_thread.finished_loading.connect(self._on_loading_finished)
        self._loader_thread.start()

        self._progress_dialog.show()
    
    def _on_loading_progress(self, progress: LoadingProgress):
        """로딩 진행률 업데이트"""
        if self._progress_dialog:
            self._progress_dialog.setValue(int(progress.progress_percent))

            # 메모리 사용량 가져오기
            try:
                proc_mem = MemoryMonitor.get_process_memory()
                mem_str = MemoryMonitor.format_memory(proc_mem['rss_mb'])
            except Exception:
                mem_str = "--"

            # ETA 계산
            eta_str = ""
            if progress.eta_seconds > 0:
                eta_str = f"\nETA: {progress.eta_seconds:.0f}s"

            self._progress_dialog.setLabelText(
                f"Loading... {progress.status}\n"
                f"{progress.loaded_rows:,} rows loaded\n"
                f"Memory: {mem_str}{eta_str}"
            )
    
    def _on_loading_finished(self, success: bool):
        """로딩 완료"""
        if self._progress_dialog:
            self._progress_dialog.close()

        if success:
            # 상태 업데이트
            self.state.set_data_loaded(True, self.engine.row_count)
            self.state.set_column_order(self.engine.columns)

            # 첫 로드 시 데이터셋 목록에 등록
            if self.engine.dataset_count == 0:
                import uuid
                dataset_id = str(uuid.uuid4())[:8]
                name = Path(self.engine._source.path).name if self.engine._source and self.engine._source.path else "Dataset"
                from ..core.data_engine import DatasetInfo
                dataset_info = DatasetInfo(
                    id=dataset_id,
                    name=name,
                    df=self.engine.df,
                    lazy_df=self.engine._lazy_df,
                    source=self.engine._source,
                    profile=self.engine.profile
                )
                self.engine._datasets[dataset_id] = dataset_info
                self.engine._active_dataset_id = dataset_id

                memory_bytes = self.engine.df.estimated_size() if self.engine.df is not None else 0
                self.state.add_dataset(
                    dataset_id=dataset_id,
                    name=name,
                    file_path=self.engine._source.path if self.engine._source else None,
                    row_count=self.engine.row_count,
                    column_count=self.engine.column_count,
                    memory_bytes=memory_bytes
                )

            # 프로파일 기반 Summary 업데이트
            if self.engine.profile:
                self._update_summary_from_profile()

            # 로딩 완료 후 메모리 정리
            gc.collect()
            logger.info(f"Data loaded: {self.engine.row_count:,} rows, {self.engine.column_count} columns")
            
            # 마법사 결과 적용 (pending이 있으면)
            self._apply_pending_wizard_result()
        else:
            error_msg = self.engine.progress.error_message or "Unknown error"
            logger.error(f"Failed to load file: {error_msg}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load file:\n{error_msg}"
            )
    
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
            if active_id:
                # 프로젝트 탐색창에 추가
                from dataclasses import replace
                graph_setting = replace(graph_setting, dataset_id=active_id)
                self.profile_store.add(graph_setting)
                self.profile_model.refresh()
                
                # 그래프 설정 적용
                self.profile_controller.apply_setting(graph_setting)
                
                logger.info(f"Wizard result applied: {graph_setting.name}")
    
    def _cancel_loading(self):
        """로딩 취소"""
        if self._loader_thread and self._loader_thread.isRunning():
            logger.info("Loading cancelled by user")
            self.engine.cancel_loading()
            # 스레드 종료 대기 및 정리
            self._loader_thread.wait(2000)
            self._loader_thread = None
            # 메모리 정리
            gc.collect()
            self.statusbar.showMessage("Loading cancelled", 3000)
    
    def _on_data_loaded(self):
        """데이터 로드 완료"""
        self._update_ui_state()
        
        # 패널들에 데이터 전달
        self.table_panel.set_data(self.engine.df)
        if self.engine.is_windowed:
            self.state.set_visible_rows(len(self.engine.df))
        
        # 그래프 패널에 컬럼 목록 전달 (X-Axis 드롭다운용)
        self.graph_panel.set_columns(self.engine.columns)
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
    
    def _update_summary_from_profile(self):
        """프로파일에서 Summary 업데이트"""
        if not self.engine.profile:
            return

        profile = self.engine.profile
        summary = self.engine.get_full_profile_summary()
        if summary is None and profile is None:
            return

        # Get file name from engine source
        file_name = ""
        if self.engine._source and self.engine._source.path:
            file_name = Path(self.engine._source.path).name

        if summary is None and profile is not None:
            # Count column types
            numeric_cols = sum(1 for c in profile.columns if c.is_numeric)
            text_cols = sum(1 for c in profile.columns if not c.is_numeric and not c.is_temporal)
            temporal_cols = sum(1 for c in profile.columns if c.is_temporal)

            # Calculate missing data percentage
            total_cells = profile.total_rows * profile.total_columns
            total_nulls = sum(c.null_count for c in profile.columns)
            missing_percent = (total_nulls / total_cells * 100) if total_cells > 0 else 0

            total_rows = profile.total_rows
            total_columns = profile.total_columns
            numeric_columns = numeric_cols
            text_columns = text_cols + temporal_cols
            memory_mb = profile.memory_bytes / (1024 * 1024)
            load_time = profile.load_time_seconds
        else:
            total_rows = summary.get('total_rows', 0)
            total_columns = summary.get('total_columns', 0)
            numeric_columns = summary.get('numeric_columns', 0)
            text_columns = summary.get('text_columns', 0)
            missing_percent = summary.get('missing_percent', 0)
            memory_mb = summary.get('memory_bytes', 0) / (1024 * 1024) if summary else 0
            load_time = summary.get('load_time_seconds', 0) if summary else 0

        # Calculate sampled rows (for graph - max 10000 points)
        MAX_GRAPH_POINTS = 10000
        sampled_rows = min(total_rows, MAX_GRAPH_POINTS)

        stats = {
            'file_name': file_name,
            'total_rows': total_rows,
            'sampled_rows': sampled_rows,
            'total_columns': total_columns,
            'numeric_columns': numeric_columns,
            'text_columns': text_columns,
            'missing_percent': missing_percent,
            'memory_mb': memory_mb,
            'load_time': load_time,
        }

        # 숫자형 컬럼 통계
        if profile is not None:
            for col_info in profile.columns:
                if col_info.is_numeric:
                    stats[col_info.name] = {
                        'min': col_info.min_value,
                        'max': col_info.max_value,
                        'null_count': col_info.null_count,
                    }

        self.state.update_summary(stats)
    
    def _on_tool_mode_changed(self):
        """툴 모드 변경"""
        mode = self.state.tool_mode
        for m, action in self._tool_actions.items():
            action.setChecked(m == mode)
    
    def _reset_graph_view(self):
        """그래프 뷰 리셋"""
        self.graph_panel.reset_view()

    def _on_clear_selection(self):
        """Clear selection and highlight"""
        self.state.clear_selection()
        if hasattr(self, 'graph_panel') and self.graph_panel is not None:
            self.graph_panel.main_graph.highlight_selection([])
    
    def _autofit_graph(self):
        """그래프 자동 맞춤"""
        self.graph_panel.autofit()
    
    def _on_save_project(self):
        """프로젝트 저장"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            "",
            "Data Graph Studio Project (*.dgs)"
        )
        if file_path:
            # TODO: 프로젝트 저장 구현
            self.statusbar.showMessage(f"Project saved: {file_path}", 3000)
    
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

    # ==================== Preset Management ====================

    def _refresh_presets(self):
        """Refresh preset dropdown list"""
        self._preset_combo.blockSignals(True)
        current_text = self._preset_combo.currentText()
        self._preset_combo.clear()
        self._preset_combo.addItem("(Default)")

        # List preset files
        if self._presets_dir.exists():
            preset_files = sorted(self._presets_dir.glob("*.json"))
            for preset_file in preset_files:
                self._preset_combo.addItem(preset_file.stem)

        # Restore selection if still exists
        idx = self._preset_combo.findText(current_text)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)
        else:
            self._preset_combo.setCurrentIndex(0)

        self._preset_combo.blockSignals(False)

    def _on_preset_selected(self, preset_name: str):
        """Load selected preset"""
        if not preset_name or preset_name == "(Default)":
            return

        preset_path = self._presets_dir / f"{preset_name}.json"
        if not preset_path.exists():
            return

        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            self._apply_preset_settings(settings)
            self.statusbar.showMessage(f"Loaded preset: {preset_name}", 3000)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Load Preset Error",
                f"Failed to load preset: {e}"
            )

    def _on_save_preset(self):
        """Save current settings as preset"""
        name, ok = QInputDialog.getText(
            self,
            "Save Preset",
            "Enter preset name:",
            text=""
        )

        if not ok or not name.strip():
            return

        name = name.strip()
        # Sanitize name for filename
        safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")
        if not safe_name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid preset name.")
            return

        preset_path = self._presets_dir / f"{safe_name}.json"

        # Check if exists
        if preset_path.exists():
            reply = QMessageBox.question(
                self,
                "Overwrite Preset",
                f"Preset '{safe_name}' already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        try:
            settings = self._get_current_settings()
            with open(preset_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False, default=str)

            self._refresh_presets()
            self._preset_combo.setCurrentText(safe_name)
            self.statusbar.showMessage(f"Saved preset: {safe_name}", 3000)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Preset Error",
                f"Failed to save preset: {e}"
            )

    def _on_delete_preset(self):
        """Delete selected preset"""
        preset_name = self._preset_combo.currentText()
        if not preset_name or preset_name == "(Default)":
            QMessageBox.information(self, "Delete Preset", "Select a preset to delete.")
            return

        reply = QMessageBox.question(
            self,
            "Delete Preset",
            f"Delete preset '{preset_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        preset_path = self._presets_dir / f"{preset_name}.json"
        try:
            if preset_path.exists():
                preset_path.unlink()
            self._refresh_presets()
            self.statusbar.showMessage(f"Deleted preset: {preset_name}", 3000)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Delete Preset Error",
                f"Failed to delete preset: {e}"
            )

    def _get_current_settings(self) -> Dict:
        """Get current chart and view settings for saving"""
        settings = {
            'version': '1.0',
            'chart_type': self.state.chart_type.value if self.state.chart_type else None,
            'tool_mode': self.state.tool_mode.value if self.state.tool_mode else None,
        }

        # Get chart options from graph panel
        if hasattr(self.graph_panel, 'get_chart_options'):
            chart_options = self.graph_panel.get_chart_options()
            # Convert QColor to string for JSON serialization
            if 'bg_color' in chart_options and chart_options['bg_color']:
                chart_options['bg_color'] = chart_options['bg_color'].name()
            settings['chart_options'] = chart_options

        # Get legend settings
        if hasattr(self.graph_panel, 'get_legend_settings'):
            settings['legend_settings'] = self.graph_panel.get_legend_settings()

        # Get panel visibility
        settings['panel_visibility'] = {
            'summary': self.summary_panel.isVisible(),
            'graph': self.graph_panel.isVisible(),
            'table': self.table_panel.isVisible(),
        }

        return settings

    def _apply_preset_settings(self, settings: Dict):
        """Apply loaded preset settings"""
        # Apply chart type
        if 'chart_type' in settings and settings['chart_type']:
            try:
                self.state.set_chart_type(ChartType(settings['chart_type']))
            except ValueError:
                pass

        # Apply chart options
        if 'chart_options' in settings and hasattr(self.graph_panel, 'apply_options'):
            self.graph_panel.apply_options(settings['chart_options'])

        # Apply panel visibility
        if 'panel_visibility' in settings:
            vis = settings['panel_visibility']
            for panel_key, visible in vis.items():
                if panel_key in self._view_actions:
                    self._view_actions[panel_key].setChecked(visible)
                    self._toggle_panel_visibility(panel_key, visible)

        # Refresh graph
        if hasattr(self.graph_panel, 'refresh'):
            self.graph_panel.refresh()

    # ==================== Profile Menu Actions ====================

    def _on_new_profile_menu(self):
        """메뉴에서 새 프로파일"""
        name, ok = QInputDialog.getText(
            self,
            "New Profile",
            "Enter profile name:",
            text="New Profile"
        )
        if ok and name.strip():
            profile = Profile.create_new(name.strip())
            self.state.set_profile(profile)
            self.statusbar.showMessage(f"Created new profile: {name.strip()}", 3000)

    def _on_load_profile_menu(self):
        """메뉴에서 프로파일 로드"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Profile",
            str(self.profile_bar.profile_manager.profiles_dir),
            "Data Graph Profile (*.dgp)"
        )
        if path:
            try:
                profile = self.profile_bar.profile_manager.load(path)
                self.state.set_profile(profile)
                self.statusbar.showMessage(f"Loaded profile: {profile.name}", 3000)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Load Profile Error",
                    f"Failed to load profile: {e}"
                )

    def _on_save_profile_menu(self):
        """메뉴에서 프로파일 저장"""
        profile = self.state.current_profile
        if not profile:
            QMessageBox.information(
                self,
                "Save Profile",
                "No profile to save. Create a new profile first."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Profile",
            str(self.profile_bar.profile_manager.profiles_dir / f"{profile.name}.dgp"),
            "Data Graph Profile (*.dgp)"
        )
        if path:
            try:
                profile.save(path)
                self.profile_bar.profile_manager._add_recent_profile(path)
                self.state.profile_saved.emit()
                self.statusbar.showMessage(f"Profile saved: {profile.name}", 3000)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Save Profile Error",
                    f"Failed to save profile: {e}"
                )

    # ==================== Profile Actions ====================

    def _on_profile_setting_clicked(self, setting_id: str):
        """프로파일 설정 클릭"""
        profile = self.state.current_profile
        if profile:
            setting = profile.get_setting(setting_id)
            if setting:
                # 설정 적용
                self.state.apply_graph_setting(setting)
                self.state.activate_setting(setting_id)
                # 그래프 새로고침
                self.graph_panel.refresh()

    def _on_profile_setting_double_clicked(self, setting_id: str):
        """프로파일 설정 더블클릭 (Floating 창 열기)"""
        profile = self.state.current_profile
        if profile and self._floating_graph_manager:
            setting = profile.get_setting(setting_id)
            if setting:
                self._floating_graph_manager.open_floating_graph(setting, self)

    def _on_add_setting_requested(self):
        """새 설정 추가 요청"""
        # 프로파일이 없으면 새로 생성
        if not self.state.current_profile:
            name, ok = QInputDialog.getText(
                self,
                "New Profile",
                "No profile loaded. Create a new profile first.\n\nEnter profile name:",
                text="New Profile"
            )
            if not ok or not name.strip():
                return
            profile = Profile.create_new(name.strip())
            self.state.set_profile(profile)

        # 설정 저장 다이얼로그 표시
        dialog = SaveSettingDialog(self)
        if dialog.exec() == QDialog.Accepted:
            setting = dialog.get_setting()
            if setting:
                # 현재 그래프 상태를 설정에 저장
                graph_state = self.state.get_current_graph_state()
                setting.chart_type = graph_state['chart_type']
                setting.x_column = graph_state['x_column']
                setting.group_columns = graph_state['group_columns']
                setting.value_columns = graph_state['value_columns']
                setting.hover_columns = graph_state['hover_columns']
                setting.chart_settings = graph_state['chart_settings']

                if dialog.get_include_filters():
                    setting.filters = graph_state['filters']
                    setting.include_filters = True

                if dialog.get_include_sorts():
                    setting.sorts = graph_state['sorts']
                    setting.include_sorts = True

                # 프로파일에 추가
                self.state.add_setting(setting)
                self.statusbar.showMessage(f"Setting '{setting.name}' saved", 3000)

    def _show_profile_manager(self):
        """프로파일 관리자 다이얼로그 표시"""
        dialog = ProfileManagerDialog(self.profile_bar.profile_manager, self)
        dialog.exec()

    # ==================== Project Explorer Actions ====================

    def _on_profile_apply_requested(self, profile_id: str):
        """프로파일 적용 요청 (ProjectTreeView에서)"""
        if self.profile_controller.apply_profile(profile_id):
            self.graph_panel.refresh()
            self.statusbar.showMessage("Profile applied", 2000)

    def _on_new_profile_requested(self, dataset_id: str):
        """새 프로파일 생성 요청"""
        name, ok = QInputDialog.getText(
            self, "New Profile", "Enter profile name:", text="New Profile"
        )
        if ok and name.strip():
            profile_id = self.profile_controller.create_profile(dataset_id, name.strip())
            if profile_id:
                self.profile_model.refresh()
                self.statusbar.showMessage(f"Profile '{name}' created", 2000)

    def _on_profile_rename_requested(self, profile_id: str):
        """프로파일 이름 변경 요청"""
        setting = self.profile_store.get(profile_id)
        if not setting:
            return
        name, ok = QInputDialog.getText(
            self, "Rename Profile", "Enter new name:", text=setting.name
        )
        if ok and name.strip():
            if self.profile_controller.rename_profile(profile_id, name.strip()):
                self.profile_model.refresh()
                self.statusbar.showMessage("Profile renamed", 2000)

    def _on_profile_delete_requested(self, profile_id: str):
        """프로파일 삭제 요청"""
        setting = self.profile_store.get(profile_id)
        if not setting:
            return
        reply = QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile '{setting.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.profile_controller.delete_profile(profile_id):
                self.profile_model.refresh()
                self.statusbar.showMessage("Profile deleted (Ctrl+Z to undo)", 3000)

    def _on_profile_duplicate_requested(self, profile_id: str):
        """프로파일 복제 요청"""
        new_id = self.profile_controller.duplicate_profile(profile_id)
        if new_id:
            self.profile_model.refresh()
            self.statusbar.showMessage("Profile duplicated", 2000)

    def _on_profile_export_requested(self, profile_id: str):
        """프로파일 내보내기 요청"""
        setting = self.profile_store.get(profile_id)
        if not setting:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Profile", f"{setting.name}.dgp", "Data Graph Profile (*.dgp)"
        )
        if path:
            if self.profile_controller.export_profile(profile_id, path):
                self.statusbar.showMessage(f"Profile exported to {path}", 3000)

    def _on_profile_import_requested(self, dataset_id: str):
        """프로파일 가져오기 요청"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Profile", "", "Data Graph Profile (*.dgp)"
        )
        if path:
            profile_id = self.profile_controller.import_profile(dataset_id, path)
            if profile_id:
                self.profile_model.refresh()
                self.statusbar.showMessage("Profile imported", 2000)

    # ==================== Multi-Dataset Operations ====================

    def _on_add_dataset(self):
        """새 데이터셋 추가 (멀티 파일 지원)"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Dataset",
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

        if not file_paths:
            return

        if len(file_paths) == 1:
            self._add_dataset_from_file(file_paths[0])
            return

        # Multi-file: load sequentially with progress
        progress = QProgressDialog(
            "Loading datasets...", "Cancel", 0, len(file_paths), self
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        for i, file_path in enumerate(file_paths):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            progress.setLabelText(f"Loading: {Path(file_path).name}")
            QApplication.processEvents()
            self._add_dataset_from_file(file_path)

        progress.setValue(len(file_paths))

    def _add_dataset_from_file(self, file_path: str):
        """파일에서 데이터셋 추가"""
        # 메모리 체크
        try:
            file_size = os.path.getsize(file_path)
            can_load, message = self.engine.can_load_dataset(file_size * 2)  # 예상 메모리는 파일 크기의 2배
            if not can_load:
                QMessageBox.warning(self, "Memory Limit", message)
                return
            elif message:
                # 경고 메시지가 있으면 표시
                self.statusbar.showMessage(message, 5000)
        except OSError:
            pass

        # 대용량 파일 경고
        if not self._check_large_file_warning(file_path):
            return

        ext = Path(file_path).suffix.lower()

        # 바이너리 포맷은 바로 로드
        if ext in ['.parquet', '.xlsx', '.xls', '.json']:
            self._load_dataset(file_path)
            return

        # 텍스트 파일은 파싱 미리보기 표시
        dialog = ParsingPreviewDialog(file_path, self)
        if dialog.exec() == QDialog.Accepted:
            settings = dialog.get_settings()
            self._load_dataset_with_settings(file_path, settings)

    def _load_dataset(self, file_path: str, settings: Optional[ParsingSettings] = None):
        """데이터셋 로드 (새 데이터셋으로 추가)"""
        import uuid
        from pathlib import Path

        dataset_id = str(uuid.uuid4())[:8]
        name = Path(file_path).name

        # 로딩 다이얼로그 표시
        self._progress_dialog = QProgressDialog(
            f"Loading {name}...",
            "Cancel",
            0, 100,
            self
        )
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setMinimumDuration(500)
        self._progress_dialog.canceled.connect(self._cancel_loading)
        self._progress_dialog.show()

        # 데이터셋 ID 저장 (콜백에서 사용)
        self._pending_dataset_id = dataset_id
        self._pending_dataset_name = name
        self._pending_dataset_path = file_path

        # 스레드로 로드
        self._cleanup_loader_thread()
        self._loader_thread = DataLoaderThread(self.engine, file_path)
        self._loader_thread.progress_updated.connect(self._on_loading_progress)
        self._loader_thread.finished_loading.connect(self._on_dataset_loading_finished)
        self._loader_thread.start()

    def _load_dataset_with_settings(self, file_path: str, settings: ParsingSettings):
        """설정을 적용하여 데이터셋 로드"""
        import uuid
        from pathlib import Path

        dataset_id = str(uuid.uuid4())[:8]
        name = Path(file_path).name

        # 로딩 다이얼로그 표시
        self._progress_dialog = QProgressDialog(
            f"Loading {name}...",
            "Cancel",
            0, 100,
            self
        )
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setMinimumDuration(500)
        self._progress_dialog.canceled.connect(self._cancel_loading)
        self._progress_dialog.show()

        # 데이터셋 ID 저장
        self._pending_dataset_id = dataset_id
        self._pending_dataset_name = name
        self._pending_dataset_path = file_path

        # 스레드로 로드
        self._cleanup_loader_thread()
        self._loader_thread = DataLoaderThreadWithSettings(self.engine, file_path, settings)
        self._loader_thread.progress_updated.connect(self._on_loading_progress)
        self._loader_thread.finished_loading.connect(self._on_dataset_loading_finished)
        self._loader_thread.start()

    def _on_dataset_loading_finished(self, success: bool):
        """데이터셋 로딩 완료"""
        if self._progress_dialog:
            self._progress_dialog.close()

        if success:
            # State에 데이터셋 추가
            dataset_id = getattr(self, '_pending_dataset_id', None)
            name = getattr(self, '_pending_dataset_name', 'Dataset')
            file_path = getattr(self, '_pending_dataset_path', None)

            if dataset_id:
                # 새 DatasetInfo 생성 (항상 새로 등록)
                from ..core.data_engine import DatasetInfo
                dataset_info = DatasetInfo(
                    id=dataset_id,
                    name=name,
                    df=self.engine.df,
                    lazy_df=self.engine._lazy_df,
                    source=self.engine._source,
                    profile=self.engine.profile
                )
                self.engine._datasets[dataset_id] = dataset_info
                self.engine._active_dataset_id = dataset_id

                # State에도 추가
                memory_bytes = self.engine.df.estimated_size() if self.engine.df is not None else 0
                self.state.add_dataset(
                    dataset_id=dataset_id,
                    name=name,
                    file_path=file_path,
                    row_count=self.engine.row_count,
                    column_count=self.engine.column_count,
                    memory_bytes=memory_bytes
                )

                # 기존 로직도 실행 (하위 호환성)
                self.state.set_data_loaded(True, self.engine.row_count)
                self.state.set_column_order(self.engine.columns)

                if self.engine.profile:
                    self._update_summary_from_profile()

                gc.collect()
                logger.info(f"Dataset added: {dataset_id} ({name}), {self.engine.row_count:,} rows")

            # pending 상태 정리
            self._pending_dataset_id = None
            self._pending_dataset_name = None
            self._pending_dataset_path = None
        else:
            error_msg = self.engine.progress.error_message or "Unknown error"
            logger.error(f"Failed to load dataset: {error_msg}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load dataset:\n{error_msg}"
            )

    def _on_dataset_activated(self, dataset_id: str):
        """데이터셋 활성화 요청"""
        # Save current dataset state before switching
        try:
            if self.state.active_dataset_id:
                self.state._sync_to_dataset_state(self.state.active_dataset_id)
        except Exception:
            pass

        if self.engine.activate_dataset(dataset_id):
            self.state.activate_dataset(dataset_id)

            # UI 업데이트
            self.state.set_data_loaded(True, self.engine.row_count)
            self.state.set_column_order(self.engine.columns)

            # 패널 업데이트
            self.table_panel.set_data(self.engine.df)
            self.graph_panel.set_columns(self.engine.columns)
            self.graph_panel.refresh()
            self.summary_panel.refresh()

            # 프로파일 업데이트
            if self.engine.profile:
                self._update_summary_from_profile()

            # 상태바 메시지
            metadata = self.state.get_dataset_metadata(dataset_id)
            if metadata:
                self.statusbar.showMessage(
                    f"Activated: {metadata.name} ({self.engine.row_count:,} rows)",
                    3000
                )

    def _on_dataset_remove_requested(self, dataset_id: str):
        """데이터셋 제거 요청"""
        metadata = self.state.get_dataset_metadata(dataset_id)
        name = metadata.name if metadata else dataset_id

        if self.engine.remove_dataset(dataset_id):
            self.state.remove_dataset(dataset_id)

            # 남은 데이터셋이 있으면 UI 업데이트
            if self.engine.dataset_count > 0:
                self._on_dataset_activated(self.engine.active_dataset_id)
            else:
                # 모든 데이터셋 제거됨
                self.state.set_data_loaded(False, 0)
                self._on_data_cleared()

            self.statusbar.showMessage(f"Removed: {name}", 3000)

    def _set_comparison_mode(self, mode: ComparisonMode):
        """비교 모드 설정 (메뉴에서 호출)"""
        self.state.set_comparison_mode(mode)
        self._on_comparison_mode_changed(mode.value)
        self._update_comparison_mode_actions(mode)

    def _update_comparison_mode_actions(self, mode: ComparisonMode):
        """비교 모드 메뉴 액션 상태 업데이트"""
        if not hasattr(self, '_comparison_mode_actions'):
            return

        for action_mode, action in self._comparison_mode_actions.items():
            action.setChecked(action_mode == mode)

    def _on_comparison_mode_changed(self, mode_value: str):
        """비교 모드 변경"""
        try:
            mode = ComparisonMode(mode_value)
            self.state.set_comparison_mode(mode)

            # Update menu action states
            self._update_comparison_mode_actions(mode)

            # Hide overlay stats widget when not in overlay mode
            if mode != ComparisonMode.OVERLAY:
                self._hide_overlay_stats_widget()

            if mode == ComparisonMode.SINGLE:
                self.statusbar.showMessage("Single dataset mode", 2000)
                # Restore single view
                self._restore_single_view()
            elif mode == ComparisonMode.OVERLAY:
                self.statusbar.showMessage("Overlay comparison mode", 2000)
                # Restore graph panel for overlay mode
                self._remove_comparison_view()
                self.graph_panel.refresh()
            elif mode == ComparisonMode.SIDE_BY_SIDE:
                self.statusbar.showMessage("Side-by-side comparison mode", 2000)
            elif mode == ComparisonMode.DIFFERENCE:
                self.statusbar.showMessage("Difference analysis mode", 2000)
        except ValueError:
            pass

    def _on_comparison_started(self, dataset_ids: List[str]):
        """비교 시작"""
        mode = self.state.comparison_mode

        if len(dataset_ids) < 2:
            QMessageBox.warning(
                self,
                "Comparison",
                "Please select at least 2 datasets for comparison."
            )
            return

        # 비교 대상 설정
        self.state.set_comparison_datasets(dataset_ids)

        # 모드별 처리
        if mode == ComparisonMode.OVERLAY:
            self._start_overlay_comparison(dataset_ids)
        elif mode == ComparisonMode.SIDE_BY_SIDE:
            self._start_side_by_side_comparison(dataset_ids)
        elif mode == ComparisonMode.DIFFERENCE:
            self._start_difference_analysis(dataset_ids)

    def _start_overlay_comparison(self, dataset_ids: List[str]):
        """오버레이 비교 시작"""
        self.statusbar.showMessage(
            f"Overlay comparison: {len(dataset_ids)} datasets",
            3000
        )
        # GraphPanel에서 오버레이 렌더링
        self.graph_panel.refresh()

        # Create and show overlay stats widget
        self._show_overlay_stats_widget()

    def _show_overlay_stats_widget(self):
        """오버레이 통계 위젯 표시"""
        # Create if not exists
        if self._overlay_stats_widget is None:
            self._overlay_stats_widget = OverlayStatsWidget(
                self.engine, self.state, self.graph_panel
            )
            self._overlay_stats_widget.close_requested.connect(self._hide_overlay_stats_widget)
            self._overlay_stats_widget.expand_requested.connect(self._show_comparison_stats_panel)

        # Position and show
        self._overlay_stats_widget.set_position("top-right")
        self._overlay_stats_widget.show_animated()

    def _hide_overlay_stats_widget(self):
        """오버레이 통계 위젯 숨기기"""
        if self._overlay_stats_widget:
            self._overlay_stats_widget.hide_animated()

    def _show_comparison_stats_panel(self):
        """전체 비교 통계 패널 표시 (다이얼로그)"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout

        if self._comparison_stats_panel is None:
            self._comparison_stats_panel = ComparisonStatsPanel(
                self.engine, self.state
            )

        dialog = QDialog(self)
        dialog.setWindowTitle("Comparison Statistics")
        dialog.setMinimumSize(600, 500)

        layout = QVBoxLayout(dialog)
        layout.addWidget(self._comparison_stats_panel)

        self._comparison_stats_panel.refresh()
        dialog.exec()

    def _on_export_comparison_report(self):
        """비교 리포트 내보내기"""
        dataset_ids = self.state.comparison_dataset_ids

        if len(dataset_ids) < 2:
            QMessageBox.information(
                self,
                "Export Report",
                "Please select at least 2 datasets for comparison first."
            )
            return

        # 파일 저장 다이얼로그
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Comparison Report",
            "comparison_report",
            "HTML Report (*.html);;JSON Report (*.json);;CSV Report (*.csv)"
        )

        if not file_path:
            return

        # 확장자 확인 및 추가
        if selected_filter.startswith("HTML") and not file_path.endswith('.html'):
            file_path += '.html'
        elif selected_filter.startswith("JSON") and not file_path.endswith('.json'):
            file_path += '.json'
        elif selected_filter.startswith("CSV") and not file_path.endswith('.csv'):
            file_path += '.csv'

        # 리포트 생성 및 저장
        report_gen = ComparisonReport(self.engine, self.state)

        success = False
        if file_path.endswith('.html'):
            success = report_gen.export_html(file_path, dataset_ids)
        elif file_path.endswith('.json'):
            success = report_gen.export_json(file_path, dataset_ids)
        elif file_path.endswith('.csv'):
            success = report_gen.export_csv(file_path, dataset_ids)

        if success:
            QMessageBox.information(
                self,
                "Export Report",
                f"Report exported successfully:\n{file_path}"
            )
        else:
            QMessageBox.warning(
                self,
                "Export Report",
                "Failed to export report. Please check the file path and try again."
            )

    def _start_side_by_side_comparison(self, dataset_ids: List[str]):
        """병렬 비교 시작"""
        self.statusbar.showMessage(
            f"Side-by-side comparison: {len(dataset_ids)} datasets",
            3000
        )

        # Remove any existing comparison view
        self._remove_comparison_view()

        # Create SideBySideLayout if not exists
        if self._side_by_side_layout is None:
            self._side_by_side_layout = SideBySideLayout(self.engine, self.state)
            self._side_by_side_layout.dataset_activated.connect(self._on_dataset_activated)

        # Replace graph panel with side-by-side layout
        self._show_comparison_view(self._side_by_side_layout)

        # Refresh to show comparison datasets
        self._side_by_side_layout.refresh()

    def _start_difference_analysis(self, dataset_ids: List[str]):
        """차이 분석 시작"""
        if len(dataset_ids) != 2:
            QMessageBox.warning(
                self,
                "Difference Analysis",
                "Please select exactly 2 datasets for difference analysis."
            )
            return

        self.statusbar.showMessage(
            f"Difference analysis: comparing 2 datasets",
            3000
        )

        # Remove any existing comparison view
        self._remove_comparison_view()

        # Create ComparisonStatsPanel if not exists
        if self._comparison_stats_panel is None:
            self._comparison_stats_panel = ComparisonStatsPanel(self.engine, self.state)

        # Replace graph panel with comparison stats panel
        self._show_comparison_view(self._comparison_stats_panel)

        # Refresh to show comparison statistics
        self._comparison_stats_panel.refresh()

    def _show_comparison_view(self, view_widget: QWidget):
        """비교 뷰를 그래프 패널 위치에 표시"""
        # Find graph panel index in splitter
        graph_index = -1
        for i in range(self.main_splitter.count()):
            if self.main_splitter.widget(i) is self.graph_panel:
                graph_index = i
                break

        if graph_index < 0:
            return

        # Save current sizes
        current_sizes = self.main_splitter.sizes()

        # Hide graph panel and show comparison view
        self.graph_panel.hide()
        self.main_splitter.replaceWidget(graph_index, view_widget)
        view_widget.show()

        # Restore sizes
        self.main_splitter.setSizes(current_sizes)

        # Track current comparison view
        self._current_comparison_view = view_widget

    def _remove_comparison_view(self):
        """비교 뷰를 제거하고 그래프 패널 복원"""
        if self._current_comparison_view is None:
            return

        # Find current comparison view index
        view_index = -1
        for i in range(self.main_splitter.count()):
            if self.main_splitter.widget(i) is self._current_comparison_view:
                view_index = i
                break

        if view_index < 0:
            return

        # Save current sizes
        current_sizes = self.main_splitter.sizes()

        # Hide comparison view and restore graph panel
        self._current_comparison_view.hide()
        self._current_comparison_view.setParent(None)
        self.main_splitter.insertWidget(view_index, self.graph_panel)
        self.graph_panel.show()

        # Restore sizes
        self.main_splitter.setSizes(current_sizes)

        # Clear tracking
        self._current_comparison_view = None

    def _restore_single_view(self):
        """단일 뷰 모드로 복귀"""
        self._remove_comparison_view()
        self.graph_panel.refresh()

    def closeEvent(self, event):
        """창 닫기 이벤트"""
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
                self._load_project(file_path)
            elif file_type == 'profile':
                # 프로필 적용
                self._load_profile(file_path)
            else:
                # 데이터 파일 로드
                self._open_file(file_path)
        else:
            # 여러 파일 - 첫 번째 파일만 로드 (또는 다중 로드 다이얼로그)
            self._open_file(files[0])
            self.statusBar().showMessage(f"Loaded first file. {len(files)-1} more files ignored.")
    
    # ==================== Clipboard ====================
    
    def keyPressEvent(self, event):
        """키보드 이벤트 - 클립보드 및 차트 단축키"""
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
        
        # 차트 타입 단축키 (1-6)
        if event.modifiers() == Qt.NoModifier:
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
                self.engine._columns = df.columns
                self.engine._row_count = len(df)
                
                # 상태 업데이트
                self.state.set_data_loaded(True, len(df))
                self.state.set_column_order(df.columns)
                
                # UI 업데이트
                self.table_panel.set_data(df)
                self.graph_panel.set_columns(df.columns)
                
                self.statusBar().showMessage(f"✓ {message}", 5000)
                
            except Exception as e:
                self.statusBar().showMessage(f"Paste error: {e}", 5000)
        else:
            self.statusBar().showMessage(message, 3000)
    
    def _copy_graph_to_clipboard(self):
        """그래프를 이미지로 클립보드에 복사"""
        try:
            if self.graph_panel and self.graph_panel.graph:
                # PyQtGraph에서 이미지 캡처
                exporter = None
                try:
                    from pyqtgraph.exporters import ImageExporter
                    exporter = ImageExporter(self.graph_panel.graph.plotItem)
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
        """계산 필드 추가 다이얼로그"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Add Calculated Field", "No data loaded.")
            return
        
        QMessageBox.information(
            self, "Add Calculated Field",
            "Calculated field dialog will be implemented.\n\n"
            "This feature allows you to create new columns based on expressions."
        )

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
        """테마 변경"""
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

    def _on_open_settings(self):
        """Open Settings - 설정/프로파일 파일 불러오기"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Settings",
            str(Path.home() / ".data_graph_studio"),
            "DGS Settings (*.dgs-settings *.json);;All Files (*.*)"
        )
        if file_path:
            try:
                # 프로파일 로드 시도
                self._on_load_profile_menu()
            except Exception as e:
                QMessageBox.warning(self, "Open Settings", f"Failed to load settings: {e}")

    def _on_open_settings_bundle(self):
        """Open Settings Bundle - 설정 묶음 불러오기"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Settings Bundle",
            str(Path.home() / ".data_graph_studio"),
            "DGS Settings Bundle (*.dgs-bundle *.zip);;All Files (*.*)"
        )
        if file_path:
            QMessageBox.information(
                self, "Open Settings Bundle",
                f"Settings bundle loading will be implemented.\n\nSelected: {file_path}"
            )
            self.statusbar.showMessage(f"Settings bundle: {Path(file_path).name}", 3000)

    def _on_save_data(self):
        """Save Data - 현재 데이터 저장"""
        if not self.state.is_data_loaded:
            QMessageBox.information(self, "Save Data", "No data loaded.")
            return
        
        # 현재 로드된 파일 경로가 있으면 그대로 저장
        current_path = getattr(self.engine, '_current_file_path', None)
        if current_path:
            try:
                self.engine.df.to_csv(current_path, index=False)
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
                    self.engine.df.to_excel(file_path, index=False)
                elif file_path.endswith('.parquet'):
                    self.engine.df.to_parquet(file_path, index=False)
                else:
                    self.engine.df.to_csv(file_path, index=False)
                self.engine._current_file_path = file_path
                self.statusbar.showMessage(f"Data saved to {file_path}", 3000)
            except Exception as e:
                QMessageBox.warning(self, "Save Data As", f"Failed to save: {e}")

    def _on_save_settings(self):
        """Save Settings - 현재 설정 저장"""
        # 현재 프로파일 저장
        self._on_save_profile_menu()

    def _on_save_settings_as(self):
        """Save Settings As - 다른 이름으로 설정 저장"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Settings As",
            str(Path.home() / ".data_graph_studio" / "settings"),
            "DGS Settings (*.dgs-settings);;JSON Files (*.json);;All Files (*.*)"
        )
        if file_path:
            try:
                # 현재 상태를 설정으로 저장
                settings = {
                    'chart_type': self.state._chart_settings.chart_type.name if hasattr(self.state, '_chart_settings') else 'LINE',
                    'x_column': self.state.x_column,
                    'y_columns': list(self.state._y_columns) if hasattr(self.state, '_y_columns') else [],
                    'theme': getattr(self, '_current_theme', 'light'),
                }
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, indent=2)
                self.statusbar.showMessage(f"Settings saved to {file_path}", 3000)
            except Exception as e:
                QMessageBox.warning(self, "Save Settings As", f"Failed to save settings: {e}")

    def _on_save_settings_bundle(self):
        """Save Settings Bundle - 설정 묶음 저장"""
        QMessageBox.information(
            self, "Save Settings Bundle",
            "Settings bundle save functionality will be implemented.\n\n"
            "This will save multiple settings configurations together."
        )

    def _on_save_settings_bundle_as(self):
        """Save Settings Bundle As - 다른 이름으로 설정 묶음 저장"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Settings Bundle As",
            str(Path.home() / ".data_graph_studio" / "bundle"),
            "DGS Settings Bundle (*.dgs-bundle);;ZIP Files (*.zip);;All Files (*.*)"
        )
        if file_path:
            QMessageBox.information(
                self, "Save Settings Bundle As",
                f"Bundle will be saved to:\n{file_path}\n\n(Feature under development)"
            )

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
                    self.engine.df.drop(columns=[column], inplace=True)
                    self.table_panel.set_data(self.engine.df)
                    self.graph_panel.update_graph()
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
