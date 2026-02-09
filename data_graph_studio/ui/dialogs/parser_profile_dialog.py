"""Parser Profile Dialog - select, create, edit, delete parser profiles."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from data_graph_studio.parsers.base import BaseParser, ParserProfile, ParserProfileStore


class ParserProfileDialog(QDialog):
    """프로파일 선택/관리 다이얼로그.

    - 왼쪽: 프로파일 목록 + 추가/삭제 버튼
    - 오른쪽: 선택된 프로파일의 settings JSON 편집기
    - 하단: OK(선택) / Cancel
    - "(Default)" 항목은 항상 맨 위에 표시 (parser의 default_settings 사용)
    """

    DEFAULT_LABEL = "(Default)"

    def __init__(
        self,
        parser: BaseParser,
        store: ParserProfileStore,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._parser = parser
        self._store = store
        self._selected_settings: Dict[str, Any] = parser.default_settings()

        self.setWindowTitle(f"{parser.name} - Profile")
        self.setMinimumSize(600, 400)
        self.resize(700, 450)

        self._build_ui()
        self._populate_profiles()
        self._connect_signals()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        # --- Left: profile list ---
        left = QVBoxLayout()
        left.addWidget(QLabel("Profiles"))

        self._list = QListWidget()
        left.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("Add")
        self._rename_btn = QPushButton("Rename")
        self._delete_btn = QPushButton("Delete")
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._rename_btn)
        btn_row.addWidget(self._delete_btn)
        left.addLayout(btn_row)

        root.addLayout(left, 1)

        # --- Right: settings editor ---
        right = QVBoxLayout()
        right.addWidget(QLabel("Settings (JSON)"))

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("{}")
        right.addWidget(self._editor, 1)

        self._save_btn = QPushButton("Save Profile")
        right.addWidget(self._save_btn)

        root.addLayout(right, 2)

        # --- Bottom buttons ---
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        # Span full width below both panels
        wrapper = QVBoxLayout()
        wrapper.addLayout(root)
        wrapper.addWidget(self._button_box)
        # Re-set layout
        QWidget().setLayout(self.layout())  # detach old
        self.setLayout(wrapper)

    def _connect_signals(self) -> None:
        self._list.currentRowChanged.connect(self._on_profile_selected)
        self._add_btn.clicked.connect(self._on_add)
        self._rename_btn.clicked.connect(self._on_rename)
        self._delete_btn.clicked.connect(self._on_delete)
        self._save_btn.clicked.connect(self._on_save)
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)

    # ----------------------------------------------------------- populate

    def _populate_profiles(self) -> None:
        self._list.clear()

        # Always show Default first
        default_item = QListWidgetItem(self.DEFAULT_LABEL)
        default_item.setData(Qt.UserRole, None)  # sentinel
        self._list.addItem(default_item)

        for profile in self._store.list_profiles(self._parser.key):
            item = QListWidgetItem(profile.name)
            item.setData(Qt.UserRole, profile.name)
            self._list.addItem(item)

        self._list.setCurrentRow(0)

    # ----------------------------------------------------------- slots

    def _on_profile_selected(self, row: int) -> None:
        if row < 0:
            return
        item = self._list.item(row)
        profile_name = item.data(Qt.UserRole)

        if profile_name is None:
            # Default
            settings = self._parser.default_settings()
            self._editor.setReadOnly(True)
        else:
            profile = self._store.get_profile(self._parser.key, profile_name)
            settings = profile.settings if profile else {}
            self._editor.setReadOnly(False)

        self._editor.setPlainText(json.dumps(settings, ensure_ascii=False, indent=2))
        is_default = profile_name is None
        self._rename_btn.setEnabled(not is_default)
        self._delete_btn.setEnabled(not is_default)
        self._save_btn.setEnabled(not is_default)

    def _on_add(self) -> None:
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name == self.DEFAULT_LABEL:
            QMessageBox.warning(self, "Error", "Cannot use reserved name.")
            return

        profile = ParserProfile(name, self._parser.default_settings())
        self._store.save_profile(self._parser.key, profile)
        self._populate_profiles()

        # Select the new profile
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.UserRole) == name:
                self._list.setCurrentRow(i)
                break

    def _on_rename(self) -> None:
        item = self._list.currentItem()
        if item is None or item.data(Qt.UserRole) is None:
            return
        old_name = item.data(Qt.UserRole)
        new_name, ok = QInputDialog.getText(
            self, "Rename Profile", "New name:", text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        self._store.rename_profile(self._parser.key, old_name, new_name.strip())
        self._populate_profiles()

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if item is None or item.data(Qt.UserRole) is None:
            return
        name = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "Delete Profile", f"Delete '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._store.delete_profile(self._parser.key, name)
            self._populate_profiles()

    def _on_save(self) -> None:
        item = self._list.currentItem()
        if item is None or item.data(Qt.UserRole) is None:
            return
        name = item.data(Qt.UserRole)
        try:
            settings = json.loads(self._editor.toPlainText())
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", str(e))
            return

        profile = ParserProfile(name, settings)
        self._store.save_profile(self._parser.key, profile)
        self.statusBar() if hasattr(self, 'statusBar') else None
        QMessageBox.information(self, "Saved", f"Profile '{name}' saved.")

    def _on_accept(self) -> None:
        """OK 버튼: 현재 에디터의 settings를 선택된 설정으로 저장하고 닫기."""
        try:
            self._selected_settings = json.loads(self._editor.toPlainText())
        except json.JSONDecodeError:
            self._selected_settings = self._parser.default_settings()
        self.accept()

    # ----------------------------------------------------------- public

    def get_selected_settings(self) -> Dict[str, Any]:
        """Return the settings dict selected by the user."""
        return self._selected_settings
