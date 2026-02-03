from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from ...core.profile import GraphSetting


@dataclass(frozen=True)
class _ProfileNode:
    dataset_id: str
    setting: Optional[GraphSetting] = None

    @property
    def is_dataset(self) -> bool:
        return self.setting is None


class ProfileModel(QAbstractItemModel):
    def __init__(self, store: Any, state: Any):
        super().__init__()
        self._store = store
        self._state = state
        self._dataset_ids: List[str] = []
        self.refresh()

    # ==================== Qt Model Interface ====================

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._dataset_ids)

        node = parent.internalPointer()
        if not isinstance(node, _ProfileNode) or not node.is_dataset:
            return 0

        try:
            return len(self._get_profiles(node.dataset_id))
        except (AttributeError, TypeError):
            return 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        node = index.internalPointer()
        if not isinstance(node, _ProfileNode):
            return None

        try:
            _ = node.dataset_id  # stale pointer 체크
        except (AttributeError, TypeError):
            return None

        if role == Qt.DisplayRole:
            if node.is_dataset:
                return self._get_dataset_name(node.dataset_id)
            # Use chart_type_icon instead of non-existent icon property
            icon = self._chart_type_icon(node.setting.chart_type)
            return f"{icon} {node.setting.name}"

        if role == Qt.UserRole:
            if node.is_dataset:
                return node.dataset_id
            return node.setting

        if role == Qt.DecorationRole:
            if not node.is_dataset:
                return self._chart_type_icon(node.setting.chart_type)

        return None

    def index(self, row: int, col: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if col != 0 or row < 0:
            return QModelIndex()

        if not parent.isValid():
            if row >= len(self._dataset_ids):
                return QModelIndex()
            dataset_id = self._dataset_ids[row]
            return self.createIndex(row, col, _ProfileNode(dataset_id=dataset_id))

        node = parent.internalPointer()
        if not isinstance(node, _ProfileNode) or not node.is_dataset:
            return QModelIndex()

        profiles = self._get_profiles(node.dataset_id)
        if row >= len(profiles):
            return QModelIndex()

        return self.createIndex(row, col, _ProfileNode(dataset_id=node.dataset_id, setting=profiles[row]))

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        node = index.internalPointer()
        if not isinstance(node, _ProfileNode) or node.is_dataset:
            return QModelIndex()

        try:
            row = self._dataset_ids.index(node.dataset_id)
        except ValueError:
            return QModelIndex()

        return self.createIndex(row, 0, _ProfileNode(dataset_id=node.dataset_id))

    # ==================== Custom Methods ====================

    def get_setting(self, index: QModelIndex) -> Optional[GraphSetting]:
        if not index.isValid():
            return None
        node = index.internalPointer()
        if isinstance(node, _ProfileNode) and not node.is_dataset:
            return node.setting
        return None

    def get_dataset_id(self, index: QModelIndex) -> Optional[str]:
        if not index.isValid():
            return None
        node = index.internalPointer()
        if isinstance(node, _ProfileNode):
            return node.dataset_id
        return None

    def refresh(self) -> None:
        self.beginResetModel()
        self._dataset_ids = list(self._get_dataset_ids())
        self.endResetModel()

    # ==================== Internal Helpers ====================

    def _get_dataset_ids(self) -> List[str]:
        if hasattr(self._state, "dataset_metadata"):
            return list(self._state.dataset_metadata.keys())
        if hasattr(self._state, "dataset_states"):
            return list(self._state.dataset_states.keys())
        if hasattr(self._state, "dataset_ids"):
            return list(self._state.dataset_ids)
        return []

    def _get_dataset_name(self, dataset_id: str) -> str:
        if hasattr(self._state, "get_dataset_metadata"):
            metadata = self._state.get_dataset_metadata(dataset_id)
            if metadata and getattr(metadata, "name", None):
                return metadata.name
        if hasattr(self._state, "dataset_metadata"):
            metadata = self._state.dataset_metadata.get(dataset_id)
            if metadata and getattr(metadata, "name", None):
                return metadata.name
        return dataset_id

    def _get_profiles(self, dataset_id: str) -> List[GraphSetting]:
        # ProfileStore API
        if hasattr(self._store, "get_by_dataset"):
            return list(self._store.get_by_dataset(dataset_id))
        if hasattr(self._store, "get_profiles"):
            return list(self._store.get_profiles(dataset_id))
        if hasattr(self._store, "get_settings"):
            return list(self._store.get_settings(dataset_id))
        if isinstance(self._store, dict):
            return list(self._store.get(dataset_id, []))
        if hasattr(self._store, "profiles_by_dataset"):
            profiles = self._store.profiles_by_dataset.get(dataset_id, [])
            return list(profiles)
        return []

    def _chart_type_icon(self, chart_type: str) -> str:
        chart_type = (chart_type or "").lower()
        mapping = {
            "line": "📈",
            "bar": "📊",
            "scatter": "⚬",
            "area": "▤",
            "pie": "🥧",
            "histogram": "▦",
        }
        return mapping.get(chart_type, "📊")
