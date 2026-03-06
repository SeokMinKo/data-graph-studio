"""
ShortcutEditDialog — FR-7.3 ~ FR-7.5: 단축키 커스터마이징 UI

- FR-7.3: 키 조합 변경
- FR-7.4: 충돌 감지 경고
- FR-7.5: 설정 영속화
"""

from typing import Optional, Dict

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QHeaderView,
    QWidget,
    QMessageBox,
    QKeySequenceEdit,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QFont

from ...core.shortcut_controller import ShortcutController


class ShortcutEditDialog(QDialog):
    """
    단축키 커스터마이징 다이얼로그

    ┌──────────────────────────────────────────┐
    │ Customize Shortcuts                 [✕]  │
    │──────────────────────────────────────────│
    │  Category / Action    Shortcut    [Edit] │
    │  ▼ File                                  │
    │    Open File          Ctrl+O      [...]  │
    │    Save Profile       Ctrl+S      [...]  │
    │  ...                                     │
    │──────────────────────────────────────────│
    │  [Reset All]          [Cancel] [Save]    │
    └──────────────────────────────────────────┘
    """

    shortcut_changed = Signal(str, str)  # shortcut_id, new_keys

    def __init__(
        self, controller: ShortcutController, parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self._controller = controller
        self._pending_changes: Dict[str, str] = {}  # id -> new_keys
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Customize Shortcuts")
        self.setMinimumSize(600, 500)
        self.resize(650, 600)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel("Customize Keyboard Shortcuts")
        header_font = QFont()
        header_font.setPointSize(14)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        info = QLabel(
            "Double-click on a shortcut to change it. "
            "Press the new key combination when prompted."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Action", "Shortcut", "Status"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(20)

        header_view = self._tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._populate_tree()
        layout.addWidget(self._tree)

        # Buttons
        btn_layout = QHBoxLayout()

        reset_all_btn = QPushButton("Reset All to Defaults")
        reset_all_btn.setToolTip("Reset all shortcuts to their default key bindings")
        reset_all_btn.clicked.connect(self._on_reset_all)
        btn_layout.addWidget(reset_all_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Discard changes and close")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setToolTip("Save shortcut changes")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _populate_tree(self):
        """카테고리별로 단축키를 트리에 추가"""
        self._tree.clear()
        self._item_map: Dict[str, QTreeWidgetItem] = {}

        categories = self._controller.get_shortcuts_by_category()

        for category_name, shortcuts in categories.items():
            category_item = QTreeWidgetItem(self._tree, [category_name, "", ""])
            category_font = QFont()
            category_font.setBold(True)
            category_item.setFont(0, category_font)
            category_item.setExpanded(True)

            for shortcut in shortcuts:
                keys_str = (
                    shortcut.keys.toString()
                    if isinstance(shortcut.keys, QKeySequence)
                    else str(shortcut.keys)
                )

                status = ""
                if shortcut.id in self._controller.get_customized():
                    status = "Modified"

                item = QTreeWidgetItem(category_item, [shortcut.name, keys_str, status])
                item.setData(0, Qt.UserRole, shortcut.id)
                self._item_map[shortcut.id] = item

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """더블 클릭 시 키 변경 다이얼로그"""
        shortcut_id = item.data(0, Qt.UserRole)
        if not shortcut_id:
            return  # 카테고리 노드

        current_keys = item.text(1)

        # 간단한 키 입력 다이얼로그
        dlg = _KeyCaptureDialog(
            shortcut_id=shortcut_id,
            current_keys=current_keys,
            controller=self._controller,
            parent=self,
        )

        if dlg.exec() == QDialog.Accepted:
            new_keys = dlg.captured_keys()
            if new_keys and new_keys != current_keys:
                # 경고 확인
                warnings = self._controller.get_conflict_warnings(shortcut_id, new_keys)
                if warnings:
                    msg = "\n".join(warnings)
                    reply = QMessageBox.warning(
                        self,
                        "Shortcut Conflict",
                        msg,
                        QMessageBox.Yes | QMessageBox.Cancel,
                        QMessageBox.Cancel,
                    )
                    if reply != QMessageBox.Yes:
                        return

                # 변경 기록
                self._pending_changes[shortcut_id] = new_keys
                item.setText(1, new_keys)
                item.setText(2, "Modified*")

    def _on_reset_all(self):
        """전체 단축키 초기화"""
        reply = QMessageBox.question(
            self,
            "Reset All Shortcuts",
            "Reset all shortcuts to their default values?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._controller.reset_all()
            self._pending_changes.clear()
            self._populate_tree()

    def _on_save(self):
        """변경사항 저장"""
        for shortcut_id, new_keys in self._pending_changes.items():
            self._controller.set_custom_keys(shortcut_id, new_keys, force=True)
            self.shortcut_changed.emit(shortcut_id, new_keys)

        self._controller.save_config()
        self.accept()


class _KeyCaptureDialog(QDialog):
    """키 조합 캡처 다이얼로그"""

    def __init__(
        self,
        shortcut_id: str,
        current_keys: str,
        controller: ShortcutController,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._shortcut_id = shortcut_id
        self._current_keys = current_keys
        self._controller = controller
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Set Shortcut")
        self.setFixedSize(350, 150)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Press the new key combination:"))

        self._key_edit = QKeySequenceEdit()
        self._key_edit.setToolTip("Press the desired key combination")
        if self._current_keys:
            self._key_edit.setKeySequence(QKeySequence(self._current_keys))
        layout.addWidget(self._key_edit)

        self._warning_label = QLabel("")
        self._warning_label.setStyleSheet("color: #ff6b6b;")
        self._warning_label.setWordWrap(True)
        layout.addWidget(self._warning_label)

        self._key_edit.keySequenceChanged.connect(self._on_key_changed)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_key_changed(self, seq: QKeySequence):
        """키 변경 시 실시간 경고"""
        keys_str = seq.toString()
        if not keys_str:
            self._warning_label.setText("")
            return

        warnings = self._controller.get_conflict_warnings(self._shortcut_id, keys_str)
        if warnings:
            self._warning_label.setText("\n".join(warnings))
        else:
            self._warning_label.setText("")

    def captured_keys(self) -> str:
        """캡처된 키 조합 반환"""
        return self._key_edit.keySequence().toString()
