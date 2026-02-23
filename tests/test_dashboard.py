"""
Tests for Dashboard Mode
"""

import pytest

import sys
import os

# Add project root to path
project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from data_graph_studio.core.state import ChartType
from data_graph_studio.ui import dashboard

DashboardLayout = dashboard.DashboardLayout
DashboardItem = dashboard.DashboardItem
DashboardManager = dashboard.DashboardManager
GridPosition = dashboard.GridPosition


class TestGridPosition:
    """그리드 위치 테스트"""
    
    def test_grid_position_creation(self):
        """위치 생성"""
        pos = GridPosition(row=0, col=0, row_span=1, col_span=1)
        
        assert pos.row == 0
        assert pos.col == 0
        assert pos.row_span == 1
        assert pos.col_span == 1
    
    def test_grid_position_span(self):
        """span 설정"""
        pos = GridPosition(row=1, col=2, row_span=2, col_span=3)
        
        assert pos.row_span == 2
        assert pos.col_span == 3
    
    def test_grid_position_equality(self):
        """위치 비교"""
        pos1 = GridPosition(0, 0, 1, 1)
        pos2 = GridPosition(0, 0, 1, 1)
        pos3 = GridPosition(0, 1, 1, 1)
        
        assert pos1 == pos2
        assert pos1 != pos3


class TestDashboardItem:
    """대시보드 아이템 테스트"""
    
    def test_item_creation(self):
        """아이템 생성"""
        item = DashboardItem(
            id="chart1",
            title="Sales Chart",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 1, 1)
        )
        
        assert item.id == "chart1"
        assert item.title == "Sales Chart"
        assert item.chart_type == ChartType.LINE
    
    def test_item_config(self):
        """아이템 설정"""
        item = DashboardItem(
            id="chart1",
            title="Chart",
            chart_type=ChartType.BAR,
            position=GridPosition(0, 0, 1, 1),
            config={
                'x_column': 'Date',
                'y_columns': ['Sales', 'Revenue'],
            }
        )
        
        assert item.config['x_column'] == 'Date'
        assert 'Sales' in item.config['y_columns']
    
    def test_item_update_position(self):
        """위치 업데이트"""
        item = DashboardItem(
            id="chart1",
            title="Chart",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 1, 1)
        )
        
        item.position = GridPosition(1, 2, 2, 2)
        
        assert item.position.row == 1
        assert item.position.col == 2


class TestDashboardLayout:
    """대시보드 레이아웃 테스트"""
    
    @pytest.fixture
    def layout(self):
        return DashboardLayout(rows=3, cols=4)
    
    def test_layout_creation(self, layout):
        """레이아웃 생성"""
        assert layout.rows == 3
        assert layout.cols == 4
    
    def test_add_item(self, layout):
        """아이템 추가"""
        item = DashboardItem(
            id="chart1",
            title="Chart",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 1, 1)
        )
        
        layout.add_item(item)
        
        assert len(layout.items) == 1
        assert layout.get_item("chart1") is not None
    
    def test_remove_item(self, layout):
        """아이템 제거"""
        item = DashboardItem(
            id="chart1",
            title="Chart",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 1, 1)
        )
        
        layout.add_item(item)
        layout.remove_item("chart1")
        
        assert len(layout.items) == 0
    
    def test_multiple_items(self, layout):
        """여러 아이템"""
        for i in range(4):
            item = DashboardItem(
                id=f"chart{i}",
                title=f"Chart {i}",
                chart_type=ChartType.LINE,
                position=GridPosition(i // 2, i % 2, 1, 1)
            )
            layout.add_item(item)
        
        assert len(layout.items) == 4
    
    def test_collision_detection(self, layout):
        """충돌 감지"""
        item1 = DashboardItem(
            id="chart1", title="Chart 1",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 2, 2)
        )
        layout.add_item(item1)
        
        # 겹치는 위치
        overlapping = layout.check_collision(GridPosition(1, 1, 1, 1))
        assert overlapping is True
        
        # 겹치지 않는 위치
        not_overlapping = layout.check_collision(GridPosition(2, 2, 1, 1))
        assert not_overlapping is False
    
    def test_find_empty_position(self, layout):
        """빈 위치 찾기"""
        item = DashboardItem(
            id="chart1", title="Chart",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 1, 1)
        )
        layout.add_item(item)
        
        empty = layout.find_empty_position(1, 1)
        
        assert empty is not None
        assert empty != GridPosition(0, 0, 1, 1)


