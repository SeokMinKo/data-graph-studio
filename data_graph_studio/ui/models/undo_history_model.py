from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from ...core.undo_manager import UndoStack


class UndoHistoryModel(QAbstractListModel):
    """ListModel for displaying undo history.

    Row 0 is the oldest entry.
    The stack cursor (index) indicates that commands < index are applied.
    """

    RoleDescription = Qt.ItemDataRole.UserRole + 1
    RoleApplied = Qt.ItemDataRole.UserRole + 2

    def __init__(self, undo_stack: UndoStack, parent=None):
        super().__init__(parent)
        self._stack = undo_stack

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._stack.commands)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        commands = self._stack.commands
        if row < 0 or row >= len(commands):
            return None

        cmd = commands[row]
        applied = row < self._stack.index

        if role == Qt.ItemDataRole.DisplayRole:
            prefix = "✓ " if applied else "  "
            return f"{prefix}{cmd.description}"
        if role == self.RoleDescription:
            return cmd.description
        if role == self.RoleApplied:
            return applied
        if role == Qt.ItemDataRole.ToolTipRole:
            ts = getattr(cmd, "timestamp", None)
            if ts:
                return f"{cmd.description}\n{ts:.0f}"
            return cmd.description

        return None

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()
