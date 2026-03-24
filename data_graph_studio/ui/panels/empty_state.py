"""
Empty State - 데이터 없을 때 표시되는 온보딩 가이드
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGraphicsDropShadowEffect,
    QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPointF, Property
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QBrush,
    QLinearGradient,
    QPainterPath,
)


class AnimatedGraphIcon(QWidget):
    """Animated line chart icon using QPainter — replaces emoji."""

    def __init__(
        self, color_primary: str = "#38BDF8", color_accent: str = "#22D3EE", parent=None
    ):
        super().__init__(parent)
        self.setFixedSize(120, 90)
        self._primary = QColor(color_primary)
        self._accent = QColor(color_accent)
        self._dot_opacity = 1.0

        # Pulse animation via timer
        self._pulse_dir = -1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(50)

        # Data points (normalized 0-1)
        self._points = [0.15, 0.35, 0.25, 0.55, 0.45, 0.72, 0.65, 0.88]

    def _get_dot_opacity(self):
        return self._dot_opacity

    def _set_dot_opacity(self, val):
        self._dot_opacity = val
        self.update()

    dotOpacity = Property(float, _get_dot_opacity, _set_dot_opacity)

    def _animate(self):
        self._dot_opacity += self._pulse_dir * 0.015
        if self._dot_opacity <= 0.35:
            self._pulse_dir = 1
        elif self._dot_opacity >= 1.0:
            self._pulse_dir = -1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        margin_x, margin_y = 16, 12
        plot_w = w - margin_x * 2
        plot_h = h - margin_y * 2

        # Axes
        axis_color = QColor(self._primary)
        axis_color.setAlpha(60)
        painter.setPen(QPen(axis_color, 1.5))
        # Y-axis
        painter.drawLine(int(margin_x), int(margin_y), int(margin_x), int(h - margin_y))
        # X-axis
        painter.drawLine(
            int(margin_x), int(h - margin_y), int(w - margin_x), int(h - margin_y)
        )

        # Build points
        pts = []
        n = len(self._points)
        for i, v in enumerate(self._points):
            px = margin_x + (i / (n - 1)) * plot_w
            py = (h - margin_y) - v * plot_h
            pts.append(QPointF(px, py))

        # Gradient fill under line
        if len(pts) >= 2:
            fill_path = QPainterPath()
            fill_path.moveTo(QPointF(pts[0].x(), h - margin_y))
            for p in pts:
                fill_path.lineTo(p)
            fill_path.lineTo(QPointF(pts[-1].x(), h - margin_y))
            fill_path.closeSubpath()

            fill_grad = QLinearGradient(0, margin_y, 0, h - margin_y)
            fill_color = QColor(self._primary)
            fill_color.setAlpha(40)
            fill_grad.setColorAt(0.0, fill_color)
            fill_color2 = QColor(self._primary)
            fill_color2.setAlpha(5)
            fill_grad.setColorAt(1.0, fill_color2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(fill_grad))
            painter.drawPath(fill_path)

        # Line
        line_grad = QLinearGradient(pts[0], pts[-1])
        line_grad.setColorAt(0.0, self._primary)
        line_grad.setColorAt(1.0, self._accent)
        painter.setPen(QPen(QBrush(line_grad), 2.5))
        painter.setBrush(Qt.NoBrush)
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])

        # Dots with pulsing opacity
        dot_color = QColor(self._accent)
        dot_color.setAlphaF(self._dot_opacity)
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot_color)
        for p in pts:
            painter.drawEllipse(p, 3.5, 3.5)

        painter.end()


class StepBadge(QWidget):
    """Circular numbered badge painted with QPainter."""

    def __init__(self, number: int, color: str = "#38BDF8", parent=None):
        super().__init__(parent)
        self._number = number
        self._color = QColor(color)
        self.setFixedSize(28, 28)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())

        # Circle background
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(2, 2, s - 4, s - 4)

        # Number text
        painter.setPen(QColor("white"))
        font = QFont("Helvetica Neue", 11, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, str(self._number))
        painter.end()


class EmptyStateWidget(QWidget):
    """
    데이터가 없을 때 표시되는 온보딩 위젯

    - 애니메이션 차트 아이콘
    - 명확한 액션 가이드
    - 드래그 앤 드롭 힌트
    """

    open_file_requested = Signal()
    load_sample_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("emptyStateWidget")

        # 외부 레이아웃 — QScrollArea로 감싸서 공간 부족 시 스크롤
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("emptyStateScroll")
        scroll.setStyleSheet("QScrollArea#emptyStateScroll { background: transparent; border: none; }"
                             " QScrollArea#emptyStateScroll > QWidget > QWidget { background: transparent; }")
        outer_layout.addWidget(scroll)

        scroll_content = QWidget()
        scroll_content.setObjectName("emptyStateScrollContent")
        scroll.setWidget(scroll_content)

        # 메인 레이아웃
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setAlignment(Qt.AlignCenter)

        # 중앙 컨테이너 (카드 스타일)
        card = QFrame()
        card.setObjectName("emptyStateCard")
        card.setMaximumWidth(560)
        card.setMinimumWidth(400)

        # 그림자 효과
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 50))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 36)
        card_layout.setSpacing(14)
        card_layout.setAlignment(Qt.AlignCenter)

        # 애니메이션 차트 아이콘
        chart_icon = AnimatedGraphIcon()
        chart_icon_layout = QHBoxLayout()
        chart_icon_layout.setAlignment(Qt.AlignCenter)
        chart_icon_layout.addWidget(chart_icon)
        card_layout.addLayout(chart_icon_layout)

        # 메인 타이틀
        title = QLabel("데이터를 불러오세요")
        title.setObjectName("emptyStateTitle")
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)

        # 서브타이틀
        subtitle = QLabel("파일을 드래그 앤 드롭하거나\n아래 버튼을 클릭하세요")
        subtitle.setObjectName("emptyStateSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        card_layout.addWidget(subtitle)

        # 지원 포맷 힌트
        formats = QLabel("CSV  •  Excel  •  Parquet  •  JSON  •  TSV")
        formats.setObjectName("emptyStateFormats")
        formats.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(formats)

        card_layout.addSpacing(12)

        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(Qt.AlignCenter)

        # 파일 열기 버튼 (Primary)
        open_btn = QPushButton("파일 열기")
        open_btn.setObjectName("emptyStatePrimaryBtn")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self.open_file_requested.emit)
        btn_layout.addWidget(open_btn)

        # 샘플 데이터 버튼 (Secondary)
        sample_btn = QPushButton("샘플 데이터")
        sample_btn.setObjectName("emptyStateSecondaryBtn")
        sample_btn.setCursor(Qt.PointingHandCursor)
        sample_btn.clicked.connect(self.load_sample_requested.emit)
        btn_layout.addWidget(sample_btn)

        card_layout.addLayout(btn_layout)

        # 단축키 힌트
        shortcut_hint = QLabel("Ctrl+O")
        shortcut_hint.setObjectName("emptyStateShortcutHint")
        shortcut_hint.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(shortcut_hint)

        # 드래그 앤 드롭 영역 표시
        card_layout.addSpacing(20)

        drop_hint = QFrame()
        drop_hint.setObjectName("emptyStateDropHint")
        drop_layout = QVBoxLayout(drop_hint)
        drop_layout.setContentsMargins(24, 18, 24, 18)

        drop_icon = QLabel("↓")
        drop_icon.setAlignment(Qt.AlignCenter)
        drop_icon.setObjectName("dropHintIcon")
        drop_icon_font = QFont()
        drop_icon_font.setPointSize(20)
        drop_icon.setFont(drop_icon_font)
        drop_layout.addWidget(drop_icon)

        drop_text = QLabel("여기에 파일을 드롭하세요")
        drop_text.setObjectName("dropHintText")
        drop_text.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(drop_text)

        card_layout.addWidget(drop_hint)

        # 단계 가이드
        card_layout.addSpacing(20)

        steps_label = QLabel("시작하기")
        steps_label.setObjectName("emptyStateStepsTitle")
        card_layout.addWidget(steps_label)

        steps = [
            (1, "파일을 열거나 드래그 앤 드롭"),
            (2, "X축에 컬럼을 드래그"),
            (3, "값(Y축)에 컬럼을 드래그"),
        ]

        for num, text in steps:
            step_widget = QWidget()
            step_layout = QHBoxLayout(step_widget)
            step_layout.setContentsMargins(0, 4, 0, 4)
            step_layout.setSpacing(12)

            badge = StepBadge(num)
            step_layout.addWidget(badge)

            text_label = QLabel(text)
            text_label.setObjectName("stepText")
            step_layout.addWidget(text_label, 1)

            card_layout.addWidget(step_widget)

        main_layout.addWidget(card)


class DropZoneOverlay(QWidget):
    """드래그 오버 시 표시되는 오버레이"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZoneOverlay")
        self._setup_ui()
        self.hide()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        icon = QLabel("📥")
        icon.setObjectName("dropOverlayIcon")
        icon_font = QFont()
        icon_font.setPointSize(48)
        icon.setFont(icon_font)
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        text = QLabel("파일을 여기에 놓으세요")
        text.setObjectName("dropOverlayText")
        text.setAlignment(Qt.AlignCenter)
        layout.addWidget(text)
