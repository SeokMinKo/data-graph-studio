"""ComparisonManager uses Observable, not Qt signals."""
import polars as pl
from data_graph_studio.core.comparison_manager import ComparisonManager
from data_graph_studio.core.observable import Observable


def test_comparison_manager_is_observable():
    mgr = ComparisonManager()
    assert isinstance(mgr, Observable)


def test_comparison_manager_is_not_qobject():
    try:
        from PySide6.QtCore import QObject
        mgr = ComparisonManager()
        assert not isinstance(mgr, QObject)
    except ImportError:
        pass


def test_dataset_added_event_fires():
    mgr = ComparisonManager()
    received = []
    mgr.subscribe("dataset_added", received.append)
    mgr.add_dataset("ds1", name="Test Dataset")
    assert "ds1" in received


def test_dataset_removed_event_fires():
    mgr = ComparisonManager()
    mgr.add_dataset("ds1", name="Test Dataset")
    received = []
    mgr.subscribe("dataset_removed", received.append)
    mgr.remove_dataset("ds1")
    assert "ds1" in received


def test_dataset_activated_event_fires():
    mgr = ComparisonManager()
    mgr.add_dataset("ds1", name="Dataset 1")
    mgr.add_dataset("ds2", name="Dataset 2")
    received = []
    mgr.subscribe("dataset_activated", received.append)
    mgr.activate_dataset("ds2")
    assert "ds2" in received
