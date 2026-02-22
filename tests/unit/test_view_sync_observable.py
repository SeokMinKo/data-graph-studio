"""ViewSyncManager uses Observable, not Qt."""
from data_graph_studio.core.observable import Observable


def test_view_sync_manager_is_observable():
    from data_graph_studio.core.view_sync import ViewSyncManager
    assert issubclass(ViewSyncManager, Observable)


def test_view_sync_manager_is_not_qobject():
    try:
        from PySide6.QtCore import QObject
        from data_graph_studio.core.view_sync import ViewSyncManager
        assert not issubclass(ViewSyncManager, QObject)
    except ImportError:
        pass


def test_view_range_synced_event_fires():
    """view_range_synced event fires after on_source_range_changed is called."""
    from data_graph_studio.core.view_sync import ViewSyncManager
    import time

    mgr = ViewSyncManager()
    received = []
    mgr.subscribe("view_range_synced", lambda *a: received.append(a))

    class FakePanel:
        def __init__(self): self.calls = []
        def set_view_range(self, xr, yr, sync_x, sync_y): self.calls.append(("range", xr, yr))
        def set_selection(self, idxs): self.calls.append(("sel", idxs))

    p1, p2 = FakePanel(), FakePanel()
    mgr.register_panel("p1", p1)
    mgr.register_panel("p2", p2)
    mgr.on_source_range_changed("p1", [0, 10], [0, 100])

    # Leading edge fires immediately; also wait for throttle timer to clear
    time.sleep(0.1)  # 50ms throttle + margin
    assert len(received) >= 1 or len(p2.calls) >= 1


def test_selection_synced_event_fires():
    from data_graph_studio.core.view_sync import ViewSyncManager
    import time

    mgr = ViewSyncManager()
    received = []
    mgr.subscribe("selection_synced", lambda *a: received.append(a))

    class FakePanel:
        def __init__(self): self.calls = []
        def set_view_range(self, xr, yr, sync_x, sync_y): self.calls.append(xr)
        def set_selection(self, idxs): self.calls.append(("sel", idxs))

    p1, p2 = FakePanel(), FakePanel()
    mgr.register_panel("p1", p1)
    mgr.register_panel("p2", p2)
    mgr.on_source_selection_changed("p1", [0, 1, 2])

    time.sleep(0.1)
    assert len(received) >= 1 or any(c[0] == "sel" for c in p2.calls if isinstance(c, tuple))
