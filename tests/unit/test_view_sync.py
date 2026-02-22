"""
Tests for ViewSyncManager (UT-2 through UT-5 + throttle).

TDD: tests written before implementation.
"""

import gc
import time

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget


# ---------------------------------------------------------------------------
# Ensure a QApplication exists for the entire test module
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _ensure_qapp():
    """Guarantee a QApplication exists (needed for QWidget)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakePanel(QWidget):
    """
    Duck-typed panel that records calls to set_view_range / set_selection.
    Must stay alive as a QWidget so WeakValueDictionary can reference it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view_range_calls: list[tuple] = []
        self.selection_calls: list[list] = []

    def set_view_range(self, x_range, y_range, sync_x, sync_y):
        self.view_range_calls.append((x_range, y_range, sync_x, sync_y))

    def set_selection(self, indices):
        self.selection_calls.append(list(indices))


@pytest.fixture()
def manager(qtbot):
    """Create a fresh ViewSyncManager for each test."""
    from data_graph_studio.core.view_sync import ViewSyncManager

    mgr = ViewSyncManager()
    yield mgr
    mgr.clear()


@pytest.fixture()
def two_panels(manager, qtbot):
    """Register two fake panels and return them along with the manager."""
    p1 = FakePanel()
    p2 = FakePanel()
    qtbot.addWidget(p1)
    qtbot.addWidget(p2)
    manager.register_panel("A", p1)
    manager.register_panel("B", p2)
    return manager, p1, p2


# ---------------------------------------------------------------------------
# UT-2: X sync on/off
# ---------------------------------------------------------------------------


class TestXSync:
    def test_x_sync_on_propagates_x_range(self, two_panels):
        mgr, p1, p2 = two_panels
        mgr.sync_x = True

        mgr.on_source_range_changed("A", [0.0, 10.0], [0.0, 5.0])

        # Panel B should have received the call with sync_x=True
        assert len(p2.view_range_calls) == 1
        call = p2.view_range_calls[0]
        assert call[0] == [0.0, 10.0]  # x_range
        assert call[2] is True  # sync_x

    def test_x_sync_off_does_not_propagate_x(self, two_panels):
        mgr, p1, p2 = two_panels
        mgr.sync_x = False
        mgr.sync_y = False  # both off → no view_range call at all

        mgr.on_source_range_changed("A", [0.0, 10.0], [0.0, 5.0])

        # When both sync_x and sync_y are False, no range sync should fire
        assert len(p2.view_range_calls) == 0

    def test_x_sync_off_y_sync_on_propagates_only_y(self, two_panels):
        mgr, p1, p2 = two_panels
        mgr.sync_x = False
        mgr.sync_y = True

        mgr.on_source_range_changed("A", [0.0, 10.0], [0.0, 5.0])

        assert len(p2.view_range_calls) == 1
        call = p2.view_range_calls[0]
        assert call[2] is False  # sync_x
        assert call[3] is True  # sync_y

    def test_source_panel_excluded(self, two_panels):
        """Source panel should never receive its own sync event."""
        mgr, p1, p2 = two_panels
        mgr.sync_x = True

        mgr.on_source_range_changed("A", [0.0, 10.0], [0.0, 5.0])

        assert len(p1.view_range_calls) == 0


# ---------------------------------------------------------------------------
# UT-3: Y sync on/off
# ---------------------------------------------------------------------------


class TestYSync:
    def test_y_sync_on_propagates_y_range(self, two_panels):
        mgr, p1, p2 = two_panels
        mgr.sync_y = True

        mgr.on_source_range_changed("A", [0.0, 10.0], [0.0, 5.0])

        assert len(p2.view_range_calls) == 1
        call = p2.view_range_calls[0]
        assert call[1] == [0.0, 5.0]  # y_range
        assert call[3] is True  # sync_y

    def test_y_sync_off_default(self, manager):
        """Default sync_y should be False."""
        assert manager.sync_y is False

    def test_y_sync_off_does_not_propagate_y(self, two_panels):
        mgr, p1, p2 = two_panels
        mgr.sync_x = True
        mgr.sync_y = False

        mgr.on_source_range_changed("A", [0.0, 10.0], [0.0, 5.0])

        assert len(p2.view_range_calls) == 1
        call = p2.view_range_calls[0]
        assert call[3] is False  # sync_y


# ---------------------------------------------------------------------------
# UT-4: Selection sync
# ---------------------------------------------------------------------------


