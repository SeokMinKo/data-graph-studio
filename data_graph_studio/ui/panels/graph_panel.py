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
    QTabWidget, QListWidget, QListWidgetItem, QGridLayout,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot, QSize
from PySide6.QtGui import QMouseEvent, QColor, QIcon, QPixmap, QPainter

from ..floatable import FloatableSection, FloatButton, FloatWindow

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

    def plot_histogram(self, data: np.ndarray, title: str, color: tuple, bins: int = 50, horizontal: bool = False):
        """Plot histogram - vertical (default) or horizontal"""
        self.setWindowTitle(title)
        self.plot_widget.clear()

        if data is not None and len(data) > 0:
            try:
                clean_data = data[~np.isnan(data)]
                hist, bin_edges = np.histogram(clean_data, bins=bins)

                if horizontal:
                    # Horizontal histogram: Y-axis is value bins, X-axis is frequency
                    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
                    bar_height = (bin_edges[1] - bin_edges[0]) * 0.8 if len(bin_edges) > 1 else 0.8

                    # Use BarGraphItem for horizontal bars
                    bar_item = pg.BarGraphItem(
                        x0=np.zeros(len(hist)),
                        y=bin_centers,
                        width=hist,
                        height=bar_height,
                        brush=color,
                        pen=pg.mkPen(color[:3], width=1)
                    )
                    self.plot_widget.addItem(bar_item)

                    self.plot_widget.setLabel('bottom', 'Frequency')
                    self.plot_widget.setLabel('left', 'Value')

                    # Mean line (horizontal)
                    mean_val = np.mean(clean_data)
                    self.plot_widget.addLine(y=mean_val, pen=pg.mkPen('r', width=2, style=Qt.DashLine))

                    # Stats text
                    stats_text = f"Mean: {mean_val:.2f}\nMedian: {np.median(clean_data):.2f}\nStd: {np.std(clean_data):.2f}"
                    text_item = pg.TextItem(stats_text, anchor=(0, 1), color='k')
                    text_item.setPos(max(hist) * 0.1, bin_edges[-1])
                    self.plot_widget.addItem(text_item)
                else:
                    # Vertical histogram (default)
                    self.plot_widget.plot(bin_edges, hist, stepMode=True, fillLevel=0,
                                          brush=color, pen=pg.mkPen(color[:3], width=1))
                    self.plot_widget.setLabel('bottom', 'Value')
                    self.plot_widget.setLabel('left', 'Frequency')

                    mean_val = np.mean(clean_data)
                    self.plot_widget.addLine(x=mean_val, pen=pg.mkPen('r', width=2, style=Qt.DashLine))

                    stats_text = f"Mean: {mean_val:.2f}\nMedian: {np.median(clean_data):.2f}\nStd: {np.std(clean_data):.2f}"
                    text_item = pg.TextItem(stats_text, anchor=(0, 0), color='k')
                    text_item.setPos(bin_edges[0], max(hist) * 0.9)
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
        self._bins = 30  # Default bin count
        self._horizontal = False  # Histogram orientation

    def set_data(self, data: np.ndarray, title: str, color: tuple, bins: int = 30, horizontal: bool = False):
        self._data = data
        self._title = title
        self._color = color
        self._bins = bins
        self._horizontal = horizontal

    def set_bins(self, bins: int):
        """Set the number of bins for histogram"""
        self._bins = bins

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            self._show_expanded()
        super().mouseDoubleClickEvent(event)

    def _show_expanded(self):
        if self._data is None:
            return
        dialog = ExpandedChartDialog(self._title, self)
        dialog.plot_histogram(self._data, self._title, self._color, bins=self._bins, horizontal=self._horizontal)
        dialog.exec()


from ...core.state import AppState, ChartType, ToolMode
from ...core.data_engine import DataEngine
from ...graph.sampling import DataSampler


