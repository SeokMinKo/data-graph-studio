"""
Data Sampling 알고리즘 테스트
"""

import pytest
import numpy as np

from data_graph_studio.graph.sampling import DataSampler


class TestLTTB:
    """LTTB (Largest Triangle Three Buckets) 알고리즘 테스트"""
    
    def test_basic(self):
        """기본 LTTB 테스트"""
        x = np.arange(1000).astype(float)
        y = np.sin(x / 50) * 100
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=100)
        
        assert len(sampled_x) == 100
        assert len(sampled_y) == 100
    
    def test_preserves_first_and_last(self):
        """첫 번째와 마지막 포인트 보존 테스트"""
        x = np.arange(100).astype(float)
        y = np.random.random(100)
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=20)
        
        assert sampled_x[0] == x[0]
        assert sampled_y[0] == y[0]
        assert sampled_x[-1] == x[-1]
        assert sampled_y[-1] == y[-1]
    
    def test_returns_original_if_below_threshold(self):
        """임계값 미만이면 원본 반환 테스트"""
        x = np.arange(50).astype(float)
        y = np.arange(50).astype(float)
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=100)
        
        assert len(sampled_x) == 50
        np.testing.assert_array_equal(sampled_x, x)
        np.testing.assert_array_equal(sampled_y, y)
    
    def test_threshold_less_than_3(self):
        """임계값 3 미만이면 원본 반환 테스트"""
        x = np.arange(100).astype(float)
        y = np.arange(100).astype(float)
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=2)
        
        assert len(sampled_x) == 100
    
    def test_preserves_extremes(self):
        """극값 보존 테스트"""
        x = np.arange(1000).astype(float)
        y = np.zeros(1000)
        # 명확한 극값 설정
        y[250] = 100  # 최댓값
        y[750] = -100  # 최솟값
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=50)
        
        # 극값 근처가 샘플에 포함되어야 함
        assert 100 in sampled_y or any(abs(v - 100) < 10 for v in sampled_y)
        assert -100 in sampled_y or any(abs(v + 100) < 10 for v in sampled_y)


class TestMinMaxPerBucket:
    """버킷별 Min/Max 샘플링 테스트"""
    
    def test_basic(self):
        """기본 Min/Max 테스트"""
        x = np.arange(1000).astype(float)
        y = np.random.random(1000)
        
        sampled_x, sampled_y = DataSampler.min_max_per_bucket(x, y, n_buckets=50)
        
        # 각 버킷에서 2개씩 (min, max) 선택
        assert len(sampled_x) == 100  # 50 * 2
    
    def test_preserves_global_extremes(self):
        """전역 극값 보존 테스트"""
        x = np.arange(100).astype(float)
        y = np.arange(100).astype(float)  # min=0, max=99
        
        sampled_x, sampled_y = DataSampler.min_max_per_bucket(x, y, n_buckets=10)
        
        assert 0 in sampled_y  # 전역 최솟값
        assert 99 in sampled_y  # 전역 최댓값
    
    def test_returns_original_if_too_few_buckets(self):
        """버킷 수가 너무 많으면 원본 반환 테스트"""
        x = np.arange(50).astype(float)
        y = np.arange(50).astype(float)
        
        sampled_x, sampled_y = DataSampler.min_max_per_bucket(x, y, n_buckets=30)
        
        assert len(sampled_x) == 50
    
    def test_ordered_by_x(self):
        """X 기준 정렬 테스트"""
        x = np.arange(100).astype(float)
        y = np.sin(x / 10) * 10
        
        sampled_x, sampled_y = DataSampler.min_max_per_bucket(x, y, n_buckets=10)
        
        # X값이 정렬되어 있어야 함 (버킷 내에서)
        for i in range(0, len(sampled_x) - 2, 2):  # 버킷 단위로
            assert sampled_x[i] <= sampled_x[i + 1]


