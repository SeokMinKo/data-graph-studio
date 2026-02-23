"""
Contract / invariant tests for core public API.

These tests verify that the invariants documented in docstrings are actually
enforced at runtime. They are NOT unit tests of specific implementation
details — they treat each class as a black box and confirm the post-condition
guarantees that callers depend on.

Covered:
  - DatasetManager (8 invariants)
  - AppState / FilterSortMixin (3 invariants)
  - ExpressionEngine (2 invariants)
  - ProfileStore (3 invariants)
  - UndoStack (3 invariants)
"""

import pytest
import polars as pl
from unittest.mock import MagicMock

from data_graph_studio.core.dataset_manager import DatasetManager
from data_graph_studio.core.file_loader import FileLoader
from data_graph_studio.core.undo_manager import UndoStack, UndoCommand, UndoActionType
from data_graph_studio.core.profile_store import ProfileStore
from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.expression_engine import ExpressionEngine, ExpressionError
from data_graph_studio.core.state import AppState


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_manager() -> DatasetManager:
    """Fresh DatasetManager backed by a minimal FileLoader mock."""
    loader = MagicMock()
    loader._df = None
    loader._lazy_df = None
    loader._source = None
    loader._profile = None
    loader._precision_mode = None
    return DatasetManager(loader)


def _load_df(manager: DatasetManager, name: str = "ds") -> str:
    """Load a small in-memory DataFrame; return dataset_id."""
    df = pl.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]})
    did = manager.load_dataset_from_dataframe(df, name=name)
    assert did is not None
    return did


def _make_setting(name: str = "test", dataset_id: str = "ds1") -> GraphSetting:
    return GraphSetting.create_new(name=name, dataset_id=dataset_id)


def _make_undo_cmd(state: dict, key: str, new_val) -> UndoCommand:
    """Build a simple UndoCommand that writes state[key] = new_val / old_val."""
    old_val = state[key]
    return UndoCommand(
        action_type=UndoActionType.FILTER_CHANGE,
        description=f"set {key}={new_val}",
        do=lambda: state.update({key: new_val}),
        undo=lambda: state.update({key: old_val}),
    )


# ===========================================================================
# DatasetManager invariants
# ===========================================================================

class TestDatasetManagerInvariants:

    def test_load_increases_dataset_count(self):
        """load_dataset_from_dataframe increments dataset_count by 1."""
        m = _make_manager()
        before = m.dataset_count
        _load_df(m)
        assert m.dataset_count == before + 1

    def test_remove_clears_dataset_id(self):
        """After remove_dataset, the removed ID is absent from datasets."""
        m = _make_manager()
        did = _load_df(m)
        assert did in m.datasets
        m.remove_dataset(did)
        assert did not in m.datasets

    def test_activate_sets_active_dataset_id(self):
        """activate_dataset sets active_dataset_id to the given ID."""
        m = _make_manager()
        did1 = _load_df(m, "first")
        did2 = _load_df(m, "second")
        # did1 is currently active (loaded first)
        m.activate_dataset(did2)
        assert m.active_dataset_id == did2
        m.activate_dataset(did1)
        assert m.active_dataset_id == did1

    def test_clear_all_datasets_resets_count_and_active(self):
        """clear_all_datasets leaves dataset_count == 0 and active_dataset_id == None."""
        m = _make_manager()
        _load_df(m, "a")
        _load_df(m, "b")
        m.clear_all_datasets()
        assert m.dataset_count == 0
        assert m.active_dataset_id is None

    def test_first_load_sets_active_dataset_id(self):
        """load_dataset_from_dataframe sets active_dataset_id when no other dataset is active."""
        m = _make_manager()
        assert m.active_dataset_id is None
        did = _load_df(m)
        assert m.active_dataset_id == did

    def test_remove_active_advances_to_next(self):
        """Removing the active dataset advances active_dataset_id to the next remaining dataset."""
        m = _make_manager()
        did1 = _load_df(m, "first")
        did2 = _load_df(m, "second")
        assert m.active_dataset_id == did1
        m.remove_dataset(did1)
        # After removing the only active, next remaining should be active
        assert m.active_dataset_id == did2

    def test_get_dataset_df_returns_none_for_unknown_id(self):
        """get_dataset_df returns None for an ID that was never loaded."""
        m = _make_manager()
        result = m.get_dataset_df("nonexistent-id")
        assert result is None

    def test_can_load_dataset_under_limit_returns_true(self):
        """can_load_dataset(0) returns (True, ...) when under MAX_DATASETS."""
        m = _make_manager()
        ok, msg = m.can_load_dataset(0)
        assert ok is True
        # message is either empty string (safe) or a warning string (near ceiling)
        assert isinstance(msg, str)


