"""MarkingManager uses Observable, not Qt signals."""
import pytest
from data_graph_studio.core.marking import MarkingManager, MarkMode


def test_marking_manager_is_not_qobject():
    """MarkingManager must not inherit from QObject."""
    try:
        from PySide6.QtCore import QObject
        mgr = MarkingManager()
        assert not isinstance(mgr, QObject), "Should not be QObject"
    except ImportError:
        pass


def test_marking_changed_event_fires():
    mgr = MarkingManager()
    received = []
    mgr.subscribe("marking_changed", lambda name, indices: received.append((name, indices)))
    mgr.create_marking("test", "#ff0000")
    mgr.set_active_marking("test")
    mgr.update_marking("test", {0, 1, 2}, MarkMode.REPLACE)
    assert len(received) == 1
    assert received[0][0] == "test"
    assert received[0][1] == {0, 1, 2}


def test_marking_created_event_fires():
    mgr = MarkingManager()
    received = []
    mgr.subscribe("marking_created", received.append)
    mgr.create_marking("new_marking", "#0000ff")
    assert received == ["new_marking"]


def test_marking_removed_event_fires():
    mgr = MarkingManager()
    mgr.create_marking("m1", "#ff0000")
    received = []
    mgr.subscribe("marking_removed", received.append)
    mgr.remove_marking("m1")
    assert received == ["m1"]
