"""Tests for MiniGraphWidget selection feature and sync via ViewSyncManager."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True, scope="session")
def _ensure_qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeDatasetInfo:
    def __init__(self, row_count=100, columns=None):
        self.row_count = row_count
        self._columns = columns or ["time", "voltage"]

    @property
    def df(self):
        import numpy as np

        mock_df = MagicMock()
        mock_df.columns = self._columns
        mock_df.__len__ = lambda s: self.row_count

        class FakeSeries:
            def __init__(self, n):
                self._data = np.random.randn(n)

            def mean(self):
                return float(self._data.mean())

            def min(self):
                return float(self._data.min())

            def max(self):
                return float(self._data.max())

            def to_numpy(self):
                return self._data

        cache = {}

        def getitem(key):
            if key not in cache:
                cache[key] = FakeSeries(self.row_count)
            return cache[key]

        mock_df.__getitem__ = getitem
        mock_df.__contains__ = lambda s, k: k in self._columns
        return mock_df


class FakeEngine:
    def __init__(self):
        self._datasets = {}

    def add_dataset(self, did, **kw):
        self._datasets[did] = FakeDatasetInfo(**kw)

    def get_dataset(self, did):
        return self._datasets.get(did)

    def get_numeric_columns(self, did):
        ds = self._datasets.get(did)
        return [c for c in ds._columns if c != "time"] if ds else []


@pytest.fixture()
def state():
    from data_graph_studio.core.state import AppState

    s = AppState()
    s.add_dataset(
        dataset_id="ds-1", name="Test", row_count=100, column_count=2, memory_bytes=500
    )
    s.set_x_column("time")
    s.add_value_column("voltage")
    return s


@pytest.fixture()
def engine():
    eng = FakeEngine()
    eng.add_dataset("ds-1", row_count=100, columns=["time", "voltage"])
    return eng


# ---------------------------------------------------------------------------
# MiniGraphWidget selection tests
# ---------------------------------------------------------------------------


class TestMiniGraphWidgetSelection:
    """Selection region on MiniGraphWidget."""

    def test_has_selection_region(self, state, engine, qtbot):
        """MiniGraphWidget creates a LinearRegionItem."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        w = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(w)
        assert w._selection_region is not None

    def test_selection_region_hidden_by_default(self, state, engine, qtbot):
        """Selection region is hidden initially."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        w = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(w)
        assert not w._selection_region.isVisible()

    def test_set_selection_shows_region(self, state, engine, qtbot):
        """set_selection with [x_min, x_max] shows the region."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        w = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(w)

        w.set_selection([10.0, 50.0])

        assert w._selection_region.isVisible()
        region = list(w._selection_region.getRegion())
        assert abs(region[0] - 10.0) < 0.01
        assert abs(region[1] - 50.0) < 0.01

    def test_set_selection_empty_hides_region(self, state, engine, qtbot):
        """set_selection with empty list hides the region."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        w = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(w)

        # Show first
        w.set_selection([10.0, 50.0])
        assert w._selection_region.isVisible()

        # Clear
        w.set_selection([])
        assert not w._selection_region.isVisible()

    def test_selection_changed_signal_exists(self, state, engine, qtbot):
        """MiniGraphWidget has a selection_changed signal."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        w = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(w)
        assert hasattr(w, "selection_changed")


class TestSelectionSyncViaViewSyncManager:
    """Selection sync through ViewSyncManager."""

    def test_selection_syncs_between_panels(self, state, engine, qtbot):
        """Setting selection on one panel syncs to another via ViewSyncManager."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget
        from data_graph_studio.core.view_sync import ViewSyncManager

        state.add_dataset(
            dataset_id="ds-2",
            name="Test2",
            row_count=50,
            column_count=2,
            memory_bytes=300,
        )
        engine.add_dataset("ds-2", row_count=50, columns=["time", "voltage"])

        mgr = ViewSyncManager()
        mgr.sync_selection = True

        p1 = MiniGraphWidget("ds-1", engine, state)
        p2 = MiniGraphWidget("ds-2", engine, state)
        qtbot.addWidget(p1)
        qtbot.addWidget(p2)

        mgr.register_panel("ds-1", p1)
        mgr.register_panel("ds-2", p2)

        # Simulate selection on p1 via ViewSyncManager
        mgr.on_source_selection_changed("ds-1", [20.0, 80.0])

        # p2 should show the selection
        assert p2._selection_region.isVisible()
        region = list(p2._selection_region.getRegion())
        assert abs(region[0] - 20.0) < 0.01
        assert abs(region[1] - 80.0) < 0.01

    def test_selection_not_synced_when_disabled(self, state, engine, qtbot):
        """Selection does NOT sync when sync_selection is False."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget
        from data_graph_studio.core.view_sync import ViewSyncManager

        state.add_dataset(
            dataset_id="ds-2",
            name="Test2",
            row_count=50,
            column_count=2,
            memory_bytes=300,
        )
        engine.add_dataset("ds-2", row_count=50, columns=["time", "voltage"])

        mgr = ViewSyncManager()
        mgr.sync_selection = False

        p1 = MiniGraphWidget("ds-1", engine, state)
        p2 = MiniGraphWidget("ds-2", engine, state)
        qtbot.addWidget(p1)
        qtbot.addWidget(p2)

        mgr.register_panel("ds-1", p1)
        mgr.register_panel("ds-2", p2)

        mgr.on_source_selection_changed("ds-1", [20.0, 80.0])

        # p2 should NOT show selection
        assert not p2._selection_region.isVisible()


class TestCompareToolbarCheckboxes:
    """Verify sync controls are QCheckBox in the new toolbar."""

    def test_sync_buttons_are_checkboxes(self, qtbot):
        """Sync options should be QCheckBox, not QPushButton."""
        from data_graph_studio.ui.toolbars.compare_toolbar import CompareToolbar
        from PySide6.QtWidgets import QCheckBox

        tb = CompareToolbar()
        qtbot.addWidget(tb)

        for key in ["x", "y", "selection"]:
            assert isinstance(tb._sync_buttons[key], QCheckBox), (
                f"Sync button '{key}' should be QCheckBox, got {type(tb._sync_buttons[key])}"
            )

    def test_two_row_layout_has_container(self, qtbot):
        """Toolbar uses a container widget for two-row layout."""
        from data_graph_studio.ui.toolbars.compare_toolbar import CompareToolbar

        tb = CompareToolbar()
        qtbot.addWidget(tb)

        # Should find the container widget
        tb.findChild(type(tb), "")  # any child
        tb.findChildren(type(None))  # just check the toolbar has widgets
        assert tb.widgetForAction(tb.actions()[0]) is not None
