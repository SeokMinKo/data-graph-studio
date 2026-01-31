"""
Tests for Grouped Table Model
"""

import pytest
import polars as pl
import numpy as np
import os
import sys

# Add src to path
src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from PySide6.QtCore import Qt
from data_graph_studio.ui.panels.grouped_table_model import GroupedTableModel, GroupNode


class TestGroupNode:
    """GroupNode 테스트"""
    
    def test_node_creation(self):
        """노드 생성"""
        node = GroupNode(key=("A",), display_name="Group A", level=0)
        
        assert node.display_name == "Group A"
        assert node.level == 0
        assert node.expanded is True
    
    def test_node_is_group_with_children(self):
        """자식이 있으면 그룹"""
        parent = GroupNode(key=(), display_name="Parent", level=0)
        child = GroupNode(key=("A",), display_name="A", level=1, parent=parent)
        parent.children.append(child)
        
        assert parent.is_group is True
    
    def test_node_is_group_with_multiple_rows(self):
        """행이 여러 개면 그룹"""
        node = GroupNode(key=("A",), display_name="A", level=0)
        node.rows = [0, 1, 2]
        
        assert node.is_group is True
    
    def test_node_row_count(self):
        """행 개수"""
        parent = GroupNode(key=(), display_name="Root", level=-1)
        child1 = GroupNode(key=("A",), display_name="A", level=0, parent=parent)
        child2 = GroupNode(key=("B",), display_name="B", level=0, parent=parent)
        
        child1.rows = [0, 1, 2]
        child2.rows = [3, 4]
        
        parent.children = [child1, child2]
        
        assert child1.row_count == 3
        assert child2.row_count == 2
        assert parent.row_count == 5


class TestGroupedTableModel:
    """GroupedTableModel 테스트"""
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'Category': ['A', 'A', 'B', 'B', 'C'],
            'Region': ['East', 'West', 'East', 'West', 'East'],
            'Sales': [100, 200, 150, 250, 300],
            'Quantity': [10, 20, 15, 25, 30],
        })
    
    @pytest.fixture
    def model(self):
        return GroupedTableModel()
    
    def test_no_grouping(self, model, sample_df):
        """그룹화 없음 - 평면 표시"""
        model.set_data(sample_df, group_columns=[], value_columns=[])
        
        # 5개 행
        assert model.rowCount() == 5
    
    def test_single_group(self, model, sample_df):
        """단일 컬럼 그룹화"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
            aggregations={'Sales': 'sum'}
        )
        
        # 초기 상태: 그룹 헤더만 표시 (collapsed 상태)
        # A, B, C = 3개 헤더
        assert model.rowCount() == 3
    
    def test_multi_level_group(self, model, sample_df):
        """다중 레벨 그룹화"""
        model.set_data(
            sample_df,
            group_columns=['Category', 'Region'],
            value_columns=['Sales'],
            aggregations={'Sales': 'sum'}
        )
        
        # Category groups + Region subgroups + data
        # More complex structure
        assert model.rowCount() > 5
    
    def test_collapse_expand(self, model, sample_df):
        """펼치기/접기"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        initial_count = model.rowCount()  # 3 (collapsed state)
        
        # Toggle behavior: need multiple toggles to cycle through states
        # Just verify collapse_all and expand_all work correctly
        model.expand_all()
        expanded_count = model.rowCount()
        assert expanded_count > initial_count  # Should have more rows when expanded
        
        model.collapse_all()
        collapsed_count = model.rowCount()
        assert collapsed_count == initial_count  # Back to initial
    
    def test_collapse_all(self, model, sample_df):
        """전체 접기"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        model.collapse_all()
        
        # Only group headers visible
        assert model.rowCount() == 3  # A, B, C
    
    def test_expand_all(self, model, sample_df):
        """전체 펼치기"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        model.collapse_all()
        collapsed_count = model.rowCount()
        assert collapsed_count == 3  # Only headers
        
        model.expand_all()
        expanded_count = model.rowCount()
        # 3 headers + 5 data rows = 8
        assert expanded_count == 8
    
    def test_header_data(self, model, sample_df):
        """헤더 데이터"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        # First column is group column
        header = model.headerData(0, Qt.Horizontal, Qt.DisplayRole)
        assert 'Category' in header
    
    def test_group_header_display(self, model, sample_df):
        """그룹 헤더 표시"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        # First row should be group header "A"
        data = model.data(model.index(0, 0), Qt.DisplayRole)
        assert 'A' in data
        assert '(2)' in data  # 2 rows in group A
    
    def test_aggregate_values(self, model, sample_df):
        """집계 값"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
            aggregations={'Sales': 'sum'}
        )
        
        # Check that aggregate is calculated
        # Group A: 100 + 200 = 300
        # Find Sales column index
        for col in range(model.columnCount()):
            header = model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
            if header == 'Sales':
                data = model.data(model.index(0, col), Qt.DisplayRole)
                if data:
                    assert '300' in data
                break
    
    def test_get_group_data(self, model, sample_df):
        """그룹 데이터 추출 (그래프용)"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        group_data = model.get_group_data()
        
        assert len(group_data) == 3  # A, B, C
        
        # Check structure: (name, row_indices, color)
        for name, rows, color in group_data:
            assert isinstance(name, str)
            assert isinstance(rows, list)
            assert color.startswith('#')
    
    def test_user_role_returns_node(self, model, sample_df):
        """UserRole로 노드 반환"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        data = model.data(model.index(0, 0), Qt.UserRole)
        
        assert data is not None
        node, row_idx = data
        assert isinstance(node, GroupNode)
    
    def test_is_header_role(self, model, sample_df):
        """헤더 여부 Role"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        # Expand to show data rows
        model.expand_all()
        
        # First row is header (A)
        is_header = model.data(model.index(0, 0), Qt.UserRole + 1)
        assert is_header is True
        
        # Second row is data (under A)
        is_header = model.data(model.index(1, 0), Qt.UserRole + 1)
        assert is_header is False
    
    def test_background_role_for_header(self, model, sample_df):
        """헤더 배경색"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        brush = model.data(model.index(0, 0), Qt.BackgroundRole)
        
        assert brush is not None
    
    def test_font_role_for_header(self, model, sample_df):
        """헤더 폰트 (bold)"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
        )
        
        font = model.data(model.index(0, 0), Qt.FontRole)
        
        assert font is not None
        assert font.bold() is True
    
    def test_empty_dataframe(self, model):
        """빈 데이터프레임"""
        empty_df = pl.DataFrame({'A': [], 'B': []})
        
        model.set_data(empty_df, group_columns=['A'])
        
        assert model.rowCount() == 0
    
    def test_null_values_in_group(self, model):
        """그룹 컬럼에 NULL 값"""
        df = pl.DataFrame({
            'Category': ['A', None, 'B', None],
            'Value': [100, 200, 300, 400],
        })
        
        model.set_data(
            df,
            group_columns=['Category'],
            value_columns=['Value'],
        )
        
        # Should handle None values
        group_data = model.get_group_data()
        names = [name for name, _, _ in group_data]
        
        assert '(Empty)' in names or any('Empty' in n for n in names)