class FormattedAxisItem(pg.AxisItem):
    """Custom axis item with value formatting"""

    def __init__(self, orientation, format_type=None, **kwargs):
        super().__init__(orientation, **kwargs)
        self.format_type = format_type

    def set_format(self, format_type):
        self.format_type = format_type

    def tickStrings(self, values, scale, spacing):
        if self.format_type is None or self.format_type == 'auto':
            return super().tickStrings(values, scale, spacing)

        strings = []
        for v in values:
            strings.append(self._format_value(v))
        return strings

    def _format_value(self, value) -> str:
        if value is None or (isinstance(value, float) and (value != value)):  # NaN check
            return ""

        try:
            if self.format_type == 'number':
                return f"{value:,.0f}"
            elif self.format_type == 'decimal':
                return f"{value:,.2f}"
            elif self.format_type == 'scientific':
                return f"{value:.2e}"
            elif self.format_type == 'percent':
                return f"{value:.1f}%"
            elif self.format_type == 'k':
                if abs(value) >= 1000:
                    return f"{value/1000:.1f}K"
                return f"{value:.0f}"
            elif self.format_type == 'm':
                if abs(value) >= 1_000_000:
                    return f"{value/1_000_000:.1f}M"
                elif abs(value) >= 1000:
                    return f"{value/1000:.1f}K"
                return f"{value:.0f}"
            elif self.format_type == 'b':
                if abs(value) >= 1_000_000_000:
                    return f"{value/1_000_000_000:.1f}B"
                elif abs(value) >= 1_000_000:
                    return f"{value/1_000_000:.1f}M"
                elif abs(value) >= 1000:
                    return f"{value/1000:.1f}K"
                return f"{value:.0f}"
            elif self.format_type == 'bytes':
                if abs(value) >= 1_073_741_824:  # GB
                    return f"{value/1_073_741_824:.1f}GB"
                elif abs(value) >= 1_048_576:  # MB
                    return f"{value/1_048_576:.1f}MB"
                elif abs(value) >= 1024:  # KB
                    return f"{value/1024:.1f}KB"
                return f"{value:.0f}B"
            elif self.format_type == 'time':
                if abs(value) >= 60000:  # minutes
                    return f"{value/60000:.1f}min"
                elif abs(value) >= 1000:  # seconds
                    return f"{value/1000:.1f}s"
                return f"{value:.0f}ms"
            else:
                return f"{value:.2f}"
        except (ValueError, TypeError):
            return str(value)


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

        # Header (no float button for internal sections)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QLabel("⚙️ Chart Options")
        header.setStyleSheet("font-weight: 600; font-size: 13px; color: #111827; padding: 4px;")
        header_layout.addWidget(header)

        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

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

        x_layout.addWidget(QLabel("Title:"), 0, 0)
        self.x_title_edit = QLineEdit()
        self.x_title_edit.setPlaceholderText("Auto")
        self.x_title_edit.textChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_title_edit, 0, 1)

        x_layout.addWidget(QLabel("Format:"), 1, 0)
        self.x_format_combo = QComboBox()
        self.x_format_combo.addItems([
            "Auto",
            "Number (1,234)",
            "Decimal (1234.56)",
            "Scientific (1.23e+4)",
            "Percent (%)",
            "K (thousands)",
            "M (millions)",
            "B (billions)",
            "KB/MB/GB",
            "ms/s/min"
        ])
        self.x_format_combo.currentIndexChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_format_combo, 1, 1)

        self.x_log_check = QCheckBox("Log Scale")
        self.x_log_check.stateChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_log_check, 2, 0, 1, 2)

        self.x_reverse_check = QCheckBox("Reverse")
        self.x_reverse_check.stateChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_reverse_check, 3, 0, 1, 2)

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

        y_layout.addWidget(QLabel("Format:"), 1, 0)
        self.y_format_combo = QComboBox()
        self.y_format_combo.addItems([
            "Auto",
            "Number (1,234)",
            "Decimal (1234.56)",
            "Scientific (1.23e+4)",
            "Percent (%)",
            "K (thousands)",
            "M (millions)",
            "B (billions)",
            "KB/MB/GB",
            "ms/s/min"
        ])
        self.y_format_combo.currentIndexChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_format_combo, 1, 1)

        y_layout.addWidget(QLabel("Min:"), 2, 0)
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setRange(-1e9, 1e9)
        self.y_min_spin.setSpecialValueText("Auto")
        self.y_min_spin.setValue(self.y_min_spin.minimum())
        self.y_min_spin.valueChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_min_spin, 2, 1)

        y_layout.addWidget(QLabel("Max:"), 3, 0)
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setRange(-1e9, 1e9)
        self.y_max_spin.setSpecialValueText("Auto")
        self.y_max_spin.setValue(self.y_max_spin.minimum())
        self.y_max_spin.valueChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_max_spin, 3, 1)

        self.y_log_check = QCheckBox("Log Scale")
        self.y_log_check.stateChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_log_check, 4, 0, 1, 2)

        self.y_reverse_check = QCheckBox("Reverse")
        self.y_reverse_check.stateChanged.connect(self._on_option_changed)
        y_layout.addWidget(self.y_reverse_check, 5, 0, 1, 2)

        layout.addWidget(y_group)

        # Sliding Window Group
        slider_group = QGroupBox("Sliding Window")
        slider_layout = QVBoxLayout(slider_group)

        self.sliding_window_check = QCheckBox("Enable Sliding Window")
        self.sliding_window_check.setChecked(False)
        self.sliding_window_check.stateChanged.connect(self._on_sliding_window_changed)
        self.sliding_window_check.setToolTip("Enable navigation minimap for large datasets")
        slider_layout.addWidget(self.sliding_window_check)

        # X-axis sliding window checkbox
        self.x_sliding_window_check = QCheckBox("X-Axis Navigator")
        self.x_sliding_window_check.setChecked(True)
        self.x_sliding_window_check.setEnabled(False)
        self.x_sliding_window_check.stateChanged.connect(self._on_option_changed)
        slider_layout.addWidget(self.x_sliding_window_check)

        # Y-axis sliding window checkbox
        self.y_sliding_window_check = QCheckBox("Y-Axis Navigator")
        self.y_sliding_window_check.setChecked(True)
        self.y_sliding_window_check.setEnabled(False)
        self.y_sliding_window_check.stateChanged.connect(self._on_option_changed)
        slider_layout.addWidget(self.y_sliding_window_check)

        # Hint label
        hint_label = QLabel("Double-click to reset view")
        hint_label.setStyleSheet("font-size: 10px; color: #9CA3AF; font-style: italic;")
        slider_layout.addWidget(hint_label)

        layout.addWidget(slider_group)

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

        # Sampling Options
        sampling_group = QGroupBox("Sampling")
        sampling_layout = QVBoxLayout(sampling_group)
        sampling_layout.setSpacing(8)

        # Show All Data checkbox
        self.show_all_data_check = QCheckBox("Show All Data (may be slow)")
        self.show_all_data_check.setChecked(False)
        self.show_all_data_check.stateChanged.connect(self._on_show_all_data_changed)
        sampling_layout.addWidget(self.show_all_data_check)

        # Max Points slider
        max_points_layout = QVBoxLayout()
        max_points_label_layout = QHBoxLayout()
        max_points_label_layout.addWidget(QLabel("Max Points:"))
        self.max_points_label = QLabel("10,000")
        self.max_points_label.setStyleSheet("font-weight: 600; color: #4F46E5;")
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
        """Handle sliding window enable/disable"""
        enabled = state == Qt.Checked
        self.x_sliding_window_check.setEnabled(enabled)
        self.y_sliding_window_check.setEnabled(enabled)
        self.option_changed.emit()

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

        # Format types mapping
        format_types = [
            None,  # Auto
            'number',  # Number (1,234)
            'decimal',  # Decimal (1234.56)
            'scientific',  # Scientific (1.23e+4)
            'percent',  # Percent (%)
            'k',  # K (thousands)
            'm',  # M (millions)
            'b',  # B (billions)
            'bytes',  # KB/MB/GB
            'time'  # ms/s/min
        ]

        # Sampling algorithm mapping
        sampling_algorithms = ['auto', 'lttb', 'minmax', 'random']

        return {
            'x_title': self.x_title_edit.text() or None,
            'x_format': format_types[self.x_format_combo.currentIndex()],
            'x_log': self.x_log_check.isChecked(),
            'x_reverse': self.x_reverse_check.isChecked(),
            'y_title': self.y_title_edit.text() or None,
            'y_format': format_types[self.y_format_combo.currentIndex()],
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
            # Sampling options
            'show_all_data': self.show_all_data_check.isChecked(),
            'max_points': self.max_points_slider.value() * 1000,
            'sampling_algorithm': sampling_algorithms[self.sampling_algo_combo.currentIndex()],
            # Sliding window options
            'sliding_window_enabled': self.sliding_window_check.isChecked(),
            'x_sliding_window': self.x_sliding_window_check.isChecked(),
            'y_sliding_window': self.y_sliding_window_check.isChecked(),
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

        # Header with float button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QLabel("📊 Legend")
        header.setStyleSheet("font-weight: 600; font-size: 13px; color: #111827; padding: 4px;")
        header_layout.addWidget(header)

        header_layout.addStretch()

        self.float_btn = FloatButton()
        header_layout.addWidget(self.float_btn)

        layout.addLayout(header_layout)

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
        self._x_bins: int = 30
        self._y_bins: int = 30

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

        # Header (no float button for internal sections)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QLabel("📈 Statistics")
        header.setStyleSheet("font-weight: 600; font-size: 13px; color: #111827; padding: 4px;")
        header_layout.addWidget(header)

        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Bin Range Control
        bin_group = QGroupBox("Bin Range")
        bin_layout = QGridLayout(bin_group)
        bin_layout.setSpacing(4)

        bin_layout.addWidget(QLabel("X bins:"), 0, 0)
        self.x_bins_spin = QSpinBox()
        self.x_bins_spin.setRange(5, 100)
        self.x_bins_spin.setValue(30)
        self.x_bins_spin.valueChanged.connect(self._on_x_bins_changed)
        bin_layout.addWidget(self.x_bins_spin, 0, 1)

        bin_layout.addWidget(QLabel("Y bins:"), 1, 0)
        self.y_bins_spin = QSpinBox()
        self.y_bins_spin.setRange(5, 100)
        self.y_bins_spin.setValue(30)
        self.y_bins_spin.valueChanged.connect(self._on_y_bins_changed)
        bin_layout.addWidget(self.y_bins_spin, 1, 1)

        layout.addWidget(bin_group)

        # X Distribution (vertical histogram - standard)
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

        # Y Distribution (horizontal histogram)
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

    def _on_x_bins_changed(self, value: int):
        self._x_bins = value
        self.x_hist_widget.set_bins(value)
        self._update_x_histogram()

    def _on_y_bins_changed(self, value: int):
        self._y_bins = value
        self.y_hist_widget.set_bins(value)
        self._update_y_histogram()

    def _update_x_histogram(self):
        self.x_hist_widget.clear()
        if self._x_data is not None and len(self._x_data) > 0:
            try:
                clean_x = self._x_data[~np.isnan(self._x_data)]
                if len(clean_x) > 0:
                    hist, bins = np.histogram(clean_x, bins=self._x_bins)
                    self.x_hist_widget.plot(bins, hist, stepMode=True, fillLevel=0,
                                            brush=(100, 100, 200, 100))
            except:
                pass

    def _update_y_histogram(self):
        self.y_hist_widget.clear()
        if self._y_data is not None and len(self._y_data) > 0:
            try:
                clean_y = self._y_data[~np.isnan(self._y_data)]
                if len(clean_y) > 0:
                    hist, bins = np.histogram(clean_y, bins=self._y_bins)
                    # Horizontal histogram: swap x and y, plot rotated
                    # bins represent Y values, hist represents frequency (horizontal extent)
                    bin_centers = (bins[:-1] + bins[1:]) / 2
                    self.y_hist_widget.plot(hist, bin_centers, stepMode=False, fillLevel=0,
                                            pen=pg.mkPen((100, 200, 100, 255), width=1),
                                            brush=(100, 200, 100, 100),
                                            symbol=None)
                    # Fill as horizontal bars using BarGraphItem
                    self.y_hist_widget.clear()
                    bar_height = (bins[1] - bins[0]) * 0.8 if len(bins) > 1 else 0.8
                    bar_item = pg.BarGraphItem(
                        x0=np.zeros(len(hist)),
                        y=bin_centers,
                        width=hist,
                        height=bar_height,
                        brush=(100, 200, 100, 100),
                        pen=pg.mkPen((100, 200, 100, 255), width=1)
                    )
                    self.y_hist_widget.addItem(bar_item)
            except:
                pass
    
    def update_histograms(self, x_data: Optional[np.ndarray], y_data: Optional[np.ndarray]):
        self._x_data = x_data
        self._y_data = y_data

        # Store data for double-click expansion
        # X Distribution: vertical histogram (default)
        if x_data is not None:
            self.x_hist_widget.set_data(
                x_data, "X-Axis Distribution", (100, 100, 200, 150),
                bins=self._x_bins, horizontal=False
            )
        # Y Distribution: horizontal histogram
        if y_data is not None:
            self.y_hist_widget.set_data(
                y_data, "Y-Axis Distribution", (100, 200, 100, 150),
                bins=self._y_bins, horizontal=True
            )

        # Update histograms using current bin settings
        self._update_x_histogram()
        self._update_y_histogram()
    
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
    """메인 그래프 위젯 with hover tooltip support"""

    points_selected = Signal(list)

    def __init__(self, state: AppState):
        # Create custom axes
        self._x_axis = FormattedAxisItem('bottom')
        self._y_axis = FormattedAxisItem('left')

        super().__init__(axisItems={'bottom': self._x_axis, 'left': self._y_axis})
        self.state = state

        self.setBackground('w')
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setLabel('left', '')
        self.setLabel('bottom', '')

        self.legend = self.addLegend()
        self._legend_visible = True
        self._legend_position = (1, 1)  # Default: top right

        self._plot_items = []
        self._scatter_items = []
        self._data_x = None
        self._data_y = None

        # Hover data columns
        self._hover_columns: List[str] = []
        self._hover_data: Optional[Dict[str, list]] = None
        self._tooltip_item = None

        # Selection ROI
        self._selection_roi = None
        self._selection_start = None
        self._is_selecting = False

        # Sampling status label
        self._sampling_label = pg.TextItem(
            text="",
            anchor=(0, 0),
            color='#6B7280'
        )
        self._sampling_label.setZValue(1000)
        self._sampling_label.setFont(pg.QtGui.QFont('Arial', 9))
        self.addItem(self._sampling_label)
        self._sampling_label.hide()

        # OpenGL state
        self._opengl_enabled = False

        # Enable mouse tracking for hover
        self.setMouseTracking(True)
        self.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        self.scene().sigMouseMoved.connect(self._on_mouse_moved)

        # Connect to tool mode changes
        self.state.tool_mode_changed.connect(self._on_tool_mode_changed)

        # Apply initial tool mode
        self._on_tool_mode_changed()

    def enable_opengl(self, enable: bool = True):
        """Enable or disable OpenGL acceleration"""
        if enable and not self._opengl_enabled:
            try:
                self.useOpenGL(True)
                self._opengl_enabled = True
            except Exception as e:
                print(f"Failed to enable OpenGL: {e}")
        elif not enable and self._opengl_enabled:
            try:
                self.useOpenGL(False)
                self._opengl_enabled = False
            except Exception:
                pass

    def update_sampling_status(
        self,
        displayed_points: int,
        total_points: int,
        is_sampled: bool,
        algorithm: str = ""
    ):
        """Update sampling status label"""
        if is_sampled and total_points > displayed_points:
            algo_text = f" [{algorithm}]" if algorithm else ""
            text = f"Showing {displayed_points:,} of {total_points:,} points{algo_text}"
            self._sampling_label.setText(text)

            # Position at top-left of the plot
            view_range = self.viewRange()
            x_pos = view_range[0][0]
            y_pos = view_range[1][1]
            self._sampling_label.setPos(x_pos, y_pos)
            self._sampling_label.show()
        else:
            self._sampling_label.hide()

    def _update_sampling_label_position(self):
        """Update sampling label position when view changes"""
        if self._sampling_label.isVisible():
            view_range = self.viewRange()
            x_pos = view_range[0][0]
            y_pos = view_range[1][1]
            self._sampling_label.setPos(x_pos, y_pos)

    def _on_tool_mode_changed(self):
        """Handle tool mode changes"""
        mode = self.state.tool_mode
        vb = self.plotItem.vb

        # Clear any existing selection ROI
        if self._selection_roi is not None:
            self.removeItem(self._selection_roi)
            self._selection_roi = None
        self._is_selecting = False

        if mode == ToolMode.ZOOM:
            # Zoom mode: left-click-drag to zoom into rect
            vb.setMouseMode(pg.ViewBox.RectMode)
            vb.setMouseEnabled(x=True, y=True)
            self.setCursor(Qt.CrossCursor)
        elif mode == ToolMode.PAN:
            # Pan mode: left-click-drag to pan
            vb.setMouseMode(pg.ViewBox.PanMode)
            vb.setMouseEnabled(x=True, y=True)
            self.setCursor(Qt.OpenHandCursor)
        elif mode in [ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT]:
            # Selection mode: disable default interactions
            vb.setMouseMode(pg.ViewBox.PanMode)  # Disable rect zoom
            vb.setMouseEnabled(x=False, y=False)  # Disable panning
            self.setCursor(Qt.CrossCursor)
        else:
            # Default mode
            vb.setMouseMode(pg.ViewBox.PanMode)
            vb.setMouseEnabled(x=True, y=True)
            self.setCursor(Qt.ArrowCursor)
    
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

        # Apply axis formats
        x_format = options.get('x_format')
        y_format = options.get('y_format')
        self._x_axis.set_format(x_format)
        self._y_axis.set_format(y_format)

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
        
        # Legend visibility and position
        if legend_settings.get('show', True):
            self.legend.show()
            # Apply legend position
            position = legend_settings.get('position', (1, 1))  # Default top right
            # Position format: (vertical, horizontal) where:
            # vertical: 0=bottom, 1=top, 0.5=middle
            # horizontal: 0=left, 1=right, 0.5=center
            v, h = position

            # Map position to anchor points
            # For legend.anchor(itemPos, parentPos):
            # itemPos: point on the legend item (0,0 = top-left, 1,1 = bottom-right)
            # parentPos: point on the parent viewbox (0,0 = top-left, 1,1 = bottom-right)
            if v == 1 and h == 1:  # Top Right
                self.legend.anchor((1, 0), (1, 0), offset=(-10, 10))
            elif v == 1 and h == 0:  # Top Left
                self.legend.anchor((0, 0), (0, 0), offset=(10, 10))
            elif v == 0 and h == 1:  # Bottom Right
                self.legend.anchor((1, 1), (1, 1), offset=(-10, -10))
            elif v == 0 and h == 0:  # Bottom Left
                self.legend.anchor((0, 1), (0, 1), offset=(10, -10))
            elif v == 1 and h == 0.5:  # Top Center
                self.legend.anchor((0.5, 0), (0.5, 0), offset=(0, 10))
            elif v == 0 and h == 0.5:  # Bottom Center
                self.legend.anchor((0.5, 1), (0.5, 1), offset=(0, -10))
            elif v == 0.5 and h == 1:  # Right
                self.legend.anchor((1, 0.5), (1, 0.5), offset=(-10, 0))
            elif v == 0.5 and h == 0:  # Left
                self.legend.anchor((0, 0.5), (0, 0.5), offset=(10, 0))
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
        """Handle mouse click for selection"""
        if self.state.tool_mode in [ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT]:
            pos = event.scenePos()
            mouse_point = self.plotItem.vb.mapSceneToView(pos)

            if event.button() == Qt.LeftButton:
                if not self._is_selecting:
                    # Start selection
                    self._selection_start = mouse_point
                    self._is_selecting = True

                    # Create selection rectangle
                    if self._selection_roi is not None:
                        self.removeItem(self._selection_roi)

                    self._selection_roi = pg.RectROI(
                        [mouse_point.x(), mouse_point.y()],
                        [0, 0],
                        pen=pg.mkPen('b', width=2, style=Qt.DashLine),
                        movable=False,
                        resizable=False
                    )
                    self._selection_roi.setPen(pg.mkPen((99, 102, 241), width=2, style=Qt.DashLine))
                    self.addItem(self._selection_roi)
                else:
                    # Finish selection
                    self._finish_selection(mouse_point)

    def _finish_selection(self, end_point):
        """Finish rectangle selection and select points within"""
        if self._data_x is None or self._data_y is None:
            self._is_selecting = False
            return

        if not hasattr(self, '_rect_start_x'):
            self._is_selecting = False
            return

        # Get selection bounds using stored start position
        start_x = self._rect_start_x
        start_y = self._rect_start_y
        end_x = end_point.x()
        end_y = end_point.y()

        x1 = min(start_x, end_x)
        x2 = max(start_x, end_x)
        y1 = min(start_y, end_y)
        y2 = max(start_y, end_y)

        # Find points within selection
        selected_indices = []
        for i in range(len(self._data_x)):
            x, y = self._data_x[i], self._data_y[i]
            if x1 <= x <= x2 and y1 <= y <= y2:
                selected_indices.append(i)

        # Emit selection signal
        if selected_indices:
            self.points_selected.emit(selected_indices)
            self.state.select_rows(selected_indices)

        # Clean up selection ROI
        if self._selection_roi is not None:
            self.removeItem(self._selection_roi)
            self._selection_roi = None

        self._is_selecting = False
        self._selection_start = None
        if hasattr(self, '_rect_start_x'):
            del self._rect_start_x
        if hasattr(self, '_rect_start_y'):
            del self._rect_start_y

    def mousePressEvent(self, event):
        """Handle mouse press for selection drag"""
        if self.state.tool_mode in [ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT]:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._selection_start = pos
                self._is_selecting = True

                # Create selection rectangle
                if self._selection_roi is not None:
                    self.removeItem(self._selection_roi)

                self._selection_roi = pg.LinearRegionItem(
                    values=[pos.x(), pos.x()],
                    orientation='vertical',
                    movable=False,
                    brush=pg.mkBrush(99, 102, 241, 30)  # #6366F1 with alpha
                )
                # Actually use RectROI for 2D selection
                self.removeItem(self._selection_roi)
                self._selection_roi = None

                # Store start position
                self._rect_start_x = pos.x()
                self._rect_start_y = pos.y()

                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for selection drag"""
        if self._is_selecting and self.state.tool_mode in [ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT]:
            pos = self.plotItem.vb.mapSceneToView(event.position())

            # Update selection rectangle visualization
            if hasattr(self, '_rect_start_x'):
                x1 = min(self._rect_start_x, pos.x())
                y1 = min(self._rect_start_y, pos.y())
                width = abs(pos.x() - self._rect_start_x)
                height = abs(pos.y() - self._rect_start_y)

                if self._selection_roi is not None:
                    self.removeItem(self._selection_roi)

                # Draw selection rectangle as a simple rect item
                rect = pg.QtWidgets.QGraphicsRectItem(x1, y1, width, height)
                rect.setPen(pg.mkPen((99, 102, 241), width=2, style=Qt.DashLine))
                rect.setBrush(pg.mkBrush(99, 102, 241, 30))  # #6366F1 with alpha
                self.addItem(rect)
                self._selection_roi = rect

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release for selection"""
        if self._is_selecting and self.state.tool_mode in [ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT]:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())

                if hasattr(self, '_rect_start_x'):
                    # Create QPointF for end point
                    from PySide6.QtCore import QPointF
                    start_point = QPointF(self._rect_start_x, self._rect_start_y)
                    self._finish_selection(pos)

                event.accept()
                return

        super().mouseReleaseEvent(event)

    def _on_mouse_moved(self, pos):
        """Handle mouse move for hover tooltip"""
        if self._data_x is None or self._data_y is None:
            self._hide_tooltip()
            return

        if not self._hover_columns or not self._hover_data:
            self._hide_tooltip()
            return

        # Convert scene position to view coordinates
        mouse_point = self.plotItem.vb.mapSceneToView(pos)
        mx, my = mouse_point.x(), mouse_point.y()

        # Find nearest point
        if len(self._data_x) == 0:
            self._hide_tooltip()
            return

        # Calculate distance to each point (normalized)
        view_range = self.viewRange()
        x_range = view_range[0][1] - view_range[0][0]
        y_range = view_range[1][1] - view_range[1][0]

        if x_range == 0 or y_range == 0:
            self._hide_tooltip()
            return

        # Normalized distance
        dx = (self._data_x - mx) / x_range
        dy = (self._data_y - my) / y_range
        distances = np.sqrt(dx**2 + dy**2)

        nearest_idx = np.argmin(distances)
        min_dist = distances[nearest_idx]

        # Only show tooltip if close enough (within 5% of view range)
        if min_dist < 0.05:
            self._show_tooltip(nearest_idx, self._data_x[nearest_idx], self._data_y[nearest_idx])
        else:
            self._hide_tooltip()

    def _show_tooltip(self, idx: int, x_val: float, y_val: float):
        """Show tooltip at data point"""
        if self._tooltip_item is None:
            self._tooltip_item = pg.TextItem(anchor=(0, 1), fill='w', border='k')
            self._tooltip_item.setZValue(1000)
            self.addItem(self._tooltip_item)

        # Build tooltip text
        lines = [f"X: {self._format_value(x_val)}", f"Y: {self._format_value(y_val)}"]

        for col in self._hover_columns:
            if col in self._hover_data and idx < len(self._hover_data[col]):
                val = self._hover_data[col][idx]
                lines.append(f"{col}: {self._format_value(val)}")

        self._tooltip_item.setText("\n".join(lines))
        self._tooltip_item.setPos(x_val, y_val)
        self._tooltip_item.show()

    def _hide_tooltip(self):
        """Hide tooltip"""
        if self._tooltip_item is not None:
            self._tooltip_item.hide()

    def _format_value(self, val) -> str:
        """Format value for display"""
        if val is None:
            return "N/A"
        if isinstance(val, float):
            if abs(val) >= 1000000:
                return f"{val:.2e}"
            elif abs(val) >= 100:
                return f"{val:.1f}"
            else:
                return f"{val:.3f}"
        return str(val)

    def set_hover_data(self, hover_columns: List[str], hover_data: Dict[str, list]):
        """Set hover data columns and values"""
        self._hover_columns = hover_columns or []
        self._hover_data = hover_data or {}


