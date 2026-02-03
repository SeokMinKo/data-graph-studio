"""
Undo Manager — PRD Section 7

Provides UndoActionType, UndoAction, and UndoStack for managing
undo/redo operations across the application.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


class UndoActionType(Enum):
    """Undo 가능한 동작 유형 — PRD Section 6.6"""
    ANNOTATION_ADD = "annotation_add"
    ANNOTATION_DELETE = "annotation_delete"
    ANNOTATION_EDIT = "annotation_edit"
    COLUMN_ADD = "column_add"
    COLUMN_DELETE = "column_delete"
    COLUMN_EDIT = "column_edit"
    DASHBOARD_LAYOUT_CHANGE = "dashboard_layout_change"
    DASHBOARD_CELL_ASSIGN = "dashboard_cell_assign"
    DASHBOARD_CELL_REMOVE = "dashboard_cell_remove"


@dataclass
class UndoAction:
    """단일 Undo 가능 동작 — PRD Section 6.6"""
    action_type: UndoActionType
    timestamp: float
    description: str
    before_state: Any = None
    after_state: Any = None
    dataset_id: Optional[str] = None
    profile_id: Optional[str] = None


class UndoStack:
    """
    Undo/Redo 스택 관리자 — PRD Section 7.2

    - max_depth=50 (FIFO: 초과 시 가장 오래된 항목 제거)
    - push 시 redo 스택 초기화
    - 복합 동작 (begin_compound / end_compound) 지원
    """

    def __init__(self, max_depth: int = 50):
        self.max_depth: int = max_depth
        self._undo_stack: List[UndoAction] = []
        self._redo_stack: List[UndoAction] = []

        # Compound action state
        self._compound_active: bool = False
        self._compound_description: str = ""
        self._compound_actions: List[UndoAction] = []

    # ── Public API ────────────────────────────────────────────

    def push(self, action: UndoAction) -> None:
        """
        동작을 undo 스택에 추가.
        - redo 스택 초기화
        - max_depth 초과 시 가장 오래된 항목 제거
        - compound 진행 중이면 compound 버퍼에 추가
        """
        if self._compound_active:
            self._compound_actions.append(action)
            return

        self._redo_stack.clear()
        self._undo_stack.append(action)
        self._enforce_max_depth()

    def undo(self) -> Optional[UndoAction]:
        """undo 스택에서 pop → redo 스택에 push. 비어있으면 None."""
        if not self._undo_stack:
            return None
        action = self._undo_stack.pop()
        self._redo_stack.append(action)
        return action

    def redo(self) -> Optional[UndoAction]:
        """redo 스택에서 pop → undo 스택에 push. 비어있으면 None."""
        if not self._redo_stack:
            return None
        action = self._redo_stack.pop()
        self._undo_stack.append(action)
        return action

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def clear(self) -> None:
        """파일/프로젝트 전환 시 전체 초기화"""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._compound_active = False
        self._compound_description = ""
        self._compound_actions.clear()

    # ── Compound Actions ──────────────────────────────────────

    def begin_compound(self, description: str) -> None:
        """
        복합 동작 시작.
        이미 compound 진행 중이면 무시 (중첩 미지원).
        """
        if self._compound_active:
            return
        self._compound_active = True
        self._compound_description = description
        self._compound_actions.clear()

    def end_compound(self) -> None:
        """
        복합 동작 종료.
        수집된 sub-actions를 하나의 UndoAction으로 합쳐서 push.
        빈 compound는 무시.
        """
        if not self._compound_active:
            return

        self._compound_active = False
        sub_actions = list(self._compound_actions)
        self._compound_actions.clear()

        if not sub_actions:
            return

        # Compound action: before_state에 sub-action 목록, after_state에도 목록
        compound_action = UndoAction(
            action_type=sub_actions[0].action_type,
            timestamp=time.time(),
            description=self._compound_description,
            before_state=[a.before_state for a in sub_actions],
            after_state=[a.after_state for a in sub_actions],
            dataset_id=sub_actions[0].dataset_id,
            profile_id=sub_actions[0].profile_id,
        )

        # Push directly (bypassing compound check since we already deactivated it)
        self._redo_stack.clear()
        self._undo_stack.append(compound_action)
        self._enforce_max_depth()

    # ── Internal ──────────────────────────────────────────────

    def _enforce_max_depth(self) -> None:
        """undo 스택이 max_depth를 초과하면 가장 오래된 항목부터 제거"""
        while len(self._undo_stack) > self.max_depth:
            self._undo_stack.pop(0)
