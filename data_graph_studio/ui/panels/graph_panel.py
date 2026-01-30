"""
Graph Panel - 메인 그래프 + 옵션 + 범례 + 통계
"""

from typing import Optional, List, Dict, Any
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QScrollArea, QSplitter, QToolButton, QButtonGroup,
    QSizePolicy, QGroupBox, QDialog, QDialogButtonBox,
    QLineEdit, QColorDialog, QPushButton, QSlider,
    QTabWidget, QListWidget, QListWidgetItem, QGridLayout
)
from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtGui import QMouseEvent, QColor, QIcon, QPixmap, QPainter

import pyqtgraph as pg


# ==================== Helper Classes ====================

class ColorButton(QPushButton):
    """색상 선택 버튼"""
    
    color_changed = Signal(QColor)
    
    def __init__(self, color: QColor = QColor("#1f77b4"), parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._on_clicked)
        self._update_style()
    
    def _update_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self._color.name()};
                border: 2px solid #E5E7EB;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: #6366F1;
            }}
        """)
    
    def _on_clicked(self):
        color = QColorDialog.getColor(self._color, self, "Select Color")
        if color.isValid():
            self._color = color
            self._update_style()
            self.color_changed.emit(color)
    
    def color(self) -> QColor:
        return self._color
    
    def set_color(self, color: QColor):
        self._color = color
        self._update_style()


class ExpandedChartDialog(QDialog):
    """확대된 차트를 보여주는 다이얼로그"""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.plot_widget)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.close)
        layout.addWidget(button_box)
    
    def plot_histogram(self, data: np.ndarray, title: str, color: tuple):
        self.setWindowTitle(title)
        self.plot_widget.clear()
        
        if data is not None and len(data) > 0:
            try:
                clean_data = data[~np.isnan(data)]
                hist, bins = np.histogram(clean_data, bins=50)
                self.plot_widget.plot(bins, hist, stepMode=True, fillLevel=0, 
                                      brush=color, pen=pg.mkPen(color[:3], width=1))
                self.plot_widget.setLabel('bottom', 'Value')
                self.plot_widget.setLabel('left', 'Frequency')
                
                mean_val = np.mean(clean_data)
                self.plot_widget.addLine(x=mean_val, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
                
                stats_text = f"Mean: {mean_val:.2f}\nMedian: {np.median(clean_data):.2f}\nStd: {np.std(clean_data):.2f}"
                text_item = pg.TextItem(stats_text, anchor=(0, 0), color='k')
                text_item.setPos(bins[0], max(hist) * 0.9)
                self.plot_widget.addItem(text_item)
            except Exception as e:
                print(f"Error plotting histogram: {e}")


class ClickablePlotWidget(pg.PlotWidget):
    """더블클릭 가능한 PlotWidget"""
    
    double_clicked = Signal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = None
        self._title = ""
        self._color = (100, 100, 200, 100)
    
    def set_data(self, data: np.ndarray, title: str, color: tuple):
        self._data = data
        self._title = title
        self._color = color
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            self._show_expanded()
        super().mouseDoubleClickEvent(event)
    
    def _show_expanded(self):
        if self._data is None:
            return
        dialog = ExpandedChartDialog(self._title, self)
        dialog.plot_histogram(self._data, self._title, self._color)
        dialog.exec()


from ...core.state import AppState, ChartType, ToolMode
from ...core.data_engine import DataEngine
from ...graph.sampling import DataSampler


# ==================== Options Panel ====================

class GraphOptionsPanel(QFrame):
    """Enhanced Graph Options Panel - Excel-like"""
    
    option_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("GraphOptionsPanel")
        self.setMinimumWidth(240)
        self.setMaximumWidth(280)
        
        self._setup_ui()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #GraphOptionsPanel {
                background: #FAFAFA;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
            QTabWidget::pane {
                border: none;
                background: transparent;
            }
            QTabBar::tab {
                background: #F3F4F6;
                border: none;
                padding: 8px 12px;
                margin-right: 2px;
                border-radius: 6px 6px 0 0;
                font-size: 11px;
                color: #6B7280;
            }
            QTabBar::tab:selected {
                background: white;
                color: #4F46E5;
                font-weight: 600;
            }
            QGroupBox {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                margin-top: 14px;
                padding: 12px;
                font-weight: 600;
                font-size: 11px;
                color: #374151;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                background: white;
            }
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
                background: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 5px;
                padding: 5px 8px;
                color: #374151;
                min-height: 24px;
            }
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
                border-color: #6366F1;
            }
            QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
                border-color: #4F46E5;
            }
            QCheckBox {
                color: #374151;
                font-size: 11px;
                spacing: 6px;
            }
            QLabel {
                color: #6B7280;
                font-size: 11px;
                background: transparent;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #E5E7EB;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin: -5px 0;
                background: #4F46E5;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #4F46E5;
                border-radius: 2px;
            }
        """)
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Header
        header = QLabel("⚙️ Chart Options")
        header.setStyleSheet("font-weight: 600; font-size: 13px; color: #111827; padding: 4px;")
        main_layout.addWidget(header)
        
        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Tab 1: Axes
        self.tabs.addTab(self._create_axes_tab(), "Axes")
        
        # Tab 2: Chart
        self.tabs.addTab(self._create_chart_tab(), "Chart")
        
        # Tab 3: Style
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
        
        x_layout.addWidget(QLabel("Title:"), 0, 0)
        self.x_title_edit = QLineEdit()
        self.x_title_edit.setPlaceholderText("Auto")
        self.x_title_edit.textChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_title_edit, 0, 1)
        
        self.x_log_check = QCheckBox("Log Scale")
        self.x_log_check.stateChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_log_check, 1, 0, 1, 2)
        
        self.x_reverse_check = QCheckBox("Reverse")
        self.x_reverse_check.stateChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_reverse_check, 2, 0, 1, 2)
        
        layout.addWidget(x_group)
        
        # Y-Axis Group
        y_group = QGroupBox("Y-Axis")
        y_layout = QGridLayout(y_group)
        y_layout.setSpacing(6)
        
        y_layout.addWidget(QLabel("Title:"), 0, 0)
        self.y_title_edit = QLineEdit()
        self.y_title_edit.setPlaceholderText("Auto")
        self.y_title_edit.textChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_title_edit, 0, 1)
        
        y_layout.addWidget(QLabel("Min:"), 1, 0)
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setRange(-1e9, 1e9)
        self.y_min_spin.setSpecialValueText("Auto")
        self.y_min_spin.setValue(self.y_min_spin.minimum())
        self.y_min_spin.valueChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_min_spin, 1, 1)
        
        y_layout.addWidget(QLabel("Max:"), 2, 0)
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setRange(-1e9, 1e9)
        self.y_max_spin.setSpecialValueText("Auto")
        self.y_max_spin.setValue(self.y_max_spin.minimum())
        self.y_max_spin.valueChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_max_spin, 2, 1)
        
        self.y_log_check = QCheckBox("Log Scale")
        self.y_log_check.stateChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_log_check, 3, 0, 1, 2)
        
        self.y_reverse_check = QCheckBox("Reverse")
        self.y_reverse_check.stateChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_reverse_check, 4, 0, 1, 2)
        
        layout.addWidget(y_group)
        
        # Grid Group
        grid_group = QGroupBox("Grid")
        grid_layout = QVBoxLayout(grid_group)
        
        self.grid_x_check = QCheckBox("Show X Grid")
        self.grid_x_check.setChecked(True)
        self.grid_x_check.stateChanged.connect(self._on_option_changed)
        grid_layout.addWidget(self.grid_x_check)
        
        self.grid_y_check = QCheckBox("Show Y Grid")
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
        chart_types = [
            ("📈 Line", ChartType.LINE),
            ("📊 Bar", ChartType.BAR),
            ("⬤ Scatter", ChartType.SCATTER),
            ("▤ Area", ChartType.AREA),
            ("📦 Box Plot", ChartType.BOX),
            ("🎻 Violin", ChartType.VIOLIN),
            ("🔥 Heatmap", ChartType.HEATMAP),
        ]
        for label, ct in chart_types:
            self.chart_type_combo.addItem(label, ct)
        self.chart_type_combo.currentIndexChanged.connect(self._on_chart_type_changed)
        type_layout.addWidget(self.chart_type_combo)
        
        layout.addWidget(type_group)
        
        # Title Group
        title_group = QGroupBox("Titles")
        title_layout = QGridLayout(title_group)
        title_layout.setSpacing(6)
        
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
        self.show_labels_check.stateChanged.connect(self._on_option_changed)
        data_layout.addWidget(self.show_labels_check)
        
        self.show_points_check = QCheckBox("Show Data Points")
        self.show_points_check.setChecked(True)
        self.show_points_check.stateChanged.connect(self._on_option_changed)
        data_layout.addWidget(self.show_points_check)
        
        self.smooth_check = QCheckBox("Smooth Line")
        self.smooth_check.stateChanged.connect(self._on_option_changed)
        data_layout.addWidget(self.smooth_check)
        
        layout.addWidget(data_group)
        
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
        self.bg_color_btn = ColorButton(QColor("#FFFFFF"))
        self.bg_color_btn.color_changed.connect(self._on_option_changed)
        bg_color_layout.addWidget(self.bg_color_btn)
        bg_color_layout.addStretch()
        bg_layout.addLayout(bg_color_layout)
        
        layout.addWidget(bg_group)
        
        layout.addStretch()
        return widget
    
    def _on_chart_type_changed(self, index: int):
        chart_type = self.chart_type_combo.currentData()
        if chart_type:
            self.state.set_chart_type(chart_type)
        self.option_changed.emit()
    
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
    
    def get_chart_options(self) -> Dict[str, Any]:
        """현재 차트 옵션 반환 (스타일링/포맷팅만)"""
        line_styles = [Qt.SolidLine, Qt.DashLine, Qt.DotLine, Qt.DashDotLine]
        marker_symbols = ['o', 's', 't', 'd', '+', 'x']
        
        return {
            'x_title': self.x_title_edit.text() or None,
            'x_log': self.x_log_check.isChecked(),
            'x_reverse': self.x_reverse_check.isChecked(),
            'y_title': self.y_title_edit.text() or None,
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
            'fill_opacity': self.fill_opacity_spin.value(),
            'bg_color': self.bg_color_btn.color(),
        }


