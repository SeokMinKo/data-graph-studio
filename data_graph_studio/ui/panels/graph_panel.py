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
from PySide6.QtGui import QMouseEvent, QColor, QIcon, QPixmap, QPainter, QBrush

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
    """확대된 차트를 보여주는 다이얼로그 (Non-modal)"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint)
        self.setModal(False)  # Non-modal: main window remains interactive
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
                    self.plot_widget.plot(bin_edges, hist, stepMode="center", fillLevel=0,
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

    def plot_pie_chart(self, labels: list, values: list, title: str, colors: list = None):
        """Plot pie chart as bar chart (pyqtgraph doesn't support pie charts natively)"""
        self.setWindowTitle(title)
        self.plot_widget.clear()

        if not labels or not values:
            return

        try:
            # Convert to percentages for display
            total = sum(values)
            if total == 0:
                return

            percentages = [v / total * 100 for v in values]

            # Default colors
            if colors is None:
                default_colors = [
                    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
                ]
                colors = [default_colors[i % len(default_colors)] for i in range(len(labels))]

            # Create horizontal bar chart representation
            x_positions = np.arange(len(labels))
            bars = pg.BarGraphItem(
                x=x_positions,
                height=values,
                width=0.6,
                brushes=[pg.mkBrush(c) for c in colors],
                pens=[pg.mkPen(c, width=1) for c in colors]
            )
            self.plot_widget.addItem(bars)

            # Set axis labels
            self.plot_widget.setLabel('left', 'Value (Sum)')
            self.plot_widget.setLabel('bottom', 'Category')

            # Create custom x-axis labels
            ax = self.plot_widget.getAxis('bottom')
            ax.setTicks([[(i, str(label)[:15]) for i, label in enumerate(labels)]])

            # Add percentage labels on top of bars
            for i, (val, pct) in enumerate(zip(values, percentages)):
                text = pg.TextItem(f'{pct:.1f}%', anchor=(0.5, 1), color='k')
                text.setPos(i, val)
                self.plot_widget.addItem(text)

            # Add total label
            total_text = pg.TextItem(f'Total: {total:,.2f}', anchor=(0, 0), color='#4B5563')
            total_text.setPos(0, max(values) * 1.1)
            self.plot_widget.addItem(total_text)

        except Exception as e:
            print(f"Error plotting pie chart: {e}")

    def plot_percentile(self, data: np.ndarray, title: str, color: tuple = (100, 100, 200)):
        """Plot percentile graph (line chart showing value at each percentile)"""
        self.setWindowTitle(title)
        self.plot_widget.clear()

        if data is None or len(data) == 0:
            return

        try:
            clean_data = data[~np.isnan(data)]
            if len(clean_data) == 0:
                return

            # Calculate percentiles from 0 to 100
            percentiles = np.arange(0, 101)
            percentile_values = np.percentile(clean_data, percentiles)

            # Plot line
            pen = pg.mkPen(color=color[:3], width=2)
            self.plot_widget.plot(percentiles, percentile_values, pen=pen)

            # Add key percentile markers
            key_percentiles = [25, 50, 75]
            key_values = np.percentile(clean_data, key_percentiles)

            scatter = pg.ScatterPlotItem(
                x=key_percentiles,
                y=key_values,
                size=10,
                brush=pg.mkBrush('#EF4444'),
                pen=pg.mkPen('w', width=1)
            )
            self.plot_widget.addItem(scatter)

            # Labels
            self.plot_widget.setLabel('bottom', 'Percentile')
            self.plot_widget.setLabel('left', 'Value')

            # Stats text
            stats_text = f"P25: {key_values[0]:.2f}\nP50: {key_values[1]:.2f}\nP75: {key_values[2]:.2f}"
            text_item = pg.TextItem(stats_text, anchor=(0, 0), color='k')
            text_item.setPos(5, percentile_values[-1] * 0.9)
            self.plot_widget.addItem(text_item)

        except Exception as e:
            print(f"Error plotting percentile: {e}")


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
        self._chart_type = "histogram"  # histogram, pie, percentile
        self._pie_labels = None
        self._pie_values = None
        self._pie_colors = None

    def set_data(self, data: np.ndarray, title: str, color: tuple, bins: int = 30, horizontal: bool = False):
        self._data = data
        self._title = title
        self._color = color
        self._bins = bins
        self._horizontal = horizontal
        self._chart_type = "histogram"

    def set_pie_data(self, labels: list, values: list, title: str, colors: list = None):
        """Set data for pie chart display"""
        self._pie_labels = labels
        self._pie_values = values
        self._title = title
        self._pie_colors = colors
        self._chart_type = "pie"

    def set_percentile_data(self, data: np.ndarray, title: str, color: tuple = (100, 100, 200)):
        """Set data for percentile chart display"""
        self._data = data
        self._title = title
        self._color = color
        self._chart_type = "percentile"

    def set_bins(self, bins: int):
        """Set the number of bins for histogram"""
        self._bins = bins

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            self._show_expanded()
        super().mouseDoubleClickEvent(event)

    def _show_expanded(self):
        dialog = ExpandedChartDialog(self._title, self)

        if self._chart_type == "histogram":
            if self._data is None:
                return
            dialog.plot_histogram(self._data, self._title, self._color, bins=self._bins, horizontal=self._horizontal)
        elif self._chart_type == "pie":
            if self._pie_labels is None or self._pie_values is None:
                return
            dialog.plot_pie_chart(self._pie_labels, self._pie_values, self._title, self._pie_colors)
        elif self._chart_type == "percentile":
            if self._data is None:
                return
            dialog.plot_percentile(self._data, self._title, self._color)
        else:
            return

        dialog.show()  # Non-modal: use show() instead of exec()


from ...core.state import AppState, ChartType, ToolMode, ComparisonMode
from ...core.data_engine import DataEngine
from ...core.expression_engine import ExpressionEngine, ExpressionError
from ...graph.sampling import DataSampler
from ..drawing import (
    DrawingManager, DrawingStyle, LineStyle,
    LineDrawing, CircleDrawing, RectDrawing, TextDrawing,
    DrawingStyleDialog, RectStyleDialog, TextInputDialog,
    snap_to_angle
)
import polars as pl


class FormattedAxisItem(pg.AxisItem):
    """Custom axis item with value formatting including Excel-style custom formats and categorical support"""

    # Preset format types
    PRESET_FORMATS = {
        'number': '#,##0',
        'decimal': '#,##0.00',
        'scientific': '0.00E+00',
        'percent': '0.0%',
        'k': '#,##0,"K"',
        'm': '#,##0,,"M"',
        'b': '#,##0,,,"B"',
        'bytes': 'bytes',
        'time': 'time',
    }

    def __init__(self, orientation, format_type=None, **kwargs):
        super().__init__(orientation, **kwargs)
        self.format_type = format_type
        self.custom_format = None  # For Excel-style custom formats
        self._categorical_labels = None  # List of category labels
        self._is_categorical = False

    def set_format(self, format_type):
        """Set format type - can be preset name or Excel-style format string"""
        self.format_type = format_type
        # Check if it's a custom format string (not a preset)
        if format_type and format_type not in self.PRESET_FORMATS and format_type != 'auto':
            self.custom_format = format_type
        else:
            self.custom_format = None

    def set_categorical(self, labels: list):
        """Set categorical labels for this axis"""
        self._categorical_labels = labels
        self._is_categorical = True if labels else False

    def clear_categorical(self):
        """Clear categorical mode"""
        self._categorical_labels = None
        self._is_categorical = False

    def tickStrings(self, values, scale, spacing):
        # Handle categorical axis
        if self._is_categorical and self._categorical_labels:
            strings = []
            for v in values:
                idx = int(round(v))
                if 0 <= idx < len(self._categorical_labels):
                    strings.append(str(self._categorical_labels[idx]))
                else:
                    strings.append("")
            return strings

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
            # Check for custom Excel-style format
            if self.custom_format:
                return self._apply_excel_format(value, self.custom_format)

            # Built-in preset formats
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

    def _apply_excel_format(self, value, fmt: str) -> str:
        """
        Apply Excel-style number format string.
        Supported patterns:
        - #,##0 : thousands separator, no decimals
        - #,##0.00 : thousands separator, 2 decimals
        - 0.00 : fixed decimals
        - 0.0% : percentage (multiplies by 100)
        - 0.00E+00 : scientific notation
        - #,##0,"K" : divide by 1000, append K
        - #,##0,,"M" : divide by 1000000, append M
        - [>1000]#,##0,"K";0 : conditional formatting
        - "prefix"#,##0"suffix" : with prefix/suffix text
        """
        try:
            # Handle percentage format
            if fmt.endswith('%'):
                # Count decimal places before %
                decimal_part = fmt[:-1]
                if '.' in decimal_part:
                    decimals = len(decimal_part.split('.')[-1])
                else:
                    decimals = 0
                return f"{value * 100:.{decimals}f}%"

            # Handle scientific notation
            if 'E' in fmt.upper():
                # Parse precision from format
                if '.' in fmt:
                    decimals = len(fmt.split('.')[1].split('E')[0].split('e')[0])
                else:
                    decimals = 2
                return f"{value:.{decimals}e}"

            # Handle thousand/million/billion divisors (Excel uses comma)
            divisor = 1
            suffix = ""
            temp_fmt = fmt

            # Count trailing commas for division
            while temp_fmt.endswith(','):
                divisor *= 1000
                temp_fmt = temp_fmt[:-1]

            # Check for suffix in quotes after format
            if '"' in temp_fmt:
                import re
                suffix_match = re.search(r'"([^"]*)"$', temp_fmt)
                if suffix_match:
                    suffix = suffix_match.group(1)
                    temp_fmt = temp_fmt[:suffix_match.start()]

            # Check for prefix in quotes
            prefix = ""
            if '"' in temp_fmt:
                import re
                prefix_match = re.search(r'^"([^"]*)"', temp_fmt)
                if prefix_match:
                    prefix = prefix_match.group(1)
                    temp_fmt = temp_fmt[prefix_match.end():]

            adjusted_value = value / divisor if divisor > 1 else value

            # Determine decimal places
            if '.' in temp_fmt:
                # Count 0s and #s after decimal
                decimal_part = temp_fmt.split('.')[-1]
                # Remove any non-digit format chars
                decimal_part = ''.join(c for c in decimal_part if c in '0#')
                decimals = len(decimal_part)
            else:
                decimals = 0

            # Check for thousands separator
            use_thousands = '#,##' in temp_fmt or '0,00' in temp_fmt or ',##0' in temp_fmt

            if use_thousands:
                result = f"{adjusted_value:,.{decimals}f}"
            else:
                result = f"{adjusted_value:.{decimals}f}"

            return f"{prefix}{result}{suffix}"

        except Exception:
            # Fallback to simple format
            return f"{value:.2f}"


# ==================== Options Panel ====================

class GraphOptionsPanel(QFrame):
    """Compact Graph Options Panel"""
    
    option_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("GraphOptionsPanel")
        self.setMinimumWidth(200)
        self.setMaximumWidth(240)
        
        self._setup_ui()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #GraphOptionsPanel {
                background: #FAFAFA;
                border: none;
                border-radius: 8px;
            }
            QTabWidget::pane {
                border: none;
                background: transparent;
            }
            QTabBar::tab {
                background: transparent;
                border: none;
                padding: 6px 10px;
                margin-right: 2px;
                font-size: 10px;
                color: #9CA3AF;
            }
            QTabBar::tab:selected {
                color: #4F46E5;
                font-weight: 600;
                border-bottom: 2px solid #4F46E5;
            }
            QGroupBox {
                background: transparent;
                border: none;
                margin-top: 8px;
                padding: 4px;
                font-weight: 500;
                font-size: 10px;
                color: #6B7280;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 4px;
                padding: 0 2px;
            }
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 4px 6px;
                color: #374151;
                min-height: 20px;
                font-size: 11px;
            }
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
                border-color: #6366F1;
            }
            QCheckBox {
                color: #374151;
                font-size: 10px;
                spacing: 4px;
            }
            QLabel {
                color: #6B7280;
                font-size: 10px;
                background: transparent;
            }
            QSlider::groove:horizontal {
                height: 3px;
                background: #E5E7EB;
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                width: 10px;
                height: 10px;
                margin: -4px 0;
                background: #4F46E5;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #4F46E5;
                border-radius: 1px;
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
        self.x_format_combo.setEditable(True)
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
        self.y_format_combo.setEditable(True)
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
    """Compact Legend Settings Panel"""
    
    settings_changed = Signal()
    
    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("LegendPanel")
        self.setMinimumWidth(160)
        self.setMaximumWidth(200)
        
        self._series_items: List[Dict] = []
        self._setup_ui()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #LegendPanel {
                background: #FAFAFA;
                border: none;
                border-radius: 8px;
            }
            QGroupBox {
                background: transparent;
                border: none;
                margin-top: 8px;
                padding: 4px;
                font-weight: 500;
                font-size: 10px;
                color: #6B7280;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 4px;
                padding: 0 2px;
            }
            QComboBox {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 4px 6px;
                color: #374151;
                min-height: 20px;
                font-size: 11px;
            }
            QCheckBox {
                color: #374151;
                font-size: 10px;
            }
            QLabel {
                color: #6B7280;
                font-size: 10px;
                background: transparent;
            }
            QListWidget {
                background: transparent;
                border: none;
                padding: 2px;
            }
            QListWidget::item {
                padding: 2px;
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
    """
    Statistics Panel with 2x2 Grid Layout - Minimal Design
    
    Layout:
    ┌─────────────────────────────────────┐
    │  📈 Statistics                      │
    ├──────────────────┬──────────────────┤
    │  X Distribution  │  Y Distribution  │
    ├──────────────────┼──────────────────┤
    │  Pie Chart       │  Percentile      │
    ├──────────────────┴──────────────────┤
    │  Summary                            │
    └─────────────────────────────────────┘
    """

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("StatPanel")
        self.setMinimumWidth(280)
        self.setMaximumWidth(360)

        self._x_data: Optional[np.ndarray] = None
        self._y_data: Optional[np.ndarray] = None
        self._x_bins: int = 30
        self._y_bins: int = 30
        self._group_data: Optional[Dict[str, float]] = None

        self._setup_ui()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #StatPanel {
                background: #FAFAFA;
                border: none;
                border-radius: 8px;
            }
            QGroupBox {
                background: transparent;
                border: none;
                margin-top: 8px;
                padding: 4px;
                font-weight: 500;
                font-size: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 4px;
                padding: 0 2px;
                color: #6B7280;
            }
            QLabel {
                background: transparent;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header - compact
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_layout.setSpacing(4)

        header = QLabel("📈 Stats")
        header.setStyleSheet("font-weight: 600; font-size: 11px; color: #374151;")
        header_layout.addWidget(header)

        header_layout.addStretch()

        # Bin controls (hidden)
        self.x_bins_spin = QSpinBox()
        self.x_bins_spin.setRange(5, 200)
        self.x_bins_spin.setValue(30)
        self.x_bins_spin.valueChanged.connect(self._on_x_bins_changed)
        self.x_bins_spin.hide()

        self.y_bins_spin = QSpinBox()
        self.y_bins_spin.setRange(5, 200)
        self.y_bins_spin.setValue(30)
        self.y_bins_spin.valueChanged.connect(self._on_y_bins_changed)
        self.y_bins_spin.hide()
        
        layout.addLayout(header_layout)

        # 2x2 Grid for graphs - compact
        graph_grid = QGridLayout()
        graph_grid.setSpacing(4)
        graph_grid.setContentsMargins(0, 0, 0, 0)

        # Create mini plot widgets with minimal chrome
        def create_plot_group(title: str) -> tuple:
            group = QGroupBox(title)
            group.setToolTip("Double-click to expand")
            grp_layout = QVBoxLayout(group)
            grp_layout.setContentsMargins(2, 2, 2, 2)
            grp_layout.setSpacing(0)
            
            widget = ClickablePlotWidget()
            widget.setMinimumHeight(60)
            widget.setMaximumHeight(80)
            widget.setBackground('#FAFAFA')
            widget.hideAxis('bottom')
            widget.hideAxis('left')
            widget.setCursor(Qt.PointingHandCursor)
            widget.getPlotItem().setContentsMargins(0, 0, 0, 0)
            grp_layout.addWidget(widget)
            return group, widget

        # X Distribution
        x_group, self.x_hist_widget = create_plot_group("X Dist")
        graph_grid.addWidget(x_group, 0, 0)

        # Y Distribution
        y_group, self.y_hist_widget = create_plot_group("Y Dist")
        graph_grid.addWidget(y_group, 0, 1)

        # Pie Chart
        pie_group, self.pie_widget = create_plot_group("Pie")
        graph_grid.addWidget(pie_group, 1, 0)

        # Percentile
        pct_group, self.percentile_widget = create_plot_group("Pctl")
        graph_grid.addWidget(pct_group, 1, 1)

        layout.addLayout(graph_grid)

        # Summary Stats - compact
        stats_group = QGroupBox("Summary")
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setContentsMargins(4, 4, 4, 4)

        self.stats_label = QLabel("No data")
        self.stats_label.setStyleSheet("font-family: 'Consolas', monospace; font-size: 9px; color: #6B7280;")
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
                    self.x_hist_widget.plot(bins, hist, stepMode="center", fillLevel=0,
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
                    # Horizontal histogram style
                    bin_centers = (bins[:-1] + bins[1:]) / 2
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

    def _update_pie_chart(self):
        """Update the pie chart (displayed as bar chart)"""
        self.pie_widget.clear()
        if self._group_data is None or len(self._group_data) == 0:
            # If no group data, show Y value distribution by quartiles
            if self._y_data is not None and len(self._y_data) > 0:
                try:
                    clean_y = self._y_data[~np.isnan(self._y_data)]
                    if len(clean_y) > 0:
                        q1 = np.percentile(clean_y, 25)
                        q2 = np.percentile(clean_y, 50)
                        q3 = np.percentile(clean_y, 75)
                        
                        # Count values in each quartile
                        c1 = np.sum(clean_y <= q1)
                        c2 = np.sum((clean_y > q1) & (clean_y <= q2))
                        c3 = np.sum((clean_y > q2) & (clean_y <= q3))
                        c4 = np.sum(clean_y > q3)
                        
                        labels = ['Q1', 'Q2', 'Q3', 'Q4']
                        values = [c1, c2, c3, c4]
                        colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444']
                        
                        # Mini bar chart
                        x = np.arange(len(labels))
                        bars = pg.BarGraphItem(
                            x=x, height=values, width=0.6,
                            brushes=[pg.mkBrush(c) for c in colors]
                        )
                        self.pie_widget.addItem(bars)
                        
                        # Store for expansion
                        self.pie_widget.set_pie_data(labels, values, "Y Value Distribution by Quartile", colors)
                except:
                    pass
            return

        try:
            labels = list(self._group_data.keys())[:10]  # Limit to 10 categories
            values = [self._group_data[k] for k in labels]
            
            colors = [
                '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
            ]
            
            # Mini bar chart representation
            x = np.arange(len(labels))
            bars = pg.BarGraphItem(
                x=x, height=values, width=0.6,
                brushes=[pg.mkBrush(colors[i % len(colors)]) for i in range(len(labels))]
            )
            self.pie_widget.addItem(bars)
            
            # Store for expansion
            self.pie_widget.set_pie_data(labels, values, "Y Groupby Aggregation", colors)
        except:
            pass

    def _update_percentile_chart(self):
        """Update the percentile line chart"""
        self.percentile_widget.clear()
        if self._y_data is None or len(self._y_data) == 0:
            return

        try:
            clean_y = self._y_data[~np.isnan(self._y_data)]
            if len(clean_y) == 0:
                return

            # Calculate percentiles (0, 10, 20, ..., 100)
            percentiles = np.arange(0, 101, 5)  # Every 5% for mini chart
            values = np.percentile(clean_y, percentiles)
            
            # Line plot
            pen = pg.mkPen(color=(148, 103, 189), width=2)  # Purple
            self.percentile_widget.plot(percentiles, values, pen=pen)
            
            # Store for expansion (use finer granularity)
            self.percentile_widget.set_percentile_data(
                clean_y, "Y Values Percentile Distribution", (148, 103, 189)
            )
        except:
            pass
    
    def update_histograms(self, x_data: Optional[np.ndarray], y_data: Optional[np.ndarray],
                          group_data: Optional[Dict[str, float]] = None):
        """Update all charts with new data"""
        self._x_data = x_data
        self._y_data = y_data
        self._group_data = group_data

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

        # Update all charts
        self._update_x_histogram()
        self._update_y_histogram()
        self._update_pie_chart()
        self._update_percentile_chart()

    def set_group_data(self, group_data: Dict[str, float]):
        """Set groupby aggregation data for pie chart"""
        self._group_data = group_data
        self._update_pie_chart()
    
    def update_stats(self, stats: Dict[str, Any]):
        if not stats:
            self.stats_label.setText("No data")
            return
        
        lines = []
        # Format stats in a more compact 2-column layout
        items = list(stats.items())
        for i in range(0, len(items), 2):
            left = items[i]
            right = items[i + 1] if i + 1 < len(items) else None
            
            left_str = f"{left[0]}: {left[1]:.2f}" if isinstance(left[1], float) else f"{left[0]}: {left[1]}"
            
            if right:
                right_str = f"{right[0]}: {right[1]:.2f}" if isinstance(right[1], float) else f"{right[0]}: {right[1]}"
                lines.append(f"{left_str:<20} {right_str}")
            else:
                lines.append(left_str)
        
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

        # Selection highlight scatter
        self._selection_scatter = None

        # Hover data columns
        self._hover_columns: List[str] = []
        self._hover_data: Optional[Dict[str, list]] = None
        self._tooltip_item = None

        # Selection ROI
        self._selection_roi = None
        self._selection_start = None
        self._is_selecting = False
        
        # Lasso selection
        self._lasso_points = []  # List of (x, y) points for lasso path
        self._lasso_path_item = None  # Visual path item
        
        # Drawing mode
        self._is_drawing = False
        self._drawing_start = None
        self._drawing_preview_item = None
        self._drawing_manager: Optional[DrawingManager] = None
        self._current_drawing_style = DrawingStyle()
        self._shift_pressed = False

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
        
        # Clear any drawing in progress
        self._is_drawing = False
        if hasattr(self, '_drawing_preview_item') and self._drawing_preview_item is not None:
            self.removeItem(self._drawing_preview_item)
            self._drawing_preview_item = None

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
        elif mode in [ToolMode.LINE_DRAW, ToolMode.CIRCLE_DRAW, 
                      ToolMode.RECT_DRAW, ToolMode.TEXT_DRAW]:
            # Drawing mode: disable default interactions
            vb.setMouseMode(pg.ViewBox.PanMode)
            vb.setMouseEnabled(x=False, y=False)
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
        legend_settings: Optional[Dict] = None,
        x_categorical_labels: Optional[List[str]] = None,
        y_categorical_labels: Optional[List[str]] = None
    ):
        self.clear_plot()

        # Handle empty or None data
        if x_data is None or y_data is None:
            self._data_x = None
            self._data_y = None
            return

        if len(x_data) == 0 or len(y_data) == 0:
            self._data_x = None
            self._data_y = None
            return

        self._data_x = x_data
        self._data_y = y_data

        options = options or {}
        legend_settings = legend_settings or {'show': True, 'series': []}

        # Apply axis formats
        x_format = options.get('x_format')
        y_format = options.get('y_format')
        self._x_axis.set_format(x_format)
        self._y_axis.set_format(y_format)

        # Apply categorical labels if provided
        if x_categorical_labels:
            self._x_axis.set_categorical(x_categorical_labels)
        else:
            self._x_axis.clear_categorical()

        if y_categorical_labels:
            self._y_axis.set_categorical(y_categorical_labels)
        else:
            self._y_axis.clear_categorical()

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
        # Clear selection highlight
        if hasattr(self, '_selection_scatter') and self._selection_scatter is not None:
            self.removeItem(self._selection_scatter)
            self._selection_scatter = None

    def highlight_selection(self, selected_indices: List[int]):
        """Highlight selected data points on the graph"""
        # Remove previous selection highlight
        if hasattr(self, '_selection_scatter') and self._selection_scatter is not None:
            self.removeItem(self._selection_scatter)
            self._selection_scatter = None
        
        if not selected_indices or self._data_x is None or self._data_y is None:
            return
        
        # Get selected points
        valid_indices = [i for i in selected_indices if 0 <= i < len(self._data_x)]
        if not valid_indices:
            return
        
        selected_x = self._data_x[valid_indices]
        selected_y = self._data_y[valid_indices]
        
        # Create highlight scatter with distinct style
        self._selection_scatter = pg.ScatterPlotItem(
            x=selected_x,
            y=selected_y,
            size=12,
            pen=pg.mkPen('#EF4444', width=2),  # Red border
            brush=pg.mkBrush('#EF444480'),  # Semi-transparent red fill
            symbol='o',
            pxMode=True
        )
        self._selection_scatter.setZValue(100)  # Render on top
        self.addItem(self._selection_scatter)

    def plot_multi_series(
        self,
        series_data: List[Dict],
        chart_type: ChartType = ChartType.LINE,
        options: Dict = None,
        legend_settings: Dict = None
    ):
        """
        Plot multiple data series on the same chart.

        Args:
            series_data: List of dicts with keys:
                - 'x': np.ndarray, X data
                - 'y': np.ndarray, Y data
                - 'name': str, Series name
                - 'color': str, Hex color code
                - 'dataset_id': str (optional)
            chart_type: Chart type to use
            options: Chart options
            legend_settings: Legend settings
        """
        options = options or {}
        legend_settings = legend_settings or {}

        # Clear existing plot
        self.clear_plot()

        # Apply axis settings
        x_title = options.get('x_title', '')
        y_title = options.get('y_title', '')
        if x_title:
            self.setLabel('bottom', x_title)
        if y_title:
            self.setLabel('left', y_title)

        # Set log scale if specified
        x_log = options.get('x_log', False)
        y_log = options.get('y_log', False)
        self.setLogMode(x=x_log, y=y_log)

        # Get style options
        line_width = options.get('line_width', 2)
        marker_size = options.get('marker_size', 6)
        fill_opacity = options.get('fill_opacity', 0.3)

        # Plot each series
        for i, series in enumerate(series_data):
            x = series['x']
            y = series['y']
            name = series.get('name', f'Series {i+1}')
            color_hex = series.get('color', '#1f77b4')

            # Convert hex color to QColor
            color = QColor(color_hex)
            r, g, b = color.red(), color.green(), color.blue()

            # Create pen
            pen = pg.mkPen(color=color_hex, width=line_width)

            if chart_type == ChartType.LINE:
                item = self.plot(x, y, pen=pen, name=name)
                self._plot_items.append(item)

            elif chart_type == ChartType.SCATTER:
                scatter = pg.ScatterPlotItem(
                    x=x, y=y,
                    pen=None,
                    brush=pg.mkBrush(r, g, b, 180),
                    size=marker_size,
                    name=name
                )
                self.addItem(scatter)
                self._scatter_items.append(scatter)

            elif chart_type == ChartType.BAR:
                # For bar chart, offset each series
                bar_width = 0.8 / len(series_data)
                offset = (i - len(series_data) / 2 + 0.5) * bar_width

                x_offset = x.astype(float) + offset
                bar_item = pg.BarGraphItem(
                    x=x_offset, height=y, width=bar_width * 0.9,
                    brush=pg.mkBrush(r, g, b, 200),
                    pen=pg.mkPen(color_hex),
                    name=name
                )
                self.addItem(bar_item)
                self._plot_items.append(bar_item)

            elif chart_type == ChartType.AREA:
                # Fill area under line
                curve = self.plot(x, y, pen=pen, name=name, fillLevel=0,
                                  brush=pg.mkBrush(r, g, b, int(255 * fill_opacity)))
                self._plot_items.append(curve)

            else:
                # Default to line
                item = self.plot(x, y, pen=pen, name=name)
                self._plot_items.append(item)

        # Store first series data for selection
        if series_data:
            self._data_x = series_data[0]['x']
            self._data_y = series_data[0]['y']

        # Update legend settings
        if legend_settings:
            self._update_legend_settings(legend_settings)

        # Auto-range to fit all data
        self.autoRange()

    def _update_legend_settings(self, settings: Dict):
        """Update legend based on settings"""
        show = settings.get('show', True)
        position = settings.get('position', 'top-right')

        if show:
            self.legend.show()
            # Map position string to anchor
            pos_map = {
                'top-left': (0, 0),
                'top-right': (1, 0),
                'bottom-left': (0, 1),
                'bottom-right': (1, 1),
            }
            anchor = pos_map.get(position, (1, 0))
            self.legend.anchor(anchor, anchor)
        else:
            self.legend.hide()

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

                    # Store start position for rect (important for _finish_selection)
                    self._rect_start_x = mouse_point.x()
                    self._rect_start_y = mouse_point.y()

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
        if self.state.tool_mode == ToolMode.RECT_SELECT:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._selection_start = pos
                self._is_selecting = True

                # Clear previous selection ROI
                if self._selection_roi is not None:
                    self.removeItem(self._selection_roi)
                    self._selection_roi = None

                # Store start position for rect
                self._rect_start_x = pos.x()
                self._rect_start_y = pos.y()

                event.accept()
                return
                
        elif self.state.tool_mode == ToolMode.LASSO_SELECT:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._selection_start = pos
                self._is_selecting = True
                
                # Clear previous lasso
                if self._lasso_path_item is not None:
                    self.removeItem(self._lasso_path_item)
                    self._lasso_path_item = None
                
                # Initialize lasso points
                self._lasso_points = [(pos.x(), pos.y())]
                
                event.accept()
                return
        
        # Drawing modes
        elif self.state.tool_mode in [ToolMode.LINE_DRAW, ToolMode.CIRCLE_DRAW, 
                                       ToolMode.RECT_DRAW]:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._drawing_start = (pos.x(), pos.y())
                self._is_drawing = True
                
                # Clear any previous preview
                if self._drawing_preview_item is not None:
                    self.removeItem(self._drawing_preview_item)
                    self._drawing_preview_item = None
                
                event.accept()
                return
        
        elif self.state.tool_mode == ToolMode.TEXT_DRAW:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._handle_text_draw(pos.x(), pos.y())
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for selection drag"""
        if self._is_selecting and self.state.tool_mode == ToolMode.RECT_SELECT:
            pos = self.plotItem.vb.mapSceneToView(event.position())

            # Update selection rectangle visualization
            if hasattr(self, '_rect_start_x'):
                x1 = min(self._rect_start_x, pos.x())
                y1 = min(self._rect_start_y, pos.y())
                width = abs(pos.x() - self._rect_start_x)
                height = abs(pos.y() - self._rect_start_y)

                if self._selection_roi is not None:
                    self.removeItem(self._selection_roi)

                # Draw selection rectangle
                rect = pg.QtWidgets.QGraphicsRectItem(x1, y1, width, height)
                rect.setPen(pg.mkPen((99, 102, 241), width=2, style=Qt.DashLine))
                rect.setBrush(pg.mkBrush(99, 102, 241, 30))
                self.addItem(rect)
                self._selection_roi = rect

            event.accept()
            return
            
        elif self._is_selecting and self.state.tool_mode == ToolMode.LASSO_SELECT:
            pos = self.plotItem.vb.mapSceneToView(event.position())
            
            # Add point to lasso path
            self._lasso_points.append((pos.x(), pos.y()))
            
            # Update lasso path visualization
            if self._lasso_path_item is not None:
                self.removeItem(self._lasso_path_item)
            
            if len(self._lasso_points) >= 2:
                # Create path
                from PySide6.QtGui import QPainterPath, QPolygonF
                from PySide6.QtCore import QPointF
                
                path = QPainterPath()
                path.moveTo(QPointF(self._lasso_points[0][0], self._lasso_points[0][1]))
                for px, py in self._lasso_points[1:]:
                    path.lineTo(QPointF(px, py))
                # Close path back to start
                path.lineTo(QPointF(self._lasso_points[0][0], self._lasso_points[0][1]))
                
                # Create graphics item
                path_item = pg.QtWidgets.QGraphicsPathItem(path)
                path_item.setPen(pg.mkPen((236, 72, 153), width=2))  # Pink color
                path_item.setBrush(pg.mkBrush(236, 72, 153, 30))
                self.addItem(path_item)
                self._lasso_path_item = path_item
            
            event.accept()
            return
        
        # Drawing mode preview
        elif self._is_drawing and self.state.tool_mode in [ToolMode.LINE_DRAW, 
                                                            ToolMode.CIRCLE_DRAW, 
                                                            ToolMode.RECT_DRAW]:
            pos = self.plotItem.vb.mapSceneToView(event.position())
            self._update_drawing_preview(pos.x(), pos.y())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release for selection"""
        if self._is_selecting and self.state.tool_mode == ToolMode.RECT_SELECT:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())

                if hasattr(self, '_rect_start_x'):
                    self._finish_rect_selection(pos)

                event.accept()
                return
                
        elif self._is_selecting and self.state.tool_mode == ToolMode.LASSO_SELECT:
            if event.button() == Qt.LeftButton:
                self._finish_lasso_selection()
                event.accept()
                return
        
        # Drawing mode finish
        elif self._is_drawing and self.state.tool_mode in [ToolMode.LINE_DRAW, 
                                                            ToolMode.CIRCLE_DRAW, 
                                                            ToolMode.RECT_DRAW]:
            if event.button() == Qt.LeftButton:
                pos = self.plotItem.vb.mapSceneToView(event.position())
                self._finish_drawing(pos.x(), pos.y())
                event.accept()
                return

        super().mouseReleaseEvent(event)
    
    def _finish_rect_selection(self, end_point):
        """Finish rectangle selection"""
        if self._data_x is None or self._data_y is None:
            self._cleanup_selection()
            return

        if not hasattr(self, '_rect_start_x'):
            self._cleanup_selection()
            return

        # Get bounds
        x1 = min(self._rect_start_x, end_point.x())
        x2 = max(self._rect_start_x, end_point.x())
        y1 = min(self._rect_start_y, end_point.y())
        y2 = max(self._rect_start_y, end_point.y())

        # Find points within rectangle
        selected_indices = []
        for i in range(len(self._data_x)):
            x, y = self._data_x[i], self._data_y[i]
            if x1 <= x <= x2 and y1 <= y <= y2:
                selected_indices.append(i)

        if selected_indices:
            self.points_selected.emit(selected_indices)
            self.state.select_rows(selected_indices)

        self._cleanup_selection()
    
    def _finish_lasso_selection(self):
        """Finish lasso selection - select points inside polygon"""
        if self._data_x is None or self._data_y is None:
            self._cleanup_lasso()
            return

        if len(self._lasso_points) < 3:
            self._cleanup_lasso()
            return

        # Use point-in-polygon algorithm
        selected_indices = []
        polygon = self._lasso_points
        
        for i in range(len(self._data_x)):
            x, y = self._data_x[i], self._data_y[i]
            if self._point_in_polygon(x, y, polygon):
                selected_indices.append(i)

        if selected_indices:
            self.points_selected.emit(selected_indices)
            self.state.select_rows(selected_indices)

        self._cleanup_lasso()
    
    def _point_in_polygon(self, x: float, y: float, polygon: list) -> bool:
        """Ray casting algorithm to check if point is inside polygon"""
        n = len(polygon)
        inside = False
        
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        
        return inside
    
    def _cleanup_selection(self):
        """Clean up rect selection state"""
        if self._selection_roi is not None:
            self.removeItem(self._selection_roi)
            self._selection_roi = None
        
        self._is_selecting = False
        self._selection_start = None
        if hasattr(self, '_rect_start_x'):
            del self._rect_start_x
        if hasattr(self, '_rect_start_y'):
            del self._rect_start_y
    
    def _cleanup_lasso(self):
        """Clean up lasso selection state"""
        if self._lasso_path_item is not None:
            self.removeItem(self._lasso_path_item)
            self._lasso_path_item = None
        
        self._lasso_points = []
        self._is_selecting = False
        self._selection_start = None

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

        # Normalized distance (handle NaN values)
        try:
            dx = (self._data_x - mx) / x_range
            dy = (self._data_y - my) / y_range
            distances = np.sqrt(dx**2 + dy**2)

            # Replace NaN distances with infinity so they're not selected
            distances = np.where(np.isnan(distances), np.inf, distances)

            if np.all(np.isinf(distances)):
                self._hide_tooltip()
                return

            nearest_idx = np.argmin(distances)
            min_dist = distances[nearest_idx]

            # Only show tooltip if close enough (within 5% of view range)
            if min_dist < 0.05 and not np.isinf(min_dist):
                self._show_tooltip(nearest_idx, self._data_x[nearest_idx], self._data_y[nearest_idx])
            else:
                self._hide_tooltip()
        except Exception:
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

    # ==================== Drawing Methods ====================

    def set_drawing_manager(self, manager: DrawingManager):
        """Set the drawing manager"""
        self._drawing_manager = manager

    def get_drawing_manager(self) -> Optional[DrawingManager]:
        """Get the drawing manager"""
        return self._drawing_manager

    def set_drawing_style(self, style: DrawingStyle):
        """Set the current drawing style"""
        self._current_drawing_style = style

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key_Shift:
            self._shift_pressed = True
        elif event.key() == Qt.Key_Delete:
            # Delete selected drawing
            if self._drawing_manager:
                self._drawing_manager.delete_selected()
        elif event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            # Undo
            if self._drawing_manager:
                self._drawing_manager.undo()
        elif event.key() == Qt.Key_Y and event.modifiers() & Qt.ControlModifier:
            # Redo
            if self._drawing_manager:
                self._drawing_manager.redo()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Handle key release events"""
        if event.key() == Qt.Key_Shift:
            self._shift_pressed = False
        super().keyReleaseEvent(event)

    def _update_drawing_preview(self, x: float, y: float):
        """Update drawing preview while dragging"""
        if not self._drawing_start:
            return

        x1, y1 = self._drawing_start
        x2, y2 = x, y

        # Apply Shift constraint
        if self._shift_pressed:
            if self.state.tool_mode == ToolMode.LINE_DRAW:
                # Snap to 45-degree angles
                x2, y2 = snap_to_angle(x1, y1, x2, y2, 45.0)
            elif self.state.tool_mode == ToolMode.CIRCLE_DRAW:
                # Make perfect circle
                radius = max(abs(x2 - x1), abs(y2 - y1))
                x2 = x1 + radius if x2 > x1 else x1 - radius
                y2 = y1 + radius if y2 > y1 else y1 - radius
            elif self.state.tool_mode == ToolMode.RECT_DRAW:
                # Make perfect square
                size = max(abs(x2 - x1), abs(y2 - y1))
                x2 = x1 + size if x2 > x1 else x1 - size
                y2 = y1 + size if y2 > y1 else y1 - size

        # Remove old preview
        if self._drawing_preview_item is not None:
            self.removeItem(self._drawing_preview_item)
            self._drawing_preview_item = None

        # Create preview based on tool mode
        style = self._current_drawing_style
        pen = pg.mkPen(
            color=style.stroke_color,
            width=style.stroke_width,
            style=style.line_style.to_qt()
        )

        if self.state.tool_mode == ToolMode.LINE_DRAW:
            # Line preview
            from PySide6.QtCore import QLineF
            line = pg.QtWidgets.QGraphicsLineItem(QLineF(x1, y1, x2, y2))
            line.setPen(pen)
            self.addItem(line)
            self._drawing_preview_item = line

        elif self.state.tool_mode == ToolMode.CIRCLE_DRAW:
            # Circle/ellipse preview
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            rx = abs(x2 - x1) / 2
            ry = abs(y2 - y1) / 2
            ellipse = pg.QtWidgets.QGraphicsEllipseItem(
                cx - rx, cy - ry, rx * 2, ry * 2
            )
            ellipse.setPen(pen)
            if style.fill_color:
                fill = QColor(style.fill_color)
                fill.setAlphaF(style.fill_opacity)
                ellipse.setBrush(QBrush(fill))
            self.addItem(ellipse)
            self._drawing_preview_item = ellipse

        elif self.state.tool_mode == ToolMode.RECT_DRAW:
            # Rectangle preview
            rect_x = min(x1, x2)
            rect_y = min(y1, y2)
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            rect = pg.QtWidgets.QGraphicsRectItem(rect_x, rect_y, width, height)
            rect.setPen(pen)
            if style.fill_color:
                fill = QColor(style.fill_color)
                fill.setAlphaF(style.fill_opacity)
                rect.setBrush(QBrush(fill))
            self.addItem(rect)
            self._drawing_preview_item = rect

    def _finish_drawing(self, x: float, y: float):
        """Finish drawing and create the object"""
        if not self._drawing_start or not self._drawing_manager:
            self._cleanup_drawing()
            return

        x1, y1 = self._drawing_start
        x2, y2 = x, y

        # Apply Shift constraint
        if self._shift_pressed:
            if self.state.tool_mode == ToolMode.LINE_DRAW:
                x2, y2 = snap_to_angle(x1, y1, x2, y2, 45.0)
            elif self.state.tool_mode == ToolMode.CIRCLE_DRAW:
                radius = max(abs(x2 - x1), abs(y2 - y1))
                x2 = x1 + radius if x2 > x1 else x1 - radius
                y2 = y1 + radius if y2 > y1 else y1 - radius
            elif self.state.tool_mode == ToolMode.RECT_DRAW:
                size = max(abs(x2 - x1), abs(y2 - y1))
                x2 = x1 + size if x2 > x1 else x1 - size
                y2 = y1 + size if y2 > y1 else y1 - size

        # Create drawing object
        style = DrawingStyle(
            stroke_color=self._current_drawing_style.stroke_color,
            stroke_width=self._current_drawing_style.stroke_width,
            line_style=self._current_drawing_style.line_style,
            fill_color=self._current_drawing_style.fill_color,
            fill_opacity=self._current_drawing_style.fill_opacity,
        )

        drawing = None

        if self.state.tool_mode == ToolMode.LINE_DRAW:
            drawing = LineDrawing(
                x1=x1, y1=y1, x2=x2, y2=y2,
                style=style
            )
        elif self.state.tool_mode == ToolMode.CIRCLE_DRAW:
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            rx = abs(x2 - x1) / 2
            ry = abs(y2 - y1) / 2
            drawing = CircleDrawing(
                cx=cx, cy=cy, rx=rx, ry=ry,
                style=style
            )
        elif self.state.tool_mode == ToolMode.RECT_DRAW:
            rect_x = min(x1, x2)
            rect_y = min(y1, y2)
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            drawing = RectDrawing(
                x=rect_x, y=rect_y, width=width, height=height,
                style=style
            )

        if drawing:
            self._drawing_manager.add_drawing(drawing)

        self._cleanup_drawing()

    def _handle_text_draw(self, x: float, y: float):
        """Handle text drawing - show dialog"""
        if not self._drawing_manager:
            return

        dialog = TextInputDialog(self)
        if dialog.exec() == QDialog.Accepted:
            text_drawing = dialog.get_text_drawing(x, y)
            self._drawing_manager.add_drawing(text_drawing)

    def _cleanup_drawing(self):
        """Clean up drawing state"""
        if self._drawing_preview_item is not None:
            self.removeItem(self._drawing_preview_item)
            self._drawing_preview_item = None

        self._is_drawing = False
        self._drawing_start = None


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

        # Splitter sizes: Options(280) + Graph(stretch) + Stats(360) - Stats doubled
        self.splitter.setSizes([280, 500, 360])
        self.splitter.setStretchFactor(0, 0)  # Options: fixed
        self.splitter.setStretchFactor(1, 1)  # Graph: stretch
        self.splitter.setStretchFactor(2, 0)  # Stats: fixed (2x width)

        layout.addWidget(self.splitter)

        # Initialize DrawingManager
        self._drawing_manager = DrawingManager(self.main_graph)
        self.main_graph.set_drawing_manager(self._drawing_manager)
    
    def _connect_signals(self):
        self.state.chart_settings_changed.connect(self.refresh)
        self.state.group_zone_changed.connect(self._on_group_changed)
        self.state.value_zone_changed.connect(self.refresh)
        self.state.hover_zone_changed.connect(self.refresh)
        self.state.selection_changed.connect(self._on_selection_changed)
        self.options_panel.option_changed.connect(self.refresh)

        # Connect graph selection to state
        self.main_graph.points_selected.connect(self._on_graph_points_selected)

        # Connect sliding window signals
        self.x_sliding_window.range_changed.connect(self._on_x_window_changed)
        self.y_sliding_window.range_changed.connect(self._on_y_window_changed)

        # Connect view range changes to update sliding windows
        self.main_graph.plotItem.sigRangeChanged.connect(self._on_graph_range_changed)

    def _on_graph_points_selected(self, indices: list):
        """Handle selection from graph (rect select, lasso select)"""
        if indices:
            self.state.select_rows(indices)

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

        # Check if we're in overlay comparison mode
        if (self.state.comparison_mode == ComparisonMode.OVERLAY and
                len(self.state.comparison_dataset_ids) >= 2):
            self._refresh_overlay_comparison()
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
        x_categorical_labels = None
        x_is_categorical = False

        if not x_col:
            x_data = np.arange(self.engine.row_count)
            options['x_title'] = options.get('x_title') or 'Index'
        else:
            # Check if X column is categorical
            x_is_categorical = self.engine.is_column_categorical(x_col)

            if x_is_categorical:
                # Get unique values as labels
                x_categorical_labels = self.engine.get_unique_values(x_col, limit=500)
                # Map values to indices
                value_to_idx = {v: i for i, v in enumerate(x_categorical_labels)}
                x_raw = self.engine.df[x_col].to_list()
                x_data = np.array([value_to_idx.get(v, 0) for v in x_raw], dtype=np.float64)
            else:
                x_data = self.engine.df[x_col].to_numpy()

            options['x_title'] = options.get('x_title') or x_col

        # Coerce non-numeric X data (e.g., datetime strings) to numeric for plotting
        if not x_is_categorical and x_data is not None and len(x_data) > 0:
            try:
                if getattr(x_data, "dtype", None) is not None and x_data.dtype.kind in ("U", "S", "O"):
                    s = pl.Series("x", x_data)
                    parsed = s.str.strptime(pl.Datetime, strict=False)
                    if parsed.null_count() < len(parsed):
                        x_data = parsed.dt.timestamp("ms").to_numpy()
                        options['x_format'] = options.get('x_format') or 'time'
                    else:
                        # Fallback: treat as categorical
                        x_categorical_labels = self.engine.get_unique_values(x_col, limit=500) if x_col else list(dict.fromkeys(x_data))[:500]
                        value_to_idx = {v: i for i, v in enumerate(x_categorical_labels)}
                        x_data = np.array([value_to_idx.get(v, 0) for v in x_data], dtype=np.float64)
                        x_is_categorical = True
                        self._x_axis.set_categorical(x_categorical_labels)
            except Exception:
                pass

        # Y column
        y_formula = ""
        y_categorical_labels = None
        y_is_categorical = False

        if self.state.value_columns:
            value_col = self.state.value_columns[0]
            y_col_name = value_col.name
            y_formula = value_col.formula or ""
        else:
            numeric_cols = [
                col for col in self.engine.columns
                if self.engine.dtypes.get(col, '').startswith(('Int', 'Float'))
            ]
            if numeric_cols:
                y_col_name = numeric_cols[0]
            else:
                # If no numeric columns, try any column (might be categorical)
                if self.engine.columns:
                    y_col_name = self.engine.columns[0]
                else:
                    return

        # Check if Y column is categorical
        y_is_categorical = self.engine.is_column_categorical(y_col_name)

        if y_is_categorical:
            # Get unique values as labels
            y_categorical_labels = self.engine.get_unique_values(y_col_name, limit=500)
            # Map values to indices
            value_to_idx = {v: i for i, v in enumerate(y_categorical_labels)}
            y_raw = self.engine.df[y_col_name].to_list()
            y_data = np.array([value_to_idx.get(v, 0) for v in y_raw], dtype=np.float64)
        else:
            y_data = self.engine.df[y_col_name].to_numpy()

        # Apply Y formula if specified
        if y_formula and not y_is_categorical:
            y_data = self._apply_y_formula(y_data, y_formula, y_col_name)
            # Update title to show formula
            if y_formula:
                options['y_title'] = options.get('y_title') or f"{y_col_name} [{y_formula}]"
        else:
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

        # Sampling logic - skip for categorical data or small datasets
        is_sampled = False
        algorithm_used = ""

        # Helper function to apply sampling algorithm
        def _apply_sampling(x_arr, y_arr, n_points, algo):
            """Apply sampling algorithm to data arrays"""
            if algo == 'auto':
                return DataSampler.auto_sample(x_arr, y_arr, max_points=n_points)
            elif algo == 'lttb':
                return DataSampler.lttb(x_arr, y_arr, threshold=n_points)
            elif algo == 'minmax':
                return DataSampler.min_max_per_bucket(x_arr, y_arr, n_buckets=max(1, n_points // 2))
            elif algo == 'random':
                return DataSampler.random_sample(x_arr, y_arr, n_samples=n_points)
            else:
                return DataSampler.auto_sample(x_arr, y_arr, max_points=n_points)

        # Don't sample categorical data
        if x_is_categorical or y_is_categorical:
            x_sampled, y_sampled = x_data, y_data
        elif show_all_data:
            # Show all data - no sampling
            x_sampled, y_sampled = x_data, y_data
        elif total_points > max_points:
            # Apply sampling
            try:
                valid_mask = ~(np.isnan(x_data.astype(float)) | np.isnan(y_data.astype(float)))
                x_valid = x_data[valid_mask].astype(np.float64)
                y_valid = y_data[valid_mask].astype(np.float64)

                if len(x_valid) > max_points:
                    is_sampled = True

                    # Group-aware sampling: sample each group separately to preserve group structure
                    if groups is not None and len(groups) > 0:
                        # Calculate points per group (proportional to group size)
                        group_sizes = {name: np.sum(mask[valid_mask]) for name, mask in groups.items()}
                        total_valid = sum(group_sizes.values())
                        
                        # Ensure minimum points per group (at least 10 or 1% of max_points)
                        min_points_per_group = max(10, max_points // 100)
                        
                        x_sampled_list = []
                        y_sampled_list = []
                        new_groups = {}
                        current_offset = 0
                        
                        for group_name, mask in groups.items():
                            # Get valid data for this group
                            group_valid_mask = mask[valid_mask]
                            x_group = x_valid[group_valid_mask]
                            y_group = y_valid[group_valid_mask]
                            
                            if len(x_group) == 0:
                                continue
                            
                            # Calculate proportional points for this group
                            group_ratio = len(x_group) / total_valid if total_valid > 0 else 0
                            group_points = max(min_points_per_group, int(max_points * group_ratio))
                            
                            # Apply sampling if group has more points than allocated
                            if len(x_group) > group_points:
                                x_group_sampled, y_group_sampled = _apply_sampling(
                                    x_group, y_group, group_points, sampling_algorithm
                                )
                            else:
                                x_group_sampled, y_group_sampled = x_group, y_group
                            
                            # Create new group mask for sampled data
                            group_len = len(x_group_sampled)
                            new_mask = np.zeros(0, dtype=bool)  # Will be resized later
                            
                            x_sampled_list.append(x_group_sampled)
                            y_sampled_list.append(y_group_sampled)
                            new_groups[group_name] = (current_offset, group_len)
                            current_offset += group_len
                        
                        # Concatenate all sampled data
                        if x_sampled_list:
                            x_sampled = np.concatenate(x_sampled_list)
                            y_sampled = np.concatenate(y_sampled_list)
                            
                            # Build new group masks for concatenated data
                            total_sampled = len(x_sampled)
                            groups = {}
                            for group_name, (offset, length) in new_groups.items():
                                mask = np.zeros(total_sampled, dtype=bool)
                                mask[offset:offset + length] = True
                                groups[group_name] = mask
                        else:
                            x_sampled, y_sampled = x_valid, y_valid
                    else:
                        # No groups - sample entire dataset
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
                    
                    # Set algorithm used for display
                    if not algorithm_used:
                        if sampling_algorithm == 'auto':
                            is_sorted = np.all(x_valid[:-1] <= x_valid[1:])
                            algorithm_used = "LTTB" if is_sorted else "Min-Max"
                        else:
                            algorithm_used = sampling_algorithm.upper()
                else:
                    x_sampled, y_sampled = x_valid, y_valid
            except (ValueError, TypeError):
                # Fallback if sampling fails
                x_sampled, y_sampled = x_data, y_data
        else:
            x_sampled, y_sampled = x_data, y_data

        # Plot data with categorical labels
        self.main_graph.plot_data(
            x_sampled, y_sampled,
            groups=groups,
            chart_type=options.get('chart_type', ChartType.LINE),
            options=options,
            legend_settings=legend_settings,
            x_categorical_labels=x_categorical_labels,
            y_categorical_labels=y_categorical_labels
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

        # Update stats - compute group aggregation for pie chart
        group_data = None
        if groups is not None and len(groups) > 0:
            # Calculate sum of Y values for each group for pie chart
            try:
                group_data = {}
                for group_name, mask in groups.items():
                    group_y = y_sampled[mask]
                    clean_y = group_y[~np.isnan(group_y)]
                    if len(clean_y) > 0:
                        group_data[group_name] = float(np.sum(clean_y))
                    else:
                        group_data[group_name] = 0.0
            except Exception:
                group_data = None

        self.stat_panel.update_histograms(x_sampled, y_sampled, group_data)
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
            if x_window_enabled and not x_is_categorical:
                try:
                    self.x_sliding_window.set_data(x_data.astype(float) if hasattr(x_data, 'astype') else np.array(x_data, dtype=float))
                except (ValueError, TypeError):
                    pass
            if y_window_enabled and not y_is_categorical:
                try:
                    self.y_sliding_window.set_data(y_data.astype(float) if hasattr(y_data, 'astype') else np.array(y_data, dtype=float))
                except (ValueError, TypeError):
                    pass

    def _apply_y_formula(self, y_data: np.ndarray, formula: str, col_name: str) -> np.ndarray:
        """Apply formula transformation to Y data

        Args:
            y_data: Original Y data as numpy array
            formula: Formula string (e.g., "y*2", "LOG(y)", "y+100")
            col_name: Original column name

        Returns:
            Transformed Y data
        """
        if not formula or not formula.strip():
            return y_data

        try:
            # Create expression engine
            expr_engine = ExpressionEngine()

            # Replace 'y' in formula with column reference
            # Support both 'y' and 'Y' as references
            adjusted_formula = formula.replace('Y', col_name).replace('y', col_name)

            # Create a temporary DataFrame with the Y data
            temp_df = pl.DataFrame({col_name: y_data.tolist()})

            # Evaluate formula
            result_series = expr_engine.evaluate(adjusted_formula, temp_df)

            # Convert back to numpy array
            return result_series.to_numpy()

        except ExpressionError as e:
            print(f"Formula error: {e}")
            return y_data
        except Exception as e:
            print(f"Error applying formula '{formula}': {e}")
            return y_data

    def _refresh_overlay_comparison(self):
        """
        Overlay comparison mode - render multiple datasets on the same chart.

        각 데이터셋을 고유한 색상으로 같은 차트에 오버레이하여 표시
        """
        options = self.options_panel.get_chart_options()
        legend_settings = self.options_panel.get_legend_settings()
        max_points = options.get('max_points', 10000)

        # Clear existing plot
        self.main_graph.clear_plot()

        # Get comparison datasets
        dataset_ids = self.state.comparison_dataset_ids
        colors = self.state.get_comparison_colors()

        # X column
        x_col = self.state.x_column

        all_series_data = []
        total_points = 0

        for dataset_id in dataset_ids:
            dataset = self.engine.get_dataset(dataset_id)
            if not dataset or not dataset.df:
                continue

            metadata = self.state.get_dataset_metadata(dataset_id)
            color = metadata.color if metadata else colors.get(dataset_id, '#1f77b4')
            name = metadata.name if metadata else dataset_id

            df = dataset.df

            # Get X data
            if not x_col or x_col not in df.columns:
                x_data = np.arange(len(df))
            else:
                x_data = df[x_col].to_numpy()

            # Get Y data - use first value column or first numeric column
            y_col_name = None
            if self.state.value_columns:
                y_col_name = self.state.value_columns[0].name
                if y_col_name not in df.columns:
                    y_col_name = None

            if not y_col_name:
                # Find first numeric column
                for col in df.columns:
                    dtype = str(df[col].dtype)
                    if dtype.startswith(('Int', 'Float', 'UInt')):
                        y_col_name = col
                        break

            if not y_col_name:
                continue

            y_data = df[y_col_name].to_numpy()

            # Apply sampling if needed
            if len(x_data) > max_points:
                try:
                    valid_mask = ~(np.isnan(x_data.astype(float)) | np.isnan(y_data.astype(float)))
                    x_valid = x_data[valid_mask].astype(np.float64)
                    y_valid = y_data[valid_mask].astype(np.float64)

                    if len(x_valid) > max_points:
                        x_sampled, y_sampled = DataSampler.auto_sample(
                            x_valid, y_valid, max_points=max_points
                        )
                    else:
                        x_sampled, y_sampled = x_valid, y_valid
                except (ValueError, TypeError):
                    x_sampled, y_sampled = x_data, y_data
            else:
                x_sampled, y_sampled = x_data, y_data

            total_points += len(x_sampled)

            all_series_data.append({
                'x': x_sampled,
                'y': y_sampled,
                'name': name,
                'color': color,
                'dataset_id': dataset_id
            })

        # Plot all series
        if all_series_data:
            self.main_graph.plot_multi_series(
                all_series_data,
                chart_type=options.get('chart_type', ChartType.LINE),
                options=options,
                legend_settings=legend_settings
            )

            # Update sampling status
            self.main_graph.update_sampling_status(
                displayed_points=total_points,
                total_points=sum(len(self.engine.get_dataset(did).df)
                               for did in dataset_ids
                               if self.engine.get_dataset(did) and self.engine.get_dataset(did).df is not None),
                is_sampled=total_points < sum(len(self.engine.get_dataset(did).df)
                                            for did in dataset_ids
                                            if self.engine.get_dataset(did) and self.engine.get_dataset(did).df is not None),
                algorithm="Multi-Dataset"
            )

            # Update options panel with series names
            series_names = [s['name'] for s in all_series_data]
            self.options_panel.set_series(series_names)

    def _on_selection_changed(self):
        """Handle selection state change - highlight selected points and update stats"""
        selected_rows = list(self.state.selection.selected_rows)
        
        # Update graph highlight
        self.main_graph.highlight_selection(selected_rows)
        
        # Update stat panel with selected data statistics
        if selected_rows and self.engine.is_loaded:
            self._update_stats_for_selection(selected_rows)
        else:
            # Show stats for all data
            if self.state.value_columns and self.engine.is_loaded:
                stats = self.engine.get_statistics(self.state.value_columns[0].name)
                self.stat_panel.update_stats(stats)

    def _update_stats_for_selection(self, selected_rows: list):
        """Update stat panel with statistics for selected rows only"""
        if not self.engine.is_loaded or not selected_rows:
            return
        
        try:
            # Get selected data
            df = self.engine.df
            if df is None:
                return
            
            # Filter to selected rows
            selected_indices = [i for i in selected_rows if 0 <= i < len(df)]
            if not selected_indices:
                return
            
            # Get Y column name - try value_columns first, then any numeric column
            y_col_name = None
            if self.state.value_columns:
                y_col_name = self.state.value_columns[0].name
            
            if not y_col_name or y_col_name not in df.columns:
                # Find first numeric column
                for col in self.engine.columns:
                    dtype = self.engine.dtypes.get(col, '')
                    if dtype.startswith(('Int', 'Float', 'UInt')):
                        y_col_name = col
                        break
            
            if not y_col_name or y_col_name not in df.columns:
                # Still no column found - show basic stats
                stats = {
                    'Selected': len(selected_rows),
                    'Total': len(df),
                }
                self.stat_panel.update_stats(stats)
                return
            
            # Get selected data for Y column
            y_data = df[y_col_name].to_numpy()
            selected_y = y_data[selected_indices]
            
            # Calculate statistics for selection
            clean_y = selected_y[~np.isnan(selected_y.astype(float))]
            if len(clean_y) == 0:
                return
            
            stats = {
                'Selected': len(selected_rows),
                'Mean': float(np.mean(clean_y)),
                'Median': float(np.median(clean_y)),
                'Std': float(np.std(clean_y)),
                'Min': float(np.min(clean_y)),
                'Max': float(np.max(clean_y)),
            }
            
            self.stat_panel.update_stats(stats)
            
            # Update histograms with selected data
            x_col = self.state.x_column
            if x_col and x_col in df.columns:
                x_data = df[x_col].to_numpy()
                selected_x = x_data[selected_indices]
            else:
                selected_x = np.array(selected_indices)
            
            self.stat_panel.update_histograms(selected_x, selected_y)
            
        except Exception as e:
            print(f"Error updating stats for selection: {e}")
    
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

    def get_chart_options(self) -> Dict[str, Any]:
        """Get current chart options from the options panel"""
        return self.options_panel.get_chart_options()

    def get_legend_settings(self) -> Dict[str, Any]:
        """Get current legend settings from the options panel"""
        return self.options_panel.get_legend_settings()

    def apply_options(self, options: Dict[str, Any]):
        """Apply chart options to the options panel"""
        if not options:
            return

        # Apply chart title
        if 'title' in options and options['title']:
            self.options_panel.chart_title_edit.setText(options['title'])
        if 'subtitle' in options and options['subtitle']:
            self.options_panel.chart_subtitle_edit.setText(options['subtitle'])

        # Apply X-axis options
        if 'x_title' in options and options['x_title']:
            self.options_panel.x_title_edit.setText(options['x_title'])
        if 'x_format' in options:
            x_format = options['x_format']
            if x_format:
                # Find matching preset or set custom
                format_map = {
                    'number': "Number (#,##0)",
                    'decimal': "Decimal (#,##0.00)",
                    'scientific': "Scientific (0.00E+00)",
                    'percent': "Percent (0.0%)",
                    'k': "K (#,##0,\"K\")",
                    'm': "M (#,##0,,\"M\")",
                    'b': "B (#,##0,,,\"B\")",
                    'bytes': "KB/MB/GB",
                    'time': "ms/s/min",
                }
                if x_format in format_map:
                    idx = self.options_panel.x_format_combo.findText(format_map[x_format])
                    if idx >= 0:
                        self.options_panel.x_format_combo.setCurrentIndex(idx)
                else:
                    self.options_panel.x_format_combo.setCurrentText(x_format)
            else:
                self.options_panel.x_format_combo.setCurrentIndex(0)  # Auto

        if 'x_log' in options:
            self.options_panel.x_log_check.setChecked(options['x_log'])
        if 'x_reverse' in options:
            self.options_panel.x_reverse_check.setChecked(options['x_reverse'])

        # Apply Y-axis options
        if 'y_title' in options and options['y_title']:
            self.options_panel.y_title_edit.setText(options['y_title'])
        if 'y_format' in options:
            y_format = options['y_format']
            if y_format:
                format_map = {
                    'number': "Number (#,##0)",
                    'decimal': "Decimal (#,##0.00)",
                    'scientific': "Scientific (0.00E+00)",
                    'percent': "Percent (0.0%)",
                    'k': "K (#,##0,\"K\")",
                    'm': "M (#,##0,,\"M\")",
                    'b': "B (#,##0,,,\"B\")",
                    'bytes': "KB/MB/GB",
                    'time': "ms/s/min",
                }
                if y_format in format_map:
                    idx = self.options_panel.y_format_combo.findText(format_map[y_format])
                    if idx >= 0:
                        self.options_panel.y_format_combo.setCurrentIndex(idx)
                else:
                    self.options_panel.y_format_combo.setCurrentText(y_format)
            else:
                self.options_panel.y_format_combo.setCurrentIndex(0)  # Auto

        if 'y_min' in options and options['y_min'] is not None:
            self.options_panel.y_min_spin.setValue(options['y_min'])
        if 'y_max' in options and options['y_max'] is not None:
            self.options_panel.y_max_spin.setValue(options['y_max'])
        if 'y_log' in options:
            self.options_panel.y_log_check.setChecked(options['y_log'])
        if 'y_reverse' in options:
            self.options_panel.y_reverse_check.setChecked(options['y_reverse'])

        # Apply grid options
        if 'grid_x' in options:
            self.options_panel.grid_x_check.setChecked(options['grid_x'])
        if 'grid_y' in options:
            self.options_panel.grid_y_check.setChecked(options['grid_y'])
        if 'grid_opacity' in options:
            self.options_panel.grid_opacity_slider.setValue(int(options['grid_opacity'] * 100))

        # Apply style options
        if 'show_labels' in options:
            self.options_panel.show_labels_check.setChecked(options['show_labels'])
        if 'show_points' in options:
            self.options_panel.show_points_check.setChecked(options['show_points'])
        if 'smooth' in options:
            self.options_panel.smooth_check.setChecked(options['smooth'])
        if 'line_width' in options:
            self.options_panel.line_width_spin.setValue(options['line_width'])
        if 'marker_size' in options:
            self.options_panel.marker_size_spin.setValue(options['marker_size'])
        if 'fill_opacity' in options:
            self.options_panel.fill_opacity_spin.setValue(options['fill_opacity'])

        # Apply background color
        if 'bg_color' in options and options['bg_color']:
            from PySide6.QtGui import QColor
            if isinstance(options['bg_color'], str):
                self.options_panel.bg_color_btn.set_color(QColor(options['bg_color']))

        # Apply sampling options
        if 'show_all_data' in options:
            self.options_panel.show_all_data_check.setChecked(options['show_all_data'])
        if 'max_points' in options:
            self.options_panel.max_points_slider.setValue(options['max_points'] // 1000)

        # Apply sliding window options
        if 'sliding_window_enabled' in options:
            self.options_panel.sliding_window_check.setChecked(options['sliding_window_enabled'])
        if 'x_sliding_window' in options:
            self.options_panel.x_sliding_window_check.setChecked(options['x_sliding_window'])
        if 'y_sliding_window' in options:
            self.options_panel.y_sliding_window_check.setChecked(options['y_sliding_window'])

    # ==================== Drawing Methods ====================

    def get_drawing_manager(self) -> DrawingManager:
        """Get the drawing manager"""
        return self._drawing_manager

    def set_drawing_style(self, style: DrawingStyle):
        """Set the current drawing style for new drawings"""
        self._drawing_manager.current_style = style
        self.main_graph.set_drawing_style(style)

    def get_drawings_data(self) -> Dict[str, Any]:
        """Get all drawings as serializable dict (for saving)"""
        return self._drawing_manager.to_dict()

    def load_drawings_data(self, data: Dict[str, Any]):
        """Load drawings from serialized dict"""
        self._drawing_manager.from_dict(data)

    def clear_drawings(self):
        """Clear all drawings"""
        self._drawing_manager.clear()

    def undo_drawing(self) -> bool:
        """Undo last drawing action"""
        return self._drawing_manager.undo()

    def redo_drawing(self) -> bool:
        """Redo last undone action"""
        return self._drawing_manager.redo()

    def delete_selected_drawing(self) -> bool:
        """Delete the currently selected drawing"""
        return self._drawing_manager.delete_selected()

    def show_drawing_style_dialog(self):
        """Show dialog to configure drawing style"""
        dialog = DrawingStyleDialog("Drawing Style", self)
        dialog.set_style(self._drawing_manager.current_style)
        if dialog.exec() == QDialog.Accepted:
            style = dialog.get_style()
            self.set_drawing_style(style)
