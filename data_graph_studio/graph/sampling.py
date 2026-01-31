"""
Data Sampling - 대용량 데이터 샘플링 알고리즘
"""

import numpy as np
from typing import Tuple, Optional


class DataSampler:
    """
    데이터 샘플링 클래스
    
    대용량 데이터를 효율적으로 시각화하기 위한 샘플링 알고리즘
    """
    
    @staticmethod
    def lttb(x: np.ndarray, y: np.ndarray, threshold: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Largest Triangle Three Buckets (LTTB) 알고리즘
        
        시계열 데이터의 특성을 유지하면서 다운샘플링
        
        Args:
            x: X 좌표 배열
            y: Y 좌표 배열
            threshold: 목표 포인트 수
        
        Returns:
            (sampled_x, sampled_y)
        """
        n = len(x)
        
        # Handle edge cases
        if n == 0:
            return np.array([]), np.array([])
        
        if threshold <= 0:
            return np.array([]), np.array([])
        
        if threshold >= n or threshold < 3:
            return x.copy(), y.copy()
        
        sampled_x = np.zeros(threshold)
        sampled_y = np.zeros(threshold)
        
        # 첫 번째와 마지막 포인트는 항상 포함
        sampled_x[0] = x[0]
        sampled_y[0] = y[0]
        sampled_x[threshold - 1] = x[n - 1]
        sampled_y[threshold - 1] = y[n - 1]
        
        # 버킷 크기
        bucket_size = (n - 2) / (threshold - 2)
        
        a = 0  # 이전 선택 포인트
        
        for i in range(1, threshold - 1):
            # 현재 버킷 범위
            bucket_start = int((i - 1) * bucket_size) + 1
            bucket_end = int(i * bucket_size) + 1
            
            # 다음 버킷의 평균점
            next_bucket_start = int(i * bucket_size) + 1
            next_bucket_end = int((i + 1) * bucket_size) + 1
            next_bucket_end = min(next_bucket_end, n)
            
            avg_x = np.mean(x[next_bucket_start:next_bucket_end])
            avg_y = np.mean(y[next_bucket_start:next_bucket_end])
            
            # 현재 버킷에서 가장 큰 삼각형을 만드는 점 찾기
            max_area = -1
            max_idx = bucket_start
            
            for j in range(bucket_start, min(bucket_end, n)):
                # 삼각형 면적 계산
                area = abs(
                    (x[a] - avg_x) * (y[j] - y[a]) -
                    (x[a] - x[j]) * (avg_y - y[a])
                )
                
                if area > max_area:
                    max_area = area
                    max_idx = j
            
            sampled_x[i] = x[max_idx]
            sampled_y[i] = y[max_idx]
            a = max_idx
        
        return sampled_x, sampled_y
    
    @staticmethod
    def min_max_per_bucket(
        x: np.ndarray, 
        y: np.ndarray, 
        n_buckets: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        버킷별 Min/Max 샘플링
        
        각 버킷에서 최소/최대 값을 유지하여 이상치 보존
        
        Args:
            x: X 좌표 배열
            y: Y 좌표 배열
            n_buckets: 버킷 수
        
        Returns:
            (sampled_x, sampled_y)
        """
        n = len(x)
        
        # Handle edge cases
        if n == 0:
            return np.array([]), np.array([])
        
        if n_buckets <= 0:
            return np.array([]), np.array([])
        
        if n_buckets >= n // 2 or n_buckets >= n:
            return x.copy(), y.copy()
        
        bucket_size = n // n_buckets
        if bucket_size == 0:
            return x.copy(), y.copy()
        
        result_x = []
        result_y = []
        
        for i in range(n_buckets):
            start = i * bucket_size
            end = start + bucket_size if i < n_buckets - 1 else n
            
            bucket_y = y[start:end]
            bucket_x = x[start:end]
            
            if len(bucket_y) == 0:
                continue
            
            # Min과 Max 인덱스
            min_idx = np.argmin(bucket_y)
            max_idx = np.argmax(bucket_y)
            
            # 순서대로 추가 (x 기준)
            if min_idx <= max_idx:
                result_x.extend([bucket_x[min_idx], bucket_x[max_idx]])
                result_y.extend([bucket_y[min_idx], bucket_y[max_idx]])
            else:
                result_x.extend([bucket_x[max_idx], bucket_x[min_idx]])
                result_y.extend([bucket_y[max_idx], bucket_y[min_idx]])
        
        return np.array(result_x), np.array(result_y)
    
    @staticmethod
    def random_sample(
        x: np.ndarray, 
        y: np.ndarray, 
        n_samples: int,
        seed: int = 42
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        무작위 샘플링
        
        Args:
            x: X 좌표 배열
            y: Y 좌표 배열
            n_samples: 샘플 수
            seed: 랜덤 시드
        
        Returns:
            (sampled_x, sampled_y)
        """
        n = len(x)
        
        if n_samples >= n:
            return x, y
        
        np.random.seed(seed)
        indices = np.sort(np.random.choice(n, n_samples, replace=False))
        
        return x[indices], y[indices]
    
    @staticmethod
    def stratified_sample(
        x: np.ndarray,
        y: np.ndarray,
        groups: np.ndarray,
        n_samples: int,
        seed: int = 42
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        층화 샘플링 (그룹별 비율 유지)
        
        Args:
            x: X 좌표 배열
            y: Y 좌표 배열
            groups: 그룹 레이블 배열
            n_samples: 총 샘플 수
            seed: 랜덤 시드
        
        Returns:
            (sampled_x, sampled_y, sampled_groups)
        """
        # Handle edge cases
        n = len(x)
        if n == 0:
            return np.array([]), np.array([]), np.array([])
        
        if n_samples <= 0:
            return np.array([]), np.array([]), np.array([])
        
        if n_samples >= n:
            return x.copy(), y.copy(), groups.copy()
        
        np.random.seed(seed)
        
        unique_groups = np.unique(groups)
        
        result_indices = []
        
        for group in unique_groups:
            group_mask = groups == group
            group_indices = np.where(group_mask)[0]
            group_size = len(group_indices)
            
            if group_size == 0:
                continue
            
            # 그룹별 샘플 수 (비율 유지)
            group_n_samples = max(1, int(n_samples * group_size / n))
            group_n_samples = min(group_n_samples, group_size)
            
            sampled = np.random.choice(group_indices, group_n_samples, replace=False)
            result_indices.extend(sampled)
        
        if not result_indices:
            return np.array([]), np.array([]), np.array([])
        
        result_indices = np.sort(result_indices)
        
        return x[result_indices], y[result_indices], groups[result_indices]
    
    @staticmethod
    def auto_sample(
        x: np.ndarray,
        y: np.ndarray,
        max_points: int = 10000,
        preserve_extremes: bool = True
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        자동 샘플링 (데이터 특성에 따라 최적 알고리즘 선택)
        
        Args:
            x: X 좌표 배열
            y: Y 좌표 배열
            max_points: 최대 포인트 수
            preserve_extremes: 극값 보존 여부
        
        Returns:
            (sampled_x, sampled_y)
        """
        n = len(x)
        
        if n <= max_points:
            return x, y
        
        # 정렬 여부 확인 (시계열 데이터인지)
        is_sorted = np.all(x[:-1] <= x[1:])
        
        if is_sorted:
            # 시계열 데이터 → LTTB
            return DataSampler.lttb(x, y, max_points)
        elif preserve_extremes:
            # 극값 보존 → Min/Max
            return DataSampler.min_max_per_bucket(x, y, max_points // 2)
        else:
            # 일반 데이터 → 무작위
            return DataSampler.random_sample(x, y, max_points)