class TestSelectionSync:
    def test_selection_propagates_to_other_panels(self, two_panels):
        mgr, p1, p2 = two_panels
        mgr.sync_selection = True

        mgr.on_source_selection_changed("A", [1, 5, 10])

        assert len(p2.selection_calls) == 1
        assert p2.selection_calls[0] == [1, 5, 10]

    def test_selection_excludes_source(self, two_panels):
        mgr, p1, p2 = two_panels
        mgr.sync_selection = True

        mgr.on_source_selection_changed("A", [1, 5, 10])

        assert len(p1.selection_calls) == 0

    def test_selection_off_does_not_propagate(self, two_panels):
        mgr, p1, p2 = two_panels
        mgr.sync_selection = False

        mgr.on_source_selection_changed("A", [1, 5, 10])

        assert len(p2.selection_calls) == 0

    def test_selection_with_three_panels(self, manager, qtbot):
        p1 = FakePanel()
        p2 = FakePanel()
        p3 = FakePanel()
        qtbot.addWidget(p1)
        qtbot.addWidget(p2)
        qtbot.addWidget(p3)
        manager.register_panel("A", p1)
        manager.register_panel("B", p2)
        manager.register_panel("C", p3)

        manager.on_source_selection_changed("B", [42])

        assert len(p1.selection_calls) == 1
        assert p1.selection_calls[0] == [42]
        assert len(p3.selection_calls) == 1
        assert p3.selection_calls[0] == [42]
        assert len(p2.selection_calls) == 0  # source excluded


# ---------------------------------------------------------------------------
# UT-5: WeakRef cleanup
# ---------------------------------------------------------------------------


class TestWeakRefCleanup:
    def test_panel_removed_after_deletion(self, manager):
        """
        UT-5: WeakValueDictionary should auto-remove panel when it's GC'd.

        PySide6/shiboken may prevent Python GC from collecting QWidgets
        immediately, so we also test that the underlying WeakValueDictionary
        works correctly with a plain QObject wrapper approach. The key
        invariant: once Python has no strong reference and GC runs, the
        panel entry vanishes.
        """
        import weakref as _weakref

        # Use a plain Python wrapper that QWidget weak-refs can track
        p1 = FakePanel()
        wr = _weakref.ref(p1)
        manager.register_panel("A", p1)
        assert manager.panel_count == 1

        # Explicitly invalidate the C++ object to ensure shiboken releases
        import shiboken6
        shiboken6.delete(p1)
        del p1
        gc.collect()

        # After C++ deletion + GC, the weak reference should be dead
        assert wr() is None
        # WeakValueDictionary should auto-remove it
        assert manager.panel_count == 0

    def test_deleted_panel_not_synced(self, manager, qtbot):
        """After panel is deleted, sync should skip it without crashing."""
        p1 = FakePanel()
        p2 = FakePanel()
        qtbot.addWidget(p1)
        manager.register_panel("A", p1)
        manager.register_panel("B", p2)

        # Explicitly delete p2 via shiboken to ensure cleanup
        import shiboken6
        shiboken6.delete(p2)
        del p2
        gc.collect()

        # Syncing from A should not crash even though B is gone
        manager.sync_x = True
        manager.on_source_range_changed("A", [0, 10], [0, 5])
        # No exception → pass


# ---------------------------------------------------------------------------
# Throttle tests
# ---------------------------------------------------------------------------


class TestThrottle:
    def test_first_event_fires_immediately(self, two_panels):
        """Leading edge: first event in a window should fire immediately."""
        mgr, p1, p2 = two_panels
        mgr.sync_x = True

        mgr.on_source_range_changed("A", [0, 10], [0, 5])

        # Should fire immediately (leading edge)
        assert len(p2.view_range_calls) == 1

    def test_rapid_events_suppressed_within_window(self, two_panels, qtbot):
        """Events within 50ms throttle window should be suppressed."""
        mgr, p1, p2 = two_panels
        mgr.sync_x = True

        # First fires immediately
        mgr.on_source_range_changed("A", [0, 10], [0, 5])
        assert len(p2.view_range_calls) == 1

        # Rapid subsequent events — should be suppressed
        mgr.on_source_range_changed("A", [1, 11], [0, 5])
        mgr.on_source_range_changed("A", [2, 12], [0, 5])
        mgr.on_source_range_changed("A", [3, 13], [0, 5])

        # Still only 1 call (suppressed within throttle window)
        assert len(p2.view_range_calls) == 1

    def test_event_fires_after_throttle_window(self, two_panels, qtbot):
        """After throttle window elapses, pending event should fire."""
        mgr, p1, p2 = two_panels
        mgr.sync_x = True

        # First fires immediately
        mgr.on_source_range_changed("A", [0, 10], [0, 5])
        assert len(p2.view_range_calls) == 1

        # Queue a pending event
        mgr.on_source_range_changed("A", [5, 15], [0, 5])
        assert len(p2.view_range_calls) == 1  # still suppressed

        # Wait for throttle timer to expire and fire the pending event
        qtbot.waitUntil(lambda: len(p2.view_range_calls) >= 2, timeout=200)
        assert len(p2.view_range_calls) == 2
        # The pending event should contain the LAST queued values
        assert p2.view_range_calls[1][0] == [5, 15]

    def test_selection_throttle_first_fires_immediately(self, two_panels):
        """Selection events should also throttle — leading edge fires."""
        mgr, p1, p2 = two_panels
        mgr.sync_selection = True

        mgr.on_source_selection_changed("A", [1, 2])
        assert len(p2.selection_calls) == 1

    def test_selection_throttle_suppresses_rapid(self, two_panels, qtbot):
        """Rapid selection events suppressed within window."""
        mgr, p1, p2 = two_panels
        mgr.sync_selection = True

        mgr.on_source_selection_changed("A", [1])
        mgr.on_source_selection_changed("A", [2])
        mgr.on_source_selection_changed("A", [3])

        # Only first fires immediately
        assert len(p2.selection_calls) == 1
        assert p2.selection_calls[0] == [1]

        # After throttle window, last pending fires
        qtbot.waitUntil(lambda: len(p2.selection_calls) >= 2, timeout=200)
        assert p2.selection_calls[1] == [3]


