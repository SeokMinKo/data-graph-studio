from __future__ import annotations

import warnings
from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize, QSortFilterProxyModel
from PySide6.QtGui import QPainter, QPalette, QAccessible
from PySide6.QtWidgets import QTreeView, QMenu, QStyledItemDelegate, QStyleOptionViewItem, QStyle

from ..models.profile_model import ProfileModel


class _SafeAccessibleTreeView(QTreeView):
    """QTreeView subclass that suppresses accessibility crashes.

    macOS accessibility (QAccessibleTree::indexFromLogical) can segfault when
    the model is empty or being reset.  Workaround: install a null model so
    the accessibility subsystem sees rowCount()==0 from the start.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Install an empty model immediately so Qt accessibility never queries
        # an uninitialized tree.  The real model replaces it via set_model().
        from PySide6.QtGui import QStandardItemModel
        self._placeholder_model = QStandardItemModel(0, 1, self)
        self.setModel(self._placeholder_model)


class _ChartIconDelegate(QStyledItemDelegate):
    """Profile 항목에 차트 아이콘 + 이름을 렌더링하는 delegate"""
    ICON_ROLE = Qt.UserRole + 1

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # 기본 배경/선택 렌더링
        self.initStyleOption(option, index)

        icon_text = index.data(self.ICON_ROLE)
        if isinstance(icon_text, str) and icon_text:
            # 선택/호버 배경 먼저 그리기
            style = option.widget.style() if option.widget else None
            if style:
                style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, option.widget)

            painter.save()

            # 텍스트 색상 설정 (선택 상태에 따라)
            if option.state & QStyle.State_Selected:
                painter.setPen(option.palette.color(QPalette.ColorRole.HighlightedText))
            else:
                painter.setPen(option.palette.color(QPalette.ColorRole.Text))

            # 아이콘 영역
            icon_rect = option.rect.adjusted(2, 0, 0, 0)
            icon_rect.setWidth(20)
            painter.setFont(option.font)
            painter.drawText(icon_rect, Qt.AlignVCenter | Qt.AlignHCenter, icon_text)

            # 텍스트 영역
            display_text = index.data(Qt.DisplayRole) or ""
            text_rect = option.rect.adjusted(24, 0, -2, 0)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, display_text)

            painter.restore()
            return

        super().paint(painter, option, index)


class ProfileFilterProxy(QSortFilterProxyModel):
    """프로파일/데이터셋 이름 필터링용 프록시 모델"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def filterAcceptsRow(self, row, parent):
        if not self.filterRegularExpression().pattern():
            return True
        return super().filterAcceptsRow(row, parent)


class ProjectTreeView(_SafeAccessibleTreeView):
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
    compare_requested = Signal(list, dict)  # profile_ids, options
    copy_to_dataset_requested = Signal(str)  # profile_id
    favorite_toggled = Signal(str)  # profile_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model: Optional[ProfileModel] = None

        self.setHeaderHidden(True)
        self.setIndentation(18)
        self.setSelectionMode(QTreeView.ExtendedSelection)  # Ctrl/Shift 멀티 선택
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setItemDelegate(_ChartIconDelegate(self))

    def set_model(self, model: ProfileModel):
        # Disconnect old signals to prevent duplicate connections
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self.doubleClicked.disconnect(self._on_double_clicked)
            except (RuntimeError, TypeError):
                pass
        old_sel = self.selectionModel()
        if old_sel:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    old_sel.selectionChanged.disconnect(self._on_selection_changed)
                except (RuntimeError, TypeError):
                    pass

        self._model = model
        self._proxy = ProfileFilterProxy(self)
        self._proxy.setSourceModel(model)
        self._proxy.setFilterRole(Qt.DisplayRole)
        self.setModel(self._proxy)
        # Discard placeholder now that real model is installed
        if hasattr(self, '_placeholder_model'):
            self._placeholder_model = None
        if self.selectionModel():
            self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.doubleClicked.connect(self._on_double_clicked)

    def set_filter_text(self, text: str):
        """검색 필터 적용"""
        self._proxy.setFilterFixedString(text)
        if text:
            self.expandAll()

    def _on_double_clicked(self, index):
        setting = self._get_setting(index)
        if setting is not None:
            self.profile_activated.emit(setting.id)
            return
        dataset_id = self._get_dataset_id(index)
        if dataset_id:
            self.project_activated.emit(dataset_id)

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

    def _get_selected_profile_ids(self) -> list:
        """선택된 모든 프로파일의 ID 반환"""
        ids = []
        for index in self.selectedIndexes():
            setting = self._get_setting(index)
            if setting is not None and setting.id not in ids:
                ids.append(setting.id)
        return ids

    def _on_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return

        # 멀티 선택된 프로파일이 2개 이상이면 Compare 메뉴
        selected_ids = self._get_selected_profile_ids()
        if len(selected_ids) >= 2:
            self._show_compare_menu(pos, selected_ids)
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

        copy_to_action = menu.addAction("Copy to Dataset...")
        copy_to_action.triggered.connect(lambda: self.copy_to_dataset_requested.emit(profile_id))

        menu.addSeparator()

        fav_action = menu.addAction("⭐ Toggle Favorite")
        fav_action.triggered.connect(lambda: self.favorite_toggled.emit(profile_id))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self.delete_requested.emit(profile_id))

        menu.exec(self.viewport().mapToGlobal(pos))

    def _show_compare_menu(self, pos, profile_ids: list):
        menu = QMenu(self)
        menu.addSection(f"{len(profile_ids)} Profiles Selected")

        # Compare 실행
        compare_sbs = menu.addAction("📊 Compare — Side by Side")
        compare_sbs.triggered.connect(lambda: self.compare_requested.emit(
            profile_ids, {"mode": "side_by_side"}
        ))

        compare_overlay = menu.addAction("🔀 Compare — Overlay")
        compare_overlay.triggered.connect(lambda: self.compare_requested.emit(
            profile_ids, {"mode": "overlay"}
        ))

        if len(profile_ids) >= 2:
            compare_diff = menu.addAction("🔍 Compare — Difference")
            compare_diff.triggered.connect(lambda: self.compare_requested.emit(
                profile_ids, {"mode": "difference"}
            ))

        menu.addSeparator()

        # Remove selected profiles
        remove_action = menu.addAction("🗑️ Remove Selected")
        remove_action.triggered.connect(lambda: self._remove_selected_profiles(profile_ids))

        menu.exec(self.viewport().mapToGlobal(pos))

    def _remove_selected_profiles(self, profile_ids: list):
        """Remove multiple selected profiles"""
        for pid in profile_ids:
            self.delete_requested.emit(pid)

    def _on_selection_changed(self, selected, deselected):
        index = self.currentIndex()
        setting = self._get_setting(index)
        if setting is not None:
            self.profile_selected.emit(setting.id)

    def _map_to_source(self, index):
        """프록시 인덱스를 소스 모델 인덱스로 변환"""
        if hasattr(self, '_proxy') and self._proxy:
            return self._proxy.mapToSource(index)
        return index

    def _get_setting(self, index):
        if not self._model or not index.isValid():
            return None
        return self._model.get_setting(self._map_to_source(index))

    def _get_dataset_id(self, index) -> Optional[str]:
        if not self._model or not index.isValid():
            return None
        return self._model.get_dataset_id(self._map_to_source(index))
