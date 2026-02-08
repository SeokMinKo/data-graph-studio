from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListView,
    QLabel,
)

from ..models.undo_history_model import UndoHistoryModel
from ...core.undo_manager import UndoStack


class HistoryPanel(QWidget):
    """Undo/Redo history panel (session-only)."""

    request_undo = Signal()
    request_redo = Signal()

    def __init__(self, undo_stack: UndoStack, parent=None):
        super().__init__(parent)
        self._stack = undo_stack
        self._model = UndoHistoryModel(undo_stack)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("History")
        title.setStyleSheet("font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        self.undo_btn = QPushButton("Undo")
        self.redo_btn = QPushButton("Redo")
        self.undo_btn.clicked.connect(self.request_undo.emit)
        self.redo_btn.clicked.connect(self.request_redo.emit)
        header.addWidget(self.undo_btn)
        header.addWidget(self.redo_btn)

        layout.addLayout(header)

        self.list = QListView()
        self.list.setModel(self._model)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.list.setAlternatingRowColors(True)
        self.list.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.list, 1)

        self.refresh()

    def refresh(self):
        self._model.refresh()
        self.undo_btn.setEnabled(self._stack.can_undo())
        self.redo_btn.setEnabled(self._stack.can_redo())
        # Auto-scroll to current cursor
        row = max(0, min(self._stack.index - 1, self._model.rowCount() - 1))
        if self._model.rowCount() > 0:
            self.list.scrollTo(self._model.index(row, 0))
