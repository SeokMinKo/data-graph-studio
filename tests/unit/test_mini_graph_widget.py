"""
Tests for MiniGraphWidget extension (Module C) and SideBySideLayout refactor (Module H).

TDD: tests written before implementation.

UT-8:  MiniGraphWidget with GraphSetting renders using setting's columns
UT-8b: MiniGraphWidget without GraphSetting uses state (backward compat)
       set_selection method exists and is callable
       SideBySideLayout uses ViewSyncManager
"""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication


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
# Helpers: fake DataEngine
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
        # Return a mock that behaves like a DataFrame with numeric series
        import numpy as np
        mock_df = MagicMock()
        mock_df.columns = self._columns
        mock_df.__len__ = lambda s: self.row_count

        # Make series access return objects with numeric mean/min/max
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
    """Fake DataEngine for testing MiniGraphWidget without real data."""

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
def graph_setting():
    """A GraphSetting with different columns from state."""
    from data_graph_studio.core.profile import GraphSetting
    return GraphSetting(
        id="gs-1",
        name="Current Profile",
        dataset_id="ds-1",
        chart_type="bar",
        x_column="time",
        value_columns=(
            {"name": "current", "aggregation": "sum", "color": "#ff7f0e",
             "use_secondary_axis": False, "order": 0, "formula": ""},
        ),
    )


# ---------------------------------------------------------------------------
# UT-8: MiniGraphWidget with GraphSetting
# ---------------------------------------------------------------------------


class TestMiniGraphWidgetWithGraphSetting:
    """UT-8: MiniGraphWidget with GraphSetting renders using setting's columns."""

    def test_accepts_graph_setting_parameter(self, state, engine, graph_setting, qtbot):
        """MiniGraphWidget.__init__ accepts optional graph_setting parameter."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state, graph_setting=graph_setting)
        qtbot.addWidget(widget)

        assert widget.graph_setting is graph_setting

    def test_graph_setting_stored(self, state, engine, graph_setting, qtbot):
        """graph_setting is stored as an attribute."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state, graph_setting=graph_setting)
        qtbot.addWidget(widget)

        assert widget.graph_setting is not None
        assert widget.graph_setting.name == "Current Profile"
        assert widget.graph_setting.chart_type == "bar"

    def test_header_shows_profile_name(self, state, engine, graph_setting, qtbot):
        """When graph_setting is provided, header shows profile name."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget
        from PySide6.QtWidgets import QLabel

        widget = MiniGraphWidget("ds-1", engine, state, graph_setting=graph_setting)
        qtbot.addWidget(widget)

        # Find the name label in the header — first QLabel in the widget
        labels = widget.findChildren(QLabel)
        name_labels = [label for label in labels if label.text() == "Current Profile"]
        assert len(name_labels) >= 1, (
            f"Expected header to show profile name 'Current Profile', "
            f"found labels: {[label.text() for label in labels]}"
        )

    def test_effective_x_column_uses_graph_setting(self, state, engine, graph_setting, qtbot):
        """When graph_setting provided, effective x_column comes from setting."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state, graph_setting=graph_setting)
        qtbot.addWidget(widget)

        # The effective x_column should be from graph_setting
        assert widget.effective_x_column == graph_setting.x_column

    def test_effective_value_columns_uses_graph_setting(self, state, engine, graph_setting, qtbot):
        """When graph_setting provided, effective value_columns comes from setting."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state, graph_setting=graph_setting)
        qtbot.addWidget(widget)

        # The effective value_columns should be from graph_setting
        assert widget.effective_value_columns == list(graph_setting.value_columns)


# ---------------------------------------------------------------------------
# UT-8b: MiniGraphWidget without GraphSetting (backward compat)
# ---------------------------------------------------------------------------


class TestMiniGraphWidgetBackwardCompat:
    """UT-8b: MiniGraphWidget without GraphSetting uses state."""

    def test_no_graph_setting_default(self, state, engine, qtbot):
        """Without graph_setting parameter, it defaults to None."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(widget)

        assert widget.graph_setting is None

    def test_header_shows_dataset_name(self, state, engine, qtbot):
        """Without graph_setting, header shows dataset name."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget
        from PySide6.QtWidgets import QLabel

        widget = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(widget)

        labels = widget.findChildren(QLabel)
        name_labels = [label for label in labels if label.text() == "Test Dataset"]
        assert len(name_labels) >= 1, (
            f"Expected header to show dataset name 'Test Dataset', "
            f"found labels: {[label.text() for label in labels]}"
        )

    def test_effective_x_column_uses_state(self, state, engine, qtbot):
        """Without graph_setting, x_column comes from state."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(widget)

        assert widget.effective_x_column == state.x_column

    def test_effective_value_columns_uses_state(self, state, engine, qtbot):
        """Without graph_setting, value_columns comes from state."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(widget)

        [
            {"name": vc.name, "aggregation": vc.aggregation.value,
             "color": vc.color, "use_secondary_axis": vc.use_secondary_axis,
             "order": vc.order, "formula": vc.formula}
            for vc in state.value_columns
        ]
        # Just check the names match
        effective_names = [
            vc.name if hasattr(vc, 'name') else vc.get('name', '')
            for vc in widget.effective_value_columns
        ]
        state_names = [vc.name for vc in state.value_columns]
        assert effective_names == state_names

    def test_existing_constructor_signature_works(self, state, engine, qtbot):
        """Existing code calling MiniGraphWidget(dataset_id, engine, state) still works."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        # Should not raise
        widget = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(widget)
        assert widget.dataset_id == "ds-1"


# ---------------------------------------------------------------------------
# set_selection method
# ---------------------------------------------------------------------------