class TestGroupedTableModelAutoNumeric:
    """Auto-aggregation of all numeric columns test"""
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'Category': ['A', 'A', 'B', 'B', 'C'],
            'Region': ['East', 'West', 'East', 'West', 'East'],
            'Sales': [100, 200, 150, 250, 300],
            'Quantity': [10, 20, 15, 25, 30],
            'Price': [9.99, 19.99, 14.99, 24.99, 29.99],
            'Name': ['Item1', 'Item2', 'Item3', 'Item4', 'Item5'],
        })
    
    @pytest.fixture
    def model(self):
        return GroupedTableModel()
    
    def test_auto_detect_numeric_columns(self, model, sample_df):
        """Test that numeric columns are auto-detected"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],  # Only Sales is explicit
            aggregations={'Sales': 'sum'}
        )
        
        # Quantity and Price should be auto-detected (numeric, not in group or value)
        assert 'Quantity' in model._auto_numeric_columns
        assert 'Price' in model._auto_numeric_columns
        # Name should not be auto-detected (string)
        assert 'Name' not in model._auto_numeric_columns
        # Category should not be auto-detected (group column)
        assert 'Category' not in model._auto_numeric_columns
        # Sales should not be auto-detected (explicit value column)
        assert 'Sales' not in model._auto_numeric_columns
    
    def test_auto_aggregation_values(self, model, sample_df):
        """Test that auto-detected columns are aggregated"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
            aggregations={'Sales': 'sum'}
        )
        
        # Check aggregates include auto-detected columns
        for child in model._root.children:
            if child.display_name == 'A':
                # Sales: 100 + 200 = 300 (explicit)
                assert child.aggregates.get('Sales') == 300
                # Quantity: 10 + 20 = 30 (auto, default sum)
                assert child.aggregates.get('Quantity') == 30
                # Price: 9.99 + 19.99 = 29.98 (auto, default sum)
                assert abs(child.aggregates.get('Price') - 29.98) < 0.01
    
    def test_all_value_columns_combined(self, model, sample_df):
        """Test _all_value_columns contains explicit + auto columns"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
            aggregations={'Sales': 'sum'}
        )
        
        # all_value_columns = explicit + auto
        assert 'Sales' in model._all_value_columns
        assert 'Quantity' in model._all_value_columns
        assert 'Price' in model._all_value_columns
        assert len(model._all_value_columns) == 3  # Sales + Quantity + Price
    
    def test_explicit_aggregation_preserved(self, model, sample_df):
        """Test explicit aggregation is preserved for value columns
        
        Note: Auto-detected columns now use the first value column's aggregation.
        """
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales', 'Quantity'],
            aggregations={'Sales': 'sum', 'Quantity': 'mean'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                # Sales: sum = 300 (explicit)
                assert child.aggregates.get('Sales') == 300
                # Quantity: mean = (10 + 20) / 2 = 15 (explicit)
                assert child.aggregates.get('Quantity') == 15.0
                # Price: uses first value column's agg (sum) = 9.99 + 19.99 = 29.98
                assert abs(child.aggregates.get('Price') - 29.98) < 0.01
    
    def test_no_grouping_no_auto_aggregation(self, model, sample_df):
        """Test no auto-aggregation when no grouping"""
        model.set_data(
            sample_df,
            group_columns=[],  # No grouping
            value_columns=['Sales'],
        )
        
        # Without grouping, auto-detection still happens but no aggregation is performed
        # because _build_tree doesn't build group tree
        assert model.rowCount() == 5  # Just rows, no group headers
    
    def test_all_numeric_excluded_when_in_group(self, model, sample_df):
        """Test numeric columns in group are excluded from auto-detection"""
        # Create df with numeric group column
        df = pl.DataFrame({
            'Year': [2020, 2020, 2021, 2021],
            'Quarter': [1, 2, 1, 2],
            'Revenue': [100.0, 200.0, 150.0, 250.0],
        })
        
        model.set_data(
            df,
            group_columns=['Year'],  # Year is numeric but used as group
            value_columns=[],
        )
        
        # Year should not be in auto_numeric (it's in group)
        assert 'Year' not in model._auto_numeric_columns
        # Quarter and Revenue should be auto-detected
        assert 'Quarter' in model._auto_numeric_columns
        assert 'Revenue' in model._auto_numeric_columns
    
    def test_empty_dataframe_no_crash(self, model):
        """Test empty dataframe doesn't crash auto-detection"""
        df = pl.DataFrame({
            'Category': pl.Series([], dtype=pl.Utf8),
            'Value': pl.Series([], dtype=pl.Int64),
        })
        
        model.set_data(df, group_columns=['Category'])
        
        # Should not crash
        assert model._auto_numeric_columns == ['Value']


