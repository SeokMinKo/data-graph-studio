"""ToolbarController - extracted from MainWindow."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QToolBar, QLabel, QPushButton
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QColor

from ...core.state import ToolMode, ChartType
from ..toolbars.compare_toolbar import CompareToolbar



logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..main_window import MainWindow

class ToolbarController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    def _setup_toolbar(self):
        """Main toolbar setup (Line 1)"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.w.addToolBar(toolbar)

        # === Project/Profile I/O Section ===
        open_project_btn = QAction("📂 Open Project", self.w)
        open_project_btn.setToolTip(self.w._format_tooltip("Open Project (.dgs)", "Ctrl+O"))
        open_project_btn.triggered.connect(self.w._on_open_file)
        toolbar.addAction(open_project_btn)

        open_profile_btn = QAction("📂 Open Profile", self.w)
        open_profile_btn.setToolTip(self.w._format_tooltip("Load Graph Profile", ""))
        open_profile_btn.triggered.connect(lambda: self.w.dataset_manager._on_load_profile())
        toolbar.addAction(open_profile_btn)

        save_project_btn = QAction("💾 Save Project", self.w)
        save_project_btn.setToolTip(self.w._format_tooltip("Save Project", "Ctrl+Alt+S"))
        save_project_btn.triggered.connect(self.w._on_save_project_file)
        toolbar.addAction(save_project_btn)

        save_profile_btn = QAction("💾 Save Profile", self.w)
        save_profile_btn.setToolTip(self.w._format_tooltip("Save Graph Profile", ""))
        save_profile_btn.triggered.connect(lambda: self.w.dataset_manager._on_save_profile())
        toolbar.addAction(save_profile_btn)

        toolbar.addSeparator()

        # === Navigation/Selection Tools ===
        self.w._tool_actions = {}

        tools = [
            (ToolMode.ZOOM, "🔍", "Zoom Mode", "Z"),
            (ToolMode.PAN, "✋", "Pan Mode", "H"),
            (ToolMode.RECT_SELECT, "⬚", "Rectangle Select", "R"),
            (ToolMode.LASSO_SELECT, "✏️", "Lasso Select", "L"),
        ]

        for mode, icon, name, shortcut in tools:
            action = QAction(f"{icon}", self.w)
            action.setToolTip(self.w._format_tooltip(name, shortcut))
            action.setCheckable(True)
            action.triggered.connect(lambda checked, m=mode: self.w.state.set_tool_mode(m))
            toolbar.addAction(action)
            self.w._tool_actions[mode] = action

        self.w._tool_actions[ToolMode.PAN].setChecked(True)

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
            action = QAction(f"{icon}", self.w)
            action.setToolTip(self.w._format_tooltip(name, shortcut))
            action.setCheckable(True)
            action.triggered.connect(lambda checked, m=mode: self.w.state.set_tool_mode(m))
            toolbar.addAction(action)
            self.w._tool_actions[mode] = action

        # Draw color picker
        self.w._draw_color = QColor("#FF0000")
        self.w._draw_color_btn = QPushButton()
        self.w._draw_color_btn.setFixedSize(24, 24)
        self.w._draw_color_btn.setCursor(Qt.PointingHandCursor)
        self.w._draw_color_btn.setToolTip("Draw Color — click to change")
        self.w._draw_color_btn.clicked.connect(self.w._on_draw_color_pick)
        self.w._update_draw_color_btn()
        toolbar.addWidget(self.w._draw_color_btn)

        clear_drawing_btn = QAction("🗑️", self.w)
        clear_drawing_btn.setToolTip(self.w._format_tooltip("Clear All Drawings", "Del"))
        clear_drawing_btn.triggered.connect(self.w._on_clear_drawings)
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
            action = QAction(icon, self.w)
            action.setToolTip(tooltip)
            action.triggered.connect(lambda checked, c=ct: self.w.state.set_chart_type(c))
            toolbar.addAction(action)

        # Store references for view actions
        self.w._reset_btn_action = None
        self.w._autofit_btn_action = None


    def _setup_streaming_toolbar(self):
        """Secondary toolbar setup (Line 2) - Streaming + Compare"""
        self.w.addToolBarBreak(Qt.TopToolBarArea)  # Force new line after main toolbar

        toolbar = QToolBar("Secondary Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        self.w.addToolBar(Qt.TopToolBarArea, toolbar)

        # === Streaming Controls (hidden by default, shown when streaming) ===
        self.w._streaming_widgets = []

        streaming_label = QLabel(" Streaming: ")
        streaming_label.setObjectName("toolbarLabel")
        toolbar.addWidget(streaming_label)
        self.w._streaming_widgets.append(streaming_label)

        # Play/Pause
        self.w._streaming_play_action = QAction("▶", self.w)
        self.w._streaming_play_action.setToolTip("Play Streaming")
        self.w._streaming_play_action.setCheckable(True)
        self.w._streaming_play_action.triggered.connect(self.w._on_streaming_play)
        toolbar.addAction(self.w._streaming_play_action)
        self.w._streaming_widgets.append(self.w._streaming_play_action)

        self.w._streaming_pause_action = QAction("⏸", self.w)
        self.w._streaming_pause_action.setToolTip("Pause Streaming")
        self.w._streaming_pause_action.triggered.connect(self.w._on_streaming_pause)
        toolbar.addAction(self.w._streaming_pause_action)
        self.w._streaming_widgets.append(self.w._streaming_pause_action)

        self.w._streaming_stop_action = QAction("⏹", self.w)
        self.w._streaming_stop_action.setToolTip("Stop Streaming")
        self.w._streaming_stop_action.triggered.connect(self.w._on_streaming_stop)
        toolbar.addAction(self.w._streaming_stop_action)
        self.w._streaming_widgets.append(self.w._streaming_stop_action)

        # Speed control
        from PySide6.QtWidgets import QComboBox
        speed_label = QLabel(" Speed: ")
        speed_label.setObjectName("toolbarLabel")
        toolbar.addWidget(speed_label)
        self.w._streaming_widgets.append(speed_label)

        self.w._streaming_speed_combo = QComboBox()
        self.w._streaming_speed_combo.addItems(["0.5x", "1x", "2x", "5x", "10x"])
        self.w._streaming_speed_combo.setCurrentIndex(1)  # Default 1x
        self.w._streaming_speed_combo.currentTextChanged.connect(self.w._on_streaming_speed_changed)
        self.w._streaming_speed_combo.setFixedWidth(60)
        toolbar.addWidget(self.w._streaming_speed_combo)
        self.w._streaming_widgets.append(self.w._streaming_speed_combo)

        # Window size
        window_label = QLabel(" Window: ")
        window_label.setObjectName("toolbarLabel")
        toolbar.addWidget(window_label)
        self.w._streaming_widgets.append(window_label)

        self.w._streaming_window_combo = QComboBox()
        self.w._streaming_window_combo.addItems(["100", "500", "1000", "5000", "All"])
        self.w._streaming_window_combo.setCurrentIndex(2)  # Default 1000
        self.w._streaming_window_combo.currentTextChanged.connect(self.w._on_streaming_window_changed)
        self.w._streaming_window_combo.setFixedWidth(70)
        toolbar.addWidget(self.w._streaming_window_combo)
        self.w._streaming_widgets.append(self.w._streaming_window_combo)

        # Hide streaming controls initially
        self._hide_streaming_controls()

        toolbar.addSeparator()

        # === View Controls (always visible) ===
        view_label = QLabel(" View: ")
        view_label.setObjectName("toolbarLabel")
        toolbar.addWidget(view_label)

        deselect_btn = QAction("✕ Clear", self.w)
        deselect_btn.setToolTip(self.w._format_tooltip("Clear Selection", "Esc"))
        deselect_btn.triggered.connect(self.w._on_clear_selection)
        toolbar.addAction(deselect_btn)

        reset_btn = QAction("↺ Reset", self.w)
        reset_btn.setToolTip(self.w._format_tooltip("Reset View", "Home"))
        reset_btn.triggered.connect(self.w._reset_graph_view)
        toolbar.addAction(reset_btn)
        self.w._reset_btn_action = reset_btn

        autofit_btn = QAction("⊡ Fit", self.w)
        autofit_btn.setToolTip(self.w._format_tooltip("Auto Fit to Data", "F"))
        autofit_btn.triggered.connect(self.w._autofit_graph)
        toolbar.addAction(autofit_btn)
        self.w._autofit_btn_action = autofit_btn

        toolbar.addSeparator()

        # === Quick Actions ===
        theme_toggle_btn = QAction("🌓", self.w)
        theme_toggle_btn.setToolTip(self.w._format_tooltip("Cycle Theme", "Ctrl+T"))
        theme_toggle_btn.triggered.connect(self.w._on_cycle_theme)
        toolbar.addAction(theme_toggle_btn)

        export_btn = QAction("📤", self.w)
        export_btn.setToolTip(self.w._format_tooltip("Export", "Ctrl+E"))
        export_btn.triggered.connect(self.w._on_export_dialog)
        toolbar.addAction(export_btn)

    def _show_streaming_controls(self):
        """Show streaming-related toolbar widgets."""
        for widget in self.w._streaming_widgets:
            if isinstance(widget, QAction):
                widget.setVisible(True)
            else:
                widget.setVisible(True)

    def _hide_streaming_controls(self):
        """Hide streaming-related toolbar widgets."""
        for widget in self.w._streaming_widgets:
            if isinstance(widget, QAction):
                widget.setVisible(False)
            else:
                widget.setVisible(False)

    def _setup_compare_toolbar(self):
        """Setup the Compare Toolbar (hidden by default, auto-shown during comparison)."""
        self.w._compare_toolbar = CompareToolbar(self.w)
        self.w.addToolBar(Qt.TopToolBarArea, self.w._compare_toolbar)
        self.w._compare_toolbar.hide()

        # View menu: "Compare Toolbar" toggle action
        # Find View menu
        view_menu = None
        for action in self.w.menuBar().actions():
            if action.text().replace("&", "") == "View":
                view_menu = action.menu()
                break

        if view_menu is not None:
            view_menu.addSeparator()
            self.w._compare_toolbar_action = self.w._compare_toolbar.toggleViewAction()
            self.w._compare_toolbar_action.setText("Compare Toolbar")
            self.w._compare_toolbar_action.setToolTip("Show/hide the compare toolbar")
            view_menu.addAction(self.w._compare_toolbar_action)


