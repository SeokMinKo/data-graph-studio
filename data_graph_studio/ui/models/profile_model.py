from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QMimeData, Qt, QByteArray

from ...core.profile import GraphSetting
from ...core.profile_store_protocol import ProfileStoreProtocol
from ..utils import chart_type_icon


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

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.MoveAction

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        node = index.internalPointer()
        if isinstance(node, _ProfileNode):
            if not node.is_dataset:
                flags |= Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
            else:
                flags |= Qt.ItemIsDropEnabled
        return flags

    def mimeTypes(self) -> List[str]:
        return ["application/x-dgs-profile-id"]

    def mimeData(self, indexes: List[QModelIndex]) -> QMimeData:
        mime = QMimeData()
        ids = []
        for idx in indexes:
            node = idx.internalPointer()
            if isinstance(node, _ProfileNode) and not node.is_dataset:
                ids.append(node.setting.id)
        mime.setData("application/x-dgs-profile-id", QByteArray(b"\n".join(i.encode() for i in ids)))
        return mime

    def dropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:
        if action != Qt.MoveAction:
            return False
        raw = bytes(data.data("application/x-dgs-profile-id")).decode()
        profile_ids = [pid for pid in raw.split("\n") if pid]
        if not profile_ids:
            return False

        # Determine target dataset
        if parent.isValid():
            parent_node = parent.internalPointer()
            if isinstance(parent_node, _ProfileNode):
                dataset_id = parent_node.dataset_id
            else:
                return False
        else:
            return False

        # Get current profile order for this dataset
        profiles = self._get_profiles(dataset_id)
        current_ids = [p.id for p in profiles]

        # Remove dragged ids from list
        moved_ids = [pid for pid in profile_ids if pid in current_ids]
        remaining = [pid for pid in current_ids if pid not in moved_ids]

        # Insert at target row
        if row < 0 or row > len(remaining):
            row = len(remaining)
        new_order = remaining[:row] + moved_ids + remaining[row:]

        # Update store order
        if hasattr(self._store, "reorder"):
            self._store.reorder(dataset_id, new_order)
        elif hasattr(self._store, "reorder_settings"):
            self._store.reorder_settings(dataset_id, new_order)

        self.refresh()
        return True

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
            prefix = "⭐ " if getattr(node.setting, 'is_favorite', False) else ""
            return prefix + node.setting.name

        if role == Qt.UserRole:
            if node.is_dataset:
                return node.dataset_id
            return node.setting

        if role == Qt.ToolTipRole:
            if not node.is_dataset:
                s = node.setting
                lines = [f"{chart_type_icon(s.chart_type)} {s.name}"]
                if s.chart_type:
                    lines.append(f"Chart: {s.chart_type}")
                if s.x_column:
                    lines.append(f"X: {s.x_column}")
                if s.value_columns:
                    y_names = [vc['name'] if isinstance(vc, dict) else str(vc) for vc in s.value_columns]
                    lines.append(f"Y: {', '.join(y_names[:3])}")
                    if len(y_names) > 3:
                        lines.append(f"  (+{len(y_names)-3} more)")
                if s.group_columns:
                    g_names = [gc['name'] if isinstance(gc, dict) else str(gc) for gc in s.group_columns]
                    lines.append(f"Group: {', '.join(g_names)}")
                if s.description:
                    lines.append(f"\n{s.description}")
                return '\n'.join(lines)
            else:
                # 데이터셋 툴팁: 행/열 수, 소스 파일
                metadata = self._state.dataset_metadata.get(node.dataset_id) if hasattr(self._state, 'dataset_metadata') else None
                if metadata:
                    lines = [metadata.name]
                    if hasattr(metadata, 'source_path') and metadata.source_path:
                        lines.append(f"Source: {metadata.source_path}")
                    if hasattr(metadata, 'row_count'):
                        lines.append(f"Rows: {metadata.row_count:,}")
                    profiles = self._get_profiles(node.dataset_id)
                    lines.append(f"Profiles: {len(profiles)}")
                    return '\n'.join(lines)

        # Note: DecorationRole은 반환하지 않음 - 문자열 반환 시 Qt가 QIcon 변환 시도하여 에러
        # 아이콘은 delegate에서 UserRole+1로 처리
        if role == Qt.UserRole + 1:
            if not node.is_dataset:
                return chart_type_icon(node.setting.chart_type)

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
        """프로파일 하나를 제거 (expand 상태 보존).

        Issue #6 — single-pass O(n) instead of O(n²).
        """
        try:
            ds_row = self._dataset_ids.index(dataset_id)
        except ValueError:
            self.refresh()
            return

        # Single-pass: find target row among this dataset's profile nodes
        row = 0
        target_idx = -1
        for i, node in enumerate(self._nodes):
            if node.dataset_id == dataset_id and node.setting is not None:
                if node.setting.id == profile_id:
                    target_idx = i
                    break
                row += 1

        if target_idx < 0:
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

        Uses dataChanged signal instead of beginResetModel to preserve
        the tree expand/collapse state.
        """
        if dataset_id not in self._dataset_ids:
            return

        # Find and replace the node in cache
        for i, node in enumerate(self._nodes):
            if (node.dataset_id == dataset_id
                    and node.setting is not None
                    and node.setting.id == setting.id):
                self._nodes[i] = _ProfileNode(dataset_id=dataset_id, setting=setting)

                # Emit dataChanged for just the affected index
                try:
                    ds_row = self._dataset_ids.index(dataset_id)
                    parent_node = self._find_node(dataset_id)
                    parent_idx = self.createIndex(ds_row, 0, parent_node)
                    profiles = self._get_profiles(dataset_id)
                    for j, p in enumerate(profiles):
                        if p.id == setting.id:
                            child_idx = self.index(j, 0, parent_idx)
                            self.dataChanged.emit(child_idx, child_idx)
                            break
                except (ValueError, IndexError):
                    pass
                return

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
        """Retrieve profiles for a dataset.

        Issue #4 — prefer the ``ProfileStoreProtocol`` method
        ``get_by_dataset`` and fall back gracefully.
        """
        profiles: List[GraphSetting] = []
        if isinstance(self._store, ProfileStoreProtocol):
            profiles = list(self._store.get_by_dataset(dataset_id))
        elif hasattr(self._store, "get_by_dataset"):
            profiles = list(self._store.get_by_dataset(dataset_id))
        elif hasattr(self._store, "get_profiles"):
            profiles = list(self._store.get_profiles(dataset_id))
        elif isinstance(self._store, dict):
            profiles = list(self._store.get(dataset_id, []))
        else:
            profiles = []

        # Sort favorites first, preserve original order within each group
        profiles.sort(key=lambda p: not getattr(p, 'is_favorite', False))
        return profiles
