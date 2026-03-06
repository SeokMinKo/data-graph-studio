"""
Save Setting Dialog - 그래프 설정 저장 다이얼로그
"""

from typing import Optional
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QFrame,
    QGridLayout,
)
from PySide6.QtCore import Qt

from ...core.profile import GraphSetting


# 사용 가능한 아이콘 목록
SETTING_ICONS = [
    "📊",
    "📈",
    "📉",
    "📋",
    "🥧",
    "📐",
    "📏",
    "🔍",
    "💹",
    "📌",
    "🎯",
    "💡",
    "⚡",
    "🔥",
    "✨",
    "🌟",
    "💎",
    "🔷",
    "🔶",
    "⭐",
]


class SaveSettingDialog(QDialog):
    """그래프 설정 저장 다이얼로그"""

    def __init__(self, parent=None, existing_setting: Optional[GraphSetting] = None):
        super().__init__(parent)
        self._existing = existing_setting
        self._result_setting: Optional[GraphSetting] = None

        self.setWindowTitle(
            "Save Graph Setting" if not existing_setting else "Edit Graph Setting"
        )
        self.setMinimumWidth(400)
        self.setModal(True)

        self._setup_ui()

        if existing_setting:
            self._load_existing(existing_setting)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 헤더
        header = QLabel("💾 Save Current Graph Setting")
        header.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: 600;
                color: #E6E9EF;
                padding: 8px 0;
            }
        """)
        layout.addWidget(header)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background: #3E4A59;")
        layout.addWidget(line)

        # 폼 영역
        form_layout = QGridLayout()
        form_layout.setSpacing(12)
        form_layout.setColumnStretch(1, 1)

        # 이름
        name_label = QLabel("Name:")
        name_label.setStyleSheet("font-weight: 500; color: #E6E9EF;")
        form_layout.addWidget(name_label, 0, 0, Qt.AlignRight)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Enter setting name...")
        self._name_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px 12px;
                background: white;
            }
            QLineEdit:focus {
                border-color: #59B8E3;
            }
        """)
        form_layout.addWidget(self._name_edit, 0, 1)

        # 아이콘
        icon_label = QLabel("Icon:")
        icon_label.setStyleSheet("font-weight: 500; color: #E6E9EF;")
        form_layout.addWidget(icon_label, 1, 0, Qt.AlignRight)

        self._icon_combo = QComboBox()
        self._icon_combo.setToolTip("Choose an icon for this setting")
        self._icon_combo.setMinimumWidth(100)
        for icon in SETTING_ICONS:
            self._icon_combo.addItem(icon, icon)
        self._icon_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px 12px;
                background: white;
                font-size: 18px;
            }
            QComboBox:hover {
                border-color: #59B8E3;
            }
        """)
        form_layout.addWidget(self._icon_combo, 1, 1, Qt.AlignLeft)

        # 설명
        desc_label = QLabel("Description:")
        desc_label.setStyleSheet("font-weight: 500; color: #E6E9EF;")
        form_layout.addWidget(desc_label, 2, 0, Qt.AlignRight | Qt.AlignTop)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Optional description...")
        self._desc_edit.setMaximumHeight(80)
        self._desc_edit.setStyleSheet("""
            QTextEdit {
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px;
                background: white;
            }
            QTextEdit:focus {
                border-color: #59B8E3;
            }
        """)
        form_layout.addWidget(self._desc_edit, 2, 1)

        layout.addLayout(form_layout)

        # 옵션 영역
        options_frame = QFrame()
        options_frame.setStyleSheet("""
            QFrame {
                background: #F9FAFB;
                border: 1px solid #3E4A59;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        options_layout = QVBoxLayout(options_frame)
        options_layout.setSpacing(8)

        options_header = QLabel("Include in setting:")
        options_header.setStyleSheet("font-weight: 500; color: #E6E9EF;")
        options_layout.addWidget(options_header)

        self._include_filters_cb = QCheckBox("Include current filters")
        self._include_filters_cb.setToolTip(
            "Save active filter settings with this profile"
        )
        self._include_filters_cb.setStyleSheet("color: #C2C8D1;")
        options_layout.addWidget(self._include_filters_cb)

        self._include_sorts_cb = QCheckBox("Include current sort order")
        self._include_sorts_cb.setToolTip(
            "Save current table sort order with this profile"
        )
        self._include_sorts_cb.setStyleSheet("color: #C2C8D1;")
        options_layout.addWidget(self._include_sorts_cb)

        layout.addWidget(options_frame)

        # 버튼
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Cancel and close dialog")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #3A4654;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 8px 20px;
                color: #E6E9EF;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #3E4A59;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setToolTip("Save graph setting")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #59B8E3;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                color: white;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #59B8E3;
            }
            QPushButton:pressed {
                background: #4338CA;
            }
        """)
        save_btn.clicked.connect(self._on_save)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _load_existing(self, setting: GraphSetting):
        """기존 설정 로드"""
        self._name_edit.setText(setting.name)

        # 아이콘 선택
        idx = self._icon_combo.findData(setting.icon)
        if idx >= 0:
            self._icon_combo.setCurrentIndex(idx)

        self._desc_edit.setPlainText(setting.description)
        self._include_filters_cb.setChecked(setting.include_filters)
        self._include_sorts_cb.setChecked(setting.include_sorts)

    def _on_save(self):
        """저장"""
        import dataclasses

        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setFocus()
            return

        icon = self._icon_combo.currentData()
        description = self._desc_edit.toPlainText().strip()
        include_filters = self._include_filters_cb.isChecked()
        include_sorts = self._include_sorts_cb.isChecked()

        if self._existing:
            # 기존 설정 업데이트 (frozen이므로 replace 사용)
            self._result_setting = dataclasses.replace(
                self._existing,
                name=name,
                icon=icon,
                description=description,
                include_filters=include_filters,
                include_sorts=include_sorts,
            )
        else:
            # 새 설정 생성
            self._result_setting = GraphSetting.create_new(name, icon)
            self._result_setting = dataclasses.replace(
                self._result_setting,
                description=description,
                include_filters=include_filters,
                include_sorts=include_sorts,
            )

        self.accept()

    def get_setting(self) -> Optional[GraphSetting]:
        """결과 설정 반환"""
        return self._result_setting

    def get_include_filters(self) -> bool:
        """필터 포함 여부"""
        return self._include_filters_cb.isChecked()

    def get_include_sorts(self) -> bool:
        """정렬 포함 여부"""
        return self._include_sorts_cb.isChecked()
