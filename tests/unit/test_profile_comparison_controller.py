"""Tests for ProfileComparisonController (Module G)."""

import time
import uuid


from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.profile_controller import ProfileController
from data_graph_studio.core.profile_store import ProfileStore
from data_graph_studio.core.state import AppState, ComparisonMode
from data_graph_studio.core.profile_comparison_controller import (
    ProfileComparisonController,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_setting(**overrides) -> GraphSetting:
    return GraphSetting(
        id=overrides.get("id", str(uuid.uuid4())),
        name=overrides.get("name", "Setting"),
        dataset_id=overrides.get("dataset_id", "ds-1"),
        chart_type=overrides.get("chart_type", "line"),
        x_column=overrides.get("x_column", "time"),
        value_columns=overrides.get("value_columns", ({"name": "voltage"},)),
        created_at=overrides.get("created_at", time.time()),
        modified_at=overrides.get("modified_at", time.time()),
    )


def make_env(n_profiles=2, same_x=True, dataset_id="ds-1"):
    """Create store, controller, state, comparison_controller + n profiles."""
    store = ProfileStore()
    state = AppState()
    controller = ProfileController(store, state)
    cc = ProfileComparisonController(store, controller, state)

    profiles = []
    for i in range(n_profiles):
        x_col = "time" if (same_x or i == 0) else f"x_{i}"
        s = make_setting(
            id=f"p{i}",
            name=f"Profile {i}",
            dataset_id=dataset_id,
            x_column=x_col,
            value_columns=({"name": f"y{i}"},),
        )
        store.add(s)
        profiles.append(s)

    return store, controller, state, cc, profiles


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_controller_creation():
    store, controller, state, cc, _ = make_env(0)
    assert cc.is_active is False
    assert cc.current_profiles == []
    assert cc.current_mode == ComparisonMode.SINGLE
    assert cc.dataset_id == ""


# ---------------------------------------------------------------------------
# start_comparison — valid
# ---------------------------------------------------------------------------


def test_start_comparison_valid_emits_signal():
    store, controller, state, cc, profiles = make_env(2)
    started = []
    cc.subscribe("comparison_started", lambda mode, ids: started.append((mode, ids)))

    ok = cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)
    assert ok is True
    assert cc.is_active is True
    assert cc.current_mode == ComparisonMode.SIDE_BY_SIDE
    assert set(cc.current_profiles) == {"p0", "p1"}
    assert cc.dataset_id == "ds-1"
    assert len(started) == 1
    assert started[0][0] == "side_by_side"
    assert set(started[0][1]) == {"p0", "p1"}


def test_start_comparison_overlay_same_x():
    store, controller, state, cc, profiles = make_env(3, same_x=True)
    ok = cc.start_comparison("ds-1", ["p0", "p1", "p2"], ComparisonMode.OVERLAY)
    assert ok is True
    assert cc.current_mode == ComparisonMode.OVERLAY


def test_start_comparison_difference_valid():
    store, controller, state, cc, profiles = make_env(2, same_x=True)
    ok = cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.DIFFERENCE)
    assert ok is True
    assert cc.current_mode == ComparisonMode.DIFFERENCE


# ---------------------------------------------------------------------------
# start_comparison — invalid cases
# ---------------------------------------------------------------------------


def test_start_comparison_less_than_2_profiles_error():
    store, controller, state, cc, profiles = make_env(1)
    errors = []
    cc.subscribe("error_occurred", errors.append)

    ok = cc.start_comparison("ds-1", ["p0"], ComparisonMode.SIDE_BY_SIDE)
    assert ok is False
    assert len(errors) == 1
    assert cc.is_active is False


def test_start_comparison_nonexistent_profile_error():
    store, controller, state, cc, profiles = make_env(2)
    errors = []
    cc.subscribe("error_occurred", errors.append)

    ok = cc.start_comparison("ds-1", ["p0", "missing"], ComparisonMode.SIDE_BY_SIDE)
    assert ok is False
    assert len(errors) == 1


def test_start_comparison_different_datasets_error():
    store = ProfileStore()
    state = AppState()
    controller = ProfileController(store, state)
    cc = ProfileComparisonController(store, controller, state)

    s0 = make_setting(id="p0", dataset_id="ds-1")
    s1 = make_setting(id="p1", dataset_id="ds-2")
    store.add(s0)
    store.add(s1)

    errors = []
    cc.subscribe("error_occurred", errors.append)

    ok = cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)
    assert ok is False
    assert len(errors) == 1


def test_start_comparison_overlay_different_x_error():
    store, controller, state, cc, profiles = make_env(2, same_x=False)
    errors = []
    cc.subscribe("error_occurred", errors.append)

    ok = cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.OVERLAY)
    assert ok is False
    assert len(errors) == 1


def test_start_comparison_difference_3_profiles_error():
    store, controller, state, cc, profiles = make_env(3, same_x=True)
    errors = []
    cc.subscribe("error_occurred", errors.append)

    ok = cc.start_comparison("ds-1", ["p0", "p1", "p2"], ComparisonMode.DIFFERENCE)
    assert ok is False
    assert len(errors) == 1


def test_start_comparison_difference_different_x_error():
    store, controller, state, cc, profiles = make_env(2, same_x=False)
    errors = []
    cc.subscribe("error_occurred", errors.append)

    ok = cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.DIFFERENCE)
    assert ok is False
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# stop_comparison
# ---------------------------------------------------------------------------


