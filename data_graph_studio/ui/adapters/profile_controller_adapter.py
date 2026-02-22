"""Qt signal adapter for ProfileController."""
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.profile_controller import ProfileController


class ProfileControllerAdapter(QObject):
    profile_applied = Signal(str)
    profile_created = Signal(str)
    profile_deleted = Signal(str)
    profile_renamed = Signal(str, str)
    error_occurred = Signal(str)

    def __init__(self, controller: ProfileController, parent=None):
        super().__init__(parent)
        self._controller = controller
        controller.subscribe("profile_applied", self.profile_applied.emit)
        controller.subscribe("profile_created", self.profile_created.emit)
        controller.subscribe("profile_deleted", self.profile_deleted.emit)
        controller.subscribe("profile_renamed", self.profile_renamed.emit)
        controller.subscribe("error_occurred", self.error_occurred.emit)

    @property
    def controller(self) -> ProfileController:
        """Return the underlying ProfileController instance."""
        return self._controller
