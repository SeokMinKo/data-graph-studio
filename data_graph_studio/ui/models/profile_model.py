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
        self._nodes: List[_ProfileNode] = []  # prevent GC of internalPointer objects
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

    def hasChildren(self, parent: QModelIndex = QModelIndex()) -> bool:
        return self.rowCount(parent) > 0

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

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
            return node.setting.name

        if role == Qt.UserRole:
            if node.is_dataset:
                return node.dataset_id
            return node.setting

        if role == Qt.ToolTipRole:
            if not node.is_dataset:
                icon = self._chart_type_icon(node.setting.chart_type)
                return f"{icon} {node.setting.name}"

        # Note: DecorationRole은 반환하지 않음 - 문자열 반환 시 Qt가 QIcon 변환 시도하여 에러
        # 아이콘은 delegate에서 UserRole+1로 처리
        if role == Qt.UserRole + 1:
            if not node.is_dataset:
                return self._chart_type_icon(node.setting.chart_type)

        return None

    def _find_node(self, dataset_id: str, setting: Optional[GraphSetting] = None) -> _ProfileNode:
        """Find a cached node, or create and cache a new one."""
        for n in self._nodes:
            if n.dataset_id == dataset_id and n.setting is setting:
                return n
        node = _ProfileNode(dataset_id=dataset_id, setting=setting)
        self._nodes.append(node)
        return node

    def index(self, row: int, col: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if col != 0 or row < 0:
            return QModelIndex()

        if not parent.isValid():
            if row >= len(self._dataset_ids):
                return QModelIndex()
            dataset_id = self._dataset_ids[row]
            node = self._find_node(dataset_id)
            return self.createIndex(row, col, node)

        parent_node = parent.internalPointer()
        if not isinstance(parent_node, _ProfileNode) or not parent_node.is_dataset:
            return QModelIndex()

        profiles = self._get_profiles(parent_node.dataset_id)
        if row >= len(profiles):
            return QModelIndex()

        node = self._find_node(parent_node.dataset_id, profiles[row])
        return self.createIndex(row, col, node)

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

        parent_node = self._find_node(node.dataset_id)
        return self.createIndex(row, 0, parent_node)

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
        # Rebuild node cache to keep internalPointer objects alive (PySide6 GC safety)
        self._nodes.clear()
        for ds_id in self._dataset_ids:
            self._nodes.append(_ProfileNode(dataset_id=ds_id))
            for profile in self._get_profiles(ds_id):
                self._nodes.append(_ProfileNode(dataset_id=ds_id, setting=profile))
        self.endResetModel()

    def add_profile_incremental(self, dataset_id: str, setting: GraphSetting) -> None:
        """프로파일 하나를 추가 (expand 상태 보존, beginResetModel 안 씀)."""
        try:
            ds_row = self._dataset_ids.index(dataset_id)
        except ValueError:
            # 데이터셋이 없으면 full refresh
            self.refresh()
            return

        profiles = self._get_profiles(dataset_id)
        new_row = len(profiles) - 1  # 이미 store에 add된 후 호출되므로
        if new_row < 0:
            self.refresh()
            return

        parent_node = self._find_node(dataset_id)
        parent_idx = self.createIndex(ds_row, 0, parent_node)

        self.beginInsertRows(parent_idx, new_row, new_row)
        self._nodes.append(_ProfileNode(dataset_id=dataset_id, setting=setting))
        self.endInsertRows()

    def remove_profile_incremental(self, dataset_id: str, profile_id: str) -> None:
        """프로파일 하나를 제거 (expand 상태 보존)."""
        try:
            ds_row = self._dataset_ids.index(dataset_id)
        except ValueError:
            self.refresh()
            return

        # 삭제 전 프로파일 목록에서 row 찾기 (이미 store에서 제거됐으므로 node cache에서 찾음)
        row = -1
        for i, node in enumerate(self._nodes):
            if (node.dataset_id == dataset_id
                    and node.setting is not None
                    and node.setting.id == profile_id):
                row_count = 0
                # 해당 dataset의 프로파일 중 몇 번째인지 계산
                for n in self._nodes:
                    if n.dataset_id == dataset_id and n.setting is not None:
                        if n.setting.id == profile_id:
                            row = row_count
                            break
                        row_count += 1
                break

        if row < 0:
            self.refresh()
            return

        parent_node = self._find_node(dataset_id)
        parent_idx = self.createIndex(ds_row, 0, parent_node)

        self.beginRemoveRows(parent_idx, row, row)
        self._nodes = [n for n in self._nodes
                       if not (n.dataset_id == dataset_id
                               and n.setting is not None
                               and n.setting.id == profile_id)]
        self.endRemoveRows()

    def update_profile_data(self, dataset_id: str, setting: GraphSetting) -> None:
        """프로파일 데이터만 업데이트 (이름 변경 등, expand 상태 보존).

        Uses beginResetModel/endResetModel to safely rebuild the node cache.
        This avoids stale internalPointer access violations that occur when
        swapping frozen _ProfileNode objects while Qt views still hold old
        QModelIndex references.
        """
        # Verify dataset exists
        if dataset_id not in self._dataset_ids:
            return

        # Check if the profile actually exists in our cache
        found = any(
            n.dataset_id == dataset_id
            and n.setting is not None
            and n.setting.id == setting.id
            for n in self._nodes
        )
        if not found:
            return

        # Safe full rebuild — clears all internalPointers before replacing nodes
        self.beginResetModel()
        self._nodes.clear()
        for ds_id in self._dataset_ids:
            self._nodes.append(_ProfileNode(dataset_id=ds_id))
            for profile in self._get_profiles(ds_id):
                # Use the updated setting for the matching profile
                if ds_id == dataset_id and profile.id == setting.id:
                    self._nodes.append(_ProfileNode(dataset_id=ds_id, setting=setting))
                else:
                    self._nodes.append(_ProfileNode(dataset_id=ds_id, setting=profile))
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
