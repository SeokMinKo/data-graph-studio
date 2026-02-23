"""FilteringManager must be testable without a Qt application instance."""
import pytest


def test_filter_manager_no_qt_required():
    """FilteringManager can be instantiated without QApplication."""
    from data_graph_studio.core.filtering import FilteringManager
    fm = FilteringManager()
    assert fm is not None


def test_filter_scheme_created_event_fires():
    """scheme_created event fires when a new scheme is created."""
    from data_graph_studio.core.filtering import FilteringManager
    fm = FilteringManager()
    received = []
    fm.subscribe("scheme_created", lambda name: received.append(name))
    fm.create_scheme("MyScheme")
    assert received == ["MyScheme"]


def test_filter_scheme_removed_event_fires():
    """scheme_removed event fires when a scheme is removed."""
    from data_graph_studio.core.filtering import FilteringManager
    fm = FilteringManager()
    fm.create_scheme("TempScheme")
    received = []
    fm.subscribe("scheme_removed", lambda name: received.append(name))
    fm.remove_scheme("TempScheme")
    assert received == ["TempScheme"]


def test_filter_changed_event_fires_on_add():
    """filter_changed event fires when a filter is added."""
    from data_graph_studio.core.filtering import FilteringManager, FilterOperator
    fm = FilteringManager()
    received = []
    fm.subscribe("filter_changed", lambda scheme: received.append(scheme))
    fm.add_filter("Page", "col1", FilterOperator.EQUALS, 42)
    assert received == ["Page"]


def test_filter_changed_event_fires_on_clear():
    """filter_changed event fires when filters are cleared."""
    from data_graph_studio.core.filtering import FilteringManager, FilterOperator
    fm = FilteringManager()
    fm.add_filter("Page", "col1", FilterOperator.EQUALS, 1)
    received = []
    fm.subscribe("filter_changed", lambda scheme: received.append(scheme))
    fm.clear_filters("Page")
    assert received == ["Page"]


def test_cannot_remove_page_scheme():
    """Page scheme cannot be removed."""
    from data_graph_studio.core.filtering import FilteringManager
    from data_graph_studio.core.exceptions import ValidationError
    fm = FilteringManager()
    with pytest.raises(ValidationError):
        fm.remove_scheme("Page")


def test_create_duplicate_scheme_raises():
    """Creating a scheme that already exists raises ValidationError."""
    from data_graph_studio.core.filtering import FilteringManager
    from data_graph_studio.core.exceptions import ValidationError
    fm = FilteringManager()
    fm.create_scheme("Dup")
    with pytest.raises(ValidationError):
        fm.create_scheme("Dup")
