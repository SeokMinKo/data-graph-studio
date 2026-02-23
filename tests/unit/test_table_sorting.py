"""
Table Sorting 테스트 - PolarsTableModel.sort() 기능
"""

import pytest
import polars as pl
from PySide6.QtCore import Qt

from data_graph_studio.ui.panels.table_panel import PolarsTableModel


class TestPolarsTableModelSorting:
    """PolarsTableModel 정렬 기능 테스트"""
    
    @pytest.fixture
    def model(self):
        """테이블 모델 인스턴스"""
        return PolarsTableModel()
    
    @pytest.fixture
    def numeric_df(self):
        """숫자 데이터프레임"""
        return pl.DataFrame({
            'id': [3, 1, 4, 1, 5, 9, 2, 6],
            'value': [30.0, 10.0, 40.0, 10.0, 50.0, 90.0, 20.0, 60.0],
            'name': ['c', 'a', 'd', 'a', 'e', 'i', 'b', 'f']
        })
    
    @pytest.fixture
    def null_df(self):
        """NULL 포함 데이터프레임"""
        return pl.DataFrame({
            'id': [3, None, 1, None, 2],
            'name': ['c', 'b', None, 'a', 'd']
        })
    
    @pytest.fixture
    def date_df(self):
        """날짜 데이터프레임"""
        return pl.DataFrame({
            'id': [1, 2, 3],
            'date': pl.Series(['2023-03-15', '2023-01-10', '2023-02-20']).str.strptime(pl.Date, '%Y-%m-%d')
        })
    
    # ==================== UT-1: 오름차순 정렬 ====================
    
    def test_sort_ascending_numeric(self, model, numeric_df):
        """UT-1: 숫자 컬럼 오름차순 정렬"""
        model.set_dataframe(numeric_df)
        
        # 컬럼 0 (id) 오름차순 정렬
        model.sort(0, Qt.AscendingOrder)
        
        # 첫 번째 행의 id 값 확인 (1이어야 함)
        index = model.index(0, 0)
        assert model.data(index, Qt.DisplayRole) == '1'
        
        # 마지막 행의 id 값 확인 (9이어야 함)
        index = model.index(model.rowCount() - 1, 0)
        assert model.data(index, Qt.DisplayRole) == '9'
    
    def test_sort_ascending_string(self, model, numeric_df):
        """UT-5: 문자열 컬럼 오름차순 정렬"""
        model.set_dataframe(numeric_df)
        
        # 컬럼 2 (name) 오름차순 정렬
        model.sort(2, Qt.AscendingOrder)
        
        # 첫 번째 행의 name 값 확인 ('a'이어야 함)
        index = model.index(0, 2)
        assert model.data(index, Qt.DisplayRole) == 'a'
    
    # ==================== UT-2: 내림차순 정렬 ====================
    
    def test_sort_descending_numeric(self, model, numeric_df):
        """UT-2: 숫자 컬럼 내림차순 정렬"""
        model.set_dataframe(numeric_df)
        
        # 컬럼 0 (id) 내림차순 정렬
        model.sort(0, Qt.DescendingOrder)
        
        # 첫 번째 행의 id 값 확인 (9이어야 함)
        index = model.index(0, 0)
        assert model.data(index, Qt.DisplayRole) == '9'
        
        # 마지막 행의 id 값 확인 (1이어야 함)
        index = model.index(model.rowCount() - 1, 0)
        assert model.data(index, Qt.DisplayRole) == '1'
    
    # ==================== UT-3: NULL 값 정렬 ====================
    
    def test_sort_null_values_last(self, model, null_df):
        """UT-3: NULL 값은 마지막으로 정렬"""
        model.set_dataframe(null_df)
        
        # 컬럼 0 (id) 오름차순 정렬
        model.sort(0, Qt.AscendingOrder)
        
        # 마지막 두 행이 NULL이어야 함 (빈 문자열로 표시)
        last_idx = model.rowCount() - 1
        assert model.data(model.index(last_idx, 0), Qt.DisplayRole) == ''
        assert model.data(model.index(last_idx - 1, 0), Qt.DisplayRole) == ''
        
        # 첫 번째 행은 1이어야 함
        assert model.data(model.index(0, 0), Qt.DisplayRole) == '1'
    
    # ==================== UT-4: 숫자 타입 정렬 ====================
    
    def test_sort_float_column(self, model, numeric_df):
        """UT-4: float 컬럼 정렬"""
        model.set_dataframe(numeric_df)
        
        # 컬럼 1 (value) 오름차순 정렬
        model.sort(1, Qt.AscendingOrder)
        
        # 첫 번째 행의 value 값 확인 (10.0이어야 함)
        index = model.index(0, 1)
        assert model.data(index, Qt.DisplayRole) == '10.0'
    
    # ==================== UT-6: 날짜 타입 정렬 ====================
    
    def test_sort_date_column(self, model, date_df):
        """UT-6: 날짜 컬럼 정렬"""
        model.set_dataframe(date_df)
        
        # 컬럼 1 (date) 오름차순 정렬
        model.sort(1, Qt.AscendingOrder)
        
        # 첫 번째 행의 id 값 확인 (id=2가 2023-01-10으로 가장 빠름)
        index = model.index(0, 0)
        assert model.data(index, Qt.DisplayRole) == '2'
    
    # ==================== UT-7: 원본 인덱스 매핑 ====================
    
    def test_sort_preserves_original_indices(self, model, numeric_df):
        """UT-7: 정렬 후 원본 인덱스 매핑 유지"""
        model.set_dataframe(numeric_df)
        
        # 정렬 전 원본 인덱스
        numeric_df['id'][0]  # 3
        
        # 정렬
        model.sort(0, Qt.AscendingOrder)
        
        # get_original_row_index() 메서드로 원본 인덱스 확인
        # 정렬 후 첫 번째 행 (id=1)의 원본 인덱스는 1 또는 3 (둘 다 id=1)
        original_idx = model.get_original_row_index(0)
        assert original_idx in [1, 3]  # id=1인 행들
    
    # ==================== 정렬 상태 관리 ====================
    
    def test_sort_state_tracking(self, model, numeric_df):
        """정렬 상태 추적"""
        model.set_dataframe(numeric_df)
        
        # 초기 상태: 정렬 없음
        assert model.get_sort_column() is None
        assert model.get_sort_order() is None
        
        # 정렬 후 상태
        model.sort(0, Qt.AscendingOrder)
        assert model.get_sort_column() == 0
        assert model.get_sort_order() == Qt.AscendingOrder
    
    def test_clear_sort(self, model, numeric_df):
        """정렬 초기화"""
        model.set_dataframe(numeric_df)
        
        # 정렬 적용
        model.sort(0, Qt.AscendingOrder)
        
        # 정렬 초기화
        model.clear_sort()
        
        # 원본 순서로 복원
        index = model.index(0, 0)
        assert model.data(index, Qt.DisplayRole) == '3'  # 원본 첫 번째 값
        
        # 상태 확인
        assert model.get_sort_column() is None
    
    def test_sort_cache_invalidation_on_new_data(self, model, numeric_df):
        """새 데이터 설정 시 정렬 캐시 무효화"""
        model.set_dataframe(numeric_df)
        model.sort(0, Qt.AscendingOrder)
        
        # 새 데이터프레임 설정
        new_df = pl.DataFrame({'x': [5, 3, 1]})
        model.set_dataframe(new_df)
        
        # 정렬 상태 초기화됨
        assert model.get_sort_column() is None
        
        # 원본 순서대로
        assert model.data(model.index(0, 0), Qt.DisplayRole) == '5'
    
    # ==================== 대용량 데이터 정렬 ====================
    
    def test_sort_large_dataset(self, model):
        """대용량 데이터셋 정렬 (성능 테스트)"""
        import time
        
        # 100,000행 데이터 생성
        large_df = pl.DataFrame({
            'id': list(range(100_000, 0, -1)),  # 역순
            'value': [float(i) for i in range(100_000)]
        })
        
        model.set_dataframe(large_df)
        
        # 정렬 시간 측정
        start = time.time()
        model.sort(0, Qt.AscendingOrder)
        elapsed = time.time() - start
        
        # 500ms 이내
        assert elapsed < 0.5, f"정렬 시간 초과: {elapsed:.3f}s"
        
        # 정렬 결과 확인
        assert model.data(model.index(0, 0), Qt.DisplayRole) == '1'


