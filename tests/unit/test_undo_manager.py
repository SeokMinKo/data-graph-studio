"""
Tests for UndoManager (UndoStack) — PRD Section 7

UT-8.1: UndoStack push/undo/redo 기본 동작
UT-8.2: UndoStack 최대 깊이(50) 초과 → 가장 오래된 항목 제거
UT-8.3: 새 동작 push → Redo 스택 초기화
UT-8.4: 복합 동작 (cascade 삭제) → 하나의 Undo로 전체 복원
"""

import time
import pytest

from data_graph_studio.core.undo_manager import (
    UndoActionType,
    UndoAction,
    UndoStack,
)


def _make_action(
    action_type: UndoActionType = UndoActionType.ANNOTATION_ADD,
    description: str = "test action",
    before_state=None,
    after_state=None,
) -> UndoAction:
    return UndoAction(
        action_type=action_type,
        timestamp=time.time(),
        description=description,
        before_state=before_state,
        after_state=after_state,
    )


# ── UT-8.1: push / undo / redo 기본 동작 ──────────────────────────


class TestUndoStackBasic:
    """UT-8.1: UndoStack push/undo/redo 기본 동작"""

    def test_initial_state(self):
        stack = UndoStack()
        assert not stack.can_undo()
        assert not stack.can_redo()

    def test_push_makes_undoable(self):
        stack = UndoStack()
        action = _make_action(description="add annotation")
        stack.push(action)
        assert stack.can_undo()
        assert not stack.can_redo()

    def test_undo_returns_action(self):
        stack = UndoStack()
        action = _make_action(description="add annotation", before_state="A", after_state="B")
        stack.push(action)

        result = stack.undo()
        assert result is not None
        assert result.description == "add annotation"
        assert result.before_state == "A"
        assert result.after_state == "B"

    def test_undo_then_redo(self):
        stack = UndoStack()
        action = _make_action(description="edit annotation")
        stack.push(action)

        undone = stack.undo()
        assert undone is not None
        assert not stack.can_undo()
        assert stack.can_redo()

        redone = stack.redo()
        assert redone is not None
        assert redone.description == "edit annotation"
        assert stack.can_undo()
        assert not stack.can_redo()

    def test_undo_empty_returns_none(self):
        stack = UndoStack()
        assert stack.undo() is None

    def test_redo_empty_returns_none(self):
        stack = UndoStack()
        assert stack.redo() is None

    def test_multiple_undo_redo(self):
        stack = UndoStack()
        for i in range(5):
            stack.push(_make_action(description=f"action {i}"))

        # Undo all 5
        descriptions = []
        for _ in range(5):
            a = stack.undo()
            assert a is not None
            descriptions.append(a.description)
        assert descriptions == [f"action {i}" for i in range(4, -1, -1)]

        # Redo all 5
        for _ in range(5):
            assert stack.redo() is not None
        assert not stack.can_redo()

    def test_clear(self):
        stack = UndoStack()
        stack.push(_make_action())
        stack.undo()
        stack.clear()
        assert not stack.can_undo()
        assert not stack.can_redo()


# ── UT-8.2: 최대 깊이 초과 → 가장 오래된 항목 제거 ──────────────


class TestUndoStackMaxDepth:
    """UT-8.2: UndoStack 최대 깊이(50) 초과 → 가장 오래된 항목 제거"""

    def test_default_max_depth_is_50(self):
        stack = UndoStack()
        assert stack.max_depth == 50

    def test_custom_max_depth(self):
        stack = UndoStack(max_depth=10)
        assert stack.max_depth == 10

    def test_oldest_removed_when_exceed(self):
        stack = UndoStack(max_depth=5)
        for i in range(7):
            stack.push(_make_action(description=f"action {i}"))

        # Should only have 5 items (actions 2-6)
        descriptions = []
        while stack.can_undo():
            a = stack.undo()
            descriptions.append(a.description)
        assert len(descriptions) == 5
        assert descriptions[0] == "action 6"  # most recent
        assert descriptions[-1] == "action 2"  # oldest surviving

    def test_max_depth_50_exactly(self):
        stack = UndoStack()
        for i in range(50):
            stack.push(_make_action(description=f"action {i}"))

        count = 0
        while stack.can_undo():
            stack.undo()
            count += 1
        assert count == 50

    def test_max_depth_51_drops_oldest(self):
        stack = UndoStack()
        for i in range(51):
            stack.push(_make_action(description=f"action {i}"))

        count = 0
        last_desc = None
        while stack.can_undo():
            a = stack.undo()
            last_desc = a.description
            count += 1
        assert count == 50
        assert last_desc == "action 1"  # action 0 was dropped


# ── UT-8.3: 새 동작 push → Redo 스택 초기화 ─────────────────────


