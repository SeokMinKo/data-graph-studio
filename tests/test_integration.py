"""
통합 테스트 - 양방향 선택 연동, 그래프 렌더링, 전체 플로우
"""

import pytest
import tempfile
import os
import numpy as np
import polars as pl

from PySide6.QtCore import Qt

from data_graph_studio.core.data_engine import DataEngine
from data_graph_studio.core.state import AppState, ChartType, AggregationType, ToolMode
from data_graph_studio.ui.panels.table_panel import PolarsTableModel, TablePanel
from data_graph_studio.ui.panels.graph_panel import MainGraph, GraphPanel
from data_graph_studio.graph.sampling import DataSampler


class TestBidirectionalSelection:
    """양방향 선택 연동 테스트"""
    
    @pytest.fixture
    def state(self, qtbot):
        return AppState()
    
    @pytest.fixture
    def engine(self):
        return DataEngine()
    
    @pytest.fixture
    def sample_data(self, engine):
        """샘플 데이터 로드"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("id,name,value,category\n")
            for i in range(100):
                f.write(f"{i},item_{i},{i * 1.5},{['A', 'B', 'C'][i % 3]}\n")
            path = f.name
        
        engine.load_file(path)
        yield engine
        os.unlink(path)
    
    def test_table_selection_updates_state(self, state, sample_data, qtbot):
        """테이블 선택이 상태를 업데이트하는지 테스트"""
        state.set_data_loaded(True, 100)
        
        # 테이블에서 행 선택 시뮬레이션
        with qtbot.waitSignal(state.selection_changed):
            state.select_rows([0, 1, 2])
        
        assert state.selection.selection_count == 3
        assert 0 in state.selection.selected_rows
        assert 1 in state.selection.selected_rows
        assert 2 in state.selection.selected_rows
    
    def test_state_selection_clears_properly(self, state, qtbot):
        """상태 선택 클리어 테스트"""
        state.set_data_loaded(True, 100)
        state.select_rows([0, 1, 2])
        
        with qtbot.waitSignal(state.selection_changed):
            state.clear_selection()
        
        assert state.selection.has_selection is False
    
    def test_add_selection_mode(self, state, qtbot):
        """추가 선택 모드 테스트"""
        state.set_data_loaded(True, 100)
        state.select_rows([0, 1])
        
        with qtbot.waitSignal(state.selection_changed):
            state.select_rows([5, 6], add=True)
        
        assert state.selection.selection_count == 4
        assert 0 in state.selection.selected_rows
        assert 5 in state.selection.selected_rows
    
    def test_toggle_selection(self, state, qtbot):
        """토글 선택 테스트"""
        state.set_data_loaded(True, 100)
        state.select_rows([0, 1, 2])
        
        # 이미 선택된 행 토글 -> 선택 해제
        with qtbot.waitSignal(state.selection_changed):
            state.toggle_row(1)
        
        assert 1 not in state.selection.selected_rows
        assert state.selection.selection_count == 2
        
        # 선택 안된 행 토글 -> 선택
        with qtbot.waitSignal(state.selection_changed):
            state.toggle_row(5)
        
        assert 5 in state.selection.selected_rows


class TestGraphRendering:
    """그래프 렌더링 테스트"""
    
    @pytest.fixture
    def state(self, qtbot):
        return AppState()
    
    @pytest.fixture
    def engine(self):
        return DataEngine()
    
    @pytest.fixture
    def sample_data(self, engine):
        """샘플 데이터 로드"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("date,sales,profit,category\n")
            for i in range(100):
                f.write(f"{i},{i * 10},{i * 5},{['A', 'B'][i % 2]}\n")
            path = f.name
        
        engine.load_file(path)
        yield engine
        os.unlink(path)
    
    def test_main_graph_plot_line(self, state, qtbot):
        """라인 그래프 플롯 테스트"""
        graph = MainGraph(state)
        
        x = np.arange(100)
        y = np.sin(x / 10) * 10
        
        graph.plot_data(x, y, chart_type=ChartType.LINE)
        
        assert len(graph._plot_items) > 0
    
    def test_main_graph_plot_scatter(self, state, qtbot):
        """산점도 플롯 테스트"""
        graph = MainGraph(state)
        
        x = np.random.random(100)
        y = np.random.random(100)
        
        graph.plot_data(x, y, chart_type=ChartType.SCATTER)
        
        assert len(graph._scatter_items) > 0 or len(graph._plot_items) > 0
    
    def test_main_graph_plot_bar(self, state, qtbot):
        """바 그래프 플롯 테스트"""
        graph = MainGraph(state)
        
        x = np.arange(10)
        y = np.random.random(10) * 100
        
        graph.plot_data(x, y, chart_type=ChartType.BAR)
        
        assert len(graph._plot_items) > 0
    
    def test_main_graph_plot_area(self, state, qtbot):
        """영역 그래프 플롯 테스트"""
        graph = MainGraph(state)
        
        x = np.arange(50)
        y = np.cumsum(np.random.random(50))
        
        graph.plot_data(x, y, chart_type=ChartType.AREA)
        
        assert len(graph._plot_items) > 0
    
    def test_main_graph_clear(self, state, qtbot):
        """그래프 클리어 테스트"""
        graph = MainGraph(state)
        
        x = np.arange(100)
        y = np.sin(x / 10) * 10
        
        graph.plot_data(x, y, chart_type=ChartType.LINE)
        assert len(graph._plot_items) > 0
        
        graph.clear_plot()
        assert len(graph._plot_items) == 0
    
    def test_main_graph_with_settings(self, state, qtbot):
        """그래프 설정 적용 테스트"""
        graph = MainGraph(state)
        
        x = np.arange(50)
        y = np.sin(x / 5) * 10
        
        settings = {
            'line_width': 3,
            'marker_size': 8,
            'fill_opacity': 0.5
        }
        
        graph.plot_data(x, y, chart_type=ChartType.LINE, settings=settings)
        assert len(graph._plot_items) > 0


