"""
AnnotationPanel — 주석 리스트 사이드 패널

PRD Section 5.4, Feature 5 (3.5.x)

- 주석 리스트 표시 (사이드 패널, 토글 가능)
- 각 주석 항목: 아이콘 + 색상 + 텍스트 미리보기 + 좌표
- 항목 클릭 → 해당 차트 위치로 이동 (navigate_to_annotation signal)
- 표시/숨기기 토글
"""

from __future__ import annotations

from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QFrame,
    QCheckBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from ...core.annotation import Annotation
from ...core.annotation_controller import AnnotationController


class AnnotationPanel(QFrame):
    """
    주석 리스트 사이드 패널.

    Signals:
        navigate_requested(str): 주석 ID → 해당 좌표로 이동 요청
        edit_requested(str): 주석 ID → 편집 다이얼로그 요청
        delete_requested(str): 주석 ID → 삭제 요청
        visibility_toggled(bool): 주석 표시/숨기기 토글
    """

    navigate_requested = Signal(str)
    edit_requested = Signal(str)
    delete_requested = Signal(str)
    visibility_toggled = Signal(bool)

    def __init__(
        self,
        controller: AnnotationController,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._controller = controller
        self._current_profile_id: Optional[str] = None
        self._annotations_visible = True

        self.setObjectName("AnnotationPanel")
        self.setMinimumWidth(220)
        self.setMaximumWidth(320)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # ── Header ──
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QLabel("📌 Annotations")
        header.setObjectName("sectionHeader")
        header_layout.addWidget(header)

        header_layout.addStretch()

        # 표시/숨기기 토글
        self._visibility_check = QCheckBox("Show")
        self._visibility_check.setToolTip("Toggle annotation visibility on chart")
        self._visibility_check.setChecked(True)
        self._visibility_check.stateChanged.connect(self._on_visibility_changed)
        header_layout.addWidget(self._visibility_check)

        layout.addLayout(header_layout)

        # ── 카운트 라벨 ──
        self._count_label = QLabel("0 annotations")
        self._count_label.setObjectName("hintLabel")
        layout.addWidget(self._count_label)

        # ── 리스트 ──
        self._list_widget = QListWidget()
        self._list_widget.setObjectName("annotationList")
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list_widget)

        # ── 하단 버튼 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self._delete_orphaned_btn = QPushButton("Clean Orphaned")
        self._delete_orphaned_btn.setObjectName("smallButton")
        self._delete_orphaned_btn.setToolTip("Remove annotations referencing deleted datasets")
        self._delete_orphaned_btn.clicked.connect(self._on_delete_orphaned)
        btn_layout.addWidget(self._delete_orphaned_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    # ── Public API ──────────────────────────────────────────

    def set_profile(self, profile_id: Optional[str]) -> None:
        """현재 프로파일 설정 및 리스트 갱신."""
        self._current_profile_id = profile_id
        self.refresh()

    def refresh(self) -> None:
        """리스트를 컨트롤러에서 다시 로드."""
        self._list_widget.clear()

        if self._current_profile_id:
            annotations = self._controller.list_by_profile(self._current_profile_id)
        else:
            annotations = self._controller.list_all()

        for ann in annotations:
            self._add_item(ann)

        self._count_label.setText(f"{len(annotations)} annotations")

    # ── Private ─────────────────────────────────────────────

    def _add_item(self, ann: Annotation) -> None:
        """주석 항목을 리스트에 추가."""
        # 텍스트 미리보기 (30자 제한)
        preview = ann.text[:30] + ("…" if len(ann.text) > 30 else "")

        # 좌표 정보
        if ann.kind == "range":
            coord = f"x: {ann.x:.1f} ~ {ann.x_end:.1f}"
        else:
            coord = f"({ann.x:.1f}, {ann.y:.1f})" if ann.y is not None else f"x: {ann.x:.1f}"

        label = f"{ann.icon} {preview}  {coord}"

        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, ann.id)

        # 색상 표시
        if ann.is_orphaned:
            item.setForeground(QColor("#888888"))  # 회색 (orphaned)
            item.setToolTip(f"[Orphaned] {ann.text}")
        else:
            item.setForeground(QColor(ann.color))
            item.setToolTip(ann.text)

        self._list_widget.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """항목 클릭 → 해당 위치로 이동."""
        ann_id = item.data(Qt.UserRole)
        if ann_id:
            self.navigate_requested.emit(ann_id)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """항목 더블클릭 → 편집."""
        ann_id = item.data(Qt.UserRole)
        if ann_id:
            self.edit_requested.emit(ann_id)

    def _on_visibility_changed(self, state: int) -> None:
        """표시/숨기기 토글."""
        self._annotations_visible = state == Qt.Checked
        self.visibility_toggled.emit(self._annotations_visible)

    def _on_delete_orphaned(self) -> None:
        """Orphaned 주석 일괄 삭제."""
        deleted = self._controller.delete_orphaned()
        if deleted > 0:
            self.refresh()

    @property
    def annotations_visible(self) -> bool:
        """주석 표시 여부."""
        return self._annotations_visible
