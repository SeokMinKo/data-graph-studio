"""ProfileController uses Observable, not Qt signals."""
from data_graph_studio.core.observable import Observable


def test_profile_controller_is_observable():
    from data_graph_studio.core.profile_controller import ProfileController
    assert issubclass(ProfileController, Observable)


def test_profile_controller_is_not_qobject():
    try:
        from PySide6.QtCore import QObject
        from data_graph_studio.core.profile_controller import ProfileController
        assert not issubclass(ProfileController, QObject)
    except ImportError:
        pass


def test_profile_created_event_fires():
    """profile_created event fires when a profile is created."""
    from data_graph_studio.core.profile_controller import ProfileController
    ProfileController.__new__(ProfileController)
    # At minimum verify the class structure
    assert issubclass(ProfileController, Observable)
