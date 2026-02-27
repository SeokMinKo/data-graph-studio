"""
Splash Screen - Professional animated splash for app startup
"""

import os
import sys

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QPixmap, QFont, QPen,
    QBrush, QPainterPath,
)


class SplashScreen(QWidget):
    """Professional splash screen with gradient background and progress bar."""

    def __init__(self, version: str = ""):
        super().__init__()
        self._version = version
        self._status = "Starting..."
        self._progress = 0
        self._logo: QPixmap | None = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(520, 380)

        self._load_logo()
        self._center_on_screen()

    def _load_logo(self):
        """Load the app logo from resources."""
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(base_dir, "..", "..", "resources", "icons", "dgs-512.png"),
            os.path.join(base_dir, "..", "..", "resources", "icons", "dgs-tech-1024.png"),
        ]
        for path in candidates:
            resolved = os.path.normpath(path)
            if os.path.exists(resolved):
                self._logo = QPixmap(resolved)
                break

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2 + geo.x()
            y = (geo.height() - self.height()) // 2 + geo.y()
            self.move(x, y)

    def set_status(self, text: str, progress: int = -1):
        """Update status text and progress."""
        self._status = text
        if progress >= 0:
            self._progress = min(progress, 100)
        self.update()
        QApplication.processEvents()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # --- Rounded rectangle clip ---
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, 16, 16)
        painter.setClipPath(path)

        # --- Gradient background ---
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor("#0B1120"))
        bg_grad.setColorAt(0.5, QColor("#111D33"))
        bg_grad.setColorAt(1.0, QColor("#1E293B"))
        painter.fillRect(0, 0, w, h, bg_grad)

        # --- Subtle decorative circles ---
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(56, 189, 248, 8))  # #38BDF8 very transparent
        painter.drawEllipse(-60, -40, 240, 240)
        painter.setBrush(QColor(34, 211, 238, 6))  # #22D3EE
        painter.drawEllipse(w - 150, h - 180, 280, 280)
        painter.setBrush(QColor(129, 140, 248, 5))  # indigo
        painter.drawEllipse(w // 2 - 100, -80, 200, 200)

        # --- Border glow ---
        border_grad = QLinearGradient(0, 0, w, h)
        border_grad.setColorAt(0.0, QColor("#38BDF8"))
        border_grad.setColorAt(1.0, QColor("#22D3EE"))
        pen = QPen(QBrush(border_grad), 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(1, 1, w - 2, h - 2, 16, 16)

        # --- Logo ---
        logo_y = 60
        if self._logo and not self._logo.isNull():
            scaled = self._logo.scaled(
                96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            logo_x = (w - scaled.width()) // 2
            painter.drawPixmap(logo_x, logo_y, scaled)
            text_y = logo_y + scaled.height() + 20
        else:
            # Fallback: draw chart icon
            self._draw_chart_icon(painter, w // 2 - 40, logo_y, 80, 60)
            text_y = logo_y + 80

        # --- App Title ---
        painter.setPen(QColor("#E2E8F0"))
        title_font = QFont("Helvetica Neue", 22, QFont.Bold)
        painter.setFont(title_font)
        painter.drawText(QRect(0, text_y, w, 36), Qt.AlignCenter, "Data Graph Studio")

        # --- Tagline ---
        tag_y = text_y + 38
        painter.setPen(QColor("#94A3B8"))
        tag_font = QFont("Helvetica Neue", 12)
        painter.setFont(tag_font)
        painter.drawText(QRect(0, tag_y, w, 22), Qt.AlignCenter, "Big Data Visualization")

        # --- Version ---
        if self._version:
            ver_y = tag_y + 26
            painter.setPen(QColor("#64748B"))
            ver_font = QFont("Helvetica Neue", 10)
            painter.setFont(ver_font)
            painter.drawText(QRect(0, ver_y, w, 18), Qt.AlignCenter, f"v{self._version}")

        # --- Progress bar ---
        bar_y = h - 60
        bar_x = 60
        bar_w = w - 120
        bar_h = 6

        # Background track
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1E293B"))
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)

        # Fill
        if self._progress > 0:
            fill_w = int(bar_w * self._progress / 100)
            fill_grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            fill_grad.setColorAt(0.0, QColor("#38BDF8"))
            fill_grad.setColorAt(1.0, QColor("#22D3EE"))
            painter.setBrush(fill_grad)
            painter.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 3, 3)

        # --- Status text ---
        status_y = bar_y + 14
        painter.setPen(QColor("#64748B"))
        status_font = QFont("Helvetica Neue", 11)
        painter.setFont(status_font)
        painter.drawText(QRect(0, status_y, w, 20), Qt.AlignCenter, self._status)

        painter.end()

    def _draw_chart_icon(self, painter: QPainter, x: int, y: int, w: int, h: int):
        """Fallback chart icon when logo is not available."""
        painter.setPen(Qt.NoPen)
        bar_colors = ["#38BDF8", "#22D3EE", "#818CF8", "#38BDF8"]
        bar_w = w // 6
        heights = [0.4, 0.7, 0.55, 0.9]
        for i, (ratio, color) in enumerate(zip(heights, bar_colors)):
            bx = x + i * (bar_w + 4) + 4
            bh = int(h * ratio)
            by = y + h - bh
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(bx, by, bar_w, bh, 2, 2)

    def finish(self, main_window):
        """Close splash after showing 'Ready' briefly."""
        self.set_status("Ready!", 100)
        QTimer.singleShot(400, self.close)
        QTimer.singleShot(400, main_window.show)
