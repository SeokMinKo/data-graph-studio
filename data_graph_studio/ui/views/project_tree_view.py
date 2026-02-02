from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QTreeView, QMenu, QStyledItemDelegate, QStyleOptionViewItem

from ..models.profile_model import ProfileModel


class _ChartIconDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        decoration = index.data(Qt.DecorationRole)
        if isinstance(decoration, str) and decoration:
            icon_rect = option.rect
            icon_rect.setWidth(min(option.rect.width(), 20))
            painter.save()
            painter.setFont(option.font)
            painter.drawText(icon_rect, Qt.AlignVCenter | Qt.AlignHCenter, decoration)
            painter.restore()

            text_option = QStyleOptionViewItem(option)
            text_option.rect = option.rect.adjusted(icon_rect.width() + 4, 0, 0, 0)
            text_option.icon = None
            text_option.decorationSize = QSize(0, 0)
            super().paint(painter, text_option, index)
            return

        super().paint(painter, option, index)


class ProjectTreeView(QTreeView):
    # Signals
    profile_activated = Signal(str)  # profile_id
    profile_selected = Signal(str)  # profile_id
    project_activated = Signal(str)  # dataset_id
    new_profile_requested = Signal(str)  # dataset_id
    rename_requested = Signal(str)  # profile_id
    delete_requested = Signal(str)  # profile_id or dataset_id
    duplicate_requested = Signal(str)  # profile_id
    export_requested = Signal(str)  # profile_id
    import_requested = Signal(str)  # dataset_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model: Optional[ProfileModel] = None

        self.setHeaderHidden(True)
        self.setIndentation(18)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setItemDelegate(_ChartIconDelegate(self))

    def set_model(self, model: ProfileModel):
        self._model = model
        self.setModel(model)
        if self.selectionModel():
            self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def keyPressEvent(self, event):
        index = self.currentIndex()
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            setting = self._get_setting(index)
            if setting is not None:
                self.profile_activated.emit(setting.id)
                return
            dataset_id = self._get_dataset_id(index)
            if dataset_id:
                self.project_activated.emit(dataset_id)
                return

        if event.key() == Qt.Key_F2:
            setting = self._get_setting(index)
            if setting is not None:
                self.rename_requested.emit(setting.id)
                return

        if event.key() == Qt.Key_Delete:
            # Delete profile if selected, not the dataset
            setting = self._get_setting(index)
            if setting is not None:
                self.delete_requested.emit(setting.id)
                return
            # Only delete dataset if it's a dataset node (not profile)
            # This case is handled via context menu, not Delete key
            return

        if event.key() == Qt.Key_N and event.modifiers() & Qt.ControlModifier:
            dataset_id = self._get_dataset_id(index)
            if dataset_id:
                self.new_profile_requested.emit(dataset_id)
                return

        if event.key() == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            setting = self._get_setting(index)
            if setting is not None:
                self.duplicate_requested.emit(setting.id)
                return

        super().keyPressEvent(event)

    def _on_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return

        setting = self._get_setting(index)
        if setting is not None:
            self._show_profile_menu(pos, setting.id)
            return

        dataset_id = self._get_dataset_id(index)
        if dataset_id:
            self._show_project_menu(pos, dataset_id)

    def _show_project_menu(self, pos, dataset_id):
        menu = QMenu(self)

        new_profile_action = menu.addAction("New Profile")
        new_profile_action.triggered.connect(lambda: self.new_profile_requested.emit(dataset_id))

        import_action = menu.addAction("Import")
        import_action.triggered.connect(lambda: self.import_requested.emit(dataset_id))

        remove_action = menu.addAction("Remove Project")
        remove_action.triggered.connect(lambda: self.delete_requested.emit(dataset_id))

        menu.exec(self.viewport().mapToGlobal(pos))

    def _show_profile_menu(self, pos, profile_id):
        menu = QMenu(self)

        apply_action = menu.addAction("Apply")
        apply_action.triggered.connect(lambda: self.profile_activated.emit(profile_id))

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self.rename_requested.emit(profile_id))

        duplicate_action = menu.addAction("Duplicate")
        duplicate_action.triggered.connect(lambda: self.duplicate_requested.emit(profile_id))

        export_action = menu.addAction("Export")
        export_action.triggered.connect(lambda: self.export_requested.emit(profile_id))

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(profile_id))

        menu.exec(self.viewport().mapToGlobal(pos))

    def _on_selection_changed(self, selected, deselected):
        index = self.currentIndex()
        setting = self._get_setting(index)
        if setting is not None:
            self.profile_selected.emit(setting.id)

    def _get_setting(self, index):
        if not self._model or not index.isValid():
            return None
        return self._model.get_setting(index)

    def _get_dataset_id(self, index) -> Optional[str]:
        if not self._model or not index.isValid():
            return None
        return self._model.get_dataset_id(index)
