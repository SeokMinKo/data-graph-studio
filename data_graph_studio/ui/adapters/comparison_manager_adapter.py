"""Qt signal adapter for ComparisonManager."""
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.comparison_manager import ComparisonManager


class ComparisonManagerAdapter(QObject):
    """Wraps ComparisonManager and re-emits Observable events as Qt Signals."""
    dataset_added = Signal(str)
    dataset_removed = Signal(str)
    dataset_activated = Signal(str)
    dataset_updated = Signal(str)
    comparison_mode_changed = Signal(str)
    comparison_settings_changed = Signal()

    def __init__(self, manager: ComparisonManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        manager.subscribe("dataset_added", self.dataset_added.emit)
        manager.subscribe("dataset_removed", self.dataset_removed.emit)
        manager.subscribe("dataset_activated", self.dataset_activated.emit)
        manager.subscribe("dataset_updated", self.dataset_updated.emit)
        manager.subscribe("comparison_mode_changed", self.comparison_mode_changed.emit)
        manager.subscribe("comparison_settings_changed", self.comparison_settings_changed.emit)

    @property
    def manager(self) -> ComparisonManager:
        """Return the underlying ComparisonManager instance."""
        return self._manager