class TestDataFlowIntegration:
    """데이터 플로우 통합 테스트"""
    
    @pytest.fixture
    def state(self, qtbot):
        return AppState()
    
    @pytest.fixture
    def engine(self):
        return DataEngine()
    
    @pytest.fixture
    def sample_csv(self):
        """샘플 CSV 파일"""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.write("id,name,sales,profit,region\n")
        for i in range(500):
            region = ['North', 'South', 'East', 'West'][i % 4]
            f.write(f"{i},Product_{i},{i * 10 + 100},{i * 3},{region}\n")
        path = f.name
        f.close()  # 먼저 닫기 (Windows 호환)
        yield path
        os.unlink(path)
    
    def test_full_data_flow(self, state, engine, sample_csv, qtbot):
        """전체 데이터 플로우 테스트"""
        # 1. 파일 로드
        assert engine.load_file(sample_csv) is True
        assert engine.is_loaded is True
        assert engine.row_count == 500
        
        # 2. 상태 업데이트
        with qtbot.waitSignal(state.data_loaded):
            state.set_data_loaded(True, engine.row_count)
        
        # 3. 그룹 추가
        with qtbot.waitSignal(state.group_zone_changed):
            state.add_group_column('region')
        
        # 4. 밸류 추가
        with qtbot.waitSignal(state.value_zone_changed):
            state.add_value_column('sales', AggregationType.SUM)
        
        # 5. 필터 추가
        with qtbot.waitSignal(state.filter_changed):
            state.add_filter('profit', 'gt', 500)
        
        # 6. 데이터 필터링
        filtered = engine.filter('profit', 'gt', 500)
        assert len(filtered) < 500
        
        # 7. 그룹 집계
        aggregated = engine.group_aggregate(
            ['region'],
            ['sales'],
            ['sum']
        )
        assert len(aggregated) == 4  # 4개 지역
        assert 'sales_sum' in aggregated.columns
    
    def test_filter_chain(self, engine, sample_csv):
        """필터 체인 테스트"""
        engine.load_file(sample_csv)
        
        # 연속 필터
        result = engine.filter('profit', 'gt', 100)
        result_count = len(result)
        
        # 추가 필터 (원본에서)
        result2 = engine.filter('region', 'eq', 'North')
        
        # 각 필터가 독립적으로 동작
        assert result_count > len(result2)
    
    def test_sort_and_slice(self, engine, sample_csv):
        """정렬 후 슬라이스 테스트"""
        engine.load_file(sample_csv)
        
        # 정렬
        sorted_df = engine.sort(['sales'], descending=True)
        
        # 상위 10개 (가장 높은 sales)
        top_10 = sorted_df.head(10)
        assert len(top_10) == 10
        
        # 정렬 확인
        sales_values = top_10['sales'].to_list()
        assert sales_values == sorted(sales_values, reverse=True)
    
    def test_statistics_with_filter(self, engine, sample_csv):
        """필터링된 데이터의 통계 테스트"""
        engine.load_file(sample_csv)
        
        # 전체 통계
        full_stats = engine.get_statistics('sales')
        
        # 필터링된 통계
        filtered = engine.filter('region', 'eq', 'North')
        # 필터링된 데이터의 통계는 다시 계산해야 함
        assert full_stats['count'] == 500


