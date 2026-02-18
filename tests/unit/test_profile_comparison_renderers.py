"""
Tests for Profile Comparison Renderers (Wave 3: Modules D, E, F).

TDD: tests written before implementation.

UT-6:  can_overlay — same x_column=True, different=False, None=False
UT-7:  compute_diff — correct diff, mean, max, RMSE values
UT-9:  Dual-axis detection — ratio >10 → dual, ≤10 → single
UT-10: Mixed chart_type detection
       can_difference — exactly 2 + same x_column
       ProfileSideBySideLayout creation and profile setting
       ProfileSideBySideLayout on_profile_deleted with <2 remaining → exit_requested
       ProfileOverlayRenderer creation
       ProfileDifferenceRenderer creation
"""

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QWidget


# ---------------------------------------------------------------------------
# Ensure QApplication
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _ensure_qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Helpers: fake DataEngine / ProfileStore
# ---------------------------------------------------------------------------


class FakeDatasetInfo:
    """Minimal DatasetInfo-like object."""

    def __init__(self, row_count=100, columns=None, data=None):
        self.row_count = row_count
        self._columns = columns or ["time", "voltage", "current"]
        self._data = data

    @property
    def df(self):
        if self._data is not None:
            return self._data
        mock_df = MagicMock()
        mock_df.columns = self._columns
        mock_df.__len__ = lambda s: self.row_count

        class FakeSeries:
            def __init__(self, n):
                self._data = np.random.randn(n)
            def mean(self): return float(np.mean(self._data))
            def min(self): return float(np.min(self._data))
            def max(self): return float(np.max(self._data))
            def to_numpy(self): return self._data

        series_cache = {}
        def getitem(key):
            if key not in series_cache:
                series_cache[key] = FakeSeries(self.row_count)
            return series_cache[key]
        mock_df.__getitem__ = getitem
        mock_df.__contains__ = lambda s, k: k in self._columns
        return mock_df


class FakeDataEngine:
    """Fake DataEngine for testing without real data."""

    def __init__(self):
        self._datasets = {}

    def add_dataset(self, dataset_id, row_count=100, columns=None, data=None):
        self._datasets[dataset_id] = FakeDatasetInfo(
            row_count=row_count, columns=columns, data=data
        )

    def get_dataset(self, dataset_id):
        return self._datasets.get(dataset_id)

    def get_numeric_columns(self, dataset_id):
        ds = self._datasets.get(dataset_id)
        if ds:
            return [c for c in ds._columns if c != "time"]
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def state(qtbot):
    from data_graph_studio.core.state import AppState
    s = AppState()
    s.add_dataset(
        dataset_id="ds-1", name="Test Dataset",
        row_count=100, column_count=3, memory_bytes=1000,
    )
    s.set_x_column("time")
    s.add_value_column("voltage")
    return s


@pytest.fixture()
def engine():
    eng = FakeDataEngine()
    eng.add_dataset("ds-1", row_count=100, columns=["time", "voltage", "current"])
    return eng


@pytest.fixture()
def store():
    from data_graph_studio.core.profile_store import ProfileStore
    from data_graph_studio.core.profile import GraphSetting
    s = ProfileStore()
    # Profile A: line, x=time, y=voltage
    s.add(GraphSetting(
        id="p1", name="Voltage", dataset_id="ds-1",
        chart_type="line", x_column="time",
        value_columns=({"name": "voltage", "aggregation": "sum", "color": "#1f77b4",
                        "use_secondary_axis": False, "order": 0, "formula": ""},),
    ))
    # Profile B: bar, x=time, y=current
    s.add(GraphSetting(
        id="p2", name="Current", dataset_id="ds-1",
        chart_type="bar", x_column="time",
        value_columns=({"name": "current", "aggregation": "sum", "color": "#ff7f0e",
                        "use_secondary_axis": False, "order": 0, "formula": ""},),
    ))
    # Profile C: line, x=voltage, y=current (different x_column)
    s.add(GraphSetting(
        id="p3", name="V-I Curve", dataset_id="ds-1",
        chart_type="line", x_column="voltage",
        value_columns=({"name": "current", "aggregation": "sum", "color": "#2ca02c",
                        "use_secondary_axis": False, "order": 0, "formula": ""},),
    ))
    # Profile D: line, x=None
    s.add(GraphSetting(
        id="p4", name="NoX", dataset_id="ds-1",
        chart_type="line", x_column=None,
        value_columns=({"name": "voltage", "aggregation": "sum", "color": "#d62728",
                        "use_secondary_axis": False, "order": 0, "formula": ""},),
    ))
    return s


# ---------------------------------------------------------------------------
# UT-6: can_overlay — same x_column check
# ---------------------------------------------------------------------------


