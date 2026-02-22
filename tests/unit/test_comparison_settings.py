"""
ComparisonSettings Extension Tests — Profile Comparison (Module A)

Tests for:
- New ComparisonSettings fields (comparison_target, comparison_profile_ids, comparison_dataset_id)
- AppState profile comparison methods (set_profile_comparison, clear_profile_comparison)
- is_profile_comparison_active property
- FR-8: Mutual exclusivity between dataset and profile comparison
- Backward compatibility with existing ComparisonSettings behavior
"""

import pytest

from data_graph_studio.core.state import (
    AppState,
    ComparisonMode,
    ComparisonSettings,
)
from data_graph_studio.ui.adapters.app_state_adapter import AppStateAdapter


# ==================== ComparisonSettings Dataclass Tests ====================


class TestComparisonSettingsExtension:
    """New fields on ComparisonSettings dataclass."""

    def test_default_comparison_target_is_dataset(self):
        """comparison_target defaults to 'dataset'."""
        settings = ComparisonSettings()
        assert settings.comparison_target == "dataset"

    def test_default_comparison_profile_ids_empty(self):
        """comparison_profile_ids defaults to empty list."""
        settings = ComparisonSettings()
        assert settings.comparison_profile_ids == []

    def test_default_comparison_dataset_id_empty(self):
        """comparison_dataset_id defaults to empty string."""
        settings = ComparisonSettings()
        assert settings.comparison_dataset_id == ""

    def test_set_comparison_target_to_profile(self):
        """Can set comparison_target to 'profile'."""
        settings = ComparisonSettings(comparison_target="profile")
        assert settings.comparison_target == "profile"

    def test_set_comparison_profile_ids(self):
        """Can set comparison_profile_ids."""
        ids = ["p1", "p2", "p3"]
        settings = ComparisonSettings(comparison_profile_ids=ids)
        assert settings.comparison_profile_ids == ids

    def test_set_comparison_dataset_id(self):
        """Can set comparison_dataset_id."""
        settings = ComparisonSettings(comparison_dataset_id="ds-abc")
        assert settings.comparison_dataset_id == "ds-abc"

    def test_existing_fields_unchanged(self):
        """Existing fields still have correct defaults."""
        settings = ComparisonSettings()
        assert settings.mode == ComparisonMode.SINGLE
        assert settings.comparison_datasets == []
        assert settings.key_column is None
        assert settings.sync_scroll is True
        assert settings.sync_zoom is True
        assert settings.sync_pan_x is True
        assert settings.sync_pan_y is True
        assert settings.sync_selection is False
        assert settings.auto_align is True

    def test_profile_ids_are_independent_instances(self):
        """Each ComparisonSettings instance has its own list."""
        s1 = ComparisonSettings()
        s2 = ComparisonSettings()
        s1.comparison_profile_ids.append("p1")
        assert s2.comparison_profile_ids == []


# ==================== AppState Profile Comparison Tests ====================


