"""
Grouped Table Model - Hierarchical data display with expand/collapse
"""

from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
import polars as pl

from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex, Signal
from PySide6.QtGui import QFont, QColor, QBrush


@dataclass
class GroupNode:
    """Group tree node"""
    key: Tuple  # Group key values (tuple for multi-level grouping)
    display_name: str
    parent: Optional['GroupNode'] = None
    children: List['GroupNode'] = field(default_factory=list)
    rows: List[int] = field(default_factory=list)  # Row indices in original df
    aggregates: Dict[str, Any] = field(default_factory=dict)  # Column -> agg value
    expanded: bool = True
    level: int = 0
    
    @property
    def is_group(self) -> bool:
        """Is this a group header (vs leaf row)?"""
        return len(self.children) > 0 or len(self.rows) > 1
    
    @property
    def row_count(self) -> int:
        """Total rows under this node"""
        if self.rows:
            return len(self.rows)
        return sum(child.row_count for child in self.children)
    
    def visible_row_count(self) -> int:
        """Visible rows (considering expanded state)"""
        if not self.expanded:
            return 1  # Just the header
        
        if self.children:
            return 1 + sum(child.visible_row_count() for child in self.children)
        else:
            return 1 + len(self.rows)  # Header + data rows


class GroupedTableModel(QAbstractItemModel):
    """
    Hierarchical table model with grouping support
    
    Features:
    - Multi-level grouping
    - Expand/collapse groups
    - Aggregate values in group headers
    - Virtual scrolling friendly
    """
    
    expand_changed = Signal()  # Emitted when expand state changes
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._df: Optional[pl.DataFrame] = None
        self._group_columns: List[str] = []
        self._value_columns: List[str] = []
        self._aggregations: Dict[str, str] = {}  # column -> agg function
        
        self._root: Optional[GroupNode] = None
        self._flat_view: List[Tuple[GroupNode, Optional[int]]] = []  # (node, row_idx or None for header)
        
        self._visible_columns: List[str] = []
        
        # Colors for groups
        self._group_colors = [
            "#6366F1", "#EC4899", "#10B981", "#F59E0B", "#3B82F6",
            "#EF4444", "#8B5CF6", "#06B6D4", "#84CC16", "#F97316"
        ]
    
    def set_data(
        self,
        df: Optional[pl.DataFrame],
        group_columns: List[str] = None,
        value_columns: List[str] = None,
        aggregations: Dict[str, str] = None
    ):
        """Set data and grouping configuration"""
        self.beginResetModel()
        
        self._df = df
        self._group_columns = group_columns or []
        self._value_columns = value_columns or []
        self._aggregations = aggregations or {}
        
        if df is not None:
            self._visible_columns = df.columns
            self._build_tree()
        else:
            self._root = None
            self._flat_view = []
            self._visible_columns = []
        
        self.endResetModel()
    
    def _build_tree(self):
        """Build hierarchical group tree"""
        if self._df is None or len(self._df) == 0:
            self._root = None
            self._flat_view = []
            return
        
        # Root node
        self._root = GroupNode(key=(), display_name="All", level=-1)
        
        if not self._group_columns:
            # No grouping - flat list
            self._root.rows = list(range(len(self._df)))
            self._rebuild_flat_view()
            return
        
        # Build grouped structure
        self._build_group_recursive(
            self._root,
            self._group_columns,
            list(range(len(self._df))),
            0
        )
        
        # Calculate aggregates
        self._calculate_aggregates(self._root)
        
        self._rebuild_flat_view()
    
    def _build_group_recursive(
        self,
        parent: GroupNode,
        remaining_columns: List[str],
        row_indices: List[int],
        level: int
    ):
        """Recursively build group tree"""
        if not remaining_columns or not row_indices:
            parent.rows = row_indices
            return
        
        group_col = remaining_columns[0]
        rest_columns = remaining_columns[1:]
        
        # Get unique values for this column
        subset = self._df[row_indices]
        unique_values = subset[group_col].unique().sort().to_list()
        
        for value in unique_values:
            # Find rows matching this value
            # Handle None/NULL values properly
            if value is None:
                mask = self._df[group_col].is_null()
            else:
                mask = self._df[group_col] == value
            child_rows = [i for i in row_indices if mask[i]]
            
            if not child_rows:
                continue
            
            # Create child node
            child_key = parent.key + (value,)
            display = f"{value}" if value is not None else "(Empty)"
            
            child = GroupNode(
                key=child_key,
                display_name=display,
                parent=parent,
                level=level
            )
            parent.children.append(child)
            
            # Recurse for deeper levels
            if rest_columns:
                self._build_group_recursive(child, rest_columns, child_rows, level + 1)
            else:
                child.rows = child_rows
    
    def _calculate_aggregates(self, node: GroupNode):
        """Calculate aggregate values for node and children"""
        # Process children first (bottom-up)
        for child in node.children:
            self._calculate_aggregates(child)
        
        if self._df is None:
            return
        
        # Get all rows under this node
        all_rows = self._get_all_rows(node)
        
        if not all_rows:
            return
        
        subset = self._df[all_rows]
        
        # Calculate aggregates for value columns
        for col in self._value_columns:
            if col not in self._df.columns:
                continue
            
            agg_func = self._aggregations.get(col, 'sum')
            
            try:
                if agg_func == 'sum':
                    node.aggregates[col] = subset[col].sum()
                elif agg_func == 'mean':
                    node.aggregates[col] = subset[col].mean()
                elif agg_func == 'count':
                    node.aggregates[col] = subset[col].count()
                elif agg_func == 'min':
                    node.aggregates[col] = subset[col].min()
                elif agg_func == 'max':
                    node.aggregates[col] = subset[col].max()
                else:
                    node.aggregates[col] = subset[col].sum()
            except:
                node.aggregates[col] = None
    
    def _get_all_rows(self, node: GroupNode) -> List[int]:
        """Get all row indices under a node"""
        if node.rows:
            return node.rows
        
        rows = []
        for child in node.children:
            rows.extend(self._get_all_rows(child))
        return rows
    
    def _rebuild_flat_view(self):
        """Rebuild flattened view for display"""
        self._flat_view = []
        
        if self._root is None:
            return
        
        if not self._group_columns:
            # No grouping - just show rows
            for row_idx in self._root.rows:
                self._flat_view.append((self._root, row_idx))
        else:
            # Build flat view from tree
            self._flatten_node(self._root)
    
    def _flatten_node(self, node: GroupNode, skip_root: bool = True):
        """Recursively flatten node into view"""
        if not skip_root or node.level >= 0:
            if node.is_group or node.level >= 0:
                # Add group header
                self._flat_view.append((node, None))
        
        if not node.expanded and node.level >= 0:
            return  # Collapsed - don't show children
        
        # Add children
        for child in node.children:
            self._flatten_node(child, skip_root=False)
        
        # Add leaf rows (only if no children)
        if not node.children:
            for row_idx in node.rows:
                self._flat_view.append((node, row_idx))
    
    # ==================== Qt Model Interface ====================
    
    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0  # Flat model (tree structure in flat_view)
        return len(self._flat_view)
    
    def columnCount(self, parent=QModelIndex()):
        # Group indent column + data columns
        return 1 + len(self._visible_columns)
    
    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        return self.createIndex(row, column)
    
    def parent(self, index):
        return QModelIndex()  # Flat model
    
    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._flat_view):
            return None
        
        node, row_idx = self._flat_view[index.row()]
        col = index.column()
        is_header = row_idx is None
        
        if role == Qt.DisplayRole:
            if col == 0:
                # Expand/collapse indicator + group name
                if is_header:
                    indicator = "▼ " if node.expanded else "▶ "
                    indent = "    " * node.level
                    count = f" ({node.row_count})"
                    return f"{indent}{indicator}{node.display_name}{count}"
                else:
                    indent = "    " * (node.level + 1)
                    return indent
            else:
                # Data column
                data_col_idx = col - 1
                if data_col_idx >= len(self._visible_columns):
                    return None
                
                col_name = self._visible_columns[data_col_idx]
                
                if is_header:
                    # Show aggregate value
                    if col_name in node.aggregates:
                        val = node.aggregates[col_name]
                        if isinstance(val, float):
                            return f"{val:,.2f}"
                        elif val is not None:
                            return str(val)
                    return ""
                else:
                    # Show actual data
                    if self._df is not None and row_idx < len(self._df):
                        val = self._df[col_name][row_idx]
                        if val is None:
                            return ""
                        if isinstance(val, float):
                            return f"{val:,.2f}"
                        return str(val)
        
        elif role == Qt.BackgroundRole:
            if is_header:
                # Group header background
                color_idx = node.level % len(self._group_colors)
                color = QColor(self._group_colors[color_idx])
                color.setAlpha(30 + node.level * 10)
                return QBrush(color)
        
        elif role == Qt.FontRole:
            if is_header:
                font = QFont()
                font.setBold(True)
                return font
        
        elif role == Qt.ForegroundRole:
            if is_header:
                color_idx = node.level % len(self._group_colors)
                return QBrush(QColor(self._group_colors[color_idx]))
        
        elif role == Qt.UserRole:
            # Return node for external use
            return (node, row_idx)
        
        elif role == Qt.UserRole + 1:
            # Is this a group header?
            return is_header
        
        return None
    
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                if self._group_columns:
                    return " / ".join(self._group_columns)
                return "Row"
            else:
                data_col_idx = section - 1
                if data_col_idx < len(self._visible_columns):
                    return self._visible_columns[data_col_idx]
        return None
    
    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    
    # ==================== Expand/Collapse ====================
    
    def toggle_expand(self, row: int):
        """Toggle expand state for a group row"""
        if row < 0 or row >= len(self._flat_view):
            return
        
        node, row_idx = self._flat_view[row]
        
        if row_idx is not None:
            return  # Not a group header
        
        if not node.children and len(node.rows) <= 1:
            return  # Nothing to expand
        
        # Toggle
        node.expanded = not node.expanded
        
        # Rebuild flat view
        self.beginResetModel()
        self._rebuild_flat_view()
        self.endResetModel()
        
        self.expand_changed.emit()
    
    def expand_all(self):
        """Expand all groups"""
        self._set_expand_all(self._root, True)
        self.beginResetModel()
        self._rebuild_flat_view()
        self.endResetModel()
        self.expand_changed.emit()
    
    def collapse_all(self):
        """Collapse all groups"""
        self._set_expand_all(self._root, False)
        self.beginResetModel()
        self._rebuild_flat_view()
        self.endResetModel()
        self.expand_changed.emit()
    
    def _set_expand_all(self, node: GroupNode, expanded: bool):
        """Set expand state for node and all children"""
        if node is None:
            return
        node.expanded = expanded
        for child in node.children:
            self._set_expand_all(child, expanded)
    
    # ==================== Accessors ====================
    
    def get_group_data(self) -> List[Tuple[str, List[int], str]]:
        """
        Get group info for graph rendering
        
        Returns: [(group_name, row_indices, color), ...]
        """
        if self._root is None or not self._group_columns:
            return []
        
        result = []
        self._collect_leaf_groups(self._root, result)
        return result
    
    def _collect_leaf_groups(
        self,
        node: GroupNode,
        result: List[Tuple[str, List[int], str]]
    ):
        """Collect leaf groups (groups with actual rows)"""
        if node.level < 0:
            # Root node
            for child in node.children:
                self._collect_leaf_groups(child, result)
            return
        
        if node.children:
            # Has sub-groups
            for child in node.children:
                self._collect_leaf_groups(child, result)
        else:
            # Leaf group
            color_idx = len(result) % len(self._group_colors)
            result.append((
                node.display_name,
                node.rows,
                self._group_colors[color_idx]
            ))
    
    def get_group_colors(self) -> List[str]:
        """Get color palette"""
        return self._group_colors.copy()
    
    def get_visible_row_indices(self) -> List[int]:
        """Get original DataFrame row indices for visible rows"""
        indices = []
        for node, row_idx in self._flat_view:
            if row_idx is not None:
                indices.append(row_idx)
        return indices