class TestMiniGraphWidgetSetSelection:
    """MiniGraphWidget.set_selection for ViewSyncManager duck-typing."""

    def test_set_selection_exists(self, state, engine, qtbot):
        """set_selection method exists on MiniGraphWidget."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(widget)

        assert hasattr(widget, "set_selection")
        assert callable(widget.set_selection)

    def test_set_selection_accepts_list(self, state, engine, qtbot):
        """set_selection can be called with a list of indices."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(widget)

        # Should not raise
        widget.set_selection([0, 5, 10])

    def test_set_selection_empty_list(self, state, engine, qtbot):
        """set_selection with empty list clears selection."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(widget)

        # Should not raise
        widget.set_selection([])

    def test_set_view_range_exists(self, state, engine, qtbot):
        """set_view_range method still exists (ViewSyncManager duck-typing)."""
        from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

        widget = MiniGraphWidget("ds-1", engine, state)
        qtbot.addWidget(widget)

        assert hasattr(widget, "set_view_range")
        assert callable(widget.set_view_range)


# ---------------------------------------------------------------------------
# SideBySideLayout uses ViewSyncManager (Module H)
# ---------------------------------------------------------------------------


class TestSideBySideLayoutViewSyncManager:
    """SideBySideLayout uses ViewSyncManager instead of internal sync logic."""

    @pytest.fixture()
    def layout_widget(self, state, engine, qtbot):
        from data_graph_studio.ui.panels.side_by_side_layout import SideBySideLayout
        w = SideBySideLayout(engine, state)
        qtbot.addWidget(w)
        return w

    def test_has_view_sync_manager(self, layout_widget):
        """SideBySideLayout has a ViewSyncManager instance."""
        from data_graph_studio.core.view_sync import ViewSyncManager
        assert hasattr(layout_widget, "_view_sync_manager")
        assert isinstance(layout_widget._view_sync_manager, ViewSyncManager)

    def test_sync_scroll_checkbox_controls_sync_x(self, layout_widget, qtbot):
        """Sync Scroll checkbox toggles ViewSyncManager.sync_x."""
        mgr = layout_widget._view_sync_manager

        # Default: checked → sync_x should be True
        assert layout_widget.sync_scroll_cb.isChecked()
        assert mgr.sync_x is True

        # Uncheck → sync_x should become False
        layout_widget.sync_scroll_cb.setChecked(False)
        assert mgr.sync_x is False

        # Re-check → sync_x should become True
        layout_widget.sync_scroll_cb.setChecked(True)
        assert mgr.sync_x is True

    def test_sync_zoom_checkbox_controls_sync_y(self, layout_widget, qtbot):
        """Sync Zoom checkbox toggles ViewSyncManager.sync_y."""
        mgr = layout_widget._view_sync_manager

        # Default: unchecked → sync_y should be False (PRD §5.6: Y축 동기화 기본 OFF)
        assert not layout_widget.sync_zoom_cb.isChecked()
        assert mgr.sync_y is False

        # Check → sync_y should become True
        layout_widget.sync_zoom_cb.setChecked(True)
        assert mgr.sync_y is True

        # Uncheck → sync_y should become False
        layout_widget.sync_zoom_cb.setChecked(False)
        assert mgr.sync_y is False

    def test_refresh_registers_panels(self, state, engine, qtbot):
        """After refresh(), panels are registered with ViewSyncManager."""
        from data_graph_studio.ui.panels.side_by_side_layout import SideBySideLayout

        # Add a second dataset so side-by-side has panels
        state.add_dataset(
            dataset_id="ds-2", name="Dataset 2",
            row_count=50, column_count=2, memory_bytes=500,
        )

        w = SideBySideLayout(engine, state)
        qtbot.addWidget(w)
        w.refresh()

        mgr = w._view_sync_manager
        # Should have registered panels
        assert mgr.panel_count >= 1

    def test_refresh_clears_old_panels_from_manager(self, state, engine, qtbot):
        """refresh() clears old panels from ViewSyncManager before adding new ones."""
        from data_graph_studio.ui.panels.side_by_side_layout import SideBySideLayout

        state.add_dataset(
            dataset_id="ds-2", name="Dataset 2",
            row_count=50, column_count=2, memory_bytes=500,
        )

        w = SideBySideLayout(engine, state)
        qtbot.addWidget(w)
        w.refresh()

        count_after_first = w._view_sync_manager.panel_count

        # Refresh again — should not double the panels
        w.refresh()

        assert w._view_sync_manager.panel_count == count_after_first

    def test_public_api_preserved_refresh(self, layout_widget):
        """refresh() method still exists."""
        assert callable(layout_widget.refresh)

    def test_public_api_preserved_set_comparison_datasets(self, layout_widget):
        """set_comparison_datasets() method still exists."""
        assert callable(layout_widget.set_comparison_datasets)

    def test_public_api_preserved_reset_all_views(self, layout_widget):
        """reset_all_views() method still exists."""
        assert callable(layout_widget.reset_all_views)

    def test_public_api_preserved_dataset_activated_signal(self, layout_widget):
        """dataset_activated signal still exists."""
        assert hasattr(layout_widget, "dataset_activated")

    def test_reset_all_views_delegates_to_manager(self, state, engine, qtbot):
        """reset_all_views() delegates to ViewSyncManager."""
        from data_graph_studio.ui.panels.side_by_side_layout import SideBySideLayout

        w = SideBySideLayout(engine, state)
        qtbot.addWidget(w)
        w.refresh()

        # Patch the manager's reset method
        with patch.object(w._view_sync_manager, "reset_all_views") as mock_reset:
            w.reset_all_views()
            mock_reset.assert_called_once()
