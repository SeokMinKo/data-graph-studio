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
        return len(self.children) > 0 or len(self.rows) > 1 or "_count" in self.aggregates

    @property
    def row_count(self) -> int:
        """Total rows under this node"""
        # Use _count aggregate if available (from optimized tree build)
        if "_count" in self.aggregates:
            return int(self.aggregates["_count"])
        if self.rows:
            return len(self.rows)
        if self.children:
            return sum(child.row_count for child in self.children)
        return 0

    def visible_row_count(self) -> int:
        """Visible rows (considering expanded state)"""
        if not self.expanded:
            return 1  # Just the header

        if self.children:
            return 1 + sum(child.visible_row_count() for child in self.children)
        else:
            # If using optimized build (_count), don't show individual rows
            if "_count" in self.aggregates and not self.rows:
                return 1  # Just the header
            return 1 + len(self.rows)  # Header + data rows


class GroupedTableModel(QAbstractItemModel):
    """
    Hierarchical table model with grouping support
    
    Features:
    - Multi-level grouping
    - Expand/collapse groups
    - Aggregate values in group headers
    - Virtual scrolling friendly
    - Auto-aggregation of all numeric columns
    """
    
    expand_changed = Signal()  # Emitted when expand state changes
    
    # Default aggregation for auto-detected numeric columns (fallback when Value Zone is empty)
    DEFAULT_AUTO_AGGREGATION = 'sum'
    
    def _get_effective_default_aggregation(self) -> str:
        """Get default aggregation for auto-detected numeric columns.
        
        If Value Zone has columns with specified aggregation, use the first one's type.
        Otherwise, fall back to DEFAULT_AUTO_AGGREGATION (sum).
        
        Returns:
            Aggregation function name ('sum', 'mean', 'count', 'min', 'max')
        """
        # If there are value columns with specified aggregations, use the first one
        if self._value_columns and self._aggregations:
            for col in self._value_columns:
                if col in self._aggregations:
                    return self._aggregations[col]
        
        return self.DEFAULT_AUTO_AGGREGATION
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._df: Optional[pl.DataFrame] = None
        self._group_columns: List[str] = []
        self._value_columns: List[str] = []  # Explicit value columns from Value Zone
        self._aggregations: Dict[str, str] = {}  # column -> agg function
        
        # Auto-detected numeric columns (not in value_columns)
        self._auto_numeric_columns: List[str] = []
        # Combined list: value_columns + auto_numeric_columns
        self._all_value_columns: List[str] = []
        
        self._root: Optional[GroupNode] = None
        self._flat_view: List[Tuple[GroupNode, Optional[int]]] = []  # (node, row_idx or None for header)
        
        self._visible_columns: List[str] = []
        
        # Colors for groups
        self._group_colors = [
            "#59B8E3", "#EC4899", "#10B981", "#F59E0B", "#3B82F6",
            "#EF4444", "#8B5CF6", "#06B6D4", "#84CC16", "#F97316"
        ]
    
    def set_data(
        self,
        df: Optional[pl.DataFrame],
        group_columns: List[str] = None,
        value_columns: List[str] = None,
        aggregations: Dict[str, str] = None
    ):
        """Set data and grouping configuration
        
        Auto-detects all numeric columns and aggregates them:
        - Explicit value_columns use their specified aggregation
        - Other numeric columns use DEFAULT_AUTO_AGGREGATION (sum)
        """
        self.beginResetModel()
        
        self._df = df
        self._group_columns = group_columns or []
        self._value_columns = value_columns or []
        self._aggregations = aggregations or {}
        
        if df is not None:
            self._visible_columns = df.columns
            # Auto-detect numeric columns not in value_columns
            self._auto_numeric_columns = self._detect_numeric_columns(df)
            # Combine explicit and auto columns
            self._all_value_columns = self._value_columns + self._auto_numeric_columns
            self._build_tree()
        else:
            self._root = None
            self._flat_view = []
            self._visible_columns = []
            self._auto_numeric_columns = []
            self._all_value_columns = []
        
        self.endResetModel()
    
    def _detect_numeric_columns(self, df: pl.DataFrame) -> List[str]:
        """Detect numeric columns not already in value_columns or group_columns
        
        Returns:
            List of numeric column names to auto-aggregate
        """
        if df is None or len(df.columns) == 0:
            return []
        
        # Columns to exclude from auto-detection
        exclude_set = set(self._value_columns) | set(self._group_columns)
        
        # Numeric dtypes in Polars
        numeric_dtypes = (
            pl.Int8, pl.Int16, pl.Int32, pl.Int64,
            pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
            pl.Float32, pl.Float64,
        )
        
        auto_numeric = []
        for col in df.columns:
            if col in exclude_set:
                continue
            # Check if column is numeric
            if df[col].dtype in numeric_dtypes:
                auto_numeric.append(col)
        
        return auto_numeric
    
    def _build_tree(self):
        """Build hierarchical group tree (optimized with Polars)"""
        if self._df is None or len(self._df) == 0:
            self._root = None
            self._flat_view = []
            return
        
        # Root node
        self._root = GroupNode(key=(), display_name="All", level=-1)
        
        if not self._group_columns:
            # No grouping - flat list (limit for performance)
            max_rows = min(len(self._df), 100000)  # 테이블에 표시할 최대 행
            self._root.rows = list(range(max_rows))
            self._rebuild_flat_view()
            return
        
        # Polars groupby로 빠르게 그룹화 (최적화)
        self._build_tree_optimized()
        
        self._rebuild_flat_view()
    
    def _build_tree_optimized(self):
        """Polars groupby를 사용한 최적화된 트리 빌드
        
        Aggregates all value columns:
        - Explicit value_columns use their specified aggregation
        - Auto-detected numeric columns use DEFAULT_AUTO_AGGREGATION
        """
        if self._df is None or not self._group_columns:
            return
        
        # 그룹별 집계를 Polars로 한번에 계산
        agg_exprs = [pl.len().alias("_count")]
        
        # Get effective default aggregation from Value Zone
        effective_default_agg = self._get_effective_default_aggregation()
        
        # Aggregate all value columns (explicit + auto-detected)
        for col in self._all_value_columns:
            if col in self._df.columns:
                # Use explicit aggregation if specified, otherwise use effective default
                if col in self._value_columns:
                    agg_func = self._aggregations.get(col, 'sum')
                else:
                    # Auto-detected column: use effective default (from Value Zone or fallback)
                    agg_func = effective_default_agg
                
                if agg_func == 'sum':
                    agg_exprs.append(pl.col(col).sum().alias(f"_agg_{col}"))
                elif agg_func == 'mean':
                    agg_exprs.append(pl.col(col).mean().alias(f"_agg_{col}"))
                elif agg_func == 'count':
                    agg_exprs.append(pl.col(col).count().alias(f"_agg_{col}"))
                elif agg_func == 'min':
                    agg_exprs.append(pl.col(col).min().alias(f"_agg_{col}"))
                elif agg_func == 'max':
                    agg_exprs.append(pl.col(col).max().alias(f"_agg_{col}"))
                else:
                    agg_exprs.append(pl.col(col).sum().alias(f"_agg_{col}"))
        
        # Polars groupby 실행 (C 레벨에서 최적화)
        try:
            grouped = self._df.group_by(self._group_columns).agg(agg_exprs).sort(self._group_columns)
        except:
            # 실패 시 기본 방식
            self._build_group_recursive(
                self._root,
                self._group_columns,
                list(range(min(len(self._df), 10000))),
                0
            )
            return
        
        # 그룹 개수 제한 (성능)
        MAX_GROUPS = 1000
        if len(grouped) > MAX_GROUPS:
            grouped = grouped.head(MAX_GROUPS)
        
        # 트리 구조 빌드 (집계 결과에서)
        for row in grouped.iter_rows(named=True):
            parent = self._root
            
            for i, col in enumerate(self._group_columns):
                value = row[col]
                display = f"{value}" if value is not None else "(Empty)"
                
                # 기존 자식 찾기
                existing = None
                for child in parent.children:
                    if child.display_name == display:
                        existing = child
                        break
                
                if existing:
                    parent = existing
                else:
                    # 새 노드 생성
                    child = GroupNode(
                        key=parent.key + (value,),
                        display_name=display,
                        parent=parent,
                        level=i
                    )
                    parent.children.append(child)
                    parent = child
            
            # 마지막 노드에 집계값 저장
            parent.aggregates["_count"] = row["_count"]
            for col in self._all_value_columns:
                agg_key = f"_agg_{col}"
                if agg_key in row:
                    parent.aggregates[col] = row[agg_key]
            
            # 행 인덱스는 저장하지 않음 (성능)
    
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
        """Calculate aggregate values for node and children
        
        Aggregates all value columns (explicit + auto-detected)
        """
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
        
        # Get effective default aggregation from Value Zone
        effective_default_agg = self._get_effective_default_aggregation()
        
        # Calculate aggregates for all value columns (explicit + auto-detected)
        for col in self._all_value_columns:
            if col not in self._df.columns:
                continue
            
            # Use explicit aggregation if specified, otherwise use effective default
            if col in self._value_columns:
                agg_func = self._aggregations.get(col, 'sum')
            else:
                agg_func = effective_default_agg
            
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

        # Add leaf rows (only if no children and rows exist)
        # Skip if using optimized build with _count but no rows
        if not node.children and node.rows:
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

        # If expanding and node has _count but no rows, load rows dynamically
        if not node.expanded and "_count" in node.aggregates and not node.rows and not node.children:
            self._load_node_rows(node)

        if not node.children and len(node.rows) <= 1 and "_count" not in node.aggregates:
            return  # Nothing to expand

        # Toggle
        node.expanded = not node.expanded

        # Rebuild flat view
        self.beginResetModel()
        self._rebuild_flat_view()
        self.endResetModel()

        self.expand_changed.emit()

    def _load_node_rows(self, node: GroupNode):
        """Dynamically load row indices for a node from the original dataframe"""
        if self._df is None or not self._group_columns:
            return

        # Build filter for this group
        # The node.key contains the values for each group column in order
        if len(node.key) != len(self._group_columns):
            return

        try:
            # Create mask for rows matching this group
            mask = None
            for col, val in zip(self._group_columns, node.key):
                if val is None:
                    col_mask = self._df[col].is_null()
                else:
                    col_mask = self._df[col] == val

                if mask is None:
                    mask = col_mask
                else:
                    mask = mask & col_mask

            if mask is not None:
                # Get row indices where mask is True
                # Limit to prevent memory issues with very large groups
                MAX_ROWS_PER_GROUP = 1000
                row_indices = []
                mask_list = mask.to_list()
                for i, m in enumerate(mask_list):
                    if m:
                        row_indices.append(i)
                        if len(row_indices) >= MAX_ROWS_PER_GROUP:
                            break

                node.rows = row_indices
        except Exception as e:
            print(f"Error loading node rows: {e}")
            node.rows = []
    
    def expand_all(self):
        """Expand all groups"""
        # First load rows for all leaf nodes that need it
        self._load_all_leaf_rows(self._root)
        self._set_expand_all(self._root, True)
        self.beginResetModel()
        self._rebuild_flat_view()
        self.endResetModel()
        self.expand_changed.emit()

    def _load_all_leaf_rows(self, node: GroupNode):
        """Load rows for all leaf nodes that have _count but no rows"""
        if node is None:
            return

        if node.children:
            for child in node.children:
                self._load_all_leaf_rows(child)
        else:
            # Leaf node - load rows if needed
            if "_count" in node.aggregates and not node.rows:
                self._load_node_rows(node)
    
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
    
    def get_column_name(self, index: int) -> Optional[str]:
        """Get column name by visual index (for drag & drop compatibility)"""
        if index == 0:
            # First column is the group/row indicator
            return None
        
        data_col_idx = index - 1
        if 0 <= data_col_idx < len(self._visible_columns):
            return self._visible_columns[data_col_idx]
        return None