class TestAppStateProfileComparison:
    """AppState profile comparison methods."""

    @pytest.fixture
    def state(self, qtbot):
        return AppState()

    @pytest.fixture
    def adapter(self, state, qtbot):
        return AppStateAdapter(state)

    # ---------- set_profile_comparison ----------

    def test_set_profile_comparison_basic(self, state):
        """set_profile_comparison sets correct fields."""
        state.set_profile_comparison("ds-1", ["p1", "p2"])

        cs = state.comparison_settings
        assert cs.comparison_target == "profile"
        assert cs.comparison_dataset_id == "ds-1"
        assert cs.comparison_profile_ids == ["p1", "p2"]

    def test_set_profile_comparison_changes_mode_to_side_by_side(self, state):
        """set_profile_comparison activates SIDE_BY_SIDE mode by default
        (when currently SINGLE)."""
        state.set_profile_comparison("ds-1", ["p1", "p2"])
        assert state.comparison_mode != ComparisonMode.SINGLE

    def test_set_profile_comparison_emits_signal(self, state, adapter, qtbot):
        """set_profile_comparison emits comparison_settings_changed."""
        with qtbot.waitSignal(adapter.comparison_settings_changed, timeout=1000):
            state.set_profile_comparison("ds-1", ["p1", "p2"])

    def test_set_profile_comparison_emits_mode_signal(self, state, adapter, qtbot):
        """set_profile_comparison emits comparison_mode_changed when mode changes."""
        with qtbot.waitSignal(adapter.comparison_mode_changed, timeout=1000):
            state.set_profile_comparison("ds-1", ["p1", "p2"])

    # ---------- clear_profile_comparison ----------

    def test_clear_profile_comparison(self, state):
        """clear_profile_comparison resets profile comparison fields."""
        state.set_profile_comparison("ds-1", ["p1", "p2"])
        state.clear_profile_comparison()

        cs = state.comparison_settings
        assert cs.comparison_target == "dataset"
        assert cs.comparison_profile_ids == []
        assert cs.comparison_dataset_id == ""
        assert cs.mode == ComparisonMode.SINGLE

    def test_clear_profile_comparison_emits_signal(self, state, adapter, qtbot):
        """clear_profile_comparison emits comparison_settings_changed."""
        state.set_profile_comparison("ds-1", ["p1", "p2"])
        with qtbot.waitSignal(adapter.comparison_settings_changed, timeout=1000):
            state.clear_profile_comparison()

    def test_clear_profile_comparison_noop_when_inactive(self, state, qtbot):
        """clear_profile_comparison is safe to call when no profile comparison active."""
        # Should not raise
        state.clear_profile_comparison()
        assert state.comparison_settings.comparison_target == "dataset"

    # ---------- is_profile_comparison_active ----------

    def test_is_profile_comparison_active_false_by_default(self, state):
        """is_profile_comparison_active is False initially."""
        assert state.is_profile_comparison_active is False

    def test_is_profile_comparison_active_true_after_set(self, state):
        """is_profile_comparison_active is True after set_profile_comparison."""
        state.set_profile_comparison("ds-1", ["p1", "p2"])
        assert state.is_profile_comparison_active is True

    def test_is_profile_comparison_active_false_after_clear(self, state):
        """is_profile_comparison_active is False after clear_profile_comparison."""
        state.set_profile_comparison("ds-1", ["p1", "p2"])
        state.clear_profile_comparison()
        assert state.is_profile_comparison_active is False


# ==================== FR-8: Mutual Exclusivity Tests ====================


