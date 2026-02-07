"""
Empty State - 데이터 없을 때 표시되는 온보딩 가이드
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont


class EmptyStateWidget(QWidget):
    """
    데이터가 없을 때 표시되는 온보딩 위젯
    
    - 중앙 정렬된 큰 아이콘
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
        
        # 메인 레이아웃
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setAlignment(Qt.AlignCenter)
        
        # 중앙 컨테이너 (카드 스타일)
        card = QFrame()
        card.setObjectName("emptyStateCard")
        card.setMaximumWidth(480)
        card.setMinimumWidth(360)
        
        # 그림자 효과
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 40))
        card.setGraphicsEffect(shadow)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 48, 40, 40)
        card_layout.setSpacing(16)
        card_layout.setAlignment(Qt.AlignCenter)
        
        # 아이콘 (이모지 대신 큰 텍스트)
        icon_label = QLabel("📊")
        icon_label.setObjectName("emptyStateIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_font = QFont()
        icon_font.setPointSize(64)
        icon_label.setFont(icon_font)
        card_layout.addWidget(icon_label)
        
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
        formats = QLabel("CSV • Excel • Parquet • JSON • TSV")
        formats.setObjectName("emptyStateFormats")
        formats.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(formats)
        
        card_layout.addSpacing(16)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(Qt.AlignCenter)
        
        # 파일 열기 버튼 (Primary)
        open_btn = QPushButton("📂 파일 열기")
        open_btn.setObjectName("emptyStatePrimaryBtn")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self.open_file_requested.emit)
        btn_layout.addWidget(open_btn)
        
        # 샘플 데이터 버튼 (Secondary)
        sample_btn = QPushButton("✨ 샘플 데이터")
        sample_btn.setObjectName("emptyStateSecondaryBtn")
        sample_btn.setCursor(Qt.PointingHandCursor)
        sample_btn.clicked.connect(self.load_sample_requested.emit)
        btn_layout.addWidget(sample_btn)
        
        card_layout.addLayout(btn_layout)
        
        # 드래그 앤 드롭 영역 표시
        card_layout.addSpacing(24)
        
        drop_hint = QFrame()
        drop_hint.setObjectName("emptyStateDropHint")
        drop_layout = QVBoxLayout(drop_hint)
        drop_layout.setContentsMargins(20, 16, 20, 16)
        
        drop_icon = QLabel("⬇️")
        drop_icon.setAlignment(Qt.AlignCenter)
        drop_icon.setObjectName("dropHintIcon")
        drop_layout.addWidget(drop_icon)
        
        drop_text = QLabel("여기에 파일을 드롭하세요")
        drop_text.setObjectName("dropHintText")
        drop_text.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(drop_text)
        
        card_layout.addWidget(drop_hint)
        
        # 단계 가이드
        card_layout.addSpacing(24)
        
        steps_label = QLabel("시작하기")
        steps_label.setObjectName("emptyStateStepsTitle")
        card_layout.addWidget(steps_label)
        
        steps = [
            ("1️⃣", "파일을 열거나 드래그 앤 드롭"),
            ("2️⃣", "X축에 컬럼을 드래그"),
            ("3️⃣", "값(Y축)에 컬럼을 드래그"),
        ]
        
        for num, text in steps:
            step_widget = QWidget()
            step_layout = QHBoxLayout(step_widget)
            step_layout.setContentsMargins(0, 4, 0, 4)
            step_layout.setSpacing(12)
            
            num_label = QLabel(num)
            num_label.setObjectName("stepNumber")
            step_layout.addWidget(num_label)
            
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