class TestCanOverlay:
    """UT-6: ProfileOverlayRenderer.can_overlay — X column match check."""

    def test_same_x_column_returns_true(self, store):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        p1 = store.get("p1")
        p2 = store.get("p2")
        assert ProfileOverlayRenderer.can_overlay([p1, p2]) is True

    def test_different_x_column_returns_false(self, store):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        p1 = store.get("p1")  # x=time
        p3 = store.get("p3")  # x=voltage
        assert ProfileOverlayRenderer.can_overlay([p1, p3]) is False

    def test_none_x_column_returns_false(self, store):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        p4 = store.get("p4")  # x=None
        p1 = store.get("p1")
        assert ProfileOverlayRenderer.can_overlay([p4, p1]) is False

    def test_all_none_returns_false(self, store):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        p4 = store.get("p4")  # x=None
        from data_graph_studio.core.profile import GraphSetting
        p5 = GraphSetting(id="p5", name="NoX2", dataset_id="ds-1",
                          chart_type="line", x_column=None)
        assert ProfileOverlayRenderer.can_overlay([p4, p5]) is False

    def test_single_profile_same_x_returns_true(self, store):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        p1 = store.get("p1")
        assert ProfileOverlayRenderer.can_overlay([p1]) is True

    def test_empty_list_returns_false(self):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        assert ProfileOverlayRenderer.can_overlay([]) is False

    def test_three_same_x_returns_true(self, store):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        from data_graph_studio.core.profile import GraphSetting
        p1 = store.get("p1")  # x=time
        p2 = store.get("p2")  # x=time
        p_extra = GraphSetting(id="p_extra", name="Extra", dataset_id="ds-1",
                               chart_type="line", x_column="time",
                               value_columns=({"name": "voltage"},))
        assert ProfileOverlayRenderer.can_overlay([p1, p2, p_extra]) is True


# ---------------------------------------------------------------------------
# UT-7: compute_diff — correct diff, mean, max, RMSE
# ---------------------------------------------------------------------------


class TestComputeDiff:
    """UT-7: ProfileDifferenceRenderer.compute_diff correctness."""

    def test_basic_diff(self):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        import pandas as pd

        df = pd.DataFrame({
            "y_a": [10.0, 20.0, 30.0, 40.0],
            "y_b": [5.0, 15.0, 25.0, 35.0],
        })

        result = ProfileDifferenceRenderer.compute_diff(df, "y_a", "y_b")

        expected_diff = np.array([5.0, 5.0, 5.0, 5.0])
        np.testing.assert_array_almost_equal(result["diff_series"], expected_diff)
        assert result["mean_diff"] == pytest.approx(5.0)
        assert result["max_diff"] == pytest.approx(5.0)
        assert result["rmse"] == pytest.approx(5.0)

    def test_negative_diff(self):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        import pandas as pd

        df = pd.DataFrame({
            "y_a": [1.0, 2.0, 3.0],
            "y_b": [4.0, 5.0, 6.0],
        })

        result = ProfileDifferenceRenderer.compute_diff(df, "y_a", "y_b")

        expected_diff = np.array([-3.0, -3.0, -3.0])
        np.testing.assert_array_almost_equal(result["diff_series"], expected_diff)
        # mean_diff = mean of absolute diff
        assert result["mean_diff"] == pytest.approx(3.0)
        # max_diff = max of absolute diff
        assert result["max_diff"] == pytest.approx(3.0)
        assert result["rmse"] == pytest.approx(3.0)

    def test_mixed_diff(self):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        import pandas as pd

        df = pd.DataFrame({
            "y_a": [10.0, 5.0],
            "y_b": [5.0, 10.0],
        })

        result = ProfileDifferenceRenderer.compute_diff(df, "y_a", "y_b")

        expected_diff = np.array([5.0, -5.0])
        np.testing.assert_array_almost_equal(result["diff_series"], expected_diff)
        assert result["mean_diff"] == pytest.approx(5.0)
        assert result["max_diff"] == pytest.approx(5.0)
        # RMSE = sqrt(mean(25 + 25)) = sqrt(25) = 5.0
        assert result["rmse"] == pytest.approx(5.0)

    def test_rmse_calculation(self):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        import pandas as pd

        df = pd.DataFrame({
            "y_a": [3.0, 0.0],
            "y_b": [0.0, 4.0],
        })

        result = ProfileDifferenceRenderer.compute_diff(df, "y_a", "y_b")

        # diff = [3, -4], rmse = sqrt((9+16)/2) = sqrt(12.5)
        assert result["rmse"] == pytest.approx(math.sqrt(12.5))

    def test_empty_df(self):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        import pandas as pd

        df = pd.DataFrame({"y_a": [], "y_b": []})

        result = ProfileDifferenceRenderer.compute_diff(df, "y_a", "y_b")

        assert len(result["diff_series"]) == 0


