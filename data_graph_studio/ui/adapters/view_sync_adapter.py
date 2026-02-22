"""Qt signal adapter for ViewSyncManager."""
from PySide6.QtCore import QObject, Signal

from data_graph_studio.core.view_sync import ViewSyncManager


class ViewSyncManagerAdapter(QObject):
    view_range_synced = Signal(str, object, object)  # source_id, x_range, y_range
    selection_synced = Signal(str, object)            # source_id, indices

    def __init__(self, manager: ViewSyncManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._range_handler = self.view_range_synced.emit
        self._sel_handler = self.selection_synced.emit
        manager.subscribe("view_range_synced", self._range_handler)
        manager.subscribe("selection_synced", self._sel_handler)
        self.destroyed.connect(self._cleanup)

    def _cleanup(self):
        self._manager.unsubscribe("view_range_synced", self._range_handler)
        self._manager.unsubscribe("selection_synced", self._sel_handler)

    @property
    def manager(self) -> ViewSyncManager:
        """Return the underlying ViewSyncManager instance."""
        return self._manager
