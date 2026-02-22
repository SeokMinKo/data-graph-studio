"""Qt signal adapter for MarkingManager."""
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.marking import MarkingManager


class MarkingManagerAdapter(QObject):
    """Wraps MarkingManager and re-emits Observable events as Qt Signals."""
    marking_changed = Signal(str, object)   # name, indices (set)
    active_marking_changed = Signal(str)
    marking_created = Signal(str)
    marking_removed = Signal(str)

    def __init__(self, manager: MarkingManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        manager.subscribe("marking_changed", self.marking_changed.emit)
        manager.subscribe("active_marking_changed", self.active_marking_changed.emit)
        manager.subscribe("marking_created", self.marking_created.emit)
        manager.subscribe("marking_removed", self.marking_removed.emit)

    @property
    def manager(self) -> MarkingManager:
        return self._manager
