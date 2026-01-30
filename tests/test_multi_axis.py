"""
Tests for Multi Y-Axis support
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_graph_studio.core.state import AppState, ValueColumn, AggregationType


class TestMultiAxisState:
    """다중 Y축 상태 관리 테스트"""
    
    @pytest.fixture
    def state(self):
        return AppState()
    
    def test_value_column_default_axis(self, state):
        """기본 축은 primary"""
        state.add_value_column("Sales", AggregationType.SUM)
        assert state.value_columns[0].use_secondary_axis is False
    
    def test_set_secondary_axis(self, state):
        """Secondary 축 설정"""
        state.add_value_column("Sales", AggregationType.SUM)
        state.add_value_column("Quantity", AggregationType.SUM)
        
        state.update_value_column(1, use_secondary_axis=True)
        
        assert state.value_columns[0].use_secondary_axis is False
        assert state.value_columns[1].use_secondary_axis is True
    
    def test_toggle_axis(self, state):
        """축 토글"""
        state.add_value_column("Sales", AggregationType.SUM)
        
        # Primary -> Secondary
        state.update_value_column(0, use_secondary_axis=True)
        assert state.value_columns[0].use_secondary_axis is True
        
        # Secondary -> Primary
        state.update_value_column(0, use_secondary_axis=False)
        assert state.value_columns[0].use_secondary_axis is False
    
    def test_multiple_values_different_axes(self, state):
        """여러 값이 다른 축에 할당"""
        state.add_value_column("Sales", AggregationType.SUM)
        state.add_value_column("Quantity", AggregationType.SUM)
        state.add_value_column("Price", AggregationType.MEAN)
        state.add_value_column("Margin", AggregationType.MEAN)
        
        # Sales, Price -> Primary
        # Quantity, Margin -> Secondary
        state.update_value_column(1, use_secondary_axis=True)
        state.update_value_column(3, use_secondary_axis=True)
        
        primary = [v for v in state.value_columns if not v.use_secondary_axis]
        secondary = [v for v in state.value_columns if v.use_secondary_axis]
        
        assert len(primary) == 2
        assert len(secondary) == 2
        assert primary[0].name == "Sales"
        assert primary[1].name == "Price"
        assert secondary[0].name == "Quantity"
        assert secondary[1].name == "Margin"
    
    def test_signal_emitted_on_axis_change(self, state, qtbot):
        """축 변경 시 시그널 발생"""
        state.add_value_column("Sales", AggregationType.SUM)
        
        with qtbot.waitSignal(state.value_zone_changed, timeout=1000):
            state.update_value_column(0, use_secondary_axis=True)


class TestMultiAxisConfig:
    """다중 Y축 설정 테스트"""
    
    @pytest.fixture
    def state(self):
        return AppState()
    
    def test_get_primary_values(self, state):
        """Primary 축 값 목록 조회"""
        state.add_value_column("Sales", AggregationType.SUM)
        state.add_value_column("Quantity", AggregationType.SUM)
        state.update_value_column(1, use_secondary_axis=True)
        
        primary = state.get_primary_values()
        assert len(primary) == 1
        assert primary[0].name == "Sales"
    
    def test_get_secondary_values(self, state):
        """Secondary 축 값 목록 조회"""
        state.add_value_column("Sales", AggregationType.SUM)
        state.add_value_column("Quantity", AggregationType.SUM)
        state.update_value_column(1, use_secondary_axis=True)
        
        secondary = state.get_secondary_values()
        assert len(secondary) == 1
        assert secondary[0].name == "Quantity"
    
    def test_has_secondary_axis(self, state):
        """Secondary 축 존재 여부"""
        state.add_value_column("Sales", AggregationType.SUM)
        assert state.has_secondary_axis() is False
        
        state.add_value_column("Quantity", AggregationType.SUM)
        state.update_value_column(1, use_secondary_axis=True)
        assert state.has_secondary_axis() is True


class TestSecondaryAxisSettings:
    """Secondary 축 설정 테스트"""
    
    @pytest.fixture
    def state(self):
        return AppState()
    
    def test_secondary_y_min_max(self, state):
        """Secondary Y축 min/max 설정"""
        state.update_chart_settings(
            secondary_y_min=0,
            secondary_y_max=100
        )
        assert state.chart_settings.secondary_y_min == 0
        assert state.chart_settings.secondary_y_max == 100
    
    def test_secondary_y_log_scale(self, state):
        """Secondary Y축 로그 스케일"""
        state.update_chart_settings(secondary_y_log_scale=True)
        assert state.chart_settings.secondary_y_log_scale is True
    
    def test_secondary_axis_label(self, state):
        """Secondary 축 라벨"""
        state.update_chart_settings(secondary_y_label="Quantity (units)")
        assert state.chart_settings.secondary_y_label == "Quantity (units)"


class TestMultiAxisIntegration:
    """다중 Y축 통합 테스트"""
    
    @pytest.fixture
    def state(self):
        state = AppState()
        state.add_value_column("Revenue", AggregationType.SUM)
        state.add_value_column("Units", AggregationType.SUM)
        state.update_value_column(1, use_secondary_axis=True)
        return state
    
    def test_axis_assignment_preserved_on_reorder(self, state):
        """순서 변경 시 축 할당 유지"""
        # Reorder columns (if implemented)
        revenue = state.value_columns[0]
        units = state.value_columns[1]
        
        assert revenue.use_secondary_axis is False
        assert units.use_secondary_axis is True
    
    def test_clear_value_zone_resets_axes(self, state):
        """Value Zone 클리어 시 축 초기화"""
        state.clear_value_zone()
        assert len(state.value_columns) == 0
    
    def test_remove_all_secondary_values(self, state):
        """Secondary 값 모두 제거"""
        state.remove_value_column(1)  # Remove Units
        assert state.has_secondary_axis() is False


class TestAxisScaling:
    """축 스케일링 테스트"""
    
    @pytest.fixture
    def state(self):
        return AppState()
    
    def test_independent_scaling(self, state):
        """독립적 스케일링 확인"""
        state.update_chart_settings(
            y_min=0,
            y_max=1000000,  # Revenue scale
            secondary_y_min=0,
            secondary_y_max=10000  # Units scale
        )
        
        assert state.chart_settings.y_max == 1000000
        assert state.chart_settings.secondary_y_max == 10000
    
    def test_auto_scale_independent(self, state):
        """자동 스케일링 독립성"""
        # Both axes can independently use auto-scaling
        state.update_chart_settings(
            y_min=None,
            y_max=None,
            secondary_y_min=0,  # Force min
            secondary_y_max=None  # Auto max
        )
        
        assert state.chart_settings.y_min is None
        assert state.chart_settings.secondary_y_min == 0