# ==================== Legend Panel ====================

class LegendSettingsPanel(QFrame):
    """범례 설정 패널"""
    
    settings_changed = Signal()
    
    # Default colors
    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("LegendPanel")
        self.setMinimumWidth(200)
        self.setMaximumWidth(240)
        
        self._series_items: List[Dict] = []  # {name, color_btn, visible_check}
        self._setup_ui()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #LegendPanel {
                background: #FAFAFA;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
            QGroupBox {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                margin-top: 14px;
                padding: 10px;
                font-weight: 600;
                font-size: 11px;
                color: #374151;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                background: white;
            }
            QComboBox {
                background: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 5px;
                padding: 5px 8px;
                color: #374151;
                min-height: 24px;
            }
            QCheckBox {
                color: #374151;
                font-size: 11px;
            }
            QLabel {
                color: #6B7280;
                font-size: 11px;
                background: transparent;
            }
            QListWidget {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 4px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background: #F3F4F6;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("📊 Legend")
        header.setStyleSheet("font-weight: 600; font-size: 13px; color: #111827; padding: 4px;")
        layout.addWidget(header)
        
        # Legend Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        
        self.show_legend_check = QCheckBox("Show Legend")
        self.show_legend_check.setChecked(True)
        self.show_legend_check.stateChanged.connect(self._on_settings_changed)
        options_layout.addWidget(self.show_legend_check)
        
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("Position:"))
        self.legend_pos_combo = QComboBox()
        self.legend_pos_combo.addItems([
            "Top Right", "Top Left", "Bottom Right", "Bottom Left",
            "Top Center", "Bottom Center", "Right", "Left"
        ])
        self.legend_pos_combo.currentIndexChanged.connect(self._on_settings_changed)
        pos_layout.addWidget(self.legend_pos_combo)
        options_layout.addLayout(pos_layout)
        
        layout.addWidget(options_group)
        
        # Series List
        series_group = QGroupBox("Series")
        series_layout = QVBoxLayout(series_group)
        
        # Scroll area for series list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(150)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
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
        show_all_btn.setStyleSheet("font-size: 10px; padding: 4px 8px;")
        show_all_btn.clicked.connect(self._show_all_series)
        btn_layout.addWidget(show_all_btn)
        
        hide_all_btn = QPushButton("Hide All")
        hide_all_btn.setStyleSheet("font-size: 10px; padding: 4px 8px;")
        hide_all_btn.clicked.connect(self._hide_all_series)
        btn_layout.addWidget(hide_all_btn)
        
        series_layout.addLayout(btn_layout)
        
        layout.addWidget(series_group)
        
        layout.addStretch()
    
    def set_series(self, series_names: List[str]):
        """시리즈 목록 설정"""
        # Clear existing
        for item in self._series_items:
            item['widget'].deleteLater()
        self._series_items.clear()
        
        # Add new series
        for i, name in enumerate(series_names):
            color = QColor(self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)])
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
        visible_check.stateChanged.connect(self._on_settings_changed)
        item_layout.addWidget(visible_check)
        
        # Color button
        color_btn = ColorButton(color)
        color_btn.color_changed.connect(self._on_settings_changed)
        item_layout.addWidget(color_btn)
        
        # Name label
        name_label = QLabel(name)
        name_label.setStyleSheet("font-size: 11px; color: #374151;")
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
    
    def _show_all_series(self):
        for item in self._series_items:
            item['visible_check'].setChecked(True)
    
    def _hide_all_series(self):
        for item in self._series_items:
            item['visible_check'].setChecked(False)
    
    def _on_settings_changed(self):
        self.settings_changed.emit()
    
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


