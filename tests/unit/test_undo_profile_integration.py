"""Tests for ProfileController integration with main UndoStack (#2)."""

import time
import uuid

from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.profile_controller import ProfileController
from data_graph_studio.core.profile_store import ProfileStore
from data_graph_studio.core.state import AppState
from data_graph_studio.core.undo_manager import UndoStack


def _make_setting(**kw) -> GraphSetting:
    return GraphSetting(
        id=kw.get("id", str(uuid.uuid4())),
        name=kw.get("name", "Setting"),
        dataset_id=kw.get("dataset_id", "ds-1"),
        schema_version=1,
        chart_type="line",
        x_column=None,
        group_columns=(),
        value_columns=(),
        hover_columns=(),
        filters=(),
        sorts=(),
        chart_settings={},
        created_at=time.time(),
        modified_at=time.time(),
    )


def _make_env():
    store = ProfileStore()
    state = AppState()
    stack = UndoStack(max_depth=50)
    ctrl = ProfileController(store, state, undo_stack=stack)
    return store, state, stack, ctrl


class TestProfileRenameUndo:
    def test_rename_undo_restores_name(self):
        store, state, stack, ctrl = _make_env()
        s = _make_setting(id="p1", name="Alpha")
        store.add(s)

        ctrl.rename_profile("p1", "Beta")
        assert store.get("p1").name == "Beta"

        stack.undo()
        assert store.get("p1").name == "Alpha"

    def test_rename_redo(self):
        store, state, stack, ctrl = _make_env()
        s = _make_setting(id="p1", name="Alpha")
        store.add(s)

        ctrl.rename_profile("p1", "Beta")
        stack.undo()
        stack.redo()
        assert store.get("p1").name == "Beta"


class TestProfileDeleteUndo:
    def test_delete_undo_restores(self):
        store, state, stack, ctrl = _make_env()
        s = _make_setting(id="p1", name="ToDelete")
        store.add(s)

        ctrl.delete_profile("p1")
        assert store.get("p1") is None

        stack.undo()
        restored = store.get("p1")
        assert restored is not None
        assert restored.name == "ToDelete"

    def test_delete_redo(self):
        store, state, stack, ctrl = _make_env()
        s = _make_setting(id="p1", name="ToDelete")
        store.add(s)

        ctrl.delete_profile("p1")
        stack.undo()
        stack.redo()
        assert store.get("p1") is None


class TestProfileUndoDelegation:
    def test_controller_undo_delegates(self):
        store, state, stack, ctrl = _make_env()
        s = _make_setting(id="p1", name="A")
        store.add(s)
        ctrl.rename_profile("p1", "B")

        assert ctrl.undo() is True
        assert store.get("p1").name == "A"

    def test_controller_undo_empty(self):
        _, _, stack, ctrl = _make_env()
        assert ctrl.undo() is False


class TestNoSeparateStack:
    def test_no_internal_undo_stack(self):
        """ProfileController should not have its own _undo_stack list anymore."""
        _, _, _, ctrl = _make_env()
        # The old implementation had _undo_stack as a list; now it should not exist
        assert not hasattr(ctrl, '_undo_stack') or not isinstance(getattr(ctrl, '_undo_stack', None), list)
