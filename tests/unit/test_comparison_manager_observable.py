"""ComparisonManager uses Observable, not Qt signals."""
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


def test_set_comparison_datasets_filters_invalid_ids_contract():
    """Contract: only loaded dataset IDs remain in comparison_datasets."""
    mgr = ComparisonManager()
    mgr.add_dataset("ds1", name="Dataset 1")
    mgr.add_dataset("ds2", name="Dataset 2")

    mgr.set_comparison_datasets(["ds1", "ghost", "ds2", "missing"])

    assert mgr.comparison_settings.comparison_datasets == ["ds1", "ds2"]


def test_clear_profile_comparison_resets_target_and_mode():
    """Failure/rollback path: clear_profile_comparison returns to dataset+SINGLE mode."""
    mgr = ComparisonManager()
    mgr.add_dataset("ds1", name="Dataset 1")

    mgr.set_profile_comparison("ds1", ["p1", "p2"])
    mgr.clear_profile_comparison()

    assert mgr.comparison_settings.comparison_target == "dataset"
    assert mgr.comparison_settings.mode.value == "single"
    assert mgr.comparison_settings.comparison_profile_ids == []
