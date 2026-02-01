"""
Profile Bar - 프로파일 설정 바 UI
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QScrollArea, QMenu, QSizePolicy,
    QToolButton, QMessageBox, QFileDialog, QInputDialog
)
from PySide6.QtCore import Qt, Signal, QSize, QMimeData
from PySide6.QtGui import QDrag, QMouseEvent, QAction

from ...core.state import AppState
from ...core.profile import Profile, GraphSetting, ProfileManager


class SettingButton(QFrame):
    """프로파일 설정 버튼"""

    clicked = Signal()
    double_clicked = Signal()
    float_requested = Signal()
    edit_requested = Signal()
    duplicate_requested = Signal()
    delete_requested = Signal()
    rename_requested = Signal()

    def __init__(self, setting: GraphSetting, is_active: bool = False, parent=None):
        super().__init__(parent)
        self._setting = setting
        self._is_active = is_active
        self._drag_start_pos = None

        self._setup_ui()
        self._update_style()

        self.setAcceptDrops(True)

    def _setup_ui(self):
        self.setFixedSize(90, 60)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # 아이콘
        self._icon_label = QLabel(self._setting.icon)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setStyleSheet("font-size: 18px; background: transparent;")
        layout.addWidget(self._icon_label)

        # 이름
        self._name_label = QLabel(self._setting.name)
        self._name_label.setAlignment(Qt.AlignCenter)
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #222222;
                background: transparent;
            }
        """)
        layout.addWidget(self._name_label)

        # 액션 버튼들 (hover 시 표시)
        self._action_bar = QWidget()
        self._action_bar.setStyleSheet("background: transparent;")
        action_layout = QHBoxLayout(self._action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(2)

        # Float 버튼
        self._float_btn = QToolButton()
        self._float_btn.setText("⬈")
        self._float_btn.setToolTip("Open as floating window")
        self._float_btn.setFixedSize(18, 18)
        self._float_btn.setStyleSheet("""
            QToolButton {
                background: rgba(255, 255, 255, 0.8);
                border: 1px solid #D1D5DB;
                border-radius: 3px;
                font-size: 10px;
            }
            QToolButton:hover {
                background: #EEF2FF;
                border-color: #3A7AFE;
            }
        """)
        self._float_btn.clicked.connect(self.float_requested.emit)
        action_layout.addWidget(self._float_btn)

        action_layout.addStretch()
        layout.addWidget(self._action_bar)
        self._action_bar.hide()

        # 컨텍스트 메뉴 설정
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _update_style(self):
        if self._is_active:
            self.setStyleSheet("""
                SettingButton {
                    background: #EEF2FF;
                    border: 2px solid #3A7AFE;
                    border-radius: 8px;
                }
                SettingButton:hover {
                    background: #E0E7FF;
                }
            """)
        else:
            self.setStyleSheet("""
                SettingButton {
                    background: #F9FAFB;
                    border: 1px solid #E6E6E6;
                    border-radius: 8px;
                }
                SettingButton:hover {
                    background: #EFEFEF;
                    border-color: #D1D5DB;
                }
            """)

    def set_active(self, active: bool):
        self._is_active = active
        self._update_style()

    def update_setting(self, setting: GraphSetting):
        self._setting = setting
        self._icon_label.setText(setting.icon)
        self._name_label.setText(setting.name)

    @property
    def setting(self) -> GraphSetting:
        return self._setting

    def enterEvent(self, event):
        self._action_bar.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._action_bar.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = None
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start_pos is None:
            return

        # 드래그 시작 조건
        if (event.pos() - self._drag_start_pos).manhattanLength() < 10:
            return

        # 드래그 시작
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(self._setting.id)
        drag.setMimeData(mime_data)
        drag.exec(Qt.MoveAction)

    def _show_context_menu(self, pos):
        menu = QMenu(self)

        edit_action = QAction("Edit Setting", self)
        edit_action.triggered.connect(self.edit_requested.emit)
        menu.addAction(edit_action)

        duplicate_action = QAction("Duplicate", self)
        duplicate_action.triggered.connect(self.duplicate_requested.emit)
        menu.addAction(duplicate_action)

        rename_action = QAction("Rename", self)
        rename_action.triggered.connect(self.rename_requested.emit)
        menu.addAction(rename_action)

        menu.addSeparator()

        float_action = QAction("Open Floating", self)
        float_action.triggered.connect(self.float_requested.emit)
        menu.addAction(float_action)

        menu.addSeparator()

        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(self.delete_requested.emit)
        menu.addAction(delete_action)

        menu.exec(self.mapToGlobal(pos))


class AddSettingButton(QPushButton):
    """새 설정 추가 버튼"""

    def __init__(self, parent=None):
        super().__init__("+", parent)
        self.setFixedSize(50, 60)
        self.setToolTip("Save current graph setting")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background: #F9FAFB;
                border: 2px dashed #D1D5DB;
                border-radius: 8px;
                font-size: 24px;
                font-weight: 300;
                color: #9CA3AF;
            }
            QPushButton:hover {
                background: #EFEFEF;
                border-color: #3A7AFE;
                color: #3A7AFE;
            }
            QPushButton:pressed {
                background: #E6E6E6;
            }
        """)


class ProfileBar(QFrame):
    """프로파일 바 - Summary Panel 아래에 위치"""

    setting_clicked = Signal(str)         # setting_id
    setting_double_clicked = Signal(str)  # setting_id -> float
    add_setting_requested = Signal()
    profile_load_requested = Signal()
    profile_save_requested = Signal()
    profile_new_requested = Signal()

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._setting_buttons: dict[str, SettingButton] = {}
        self._profile_manager = ProfileManager()

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        self.setStyleSheet("""
            ProfileBar {
                background: #FFFFFF;
                border: 1px solid #E6E6E6;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # 상단: 프로파일 선택 영역
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        # 프로파일 아이콘
        profile_icon = QLabel("📁")
        profile_icon.setStyleSheet("font-size: 14px; background: transparent;")
        header_layout.addWidget(profile_icon)

        # 프로파일 라벨
        profile_label = QLabel("Profile:")
        profile_label.setStyleSheet("color: #666666; font-size: 12px; background: transparent;")
        header_layout.addWidget(profile_label)

        # 프로파일 드롭다운
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(150)
        self._profile_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 8px;
                background: white;
                min-height: 20px;
            }
            QComboBox:hover {
                border-color: #3A7AFE;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        header_layout.addWidget(self._profile_combo)

        # 프로파일 액션 버튼들
        load_btn = QToolButton()
        load_btn.setText("📂")
        load_btn.setToolTip("Load profile")
        load_btn.setFixedSize(28, 28)
        load_btn.setStyleSheet(self._action_btn_style())
        load_btn.clicked.connect(self._on_load_profile)
        header_layout.addWidget(load_btn)

        save_btn = QToolButton()
        save_btn.setText("💾")
        save_btn.setToolTip("Save profile")
        save_btn.setFixedSize(28, 28)
        save_btn.setStyleSheet(self._action_btn_style())
        save_btn.clicked.connect(self._on_save_profile)
        header_layout.addWidget(save_btn)

        new_btn = QToolButton()
        new_btn.setText("➕")
        new_btn.setToolTip("New profile")
        new_btn.setFixedSize(28, 28)
        new_btn.setStyleSheet(self._action_btn_style())
        new_btn.clicked.connect(self._on_new_profile)
        header_layout.addWidget(new_btn)

        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 하단: 설정 버튼들 스크롤 영역
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFixedHeight(80)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
        """)

        self._settings_container = QWidget()
        self._settings_layout = QHBoxLayout(self._settings_container)
        self._settings_layout.setContentsMargins(0, 0, 0, 0)
        self._settings_layout.setSpacing(8)
        self._settings_layout.setAlignment(Qt.AlignLeft)

        # 추가 버튼
        self._add_btn = AddSettingButton()
        self._add_btn.clicked.connect(self.add_setting_requested.emit)
        self._settings_layout.addWidget(self._add_btn)

        self._settings_layout.addStretch()

        scroll_area.setWidget(self._settings_container)
        layout.addWidget(scroll_area)

        # 초기 프로파일 목록 로드
        self._refresh_profile_list()

    def _action_btn_style(self) -> str:
        return """
            QToolButton {
                background: #EFEFEF;
                border: 1px solid #E6E6E6;
                border-radius: 4px;
                font-size: 14px;
            }
            QToolButton:hover {
                background: #E6E6E6;
                border-color: #D1D5DB;
            }
            QToolButton:pressed {
                background: #D1D5DB;
            }
        """

    def _connect_signals(self):
        # State signals
        self._state.profile_loaded.connect(self._on_profile_loaded)
        self._state.profile_cleared.connect(self._on_profile_cleared)
        self._state.setting_activated.connect(self._on_setting_activated)
        self._state.setting_added.connect(self._on_setting_added)
        self._state.setting_removed.connect(self._on_setting_removed)

    def _refresh_profile_list(self):
        """프로파일 목록 새로고침"""
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        self._profile_combo.addItem("(No Profile)")

        # 최근 프로파일
        recent = self._profile_manager.get_recent_profiles()
        for path in recent:
            name = path.split('/')[-1].replace('.dgp', '')
            self._profile_combo.addItem(name, path)

        # 저장된 프로파일
        profiles = self._profile_manager.list_profiles()
        for profile_path in profiles:
            name = profile_path.stem
            path_str = str(profile_path)
            # 중복 방지
            found = False
            for i in range(self._profile_combo.count()):
                if self._profile_combo.itemData(i) == path_str:
                    found = True
                    break
            if not found:
                self._profile_combo.addItem(name, path_str)

        self._profile_combo.blockSignals(False)

    def _on_profile_selected(self, index: int):
        """프로파일 선택"""
        if index <= 0:
            self._state.set_profile(None)
            return

        path = self._profile_combo.itemData(index)
        if path:
            try:
                profile = self._profile_manager.load(path)
                self._state.set_profile(profile)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Load Profile Error",
                    f"Failed to load profile: {e}"
                )

    def _on_load_profile(self):
        """프로파일 불러오기"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Profile",
            str(self._profile_manager.profiles_dir),
            "Data Graph Profile (*.dgp)"
        )
        if path:
            try:
                profile = self._profile_manager.load(path)
                self._state.set_profile(profile)
                self._refresh_profile_list()
                # 콤보박스에서 선택
                for i in range(self._profile_combo.count()):
                    if self._profile_combo.itemData(i) == path:
                        self._profile_combo.setCurrentIndex(i)
                        break
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Load Profile Error",
                    f"Failed to load profile: {e}"
                )

    def _on_save_profile(self):
        """프로파일 저장"""
        profile = self._state.current_profile
        if not profile:
            QMessageBox.information(
                self,
                "Save Profile",
                "No profile to save. Create a new profile first."
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Profile",
            str(self._profile_manager.profiles_dir / f"{profile.name}.dgp"),
            "Data Graph Profile (*.dgp)"
        )
        if path:
            try:
                profile.save(path)
                self._profile_manager._add_recent_profile(path)
                self._refresh_profile_list()
                self._state.profile_saved.emit()
                QMessageBox.information(
                    self,
                    "Profile Saved",
                    f"Profile saved successfully."
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Save Profile Error",
                    f"Failed to save profile: {e}"
                )

    def _on_new_profile(self):
        """새 프로파일 생성"""
        name, ok = QInputDialog.getText(
            self,
            "New Profile",
            "Enter profile name:",
            text="New Profile"
        )
        if ok and name.strip():
            profile = Profile.create_new(name.strip())
            self._state.set_profile(profile)

    def _on_profile_loaded(self, profile: Profile):
        """프로파일 로드됨"""
        self._clear_setting_buttons()

        # 설정 버튼들 생성
        for setting in profile.settings:
            is_active = setting.id == self._state.current_setting_id
            self._add_setting_button(setting, is_active)

    def _on_profile_cleared(self):
        """프로파일 클리어됨"""
        self._clear_setting_buttons()
        self._profile_combo.setCurrentIndex(0)

    def _on_setting_activated(self, setting_id: str):
        """설정 활성화됨"""
        for sid, btn in self._setting_buttons.items():
            btn.set_active(sid == setting_id)

    def _on_setting_added(self, setting_id: str):
        """설정 추가됨"""
        profile = self._state.current_profile
        if profile:
            setting = profile.get_setting(setting_id)
            if setting:
                self._add_setting_button(setting, False)

    def _on_setting_removed(self, setting_id: str):
        """설정 제거됨"""
        if setting_id in self._setting_buttons:
            btn = self._setting_buttons.pop(setting_id)
            self._settings_layout.removeWidget(btn)
            btn.deleteLater()

    def _add_setting_button(self, setting: GraphSetting, is_active: bool):
        """설정 버튼 추가"""
        btn = SettingButton(setting, is_active)
        btn.clicked.connect(lambda: self._on_setting_clicked(setting.id))
        btn.double_clicked.connect(lambda: self.setting_double_clicked.emit(setting.id))
        btn.float_requested.connect(lambda: self.setting_double_clicked.emit(setting.id))
        btn.edit_requested.connect(lambda: self._on_edit_setting(setting.id))
        btn.duplicate_requested.connect(lambda: self._on_duplicate_setting(setting.id))
        btn.delete_requested.connect(lambda: self._on_delete_setting(setting.id))
        btn.rename_requested.connect(lambda: self._on_rename_setting(setting.id))

        # 추가 버튼 앞에 삽입
        index = self._settings_layout.count() - 2  # -2: add_btn, stretch
        if index < 0:
            index = 0
        self._settings_layout.insertWidget(index, btn)
        self._setting_buttons[setting.id] = btn

    def _clear_setting_buttons(self):
        """모든 설정 버튼 제거"""
        for btn in self._setting_buttons.values():
            self._settings_layout.removeWidget(btn)
            btn.deleteLater()
        self._setting_buttons.clear()

    def _on_setting_clicked(self, setting_id: str):
        """설정 버튼 클릭"""
        self._state.activate_setting(setting_id)
        self.setting_clicked.emit(setting_id)

    def _on_edit_setting(self, setting_id: str):
        """설정 편집"""
        # TODO: 편집 다이얼로그 표시
        pass

    def _on_duplicate_setting(self, setting_id: str):
        """설정 복제"""
        profile = self._state.current_profile
        if profile:
            original = profile.get_setting(setting_id)
            if original:
                import copy
                new_setting = GraphSetting.from_dict(original.to_dict())
                new_setting.id = GraphSetting.create_new("").id
                new_setting.name = f"{original.name} (copy)"
                self._state.add_setting(new_setting)

    def _on_delete_setting(self, setting_id: str):
        """설정 삭제"""
        reply = QMessageBox.question(
            self,
            "Delete Setting",
            "Are you sure you want to delete this setting?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._state.remove_setting(setting_id)

    def _on_rename_setting(self, setting_id: str):
        """설정 이름 변경"""
        profile = self._state.current_profile
        if profile:
            setting = profile.get_setting(setting_id)
            if setting:
                name, ok = QInputDialog.getText(
                    self,
                    "Rename Setting",
                    "Enter new name:",
                    text=setting.name
                )
                if ok and name.strip():
                    setting.name = name.strip()
                    setting.update_modified()
                    if setting_id in self._setting_buttons:
                        self._setting_buttons[setting_id].update_setting(setting)

    @property
    def profile_manager(self) -> ProfileManager:
        return self._profile_manager
