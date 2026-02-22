"""Qt signal adapter for ProfileComparisonController."""
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.profile_comparison_controller import ProfileComparisonController


class ProfileComparisonControllerAdapter(QObject):
    comparison_started = Signal(str, object)  # mode, profile_ids list
    comparison_ended = Signal()
    comparison_mode_changed = Signal(str)
    panel_removed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, controller: ProfileComparisonController, parent=None):
        super().__init__(parent)
        self._controller = controller
        controller.subscribe("comparison_started", self.comparison_started.emit)
        controller.subscribe("comparison_ended", self.comparison_ended.emit)
        controller.subscribe("comparison_mode_changed", self.comparison_mode_changed.emit)
        controller.subscribe("panel_removed", self.panel_removed.emit)
        controller.subscribe("error_occurred", self.error_occurred.emit)

    @property
    def controller(self) -> ProfileComparisonController:
        return self._controller