# ---------------------------------------------------------------------------
# can_difference — exactly 2 + same x_column
# ---------------------------------------------------------------------------


class TestCanDifference:
    """ProfileDifferenceRenderer.can_difference."""

    def test_two_profiles_same_x_returns_true(self, store):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        p1 = store.get("p1")  # x=time
        p2 = store.get("p2")  # x=time
        assert ProfileDifferenceRenderer.can_difference([p1, p2]) is True

    def test_three_profiles_returns_true(self, store):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        from data_graph_studio.core.profile import GraphSetting
        p1 = store.get("p1")
        p2 = store.get("p2")
        p_extra = GraphSetting(id="px", name="X", dataset_id="ds-1",
                               chart_type="line", x_column="time")
        # New behavior: difference mode supports 2+ profiles (same X)
        assert ProfileDifferenceRenderer.can_difference([p1, p2, p_extra]) is True

    def test_one_profile_returns_false(self, store):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        p1 = store.get("p1")
        assert ProfileDifferenceRenderer.can_difference([p1]) is False

    def test_two_profiles_different_x_returns_false(self, store):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        p1 = store.get("p1")  # x=time
        p3 = store.get("p3")  # x=voltage
        assert ProfileDifferenceRenderer.can_difference([p1, p3]) is False

    def test_two_profiles_none_x_returns_false(self, store):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        from data_graph_studio.core.profile import GraphSetting
        pa = GraphSetting(id="pa", name="A", dataset_id="ds-1",
                          chart_type="line", x_column=None)
        pb = GraphSetting(id="pb", name="B", dataset_id="ds-1",
                          chart_type="line", x_column=None)
        assert ProfileDifferenceRenderer.can_difference([pa, pb]) is False

    def test_empty_list_returns_false(self):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        assert ProfileDifferenceRenderer.can_difference([]) is False


# ---------------------------------------------------------------------------
# UT-9: Dual-axis detection — ratio >10 → dual, ≤10 → single
# ---------------------------------------------------------------------------


class TestDualAxisDetection:
    """UT-9: ProfileOverlayRenderer dual-axis detection."""

    def test_ratio_above_10_returns_true(self):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer

        # Y_A range: 0-100, Y_B range: 0-5  →  ratio = 100/5 = 20 > 10
        assert ProfileOverlayRenderer.needs_dual_axis(100.0, 5.0) is True

    def test_ratio_below_10_returns_false(self):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer

        # Y_A range: 0-10, Y_B range: 0-5  →  ratio = 10/5 = 2 ≤ 10
        assert ProfileOverlayRenderer.needs_dual_axis(10.0, 5.0) is False

    def test_ratio_exactly_10_returns_false(self):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer

        # ratio = 50/5 = 10 → not strictly > 10
        assert ProfileOverlayRenderer.needs_dual_axis(50.0, 5.0) is False

    def test_inverse_ratio_above_10_returns_true(self):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer

        # Y_A range: 0-3, Y_B range: 0-100  →  ratio = 100/3 > 10
        assert ProfileOverlayRenderer.needs_dual_axis(3.0, 100.0) is True

    def test_zero_max_returns_false(self):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer

        # Edge case: zero max → avoid division by zero, return False
        assert ProfileOverlayRenderer.needs_dual_axis(0.0, 5.0) is False
        assert ProfileOverlayRenderer.needs_dual_axis(5.0, 0.0) is False

    def test_both_zero_returns_false(self):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        assert ProfileOverlayRenderer.needs_dual_axis(0.0, 0.0) is False

    def test_equal_values_returns_false(self):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        assert ProfileOverlayRenderer.needs_dual_axis(50.0, 50.0) is False


# ---------------------------------------------------------------------------
# UT-10: Mixed chart_type detection
# ---------------------------------------------------------------------------


class TestMixedChartTypeDetection:
    """UT-10: ProfileOverlayRenderer.has_mixed_chart_types."""

    def test_all_same_type_returns_false(self, store):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        from data_graph_studio.core.profile import GraphSetting
        pa = GraphSetting(id="a", name="A", dataset_id="ds-1",
                          chart_type="line", x_column="time")
        pb = GraphSetting(id="b", name="B", dataset_id="ds-1",
                          chart_type="line", x_column="time")
        assert ProfileOverlayRenderer.has_mixed_chart_types([pa, pb]) is False

    def test_different_types_returns_true(self, store):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        p1 = store.get("p1")  # chart_type="line"
        p2 = store.get("p2")  # chart_type="bar"
        assert ProfileOverlayRenderer.has_mixed_chart_types([p1, p2]) is True

    def test_single_profile_returns_false(self, store):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        p1 = store.get("p1")
        assert ProfileOverlayRenderer.has_mixed_chart_types([p1]) is False

    def test_empty_list_returns_false(self):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        assert ProfileOverlayRenderer.has_mixed_chart_types([]) is False


