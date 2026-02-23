"""Layout setup and panel management for MainWindow.

Handles window construction, toolbar setup, panel layout,
signal wiring, and shortcut configuration. Called once during __init__.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QApplication, QLabel, QFrame,
    QTabWidget, QDockWidget, QLineEdit
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut

from ..utils.memory import MemoryMonitor
from .panels.history_panel import HistoryPanel
from .panels.summary_panel import SummaryPanel
from .panels.graph_panel import GraphPanel
from .panels.table_panel import TablePanel
from .panels.dataset_manager_panel import DatasetManagerPanel
from .floating_graph import FloatingGraphManager
from .models.profile_model import ProfileModel
from .views.project_tree_view import ProjectTreeView



logger = logging.getLogger(__name__)

class _MainWindowLayoutMixin:
    """Mixin providing layout setup and panel management for MainWindow.

    Requires: full MainWindow instance attributes set by MainWindow.__init__
    """

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

        from .panels.profile_bar import ProfileBar
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
            logger.debug("layout_mixin.graph_setting_loaded", extra={"active_id": active_id, "graph_setting": graph_setting})
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
