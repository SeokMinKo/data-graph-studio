"""
Profile Manager Dialog - 프로파일 관리 다이얼로그
"""

import logging
from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QMessageBox, QInputDialog, QFileDialog, QWidget,
    QToolButton, QScrollArea
)
from PySide6.QtCore import Qt, Signal

logger = logging.getLogger(__name__)

from ...core.profile import Profile, GraphSetting, ProfileManager


class SettingItem(QFrame):
    """설정 아이템 위젯"""

    edit_requested = Signal()
    delete_requested = Signal()
    set_default_requested = Signal()

    def __init__(self, setting: GraphSetting, is_default: bool = False, parent=None):
        super().__init__(parent)
        self._setting = setting
        self._is_default = is_default

        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("settingItem")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 아이콘
        icon_label = QLabel(self._setting.icon)
        icon_label.setObjectName("settingIcon")
        layout.addWidget(icon_label)

        # 정보 영역
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 이름 + 기본 설정 표시
        name_layout = QHBoxLayout()
        name_label = QLabel(self._setting.name)
        name_label.setObjectName("settingName")
        name_layout.addWidget(name_label)

        if self._is_default:
            default_badge = QLabel("⭐ Default")
            default_badge.setObjectName("defaultBadge")
            name_layout.addWidget(default_badge)

        name_layout.addStretch()
        info_layout.addLayout(name_layout)

        # 세부 정보
        details = f"{self._setting.chart_type.title()}"
        if self._setting.x_column:
            details += f", X: {self._setting.x_column}"
        if self._setting.value_columns:
            details += f", {len(self._setting.value_columns)} value(s)"

        detail_label = QLabel(details)
        detail_label.setObjectName("settingDetail")
        info_layout.addWidget(detail_label)

        layout.addLayout(info_layout, 1)

        # 액션 버튼들
        action_layout = QHBoxLayout()
        action_layout.setSpacing(4)

        if not self._is_default:
            default_btn = QToolButton()
            default_btn.setText("⭐")
            default_btn.setToolTip("Set as default")
            default_btn.setObjectName("actionButton")
            default_btn.clicked.connect(self.set_default_requested.emit)
            action_layout.addWidget(default_btn)

        edit_btn = QToolButton()
        edit_btn.setText("✏️")
        edit_btn.setToolTip("Edit")
        edit_btn.setObjectName("actionButton")
        edit_btn.clicked.connect(self.edit_requested.emit)
        action_layout.addWidget(edit_btn)

        delete_btn = QToolButton()
        delete_btn.setText("🗑️")
        delete_btn.setToolTip("Delete")
        delete_btn.setObjectName("actionButton")
        delete_btn.clicked.connect(self.delete_requested.emit)
        action_layout.addWidget(delete_btn)

        layout.addLayout(action_layout)

    @property
    def setting(self) -> GraphSetting:
        return self._setting


