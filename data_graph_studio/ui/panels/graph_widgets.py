"""
Graph Widgets - Helper classes for graph panel
"""

import numpy as np
from PySide6.QtWidgets import (
    QPushButton, QDialog, QVBoxLayout, QDialogButtonBox, QColorDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent

import pyqtgraph as pg


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
                border: 2px solid #3E4A59;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: #59B8E3;
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
        self.setModal(False)
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
                    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
                    bar_height = (bin_edges[1] - bin_edges[0]) * 0.8 if len(bin_edges) > 1 else 0.8

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

                    mean_val = np.mean(clean_data)
                    self.plot_widget.addLine(y=mean_val, pen=pg.mkPen('r', width=2, style=Qt.DashLine))

                    stats_text = f"Mean: {mean_val:.2f}\nMedian: {np.median(clean_data):.2f}\nStd: {np.std(clean_data):.2f}"
                    text_item = pg.TextItem(stats_text, anchor=(0, 1), color='k')
                    text_item.setPos(max(hist) * 0.1, bin_edges[-1])
                    self.plot_widget.addItem(text_item)
                else:
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
        """Plot pie chart"""
        self.setWindowTitle(title)
        self.plot_widget.clear()

        if not labels or not values:
            return

        try:
            total = sum(values)
            if total == 0:
                return

            if colors is None:
                default_colors = [
                    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
                ]
                colors = [default_colors[i % len(default_colors)] for i in range(len(labels))]

            try:
                from pyqtgraph.graphicsItems.PieChartItem import PieChartItem
                pie = PieChartItem(values, brushes=[pg.mkBrush(c) for c in colors])
                pie.setZValue(10)
                self.plot_widget.addItem(pie)
                self.plot_widget.setAspectLocked(True)
                self.plot_widget.hideAxis('bottom')
                self.plot_widget.hideAxis('left')
            except Exception:
                x_positions = np.arange(len(labels))
                bars = pg.BarGraphItem(
                    x=x_positions,
                    height=values,
                    width=0.6,
                    brushes=[pg.mkBrush(c) for c in colors],
                    pens=[pg.mkPen(c, width=1) for c in colors]
                )
                self.plot_widget.addItem(bars)
                # Set X-axis labels to group names
                ax = self.plot_widget.getAxis('bottom')
                ticks = [(i, str(lbl)) for i, lbl in enumerate(labels)]
                ax.setTicks([ticks])

            y0 = 0
            for i, (label, val) in enumerate(zip(labels, values)):
                pct = (val / total) * 100
                text = pg.TextItem(f"{label}: {pct:.1f}%", anchor=(0, 0), color='#E6E9EF')
                text.setPos(0, y0)
                text.setZValue(20)
                self.plot_widget.addItem(text)
                y0 -= (total * 0.01)

        except Exception as e:
            print(f"Error plotting pie chart: {e}")

    def plot_percentile(self, data: np.ndarray, title: str, color: tuple = (100, 100, 200)):
        """Plot percentile graph"""
        self.setWindowTitle(title)
        self.plot_widget.clear()

        if data is None or len(data) == 0:
            return

        try:
            clean_data = data[~np.isnan(data)]
            if len(clean_data) == 0:
                return

            percentiles = np.array([0, 1, 2, 3, 4, 5, 10, 25, 50, 75, 90, 95, 97, 99, 99.7, 99.9, 99.99, 100])
            percentile_values = np.percentile(clean_data, percentiles)

            pen = pg.mkPen(color=color[:3], width=2)
            self.plot_widget.plot(percentiles, percentile_values, pen=pen)

            key_percentiles = [25, 50, 75, 90, 95, 99]
            key_values = np.percentile(clean_data, key_percentiles)

            scatter = pg.ScatterPlotItem(
                x=key_percentiles,
                y=key_values,
                size=8,
                brush=pg.mkBrush('#EF4444'),
                pen=pg.mkPen('w', width=1)
            )
            self.plot_widget.addItem(scatter)

            self.plot_widget.setLabel('bottom', 'Percentile')
            self.plot_widget.setLabel('left', 'Value')

            stats_text = "\n".join([f"P{p}: {v:.2f}" for p, v in zip(key_percentiles, key_values)])
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
        self._bins = 30
        self._horizontal = False
        self._chart_type = "histogram"
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
        self._pie_labels = labels
        self._pie_values = values
        self._title = title
        self._pie_colors = colors
        self._chart_type = "pie"

    def set_percentile_data(self, data: np.ndarray, title: str, color: tuple = (100, 100, 200)):
        self._data = data
        self._title = title
        self._color = color
        self._chart_type = "percentile"

    def set_bins(self, bins: int):
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

        dialog.show()


class FormattedAxisItem(pg.AxisItem):
    """Custom axis item with value formatting"""

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
        self.custom_format = None
        self._categorical_labels = None
        self._is_categorical = False

    def set_format(self, format_type):
        self.format_type = format_type
        if format_type and format_type not in self.PRESET_FORMATS and format_type != 'auto':
            self.custom_format = format_type
        else:
            self.custom_format = None

    def set_categorical(self, labels: list):
        self._categorical_labels = labels
        self._is_categorical = True if labels else False

    def clear_categorical(self):
        self._categorical_labels = None
        self._is_categorical = False

    def tickStrings(self, values, scale, spacing):
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
        if value is None or (isinstance(value, float) and (value != value)):
            return ""

        try:
            if self.custom_format:
                return self._apply_excel_format(value, self.custom_format)

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
                if abs(value) >= 1_073_741_824:
                    return f"{value/1_073_741_824:.1f}GB"
                elif abs(value) >= 1_048_576:
                    return f"{value/1_048_576:.1f}MB"
                elif abs(value) >= 1024:
                    return f"{value/1024:.1f}KB"
                return f"{value:.0f}B"
            elif self.format_type == 'time':
                if abs(value) >= 60000:
                    return f"{value/60000:.1f}min"
                elif abs(value) >= 1000:
                    return f"{value/1000:.1f}s"
                return f"{value:.0f}ms"
            else:
                return f"{value:.2f}"
        except (ValueError, TypeError):
            return str(value)

    def _apply_excel_format(self, value, fmt: str) -> str:
        try:
            if fmt.endswith('%'):
                decimal_part = fmt[:-1]
                if '.' in decimal_part:
                    decimals = len(decimal_part.split('.')[-1])
                else:
                    decimals = 0
                return f"{value * 100:.{decimals}f}%"

            if 'E' in fmt.upper():
                if '.' in fmt:
                    decimals = len(fmt.split('.')[1].split('E')[0].split('e')[0])
                else:
                    decimals = 2
                return f"{value:.{decimals}e}"

            divisor = 1
            suffix = ""
            temp_fmt = fmt

            while temp_fmt.endswith(','):
                divisor *= 1000
                temp_fmt = temp_fmt[:-1]

            if '"' in temp_fmt:
                import re
                suffix_match = re.search(r'"([^"]*)"$', temp_fmt)
                if suffix_match:
                    suffix = suffix_match.group(1)
                    temp_fmt = temp_fmt[:suffix_match.start()]

            prefix = ""
            if '"' in temp_fmt:
                import re
                prefix_match = re.search(r'^"([^"]*)"', temp_fmt)
                if prefix_match:
                    prefix = prefix_match.group(1)
                    temp_fmt = temp_fmt[prefix_match.end():]

            adjusted_value = value / divisor if divisor > 1 else value

            if '.' in temp_fmt:
                decimal_part = temp_fmt.split('.')[-1]
                decimal_part = ''.join(c for c in decimal_part if c in '0#')
                decimals = len(decimal_part)
            else:
                decimals = 0

            use_thousands = '#,##' in temp_fmt or '0,00' in temp_fmt or ',##0' in temp_fmt

            if use_thousands:
                result = f"{adjusted_value:,.{decimals}f}"
            else:
                result = f"{adjusted_value:.{decimals}f}"

            return f"{prefix}{result}{suffix}"

        except Exception:
            return f"{value:.2f}"
