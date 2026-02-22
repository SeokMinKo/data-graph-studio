"""
AnnotationController — 주석 CRUD 및 관리

PRD Section 9.2, Feature 5 (3.5.x)

- Annotation CRUD (add, edit, delete, list)
- 프로파일 연동 (저장/복원)
- 좌표 변환 (데이터 좌표 ↔ 화면 좌표)
- Orphaned annotation 감지/처리
- UndoManager 연동 (optional)
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

from .annotation import Annotation, MAX_ANNOTATION_TEXT_LENGTH

# UndoManager는 다른 에이전트가 구현 중 — optional import
try:
    from .undo_manager import UndoStack, UndoCommand, UndoActionType
except ImportError:  # pragma: no cover
    UndoStack = None  # type: ignore[assignment,misc]
    UndoCommand = None  # type: ignore[assignment,misc]
    UndoActionType = None  # type: ignore[assignment,misc]


class AnnotationController:
    """
    Annotation CRUD 및 관리 컨트롤러.

    Parameters:
        undo_manager: Optional UndoManager 인스턴스. 없으면 undo 없이 동작.
    """

    def __init__(self, undo_manager: Any = None):
        self._annotations: Dict[str, Annotation] = {}
        self._undo_manager = undo_manager

    def _snapshot_for_undo(self) -> Dict[str, Dict]:
        """Snapshot all annotations for undo/redo (small enough in practice)."""
        return {aid: copy.deepcopy(ann.to_dict()) for aid, ann in self._annotations.items()}

    def _restore_from_undo_state(self, state: Any) -> None:
        """Restore annotations from a snapshot."""
        if state is None:
            self._annotations.clear()
            return
        if not isinstance(state, dict):
            return

        self._annotations.clear()
        for aid, ann_dict in state.items():
            try:
                ann = Annotation.from_dict(ann_dict)
                self._annotations[aid] = ann
            except Exception:
                continue

    # ── CRUD ──────────────────────────────────────────────────

    def add(self, annotation: Annotation) -> None:
        """
        주석 추가.

        Raises:
            ValueError: 텍스트가 200자 초과 시 (ERR-5.1)
        """
        # 텍스트 길이 재검증 (dataclass __post_init__에서도 체크하지만 명시적 확인)
        if len(annotation.text) > MAX_ANNOTATION_TEXT_LENGTH:
            raise ValueError(
                f"Annotation text exceeds {MAX_ANNOTATION_TEXT_LENGTH} characters "
                f"(got {len(annotation.text)})"
            )

        before = self._snapshot_for_undo()
        self._annotations[annotation.id] = annotation
        after = self._snapshot_for_undo()

        logger.debug("annotation_controller.add", extra={"annotation_id": annotation.id})
        # Undo 지원
        self._push_undo(
            description=f"Add annotation '{annotation.text[:30]}'",
            before_state=before,
            after_state=after,
            action_type_name="ANNOTATION_ADD",
        )

    def get(self, annotation_id: str) -> Optional[Annotation]:
        """ID로 주석 조회."""
        return self._annotations.get(annotation_id)

    def edit(self, annotation_id: str, **kwargs: Any) -> bool:
        """
        주석 편집.

        Parameters:
            annotation_id: 대상 주석 ID
            **kwargs: 변경할 필드 (text, color, icon 등)

        Returns:
            True if edited, False if not found.

        Raises:
            ValueError: 텍스트가 200자 초과 시
        """
        ann = self._annotations.get(annotation_id)
        if ann is None:
            return False

        # 텍스트 길이 검증
        new_text = kwargs.get("text")
        if new_text is not None and len(new_text) > MAX_ANNOTATION_TEXT_LENGTH:
            raise ValueError(
                f"Annotation text exceeds {MAX_ANNOTATION_TEXT_LENGTH} characters "
                f"(got {len(new_text)})"
            )

        before = self._snapshot_for_undo()

        # 필드 업데이트
        for key, value in kwargs.items():
            if hasattr(ann, key):
                object.__setattr__(ann, key, value)

        after = self._snapshot_for_undo()

        logger.debug("annotation_controller.edit", extra={"annotation_id": annotation_id})
        self._push_undo(
            description=f"Edit annotation '{ann.text[:30]}'",
            before_state=before,
            after_state=after,
            action_type_name="ANNOTATION_EDIT",
        )

        return True

    def delete(self, annotation_id: str) -> bool:
        """
        주석 삭제.

        Returns:
            True if deleted, False if not found.
        """
        before = self._snapshot_for_undo()
        ann = self._annotations.pop(annotation_id, None)
        if ann is None:
            logger.warning("annotation_controller.delete.not_found", extra={"annotation_id": annotation_id})
            return False
        after = self._snapshot_for_undo()

        logger.debug("annotation_controller.delete", extra={"annotation_id": annotation_id})
        self._push_undo(
            description=f"Delete annotation '{ann.text[:30]}'",
            before_state=before,
            after_state=after,
            action_type_name="ANNOTATION_DELETE",
        )

        return True

    # ── List / Query ──────────────────────────────────────────

    def list_all(self) -> List[Annotation]:
        """모든 주석 리스트."""
        return list(self._annotations.values())

    def list_by_profile(self, profile_id: str) -> List[Annotation]:
        """프로파일별 주석 리스트."""
        return [a for a in self._annotations.values() if a.profile_id == profile_id]

    def list_by_dataset(self, dataset_id: str) -> List[Annotation]:
        """데이터셋별 주석 리스트."""
        return [a for a in self._annotations.values() if a.dataset_id == dataset_id]

    # ── 좌표 변환 ────────────────────────────────────────────

    @staticmethod
    def data_to_screen(
        data_x: float,
        data_y: float,
        view_rect: Dict[str, float],
        screen_size: Dict[str, int],
    ) -> Tuple[float, float]:
        """
        데이터 좌표 → 화면 좌표 변환.

        Parameters:
            data_x: 데이터 X 좌표
            data_y: 데이터 Y 좌표
            view_rect: 현재 뷰 범위 {"x_min", "x_max", "y_min", "y_max"}
            screen_size: 화면 크기 {"width", "height"}

        Returns:
            (screen_x, screen_y) 튜플
        """
        x_range = view_rect["x_max"] - view_rect["x_min"]
        y_range = view_rect["y_max"] - view_rect["y_min"]

        if x_range == 0 or y_range == 0:
            return (0.0, 0.0)

        screen_x = (data_x - view_rect["x_min"]) / x_range * screen_size["width"]
        screen_y = (data_y - view_rect["y_min"]) / y_range * screen_size["height"]

        return (screen_x, screen_y)

    @staticmethod
    def screen_to_data(
        screen_x: float,
        screen_y: float,
        view_rect: Dict[str, float],
        screen_size: Dict[str, int],
    ) -> Tuple[float, float]:
        """
        화면 좌표 → 데이터 좌표 변환.

        Parameters:
            screen_x: 화면 X 좌표
            screen_y: 화면 Y 좌표
            view_rect: 현재 뷰 범위
            screen_size: 화면 크기

        Returns:
            (data_x, data_y) 튜플
        """
        x_range = view_rect["x_max"] - view_rect["x_min"]
        y_range = view_rect["y_max"] - view_rect["y_min"]

        data_x = screen_x / screen_size["width"] * x_range + view_rect["x_min"]
        data_y = screen_y / screen_size["height"] * y_range + view_rect["y_min"]

        return (data_x, data_y)

    # ── Orphaned 감지 / 처리 ─────────────────────────────────

    def find_orphaned(self, active_dataset_ids: Set[str]) -> List[Annotation]:
        """
        Orphaned 주석 감지 (ERR-5.3).

        Parameters:
            active_dataset_ids: 현재 활성 데이터셋 ID 집합

        Returns:
            orphaned 주석 리스트
        """
        return [
            a
            for a in self._annotations.values()
            if a.dataset_id not in active_dataset_ids
        ]

    def mark_orphaned(self, active_dataset_ids: Set[str]) -> None:
        """
        활성 데이터셋에 없는 주석을 orphaned로 표시.
        활성 데이터셋에 있는 주석은 orphaned 해제.
        """
        for ann in self._annotations.values():
            ann.is_orphaned = ann.dataset_id not in active_dataset_ids

    def delete_orphaned(self) -> int:
        """
        Orphaned 주석 일괄 삭제.

        Returns:
            삭제된 주석 수
        """
        orphaned_ids = [
            aid for aid, ann in self._annotations.items() if ann.is_orphaned
        ]
        for aid in orphaned_ids:
            del self._annotations[aid]
        return len(orphaned_ids)

    # ── 프로파일 연동 ────────────────────────────────────────

    def export_for_profile(self, profile_id: str) -> List[Dict]:
        """프로파일 저장 시 주석 데이터 내보내기."""
        return [a.to_dict() for a in self.list_by_profile(profile_id)]

    def import_for_profile(self, profile_id: str, data: List[Dict]) -> None:
        """
        프로파일 복원 시 주석 데이터 가져오기.
        기존 해당 프로파일 주석을 교체.
        """
        # 기존 프로파일 주석 제거
        self.clear_profile(profile_id)

        # 새 주석 추가
        for item in data:
            ann = Annotation.from_dict(item)
            # profile_id 강제 설정
            ann.profile_id = profile_id
            self._annotations[ann.id] = ann

    def clear_profile(self, profile_id: str) -> None:
        """특정 프로파일의 모든 주석 제거."""
        to_remove = [
            aid for aid, ann in self._annotations.items()
            if ann.profile_id == profile_id
        ]
        for aid in to_remove:
            del self._annotations[aid]

    # ── Undo 지원 (optional) ─────────────────────────────────

    def _push_undo(
        self,
        description: str,
        before_state: Any,
        after_state: Any,
        action_type_name: str = "ANNOTATION_ADD",
    ) -> None:
        """UndoManager에 액션 push (존재할 때만)."""
        if self._undo_manager is None:
            return
        if UndoCommand is None or UndoActionType is None:
            return  # pragma: no cover

        try:
            action_type = getattr(UndoActionType, action_type_name)
        except AttributeError:
            return  # pragma: no cover

        import time

        # Annotation change already happened; record with do/undo applying snapshots.
        def _apply(state: Any):
            self._restore_from_undo_state(state)

        self._undo_manager.record(
            UndoCommand(
                action_type=action_type,
                description=description,
                do=lambda: _apply(after_state),
                undo=lambda: _apply(before_state),
                timestamp=time.time(),
            )
        )