# ---------------------------------------------------------------------------
# ProfileSideBySideLayout: creation and profile setting
# ---------------------------------------------------------------------------


class TestProfileSideBySideLayoutCreation:
    """ProfileSideBySideLayout creation and basic operations."""

    def test_creation(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        assert w is not None

    def test_has_exit_requested_signal(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        assert hasattr(w, "exit_requested")

    def test_has_profile_activated_signal(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        assert hasattr(w, "profile_activated")

    def test_set_profiles(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles(["p1", "p2"])
        # Should have created panels for both profiles
        assert w._view_sync_manager.panel_count == 2

    def test_set_profiles_max_6(self, state, engine, store, qtbot):
        """MAX_PANELS = 6: up to first 6 profiles used."""
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        from data_graph_studio.core.profile import GraphSetting
        # Add more profiles to store
        for i in range(5, 12):
            store.add(GraphSetting(
                id=f"p{i}", name=f"Profile {i}", dataset_id="ds-1",
                chart_type="line", x_column="time",
            ))

        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles(["p1", "p2", "p3", "p5", "p6", "p7", "p8"])
        assert w._view_sync_manager.panel_count == 6  # MAX_PANELS

    def test_has_view_sync_manager(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        from data_graph_studio.core.view_sync import ViewSyncManager
        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        assert hasattr(w, "_view_sync_manager")
        assert isinstance(w._view_sync_manager, ViewSyncManager)

    def test_refresh_does_not_crash(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles(["p1", "p2"])
        w.refresh()  # Should not raise


# ---------------------------------------------------------------------------
# ProfileSideBySideLayout: on_profile_deleted
# ---------------------------------------------------------------------------


class TestProfileSideBySideOnProfileDeleted:
    """FR-10: on_profile_deleted → remove panel; <2 remaining → exit_requested."""

    def test_removes_panel_on_delete(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles(["p1", "p2", "p3"])
        assert w._view_sync_manager.panel_count == 3

        w.on_profile_deleted("p2")
        assert w._view_sync_manager.panel_count == 2

    def test_exit_requested_when_less_than_2(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles(["p1", "p2"])
        assert w._view_sync_manager.panel_count == 2

        with qtbot.waitSignal(w.exit_requested, timeout=1000):
            w.on_profile_deleted("p1")

    def test_on_profile_renamed_updates_header(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout
        w = ProfileSideBySideLayout("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles(["p1", "p2"])

        # Should not raise
        w.on_profile_renamed("p1", "Voltage (renamed)")


# ---------------------------------------------------------------------------
# ProfileOverlayRenderer: creation
# ---------------------------------------------------------------------------


class TestProfileOverlayRendererCreation:
    """ProfileOverlayRenderer creation and basic operations."""

    def test_creation(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        w = ProfileOverlayRenderer("ds-1", engine, state, store)
        qtbot.addWidget(w)
        assert w is not None

    def test_has_exit_requested_signal(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        w = ProfileOverlayRenderer("ds-1", engine, state, store)
        qtbot.addWidget(w)
        assert hasattr(w, "exit_requested")

    def test_set_profiles_does_not_crash(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        w = ProfileOverlayRenderer("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles(["p1", "p2"])

    def test_refresh_does_not_crash(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_overlay import ProfileOverlayRenderer
        w = ProfileOverlayRenderer("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles(["p1", "p2"])
        w.refresh()


# ---------------------------------------------------------------------------
# ProfileDifferenceRenderer: creation
# ---------------------------------------------------------------------------


class TestProfileDifferenceRendererCreation:
    """ProfileDifferenceRenderer creation and basic operations."""

    def test_creation(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        w = ProfileDifferenceRenderer("ds-1", engine, state, store)
        qtbot.addWidget(w)
        assert w is not None

    def test_has_exit_requested_signal(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        w = ProfileDifferenceRenderer("ds-1", engine, state, store)
        qtbot.addWidget(w)
        assert hasattr(w, "exit_requested")

    def test_set_profiles_does_not_crash(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        w = ProfileDifferenceRenderer("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles("p1", "p2")

    def test_refresh_does_not_crash(self, state, engine, store, qtbot):
        from data_graph_studio.ui.panels.profile_difference import ProfileDifferenceRenderer
        w = ProfileDifferenceRenderer("ds-1", engine, state, store)
        qtbot.addWidget(w)
        w.set_profiles("p1", "p2")
        w.refresh()
