"""
Main Window - 메인 윈도우 및 레이아웃
"""

import os
import gc
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QMenu, QToolBar, QStatusBar, QFileDialog, QMessageBox,
    QProgressDialog, QApplication, QLabel, QDialog, QFrame, QComboBox,
    QInputDialog
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence

from ..core.data_engine import DataEngine, LoadingProgress, FileType, DelimiterType
from ..core.state import AppState, ToolMode, ChartType
from ..utils.memory import MemoryMonitor

# 에러 로깅 설정
logger = logging.getLogger(__name__)

from .panels.summary_panel import SummaryPanel
from .panels.graph_panel import GraphPanel
from .panels.table_panel import TablePanel
from .panels.profile_bar import ProfileBar
from .dialogs.parsing_preview_dialog import ParsingPreviewDialog, ParsingSettings
from .dialogs.save_setting_dialog import SaveSettingDialog
from .dialogs.profile_manager_dialog import ProfileManagerDialog
from .floatable import FloatWindow
from .floating_graph import FloatingGraphWindow, FloatingGraphManager
from ..core.profile import Profile, GraphSetting, ProfileManager


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

        # Loading thread
        self._loader_thread: Optional[DataLoaderThread] = None

        # Float windows tracking
        self._float_windows: Dict[str, FloatWindow] = {}
        self._placeholders: Dict[str, QWidget] = {}

        # Floating graph manager
        self._floating_graph_manager: Optional[FloatingGraphManager] = None

        # Setup UI
        self._setup_window()
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_main_layout()
        self._setup_statusbar()

        # Connect signals
        self._connect_signals()

        # Setup float handlers for main panels
        self._setup_float_handlers()

        # Setup memory monitoring timer
        self._setup_memory_monitor()

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

    @staticmethod
    def _format_tooltip(action_name: str, shortcut: str) -> str:
        """툴팁에 단축키를 보기 좋게 포맷팅"""
        return f"<b>{action_name}</b><br><span style='color: #6B7280;'>Shortcut: {shortcut}</span>"
    
    def _setup_menubar(self):
        """메뉴바 설정"""
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.setStatusTip("Open a data file (Ctrl+O)")
        open_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        save_project_action = QAction("&Save Project...", self)
        save_project_action.setShortcut(QKeySequence.Save)
        save_project_action.setStatusTip("Save current project (Ctrl+S)")
        save_project_action.triggered.connect(self._on_save_project)
        file_menu.addAction(save_project_action)

        file_menu.addSeparator()

        export_menu = file_menu.addMenu("&Export")

        export_csv = QAction("Export as CSV...", self)
        export_csv.setShortcut("Ctrl+E")
        export_csv.setStatusTip("Export data as CSV file")
        export_csv.triggered.connect(lambda: self._on_export("csv"))
        export_menu.addAction(export_csv)

        export_excel = QAction("Export as Excel...", self)
        export_excel.setStatusTip("Export data as Excel file")
        export_excel.triggered.connect(lambda: self._on_export("excel"))
        export_menu.addAction(export_excel)

        export_image = QAction("Export Graph as PNG...", self)
        export_image.setStatusTip("Export current graph as PNG image")
        export_image.triggered.connect(lambda: self._on_export("png"))
        export_menu.addAction(export_image)

        file_menu.addSeparator()

        # Profile submenu
        profile_menu = file_menu.addMenu("&Profile")

        new_profile_action = QAction("New Profile", self)
        new_profile_action.setStatusTip("Create a new profile")
        new_profile_action.triggered.connect(self._on_new_profile_menu)
        profile_menu.addAction(new_profile_action)

        load_profile_action = QAction("Load Profile...", self)
        load_profile_action.setShortcut("Ctrl+Shift+O")
        load_profile_action.setStatusTip("Load a profile file")
        load_profile_action.triggered.connect(self._on_load_profile_menu)
        profile_menu.addAction(load_profile_action)

        save_profile_action = QAction("Save Profile...", self)
        save_profile_action.setShortcut("Ctrl+Shift+S")
        save_profile_action.setStatusTip("Save current profile")
        save_profile_action.triggered.connect(self._on_save_profile_menu)
        profile_menu.addAction(save_profile_action)

        profile_menu.addSeparator()

        manage_profiles_action = QAction("Manage Profiles...", self)
        manage_profiles_action.setStatusTip("Open profile manager")
        manage_profiles_action.triggered.connect(self._show_profile_manager)
        profile_menu.addAction(manage_profiles_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.setStatusTip("Exit application (Ctrl+Q)")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        edit_menu.addAction(undo_action)
        
        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.Redo)
        edit_menu.addAction(redo_action)
        
        edit_menu.addSeparator()
        
        clear_selection = QAction("Clear Selection", self)
        clear_selection.setShortcut(Qt.Key_Escape)
        clear_selection.triggered.connect(self.state.clear_selection)
        edit_menu.addAction(clear_selection)
        
        select_all = QAction("Select All", self)
        select_all.setShortcut(QKeySequence.SelectAll)
        select_all.triggered.connect(self.state.select_all)
        edit_menu.addAction(select_all)
        
        # View Menu
        view_menu = menubar.addMenu("&View")

        reset_layout = QAction("Reset Layout", self)
        reset_layout.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_layout)

        view_menu.addSeparator()

        # Views submenu - Toggle panels visibility
        views_submenu = view_menu.addMenu("Views")

        self._view_actions = {}

        # Overview panel toggle
        overview_action = QAction("Overview", self)
        overview_action.setCheckable(True)
        overview_action.setChecked(True)
        overview_action.triggered.connect(lambda checked: self._toggle_panel_visibility("summary", checked))
        views_submenu.addAction(overview_action)
        self._view_actions["summary"] = overview_action

        # Graph panel toggle
        graph_action = QAction("Graph", self)
        graph_action.setCheckable(True)
        graph_action.setChecked(True)
        graph_action.triggered.connect(lambda checked: self._toggle_panel_visibility("graph", checked))
        views_submenu.addAction(graph_action)
        self._view_actions["graph"] = graph_action

        # Table panel toggle
        table_action = QAction("Table", self)
        table_action.setCheckable(True)
        table_action.setChecked(True)
        table_action.triggered.connect(lambda checked: self._toggle_panel_visibility("table", checked))
        views_submenu.addAction(table_action)
        self._view_actions["table"] = table_action

        view_menu.addSeparator()

        # Chart Type submenu
        chart_menu = view_menu.addMenu("Chart Type")
        for chart_type in ChartType:
            action = QAction(chart_type.value.title(), self)
            action.triggered.connect(lambda checked, ct=chart_type: self.state.set_chart_type(ct))
            chart_menu.addAction(action)
        
        # Help Menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_toolbar(self):
        """Modern toolbar setup"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setStyleSheet("""
            QToolBar {
                background: white;
                border: none;
                border-bottom: 1px solid #E5E7EB;
                padding: 8px 16px;
                spacing: 4px;
            }
            QToolBar::separator {
                width: 1px;
                background: #E5E7EB;
                margin: 6px 12px;
            }
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #374151;
            }
            QToolButton:hover {
                background: #F3F4F6;
            }
            QToolButton:checked {
                background: #EEF2FF;
                color: #4338CA;
            }
            QToolButton:pressed {
                background: #E0E7FF;
            }
        """)
        self.addToolBar(toolbar)
        
        # Open file button with modern style
        open_btn = QAction("📂  Open", self)
        open_btn.setToolTip(self._format_tooltip("Open File", "Ctrl+O"))
        open_btn.triggered.connect(self._on_open_file)
        toolbar.addAction(open_btn)

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

        # Action buttons
        deselect_btn = QAction("✕  Clear", self)
        deselect_btn.setToolTip(self._format_tooltip("Clear Selection", "Esc"))
        deselect_btn.triggered.connect(self.state.clear_selection)
        toolbar.addAction(deselect_btn)

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
        self._chart_type_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        toolbar.addWidget(self._chart_type_label)
        
        chart_types = [
            (ChartType.LINE, "📈", "Line Chart"),
            (ChartType.BAR, "📊", "Bar Chart"),
            (ChartType.SCATTER, "⚬", "Scatter Plot"),
            (ChartType.AREA, "▤", "Area Chart"),
        ]
        
        for ct, icon, tooltip in chart_types:
            action = QAction(icon, self)
            action.setToolTip(tooltip)
            action.triggered.connect(lambda checked, c=ct: self.state.set_chart_type(c))
            toolbar.addAction(action)

        toolbar.addSeparator()

        # Preset management
        preset_label = QLabel("  Preset: ")
        preset_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        toolbar.addWidget(preset_label)

        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(120)
        self._preset_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 4px 8px;
                background: white;
                min-height: 24px;
            }
            QComboBox:hover {
                border-color: #6366F1;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
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
        """메인 레이아웃 설정 (3단 스플리터)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 메인 스플리터 (수직)
        self.main_splitter = QSplitter(Qt.Vertical)

        # Summary Panel (상단)
        self.summary_panel = SummaryPanel(self.state)
        self.main_splitter.addWidget(self.summary_panel)

        # Profile Bar (Summary 아래) - 컨테이너로 감싸서 추가
        self._profile_bar_container = QWidget()
        profile_bar_layout = QVBoxLayout(self._profile_bar_container)
        profile_bar_layout.setContentsMargins(8, 0, 8, 8)
        profile_bar_layout.setSpacing(0)

        self.profile_bar = ProfileBar(self.state)
        self.profile_bar.setting_clicked.connect(self._on_profile_setting_clicked)
        self.profile_bar.setting_double_clicked.connect(self._on_profile_setting_double_clicked)
        self.profile_bar.add_setting_requested.connect(self._on_add_setting_requested)
        profile_bar_layout.addWidget(self.profile_bar)

        self.main_splitter.addWidget(self._profile_bar_container)

        # Graph Panel (중간)
        self.graph_panel = GraphPanel(self.state, self.engine)
        self.main_splitter.addWidget(self.graph_panel)

        # Table Panel (하단)
        self.table_panel = TablePanel(self.state, self.engine)
        self.main_splitter.addWidget(self.table_panel)

        # 초기 비율 설정
        self._reset_layout()

        layout.addWidget(self.main_splitter)

        # Initialize floating graph manager
        self._floating_graph_manager = FloatingGraphManager(self.state, self.engine)
    
    def _reset_layout(self):
        """레이아웃 비율 초기화 및 모든 Float 창 Dock"""
        # First, dock all floating panels back to main window
        float_keys = list(self._float_windows.keys())
        for panel_key in float_keys:
            self._dock_main_panel(panel_key)

        # Ensure all panels are visible and in correct order
        panel_widgets = [self.summary_panel, self._profile_bar_container, self.graph_panel, self.table_panel]

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

        # Set sizes
        total_height = self.main_splitter.height()
        if total_height == 0:
            total_height = 800  # 기본값

        sizes = [
            int(total_height * 0.08),   # Summary
            120,                         # Profile Bar (고정 높이)
            int(total_height * 0.42),   # Graph
            int(total_height * 0.42),   # Table
        ]
        self.main_splitter.setSizes(sizes)

    def _get_panel_key(self, panel: QWidget) -> Optional[str]:
        """Get the panel key for a widget"""
        if panel is self.summary_panel:
            return "summary"
        elif panel is self.graph_panel:
            return "graph"
        elif panel is self.table_panel:
            return "table"
        return None

    def _toggle_panel_visibility(self, panel_key: str, visible: bool):
        """Toggle visibility of a panel"""
        panel_map = {
            "summary": self.summary_panel,
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
        self.statusbar.setStyleSheet("""
            QStatusBar {
                background: #FAFAFA;
                border-top: 1px solid #E5E7EB;
                padding: 6px 16px;
                font-size: 12px;
            }
            QStatusBar::item {
                border: none;
            }
            QLabel {
                color: #6B7280;
                padding: 0 8px;
            }
        """)
        self.setStatusBar(self.statusbar)

        # Status labels with icons
        self._status_data_label = QLabel("📋 No data loaded")
        self._status_data_label.setStyleSheet("color: #9CA3AF;")

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
            self._status_memory_label.setStyleSheet(f"color: {color}; font-weight: 500;")
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

    def _setup_float_handlers(self):
        """메인 패널들의 Float 버튼 핸들러 설정"""
        # Connect float buttons for main panels
        self.summary_panel.float_btn.clicked.connect(lambda: self._float_main_panel("summary"))
        # GraphPanel은 내부적으로 float 처리
        # TablePanel도 내부적으로 float 처리

        # Create placeholders
        for key, title in [("summary", "📊 Overview"), ("graph", "📈 Graph"), ("table", "📋 Table")]:
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
            label = QLabel(f"📤 {title}\n\nFloating as separate window\n\nClick 'Dock' to return")
            label.setStyleSheet("color: #9CA3AF; font-size: 12px; background: transparent;")
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
            self._status_data_label.setStyleSheet("color: #10B981; font-weight: 500;")
        else:
            self._status_data_label.setText("📋 Drag & drop a file to start")
            self._status_data_label.setStyleSheet("color: #9CA3AF;")
    
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
        """파일 열기 다이얼로그"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Data File",
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
            self._show_parsing_preview(file_path)
    
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

            # 프로파일 기반 Summary 업데이트
            if self.engine.profile:
                self._update_summary_from_profile()

            # 로딩 완료 후 메모리 정리
            gc.collect()
            logger.info(f"Data loaded: {self.engine.row_count:,} rows, {self.engine.column_count} columns")
        else:
            error_msg = self.engine.progress.error_message or "Unknown error"
            logger.error(f"Failed to load file: {error_msg}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load file:\n{error_msg}"
            )
    
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
        
        # 그래프 패널에 컬럼 목록 전달 (X-Axis 드롭다운용)
        self.graph_panel.set_columns(self.engine.columns)
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

        # Count column types
        numeric_cols = sum(1 for c in profile.columns if c.is_numeric)
        text_cols = sum(1 for c in profile.columns if not c.is_numeric and not c.is_temporal)
        temporal_cols = sum(1 for c in profile.columns if c.is_temporal)

        # Calculate missing data percentage
        total_cells = profile.total_rows * profile.total_columns
        total_nulls = sum(c.null_count for c in profile.columns)
        missing_percent = (total_nulls / total_cells * 100) if total_cells > 0 else 0

        # Get file name from engine source
        file_name = ""
        if self.engine._source and self.engine._source.path:
            file_name = Path(self.engine._source.path).name

        # Calculate sampled rows (for graph - max 10000 points)
        MAX_GRAPH_POINTS = 10000
        sampled_rows = min(profile.total_rows, MAX_GRAPH_POINTS)

        stats = {
            'file_name': file_name,
            'total_rows': profile.total_rows,
            'sampled_rows': sampled_rows,
            'total_columns': profile.total_columns,
            'numeric_columns': numeric_cols,
            'text_columns': text_cols + temporal_cols,
            'missing_percent': missing_percent,
            'memory_mb': profile.memory_bytes / (1024 * 1024),
            'load_time': profile.load_time_seconds,
        }

        # 숫자형 컬럼 통계
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
            "<h2>Data Graph Studio</h2>"
            "<p>Version 0.1.0</p>"
            "<p>Big Data Visualization Tool</p>"
            "<p>© 2026 Godol</p>"
        )

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

    def closeEvent(self, event):
        """창 닫기 이벤트"""
        # Close all floating graph windows
        if self._floating_graph_manager:
            self._floating_graph_manager.close_all()

        # TODO: 저장 확인
        event.accept()
