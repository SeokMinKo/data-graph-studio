"""Qt signal adapter for ViewSyncManager."""
from PySide6.QtCore import QObject, Signal

from data_graph_studio.core.view_sync import ViewSyncManager


class ViewSyncManagerAdapter(QObject):
    view_range_synced = Signal(str, object, object)  # source_id, x_range, y_range
    selection_synced = Signal(str, object)            # source_id, indices

    def __init__(self, manager: ViewSyncManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        manager.subscribe("view_range_synced", self.view_range_synced.emit)
        manager.subscribe("selection_synced", self.selection_synced.emit)

    @property
    def manager(self) -> ViewSyncManager:
        return self._manager
