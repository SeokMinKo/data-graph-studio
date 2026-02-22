"""Qt signal adapter for StreamingController.

Translates Observable events to PySide6 Signals so that UI components
that use Qt signal/slot connections continue to work unchanged.
"""

from PySide6.QtCore import QObject, Signal

from data_graph_studio.core.streaming_controller import StreamingController


class StreamingControllerAdapter(QObject):
    """
    Wraps StreamingController and re-emits its Observable events as Qt Signals.
    Used by MainWindow and other UI components that need Qt signal connections.

    Usage:
        ctrl = StreamingController(fs=..., timer_factory=...)
        adapter = StreamingControllerAdapter(ctrl, parent=self)
        adapter.streaming_state_changed.connect(my_slot)
        # Use ctrl directly for control calls:
        ctrl.start("/path/to/file.csv")
    """

    streaming_state_changed = Signal(str)   # "off" | "live" | "paused"
    data_updated = Signal(str, int)         # file_path, new_row_count
    file_deleted = Signal(str)              # file_path

    def __init__(self, controller: StreamingController, parent=None):
        super().__init__(parent)
        self._controller = controller
        controller.subscribe("streaming_state_changed", self.streaming_state_changed.emit)
        controller.subscribe("data_updated", self._on_data_updated)
        controller.subscribe("file_deleted", self.file_deleted.emit)

    def _on_data_updated(self, file_path: str, new_row_count: int) -> None:
        self.data_updated.emit(file_path, new_row_count)

    @property
    def controller(self) -> StreamingController:
        """Return the underlying StreamingController instance."""
        return self._controller