class TestRandomSample:
    """무작위 샘플링 테스트"""
    
    def test_basic(self):
        """기본 무작위 샘플링 테스트"""
        x = np.arange(1000).astype(float)
        y = np.arange(1000).astype(float)
        
        sampled_x, sampled_y = DataSampler.random_sample(x, y, n_samples=100)
        
        assert len(sampled_x) == 100
    
    def test_deterministic_with_seed(self):
        """시드로 재현 가능 테스트"""
        x = np.arange(1000).astype(float)
        y = np.arange(1000).astype(float)
        
        sampled1_x, _ = DataSampler.random_sample(x, y, n_samples=100, seed=42)
        sampled2_x, _ = DataSampler.random_sample(x, y, n_samples=100, seed=42)
        
        np.testing.assert_array_equal(sampled1_x, sampled2_x)
    
    def test_different_seeds_different_results(self):
        """다른 시드는 다른 결과 테스트"""
        x = np.arange(1000).astype(float)
        y = np.arange(1000).astype(float)
        
        sampled1_x, _ = DataSampler.random_sample(x, y, n_samples=100, seed=42)
        sampled2_x, _ = DataSampler.random_sample(x, y, n_samples=100, seed=123)
        
        # 완전히 같을 확률은 매우 낮음
        assert not np.array_equal(sampled1_x, sampled2_x)
    
    def test_returns_original_if_below_samples(self):
        """샘플 수보다 작으면 원본 반환 테스트"""
        x = np.arange(50).astype(float)
        y = np.arange(50).astype(float)
        
        sampled_x, sampled_y = DataSampler.random_sample(x, y, n_samples=100)
        
        assert len(sampled_x) == 50
    
    def test_sorted_indices(self):
        """인덱스 정렬 테스트"""
        x = np.arange(1000).astype(float)
        y = np.arange(1000).astype(float)
        
        sampled_x, _ = DataSampler.random_sample(x, y, n_samples=100)
        
        # X 값이 정렬되어 있어야 함 (인덱스가 정렬되어 선택되므로)
        assert np.all(sampled_x[:-1] <= sampled_x[1:])


class TestStratifiedSample:
    """층화 샘플링 테스트"""
    
    def test_basic(self):
        """기본 층화 샘플링 테스트"""
        x = np.arange(1000).astype(float)
        y = np.arange(1000).astype(float)
        groups = np.array(['A'] * 500 + ['B'] * 500)
        
        sampled_x, sampled_y, sampled_groups = DataSampler.stratified_sample(
            x, y, groups, n_samples=100
        )
        
        # 각 그룹에서 비율에 맞게 샘플링
        a_count = np.sum(sampled_groups == 'A')
        b_count = np.sum(sampled_groups == 'B')
        
        # 대략 50:50 비율
        assert 40 <= a_count <= 60
        assert 40 <= b_count <= 60
    
    def test_preserves_proportions(self):
        """비율 보존 테스트"""
        x = np.arange(1000).astype(float)
        y = np.arange(1000).astype(float)
        # 불균형한 그룹: A=700, B=200, C=100
        groups = np.array(['A'] * 700 + ['B'] * 200 + ['C'] * 100)
        
        sampled_x, sampled_y, sampled_groups = DataSampler.stratified_sample(
            x, y, groups, n_samples=100
        )
        
        a_count = np.sum(sampled_groups == 'A')
        b_count = np.sum(sampled_groups == 'B')
        c_count = np.sum(sampled_groups == 'C')
        
        # 비율이 대략 보존되어야 함 (오차 허용)
        assert a_count > b_count > c_count
    
    def test_deterministic_with_seed(self):
        """시드로 재현 가능 테스트"""
        x = np.arange(1000).astype(float)
        y = np.arange(1000).astype(float)
        groups = np.array(['A'] * 500 + ['B'] * 500)
        
        result1 = DataSampler.stratified_sample(x, y, groups, n_samples=100, seed=42)
        result2 = DataSampler.stratified_sample(x, y, groups, n_samples=100, seed=42)
        
        np.testing.assert_array_equal(result1[0], result2[0])


