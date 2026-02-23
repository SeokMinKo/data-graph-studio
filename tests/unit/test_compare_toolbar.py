"""Tests for CompareToolbar signals, state, and defaults."""

from __future__ import annotations

import pytest



@pytest.fixture
def toolbar(qtbot):
    from data_graph_studio.ui.toolbars.compare_toolbar import CompareToolbar
    tb = CompareToolbar()
    qtbot.addWidget(tb)
    return tb


class TestCompareToolbarSignals:
    """Verify signal emissions on user interactions."""

    def test_grid_layout_changed_emits_on_column(self, toolbar, qtbot):
        """Clicking Column action emits grid_layout_changed('column')."""
        with qtbot.waitSignal(toolbar.grid_layout_changed, timeout=1000) as blocker:
            toolbar._grid_actions["column"].trigger()
        assert blocker.args == ["column"]

    def test_grid_layout_changed_emits_on_grid(self, toolbar, qtbot):
        """Clicking 2×2 action emits grid_layout_changed('grid')."""
        with qtbot.waitSignal(toolbar.grid_layout_changed, timeout=1000) as blocker:
            toolbar._grid_actions["grid"].trigger()
        assert blocker.args == ["grid"]

    def test_grid_layout_no_signal_when_same(self, toolbar, qtbot):
        """Clicking the already-active layout does NOT re-emit."""
        # Default is "row", clicking "row" again should not emit
        signals = []
        toolbar.grid_layout_changed.connect(lambda v: signals.append(v))
        toolbar._grid_actions["row"].trigger()
        assert signals == []

    def test_sync_changed_emits(self, toolbar, qtbot):
        """Toggling a sync button emits sync_changed(key, bool)."""
        # X is initially ON, toggle it OFF
        with qtbot.waitSignal(toolbar.sync_changed, timeout=1000) as blocker:
            toolbar._sync_buttons["x"].click()
        assert blocker.args == ["x", False]

    def test_sync_changed_all_keys(self, toolbar, qtbot):
        """All sync keys emit correctly."""
        for key in ["x", "y", "selection"]:
            signals = []
            toolbar.sync_changed.connect(lambda k, v: signals.append((k, v)))
            toolbar._sync_buttons[key].click()
            assert len(signals) > 0
            assert signals[-1][0] == key
            toolbar.sync_changed.disconnect()

    def test_exit_requested_emits(self, toolbar, qtbot):
        """Exit button emits exit_requested."""
        from PySide6.QtWidgets import QPushButton
        with qtbot.waitSignal(toolbar.exit_requested, timeout=1000):
            # The exit button is nested inside the two-row container
            for child in toolbar.findChildren(QPushButton):
                if 'Exit' in child.text():
                    child.click()
                    break


class TestCompareToolbarState:
    """Verify state read/write API."""

    def test_default_sync_state(self, toolbar):
        """Default sync state matches spec: X=ON, Y=OFF, Sel=ON."""
        state = toolbar.sync_state()
        assert state == {"x": True, "y": False, "selection": True}

    def test_default_grid_layout(self, toolbar):
        """Default grid layout is 'row'."""
        assert toolbar.grid_layout() == "row"

    def test_set_sync_state_round_trip(self, toolbar):
        """set_sync_state → sync_state round-trip."""
        toolbar.set_sync_state("y", True)
        toolbar.set_sync_state("x", False)
        state = toolbar.sync_state()
        assert state["y"] is True
        assert state["x"] is False

    def test_set_grid_layout_round_trip(self, toolbar):
        """set_grid_layout → grid_layout round-trip."""
        toolbar.set_grid_layout("grid")
        assert toolbar.grid_layout() == "grid"
        toolbar.set_grid_layout("column")
        assert toolbar.grid_layout() == "column"

    def test_reset_to_defaults(self, toolbar):
        """reset_to_defaults restores all states."""
        toolbar.set_sync_state("x", False)
        toolbar.set_sync_state("y", True)
        toolbar.set_grid_layout("grid")

        toolbar.reset_to_defaults()

        assert toolbar.grid_layout() == "row"
        assert toolbar.sync_state() == {"x": True, "y": False, "selection": True}

    def test_set_sync_state_invalid_key(self, toolbar):
        """set_sync_state with unknown key is a no-op."""
        toolbar.set_sync_state("nonexistent", True)  # should not raise

    def test_set_grid_layout_invalid(self, toolbar):
        """set_grid_layout with unknown key is a no-op."""
        toolbar.set_grid_layout("diagonal")  # should not raise
        # Grid stays at last valid value
        assert toolbar.grid_layout() == "row"
