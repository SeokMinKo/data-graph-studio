"""Tests for zone-change undo (#1, #4, #5) and related improvements."""

import copy

from data_graph_studio.core.state import AppState, AggregationType, GridDirection
from data_graph_studio.core.undo_manager import UndoStack, UndoActionType


def _make_state():
    state = AppState()
    stack = UndoStack(max_depth=50)
    state.set_undo_stack(stack)
    return state, stack


class TestXColumnUndo:
    def test_set_x_column_undo(self):
        state, stack = _make_state()
        state.set_x_column("col_a")
        assert state.x_column == "col_a"
        assert stack.can_undo()

        stack.undo()
        assert state.x_column is None

    def test_set_x_column_redo(self):
        state, stack = _make_state()
        state.set_x_column("col_a")
        stack.undo()
        stack.redo()
        assert state.x_column == "col_a"

    def test_set_x_column_noop_same_value(self):
        state, stack = _make_state()
        state.set_x_column("col_a")
        stack.clear()
        state.set_x_column("col_a")  # same value
        assert not stack.can_undo()


class TestGroupZoneUndo:
    def test_add_group_column_undo(self):
        state, stack = _make_state()
        state.add_group_column("g1")
        assert len(state.group_columns) == 1
        stack.undo()
        assert len(state.group_columns) == 0

    def test_remove_group_column_undo(self):
        state, stack = _make_state()
        state.add_group_column("g1")
        stack.clear()
        state.remove_group_column("g1")
        assert len(state.group_columns) == 0
        stack.undo()
        assert len(state.group_columns) == 1

    def test_clear_group_zone_undo(self):
        state, stack = _make_state()
        state.add_group_column("g1")
        state.add_group_column("g2")
        stack.clear()
        state.clear_group_zone()
        assert len(state.group_columns) == 0
        stack.undo()
        assert len(state.group_columns) == 2

    def test_clear_group_zone_noop_empty(self):
        state, stack = _make_state()
        state.clear_group_zone()
        assert not stack.can_undo()


class TestValueZoneUndo:
    def test_add_value_column_undo(self):
        state, stack = _make_state()
        state.add_value_column("v1")
        assert len(state.value_columns) == 1
        stack.undo()
        assert len(state.value_columns) == 0

    def test_remove_value_column_undo(self):
        state, stack = _make_state()
        state.add_value_column("v1")
        stack.clear()
        state.remove_value_column(0)
        assert len(state.value_columns) == 0
        stack.undo()
        assert len(state.value_columns) == 1

    def test_clear_value_zone_undo(self):
        state, stack = _make_state()
        state.add_value_column("v1")
        state.add_value_column("v2")
        stack.clear()
        state.clear_value_zone()
        stack.undo()
        assert len(state.value_columns) == 2

    def test_remove_value_by_name_undo(self):
        state, stack = _make_state()
        state.add_value_column("v1")
        stack.clear()
        state.remove_value_column_by_name("v1")
        assert len(state.value_columns) == 0
        stack.undo()
        assert len(state.value_columns) == 1


class TestHoverZoneUndo:
    def test_add_hover_column_undo(self):
        state, stack = _make_state()
        state.add_hover_column("h1")
        assert state.hover_columns == ["h1"]
        stack.undo()
        assert state.hover_columns == []

    def test_remove_hover_column_undo(self):
        state, stack = _make_state()
        state.add_hover_column("h1")
        stack.clear()
        state.remove_hover_column("h1")
        stack.undo()
        assert state.hover_columns == ["h1"]

    def test_clear_hover_columns_undo(self):
        state, stack = _make_state()
        state.add_hover_column("h1")
        state.add_hover_column("h2")
        stack.clear()
        state.clear_hover_columns()
        stack.undo()
        assert len(state.hover_columns) == 2


class TestColumnVisibilityUndo:
    def test_toggle_visibility_undo(self):
        state, stack = _make_state()
        state.toggle_column_visibility("col_a")
        assert state.is_column_hidden("col_a")
        stack.undo()
        assert not state.is_column_hidden("col_a")

    def test_column_order_undo(self):
        state, stack = _make_state()
        state.set_column_order(["a", "b", "c"])
        stack.clear()
        state.set_column_order(["c", "b", "a"])
        stack.undo()
        assert state.get_column_order() == ["a", "b", "c"]


class TestGridViewUndo:
    def test_grid_enabled_undo(self):
        state, stack = _make_state()
        state.set_grid_view_enabled(True)
        assert state.grid_view_settings.enabled is True
        stack.undo()
        assert state.grid_view_settings.enabled is False

    def test_grid_split_by_undo(self):
        state, stack = _make_state()
        state.set_grid_view_split_by("col_a")
        stack.undo()
        assert state.grid_view_settings.split_by is None

    def test_grid_direction_undo(self):
        state, stack = _make_state()
        state.set_grid_view_direction(GridDirection.ROW)
        stack.undo()
        assert state.grid_view_settings.direction == GridDirection.WRAP

    def test_update_grid_view_undo(self):
        state, stack = _make_state()
        state.update_grid_view_settings(max_columns=8)
        stack.undo()
        assert state.grid_view_settings.max_columns == 4


class TestUndoCommandTimestamp:
    def test_timestamp_auto_set(self):
        from data_graph_studio.core.undo_manager import UndoCommand
        cmd = UndoCommand(
            action_type=UndoActionType.ZONE_X_CHANGE,
            description="test",
            do=lambda: None,
            undo=lambda: None,
        )
        assert cmd.timestamp > 0

    def test_timestamp_preserved_if_set(self):
        from data_graph_studio.core.undo_manager import UndoCommand
        cmd = UndoCommand(
            action_type=UndoActionType.ZONE_X_CHANGE,
            description="test",
            do=lambda: None,
            undo=lambda: None,
            timestamp=42.0,
        )
        assert cmd.timestamp == 42.0


class TestSizeHintEviction:
    def test_large_commands_evicted(self):
        stack = UndoStack(max_depth=100, max_memory_bytes=100)
        from data_graph_studio.core.undo_manager import UndoCommand
        for i in range(5):
            stack.record(UndoCommand(
                action_type=UndoActionType.COLUMN_ADD,
                description=f"big {i}",
                do=lambda: None,
                undo=lambda: None,
                size_hint=50,
            ))
        # 5 * 50 = 250 > 100, should evict oldest
        assert len(stack.commands) < 5