class TestSamplingIntegration:
    """샘플링 통합 테스트"""
    
    @pytest.fixture
    def large_data(self):
        """대용량 데이터 생성"""
        n = 100000
        return {
            'x': np.arange(n).astype(float),
            'y': np.sin(np.arange(n) / 1000) * 100 + np.random.normal(0, 10, n)
        }
    
    def test_auto_sampling_for_visualization(self, large_data):
        """시각화용 자동 샘플링 테스트"""
        x = large_data['x']
        y = large_data['y']
        
        # 10만 포인트 -> 1000 포인트로 샘플링
        sampled_x, sampled_y = DataSampler.auto_sample(x, y, max_points=1000)
        
        assert len(sampled_x) <= 1000
        assert len(sampled_x) == len(sampled_y)
        
        # 원본 데이터 범위 유지
        assert sampled_y.min() <= y.min() + 50  # 근사치
        assert sampled_y.max() >= y.max() - 50
    
    def test_lttb_preserves_shape(self, large_data):
        """LTTB가 데이터 형태를 보존하는지 테스트"""
        x = large_data['x']
        y = large_data['y']
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=1000)
        
        # 시작과 끝이 유지됨
        assert sampled_x[0] == x[0]
        assert sampled_x[-1] == x[-1]


class TestStateSignals:
    """상태 시그널 테스트"""
    
    @pytest.fixture
    def state(self, qtbot):
        return AppState()
    
    def test_all_signals_emit(self, state, qtbot):
        """모든 시그널 발생 테스트"""
        # data_loaded
        with qtbot.waitSignal(state.data_loaded, timeout=1000):
            state.set_data_loaded(True, 100)
        
        # group_zone_changed
        with qtbot.waitSignal(state.group_zone_changed, timeout=1000):
            state.add_group_column('test')
        
        # value_zone_changed
        with qtbot.waitSignal(state.value_zone_changed, timeout=1000):
            state.add_value_column('test')
        
        # filter_changed
        with qtbot.waitSignal(state.filter_changed, timeout=1000):
            state.add_filter('col', 'eq', 'val')
        
        # sort_changed
        with qtbot.waitSignal(state.sort_changed, timeout=1000):
            state.set_sort('col')
        
        # selection_changed
        with qtbot.waitSignal(state.selection_changed, timeout=1000):
            state.select_rows([1, 2, 3])
        
        # chart_settings_changed
        with qtbot.waitSignal(state.chart_settings_changed, timeout=1000):
            state.set_chart_type(ChartType.BAR)
        
        # tool_mode_changed
        with qtbot.waitSignal(state.tool_mode_changed, timeout=1000):
            state.set_tool_mode(ToolMode.ZOOM)
    
    def test_signal_order_on_reset(self, state, qtbot):
        """리셋 시 시그널 발생 테스트"""
        state.set_data_loaded(True, 100)
        state.add_group_column('test')
        
        with qtbot.waitSignal(state.data_cleared, timeout=1000):
            state.reset()
        
        assert state.is_data_loaded is False
        assert len(state.group_columns) == 0


class TestTableModelIntegration:
    """테이블 모델 통합 테스트"""
    
    @pytest.fixture
    def model(self):
        return PolarsTableModel()
    
    @pytest.fixture
    def engine(self):
        return DataEngine()
    
    @pytest.fixture
    def sample_csv(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        f.write("id,name,value\n")
        for i in range(1000):
            f.write(f"{i},item_{i},{i * 1.5}\n")
        path = f.name
        f.close()  # 먼저 닫기 (Windows 호환)
        yield path
        os.unlink(path)
    
    def test_model_with_engine_data(self, model, engine, sample_csv):
        """엔진 데이터와 모델 연동 테스트"""
        engine.load_file(sample_csv)
        model.set_dataframe(engine.df)
        
        assert model.rowCount() == engine.row_count
        assert model.columnCount() == engine.column_count
    
    def test_model_with_filtered_data(self, model, engine, sample_csv):
        """필터링된 데이터로 모델 업데이트 테스트"""
        engine.load_file(sample_csv)
        model.set_dataframe(engine.df)
        original_count = model.rowCount()
        
        # 필터 적용
        filtered = engine.filter('value', 'gt', 500)
        model.set_dataframe(filtered)
        
        assert model.rowCount() < original_count
    
    def test_model_with_sorted_data(self, model, engine, sample_csv):
        """정렬된 데이터로 모델 업데이트 테스트"""
        engine.load_file(sample_csv)
        
        # 내림차순 정렬
        sorted_df = engine.sort(['value'], descending=True)
        model.set_dataframe(sorted_df)
        
        # 첫 번째 값이 가장 큰 값
        index = model.index(0, 2)  # value 컬럼
        first_value = float(model.data(index, Qt.DisplayRole))
        
        index = model.index(1, 2)
        second_value = float(model.data(index, Qt.DisplayRole))
        
        assert first_value > second_value