# ==================== Sliding Window Widget ====================

class SlidingWindowWidget(QWidget):
    """
    Sliding Window 위젯 - 데이터 범위 탐색용 미니맵

    X축 또는 Y축의 전체 데이터 범위를 보여주고,
    드래그 가능한 윈도우로 현재 보이는 범위를 조절
    """

    range_changed = Signal(float, float)  # min, max

    def __init__(self, orientation: str = 'horizontal', parent=None):
        super().__init__(parent)
        self.orientation = orientation  # 'horizontal' for X-axis, 'vertical' for Y-axis

        self._data_min = 0.0
        self._data_max = 1.0
        self._window_min = 0.0
        self._window_max = 1.0
        self._data = None

        self._dragging = False
        self._drag_mode = None  # 'move', 'left', 'right', 'top', 'bottom'
        self._drag_start = None
        self._drag_start_min = None
        self._drag_start_max = None

        self._setup_ui()
        self.setMouseTracking(True)

    def _setup_ui(self):
        if self.orientation == 'horizontal':
            self.setMinimumHeight(50)
            self.setMaximumHeight(60)
        else:
            self.setMinimumWidth(50)
            self.setMaximumWidth(60)

        self.setStyleSheet("""
            SlidingWindowWidget {
                background: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
            }
        """)

    def set_data(self, data: np.ndarray):
        """Set the data for the overview display"""
        if data is None or len(data) == 0:
            self._data = None
            return

        self._data = data

        # Handle non-numeric data
        try:
            clean_data = data[~np.isnan(data.astype(float))]
            if len(clean_data) > 0:
                self._data_min = float(np.min(clean_data))
                self._data_max = float(np.max(clean_data))
            else:
                self._data_min = 0.0
                self._data_max = 1.0
        except (TypeError, ValueError):
            # Non-numeric data - use indices
            self._data_min = 0.0
            self._data_max = float(len(data) - 1) if len(data) > 1 else 1.0

        # Ensure range is valid
        if self._data_min >= self._data_max:
            self._data_max = self._data_min + 1.0

        # Initialize window to full range
        self._window_min = self._data_min
        self._window_max = self._data_max

        self.update()

    def set_window(self, min_val: float, max_val: float):
        """Set the current visible window range"""
        self._window_min = max(self._data_min, min(min_val, self._data_max))
        self._window_max = min(self._data_max, max(max_val, self._data_min))

        # Ensure valid range
        if self._window_min >= self._window_max:
            self._window_max = self._window_min + (self._data_max - self._data_min) * 0.1

        self.update()

    def reset_window(self):
        """Reset window to full data range"""
        self._window_min = self._data_min
        self._window_max = self._data_max
        self.range_changed.emit(self._window_min, self._window_max)
        self.update()

    def _value_to_pos(self, value: float) -> float:
        """Convert data value to widget position (0-1 normalized)"""
        data_range = self._data_max - self._data_min
        if data_range == 0:
            return 0.5
        return (value - self._data_min) / data_range

    def _pos_to_value(self, pos: float) -> float:
        """Convert widget position (0-1 normalized) to data value"""
        return self._data_min + pos * (self._data_max - self._data_min)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QPen, QBrush, QLinearGradient

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        margin = 4

        if self.orientation == 'horizontal':
            plot_rect = rect.adjusted(margin, margin + 15, -margin, -margin)
        else:
            plot_rect = rect.adjusted(margin + 15, margin, -margin, -margin)

        # Background
        painter.fillRect(plot_rect, QColor('#FFFFFF'))
        painter.setPen(QPen(QColor('#E5E7EB'), 1))
        painter.drawRect(plot_rect)

        # Draw data overview (simplified histogram/line)
        if self._data is not None and len(self._data) > 0:
            self._draw_data_overview(painter, plot_rect)

        # Draw window region
        self._draw_window_region(painter, plot_rect)

        # Draw labels
        self._draw_labels(painter, rect, plot_rect)

    def _draw_data_overview(self, painter, plot_rect):
        """Draw simplified data overview"""
        from PySide6.QtGui import QPen, QBrush, QPainterPath

        try:
            clean_data = self._data[~np.isnan(self._data.astype(float))].astype(float)
        except (TypeError, ValueError):
            return

        if len(clean_data) == 0:
            return

        # Downsample for display
        if self.orientation == 'horizontal':
            n_bins = min(plot_rect.width(), 100)
        else:
            n_bins = min(plot_rect.height(), 100)

        n_bins = max(10, int(n_bins))

        try:
            hist, bin_edges = np.histogram(clean_data, bins=n_bins)
            max_hist = max(hist) if max(hist) > 0 else 1

            # Draw histogram bars
            painter.setPen(QPen(QColor('#94A3B8'), 1))
            painter.setBrush(QBrush(QColor('#CBD5E1')))

            if self.orientation == 'horizontal':
                bar_width = plot_rect.width() / len(hist)
                for i, h in enumerate(hist):
                    bar_height = (h / max_hist) * (plot_rect.height() - 4)
                    x = plot_rect.left() + i * bar_width
                    y = plot_rect.bottom() - bar_height - 2
                    painter.drawRect(int(x), int(y), int(bar_width - 1), int(bar_height))
            else:
                bar_height = plot_rect.height() / len(hist)
                for i, h in enumerate(hist):
                    bar_width = (h / max_hist) * (plot_rect.width() - 4)
                    x = plot_rect.left() + 2
                    y = plot_rect.top() + i * bar_height
                    painter.drawRect(int(x), int(y), int(bar_width), int(bar_height - 1))
        except Exception:
            pass

    def _draw_window_region(self, painter, plot_rect):
        """Draw the sliding window region"""
        from PySide6.QtGui import QPen, QBrush

        # Calculate window position in widget coordinates
        win_start = self._value_to_pos(self._window_min)
        win_end = self._value_to_pos(self._window_max)

        if self.orientation == 'horizontal':
            x1 = plot_rect.left() + win_start * plot_rect.width()
            x2 = plot_rect.left() + win_end * plot_rect.width()

            # Draw shaded regions outside window
            painter.fillRect(
                int(plot_rect.left()), plot_rect.top(),
                int(x1 - plot_rect.left()), plot_rect.height(),
                QColor(0, 0, 0, 40)
            )
            painter.fillRect(
                int(x2), plot_rect.top(),
                int(plot_rect.right() - x2), plot_rect.height(),
                QColor(0, 0, 0, 40)
            )

            # Draw window frame
            painter.setPen(QPen(QColor('#4F46E5'), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(x1), plot_rect.top(), int(x2 - x1), plot_rect.height())

            # Draw handles
            handle_width = 6
            painter.fillRect(int(x1 - handle_width // 2), plot_rect.top(),
                            handle_width, plot_rect.height(), QColor('#4F46E5'))
            painter.fillRect(int(x2 - handle_width // 2), plot_rect.top(),
                            handle_width, plot_rect.height(), QColor('#4F46E5'))
        else:
            y1 = plot_rect.top() + (1 - win_end) * plot_rect.height()
            y2 = plot_rect.top() + (1 - win_start) * plot_rect.height()

            # Draw shaded regions outside window
            painter.fillRect(
                plot_rect.left(), plot_rect.top(),
                plot_rect.width(), int(y1 - plot_rect.top()),
                QColor(0, 0, 0, 40)
            )
            painter.fillRect(
                plot_rect.left(), int(y2),
                plot_rect.width(), int(plot_rect.bottom() - y2),
                QColor(0, 0, 0, 40)
            )

            # Draw window frame
            painter.setPen(QPen(QColor('#4F46E5'), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(plot_rect.left(), int(y1), plot_rect.width(), int(y2 - y1))

            # Draw handles
            handle_height = 6
            painter.fillRect(plot_rect.left(), int(y1 - handle_height // 2),
                            plot_rect.width(), handle_height, QColor('#4F46E5'))
            painter.fillRect(plot_rect.left(), int(y2 - handle_height // 2),
                            plot_rect.width(), handle_height, QColor('#4F46E5'))

    def _draw_labels(self, painter, rect, plot_rect):
        """Draw axis labels"""
        from PySide6.QtGui import QFont

        font = QFont('Arial', 8)
        painter.setFont(font)
        painter.setPen(QColor('#6B7280'))

        # Format values
        def fmt(v):
            if abs(v) >= 1e6:
                return f'{v/1e6:.1f}M'
            elif abs(v) >= 1e3:
                return f'{v/1e3:.1f}K'
            elif abs(v) < 0.01 and v != 0:
                return f'{v:.2e}'
            else:
                return f'{v:.2f}'

        if self.orientation == 'horizontal':
            # Draw min/max labels
            painter.drawText(plot_rect.left(), rect.top() + 12, fmt(self._data_min))
            painter.drawText(plot_rect.right() - 40, rect.top() + 12, fmt(self._data_max))

            # Draw current window values
            win_start_x = plot_rect.left() + self._value_to_pos(self._window_min) * plot_rect.width()
            win_end_x = plot_rect.left() + self._value_to_pos(self._window_max) * plot_rect.width()

            painter.setPen(QColor('#4F46E5'))
            painter.drawText(int(win_start_x) - 20, rect.bottom() - 2, fmt(self._window_min))
            painter.drawText(int(win_end_x) - 20, rect.bottom() - 2, fmt(self._window_max))
        else:
            # Vertical labels
            painter.drawText(2, plot_rect.bottom(), fmt(self._data_min))
            painter.drawText(2, plot_rect.top() + 10, fmt(self._data_max))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        pos = event.position()
        self._drag_start = pos

        margin = 4
        if self.orientation == 'horizontal':
            plot_rect = self.rect().adjusted(margin, margin + 15, -margin, -margin)
            x = pos.x()

            win_start_x = plot_rect.left() + self._value_to_pos(self._window_min) * plot_rect.width()
            win_end_x = plot_rect.left() + self._value_to_pos(self._window_max) * plot_rect.width()

            handle_size = 10

            if abs(x - win_start_x) < handle_size:
                self._drag_mode = 'left'
            elif abs(x - win_end_x) < handle_size:
                self._drag_mode = 'right'
            elif win_start_x <= x <= win_end_x:
                self._drag_mode = 'move'
            else:
                self._drag_mode = None
        else:
            plot_rect = self.rect().adjusted(margin + 15, margin, -margin, -margin)
            y = pos.y()

            win_top_y = plot_rect.top() + (1 - self._value_to_pos(self._window_max)) * plot_rect.height()
            win_bottom_y = plot_rect.top() + (1 - self._value_to_pos(self._window_min)) * plot_rect.height()

            handle_size = 10

            if abs(y - win_top_y) < handle_size:
                self._drag_mode = 'top'
            elif abs(y - win_bottom_y) < handle_size:
                self._drag_mode = 'bottom'
            elif win_top_y <= y <= win_bottom_y:
                self._drag_mode = 'move'
            else:
                self._drag_mode = None

        if self._drag_mode:
            self._dragging = True
            self._drag_start_min = self._window_min
            self._drag_start_max = self._window_max
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        pos = event.position()

        margin = 4
        if self.orientation == 'horizontal':
            plot_rect = self.rect().adjusted(margin, margin + 15, -margin, -margin)
        else:
            plot_rect = self.rect().adjusted(margin + 15, margin, -margin, -margin)

        if self._dragging and self._drag_mode:
            delta_value = 0

            if self.orientation == 'horizontal':
                delta_px = pos.x() - self._drag_start.x()
                delta_value = (delta_px / plot_rect.width()) * (self._data_max - self._data_min)

                if self._drag_mode == 'move':
                    new_min = self._drag_start_min + delta_value
                    new_max = self._drag_start_max + delta_value
                    window_size = self._drag_start_max - self._drag_start_min

                    # Clamp to data range
                    if new_min < self._data_min:
                        new_min = self._data_min
                        new_max = self._data_min + window_size
                    if new_max > self._data_max:
                        new_max = self._data_max
                        new_min = self._data_max - window_size

                    self._window_min = new_min
                    self._window_max = new_max

                elif self._drag_mode == 'left':
                    new_min = self._drag_start_min + delta_value
                    new_min = max(self._data_min, min(new_min, self._window_max - 0.01 * (self._data_max - self._data_min)))
                    self._window_min = new_min

                elif self._drag_mode == 'right':
                    new_max = self._drag_start_max + delta_value
                    new_max = min(self._data_max, max(new_max, self._window_min + 0.01 * (self._data_max - self._data_min)))
                    self._window_max = new_max
            else:
                # Vertical orientation - invert because Y grows downward
                delta_px = self._drag_start.y() - pos.y()
                delta_value = (delta_px / plot_rect.height()) * (self._data_max - self._data_min)

                if self._drag_mode == 'move':
                    new_min = self._drag_start_min + delta_value
                    new_max = self._drag_start_max + delta_value
                    window_size = self._drag_start_max - self._drag_start_min

                    if new_min < self._data_min:
                        new_min = self._data_min
                        new_max = self._data_min + window_size
                    if new_max > self._data_max:
                        new_max = self._data_max
                        new_min = self._data_max - window_size

                    self._window_min = new_min
                    self._window_max = new_max

                elif self._drag_mode == 'top':
                    new_max = self._drag_start_max + delta_value
                    new_max = min(self._data_max, max(new_max, self._window_min + 0.01 * (self._data_max - self._data_min)))
                    self._window_max = new_max

                elif self._drag_mode == 'bottom':
                    new_min = self._drag_start_min + delta_value
                    new_min = max(self._data_min, min(new_min, self._window_max - 0.01 * (self._data_max - self._data_min)))
                    self._window_min = new_min

            self.range_changed.emit(self._window_min, self._window_max)
            self.update()
        else:
            # Update cursor based on position
            if self.orientation == 'horizontal':
                x = pos.x()
                win_start_x = plot_rect.left() + self._value_to_pos(self._window_min) * plot_rect.width()
                win_end_x = plot_rect.left() + self._value_to_pos(self._window_max) * plot_rect.width()

                if abs(x - win_start_x) < 10 or abs(x - win_end_x) < 10:
                    self.setCursor(Qt.SizeHorCursor)
                elif win_start_x <= x <= win_end_x:
                    self.setCursor(Qt.OpenHandCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            else:
                y = pos.y()
                win_top_y = plot_rect.top() + (1 - self._value_to_pos(self._window_max)) * plot_rect.height()
                win_bottom_y = plot_rect.top() + (1 - self._value_to_pos(self._window_min)) * plot_rect.height()

                if abs(y - win_top_y) < 10 or abs(y - win_bottom_y) < 10:
                    self.setCursor(Qt.SizeVerCursor)
                elif win_top_y <= y <= win_bottom_y:
                    self.setCursor(Qt.OpenHandCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._drag_mode = None
            self.setCursor(Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, event):
        """Double-click to reset to full range"""
        if event.button() == Qt.LeftButton:
            self.reset_window()


# ==================== Graph Panel ====================

class GraphPanel(QWidget):
    """
    Graph Panel - Main container

    Layout:
    ┌──────────────┬───────────────────────────┬──────────┐
    │   Options    │       Main Graph          │  Stats   │
    │ (280px)      │    + Sliding Windows      │ (180px)  │
    │ (Chart/      │                           │          │
    │  Legend/     │                           │          │
    │  Axes/Style) │                           │          │
    └──────────────┴───────────────────────────┴──────────┘
    """

    def __init__(self, state: AppState, engine: DataEngine):
        super().__init__()
        self.state = state
        self.engine = engine

        # Sliding window state
        self._sliding_window_enabled = False
        self._x_window_enabled = True
        self._y_window_enabled = True

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)

        # Options Panel (left) - now includes Legend as a tab
        self.options_panel = GraphOptionsPanel(self.state)
        self.splitter.addWidget(self.options_panel)

        # Center panel with main graph and sliding windows
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)

        # Graph container with Y sliding window
        graph_container = QWidget()
        graph_layout = QHBoxLayout(graph_container)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(4)

        # Y-axis sliding window (left of graph)
        self.y_sliding_window = SlidingWindowWidget(orientation='vertical')
        self.y_sliding_window.setVisible(False)  # Hidden by default
        graph_layout.addWidget(self.y_sliding_window)

        # Main Graph
        self.main_graph = MainGraph(self.state)
        graph_layout.addWidget(self.main_graph, 1)

        center_layout.addWidget(graph_container, 1)

        # X-axis sliding window (below graph)
        self.x_sliding_window = SlidingWindowWidget(orientation='horizontal')
        self.x_sliding_window.setVisible(False)  # Hidden by default
        center_layout.addWidget(self.x_sliding_window)

        self.splitter.addWidget(center_widget)

        # Stat Panel (right) - no float button
        self.stat_panel = StatPanel(self.state)
        self.splitter.addWidget(self.stat_panel)

        # Splitter sizes: Options(280) + Graph(stretch) + Stats(180)
        self.splitter.setSizes([280, 500, 180])
        self.splitter.setStretchFactor(0, 0)  # Options: fixed
        self.splitter.setStretchFactor(1, 1)  # Graph: stretch
        self.splitter.setStretchFactor(2, 0)  # Stats: fixed

        layout.addWidget(self.splitter)
    
    def _connect_signals(self):
        self.state.chart_settings_changed.connect(self.refresh)
        self.state.group_zone_changed.connect(self._on_group_changed)
        self.state.value_zone_changed.connect(self.refresh)
        self.state.hover_zone_changed.connect(self.refresh)
        self.state.selection_changed.connect(self._on_selection_changed)
        self.options_panel.option_changed.connect(self.refresh)

        # Connect sliding window signals
        self.x_sliding_window.range_changed.connect(self._on_x_window_changed)
        self.y_sliding_window.range_changed.connect(self._on_y_window_changed)

        # Connect view range changes to update sliding windows
        self.main_graph.plotItem.sigRangeChanged.connect(self._on_graph_range_changed)

    def _on_x_window_changed(self, min_val: float, max_val: float):
        """Handle X-axis sliding window range change"""
        if self._sliding_window_enabled and self._x_window_enabled:
            self.main_graph.setXRange(min_val, max_val, padding=0)

    def _on_y_window_changed(self, min_val: float, max_val: float):
        """Handle Y-axis sliding window range change"""
        if self._sliding_window_enabled and self._y_window_enabled:
            self.main_graph.setYRange(min_val, max_val, padding=0)

    def _on_graph_range_changed(self, vb, ranges):
        """Update sliding windows when graph range changes"""
        if not self._sliding_window_enabled:
            return

        x_range, y_range = ranges
        if self._x_window_enabled:
            self.x_sliding_window.set_window(x_range[0], x_range[1])
        if self._y_window_enabled:
            self.y_sliding_window.set_window(y_range[0], y_range[1])

    def set_sliding_window_enabled(self, enabled: bool, x_enabled: bool = True, y_enabled: bool = True):
        """Enable or disable sliding window controls"""
        self._sliding_window_enabled = enabled
        self._x_window_enabled = x_enabled
        self._y_window_enabled = y_enabled

        self.x_sliding_window.setVisible(enabled and x_enabled)
        self.y_sliding_window.setVisible(enabled and y_enabled)

        if enabled:
            self._update_sliding_window_data()

    def _update_sliding_window_data(self):
        """Update sliding window data from current graph data"""
        if self.main_graph._data_x is not None:
            self.x_sliding_window.set_data(self.main_graph._data_x)
        if self.main_graph._data_y is not None:
            self.y_sliding_window.set_data(self.main_graph._data_y)

    def _on_group_changed(self):
        """그룹 변경 시 범례 업데이트"""
        if self.state.group_columns:
            groups = self._build_group_masks()
            if groups:
                self.options_panel.set_series(list(groups.keys()))
        else:
            # Single series
            if self.state.value_columns:
                self.options_panel.set_series([self.state.value_columns[0].name])
            else:
                self.options_panel.set_series(["Data"])
        self.refresh()

    def refresh(self):
        """Refresh graph"""
        if not self.engine.is_loaded:
            return

        # Get options including legend settings
        options = self.options_panel.get_chart_options()
        legend_settings = self.options_panel.get_legend_settings()

        # Get sampling settings from options
        show_all_data = options.get('show_all_data', False)
        max_points = options.get('max_points', 10000)
        sampling_algorithm = options.get('sampling_algorithm', 'auto')

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

        # Total points for status display
        total_points = len(x_data)

        # Determine if we need OpenGL acceleration
        # Auto-enable OpenGL for large datasets (>50K points) or when showing all data
        OPENGL_THRESHOLD = 50000
        needs_opengl = total_points > OPENGL_THRESHOLD or (show_all_data and total_points > max_points)
        self.main_graph.enable_opengl(needs_opengl)

        # Sampling logic
        is_sampled = False
        algorithm_used = ""

        if show_all_data:
            # Show all data - no sampling
            x_sampled, y_sampled = x_data, y_data
        elif total_points > max_points:
            # Apply sampling
            valid_mask = ~(np.isnan(x_data.astype(float)) | np.isnan(y_data.astype(float)))
            x_valid = x_data[valid_mask].astype(np.float64)
            y_valid = y_data[valid_mask].astype(np.float64)

            if len(x_valid) > max_points:
                is_sampled = True

                # Apply selected sampling algorithm
                if sampling_algorithm == 'auto':
                    x_sampled, y_sampled = DataSampler.auto_sample(
                        x_valid, y_valid, max_points=max_points
                    )
                    # Determine which algorithm was used
                    is_sorted = np.all(x_valid[:-1] <= x_valid[1:])
                    algorithm_used = "LTTB" if is_sorted else "Min-Max"
                elif sampling_algorithm == 'lttb':
                    x_sampled, y_sampled = DataSampler.lttb(
                        x_valid, y_valid, threshold=max_points
                    )
                    algorithm_used = "LTTB"
                elif sampling_algorithm == 'minmax':
                    x_sampled, y_sampled = DataSampler.min_max_per_bucket(
                        x_valid, y_valid, n_buckets=max_points // 2
                    )
                    algorithm_used = "Min-Max"
                elif sampling_algorithm == 'random':
                    x_sampled, y_sampled = DataSampler.random_sample(
                        x_valid, y_valid, n_samples=max_points
                    )
                    algorithm_used = "Random"
                else:
                    x_sampled, y_sampled = DataSampler.auto_sample(
                        x_valid, y_valid, max_points=max_points
                    )
                    algorithm_used = "Auto"

                # Clear groups when sampling (can't maintain group structure)
                groups = None
            else:
                x_sampled, y_sampled = x_valid, y_valid
        else:
            x_sampled, y_sampled = x_data, y_data

        # Plot data
        self.main_graph.plot_data(
            x_sampled, y_sampled,
            groups=groups,
            chart_type=options.get('chart_type', ChartType.LINE),
            options=options,
            legend_settings=legend_settings
        )

        # Update sampling status label
        displayed_points = len(x_sampled)
        self.main_graph.update_sampling_status(
            displayed_points=displayed_points,
            total_points=total_points,
            is_sampled=is_sampled,
            algorithm=algorithm_used
        )

        # Set hover data
        hover_columns = self.state.hover_columns
        if hover_columns:
            hover_data = {}
            for col in hover_columns:
                if col in self.engine.df.columns:
                    col_data = self.engine.df[col].to_list()
                    # Apply same sampling if needed
                    if len(col_data) > max_points and len(x_sampled) < len(col_data):
                        # Simple downsampling for hover data
                        step = len(col_data) // len(x_sampled)
                        col_data = col_data[::step][:len(x_sampled)]
                    hover_data[col] = col_data
            self.main_graph.set_hover_data(hover_columns, hover_data)
        else:
            self.main_graph.set_hover_data([], {})

        # Update stats
        self.stat_panel.update_histograms(x_sampled, y_sampled)
        if self.state.value_columns:
            stats = self.engine.get_statistics(self.state.value_columns[0].name)
            self.stat_panel.update_stats(stats)

        # Update sliding windows with full data for navigation
        # Use original data for navigation, not sampled data
        sliding_window_enabled = options.get('sliding_window_enabled', False)
        x_window_enabled = options.get('x_sliding_window', True)
        y_window_enabled = options.get('y_sliding_window', True)

        self._sliding_window_enabled = sliding_window_enabled
        self._x_window_enabled = x_window_enabled
        self._y_window_enabled = y_window_enabled

        self.x_sliding_window.setVisible(sliding_window_enabled and x_window_enabled)
        self.y_sliding_window.setVisible(sliding_window_enabled and y_window_enabled)

        if sliding_window_enabled:
            if x_window_enabled:
                self.x_sliding_window.set_data(x_data.astype(float) if hasattr(x_data, 'astype') else np.array(x_data, dtype=float))
            if y_window_enabled:
                self.y_sliding_window.set_data(y_data.astype(float) if hasattr(y_data, 'astype') else np.array(y_data, dtype=float))

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
            self.options_panel.set_series([numeric_cols[0]])
