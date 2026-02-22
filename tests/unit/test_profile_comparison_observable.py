"""ProfileComparisonController uses Observable, not Qt signals."""
from data_graph_studio.core.observable import Observable


def test_profile_comparison_controller_is_observable():
    from data_graph_studio.core.profile_comparison_controller import ProfileComparisonController
    assert issubclass(ProfileComparisonController, Observable)


def test_profile_comparison_controller_is_not_qobject():
    try:
        from PySide6.QtCore import QObject
        from data_graph_studio.core.profile_comparison_controller import ProfileComparisonController
        assert not issubclass(ProfileComparisonController, QObject)
    except ImportError:
        pass
