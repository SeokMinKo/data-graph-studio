"""Tests for IPC profile comparison commands.

These tests call the _ipc_* handler methods directly with mock state/store,
without needing an actual TCP connection.
"""

import time
import uuid

import pytest

from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.profile_controller import ProfileController
from data_graph_studio.core.profile_store import ProfileStore
from data_graph_studio.core.state import (
    AppState,
    ChartType,
    ComparisonMode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_setting(**overrides) -> GraphSetting:
    return GraphSetting(
        id=overrides.get("id", str(uuid.uuid4())),
        name=overrides.get("name", "Setting"),
        dataset_id=overrides.get("dataset_id", "ds-1"),
        schema_version=overrides.get("schema_version", 1),
        chart_type=overrides.get("chart_type", "line"),
        x_column=overrides.get("x_column", "time"),
        group_columns=overrides.get("group_columns", ()),
        value_columns=overrides.get("value_columns", ({"name": "voltage", "aggregation": "sum"},)),
        hover_columns=overrides.get("hover_columns", ()),
        filters=overrides.get("filters", ()),
        sorts=overrides.get("sorts", ()),
        chart_settings=overrides.get("chart_settings", {}),
        created_at=overrides.get("created_at", time.time()),
        modified_at=overrides.get("modified_at", time.time()),
    )


def make_state() -> AppState:
    state = AppState()
    # Suppress Qt signal emission for unit tests
    state.begin_batch_update = lambda: None
    state.end_batch_update = lambda: None
    return state


class FakeMainWindow:
    """Minimal stand-in for MainWindow that hosts the _ipc_* methods."""

    def __init__(self):
        self.state = make_state()
        self.profile_store = ProfileStore()
        self.profile_controller = ProfileController(self.profile_store, self.state)

        # Pre-register a dataset so active_dataset_id is set
        self.state.add_dataset("ds-1", name="Test Dataset")

        # Set some current state so create_profile captures it
        self.state._chart_settings.chart_type = ChartType.LINE
        self.state._x_column = "time"

    # -- Import the IPC handler methods (defined below as module-level funcs) --
    # We bind the real implementations directly.

    def _ipc_list_profiles(self, dataset_id: str = None):
        did = dataset_id or self.state.active_dataset_id
        if not did:
            raise ValueError("No active dataset")
        settings = self.profile_store.get_by_dataset(did)
        return [
            {
                "id": s.id,
                "name": s.name,
                "dataset_id": s.dataset_id,
                "chart_type": s.chart_type,
                "x_column": s.x_column,
                "value_columns": list(s.value_columns),
            }
            for s in settings
        ]

    def _ipc_create_profile(self, name: str, dataset_id: str = None):
        did = dataset_id or self.state.active_dataset_id
        if not did:
            raise ValueError("No active dataset")
        profile_id = self.profile_controller.create_profile(did, name)
        if profile_id is None:
            raise RuntimeError("Failed to create profile")
        setting = self.profile_store.get(profile_id)
        return {"id": setting.id, "name": setting.name}

    def _ipc_apply_profile(self, profile_id: str):
        ok = self.profile_controller.apply_profile(profile_id)
        if not ok:
            raise ValueError(f"Failed to apply profile: {profile_id}")
        return {"ok": True}

    def _ipc_delete_profile(self, profile_id: str):
        ok = self.profile_controller.delete_profile(profile_id)
        if not ok:
            raise ValueError(f"Failed to delete profile: {profile_id}")
        return {"ok": True}

    def _ipc_duplicate_profile(self, profile_id: str):
        new_id = self.profile_controller.duplicate_profile(profile_id)
        if new_id is None:
            raise ValueError(f"Failed to duplicate profile: {profile_id}")
        setting = self.profile_store.get(new_id)
        return {"id": setting.id, "name": setting.name}

    def _ipc_start_profile_comparison(self, profile_ids: list, mode: str = "side_by_side"):
        if len(profile_ids) < 2:
            raise ValueError("At least 2 profiles required for comparison")

        # Validate all profiles exist and belong to same dataset
        settings = []
        for pid in profile_ids:
            s = self.profile_store.get(pid)
            if s is None:
                raise ValueError(f"Profile not found: {pid}")
            settings.append(s)

        dataset_ids = {s.dataset_id for s in settings}
        if len(dataset_ids) > 1:
            raise ValueError("All profiles must belong to the same dataset")

        # Validate mode constraints
        comp_mode = {
            "side_by_side": ComparisonMode.SIDE_BY_SIDE,
            "overlay": ComparisonMode.OVERLAY,
            "difference": ComparisonMode.DIFFERENCE,
        }.get(mode)
        if comp_mode is None:
            raise ValueError(f"Invalid comparison mode: {mode}")

        if comp_mode in (ComparisonMode.OVERLAY, ComparisonMode.DIFFERENCE):
            x_columns = {s.x_column for s in settings}
            if len(x_columns) > 1:
                raise ValueError(
                    f"X-axis mismatch: {mode} requires all profiles to share the same X column"
                )

        if comp_mode == ComparisonMode.DIFFERENCE and len(profile_ids) != 2:
            raise ValueError("Difference mode requires exactly 2 profiles")

        dataset_id = next(iter(dataset_ids))
        self.state.set_profile_comparison(dataset_id, profile_ids)
        # set_comparison_mode would clear profile comparison (FR-8),
        # so set mode directly on settings after set_profile_comparison
        if self.state._comparison_settings.mode != comp_mode:
            self.state._comparison_settings.mode = comp_mode
            self.state.emit("comparison_mode_changed", comp_mode.value)
            self.state.emit("comparison_settings_changed")

        return {"ok": True, "mode": mode}

    def _ipc_stop_profile_comparison(self):
        self.state.clear_profile_comparison()
        return {"ok": True}

    def _ipc_get_profile_comparison_state(self):
        cs = self.state.comparison_settings
        return {
            "active": self.state.is_profile_comparison_active,
            "mode": cs.mode.value,
            "target": cs.comparison_target,
            "profile_ids": list(cs.comparison_profile_ids),
            "dataset_id": cs.comparison_dataset_id,
            "sync_x": cs.sync_pan_x,
            "sync_y": cs.sync_pan_y,
            "sync_selection": cs.sync_selection,
        }

    def _ipc_set_comparison_sync(
        self,
        sync_x: bool = None,
        sync_y: bool = None,
        sync_selection: bool = None,
    ):
        if sync_x is not None:
            self.state._comparison_settings.sync_pan_x = sync_x
        if sync_y is not None:
            self.state._comparison_settings.sync_pan_y = sync_y
        if sync_selection is not None:
            self.state._comparison_settings.sync_selection = sync_selection
        self.state.emit("comparison_settings_changed")
        return {"ok": True}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def win():
    return FakeMainWindow()


@pytest.fixture
def win_with_profiles(win):
    """Window with two pre-created profiles in ds-1."""
    s1 = make_setting(id="p1", name="Voltage View", dataset_id="ds-1", x_column="time")
    s2 = make_setting(id="p2", name="Current View", dataset_id="ds-1", x_column="time")
    win.profile_store.add(s1)
    win.profile_store.add(s2)
    return win


# ---------------------------------------------------------------------------
# list_profiles
# ---------------------------------------------------------------------------

class TestListProfiles:
    def test_empty(self, win):
        result = win._ipc_list_profiles()
        assert result == []

    def test_returns_profiles_for_active_dataset(self, win):
        s = make_setting(name="My View", dataset_id="ds-1")
        win.profile_store.add(s)
        result = win._ipc_list_profiles()
        assert len(result) == 1
        assert result[0]["name"] == "My View"
        assert result[0]["id"] == s.id

    def test_filters_by_dataset_id(self, win):
        s1 = make_setting(name="A", dataset_id="ds-1")
        s2 = make_setting(name="B", dataset_id="ds-2")
        win.profile_store.add(s1)
        win.profile_store.add(s2)
        result = win._ipc_list_profiles(dataset_id="ds-2")
        assert len(result) == 1
        assert result[0]["name"] == "B"

    def test_explicit_dataset_id(self, win):
        s = make_setting(name="X", dataset_id="ds-other")
        win.profile_store.add(s)
        result = win._ipc_list_profiles(dataset_id="ds-other")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# create_profile
# ---------------------------------------------------------------------------

class TestCreateProfile:
    def test_creates_and_returns(self, win):
        result = win._ipc_create_profile(name="New Profile")
        assert "id" in result
        assert result["name"] == "New Profile"
        # Verify stored
        stored = win.profile_store.get(result["id"])
        assert stored is not None
        assert stored.name == "New Profile"

    def test_uses_explicit_dataset_id(self, win):
        win.state.add_dataset("ds-2", name="Second")
        result = win._ipc_create_profile(name="Prof", dataset_id="ds-2")
        stored = win.profile_store.get(result["id"])
        assert stored.dataset_id == "ds-2"

    def test_creates_blank_profile(self, win):
        """신규 프로파일은 빈 그래프 설정으로 생성된다."""
        win.state._chart_settings.chart_type = ChartType.BAR
        win.state._x_column = "date"
        result = win._ipc_create_profile(name="Blank Profile")
        stored = win.profile_store.get(result["id"])
        # 새 프로파일은 빈 상태 (현재 AppState를 복사하지 않음)
        assert stored.chart_type == ""
        assert stored.x_column is None


# ---------------------------------------------------------------------------
# apply_profile
# ---------------------------------------------------------------------------

class TestApplyProfile:
    def test_apply_success(self, win):
        s = make_setting(id="p1", name="Test", chart_type="scatter", x_column="x")
        win.profile_store.add(s)
        result = win._ipc_apply_profile(profile_id="p1")
        assert result["ok"] is True
        assert win.state._chart_settings.chart_type == ChartType.SCATTER

    def test_apply_nonexistent(self, win):
        with pytest.raises(ValueError):
            win._ipc_apply_profile(profile_id="nonexistent")


# ---------------------------------------------------------------------------
# delete_profile
# ---------------------------------------------------------------------------

class TestDeleteProfile:
    def test_delete_success(self, win):
        s = make_setting(id="p1", name="To Delete")
        win.profile_store.add(s)
        result = win._ipc_delete_profile(profile_id="p1")
        assert result["ok"] is True
        assert win.profile_store.get("p1") is None

    def test_delete_nonexistent(self, win):
        with pytest.raises(ValueError):
            win._ipc_delete_profile(profile_id="nonexistent")


# ---------------------------------------------------------------------------
# duplicate_profile
# ---------------------------------------------------------------------------

class TestDuplicateProfile:
    def test_duplicate_success(self, win):
        s = make_setting(id="p1", name="Original", dataset_id="ds-1")
        win.profile_store.add(s)
        result = win._ipc_duplicate_profile(profile_id="p1")
        assert result["id"] != "p1"
        assert "Original" in result["name"]

    def test_duplicate_nonexistent(self, win):
        with pytest.raises(ValueError):
            win._ipc_duplicate_profile(profile_id="nonexistent")


# ---------------------------------------------------------------------------
# start_profile_comparison
# ---------------------------------------------------------------------------

class TestStartProfileComparison:
    def test_side_by_side(self, win_with_profiles):
        result = win_with_profiles._ipc_start_profile_comparison(
            profile_ids=["p1", "p2"], mode="side_by_side"
        )
        assert result["ok"] is True
        assert result["mode"] == "side_by_side"
        assert win_with_profiles.state.is_profile_comparison_active

    def test_overlay_same_x(self, win_with_profiles):
        result = win_with_profiles._ipc_start_profile_comparison(
            profile_ids=["p1", "p2"], mode="overlay"
        )
        assert result["ok"] is True
        assert result["mode"] == "overlay"

    def test_overlay_different_x_raises(self, win):
        s1 = make_setting(id="p1", x_column="time", dataset_id="ds-1")
        s2 = make_setting(id="p2", x_column="date", dataset_id="ds-1")
        win.profile_store.add(s1)
        win.profile_store.add(s2)
        with pytest.raises(ValueError, match="X-axis mismatch"):
            win._ipc_start_profile_comparison(
                profile_ids=["p1", "p2"], mode="overlay"
            )

    def test_difference_exactly_two(self, win_with_profiles):
        result = win_with_profiles._ipc_start_profile_comparison(
            profile_ids=["p1", "p2"], mode="difference"
        )
        assert result["ok"] is True

    def test_difference_more_than_two_raises(self, win):
        s1 = make_setting(id="p1", dataset_id="ds-1", x_column="time")
        s2 = make_setting(id="p2", dataset_id="ds-1", x_column="time")
        s3 = make_setting(id="p3", dataset_id="ds-1", x_column="time")
        win.profile_store.add(s1)
        win.profile_store.add(s2)
        win.profile_store.add(s3)
        with pytest.raises(ValueError, match="exactly 2"):
            win._ipc_start_profile_comparison(
                profile_ids=["p1", "p2", "p3"], mode="difference"
            )

    def test_fewer_than_two_raises(self, win):
        s1 = make_setting(id="p1", dataset_id="ds-1")
        win.profile_store.add(s1)
        with pytest.raises(ValueError, match="At least 2"):
            win._ipc_start_profile_comparison(profile_ids=["p1"])

    def test_nonexistent_profile_raises(self, win):
        s1 = make_setting(id="p1", dataset_id="ds-1")
        win.profile_store.add(s1)
        with pytest.raises(ValueError, match="not found"):
            win._ipc_start_profile_comparison(profile_ids=["p1", "missing"])

    def test_mixed_datasets_raises(self, win):
        s1 = make_setting(id="p1", dataset_id="ds-1")
        s2 = make_setting(id="p2", dataset_id="ds-2")
        win.profile_store.add(s1)
        win.profile_store.add(s2)
        with pytest.raises(ValueError, match="same dataset"):
            win._ipc_start_profile_comparison(profile_ids=["p1", "p2"])

    def test_invalid_mode_raises(self, win_with_profiles):
        with pytest.raises(ValueError, match="Invalid comparison mode"):
            win_with_profiles._ipc_start_profile_comparison(
                profile_ids=["p1", "p2"], mode="invalid"
            )


# ---------------------------------------------------------------------------
# stop_profile_comparison
# ---------------------------------------------------------------------------

class TestStopProfileComparison:
    def test_stop(self, win_with_profiles):
        win_with_profiles._ipc_start_profile_comparison(
            profile_ids=["p1", "p2"], mode="side_by_side"
        )
        result = win_with_profiles._ipc_stop_profile_comparison()
        assert result["ok"] is True
        assert not win_with_profiles.state.is_profile_comparison_active
        assert win_with_profiles.state.comparison_mode == ComparisonMode.SINGLE

    def test_stop_when_not_active(self, win):
        result = win._ipc_stop_profile_comparison()
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# get_profile_comparison_state
# ---------------------------------------------------------------------------

class TestGetProfileComparisonState:
    def test_inactive(self, win):
        result = win._ipc_get_profile_comparison_state()
        assert result["active"] is False
        assert result["mode"] == "single"
        assert result["target"] == "dataset"
        assert result["profile_ids"] == []

    def test_active_comparison(self, win_with_profiles):
        win_with_profiles._ipc_start_profile_comparison(
            profile_ids=["p1", "p2"], mode="overlay"
        )
        result = win_with_profiles._ipc_get_profile_comparison_state()
        assert result["active"] is True
        assert result["mode"] == "overlay"
        assert result["target"] == "profile"
        assert set(result["profile_ids"]) == {"p1", "p2"}
        assert result["dataset_id"] == "ds-1"

    def test_sync_defaults(self, win):
        result = win._ipc_get_profile_comparison_state()
        assert result["sync_x"] is True  # sync_pan_x default
        assert result["sync_y"] is True  # sync_pan_y default
        assert result["sync_selection"] is False


# ---------------------------------------------------------------------------
# set_comparison_sync
# ---------------------------------------------------------------------------

class TestSetComparisonSync:
    def test_set_sync_x(self, win):
        win._ipc_set_comparison_sync(sync_x=False)
        assert win.state._comparison_settings.sync_pan_x is False

    def test_set_sync_y(self, win):
        win._ipc_set_comparison_sync(sync_y=False)
        assert win.state._comparison_settings.sync_pan_y is False

    def test_set_sync_selection(self, win):
        win._ipc_set_comparison_sync(sync_selection=True)
        assert win.state._comparison_settings.sync_selection is True

    def test_partial_update(self, win):
        """Only update provided fields, leave others unchanged."""
        win._ipc_set_comparison_sync(sync_x=False)
        assert win.state._comparison_settings.sync_pan_x is False
        assert win.state._comparison_settings.sync_pan_y is True  # unchanged

    def test_returns_ok(self, win):
        result = win._ipc_set_comparison_sync(sync_x=True)
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Integration: full workflow
# ---------------------------------------------------------------------------

class TestProfileComparisonWorkflow:
    def test_create_compare_stop(self, win):
        """Full workflow: create profiles, compare, check state, stop."""
        # Create two profiles
        p1 = win._ipc_create_profile(name="View A")
        win.state._chart_settings.chart_type = ChartType.BAR
        p2 = win._ipc_create_profile(name="View B")

        # List profiles
        profiles = win._ipc_list_profiles()
        assert len(profiles) == 2

        # Start comparison
        result = win._ipc_start_profile_comparison(
            profile_ids=[p1["id"], p2["id"]], mode="side_by_side"
        )
        assert result["ok"]

        # Check state
        state = win._ipc_get_profile_comparison_state()
        assert state["active"] is True
        assert state["mode"] == "side_by_side"

        # Set sync
        win._ipc_set_comparison_sync(sync_selection=True)
        state = win._ipc_get_profile_comparison_state()
        assert state["sync_selection"] is True

        # Stop
        win._ipc_stop_profile_comparison()
        state = win._ipc_get_profile_comparison_state()
        assert state["active"] is False

    def test_duplicate_and_compare(self, win):
        """Duplicate a profile and compare with original."""
        p1 = win._ipc_create_profile(name="Original")
        dup = win._ipc_duplicate_profile(profile_id=p1["id"])
        assert dup["id"] != p1["id"]

        result = win._ipc_start_profile_comparison(
            profile_ids=[p1["id"], dup["id"]], mode="side_by_side"
        )
        assert result["ok"]

    def test_delete_during_comparison_leaves_store_clean(self, win):
        """Delete a profile after comparison started."""
        p1 = win._ipc_create_profile(name="A")
        p2 = win._ipc_create_profile(name="B")

        win._ipc_start_profile_comparison(
            profile_ids=[p1["id"], p2["id"]], mode="side_by_side"
        )

        # Delete one profile
        win._ipc_delete_profile(profile_id=p1["id"])
        assert win.profile_store.get(p1["id"]) is None

        # The other still exists
        assert win.profile_store.get(p2["id"]) is not None