class TestPolarsTableModelSortingEdgeCases:
    """정렬 엣지 케이스 테스트"""
    
    @pytest.fixture
    def model(self):
        return PolarsTableModel()
    
    def test_sort_empty_dataframe(self, model):
        """빈 데이터프레임 정렬"""
        df = pl.DataFrame({'x': []})
        model.set_dataframe(df)
        
        # 에러 없이 정렬 가능
        model.sort(0, Qt.AscendingOrder)
        assert model.rowCount() == 0
    
    def test_sort_single_row(self, model):
        """단일 행 정렬"""
        df = pl.DataFrame({'x': [1]})
        model.set_dataframe(df)
        
        model.sort(0, Qt.AscendingOrder)
        assert model.data(model.index(0, 0), Qt.DisplayRole) == '1'
    
    def test_sort_invalid_column(self, model):
        """잘못된 컬럼 인덱스"""
        df = pl.DataFrame({'x': [1, 2, 3]})
        model.set_dataframe(df)
        
        # 잘못된 컬럼 인덱스로 정렬 시도 (에러 없어야 함)
        model.sort(100, Qt.AscendingOrder)
        
        # 원본 순서 유지
        assert model.data(model.index(0, 0), Qt.DisplayRole) == '1'
    
    def test_sort_all_same_values(self, model):
        """모든 값이 동일한 경우"""
        df = pl.DataFrame({'x': [5, 5, 5, 5]})
        model.set_dataframe(df)
        
        model.sort(0, Qt.AscendingOrder)
        
        # 모든 값이 5
        for i in range(4):
            assert model.data(model.index(i, 0), Qt.DisplayRole) == '5'
    
    def test_sort_all_null(self, model):
        """모든 값이 NULL인 경우"""
        df = pl.DataFrame({'x': [None, None, None]})
        model.set_dataframe(df)
        
        model.sort(0, Qt.AscendingOrder)
        
        # 모든 값이 빈 문자열
        for i in range(3):
            assert model.data(model.index(i, 0), Qt.DisplayRole) == ''
