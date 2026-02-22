"""Qt bridge for ExportController Observable events."""
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.export_controller import ExportController


class ExportControllerAdapter(QObject):
    """Bridges ExportController Observable events to Qt Signals for UI consumption."""

    progress_changed = Signal(int)
    export_completed = Signal(str)
    export_failed = Signal(str)

    def __init__(self, controller: ExportController, parent=None):
        super().__init__(parent)
        self._controller = controller
        controller.subscribe("progress_changed", self.progress_changed.emit)
        controller.subscribe("export_completed", self.export_completed.emit)
        controller.subscribe("export_failed", self.export_failed.emit)
