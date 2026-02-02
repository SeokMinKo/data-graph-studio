"""
Sliding Window Widget - 데이터 범위 탐색용 미니맵
"""

import numpy as np
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont


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
                background: #2B3440;
                border: 1px solid #3E4A59;
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
        norm = (value - self._data_min) / data_range
        # Vertical axis: invert so min at bottom, max at top
        if self.orientation == 'vertical':
            return 1.0 - norm
        return norm

    def _pos_to_value(self, pos: float) -> float:
        """Convert widget position (0-1 normalized) to data value"""
        if self.orientation == 'vertical':
            pos = 1.0 - pos
        return self._data_min + pos * (self._data_max - self._data_min)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        margin = 4

        if self.orientation == 'horizontal':
            plot_rect = rect.adjusted(margin, margin + 15, -margin, -margin)
        else:
            plot_rect = rect.adjusted(margin + 15, margin, -margin, -margin)

        # Background
        painter.fillRect(plot_rect, QColor('#323D4A'))
        painter.setPen(QPen(QColor('#3E4A59'), 1))
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
                    y = plot_rect.bottom() - (i + 1) * bar_height
                    painter.drawRect(int(x), int(y), int(bar_width), int(bar_height - 1))
        except Exception:
            pass

    def _draw_window_region(self, painter, plot_rect):
        """Draw the sliding window region"""
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
            painter.setPen(QPen(QColor('#59B8E3'), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(x1), plot_rect.top(), int(x2 - x1), plot_rect.height())

            # Draw handles
            handle_width = 6
            painter.fillRect(int(x1 - handle_width // 2), plot_rect.top(),
                            handle_width, plot_rect.height(), QColor('#59B8E3'))
            painter.fillRect(int(x2 - handle_width // 2), plot_rect.top(),
                            handle_width, plot_rect.height(), QColor('#59B8E3'))
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
            painter.setPen(QPen(QColor('#59B8E3'), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(plot_rect.left(), int(y1), plot_rect.width(), int(y2 - y1))

            # Draw handles
            handle_height = 6
            painter.fillRect(plot_rect.left(), int(y1 - handle_height // 2),
                            plot_rect.width(), handle_height, QColor('#59B8E3'))
            painter.fillRect(plot_rect.left(), int(y2 - handle_height // 2),
                            plot_rect.width(), handle_height, QColor('#59B8E3'))

    def _draw_labels(self, painter, rect, plot_rect):
        """Draw axis labels"""
        font = QFont('Arial', 8)
        painter.setFont(font)
        painter.setPen(QColor('#C2C8D1'))

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

            painter.setPen(QColor('#59B8E3'))
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