class TestDashboardManager:
    """대시보드 매니저 테스트"""
    
    @pytest.fixture
    def manager(self):
        return DashboardManager()
    
    def test_create_dashboard(self, manager):
        """대시보드 생성"""
        dashboard = manager.create_dashboard("My Dashboard", rows=2, cols=2)
        
        assert dashboard.name == "My Dashboard"
        assert dashboard.layout.rows == 2
        assert dashboard.layout.cols == 2
    
    def test_list_dashboards(self, manager):
        """대시보드 목록"""
        manager.create_dashboard("Dashboard 1")
        manager.create_dashboard("Dashboard 2")
        
        dashboards = manager.list_dashboards()
        
        assert len(dashboards) == 2
    
    def test_delete_dashboard(self, manager):
        """대시보드 삭제"""
        dashboard = manager.create_dashboard("To Delete")
        manager.delete_dashboard(dashboard.id)
        
        assert len(manager.list_dashboards()) == 0
    
    def test_switch_dashboard(self, manager):
        """대시보드 전환"""
        d1 = manager.create_dashboard("Dashboard 1")
        d2 = manager.create_dashboard("Dashboard 2")
        
        manager.switch_to(d1.id)
        assert manager.current.id == d1.id
        
        manager.switch_to(d2.id)
        assert manager.current.id == d2.id


class TestSharedFilter:
    """공유 필터 테스트"""
    
    @pytest.fixture
    def layout(self):
        return DashboardLayout(rows=2, cols=2)
    
    def test_add_shared_filter(self, layout):
        """공유 필터 추가"""
        layout.add_shared_filter('Date', 'ge', '2024-01-01')
        
        assert len(layout.shared_filters) == 1
    
    def test_shared_filter_applies_to_all(self, layout):
        """공유 필터가 모든 아이템에 적용"""
        for i in range(2):
            item = DashboardItem(
                id=f"chart{i}",
                title=f"Chart {i}",
                chart_type=ChartType.LINE,
                position=GridPosition(0, i, 1, 1)
            )
            layout.add_item(item)
        
        layout.add_shared_filter('Category', 'eq', 'A')
        
        filters = layout.get_filters_for_item("chart0")
        assert any(f['column'] == 'Category' for f in filters)
        
        filters = layout.get_filters_for_item("chart1")
        assert any(f['column'] == 'Category' for f in filters)
    
    def test_item_local_filter(self, layout):
        """아이템별 로컬 필터"""
        item = DashboardItem(
            id="chart1",
            title="Chart",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 1, 1),
            filters=[{'column': 'Region', 'op': 'eq', 'value': 'North'}]
        )
        layout.add_item(item)
        
        layout.add_shared_filter('Year', 'eq', 2024)
        
        filters = layout.get_filters_for_item("chart1")
        
        # 공유 필터 + 로컬 필터
        assert len(filters) == 2
        assert any(f['column'] == 'Year' for f in filters)
        assert any(f['column'] == 'Region' for f in filters)
    
    def test_remove_shared_filter(self, layout):
        """공유 필터 제거"""
        layout.add_shared_filter('Date', 'ge', '2024-01-01')
        layout.add_shared_filter('Category', 'eq', 'A')
        
        layout.remove_shared_filter(0)
        
        assert len(layout.shared_filters) == 1
        assert layout.shared_filters[0]['column'] == 'Category'
    
    def test_clear_shared_filters(self, layout):
        """공유 필터 전체 클리어"""
        layout.add_shared_filter('A', 'eq', 1)
        layout.add_shared_filter('B', 'eq', 2)
        
        layout.clear_shared_filters()
        
        assert len(layout.shared_filters) == 0


class TestDashboardResizing:
    """대시보드 리사이징 테스트"""
    
    @pytest.fixture
    def layout(self):
        return DashboardLayout(rows=2, cols=2)
    
    def test_resize_grid(self, layout):
        """그리드 크기 변경"""
        layout.resize(rows=4, cols=4)
        
        assert layout.rows == 4
        assert layout.cols == 4
    
    def test_resize_preserves_items(self, layout):
        """리사이징 시 아이템 유지"""
        item = DashboardItem(
            id="chart1", title="Chart",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 1, 1)
        )
        layout.add_item(item)
        
        layout.resize(rows=4, cols=4)
        
        assert len(layout.items) == 1
        assert layout.get_item("chart1") is not None


class TestDashboardSerialization:
    """대시보드 직렬화 테스트"""
    
    @pytest.fixture
    def layout(self):
        layout = DashboardLayout(rows=2, cols=3, name="Test Dashboard")
        layout.add_item(DashboardItem(
            id="chart1", title="Sales",
            chart_type=ChartType.LINE,
            position=GridPosition(0, 0, 1, 2),
            config={'x_column': 'Date'}
        ))
        layout.add_shared_filter('Category', 'eq', 'Electronics')
        return layout
    
    def test_to_dict(self, layout):
        """딕셔너리로 변환"""
        data = layout.to_dict()
        
        assert data['name'] == "Test Dashboard"
        assert data['rows'] == 2
        assert data['cols'] == 3
        assert len(data['items']) == 1
        assert len(data['shared_filters']) == 1
    
    def test_from_dict(self, layout):
        """딕셔너리에서 복원"""
        data = layout.to_dict()
        
        restored = DashboardLayout.from_dict(data)
        
        assert restored.name == layout.name
        assert restored.rows == layout.rows
        assert restored.cols == layout.cols
        assert len(restored.items) == len(layout.items)
        assert len(restored.shared_filters) == len(layout.shared_filters)