# ---------------------------------------------------------------------------
# Register / unregister / clear
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_unregister(self, manager, qtbot):
        p = FakePanel()
        qtbot.addWidget(p)
        manager.register_panel("X", p)
        assert manager.panel_count == 1

        manager.unregister_panel("X")
        assert manager.panel_count == 0

    def test_unregister_unknown_is_noop(self, manager):
        manager.unregister_panel("nonexistent")  # should not raise

    def test_clear_removes_all(self, manager, qtbot):
        p1 = FakePanel()
        p2 = FakePanel()
        qtbot.addWidget(p1)
        qtbot.addWidget(p2)
        manager.register_panel("A", p1)
        manager.register_panel("B", p2)

        manager.clear()
        assert manager.panel_count == 0

    def test_re_register_replaces(self, manager, qtbot):
        p1 = FakePanel()
        p2 = FakePanel()
        p3 = FakePanel()
        qtbot.addWidget(p1)
        qtbot.addWidget(p2)
        qtbot.addWidget(p3)
        manager.register_panel("A", p1)
        manager.register_panel("A", p2)  # same id, new panel

        assert manager.panel_count == 1

        manager.sync_x = True
        # Register B so we can fire from it
        manager.register_panel("B", p3)
        manager.on_source_range_changed("B", [0, 10], [0, 5])

        # p2 (registered as "A") should receive the sync, not p1
        assert len(p2.view_range_calls) == 1
        assert len(p1.view_range_calls) == 0


# ---------------------------------------------------------------------------
# reset_all_views
# ---------------------------------------------------------------------------


class TestResetAllViews:
    def test_reset_emits_to_all_panels(self, two_panels):
        mgr, p1, p2 = two_panels

        mgr.reset_all_views()

        # Both panels should receive a reset (set_view_range with None ranges)
        # The reset uses set_view_range(None, None, ...) to indicate auto-range
        assert len(p1.view_range_calls) == 1
        assert p1.view_range_calls[0][0] is None  # x_range = None → auto
        assert len(p2.view_range_calls) == 1
        assert p2.view_range_calls[0][0] is None


# ---------------------------------------------------------------------------
# Signal emission
# ---------------------------------------------------------------------------


class TestSignals:
    def test_view_range_synced_signal_emitted(self, two_panels, qtbot):
        mgr, p1, p2 = two_panels
        mgr.sync_x = True

        received = []
        mgr.subscribe("view_range_synced", lambda *a: received.append(a))
        mgr.on_source_range_changed("A", [0, 10], [0, 5])
        assert len(received) == 1
        assert received[0][0] == "A"

    def test_selection_synced_signal_emitted(self, two_panels, qtbot):
        mgr, p1, p2 = two_panels
        mgr.sync_selection = True

        received = []
        mgr.subscribe("selection_synced", lambda *a: received.append(a))
        mgr.on_source_selection_changed("A", [1, 2, 3])
        assert len(received) == 1
        assert received[0][0] == "A"


# ---------------------------------------------------------------------------
# Infinite-loop prevention
# ---------------------------------------------------------------------------


class TestInfiniteLoopPrevention:
    def test_nested_sync_blocked(self, manager, qtbot):
        """
        If a panel's set_view_range triggers on_source_range_changed back,
        the _is_syncing flag should prevent infinite recursion.
        """

        class ReentrantPanel(QWidget):
            def __init__(self, mgr):
                super().__init__()
                self.mgr = mgr
                self.call_count = 0

            def set_view_range(self, x_range, y_range, sync_x, sync_y):
                self.call_count += 1
                # Simulate reentrant call (panel fires event back)
                self.mgr.on_source_range_changed("reentrant", x_range, y_range)

            def set_selection(self, indices):
                pass

        rp = ReentrantPanel(manager)
        other = FakePanel()
        qtbot.addWidget(rp)
        qtbot.addWidget(other)
        manager.register_panel("reentrant", rp)
        manager.register_panel("other", other)
        manager.sync_x = True

        manager.on_source_range_changed("other", [0, 10], [0, 5])

        # reentrant panel got called once, its re-fire was blocked
        assert rp.call_count == 1