# ==================== Stat Panel ====================

class StatPanel(QFrame):
    """Statistics Panel"""
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("StatPanel")
        self.setMinimumWidth(180)
        self.setMaximumWidth(220)
        
        self._x_data: Optional[np.ndarray] = None
        self._y_data: Optional[np.ndarray] = None
        
        self._setup_ui()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #StatPanel {
                background: #FAFAFA;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
            QGroupBox {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
                margin-top: 12px;
                padding: 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                background: white;
                color: #374151;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("📈 Statistics")
        header.setStyleSheet("font-weight: 600; font-size: 13px; color: #111827; padding: 4px;")
        layout.addWidget(header)
        
        # X Distribution
        x_group = QGroupBox("X Distribution")
        x_group.setToolTip("Double-click to expand")
        x_layout = QVBoxLayout(x_group)
        
        self.x_hist_widget = ClickablePlotWidget()
        self.x_hist_widget.setMaximumHeight(80)
        self.x_hist_widget.setBackground('w')
        self.x_hist_widget.hideAxis('bottom')
        self.x_hist_widget.hideAxis('left')
        self.x_hist_widget.setCursor(Qt.PointingHandCursor)
        x_layout.addWidget(self.x_hist_widget)
        
        layout.addWidget(x_group)
        
        # Y Distribution
        y_group = QGroupBox("Y Distribution")
        y_group.setToolTip("Double-click to expand")
        y_layout = QVBoxLayout(y_group)
        
        self.y_hist_widget = ClickablePlotWidget()
        self.y_hist_widget.setMaximumHeight(80)
        self.y_hist_widget.setBackground('w')
        self.y_hist_widget.hideAxis('bottom')
        self.y_hist_widget.hideAxis('left')
        self.y_hist_widget.setCursor(Qt.PointingHandCursor)
        y_layout.addWidget(self.y_hist_widget)
        
        layout.addWidget(y_group)
        
        # Summary Stats
        stats_group = QGroupBox("Summary")
        stats_layout = QVBoxLayout(stats_group)
        
        self.stats_label = QLabel("No data")
        self.stats_label.setStyleSheet("font-family: 'Consolas', monospace; font-size: 10px; color: #4B5563;")
        self.stats_label.setWordWrap(True)
        stats_layout.addWidget(self.stats_label)
        
        layout.addWidget(stats_group)
        
        layout.addStretch()
    
    def update_histograms(self, x_data: Optional[np.ndarray], y_data: Optional[np.ndarray]):
        self._x_data = x_data
        self._y_data = y_data
        
        self.x_hist_widget.clear()
        if x_data is not None and len(x_data) > 0:
            try:
                clean_x = x_data[~np.isnan(x_data)]
                hist, bins = np.histogram(clean_x, bins=30)
                self.x_hist_widget.plot(bins, hist, stepMode=True, fillLevel=0, 
                                        brush=(100, 100, 200, 100))
                self.x_hist_widget.set_data(x_data, "X-Axis Distribution", (100, 100, 200, 150))
            except:
                pass
        
        self.y_hist_widget.clear()
        if y_data is not None and len(y_data) > 0:
            try:
                clean_y = y_data[~np.isnan(y_data)]
                hist, bins = np.histogram(clean_y, bins=30)
                self.y_hist_widget.plot(bins, hist, stepMode=True, fillLevel=0,
                                        brush=(100, 200, 100, 100))
                self.y_hist_widget.set_data(y_data, "Y-Axis Distribution", (100, 200, 100, 150))
            except:
                pass
    
    def update_stats(self, stats: Dict[str, Any]):
        if not stats:
            self.stats_label.setText("No data")
            return
        
        lines = []
        for key, value in stats.items():
            if isinstance(value, float):
                lines.append(f"{key}: {value:.2f}")
            else:
                lines.append(f"{key}: {value}")
        
        self.stats_label.setText("\n".join(lines))


# ==================== Main Graph ====================

class MainGraph(pg.PlotWidget):
    """메인 그래프 위젯"""
    
    points_selected = Signal(list)
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        
        self.setBackground('w')
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setLabel('left', '')
        self.setLabel('bottom', '')
        
        self.legend = self.addLegend()
        
        self._plot_items = []
        self._scatter_items = []
        self._data_x = None
        self._data_y = None
        
        self.scene().sigMouseClicked.connect(self._on_mouse_clicked)
    
    def plot_data(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        groups: Optional[Dict[str, np.ndarray]] = None,
        chart_type: ChartType = ChartType.LINE,
        options: Optional[Dict] = None,
        legend_settings: Optional[Dict] = None
    ):
        self.clear_plot()
        
        self._data_x = x_data
        self._data_y = y_data
        
        options = options or {}
        legend_settings = legend_settings or {'show': True, 'series': []}
        
        # Apply options
        x_label = options.get('x_title', 'X')
        y_label = options.get('y_title', 'Y')
        self.setLabel('bottom', x_label)
        self.setLabel('left', y_label)
        
        # Grid
        grid_x = options.get('grid_x', True)
        grid_y = options.get('grid_y', True)
        grid_alpha = options.get('grid_opacity', 0.3)
        self.showGrid(x=grid_x, y=grid_y, alpha=grid_alpha)
        
        # Background
        bg_color = options.get('bg_color', QColor('#FFFFFF'))
        self.setBackground(bg_color.name())
        
        # Title
        title = options.get('title')
        if title:
            self.setTitle(title)
        
        # Y-axis range
        y_min = options.get('y_min')
        y_max = options.get('y_max')
        if y_min is not None and y_max is not None:
            self.setYRange(y_min, y_max)
        
        # Log scale
        if options.get('x_log'):
            self.setLogMode(x=True, y=False)
        if options.get('y_log'):
            self.setLogMode(x=self.getPlotItem().getAxis('bottom').logMode, y=True)
        
        # Legend visibility
        if legend_settings.get('show', True):
            self.legend.show()
        else:
            self.legend.hide()
        
        # Get style options
        line_width = options.get('line_width', 2)
        marker_size = options.get('marker_size', 6)
        line_style = options.get('line_style', Qt.SolidLine)
        marker_symbol = options.get('marker_symbol', 'o')
        show_points = options.get('show_points', True)
        
        # Default colors
        default_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        
        # Get series colors from legend settings
        series_colors = {}
        series_visible = {}
        for s in legend_settings.get('series', []):
            series_colors[s['name']] = s.get('color', default_colors[0])
            series_visible[s['name']] = s.get('visible', True)
        
        if groups:
            for i, (group_name, mask) in enumerate(groups.items()):
                if not series_visible.get(group_name, True):
                    continue  # Skip hidden series
                
                color = series_colors.get(group_name, default_colors[i % len(default_colors)])
                self._plot_series(
                    x_data[mask], y_data[mask],
                    chart_type, color, group_name,
                    line_width, marker_size, line_style, marker_symbol, show_points
                )
        else:
            color = default_colors[0]
            if legend_settings.get('series'):
                first_series = legend_settings['series'][0]
                color = first_series.get('color', color)
                if not first_series.get('visible', True):
                    return  # Hidden
            
            self._plot_series(
                x_data, y_data,
                chart_type, color, None,
                line_width, marker_size, line_style, marker_symbol, show_points
            )
    
    def _plot_series(
        self,
        x: np.ndarray,
        y: np.ndarray,
        chart_type: ChartType,
        color: str,
        name: Optional[str],
        line_width: int,
        marker_size: int,
        line_style: Qt.PenStyle,
        marker_symbol: str,
        show_points: bool
    ):
        pen = pg.mkPen(color=color, width=line_width, style=line_style)
        brush = pg.mkBrush(color=color)
        
        if chart_type == ChartType.LINE:
            item = self.plot(x, y, pen=pen, name=name)
            if show_points and marker_size > 0:
                scatter = pg.ScatterPlotItem(x, y, size=marker_size, brush=brush, symbol=marker_symbol)
                self.addItem(scatter)
                self._scatter_items.append(scatter)
                
        elif chart_type == ChartType.SCATTER:
            scatter = pg.ScatterPlotItem(x, y, size=marker_size, brush=brush, symbol=marker_symbol, name=name)
            self.addItem(scatter)
            self._scatter_items.append(scatter)
            item = scatter
            
        elif chart_type == ChartType.BAR:
            width = (x.max() - x.min()) / len(x) * 0.8 if len(x) > 1 else 0.8
            item = pg.BarGraphItem(x=x, height=y, width=width, brush=brush, name=name)
            self.addItem(item)
            
        elif chart_type == ChartType.AREA:
            fill_brush = pg.mkBrush(color=color)
            fill_color = QColor(color)
            fill_color.setAlpha(50)
            item = self.plot(x, y, pen=pen, fillLevel=0, brush=fill_color, name=name)
            
        else:
            item = self.plot(x, y, pen=pen, name=name)
        
        self._plot_items.append(item)
    
    def clear_plot(self):
        for item in self._plot_items:
            self.removeItem(item)
        for item in self._scatter_items:
            self.removeItem(item)
        self._plot_items.clear()
        self._scatter_items.clear()
        self._data_x = None
        self._data_y = None
        self.legend.clear()
    
    def reset_view(self):
        self.autoRange()
        self.setLogMode(x=False, y=False)
    
    def _on_mouse_clicked(self, event):
        if self.state.tool_mode in [ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT]:
            pos = event.scenePos()
            mouse_point = self.plotItem.vb.mapSceneToView(pos)
            # TODO: Selection logic
            pass


# ==================== Graph Panel ====================

class GraphPanel(QWidget):
    """
    Graph Panel - Main container
    
    Layout:
    ┌──────────┬───────────────────────────┬──────────┬──────────┐
    │ Options  │       Main Graph          │  Legend  │  Stats   │
    │ (240px)  │                           │ (200px)  │ (180px)  │
    └──────────┴───────────────────────────┴──────────┴──────────┘
    """
    
    def __init__(self, state: AppState, engine: DataEngine):
        super().__init__()
        self.state = state
        self.engine = engine
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # Options Panel (left)
        self.options_panel = GraphOptionsPanel(self.state)
        splitter.addWidget(self.options_panel)
        
        # Main Graph (center)
        self.main_graph = MainGraph(self.state)
        splitter.addWidget(self.main_graph)
        
        # Legend Panel (right)
        self.legend_panel = LegendSettingsPanel(self.state)
        splitter.addWidget(self.legend_panel)
        
        # Stat Panel (far right)
        self.stat_panel = StatPanel(self.state)
        splitter.addWidget(self.stat_panel)
        
        # Splitter sizes
        splitter.setSizes([240, 500, 200, 180])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setStretchFactor(3, 0)
        
        layout.addWidget(splitter)
    
    def _connect_signals(self):
        self.state.chart_settings_changed.connect(self.refresh)
        self.state.group_zone_changed.connect(self._on_group_changed)
        self.state.value_zone_changed.connect(self.refresh)
        self.state.selection_changed.connect(self._on_selection_changed)
        self.options_panel.option_changed.connect(self.refresh)
        self.legend_panel.settings_changed.connect(self.refresh)
    
    def _on_group_changed(self):
        """그룹 변경 시 범례 업데이트"""
        if self.state.group_columns:
            groups = self._build_group_masks()
            if groups:
                self.legend_panel.set_series(list(groups.keys()))
        else:
            # Single series
            if self.state.value_columns:
                self.legend_panel.set_series([self.state.value_columns[0].name])
            else:
                self.legend_panel.set_series(["Data"])
        self.refresh()
    
    def refresh(self):
        """Refresh graph"""
        if not self.engine.is_loaded:
            return
        
        # Get options
        options = self.options_panel.get_chart_options()
        legend_settings = self.legend_panel.get_legend_settings()
        
        # X column (from state, set by X Zone)
        x_col = self.state.x_column
        if not x_col:
            x_data = np.arange(self.engine.row_count)
            options['x_title'] = options.get('x_title') or 'Index'
        else:
            x_data = self.engine.df[x_col].to_numpy()
            options['x_title'] = options.get('x_title') or x_col
        
        # Y column
        if self.state.value_columns:
            value_col = self.state.value_columns[0]
            y_col_name = value_col.name
        else:
            numeric_cols = [
                col for col in self.engine.columns
                if self.engine.dtypes.get(col, '').startswith(('Int', 'Float'))
            ]
            if numeric_cols:
                y_col_name = numeric_cols[0]
            else:
                return
        
        y_data = self.engine.df[y_col_name].to_numpy()
        options['y_title'] = options.get('y_title') or y_col_name
        
        # Groups
        groups = None
        if self.state.group_columns:
            groups = self._build_group_masks()
        
        # Sampling for large datasets
        MAX_POINTS = 10000
        if len(x_data) > MAX_POINTS:
            valid_mask = ~(np.isnan(x_data.astype(float)) | np.isnan(y_data.astype(float)))
            x_valid = x_data[valid_mask].astype(np.float64)
            y_valid = y_data[valid_mask].astype(np.float64)
            
            if len(x_valid) > MAX_POINTS:
                x_sampled, y_sampled = DataSampler.auto_sample(
                    x_valid, y_valid, max_points=MAX_POINTS
                )
                groups = None
            else:
                x_sampled, y_sampled = x_valid, y_valid
        else:
            x_sampled, y_sampled = x_data, y_data
        
        self.main_graph.plot_data(
            x_sampled, y_sampled,
            groups=groups,
            chart_type=options.get('chart_type', ChartType.LINE),
            options=options,
            legend_settings=legend_settings
        )
        
        # Update stats
        self.stat_panel.update_histograms(x_sampled, y_sampled)
        if self.state.value_columns:
            stats = self.engine.get_statistics(self.state.value_columns[0].name)
            self.stat_panel.update_stats(stats)
    
    def _on_selection_changed(self):
        pass
    
    def _build_group_masks(self) -> Dict[str, np.ndarray]:
        if not self.state.group_columns or not self.engine.is_loaded:
            return None
        
        df = self.engine.df
        n_rows = len(df)
        group_cols = [g.name for g in self.state.group_columns]
        groups = {}
        
        if len(group_cols) == 1:
            col = group_cols[0]
            unique_values = df[col].unique().sort().to_list()
            
            for val in unique_values:
                group_name = str(val) if val is not None else "(Empty)"
                mask = (df[col] == val).to_numpy()
                groups[group_name] = mask
        else:
            combined = df.select(group_cols)
            unique_combos = combined.unique().sort(group_cols)
            
            for row in unique_combos.iter_rows():
                parts = [str(v) if v is not None else "(Empty)" for v in row]
                group_name = " / ".join(parts)
                
                mask = np.ones(n_rows, dtype=bool)
                for col, val in zip(group_cols, row):
                    if val is None:
                        mask &= df[col].is_null().to_numpy()
                    else:
                        mask &= (df[col] == val).to_numpy()
                
                groups[group_name] = mask
        
        return groups
    
    def reset_view(self):
        self.main_graph.reset_view()
    
    def autofit(self):
        self.main_graph.autoRange()
    
    def export_image(self, path: str):
        exporter = pg.exporters.ImageExporter(self.main_graph.plotItem)
        exporter.export(path)
    
    def clear(self):
        self.main_graph.clear_plot()
        self.stat_panel.update_histograms(None, None)
        self.stat_panel.update_stats({})
    
    def set_columns(self, columns: List[str]):
        """컬럼 목록 설정 (범례 초기화용)"""
        # Initialize legend with first numeric column
        numeric_cols = [
            col for col in columns
            if self.engine.dtypes.get(col, '').startswith(('Int', 'Float'))
        ]
        if numeric_cols:
            self.legend_panel.set_series([numeric_cols[0]])