# ===========================================================================
# AppState / FilterSortMixin invariants
# ===========================================================================

class TestFilteringStateInvariants:

    def setup_method(self):
        self.state = AppState()
        # Wire a no-op undo stack so push_undo doesn't crash
        self.state._undo_stack = UndoStack()

    def test_add_filter_increases_count(self):
        """add_filter appends exactly one FilterCondition."""
        before = len(self.state.filters)
        self.state.add_filter("x", "eq", 1)
        assert len(self.state.filters) == before + 1

    def test_remove_filter_removes_specific_entry(self):
        """remove_filter(index) removes the condition at that position."""
        self.state.add_filter("col_a", "gt", 5)
        self.state.add_filter("col_b", "lt", 10)
        # Remove first filter
        col_b_condition = self.state.filters[1]
        self.state.remove_filter(0)
        assert len(self.state.filters) == 1
        # Remaining filter is what was at index 1
        assert self.state.filters[0].column == col_b_condition.column

    def test_clear_filters_empties_list(self):
        """clear_filters results in an empty filters list."""
        self.state.add_filter("x", "eq", 42)
        self.state.add_filter("y", "ne", 0)
        assert len(self.state.filters) > 0
        self.state.clear_filters()
        assert self.state.filters == []


# ===========================================================================
# ExpressionEngine invariants
# ===========================================================================

class TestExpressionEngineInvariants:

    def setup_method(self):
        self.engine = ExpressionEngine()
        self.df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

    def test_evaluate_simple_arithmetic_returns_correct_series(self):
        """evaluate('1 + 1', df) returns a Series of all 2s, one per row."""
        result = self.engine.evaluate("1 + 1", self.df)
        assert isinstance(result, pl.Series)
        assert len(result) == len(self.df)
        assert all(v == 2 for v in result.to_list())

    def test_evaluate_invalid_expression_raises_expression_error(self):
        """evaluate with a reference to a non-existent column raises ExpressionError."""
        with pytest.raises(ExpressionError):
            self.engine.evaluate("[nonexistent_column]", self.df)


# ===========================================================================
# ProfileStore invariants
# ===========================================================================

class TestProfileStoreInvariants:

    def setup_method(self):
        self.store = ProfileStore()

    def test_add_then_get_returns_profile(self):
        """After add(setting), get(setting.id) returns the same setting."""
        s = _make_setting("my_profile")
        self.store.add(s)
        retrieved = self.store.get(s.id)
        assert retrieved is not None
        assert retrieved.id == s.id
        assert retrieved.name == s.name

    def test_remove_then_get_returns_none(self):
        """After remove(id), get(id) returns None."""
        s = _make_setting("to_remove")
        self.store.add(s)
        removed = self.store.remove(s.id)
        assert removed is True
        assert self.store.get(s.id) is None

    def test_update_reflects_new_values(self):
        """After update(setting), get(setting.id) reflects the updated attributes."""
        s = _make_setting("original")
        self.store.add(s)
        updated = GraphSetting(
            id=s.id,
            name="updated_name",
            dataset_id=s.dataset_id,
            chart_type="bar",
        )
        self.store.update(updated)
        result = self.store.get(s.id)
        assert result is not None
        assert result.name == "updated_name"
        assert result.chart_type == "bar"


# ===========================================================================
# UndoStack invariants
# ===========================================================================

class TestUndoStackInvariants:

    def test_push_then_undo_restores_state(self):
        """push followed by undo reverses the state change."""
        state = {"val": 0}
        stack = UndoStack()
        cmd = _make_undo_cmd(state, "val", 99)
        stack.push(cmd)
        assert state["val"] == 99
        stack.undo()
        assert state["val"] == 0

    def test_undo_on_empty_stack_returns_none(self):
        """undo() on an empty stack returns None and does not raise."""
        stack = UndoStack()
        result = stack.undo()
        assert result is None

    def test_size_equals_pushes_minus_undos(self):
        """index equals number of pushes minus number of undos performed."""
        state = {"v": 0}
        stack = UndoStack()

        cmd1 = _make_undo_cmd(state, "v", 1)
        cmd2 = _make_undo_cmd(state, "v", 2)
        cmd3 = _make_undo_cmd(state, "v", 3)

        stack.push(cmd1)
        stack.push(cmd2)
        stack.push(cmd3)
        assert stack.index == 3

        stack.undo()
        assert stack.index == 2

        stack.undo()
        assert stack.index == 1
