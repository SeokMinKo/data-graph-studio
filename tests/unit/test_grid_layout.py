"""Tests for ProfileSideBySideLayout grid layout switching."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QGridLayout


def _make_mock_store(profile_ids):
    """Create a mock ProfileStore with given profile IDs."""
    from data_graph_studio.core.profile import GraphSetting

    store = MagicMock()
    settings = {}
    for pid in profile_ids:
        gs = GraphSetting(
            id=pid,
            name=f"Profile {pid}",
            dataset_id="ds-1",
            chart_type="line",
            x_column="x",
            value_columns=({"name": "y"},),
        )
        settings[pid] = gs

    store.get.side_effect = lambda pid: settings.get(pid)
    return store


def _make_mock_engine():
    engine = MagicMock()
    ds = MagicMock()
    ds.df = None
    ds.row_count = 0
    engine.get_dataset.return_value = ds
    engine.get_numeric_columns.return_value = []
    return engine


def _make_mock_state():
    state = MagicMock()
    metadata = MagicMock()
    metadata.color = "#1f77b4"
    metadata.name = "Test"
    state.get_dataset_metadata.return_value = metadata
    return state


@pytest.fixture
def layout_widget(qtbot):
    """Create a ProfileSideBySideLayout with 4 profiles."""
    from data_graph_studio.ui.panels.profile_side_by_side import ProfileSideBySideLayout

    pids = ["p1", "p2", "p3", "p4"]
    store = _make_mock_store(pids)
    engine = _make_mock_engine()
    state = _make_mock_state()

    layout = ProfileSideBySideLayout("ds-1", engine, state, store)
    qtbot.addWidget(layout)
    layout.set_profiles(pids)
    return layout


class TestGridLayoutSwitching:
    """Verify set_grid_layout rearranges panels correctly."""

    def test_default_is_row(self, layout_widget):
        """Default layout is horizontal splitter (row)."""
        assert layout_widget._current_grid_layout == "row"
        assert layout_widget._splitter is not None
        assert layout_widget._splitter.orientation() == Qt.Horizontal

    def test_switch_to_column(self, layout_widget):
        """Switching to 'column' creates vertical splitter."""
        layout_widget.set_grid_layout("column")
        assert layout_widget._current_grid_layout == "column"
        assert layout_widget._splitter is not None
        assert layout_widget._splitter.orientation() == Qt.Vertical

    def test_switch_to_grid(self, layout_widget):
        """Switching to 'grid' creates QGridLayout container."""
        layout_widget.set_grid_layout("grid")
        assert layout_widget._current_grid_layout == "grid"
        assert layout_widget._grid_container is not None
        grid = layout_widget._grid_container.layout()
        assert isinstance(grid, QGridLayout)
        # 4 panels in 2×2 grid
        assert grid.count() == 4

    def test_switch_back_to_row(self, layout_widget):
        """Switching from grid back to row restores horizontal splitter."""
        layout_widget.set_grid_layout("grid")
        layout_widget.set_grid_layout("row")
        assert layout_widget._splitter is not None
        assert layout_widget._splitter.orientation() == Qt.Horizontal
        assert layout_widget._grid_container is None

    def test_panels_preserved_after_switch(self, layout_widget):
        """All 4 panels still exist after layout switch."""
        layout_widget.set_grid_layout("column")
        assert len(layout_widget._panels) == 4

        layout_widget.set_grid_layout("grid")
        assert len(layout_widget._panels) == 4

        layout_widget.set_grid_layout("row")
        assert len(layout_widget._panels) == 4


class TestSyncOptions:
    """Verify set_sync_option delegates to ViewSyncManager."""

    def test_set_sync_x(self, layout_widget):
        layout_widget.set_sync_option("x", False)
        assert layout_widget._view_sync_manager.sync_x is False

    def test_set_sync_y(self, layout_widget):
        layout_widget.set_sync_option("y", True)
        assert layout_widget._view_sync_manager.sync_y is True

    def test_set_sync_selection(self, layout_widget):
        layout_widget.set_sync_option("selection", False)
        assert layout_widget._view_sync_manager.sync_selection is False

    def test_set_sync_zoom(self, layout_widget):
        """Zoom sets both x and y."""
        layout_widget.set_sync_option("zoom", True)
        assert layout_widget._view_sync_manager.sync_x is True
        assert layout_widget._view_sync_manager.sync_y is True

    def test_get_sync_options(self, layout_widget):
        opts = layout_widget.get_sync_options()
        assert "x" in opts
        assert "y" in opts
        assert "zoom" in opts
        assert "selection" in opts