class ProfileManagerDialog(QDialog):
    """프로파일 관리 다이얼로그"""

    profile_selected = Signal(object)  # Profile

    def __init__(self, profile_manager: ProfileManager, parent=None):
        super().__init__(parent)
        self._profile_manager = profile_manager
        self._selected_profile: Optional[Profile] = None

        self.setWindowTitle("Profile Manager")
        self.setMinimumSize(800, 500)
        self.resize(900, 600)
        self.setModal(True)

        self._setup_ui()
        self._refresh_profiles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # 메인 스플리터
        splitter = QSplitter(Qt.Horizontal)

        # 왼쪽: 프로파일 목록
        left_panel = QFrame()
        left_panel.setObjectName("dialogPanelLeft")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        # 프로파일 헤더
        profile_header = QLabel("📁 Profiles")
        profile_header.setObjectName("sectionHeader")
        left_layout.addWidget(profile_header)

        # 프로파일 리스트
        self._profile_list = QListWidget()
        # Style handled by global theme stylesheet
        self._profile_list.currentItemChanged.connect(self._on_profile_selected)
        left_layout.addWidget(self._profile_list, 1)

        # 프로파일 액션 버튼들
        profile_actions = QHBoxLayout()
        profile_actions.setSpacing(8)

        new_profile_btn = QPushButton("➕ New")
        new_profile_btn.setToolTip("Create a new empty profile")
        new_profile_btn.setObjectName("smallButton")
        new_profile_btn.clicked.connect(self._on_new_profile)
        profile_actions.addWidget(new_profile_btn)

        import_btn = QPushButton("📂 Import")
        import_btn.setToolTip("Import a profile from file")
        import_btn.setObjectName("smallButton")
        import_btn.clicked.connect(self._on_import_profile)
        profile_actions.addWidget(import_btn)

        profile_actions.addStretch()
        left_layout.addLayout(profile_actions)

        splitter.addWidget(left_panel)

        # 오른쪽: 설정 목록
        right_panel = QFrame()
        right_panel.setObjectName("dialogPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        # 설정 헤더
        self._settings_header = QLabel("Select a profile")
        self._settings_header.setObjectName("sectionHeader")
        right_layout.addWidget(self._settings_header)

        # 설정 스크롤 영역
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # Style handled by global theme stylesheet

        self._settings_container = QWidget()
        self._settings_layout = QVBoxLayout(self._settings_container)
        self._settings_layout.setContentsMargins(0, 0, 0, 0)
        self._settings_layout.setSpacing(8)
        self._settings_layout.addStretch()

        scroll_area.setWidget(self._settings_container)
        right_layout.addWidget(scroll_area, 1)

        # 설정 액션 버튼들
        settings_actions = QHBoxLayout()
        settings_actions.setSpacing(8)

        export_btn = QPushButton("💾 Export Profile")
        export_btn.setToolTip("Export selected profile to a file")
        export_btn.setObjectName("smallButton")
        export_btn.clicked.connect(self._on_export_profile)
        settings_actions.addWidget(export_btn)

        delete_profile_btn = QPushButton("🗑️ Delete Profile")
        delete_profile_btn.setToolTip("Permanently delete selected profile")
        delete_profile_btn.setObjectName("deleteButton")
        delete_profile_btn.clicked.connect(self._on_delete_profile)
        settings_actions.addWidget(delete_profile_btn)

        settings_actions.addStretch()
        right_layout.addLayout(settings_actions)

        splitter.addWidget(right_panel)

        # 스플리터 비율
        splitter.setSizes([250, 550])

        layout.addWidget(splitter, 1)

        # 하단 버튼
        footer = QFrame()
        footer.setObjectName("dialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 12, 16, 12)

        footer_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setToolTip("Close profile manager")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.close)
        footer_layout.addWidget(close_btn)

        layout.addWidget(footer)

    def _refresh_profiles(self):
        """프로파일 목록 새로고침"""
        self._profile_list.clear()

        # 현재 프로파일
        current = self._profile_manager.current_profile
        if current:
            item = QListWidgetItem(f"📊 {current.name} (Current)")
            item.setData(Qt.UserRole, current)
            self._profile_list.addItem(item)

        # 저장된 프로파일들
        for profile_path in self._profile_manager.list_profiles():
            try:
                profile = Profile.load(str(profile_path))
                # 현재 프로파일과 중복 방지
                if current and profile.id == current.id:
                    continue
                item = QListWidgetItem(f"📁 {profile.name}")
                item.setData(Qt.UserRole, profile)
                item.setData(Qt.UserRole + 1, str(profile_path))  # 경로 저장
                self._profile_list.addItem(item)
            except Exception:
                logger.warning("profile_manager_dialog.refresh_profiles.parse_error", exc_info=True)
                continue

    def _on_profile_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """프로파일 선택"""
        if not current:
            self._selected_profile = None
            self._settings_header.setText("Select a profile")
            self._clear_settings()
            return

        self._selected_profile = current.data(Qt.UserRole)
        if self._selected_profile:
            self._settings_header.setText(f"Settings in \"{self._selected_profile.name}\"")
            self._refresh_settings()

    def _refresh_settings(self):
        """설정 목록 새로고침"""
        self._clear_settings()

        if not self._selected_profile:
            return

        for setting in self._selected_profile.settings:
            is_default = setting.id == self._selected_profile.default_setting_id
            item = SettingItem(setting, is_default)
            item.edit_requested.connect(lambda s=setting: self._on_edit_setting(s))
            item.delete_requested.connect(lambda s=setting: self._on_delete_setting(s))
            item.set_default_requested.connect(lambda s=setting: self._on_set_default(s))

            # stretch 앞에 삽입
            self._settings_layout.insertWidget(self._settings_layout.count() - 1, item)

    def _clear_settings(self):
        """설정 목록 클리어"""
        while self._settings_layout.count() > 1:  # stretch 유지
            item = self._settings_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_new_profile(self):
        """새 프로파일"""
        name, ok = QInputDialog.getText(
            self,
            "New Profile",
            "Enter profile name:"
        )
        if ok and name.strip():
            profile = Profile.create_new(name.strip())
            self._profile_manager._current = profile
            self._refresh_profiles()
            # 새 프로파일 선택
            for i in range(self._profile_list.count()):
                item = self._profile_list.item(i)
                p = item.data(Qt.UserRole)
                if p and p.id == profile.id:
                    self._profile_list.setCurrentItem(item)
                    break

    def _on_import_profile(self):
        """프로파일 가져오기"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Profile",
            "",
            "Data Graph Profile (*.dgp)"
        )
        if path:
            try:
                profile = Profile.load(path)
                # profiles 디렉토리에 복사
                new_path = self._profile_manager.profiles_dir / f"{profile.name}.dgp"
                profile.save(str(new_path))
                self._refresh_profiles()
                QMessageBox.information(
                    self,
                    "Import Successful",
                    f"Profile '{profile.name}' imported successfully."
                )
            except Exception as e:
                logger.exception("profile_manager_dialog.import_profile.error")
                QMessageBox.critical(
                    self,
                    "Import Error",
                    f"Failed to import profile: {e}"
                )

    def _on_export_profile(self):
        """프로파일 내보내기"""
        if not self._selected_profile:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Profile",
            f"{self._selected_profile.name}.dgp",
            "Data Graph Profile (*.dgp)"
        )
        if path:
            try:
                self._selected_profile.save(path)
                QMessageBox.information(
                    self,
                    "Export Successful",
                    "Profile exported successfully."
                )
            except Exception as e:
                logger.exception("profile_manager_dialog.export_profile.error")
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export profile: {e}"
                )

    def _on_delete_profile(self):
        """프로파일 삭제"""
        if not self._selected_profile:
            return

        current_item = self._profile_list.currentItem()
        if not current_item:
            return

        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Are you sure you want to delete '{self._selected_profile.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            path = current_item.data(Qt.UserRole + 1)
            if path:
                self._profile_manager.delete_profile(path)

            # 현재 프로파일이면 클리어
            if self._profile_manager.current_profile and \
               self._profile_manager.current_profile.id == self._selected_profile.id:
                self._profile_manager._current = None

            self._refresh_profiles()
            self._clear_settings()

    def _on_edit_setting(self, setting: GraphSetting):
        """설정 편집"""
        from .save_setting_dialog import SaveSettingDialog

        dialog = SaveSettingDialog(self, existing_setting=setting)
        if dialog.exec() == QDialog.Accepted:
            self._refresh_settings()

    def _on_delete_setting(self, setting: GraphSetting):
        """설정 삭제"""
        reply = QMessageBox.question(
            self,
            "Delete Setting",
            f"Are you sure you want to delete '{setting.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self._selected_profile:
                self._selected_profile.remove_setting(setting.id)
                self._refresh_settings()

    def _on_set_default(self, setting: GraphSetting):
        """기본 설정으로 지정"""
        if self._selected_profile:
            self._selected_profile.default_setting_id = setting.id
            self._refresh_settings()

    def get_selected_profile(self) -> Optional[Profile]:
        """선택된 프로파일 반환"""
        return self._selected_profile