class TestUndoStackRedoClear:
    """UT-8.3: 새 동작 push → Redo 스택 초기화"""

    def test_push_clears_redo(self):
        stack = UndoStack()
        stack.push(_make_action(description="action 1"))
        stack.push(_make_action(description="action 2"))
        stack.undo()
        assert stack.can_redo()

        # New push should clear redo stack
        stack.push(_make_action(description="action 3"))
        assert not stack.can_redo()

    def test_push_after_multiple_undos_clears_all_redo(self):
        stack = UndoStack()
        for i in range(5):
            stack.push(_make_action(description=f"action {i}"))

        # Undo 3 times → 3 items in redo
        stack.undo()
        stack.undo()
        stack.undo()
        assert stack.can_redo()

        # New push clears all 3 from redo
        stack.push(_make_action(description="new action"))
        assert not stack.can_redo()

        # Undo should show "new action" then "action 1" then "action 0"
        a = stack.undo()
        assert a.description == "new action"
        a = stack.undo()
        assert a.description == "action 1"


# ── UT-8.4: 복합 동작 → 하나의 Undo로 전체 복원 ─────────────────


class TestUndoStackCompound:
    """UT-8.4: 복합 동작 (cascade 삭제) → 하나의 Undo로 전체 복원"""

    def test_compound_single_undo(self):
        stack = UndoStack()

        # Push a normal action first
        stack.push(_make_action(description="normal action"))

        # Begin compound — cascade delete
        stack.begin_compound("Delete column with dependents")
        stack.push(_make_action(
            action_type=UndoActionType.COLUMN_DELETE,
            description="delete col_a",
            before_state={"name": "col_a"},
        ))
        stack.push(_make_action(
            action_type=UndoActionType.COLUMN_DELETE,
            description="delete col_b (dependent)",
            before_state={"name": "col_b"},
        ))
        stack.push(_make_action(
            action_type=UndoActionType.COLUMN_DELETE,
            description="delete col_c (dependent)",
            before_state={"name": "col_c"},
        ))
        stack.end_compound()

        # Should be 2 undo items: 1 normal + 1 compound
        result = stack.undo()
        assert result is not None
        assert result.description == "Delete column with dependents"
        # Compound action should contain sub-actions
        assert isinstance(result.before_state, list)
        assert len(result.before_state) == 3

        # Next undo should be the normal action
        result = stack.undo()
        assert result is not None
        assert result.description == "normal action"

    def test_compound_redo(self):
        stack = UndoStack()
        stack.begin_compound("Cascade delete")
        stack.push(_make_action(description="sub-1", before_state="s1"))
        stack.push(_make_action(description="sub-2", before_state="s2"))
        stack.end_compound()

        undone = stack.undo()
        assert undone is not None

        redone = stack.redo()
        assert redone is not None
        assert redone.description == "Cascade delete"

    def test_nested_compound_not_allowed(self):
        """중첩 compound는 무시 (이미 compound 진행 중이면 경고 없이 무시)"""
        stack = UndoStack()
        stack.begin_compound("outer")
        # Second begin_compound should be ignored or raise
        stack.begin_compound("inner")
        stack.push(_make_action(description="action"))
        stack.end_compound()

        # end_compound should close the first one
        result = stack.undo()
        assert result is not None

    def test_empty_compound(self):
        """빈 compound는 무시"""
        stack = UndoStack()
        stack.begin_compound("empty")
        stack.end_compound()
        assert not stack.can_undo()

    def test_compound_counts_as_one_depth(self):
        """compound도 max_depth에서 1개로 취급"""
        stack = UndoStack(max_depth=3)
        for i in range(2):
            stack.push(_make_action(description=f"normal {i}"))

        stack.begin_compound("compound")
        stack.push(_make_action(description="sub-1"))
        stack.push(_make_action(description="sub-2"))
        stack.end_compound()

        # Now 3 items. Add one more → oldest removed
        stack.push(_make_action(description="normal 2"))

        count = 0
        while stack.can_undo():
            stack.undo()
            count += 1
        assert count == 3


# ── UndoActionType enum tests ────────────────────────────────────


class TestUndoActionType:
    def test_all_types_exist(self):
        expected = [
            "ANNOTATION_ADD", "ANNOTATION_DELETE", "ANNOTATION_EDIT",
            "COLUMN_ADD", "COLUMN_DELETE", "COLUMN_EDIT",
            "DASHBOARD_LAYOUT_CHANGE", "DASHBOARD_CELL_ASSIGN", "DASHBOARD_CELL_REMOVE",
        ]
        for name in expected:
            assert hasattr(UndoActionType, name)

    def test_values_are_strings(self):
        assert UndoActionType.ANNOTATION_ADD.value == "annotation_add"