def test_stop_comparison_emits_signal_and_clears():
    store, controller, state, cc, profiles = make_env(2)
    ended = []
    cc.subscribe("comparison_ended", lambda: ended.append(True))

    cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)
    assert cc.is_active is True

    cc.stop_comparison()
    assert cc.is_active is False
    assert len(ended) == 1
    # State should be cleared back to single
    assert state.comparison_settings.mode == ComparisonMode.SINGLE
    assert state.comparison_settings.comparison_target == "dataset"


def test_stop_comparison_idempotent():
    store, controller, state, cc, profiles = make_env(2)
    ended = []
    cc.subscribe("comparison_ended", lambda: ended.append(True))

    cc.stop_comparison()
    # Should not emit when not active
    assert len(ended) == 0


# ---------------------------------------------------------------------------
# FR-8: start_comparison clears dataset comparison
# ---------------------------------------------------------------------------


def test_fr8_start_clears_dataset_comparison():
    store, controller, state, cc, profiles = make_env(2)

    # Simulate an active dataset comparison
    state._comparison_settings.comparison_target = "dataset"
    state._comparison_settings.comparison_datasets = ["ds-a", "ds-b"]
    state._comparison_settings.mode = ComparisonMode.SIDE_BY_SIDE

    cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)

    # Dataset comparison should be cleared
    assert state.comparison_settings.comparison_target == "profile"
    assert state.comparison_settings.comparison_datasets == []
    assert set(state.comparison_settings.comparison_profile_ids) == {"p0", "p1"}


# ---------------------------------------------------------------------------
# FR-10: profile deleted during comparison
# ---------------------------------------------------------------------------


def test_fr10_profile_deleted_panel_removed():
    store, controller, state, cc, profiles = make_env(3, same_x=True)
    removed = []
    cc.subscribe("panel_removed", removed.append)

    cc.start_comparison("ds-1", ["p0", "p1", "p2"], ComparisonMode.SIDE_BY_SIDE)
    assert cc.is_active is True

    # Delete one profile via ProfileController
    controller.delete_profile("p0")

    assert "p0" in removed
    assert "p0" not in cc.current_profiles
    assert cc.is_active is True  # still >=2


def test_fr10_profile_deleted_auto_stop_when_less_than_2():
    store, controller, state, cc, profiles = make_env(2)
    ended = []
    cc.subscribe("comparison_ended", lambda: ended.append(True))

    cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)
    controller.delete_profile("p0")

    assert cc.is_active is False
    assert len(ended) == 1


def test_fr10_profile_deleted_not_in_comparison_ignored():
    store, controller, state, cc, profiles = make_env(3, same_x=True)
    removed = []
    cc.subscribe("panel_removed", removed.append)

    cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)

    # Delete p2 which is NOT in the comparison
    controller.delete_profile("p2")
    assert len(removed) == 0
    assert cc.is_active is True


# ---------------------------------------------------------------------------
# FR-10: profile renamed during comparison
# ---------------------------------------------------------------------------


def test_fr10_profile_renamed_signal_forwarded():
    store, controller, state, cc, profiles = make_env(2)

    cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)

    # We track panel_removed to ensure rename does NOT remove
    removed = []
    cc.subscribe("panel_removed", removed.append)

    controller.rename_profile("p0", "Renamed Profile")
    assert len(removed) == 0  # rename should NOT remove


# ---------------------------------------------------------------------------
# change_mode
# ---------------------------------------------------------------------------


def test_change_mode_side_by_side_to_overlay_valid():
    store, controller, state, cc, profiles = make_env(2, same_x=True)
    mode_changed = []
    cc.subscribe("comparison_mode_changed", mode_changed.append)

    cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)

    ok = cc.change_mode(ComparisonMode.OVERLAY)
    assert ok is True
    assert cc.current_mode == ComparisonMode.OVERLAY
    assert "overlay" in mode_changed


def test_change_mode_to_overlay_incompatible_x_error():
    store, controller, state, cc, profiles = make_env(2, same_x=False)
    errors = []
    cc.subscribe("error_occurred", errors.append)

    cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)

    ok = cc.change_mode(ComparisonMode.OVERLAY)
    assert ok is False
    assert len(errors) == 1
    assert cc.current_mode == ComparisonMode.SIDE_BY_SIDE  # unchanged


def test_change_mode_to_difference_with_3_profiles_error():
    store, controller, state, cc, profiles = make_env(3, same_x=True)
    errors = []
    cc.subscribe("error_occurred", errors.append)

    cc.start_comparison("ds-1", ["p0", "p1", "p2"], ComparisonMode.SIDE_BY_SIDE)

    ok = cc.change_mode(ComparisonMode.DIFFERENCE)
    assert ok is False
    assert len(errors) == 1


def test_change_mode_not_active_returns_false():
    store, controller, state, cc, profiles = make_env(2)
    ok = cc.change_mode(ComparisonMode.OVERLAY)
    assert ok is False


def test_change_mode_to_single_stops_comparison():
    store, controller, state, cc, profiles = make_env(2)
    ended = []
    cc.subscribe("comparison_ended", lambda: ended.append(True))

    cc.start_comparison("ds-1", ["p0", "p1"], ComparisonMode.SIDE_BY_SIDE)

    ok = cc.change_mode(ComparisonMode.SINGLE)
    assert ok is True
    assert cc.is_active is False
    assert len(ended) == 1


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_properties_reflect_state():
    store, controller, state, cc, profiles = make_env(3, same_x=True)
    cc.start_comparison("ds-1", ["p0", "p1", "p2"], ComparisonMode.SIDE_BY_SIDE)

    assert cc.is_active is True
    assert set(cc.current_profiles) == {"p0", "p1", "p2"}
    assert cc.current_mode == ComparisonMode.SIDE_BY_SIDE
    assert cc.dataset_id == "ds-1"
