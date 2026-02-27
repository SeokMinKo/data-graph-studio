"""
About Dialog - Professional about dialog with gradient header
"""

import os
import sys
import platform

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QGridLayout, QFrame,
)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QPixmap, QFont, QDesktopServices,
)

from data_graph_studio import __version__, __author__


class _GradientHeader(QWidget):
    """Gradient header with logo and app name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(140)
        self._logo: QPixmap | None = None
        self._load_logo()

    def _load_logo(self):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(base_dir, "..", "..", "..", "resources", "icons", "dgs-512.png"),
            os.path.join(base_dir, "..", "..", "..", "resources", "icons", "dgs-tech-1024.png"),
        ]
        for path in candidates:
            resolved = os.path.normpath(path)
            if os.path.exists(resolved):
                self._logo = QPixmap(resolved)
                break

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Gradient background
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor("#0B1120"))
        grad.setColorAt(1.0, QColor("#1E293B"))
        painter.fillRect(0, 0, w, h, grad)

        # Decorative circles
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(56, 189, 248, 12))
        painter.drawEllipse(-40, -30, 160, 160)
        painter.setBrush(QColor(34, 211, 238, 8))
        painter.drawEllipse(w - 100, h - 100, 180, 180)

        # Logo
        center_x = w // 2
        if self._logo and not self._logo.isNull():
            scaled = self._logo.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(center_x - 28, 20, scaled)
            text_y = 82
        else:
            text_y = 30

        # Title
        painter.setPen(QColor("#E2E8F0"))
        title_font = QFont("Helvetica Neue", 17, QFont.Bold)
        painter.setFont(title_font)
        painter.drawText(QRect(0, text_y, w, 28), Qt.AlignCenter, "Data Graph Studio")

        # Version
        painter.setPen(QColor("#94A3B8"))
        ver_font = QFont("Helvetica Neue", 11)
        painter.setFont(ver_font)
        painter.drawText(QRect(0, text_y + 28, w, 20), Qt.AlignCenter, f"v{__version__}")

        painter.end()


class AboutDialog(QDialog):
    """Professional about dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Data Graph Studio")
        self.setFixedSize(450, 520)
        self.setObjectName("aboutDialog")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Gradient header
        header = _GradientHeader()
        layout.addWidget(header)

        # Content area
        content = QWidget()
        content.setObjectName("aboutContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 16)
        content_layout.setSpacing(16)

        # Tagline
        tagline = QLabel("Big Data Visualization & Analysis Tool")
        tagline.setObjectName("aboutTagline")
        tagline.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(tagline)

        # Features grid (2x3)
        features_frame = QFrame()
        features_frame.setObjectName("aboutFeaturesFrame")
        features_grid = QGridLayout(features_frame)
        features_grid.setContentsMargins(8, 8, 8, 8)
        features_grid.setSpacing(8)

        feature_list = [
            ("20+ Chart Types", "Line, Bar, Scatter, Heatmap..."),
            ("10M+ Rows", "LTTB sampling for big data"),
            ("Multi-Dataset", "Compare & overlay datasets"),
            ("Drag & Drop", "Intuitive column mapping"),
            ("Export", "PNG, PDF, PPTX, HTML reports"),
            ("Streaming", "Live file watch & reload"),
        ]

        for i, (title, desc) in enumerate(feature_list):
            row, col = divmod(i, 2)
            card = self._make_feature_card(title, desc)
            features_grid.addWidget(card, row, col)

        content_layout.addWidget(features_frame)

        # Built with section
        built_label = QLabel("Built with")
        built_label.setObjectName("aboutBuiltLabel")
        content_layout.addWidget(built_label)

        tech_layout = QHBoxLayout()
        tech_layout.setSpacing(12)
        techs = self._get_tech_versions()
        for name, ver in techs:
            chip = QLabel(f"{name} {ver}")
            chip.setObjectName("aboutTechChip")
            chip.setAlignment(Qt.AlignCenter)
            tech_layout.addWidget(chip)
        tech_layout.addStretch()
        content_layout.addLayout(tech_layout)

        content_layout.addStretch()

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(8)

        copy_label = QLabel(f"\u00a9 2026 {__author__}")
        copy_label.setObjectName("aboutCopyright")
        footer.addWidget(copy_label)

        footer.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setObjectName("aboutCloseBtn")
        close_btn.setProperty("class", "primary")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)

        content_layout.addLayout(footer)
        layout.addWidget(content)

    def _make_feature_card(self, title: str, desc: str) -> QFrame:
        card = QFrame()
        card.setObjectName("aboutFeatureCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("aboutFeatureTitle")
        layout.addWidget(title_label)

        desc_label = QLabel(desc)
        desc_label.setObjectName("aboutFeatureDesc")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        return card

    @staticmethod
    def _get_tech_versions():
        techs = []
        techs.append(("Python", platform.python_version()))
        try:
            import PySide6
            techs.append(("PySide6", PySide6.__version__))
        except Exception:
            techs.append(("PySide6", "?"))
        try:
            import polars
            techs.append(("Polars", polars.__version__))
        except Exception:
            pass
        try:
            import pyqtgraph
            techs.append(("PyQtGraph", pyqtgraph.__version__))
        except Exception:
            pass
        return techs
