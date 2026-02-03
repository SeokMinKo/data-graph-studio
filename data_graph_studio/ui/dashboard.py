"""
Dashboard Mode - Multiple graphs layout
"""

import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QMenu, QSizePolicy, QScrollArea
)
from PySide6.QtCore import Qt, Signal

try:
    from ..core.state import ChartType
except ImportError:
    from core.state import ChartType


@dataclass
class GridPosition:
    """그리드 위치"""
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
        """겹침 여부"""
        # 각 위치의 범위
        r1_start, r1_end = self.row, self.row + self.row_span
        c1_start, c1_end = self.col, self.col + self.col_span
        r2_start, r2_end = other.row, other.row + other.row_span
        c2_start, c2_end = other.col, other.col + other.col_span
        
        # 겹침 체크
        row_overlap = r1_start < r2_end and r2_start < r1_end
        col_overlap = c1_start < c2_end and c2_start < c1_end
        
        return row_overlap and col_overlap
    
    def to_dict(self) -> Dict:
        return {
            'row': self.row,
            'col': self.col,
            'row_span': self.row_span,
            'col_span': self.col_span,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GridPosition':
        return cls(
            row=data['row'],
            col=data['col'],
            row_span=data.get('row_span', 1),
            col_span=data.get('col_span', 1),
        )


@dataclass
class DashboardItem:
    """대시보드 아이템"""
    id: str
    title: str
    chart_type: ChartType
    position: GridPosition
    config: Dict[str, Any] = field(default_factory=dict)
    filters: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'chart_type': self.chart_type.value,
            'position': self.position.to_dict(),
            'config': self.config,
            'filters': self.filters,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DashboardItem':
        return cls(
            id=data['id'],
            title=data['title'],
            chart_type=ChartType(data['chart_type']),
            position=GridPosition.from_dict(data['position']),
            config=data.get('config', {}),
            filters=data.get('filters', []),
        )


class DashboardLayout:
    """대시보드 레이아웃"""
    
    def __init__(
        self,
        rows: int = 2,
        cols: int = 2,
        name: str = "Untitled Dashboard"
    ):
        self.rows = rows
        self.cols = cols
        self.name = name
        self.items: List[DashboardItem] = []
        self.shared_filters: List[Dict] = []
    
    def add_item(self, item: DashboardItem):
        """아이템 추가"""
        self.items.append(item)
    
    def remove_item(self, item_id: str):
        """아이템 제거"""
        self.items = [i for i in self.items if i.id != item_id]
    
    def get_item(self, item_id: str) -> Optional[DashboardItem]:
        """아이템 조회"""
        for item in self.items:
            if item.id == item_id:
                return item
        return None
    
    def check_collision(
        self,
        position: GridPosition,
        exclude_id: Optional[str] = None
    ) -> bool:
        """충돌 체크"""
        for item in self.items:
            if exclude_id and item.id == exclude_id:
                continue
            if item.position.overlaps(position):
                return True
        return False
    
    def find_empty_position(
        self,
        row_span: int = 1,
        col_span: int = 1
    ) -> Optional[GridPosition]:
        """빈 위치 찾기"""
        for row in range(self.rows - row_span + 1):
            for col in range(self.cols - col_span + 1):
                pos = GridPosition(row, col, row_span, col_span)
                if not self.check_collision(pos):
                    return pos
        return None
    
    def resize(self, rows: int, cols: int):
        """그리드 크기 변경"""
        self.rows = rows
        self.cols = cols
    
    # ==================== Shared Filters ====================
    
    def add_shared_filter(self, column: str, op: str, value: Any):
        """공유 필터 추가"""
        self.shared_filters.append({
            'column': column,
            'op': op,
            'value': value,
        })
    
    def remove_shared_filter(self, index: int):
        """공유 필터 제거"""
        if 0 <= index < len(self.shared_filters):
            self.shared_filters.pop(index)
    
    def clear_shared_filters(self):
        """공유 필터 전체 클리어"""
        self.shared_filters.clear()
    
    def get_filters_for_item(self, item_id: str) -> List[Dict]:
        """아이템에 적용되는 필터 (공유 + 로컬)"""
        item = self.get_item(item_id)
        if not item:
            return []
        
        # 공유 필터 + 로컬 필터
        return self.shared_filters + item.filters
    
    # ==================== Serialization ====================
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            'name': self.name,
            'rows': self.rows,
            'cols': self.cols,
            'items': [item.to_dict() for item in self.items],
            'shared_filters': self.shared_filters,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DashboardLayout':
        """딕셔너리에서 복원"""
        layout = cls(
            rows=data['rows'],
            cols=data['cols'],
            name=data.get('name', 'Untitled Dashboard'),
        )
        
        for item_data in data.get('items', []):
            layout.add_item(DashboardItem.from_dict(item_data))
        
        layout.shared_filters = data.get('shared_filters', [])
        
        return layout


@dataclass
class Dashboard:
    """대시보드"""
    id: str
    name: str
    layout: DashboardLayout
    
    @classmethod
    def create(cls, name: str, rows: int = 2, cols: int = 2) -> 'Dashboard':
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            layout=DashboardLayout(rows=rows, cols=cols, name=name),
        )