class TestAutoSample:
    """자동 샘플링 테스트"""
    
    def test_returns_original_if_small(self):
        """작은 데이터는 원본 반환 테스트"""
        x = np.arange(100).astype(float)
        y = np.arange(100).astype(float)
        
        sampled_x, sampled_y = DataSampler.auto_sample(x, y, max_points=1000)
        
        assert len(sampled_x) == 100
    
    def test_uses_lttb_for_sorted_data(self):
        """정렬된 데이터에 LTTB 사용 테스트"""
        x = np.arange(10000).astype(float)  # 정렬된 데이터
        y = np.sin(x / 100) * 10
        
        sampled_x, sampled_y = DataSampler.auto_sample(x, y, max_points=100)
        
        assert len(sampled_x) == 100
        # LTTB는 첫 번째와 마지막 포인트 보존
        assert sampled_x[0] == x[0]
        assert sampled_x[-1] == x[-1]
    
    def test_uses_minmax_for_unsorted_with_extremes(self):
        """정렬 안된 데이터 + 극값 보존 테스트"""
        np.random.seed(42)
        x = np.random.random(10000)  # 정렬 안된 데이터
        y = np.random.random(10000)
        
        sampled_x, sampled_y = DataSampler.auto_sample(
            x, y, max_points=100, preserve_extremes=True
        )
        
        assert len(sampled_x) <= 100 * 2  # min/max는 2배 포인트
    
    def test_respects_max_points(self):
        """최대 포인트 수 제한 테스트"""
        x = np.arange(100000).astype(float)
        y = np.arange(100000).astype(float)
        
        sampled_x, sampled_y = DataSampler.auto_sample(x, y, max_points=1000)
        
        assert len(sampled_x) <= 2000  # min/max 경우 최대 2배