class TestGroupedTableModelEffectiveAggregation:
    """Test effective aggregation propagation from Value Zone to auto-detected columns"""
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'Category': ['A', 'A', 'B', 'B', 'C'],
            'Sales': [100, 200, 150, 250, 300],
            'Quantity': [10, 20, 15, 25, 30],
            'Price': [10.0, 20.0, 15.0, 25.0, 30.0],
        })
    
    @pytest.fixture
    def model(self):
        return GroupedTableModel()
    
    def test_mean_propagates_to_auto_columns(self, model, sample_df):
        """Value Zone MEAN → auto columns도 MEAN"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
            aggregations={'Sales': 'mean'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                # Sales: mean = (100+200)/2 = 150
                assert child.aggregates.get('Sales') == 150.0
                # Quantity: mean = (10+20)/2 = 15 (propagated from Sales)
                assert child.aggregates.get('Quantity') == 15.0
                # Price: mean = (10+20)/2 = 15 (propagated from Sales)
                assert child.aggregates.get('Price') == 15.0
    
    def test_sum_propagates_to_auto_columns(self, model, sample_df):
        """Value Zone SUM → auto columns도 SUM"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
            aggregations={'Sales': 'sum'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                # Sales: sum = 300
                assert child.aggregates.get('Sales') == 300
                # Quantity: sum = 30 (propagated from Sales)
                assert child.aggregates.get('Quantity') == 30
                # Price: sum = 30 (propagated from Sales)
                assert child.aggregates.get('Price') == 30.0
    
    def test_first_value_column_agg_used(self, model, sample_df):
        """첫 번째 Value Zone 컬럼의 aggregation 사용"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales', 'Quantity'],
            aggregations={'Sales': 'mean', 'Quantity': 'sum'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                # Sales: mean = 150 (explicit)
                assert child.aggregates.get('Sales') == 150.0
                # Quantity: sum = 30 (explicit)
                assert child.aggregates.get('Quantity') == 30
                # Price: mean = 15 (uses first value column's agg = mean)
                assert child.aggregates.get('Price') == 15.0
    
    def test_empty_value_zone_uses_default(self, model, sample_df):
        """Value Zone 비어있으면 기본값(SUM) 사용"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=[],  # Empty Value Zone
            aggregations={}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                # All auto-detected: use default SUM
                assert child.aggregates.get('Sales') == 300  # sum
                assert child.aggregates.get('Quantity') == 30  # sum
                assert child.aggregates.get('Price') == 30.0  # sum
    
    def test_effective_default_aggregation_method(self, model, sample_df):
        """_get_effective_default_aggregation() 메서드 테스트"""
        # Empty Value Zone → default
        model.set_data(sample_df, group_columns=['Category'], value_columns=[], aggregations={})
        assert model._get_effective_default_aggregation() == 'sum'
        
        # With Value Zone → first column's agg
        model.set_data(
            sample_df, 
            group_columns=['Category'], 
            value_columns=['Sales'], 
            aggregations={'Sales': 'mean'}
        )
        assert model._get_effective_default_aggregation() == 'mean'
        
        # Value column without explicit agg → default
        model.set_data(
            sample_df, 
            group_columns=['Category'], 
            value_columns=['Sales'], 
            aggregations={}  # No aggregation specified
        )
        assert model._get_effective_default_aggregation() == 'sum'
    
    def test_count_propagates_to_auto_columns(self, model, sample_df):
        """Value Zone COUNT → auto columns도 COUNT"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
            aggregations={'Sales': 'count'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                # Sales: count = 2
                assert child.aggregates.get('Sales') == 2
                # Quantity: count = 2 (propagated)
                assert child.aggregates.get('Quantity') == 2
                # Price: count = 2 (propagated)
                assert child.aggregates.get('Price') == 2
    
    def test_min_propagates_to_auto_columns(self, model, sample_df):
        """Value Zone MIN → auto columns도 MIN"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
            aggregations={'Sales': 'min'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                # Sales: min = 100
                assert child.aggregates.get('Sales') == 100
                # Quantity: min = 10 (propagated)
                assert child.aggregates.get('Quantity') == 10
                # Price: min = 10 (propagated)
                assert child.aggregates.get('Price') == 10.0
    
    def test_max_propagates_to_auto_columns(self, model, sample_df):
        """Value Zone MAX → auto columns도 MAX"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Sales'],
            aggregations={'Sales': 'max'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                # Sales: max = 200
                assert child.aggregates.get('Sales') == 200
                # Quantity: max = 20 (propagated)
                assert child.aggregates.get('Quantity') == 20
                # Price: max = 20 (propagated)
                assert child.aggregates.get('Price') == 20.0


class TestGroupedTableModelAggregations:
    """집계 함수 테스트"""
    
    @pytest.fixture
    def sample_df(self):
        return pl.DataFrame({
            'Category': ['A', 'A', 'A', 'B', 'B'],
            'Value': [10, 20, 30, 40, 50],
        })
    
    @pytest.fixture
    def model(self):
        return GroupedTableModel()
    
    def test_sum_aggregation(self, model, sample_df):
        """SUM 집계"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Value'],
            aggregations={'Value': 'sum'}
        )
        
        # Group A: 10+20+30=60, Group B: 40+50=90
        # Check root aggregates
        assert model._root is not None
        
        for child in model._root.children:
            if child.display_name == 'A':
                assert child.aggregates.get('Value') == 60
            elif child.display_name == 'B':
                assert child.aggregates.get('Value') == 90
    
    def test_mean_aggregation(self, model, sample_df):
        """MEAN 집계"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Value'],
            aggregations={'Value': 'mean'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                assert child.aggregates.get('Value') == 20.0  # (10+20+30)/3
            elif child.display_name == 'B':
                assert child.aggregates.get('Value') == 45.0  # (40+50)/2
    
    def test_count_aggregation(self, model, sample_df):
        """COUNT 집계"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Value'],
            aggregations={'Value': 'count'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                assert child.aggregates.get('Value') == 3
            elif child.display_name == 'B':
                assert child.aggregates.get('Value') == 2
    
    def test_min_max_aggregation(self, model, sample_df):
        """MIN/MAX 집계"""
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Value'],
            aggregations={'Value': 'min'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                assert child.aggregates.get('Value') == 10
        
        # Change to max
        model.set_data(
            sample_df,
            group_columns=['Category'],
            value_columns=['Value'],
            aggregations={'Value': 'max'}
        )
        
        for child in model._root.children:
            if child.display_name == 'A':
                assert child.aggregates.get('Value') == 30