class DashboardManager:
    """대시보드 매니저"""
    
    def __init__(self):
        self._dashboards: Dict[str, Dashboard] = {}
        self._current_id: Optional[str] = None
    
    @property
    def current(self) -> Optional[Dashboard]:
        """현재 대시보드"""
        if self._current_id:
            return self._dashboards.get(self._current_id)
        return None
    
    def create_dashboard(
        self,
        name: str,
        rows: int = 2,
        cols: int = 2
    ) -> Dashboard:
        """대시보드 생성"""
        dashboard = Dashboard.create(name, rows, cols)
        self._dashboards[dashboard.id] = dashboard
        
        if self._current_id is None:
            self._current_id = dashboard.id
        
        return dashboard
    
    def delete_dashboard(self, dashboard_id: str):
        """대시보드 삭제"""
        if dashboard_id in self._dashboards:
            del self._dashboards[dashboard_id]
            
            if self._current_id == dashboard_id:
                self._current_id = next(iter(self._dashboards.keys()), None)
    
    def list_dashboards(self) -> List[Dashboard]:
        """대시보드 목록"""
        return list(self._dashboards.values())
    
    def switch_to(self, dashboard_id: str):
        """대시보드 전환"""
        if dashboard_id in self._dashboards:
            self._current_id = dashboard_id
    
    def get_dashboard(self, dashboard_id: str) -> Optional[Dashboard]:
        """대시보드 조회"""
        return self._dashboards.get(dashboard_id)


class DashboardItemWidget(QFrame):
    """대시보드 아이템 위젯"""
    
    remove_requested = Signal(str)  # item_id
    
    def __init__(self, item: DashboardItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._setup_ui()
    
    def _setup_ui(self):
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # 헤더
        header = QHBoxLayout()
        
        title = QLabel(self.item.title)
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title)
        
        header.addStretch()
        
        # 메뉴 버튼
        menu_btn = QPushButton("⋮")
        menu_btn.setFixedWidth(30)
        menu_btn.setToolTip("Dashboard item options")
        menu_btn.clicked.connect(self._show_menu)
        header.addWidget(menu_btn)
        
        layout.addLayout(header)
        
        # 차트 영역 (플레이스홀더)
        chart_area = QFrame()
        chart_area.setStyleSheet("background-color: #f0f0f0;")
        chart_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(chart_area)
    
    def _show_menu(self):
        menu = QMenu(self)
        menu.addAction("Edit", self._on_edit)
        menu.addAction("Remove", self._on_remove)
        menu.exec(self.mapToGlobal(self.rect().bottomRight()))
    
    def _on_edit(self):
        # TODO: 편집 다이얼로그
        pass
    
    def _on_remove(self):
        self.remove_requested.emit(self.item.id)


class DashboardWidget(QWidget):
    """대시보드 위젯"""
    
    def __init__(self, layout: DashboardLayout, parent=None):
        super().__init__(parent)
        self.dashboard_layout = layout
        self._item_widgets: Dict[str, DashboardItemWidget] = {}
        
        self._setup_ui()
        self._populate()
    
    def _setup_ui(self):
        self._grid = QGridLayout(self)
        self._grid.setSpacing(8)
    
    def _populate(self):
        """레이아웃에서 위젯 생성"""
        for item in self.dashboard_layout.items:
            self._add_item_widget(item)
    
    def _add_item_widget(self, item: DashboardItem):
        """아이템 위젯 추가"""
        widget = DashboardItemWidget(item)
        widget.remove_requested.connect(self._on_remove_item)
        
        self._grid.addWidget(
            widget,
            item.position.row,
            item.position.col,
            item.position.row_span,
            item.position.col_span,
        )
        
        self._item_widgets[item.id] = widget
    
    def _on_remove_item(self, item_id: str):
        """아이템 제거"""
        if item_id in self._item_widgets:
            widget = self._item_widgets.pop(item_id)
            self._grid.removeWidget(widget)
            widget.deleteLater()
            
            self.dashboard_layout.remove_item(item_id)
    
    def refresh(self):
        """새로고침"""
        # 기존 위젯 제거
        for widget in self._item_widgets.values():
            self._grid.removeWidget(widget)
            widget.deleteLater()
        
        self._item_widgets.clear()
        
        # 다시 생성
        self._populate()
