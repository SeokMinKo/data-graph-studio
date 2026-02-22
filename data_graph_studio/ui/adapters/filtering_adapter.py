"""Qt signal adapter for FilteringManager.

Translates Observable events to PySide6 Signals so that UI components
that use Qt signal/slot connections continue to work unchanged.
"""

from PySide6.QtCore import QObject, Signal

from data_graph_studio.core.filtering import FilteringManager


class FilteringManagerAdapter(QObject):
    """
    Wraps FilteringManager and re-emits its Observable events as Qt Signals.
    Used by UI components that need Qt signal connections.

    Usage:
        manager = FilteringManager()
        adapter = FilteringManagerAdapter(manager, parent=self)
        adapter.filter_changed.connect(my_slot)
        # Use manager directly for API calls:
        manager.add_filter(...)
    """

    filter_changed = Signal(str)   # scheme_name
    scheme_created = Signal(str)   # scheme_name
    scheme_removed = Signal(str)   # scheme_name

    def __init__(self, manager: FilteringManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        manager.subscribe("filter_changed", self.filter_changed.emit)
        manager.subscribe("scheme_created", self.scheme_created.emit)
        manager.subscribe("scheme_removed", self.scheme_removed.emit)

    @property
    def manager(self) -> FilteringManager:
        return self._manager
