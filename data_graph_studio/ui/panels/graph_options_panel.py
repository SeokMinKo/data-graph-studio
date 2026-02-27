"""
GraphOptionsPanel - Compact Graph Options Panel
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QScrollArea, QGroupBox, QLineEdit, QPushButton, QSlider,
    QTabWidget, QGridLayout, QMessageBox, QSizePolicy, QMenu,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from .graph_widgets import ColorButton
from .data_tab import DataTab
from ...core.state import AppState, ChartType

if TYPE_CHECKING:
    from ...core.data_engine import DataEngine


# ==================== Options Panel ====================

class GraphOptionsPanel(QFrame):
    """Compact Graph Options Panel"""
    
    option_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("GraphOptionsPanel")
        self.setMinimumWidth(260)
        self.setMaximumWidth(320)
        
        self._setup_ui()
        self._apply_style()
        # Enable sliding window UX by default
        self._on_sliding_window_changed(Qt.Checked)
    
    def _apply_style(self):
        # Styles now handled by global theme stylesheet
        pass
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(8)

        # Header (no float button for internal sections)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QLabel("⚙️ Chart Options")
        header.setObjectName("sectionHeader")
        header_layout.addWidget(header)

        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        # 좁은 패널에서 우측 탭(Axes/Style)이 잘리지 않도록 스크롤 기반 탭바 강제
        tab_bar = self.tabs.tabBar()
        tab_bar.setExpanding(False)
        tab_bar.setUsesScrollButtons(True)
        tab_bar.setElideMode(Qt.ElideRight)
        self.tabs.setElideMode(Qt.ElideRight)
        # Tab bar styling handled by ThemeManager.generate_stylesheet()
        main_layout.addWidget(self.tabs)

        # Tab 0: Data (X/Y/Group/Hover configuration)
        self._data_tab = DataTab(self.state)
        self.tabs.addTab(self._data_tab, "Data")

        # Tab 1: Chart (includes chart type)
        self.tabs.addTab(self._create_chart_tab(), "Chart")

        # Tab 2: Legend (moved here as tab)
        self.tabs.addTab(self._create_legend_tab(), "Legend")

        # Tab 3: Axes
        self.tabs.addTab(self._create_axes_tab(), "Axes")

        # Tab 4: Style
        self.tabs.addTab(self._create_style_tab(), "Style")
    
    def _create_axes_tab(self) -> QWidget:
        """축 설정 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # X-Axis Format Group (no column selection - that's in X Zone)
        x_group = QGroupBox("X-Axis Format")
        x_layout = QGridLayout(x_group)
        x_layout.setSpacing(6)
        x_layout.setColumnMinimumWidth(0, 60)
        x_layout.setColumnStretch(1, 1)

        x_layout.addWidget(QLabel("Title:"), 0, 0)
        self.x_title_edit = QLineEdit()
        self.x_title_edit.setPlaceholderText("Auto")
        self.x_title_edit.textChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_title_edit, 0, 1)

        x_layout.addWidget(QLabel("Format:"), 1, 0)
        self.x_format_combo = QComboBox()
        self.x_format_combo.setEditable(True)
        if self.x_format_combo.lineEdit():
            self.x_format_combo.lineEdit().setPlaceholderText("e.g. 0.00\" MB\"")
        self.x_format_combo.addItems([
            "Auto",
            "Number (#,##0)",
            "Decimal (#,##0.00)",
            "Scientific (0.00E+00)",
            "Percent (0.0%)",
            "K (#,##0,\"K\")",
            "M (#,##0,,\"M\")",
            "B (#,##0,,,\"B\")",
            "KB/MB/GB",
            "ms/s/min"
        ])
        self.x_format_combo.setToolTip(
            "Select preset or type custom Excel-style format:\n"
            "  #,##0 - thousands separator\n"
            "  0.00 - fixed decimals\n"
            "  0.0% - percentage\n"
            "  #,##0,\"K\" - divide by 1000\n"
            "  \"$\"#,##0 - with prefix"
        )
        self.x_format_combo.currentTextChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_format_combo, 1, 1)

        self.x_log_check = QCheckBox("Log Scale")
        self.x_log_check.setToolTip("Use logarithmic scale for X-axis")
        self.x_log_check.stateChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_log_check, 2, 0, 1, 2)

        self.x_reverse_check = QCheckBox("Reverse")
        self.x_reverse_check.setToolTip("Reverse X-axis direction")
        self.x_reverse_check.stateChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_reverse_check, 3, 0, 1, 2)

        layout.addWidget(x_group)

        # Y-Axis Group
        y_group = QGroupBox("Y-Axis")
        y_layout = QGridLayout(y_group)
        y_layout.setSpacing(6)
        y_layout.setColumnMinimumWidth(0, 60)
        y_layout.setColumnStretch(1, 1)

        y_layout.addWidget(QLabel("Title:"), 0, 0)
        self.y_title_edit = QLineEdit()
        self.y_title_edit.setPlaceholderText("Auto")
        self.y_title_edit.textChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_title_edit, 0, 1)

        y_layout.addWidget(QLabel("Format:"), 1, 0)
        self.y_format_combo = QComboBox()
        self.y_format_combo.setEditable(True)
        if self.y_format_combo.lineEdit():
            self.y_format_combo.lineEdit().setPlaceholderText("e.g. 0.00\" MB\"")
        self.y_format_combo.addItems([
            "Auto",
            "Number (#,##0)",
            "Decimal (#,##0.00)",
            "Scientific (0.00E+00)",
            "Percent (0.0%)",
            "K (#,##0,\"K\")",
            "M (#,##0,,\"M\")",
            "B (#,##0,,,\"B\")",
            "KB/MB/GB",
            "ms/s/min"
        ])
        self.y_format_combo.setToolTip(
            "Select preset or type custom Excel-style format:\n"
            "  #,##0 - thousands separator\n"
            "  0.00 - fixed decimals\n"
            "  0.0% - percentage\n"
            "  #,##0,\"K\" - divide by 1000\n"
            "  \"$\"#,##0 - with prefix"
        )
        self.y_format_combo.currentTextChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_format_combo, 1, 1)

        y_layout.addWidget(QLabel("Min:"), 2, 0)
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setToolTip("Minimum Y-axis value (Auto = fit to data)")
        self.y_min_spin.setRange(-1e9, 1e9)
        self.y_min_spin.setSpecialValueText("Auto")
        self.y_min_spin.setValue(self.y_min_spin.minimum())
        self.y_min_spin.valueChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_min_spin, 2, 1)

        y_layout.addWidget(QLabel("Max:"), 3, 0)
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setToolTip("Maximum Y-axis value (Auto = fit to data)")
        self.y_max_spin.setRange(-1e9, 1e9)
        self.y_max_spin.setSpecialValueText("Auto")
        self.y_max_spin.setValue(self.y_max_spin.minimum())
        self.y_max_spin.valueChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_max_spin, 3, 1)

        self.y_log_check = QCheckBox("Log Scale")
        self.y_log_check.setToolTip("Use logarithmic scale for Y-axis")
        self.y_log_check.stateChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_log_check, 4, 0, 1, 2)

        self.y_reverse_check = QCheckBox("Reverse")
        self.y_reverse_check.setToolTip("Reverse Y-axis direction")
        self.y_reverse_check.stateChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_reverse_check, 5, 0, 1, 2)

        layout.addWidget(y_group)

        # Sliding Window Group
        slider_group = QGroupBox("Sliding Window")
        slider_layout = QVBoxLayout(slider_group)

        self.sliding_window_check = QCheckBox("Enable Sliding Window")
        self.sliding_window_check.setChecked(True)
        self.sliding_window_check.stateChanged.connect(self._on_sliding_window_changed)
        self.sliding_window_check.setToolTip("Enable navigation minimap for large datasets")
        slider_layout.addWidget(self.sliding_window_check)

        # X-axis sliding window checkbox
        self.x_sliding_window_check = QCheckBox("X-Axis Navigator")
        self.x_sliding_window_check.setToolTip("Show X-axis minimap navigator")
        self.x_sliding_window_check.setChecked(True)
        self.x_sliding_window_check.setEnabled(True)  # Enabled by default since master is checked
        self.x_sliding_window_check.stateChanged.connect(self._on_option_changed)
        slider_layout.addWidget(self.x_sliding_window_check)

        # Y-axis sliding window checkbox
        self.y_sliding_window_check = QCheckBox("Y-Axis Navigator")
        self.y_sliding_window_check.setToolTip("Show Y-axis minimap navigator")
        self.y_sliding_window_check.setChecked(True)
        self.y_sliding_window_check.setEnabled(True)  # Enabled by default since master is checked
        self.y_sliding_window_check.stateChanged.connect(self._on_option_changed)
        slider_layout.addWidget(self.y_sliding_window_check)

        # Hint label
        hint_label = QLabel("Double-click to reset view")
        hint_label.setObjectName("hintLabel")
        slider_layout.addWidget(hint_label)

        layout.addWidget(slider_group)

        # Grid Group
        grid_group = QGroupBox("Grid")
        grid_layout = QVBoxLayout(grid_group)
        
        self.grid_x_check = QCheckBox("Show X Grid")
        self.grid_x_check.setToolTip("Show vertical grid lines")
        self.grid_x_check.setChecked(True)
        self.grid_x_check.stateChanged.connect(self._on_option_changed)
        grid_layout.addWidget(self.grid_x_check)
        
        self.grid_y_check = QCheckBox("Show Y Grid")
        self.grid_y_check.setToolTip("Show horizontal grid lines")
        self.grid_y_check.setChecked(True)
        self.grid_y_check.stateChanged.connect(self._on_option_changed)
        grid_layout.addWidget(self.grid_y_check)
        
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:"))
        self.grid_opacity_slider = QSlider(Qt.Horizontal)
        self.grid_opacity_slider.setRange(0, 100)
        self.grid_opacity_slider.setValue(30)
        self.grid_opacity_slider.valueChanged.connect(self._on_option_changed)
        opacity_layout.addWidget(self.grid_opacity_slider)
        grid_layout.addLayout(opacity_layout)
        
        layout.addWidget(grid_group)
        
        layout.addStretch()
        return widget
    
    def _create_chart_tab(self) -> QWidget:
        """차트 설정 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        
        # Chart Type
        type_group = QGroupBox("Chart Type")
        type_layout = QVBoxLayout(type_group)
        
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.setToolTip("Select chart visualization type")
        chart_types = [
            ("📈 Line", ChartType.LINE),
            ("📊 Bar", ChartType.BAR),
            ("⬤ Scatter", ChartType.SCATTER),
            ("▤ Area", ChartType.AREA),
            ("🔀 Combination", ChartType.COMBINATION),
            ("📦 Box Plot", ChartType.BOX),
            ("🎻 Violin", ChartType.VIOLIN),
            ("🔥 Heatmap", ChartType.HEATMAP),
        ]
        for label, ct in chart_types:
            self.chart_type_combo.addItem(label, ct)
        self.chart_type_combo.currentIndexChanged.connect(self._on_chart_type_changed)

        # Chart type row: combo + recommend button
        chart_type_row = QHBoxLayout()
        chart_type_row.setSpacing(4)
        chart_type_row.addWidget(self.chart_type_combo, 1)

        self._recommend_btn = QPushButton("💡")
        self._recommend_btn.setFixedSize(28, 28)
        self._recommend_btn.setToolTip("데이터 기반 차트 타입 추천")
        self._recommend_btn.clicked.connect(self._show_chart_recommendations)
        chart_type_row.addWidget(self._recommend_btn)

        type_layout.addLayout(chart_type_row)

        # Per-column chart type selector (visible only in Combination mode)
        self._combo_series_widget = QWidget()
        self._combo_series_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._combo_series_layout = QVBoxLayout(self._combo_series_widget)
        self._combo_series_layout.setContentsMargins(0, 4, 0, 0)
        self._combo_series_layout.setSpacing(2)
        self._combo_series_widget.setVisible(False)
        self._combo_series_combos: Dict[str, QComboBox] = {}
        type_layout.addWidget(self._combo_series_widget)

        layout.addWidget(type_group)

        # Grid View (Facet Grid) Group
        grid_group = QGroupBox("Grid View")
        grid_group.setToolTip("Split data into multiple charts by a category column")
        grid_layout = QVBoxLayout(grid_group)
        grid_layout.setSpacing(6)

        # Enable Grid View checkbox
        self.grid_view_check = QCheckBox("Enable Grid View")
        self.grid_view_check.setToolTip("Split data into facets by selected column")
        self.grid_view_check.stateChanged.connect(self._on_grid_view_changed)
        grid_layout.addWidget(self.grid_view_check)

        # Grid View options container (shown when enabled)
        self._grid_options_widget = QWidget()
        grid_options_layout = QGridLayout(self._grid_options_widget)
        grid_options_layout.setContentsMargins(0, 4, 0, 0)
        grid_options_layout.setSpacing(6)
        grid_options_layout.setColumnMinimumWidth(0, 60)
        grid_options_layout.setColumnStretch(1, 1)

        # Split by column
        grid_options_layout.addWidget(QLabel("Split by:"), 0, 0)
        self.grid_split_combo = QComboBox()
        self.grid_split_combo.setToolTip("Column to split data by (uses Filter panel selections)")
        self.grid_split_combo.currentTextChanged.connect(self._on_grid_split_changed)
        grid_options_layout.addWidget(self.grid_split_combo, 0, 1)

        # Direction
        grid_options_layout.addWidget(QLabel("Direction:"), 1, 0)
        self.grid_direction_combo = QComboBox()
        self.grid_direction_combo.addItems(["Wrap", "Row", "Column"])
        self.grid_direction_combo.setToolTip("Layout direction: Row=horizontal, Column=vertical, Wrap=auto")
        self.grid_direction_combo.currentIndexChanged.connect(self._on_grid_direction_changed)
        grid_options_layout.addWidget(self.grid_direction_combo, 1, 1)

        # Max columns (for Wrap mode)
        grid_options_layout.addWidget(QLabel("Max Cols:"), 2, 0)
        self.grid_max_cols_spin = QSpinBox()
        self.grid_max_cols_spin.setRange(1, 10)
        self.grid_max_cols_spin.setValue(4)
        self.grid_max_cols_spin.setToolTip("Maximum columns in Wrap mode")
        self.grid_max_cols_spin.valueChanged.connect(self._on_grid_max_cols_changed)
        grid_options_layout.addWidget(self.grid_max_cols_spin, 2, 1)

        self._grid_options_widget.setVisible(False)
        grid_layout.addWidget(self._grid_options_widget)

        layout.addWidget(grid_group)
        
        # Title Group
        title_group = QGroupBox("Titles")
        title_layout = QGridLayout(title_group)
        title_layout.setSpacing(6)
        title_layout.setColumnMinimumWidth(0, 60)
        title_layout.setColumnStretch(1, 1)
        
        title_layout.addWidget(QLabel("Title:"), 0, 0)
        self.chart_title_edit = QLineEdit()
        self.chart_title_edit.setPlaceholderText("Chart Title")
        self.chart_title_edit.textChanged.connect(self._on_option_changed)
        title_layout.addWidget(self.chart_title_edit, 0, 1)
        
        title_layout.addWidget(QLabel("Subtitle:"), 1, 0)
        self.chart_subtitle_edit = QLineEdit()
        self.chart_subtitle_edit.setPlaceholderText("Optional")
        self.chart_subtitle_edit.textChanged.connect(self._on_option_changed)
        title_layout.addWidget(self.chart_subtitle_edit, 1, 1)
        
        layout.addWidget(title_group)
        
        # Data Options
        data_group = QGroupBox("Data Options")
        data_layout = QVBoxLayout(data_group)
        
        self.show_labels_check = QCheckBox("Show Data Labels")
        self.show_labels_check.setToolTip("Display values next to data points")
        self.show_labels_check.stateChanged.connect(self._on_option_changed)
        data_layout.addWidget(self.show_labels_check)
        
        self.show_points_check = QCheckBox("Show Data Points")
        self.show_points_check.setToolTip("Show markers at each data point")
        self.show_points_check.setChecked(True)
        self.show_points_check.stateChanged.connect(self._on_option_changed)
        data_layout.addWidget(self.show_points_check)
        
        self.smooth_check = QCheckBox("Smooth Line")
        self.smooth_check.setToolTip("Apply curve smoothing to line chart")
        self.smooth_check.stateChanged.connect(self._on_option_changed)
        data_layout.addWidget(self.smooth_check)

        # Style encoding by column (separate from GroupBy)
        color_by_row = QHBoxLayout()
        color_by_row.addWidget(QLabel("Color by:"))
        self.color_by_combo = QComboBox()
        self.color_by_combo.addItem("(None)", None)
        self.color_by_combo.currentIndexChanged.connect(self._on_option_changed)
        color_by_row.addWidget(self.color_by_combo)
        data_layout.addLayout(color_by_row)

        mark_by_row = QHBoxLayout()
        mark_by_row.addWidget(QLabel("Mark by:"))
        self.mark_by_combo = QComboBox()
        self.mark_by_combo.addItem("(None)", None)
        self.mark_by_combo.currentIndexChanged.connect(self._on_option_changed)
        mark_by_row.addWidget(self.mark_by_combo)
        data_layout.addLayout(mark_by_row)

        layout.addWidget(data_group)

        # Sampling Options
        sampling_group = QGroupBox("Sampling")
        sampling_layout = QVBoxLayout(sampling_group)
        sampling_layout.setSpacing(8)

        # Show All Data checkbox
        self.show_all_data_check = QCheckBox("Show All Data (may be slow)")
        self.show_all_data_check.setToolTip("Disable downsampling — render every data point")
        self.show_all_data_check.setChecked(False)
        self.show_all_data_check.stateChanged.connect(self._on_show_all_data_changed)
        sampling_layout.addWidget(self.show_all_data_check)

        # Max Points slider
        max_points_layout = QVBoxLayout()
        max_points_label_layout = QHBoxLayout()
        max_points_label_layout.addWidget(QLabel("Max Points:"))
        self.max_points_label = QLabel("10,000")
        self.max_points_label.setObjectName("maxPointsLabel")
        max_points_label_layout.addWidget(self.max_points_label)
        max_points_label_layout.addStretch()
        max_points_layout.addLayout(max_points_label_layout)

        self.max_points_slider = QSlider(Qt.Horizontal)
        self.max_points_slider.setRange(1, 100)  # 1K to 100K
        self.max_points_slider.setValue(10)  # Default 10K
        self.max_points_slider.setTickPosition(QSlider.TicksBelow)
        self.max_points_slider.setTickInterval(10)
        self.max_points_slider.valueChanged.connect(self._on_max_points_changed)
        max_points_layout.addWidget(self.max_points_slider)

        # Min/Max labels
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("1K"))
        range_layout.addStretch()
        range_layout.addWidget(QLabel("100K"))
        max_points_layout.addLayout(range_layout)

        sampling_layout.addLayout(max_points_layout)

        # Algorithm selection
        algo_layout = QHBoxLayout()
        algo_layout.addWidget(QLabel("Algorithm:"))
        self.sampling_algo_combo = QComboBox()
        self.sampling_algo_combo.addItems([
            "Auto (LTTB/Min-Max)",
            "LTTB (Time Series)",
            "Min-Max (Extremes)",
            "Random"
        ])
        self.sampling_algo_combo.currentIndexChanged.connect(self._on_option_changed)
        algo_layout.addWidget(self.sampling_algo_combo)
        sampling_layout.addLayout(algo_layout)

        layout.addWidget(sampling_group)

        layout.addStretch()
        return widget
    
    def _create_style_tab(self) -> QWidget:
        """스타일 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        
        # Line Style
        line_group = QGroupBox("Line")
        line_layout = QGridLayout(line_group)
        line_layout.setSpacing(6)
        
        line_layout.addWidget(QLabel("Width:"), 0, 0)
        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 10)
        self.line_width_spin.setValue(2)
        self.line_width_spin.valueChanged.connect(self._on_option_changed)
        line_layout.addWidget(self.line_width_spin, 0, 1)
        
        line_layout.addWidget(QLabel("Style:"), 1, 0)
        self.line_style_combo = QComboBox()
        self.line_style_combo.addItems(["Solid", "Dashed", "Dotted", "Dash-Dot"])
        self.line_style_combo.currentIndexChanged.connect(self._on_option_changed)
        line_layout.addWidget(self.line_style_combo, 1, 1)
        
        layout.addWidget(line_group)
        
        # Marker Style
        marker_group = QGroupBox("Marker")
        marker_layout = QGridLayout(marker_group)
        marker_layout.setSpacing(6)
        
        marker_layout.addWidget(QLabel("Size:"), 0, 0)
        self.marker_size_spin = QSpinBox()
        self.marker_size_spin.setRange(0, 30)
        self.marker_size_spin.setValue(6)
        self.marker_size_spin.valueChanged.connect(self._on_option_changed)
        marker_layout.addWidget(self.marker_size_spin, 0, 1)
        
        marker_layout.addWidget(QLabel("Shape:"), 1, 0)
        self.marker_shape_combo = QComboBox()
        self.marker_shape_combo.addItems(["Circle", "Square", "Triangle", "Diamond", "Cross", "Plus"])
        self.marker_shape_combo.currentIndexChanged.connect(self._on_option_changed)
        marker_layout.addWidget(self.marker_shape_combo, 1, 1)

        self.marker_border_check = QCheckBox("Border")
        self.marker_border_check.setToolTip("Show border outline around markers")
        self.marker_border_check.setChecked(False)
        self.marker_border_check.stateChanged.connect(self._on_option_changed)
        marker_layout.addWidget(self.marker_border_check, 2, 0, 1, 2)

        layout.addWidget(marker_group)
        
        # Fill
        fill_group = QGroupBox("Fill")
        fill_layout = QGridLayout(fill_group)
        fill_layout.setSpacing(6)
        
        fill_layout.addWidget(QLabel("Opacity:"), 0, 0)
        self.fill_opacity_spin = QDoubleSpinBox()
        self.fill_opacity_spin.setRange(0, 1)
        self.fill_opacity_spin.setSingleStep(0.1)
        self.fill_opacity_spin.setValue(0.3)
        self.fill_opacity_spin.valueChanged.connect(self._on_option_changed)
        fill_layout.addWidget(self.fill_opacity_spin, 0, 1)
        
        layout.addWidget(fill_group)
        
        # Background
        bg_group = QGroupBox("Background")
        bg_layout = QVBoxLayout(bg_group)
        
        bg_color_layout = QHBoxLayout()
        bg_color_layout.addWidget(QLabel("Color:"))
        self.bg_color_btn = ColorButton(QColor("#323D4A"))
        self.bg_color_btn.color_changed.connect(self._on_option_changed)
        bg_color_layout.addWidget(self.bg_color_btn)
        bg_color_layout.addStretch()
        bg_layout.addLayout(bg_color_layout)
        
        layout.addWidget(bg_group)
        
        layout.addStretch()
        return widget

    def _create_legend_tab(self) -> QWidget:
        """범례 설정 탭"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Legend Options Group
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.show_legend_check = QCheckBox("Show Legend")
        self.show_legend_check.setChecked(True)
        self.show_legend_check.stateChanged.connect(self._on_option_changed)
        options_layout.addWidget(self.show_legend_check)

        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("Position:"))
        self.legend_pos_combo = QComboBox()
        self.legend_pos_combo.addItems([
            "Top Right", "Top Left", "Bottom Right", "Bottom Left",
            "Top Center", "Bottom Center", "Right", "Left"
        ])
        self.legend_pos_combo.currentIndexChanged.connect(self._on_option_changed)
        pos_layout.addWidget(self.legend_pos_combo)
        options_layout.addLayout(pos_layout)

        layout.addWidget(options_group)

        # Series List Group
        series_group = QGroupBox("Series")
        series_layout = QVBoxLayout(series_group)

        # Scroll area for series list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(150)

        self.series_container = QWidget()
        self.series_list_layout = QVBoxLayout(self.series_container)
        self.series_list_layout.setContentsMargins(0, 0, 0, 0)
        self.series_list_layout.setSpacing(4)
        self.series_list_layout.addStretch()

        scroll.setWidget(self.series_container)
        series_layout.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()

        show_all_btn = QPushButton("Show All")
        show_all_btn.setObjectName("smallButton")
        show_all_btn.clicked.connect(self._show_all_series)
        btn_layout.addWidget(show_all_btn)

        hide_all_btn = QPushButton("Hide All")
        hide_all_btn.setObjectName("smallButton")
        hide_all_btn.clicked.connect(self._hide_all_series)
        btn_layout.addWidget(hide_all_btn)

        series_layout.addLayout(btn_layout)

        layout.addWidget(series_group)

        layout.addStretch()

        # Initialize series items list
        self._series_items: List[Dict] = []
        self._legend_colors = [
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
        ]

        return widget

    def _show_all_series(self):
        for item in self._series_items:
            item['visible_check'].setChecked(True)

    def _hide_all_series(self):
        for item in self._series_items:
            item['visible_check'].setChecked(False)

    def set_series(self, series_names: List[str]):
        """시리즈 목록 설정"""
        # Clear existing
        for item in self._series_items:
            item['widget'].deleteLater()
        self._series_items.clear()

        # Add new series
        for i, name in enumerate(series_names):
            color = QColor(self._legend_colors[i % len(self._legend_colors)])
            self._add_series_item(name, color, i)

    def _add_series_item(self, name: str, color: QColor, index: int):
        """시리즈 아이템 추가"""
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(4, 2, 4, 2)
        item_layout.setSpacing(6)

        # Visibility checkbox
        visible_check = QCheckBox()
        visible_check.setChecked(True)
        visible_check.stateChanged.connect(self._on_option_changed)
        item_layout.addWidget(visible_check)

        # Color button
        color_btn = ColorButton(color)
        color_btn.color_changed.connect(self._on_option_changed)
        item_layout.addWidget(color_btn)

        # Name label
        name_label = QLabel(name)
        name_label.setObjectName("seriesNameLabel")
        item_layout.addWidget(name_label, 1)

        # Insert before stretch
        self.series_list_layout.insertWidget(len(self._series_items), item_widget)

        self._series_items.append({
            'name': name,
            'widget': item_widget,
            'visible_check': visible_check,
            'color_btn': color_btn,
            'index': index
        })

    def get_legend_settings(self) -> Dict[str, Any]:
        """범례 설정 반환"""
        position_map = {
            0: (1, 1),   # Top Right
            1: (1, 0),   # Top Left
            2: (0, 1),   # Bottom Right
            3: (0, 0),   # Bottom Left
            4: (1, 0.5), # Top Center
            5: (0, 0.5), # Bottom Center
            6: (0.5, 1), # Right
            7: (0.5, 0), # Left
        }

        series_settings = []
        for item in self._series_items:
            series_settings.append({
                'name': item['name'],
                'visible': item['visible_check'].isChecked(),
                'color': item['color_btn'].color().name(),
            })

        return {
            'show': self.show_legend_check.isChecked(),
            'position': position_map.get(self.legend_pos_combo.currentIndex(), (1, 1)),
            'series': series_settings
        }

    def _on_max_points_changed(self, value: int):
        """Max points slider changed"""
        points = value * 1000
        self.max_points_label.setText(f"{points:,}")
        # Disable show all data when adjusting max points
        if self.show_all_data_check.isChecked():
            self.show_all_data_check.blockSignals(True)
            self.show_all_data_check.setChecked(False)
            self.show_all_data_check.blockSignals(False)
        self.option_changed.emit()

    def _on_show_all_data_changed(self, state: int):
        """Show all data checkbox changed"""
        if state == Qt.Checked:
            # Show warning dialog
            reply = QMessageBox.warning(
                self,
                "Performance Warning",
                "Displaying all data points may cause significant slowdown "
                "with large datasets (>100K points).\n\n"
                "OpenGL acceleration will be enabled automatically to improve "
                "performance, but the application may still become unresponsive.\n\n"
                "Are you sure you want to continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                self.show_all_data_check.blockSignals(True)
                self.show_all_data_check.setChecked(False)
                self.show_all_data_check.blockSignals(False)
                return

            # Disable max points slider when show all is enabled
            self.max_points_slider.setEnabled(False)
            self.sampling_algo_combo.setEnabled(False)
        else:
            self.max_points_slider.setEnabled(True)
            self.sampling_algo_combo.setEnabled(True)

        self.option_changed.emit()

    def _on_sliding_window_changed(self, state: int):
        """Handle sliding window enable/disable.

        NOTE:
        - Master OFF 시 하위 체크 상태(x/y)는 보존하고 enable 상태만 비활성화한다.
        - 다시 ON 시 기존 체크 상태를 그대로 복원해 즉시 동작 가능하게 한다.
        """
        enabled = state == Qt.Checked
        self.x_sliding_window_check.setEnabled(enabled)
        self.y_sliding_window_check.setEnabled(enabled)
        self.option_changed.emit()

    def _show_chart_recommendations(self):
        """💡 데이터 기반 차트 타입 추천 팝업 표시."""
        engine = getattr(self._data_tab, '_filter_engine', None)
        if engine is None or engine.df is None:
            QMessageBox.information(self, "Chart Recommendation", "데이터를 먼저 로드하세요.")
            return

        x_col = self.state.x_column
        y_cols = [vc.name for vc in self.state.value_columns] if self.state.value_columns else []
        group_cols = [gc.name for gc in self.state.group_columns] if self.state.group_columns else []

        if not y_cols:
            QMessageBox.information(self, "Chart Recommendation", "Y 컬럼을 선택하세요.")
            return

        try:
            recs = engine.recommend_chart_type(x_col, y_cols, group_cols)
        except Exception as e:
            QMessageBox.warning(self, "Chart Recommendation", f"추천 실패: {e}")
            return

        if not recs:
            QMessageBox.information(self, "Chart Recommendation", "추천할 차트 타입이 없습니다.")
            return

        # Show as context menu so user can click to apply
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        for chart_type, reason in recs:
            act = menu.addAction(f"{chart_type.value.upper()} — {reason}")
            act.setData(chart_type)
            act.triggered.connect(lambda checked=False, ct=chart_type: self._apply_recommended_chart(ct))
        menu.exec(self._recommend_btn.mapToGlobal(self._recommend_btn.rect().bottomLeft()))

    def _apply_recommended_chart(self, chart_type):
        """추천된 차트 타입 적용."""
        # Find index in combo
        for i in range(self.chart_type_combo.count()):
            if self.chart_type_combo.itemData(i) == chart_type:
                self.chart_type_combo.setCurrentIndex(i)
                return
        # If not in combo, set directly via state
        self.state.set_chart_type(chart_type)
        self.option_changed.emit()

    def _on_chart_type_changed(self, index: int):
        chart_type = self.chart_type_combo.currentData()
        if chart_type:
            self.state.set_chart_type(chart_type)
        # Show/hide per-column chart type selector
        is_combo = (chart_type == ChartType.COMBINATION)
        self._combo_series_widget.setVisible(is_combo)
        if is_combo:
            self._rebuild_combo_series_ui()
        self.option_changed.emit()

    def _rebuild_combo_series_ui(self):
        """Rebuild per-column chart type selectors for Combination mode."""
        # Clear existing
        for i in reversed(range(self._combo_series_layout.count())):
            w = self._combo_series_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._combo_series_combos.clear()

        combo_chart_types = [
            ("📈 Line", "line"),
            ("📊 Bar", "bar"),
            ("⬤ Scatter", "scatter"),
            ("▤ Area", "area"),
        ]

        for vc in self.state.value_columns:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            label = QLabel(vc.name)
            label.setMinimumWidth(60)
            label.setToolTip(vc.name)
            row_layout.addWidget(label, 1)

            combo = QComboBox()
            combo.setMinimumHeight(24)
            for display, val in combo_chart_types:
                combo.addItem(display, val)
            # Default: first column = line, others = line
            combo.setCurrentIndex(0)
            combo.currentIndexChanged.connect(self._on_combo_series_type_changed)
            row_layout.addWidget(combo, 1)

            self._combo_series_combos[vc.name] = combo
            self._combo_series_layout.addWidget(row)

        # Force layout update — set minimum height based on content
        row_height = 30
        total = len(self._combo_series_combos) * row_height + 8
        self._combo_series_widget.setMinimumHeight(total)
        self._combo_series_widget.adjustSize()
        # Invalidate parent layouts
        parent = self._combo_series_widget.parentWidget()
        while parent:
            if parent.layout():
                parent.layout().invalidate()
            parent = parent.parentWidget()
            if parent and parent.__class__.__name__ == 'QTabWidget':
                break

    def _on_combo_series_type_changed(self):
        """Per-column chart type changed — refresh graph."""
        self.option_changed.emit()

    def get_combo_series_chart_types(self) -> Dict[str, str]:
        """Get per-column chart type mapping for Combination mode."""
        result = {}
        for col_name, combo in self._combo_series_combos.items():
            result[col_name] = combo.currentData() or "line"
        return result

    # ==================== Grid View Handlers ====================

    def _on_grid_view_changed(self, state: int):
        """Handle Grid View enable/disable"""
        from ...core.state import GridDirection
        enabled = state == Qt.Checked
        self._grid_options_widget.setVisible(enabled)
        self.state.set_grid_view_enabled(enabled)
        self.option_changed.emit()

    def _on_grid_split_changed(self, column_name: str):
        """Handle Grid View split column change"""
        self.state.set_grid_view_split_by(column_name if column_name else None)
        self.option_changed.emit()

    def _on_grid_direction_changed(self, index: int):
        """Handle Grid View direction change"""
        from ...core.state import GridDirection
        directions = [GridDirection.WRAP, GridDirection.ROW, GridDirection.COLUMN]
        if 0 <= index < len(directions):
            self.state.set_grid_view_direction(directions[index])
        self.option_changed.emit()

    def _on_grid_max_cols_changed(self, value: int):
        """Handle Grid View max columns change"""
        self.state.update_grid_view_settings(max_columns=value)
        self.option_changed.emit()

    def update_grid_split_columns(self, columns: List[str]):
        """Update the Grid View split column combo box with available filter columns"""
        current = self.grid_split_combo.currentText()
        self.grid_split_combo.blockSignals(True)
        self.grid_split_combo.clear()
        self.grid_split_combo.addItems(columns)
        # Restore previous selection if still available
        if current in columns:
            self.grid_split_combo.setCurrentText(current)
        elif columns:
            self.grid_split_combo.setCurrentIndex(0)
        self.grid_split_combo.blockSignals(False)

    def get_grid_view_settings(self) -> Dict[str, Any]:
        """Get current Grid View settings"""
        from ...core.state import GridDirection
        direction_map = {0: GridDirection.WRAP, 1: GridDirection.ROW, 2: GridDirection.COLUMN}
        return {
            'enabled': self.grid_view_check.isChecked(),
            'split_by': self.grid_split_combo.currentText() or None,
            'direction': direction_map.get(self.grid_direction_combo.currentIndex(), GridDirection.WRAP),
            'max_columns': self.grid_max_cols_spin.value(),
        }
    
    def _on_option_changed(self):
        self.state.update_chart_settings(
            line_width=self.line_width_spin.value(),
            marker_size=self.marker_size_spin.value(),
            fill_opacity=self.fill_opacity_spin.value(),
            show_data_labels=self.show_labels_check.isChecked(),
            x_log_scale=self.x_log_check.isChecked(),
            y_log_scale=self.y_log_check.isChecked()
        )
        self.option_changed.emit()
    
    def _parse_format_text(self, text: str) -> Optional[str]:
        """Parse format combo text to get format type or custom format string"""
        if not text or text == "Auto":
            return None

        # Preset format mapping
        preset_map = {
            "Number (#,##0)": "number",
            "Decimal (#,##0.00)": "decimal",
            "Scientific (0.00E+00)": "scientific",
            "Percent (0.0%)": "percent",
            "K (#,##0,\"K\")": "k",
            "M (#,##0,,\"M\")": "m",
            "B (#,##0,,,\"B\")": "b",
            "KB/MB/GB": "bytes",
            "ms/s/min": "time",
        }

        if text in preset_map:
            return preset_map[text]

        # Return custom format string as-is (for Excel-style formats)
        return text

    # ==================== Data Tab Delegation ====================

    @property
    def data_tab(self) -> DataTab:
        """Access the Data tab widget."""
        return self._data_tab

    def set_columns(self, columns: List[str], engine: DataEngine) -> None:
        """Forward column info to the Data tab after a dataset load."""
        self._all_columns = list(columns)
        self._data_tab.set_columns(columns, engine)

        # Update style encoding combos
        current_color = self.color_by_combo.currentData() if hasattr(self, 'color_by_combo') else None
        current_mark = self.mark_by_combo.currentData() if hasattr(self, 'mark_by_combo') else None
        if hasattr(self, 'color_by_combo'):
            self.color_by_combo.blockSignals(True)
            self.color_by_combo.clear()
            self.color_by_combo.addItem("(None)", None)
            for c in self._all_columns:
                self.color_by_combo.addItem(c, c)
            idx = self.color_by_combo.findData(current_color)
            self.color_by_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.color_by_combo.blockSignals(False)
        if hasattr(self, 'mark_by_combo'):
            self.mark_by_combo.blockSignals(True)
            self.mark_by_combo.clear()
            self.mark_by_combo.addItem("(None)", None)
            for c in self._all_columns:
                self.mark_by_combo.addItem(c, c)
            idx = self.mark_by_combo.findData(current_mark)
            self.mark_by_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.mark_by_combo.blockSignals(False)

    def get_chart_options(self) -> Dict[str, Any]:
        """현재 차트 옵션 반환 (스타일링/포맷팅만)"""
        line_styles = [Qt.SolidLine, Qt.DashLine, Qt.DotLine, Qt.DashDotLine]
        marker_symbols = ['o', 's', 't', 'd', '+', 'x']

        # Sampling algorithm mapping
        sampling_algorithms = ['auto', 'lttb', 'minmax', 'random']

        # Parse format from combo text (handles both presets and custom formats)
        x_format = self._parse_format_text(self.x_format_combo.currentText())
        y_format = self._parse_format_text(self.y_format_combo.currentText())

        return {
            'x_title': self.x_title_edit.text() or None,
            'x_format': x_format,
            'x_log': self.x_log_check.isChecked(),
            'x_reverse': self.x_reverse_check.isChecked(),
            'y_title': self.y_title_edit.text() or None,
            'y_format': y_format,
            'y_min': self.y_min_spin.value() if self.y_min_spin.value() > self.y_min_spin.minimum() else None,
            'y_max': self.y_max_spin.value() if self.y_max_spin.value() > self.y_max_spin.minimum() else None,
            'y_log': self.y_log_check.isChecked(),
            'y_reverse': self.y_reverse_check.isChecked(),
            'grid_x': self.grid_x_check.isChecked(),
            'grid_y': self.grid_y_check.isChecked(),
            'grid_opacity': self.grid_opacity_slider.value() / 100.0,
            'chart_type': self.chart_type_combo.currentData(),
            'title': self.chart_title_edit.text() or None,
            'subtitle': self.chart_subtitle_edit.text() or None,
            'show_labels': self.show_labels_check.isChecked(),
            'show_points': self.show_points_check.isChecked(),
            'smooth': self.smooth_check.isChecked(),
            'line_width': self.line_width_spin.value(),
            'line_style': line_styles[self.line_style_combo.currentIndex()],
            'marker_size': self.marker_size_spin.value(),
            'marker_symbol': marker_symbols[self.marker_shape_combo.currentIndex()],
            'marker_border': self.marker_border_check.isChecked(),
            'fill_opacity': self.fill_opacity_spin.value(),
            'bg_color': self.bg_color_btn.color(),
            # Sampling options
            'show_all_data': self.show_all_data_check.isChecked(),
            'max_points': self.max_points_slider.value() * 1000,
            'sampling_algorithm': sampling_algorithms[self.sampling_algo_combo.currentIndex()],
            'color_by_column': self.color_by_combo.currentData() if hasattr(self, 'color_by_combo') else None,
            'mark_by_column': self.mark_by_combo.currentData() if hasattr(self, 'mark_by_combo') else None,
            # Sliding window options
            'sliding_window_enabled': self.sliding_window_check.isChecked(),
            'x_sliding_window': self.x_sliding_window_check.isChecked(),
            'y_sliding_window': self.y_sliding_window_check.isChecked(),
            # Grid View options
            **self.get_grid_view_settings(),
        }


# ==================== Legend Panel ====================