class TestGroupAwareSampling:
    """그룹 인식 샘플링 테스트 (GraphPanel에서 사용하는 로직)"""
    
    def test_group_sampling_preserves_all_groups(self):
        """그룹별 샘플링이 모든 그룹을 보존하는지 테스트"""
        # 3개의 그룹: A=500, B=300, C=200 (총 1000)
        x = np.arange(1000).astype(float)
        y = np.sin(x / 50) * 100
        
        groups = {
            'A': np.array([True] * 500 + [False] * 500),
            'B': np.array([False] * 500 + [True] * 300 + [False] * 200),
            'C': np.array([False] * 800 + [True] * 200)
        }
        
        max_points = 100
        
        # 그룹별 샘플링 수행 (graph_panel.py와 동일한 로직)
        total_valid = sum(np.sum(mask) for mask in groups.values())
        min_points_per_group = max(10, max_points // 100)
        
        x_sampled_list = []
        y_sampled_list = []
        new_groups = {}
        current_offset = 0
        
        for group_name, mask in groups.items():
            x_group = x[mask]
            y_group = y[mask]
            
            if len(x_group) == 0:
                continue
            
            group_ratio = len(x_group) / total_valid if total_valid > 0 else 0
            group_points = max(min_points_per_group, int(max_points * group_ratio))
            
            if len(x_group) > group_points:
                x_group_sampled, y_group_sampled = DataSampler.lttb(
                    x_group, y_group, threshold=group_points
                )
            else:
                x_group_sampled, y_group_sampled = x_group, y_group
            
            group_len = len(x_group_sampled)
            x_sampled_list.append(x_group_sampled)
            y_sampled_list.append(y_group_sampled)
            new_groups[group_name] = (current_offset, group_len)
            current_offset += group_len
        
        x_sampled = np.concatenate(x_sampled_list)
        y_sampled = np.concatenate(y_sampled_list)
        
        # 새 그룹 마스크 생성
        total_sampled = len(x_sampled)
        final_groups = {}
        for group_name, (offset, length) in new_groups.items():
            mask = np.zeros(total_sampled, dtype=bool)
            mask[offset:offset + length] = True
            final_groups[group_name] = mask
        
        # 검증: 모든 그룹이 보존됨
        assert set(final_groups.keys()) == {'A', 'B', 'C'}
        
        # 검증: 각 그룹이 최소 포인트 수 이상
        for group_name, mask in final_groups.items():
            assert np.sum(mask) >= min_points_per_group
        
        # 검증: 그룹 마스크가 겹치지 않음
        combined_mask = np.zeros(total_sampled, dtype=bool)
        for mask in final_groups.values():
            assert not np.any(combined_mask & mask)  # 겹침 없음
            combined_mask |= mask
        
        # 검증: 모든 포인트가 어떤 그룹에 속함
        assert np.all(combined_mask)
    
    def test_proportional_sampling(self):
        """그룹 크기에 비례한 샘플링 테스트"""
        # 불균형 그룹: Large=900, Small=100
        x = np.arange(1000).astype(float)
        y = np.arange(1000).astype(float)
        
        groups = {
            'Large': np.array([True] * 900 + [False] * 100),
            'Small': np.array([False] * 900 + [True] * 100)
        }
        
        max_points = 100
        total_valid = 1000
        min_points_per_group = max(10, max_points // 100)
        
        # 각 그룹의 할당 포인트 계산
        large_ratio = 900 / total_valid
        small_ratio = 100 / total_valid
        
        large_points = max(min_points_per_group, int(max_points * large_ratio))
        small_points = max(min_points_per_group, int(max_points * small_ratio))
        
        # Large 그룹이 더 많은 포인트를 가져야 함
        assert large_points > small_points
        
        # Small 그룹도 최소 포인트 수 확보
        assert small_points >= min_points_per_group
    
    def test_empty_group_handling(self):
        """빈 그룹 처리 테스트"""
        x = np.arange(100).astype(float)
        y = np.arange(100).astype(float)
        
        groups = {
            'A': np.array([True] * 50 + [False] * 50),
            'Empty': np.zeros(100, dtype=bool),  # 빈 그룹
            'B': np.array([False] * 50 + [True] * 50)
        }
        
        non_empty_groups = {k: v for k, v in groups.items() if np.sum(v) > 0}
        
        # 빈 그룹은 제외됨
        assert 'Empty' not in non_empty_groups
        assert len(non_empty_groups) == 2


class TestEdgeCases:
    """엣지 케이스 테스트"""
    
    def test_empty_arrays(self):
        """빈 배열 테스트"""
        x = np.array([])
        y = np.array([])
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=10)
        assert len(sampled_x) == 0
    
    def test_single_point(self):
        """단일 포인트 테스트"""
        x = np.array([1.0])
        y = np.array([2.0])
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=10)
        assert len(sampled_x) == 1
    
    def test_two_points(self):
        """두 개 포인트 테스트"""
        x = np.array([1.0, 2.0])
        y = np.array([3.0, 4.0])
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=10)
        assert len(sampled_x) == 2
    
    def test_with_nan_values(self):
        """NaN 값 포함 테스트"""
        x = np.arange(100).astype(float)
        y = np.arange(100).astype(float)
        y[50] = np.nan
        
        # NaN이 있어도 크래시하지 않아야 함
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=20)
        assert len(sampled_x) == 20
    
    def test_with_inf_values(self):
        """무한대 값 포함 테스트"""
        x = np.arange(100).astype(float)
        y = np.arange(100).astype(float)
        y[50] = np.inf
        
        # inf가 있어도 크래시하지 않아야 함
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=20)
        assert len(sampled_x) == 20
    
    def test_constant_values(self):
        """상수 값 테스트"""
        x = np.arange(100).astype(float)
        y = np.ones(100) * 5  # 모든 값이 5
        
        sampled_x, sampled_y = DataSampler.lttb(x, y, threshold=20)
        assert len(sampled_x) == 20
        # 모든 y 값이 5여야 함
        assert np.all(sampled_y == 5)