class TestMutualExclusivity:
    """FR-8: Dataset comparison and profile comparison are mutually exclusive."""

    @pytest.fixture
    def state(self, qtbot):
        s = AppState()
        # Add datasets so dataset comparison methods work
        s.add_dataset(dataset_id="ds-1", name="D1", row_count=10, column_count=2, memory_bytes=100)
        s.add_dataset(dataset_id="ds-2", name="D2", row_count=10, column_count=2, memory_bytes=100)
        return s

    def test_profile_comparison_clears_dataset_comparison(self, state):
        """Entering profile comparison auto-clears dataset comparison."""
        # Activate dataset comparison
        state.set_comparison_mode(ComparisonMode.SIDE_BY_SIDE)
        state.set_comparison_datasets(["ds-1", "ds-2"])
        assert state.comparison_mode == ComparisonMode.SIDE_BY_SIDE
        assert state.comparison_settings.comparison_target == "dataset"

        # Enter profile comparison → dataset comparison should be cleared
        state.set_profile_comparison("ds-1", ["p1", "p2"])

        assert state.comparison_settings.comparison_target == "profile"
        # Dataset comparison list should be cleared
        assert state.comparison_settings.comparison_datasets == []

    def test_dataset_comparison_clears_profile_comparison(self, state):
        """Entering dataset comparison auto-clears profile comparison."""
        # Activate profile comparison
        state.set_profile_comparison("ds-1", ["p1", "p2"])
        assert state.is_profile_comparison_active is True

        # Enter dataset comparison → profile comparison should be cleared
        state.set_comparison_mode(ComparisonMode.OVERLAY)

        assert state.comparison_settings.comparison_target == "dataset"
        assert state.comparison_settings.comparison_profile_ids == []
        assert state.comparison_settings.comparison_dataset_id == ""
        assert state.is_profile_comparison_active is False

    def test_set_comparison_datasets_clears_profile(self, state):
        """set_comparison_datasets also clears profile comparison."""
        state.set_profile_comparison("ds-1", ["p1", "p2"])
        assert state.is_profile_comparison_active is True

        state.set_comparison_datasets(["ds-1", "ds-2"])

        assert state.is_profile_comparison_active is False
        assert state.comparison_settings.comparison_target == "dataset"

    def test_switching_back_and_forth(self, state):
        """Can switch between dataset and profile comparison multiple times."""
        # Profile comparison
        state.set_profile_comparison("ds-1", ["p1", "p2"])
        assert state.is_profile_comparison_active is True

        # Dataset comparison
        state.set_comparison_mode(ComparisonMode.SIDE_BY_SIDE)
        assert state.is_profile_comparison_active is False

        # Profile comparison again
        state.set_profile_comparison("ds-2", ["p3", "p4"])
        assert state.is_profile_comparison_active is True
        assert state.comparison_settings.comparison_dataset_id == "ds-2"
        assert state.comparison_settings.comparison_profile_ids == ["p3", "p4"]


# ==================== Backward Compatibility Tests ====================


class TestBackwardCompatibility:
    """Ensure existing dataset comparison behavior is not broken."""

    @pytest.fixture
    def state(self, qtbot):
        s = AppState()
        s.add_dataset(dataset_id="ds-1", name="D1", row_count=10, column_count=2, memory_bytes=100)
        s.add_dataset(dataset_id="ds-2", name="D2", row_count=10, column_count=2, memory_bytes=100)
        return s

    @pytest.fixture
    def adapter(self, state, qtbot):
        return AppStateAdapter(state)

    def test_set_comparison_mode_still_works(self, state, adapter, qtbot):
        """set_comparison_mode still works as before for dataset comparison."""
        with qtbot.waitSignal(adapter.comparison_mode_changed, timeout=1000):
            state.set_comparison_mode(ComparisonMode.OVERLAY)
        assert state.comparison_mode == ComparisonMode.OVERLAY

    def test_set_comparison_datasets_still_works(self, state, adapter, qtbot):
        """set_comparison_datasets still works as before."""
        with qtbot.waitSignal(adapter.comparison_settings_changed, timeout=1000):
            state.set_comparison_datasets(["ds-1", "ds-2"])
        assert state.comparison_dataset_ids == ["ds-1", "ds-2"]

    def test_toggle_dataset_comparison_still_works(self, state):
        """toggle_dataset_comparison still works."""
        result = state.toggle_dataset_comparison("ds-1")
        # Should return a bool
        assert isinstance(result, bool)

    def test_update_comparison_settings_still_works(self, state, adapter, qtbot):
        """update_comparison_settings still works with existing fields."""
        with qtbot.waitSignal(adapter.comparison_settings_changed, timeout=1000):
            state.update_comparison_settings(sync_zoom=False, sync_pan_x=False)

        assert state.comparison_settings.sync_zoom is False
        assert state.comparison_settings.sync_pan_x is False

    def test_comparison_settings_property(self, state):
        """comparison_settings property still returns ComparisonSettings."""
        cs = state.comparison_settings
        assert isinstance(cs, ComparisonSettings)

    def test_dataset_single_mode_not_affected(self, state):
        """SINGLE mode still works as before."""
        state.set_comparison_mode(ComparisonMode.SINGLE)
        assert state.comparison_mode == ComparisonMode.SINGLE
        assert state.is_profile_comparison_active is False
