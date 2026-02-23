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
from .exceptions import ValidationError
from .types import AnnotationId

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
        """Initialize the AnnotationController with an empty annotation store.

        Input: undo_manager — Any, optional UndoManager instance; when provided,
            mutating operations push undo snapshots; defaults to None (no undo)
        Output: None
        Invariants: _annotations is empty; _undo_manager is stored as-is
        """
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
            except (ValidationError, TypeError, ValueError):
                logger.warning("annotation_controller.restore_state.invalid_entry", extra={"aid": aid}, exc_info=True)
                continue

    # ── CRUD ──────────────────────────────────────────────────

    def add(self, annotation: Annotation) -> AnnotationId:
        """Store a new annotation in the controller.

        Input: annotation — Annotation, the annotation to store; text must not exceed MAX_ANNOTATION_TEXT_LENGTH characters
        Output: None
        Raises: ValueError — if annotation.text exceeds MAX_ANNOTATION_TEXT_LENGTH characters (ERR-5.1)
        Invariants: annotation is reachable via get(annotation.id) after this call; undo snapshot is pushed when undo_manager is set
        """
        # 텍스트 길이 재검증 (dataclass __post_init__에서도 체크하지만 명시적 확인)
        if len(annotation.text) > MAX_ANNOTATION_TEXT_LENGTH:
            raise ValidationError(
                f"Annotation text exceeds {MAX_ANNOTATION_TEXT_LENGTH} characters "
                f"(got {len(annotation.text)})",
                operation="add",
                context={"text_length": len(annotation.text), "max_length": MAX_ANNOTATION_TEXT_LENGTH},
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
        return AnnotationId(annotation.id)

    def get(self, annotation_id: AnnotationId) -> Optional[Annotation]:
        """Return an annotation by its ID.

        Input: annotation_id — str, the ID of the annotation to look up
        Output: Annotation if found, or None if no annotation has that ID
        """
        return self._annotations.get(annotation_id)

    def edit(self, annotation_id: AnnotationId, **kwargs: Any) -> bool:
        """Update fields on an existing annotation.

        Input: annotation_id — str, ID of the annotation to modify;
               **kwargs — field names and new values (e.g. text, color, icon); unknown fields are silently skipped
        Output: bool — True if the annotation was found and updated, False if not found
        Raises: ValueError — if a new text value exceeds MAX_ANNOTATION_TEXT_LENGTH characters
        Invariants: only fields present on the Annotation dataclass are mutated; undo snapshot is pushed when undo_manager is set
        """
        ann = self._annotations.get(annotation_id)
        if ann is None:
            return False

        # 텍스트 길이 검증
        new_text = kwargs.get("text")
        if new_text is not None and len(new_text) > MAX_ANNOTATION_TEXT_LENGTH:
            raise ValidationError(
                f"Annotation text exceeds {MAX_ANNOTATION_TEXT_LENGTH} characters "
                f"(got {len(new_text)})",
                operation="edit",
                context={"text_length": len(new_text), "max_length": MAX_ANNOTATION_TEXT_LENGTH},
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

    def delete(self, annotation_id: AnnotationId) -> bool:
        """Remove an annotation by ID.

        Input: annotation_id — str, ID of the annotation to delete
        Output: bool — True if the annotation was found and deleted, False if not found
        Invariants: annotation_id is absent from _annotations after a successful deletion; undo snapshot is pushed when undo_manager is set
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
        """Return all stored annotations as a list.

        Output: List[Annotation] — all annotations in insertion order; empty list if none exist
        """
        return list(self._annotations.values())

    def list_by_profile(self, profile_id: str) -> List[Annotation]:
        """Return all annotations associated with a given profile.

        Input: profile_id — str, the profile ID to filter by
        Output: List[Annotation] — annotations whose profile_id matches; empty if none match
        """
        return [a for a in self._annotations.values() if a.profile_id == profile_id]

    def list_by_dataset(self, dataset_id: str) -> List[Annotation]:
        """Return all annotations associated with a given dataset.

        Input: dataset_id — str, the dataset ID to filter by
        Output: List[Annotation] — annotations whose dataset_id matches; empty if none match
        """
        return [a for a in self._annotations.values() if a.dataset_id == dataset_id]

    # ── 좌표 변환 ────────────────────────────────────────────

    @staticmethod
    def data_to_screen(
        data_x: float,
        data_y: float,
        view_rect: Dict[str, float],
        screen_size: Dict[str, int],
    ) -> Tuple[float, float]:
        """Convert a data-space coordinate to a screen-space pixel position.

        Input: data_x — float, data-space X value;
               data_y — float, data-space Y value;
               view_rect — Dict with keys x_min, x_max, y_min, y_max defining the visible data range;
               screen_size — Dict with keys width and height in pixels
        Output: Tuple[float, float] — (screen_x, screen_y) pixel coordinates; returns (0.0, 0.0) if x_range or y_range is zero
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
        """Convert a screen-space pixel position back to a data-space coordinate.

        Input: screen_x — float, pixel X position on screen;
               screen_y — float, pixel Y position on screen;
               view_rect — Dict with keys x_min, x_max, y_min, y_max defining the visible data range;
               screen_size — Dict with keys width and height in pixels
        Output: Tuple[float, float] — (data_x, data_y) values in data space
        """
        x_range = view_rect["x_max"] - view_rect["x_min"]
        y_range = view_rect["y_max"] - view_rect["y_min"]

        data_x = screen_x / screen_size["width"] * x_range + view_rect["x_min"]
        data_y = screen_y / screen_size["height"] * y_range + view_rect["y_min"]

        return (data_x, data_y)

    # ── Orphaned 감지 / 처리 ─────────────────────────────────

    def find_orphaned(self, active_dataset_ids: Set[str]) -> List[Annotation]:
        """Return annotations whose dataset_id is not in the active dataset set (ERR-5.3).

        Input: active_dataset_ids — Set[str], IDs of datasets currently loaded in the application
        Output: List[Annotation] — annotations referencing datasets absent from active_dataset_ids; empty if all are valid
        """
        return [
            a
            for a in self._annotations.values()
            if a.dataset_id not in active_dataset_ids
        ]

    def mark_orphaned(self, active_dataset_ids: Set[str]) -> None:
        """Set is_orphaned on every annotation to reflect whether its dataset is currently active.

        Input: active_dataset_ids — Set[str], IDs of datasets currently loaded in the application
        Output: None
        Invariants: annotation.is_orphaned is True iff annotation.dataset_id not in active_dataset_ids for every annotation
        """
        for ann in self._annotations.values():
            ann.is_orphaned = ann.dataset_id not in active_dataset_ids

    def delete_orphaned(self) -> int:
        """Delete all annotations currently flagged as orphaned.

        Output: int — number of annotations deleted
        Invariants: no annotation with is_orphaned == True remains in _annotations after this call
        """
        orphaned_ids = [
            aid for aid, ann in self._annotations.items() if ann.is_orphaned
        ]
        for aid in orphaned_ids:
            del self._annotations[aid]
        return len(orphaned_ids)

    # ── 프로파일 연동 ────────────────────────────────────────

    def export_for_profile(self, profile_id: str) -> List[Dict]:
        """Serialize all annotations for a profile into a list of dicts suitable for JSON persistence.

        Input: profile_id — str, the profile whose annotations to export
        Output: List[Dict] — one dict per annotation produced by Annotation.to_dict(); empty if none exist
        """
        return [a.to_dict() for a in self.list_by_profile(profile_id)]

    def import_for_profile(self, profile_id: str, data: List[Dict]) -> None:
        """Replace a profile's annotations by deserializing a list of dicts.

        Input: profile_id — str, the profile to restore annotations for;
               data — List[Dict], annotation dicts as produced by export_for_profile
        Output: None
        Invariants: all existing annotations for profile_id are cleared before import; each imported annotation has its profile_id forced to profile_id
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
        """Remove all annotations belonging to a given profile.

        Input: profile_id — str, the profile whose annotations should be deleted
        Output: None
        Invariants: no annotation with annotation.profile_id == profile_id remains in _annotations after this call
        """
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
