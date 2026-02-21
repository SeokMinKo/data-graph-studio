"""
Dashboard Mode - Legacy module.

All primary dashboard functionality has been moved to:
- data_graph_studio/ui/panels/dashboard_panel.py  (UI)
- data_graph_studio/core/dashboard_controller.py   (controller)
- data_graph_studio/core/dashboard_layout.py       (data structures)

This file re-exports legacy classes for backward compatibility with tests.
"""

# Re-export legacy classes that tests still reference
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


try:
    from ..core.state import ChartType
except ImportError:
    from core.state import ChartType


@dataclass
class GridPosition:
    """그리드 위치 (legacy — kept for test compatibility)."""
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1

    def __eq__(self, other):
        if not isinstance(other, GridPosition):
            return False
        return (self.row == other.row and
                self.col == other.col and
                self.row_span == other.row_span and
                self.col_span == other.col_span)

    def overlaps(self, other: 'GridPosition') -> bool:
        r1_start, r1_end = self.row, self.row + self.row_span
        c1_start, c1_end = self.col, self.col + self.col_span
        r2_start, r2_end = other.row, other.row + other.row_span
        c2_start, c2_end = other.col, other.col + other.col_span
        return (r1_start < r2_end and r2_start < r1_end and
                c1_start < c2_end and c2_start < c1_end)

    def to_dict(self) -> Dict:
        return {'row': self.row, 'col': self.col,
                'row_span': self.row_span, 'col_span': self.col_span}

    @classmethod
    def from_dict(cls, data: Dict) -> 'GridPosition':
        return cls(row=data['row'], col=data['col'],
                   row_span=data.get('row_span', 1), col_span=data.get('col_span', 1))


@dataclass
class DashboardItem:
    """대시보드 아이템 (legacy)."""
    id: str
    title: str
    chart_type: ChartType
    position: GridPosition
    config: Dict[str, Any] = field(default_factory=dict)
    filters: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {'id': self.id, 'title': self.title,
                'chart_type': self.chart_type.value,
                'position': self.position.to_dict(),
                'config': self.config, 'filters': self.filters}

    @classmethod
    def from_dict(cls, data: Dict) -> 'DashboardItem':
        return cls(id=data['id'], title=data['title'],
                   chart_type=ChartType(data['chart_type']),
                   position=GridPosition.from_dict(data['position']),
                   config=data.get('config', {}), filters=data.get('filters', []))


class DashboardLayout:
    """대시보드 레이아웃 (legacy)."""

    def __init__(self, rows: int = 2, cols: int = 2, name: str = "Untitled Dashboard"):
        self.rows = rows
        self.cols = cols
        self.name = name
        self.items: List[DashboardItem] = []
        self.shared_filters: List[Dict] = []

    def add_item(self, item: DashboardItem):
        self.items.append(item)

    def remove_item(self, item_id: str):
        self.items = [i for i in self.items if i.id != item_id]

    def get_item(self, item_id: str) -> Optional[DashboardItem]:
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def check_collision(self, position: GridPosition, exclude_id: Optional[str] = None) -> bool:
        for item in self.items:
            if exclude_id and item.id == exclude_id:
                continue
            if item.position.overlaps(position):
                return True
        return False

    def find_empty_position(self, row_span: int = 1, col_span: int = 1) -> Optional[GridPosition]:
        for row in range(self.rows - row_span + 1):
            for col in range(self.cols - col_span + 1):
                pos = GridPosition(row, col, row_span, col_span)
                if not self.check_collision(pos):
                    return pos
        return None

    def resize(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols

    def add_shared_filter(self, column: str, op: str, value: Any):
        self.shared_filters.append({'column': column, 'op': op, 'value': value})

    def remove_shared_filter(self, index: int):
        if 0 <= index < len(self.shared_filters):
            self.shared_filters.pop(index)

    def clear_shared_filters(self):
        self.shared_filters.clear()

    def get_filters_for_item(self, item_id: str) -> List[Dict]:
        item = self.get_item(item_id)
        if not item:
            return []
        return self.shared_filters + item.filters

    def to_dict(self) -> Dict:
        return {'name': self.name, 'rows': self.rows, 'cols': self.cols,
                'items': [item.to_dict() for item in self.items],
                'shared_filters': self.shared_filters}

    @classmethod
    def from_dict(cls, data: Dict) -> 'DashboardLayout':
        layout = cls(rows=data['rows'], cols=data['cols'],
                     name=data.get('name', 'Untitled Dashboard'))
        for item_data in data.get('items', []):
            layout.add_item(DashboardItem.from_dict(item_data))
        layout.shared_filters = data.get('shared_filters', [])
        return layout


@dataclass
class Dashboard:
    """대시보드 (legacy)."""
    id: str
    name: str
    layout: DashboardLayout

    @classmethod
    def create(cls, name: str, rows: int = 2, cols: int = 2) -> 'Dashboard':
        return cls(id=str(uuid.uuid4()), name=name,
                   layout=DashboardLayout(rows=rows, cols=cols, name=name))


class DashboardManager:
    """대시보드 매니저 (legacy)."""

    def __init__(self):
        self._dashboards: Dict[str, Dashboard] = {}
        self._current_id: Optional[str] = None

    @property
    def current(self) -> Optional[Dashboard]:
        if self._current_id:
            return self._dashboards.get(self._current_id)
        return None

    def create_dashboard(self, name: str, rows: int = 2, cols: int = 2) -> Dashboard:
        dashboard = Dashboard.create(name, rows, cols)
        self._dashboards[dashboard.id] = dashboard
        if self._current_id is None:
            self._current_id = dashboard.id
        return dashboard

    def delete_dashboard(self, dashboard_id: str):
        if dashboard_id in self._dashboards:
            del self._dashboards[dashboard_id]
            if self._current_id == dashboard_id:
                self._current_id = next(iter(self._dashboards.keys()), None)

    def list_dashboards(self) -> List[Dashboard]:
        return list(self._dashboards.values())

    def switch_to(self, dashboard_id: str):
        if dashboard_id in self._dashboards:
            self._current_id = dashboard_id

    def get_dashboard(self, dashboard_id: str) -> Optional[Dashboard]:
        return self._dashboards.get(dashboard_id)
