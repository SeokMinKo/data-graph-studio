"""
Statistical Analysis - Spotfire 스타일 통계 분석 도구

상관 분석, 클러스터링, 시계열 분석, 가설 검정 등을 제공합니다.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
import polars as pl
from scipy import stats
from scipy.cluster import hierarchy
from scipy.signal import find_peaks

logger = logging.getLogger(__name__)


class CorrelationMethod(Enum):
    """상관 계수 방법"""
    PEARSON = "pearson"      # 피어슨 (선형 관계)
    SPEARMAN = "spearman"    # 스피어만 (순위 기반)
    KENDALL = "kendall"      # 켄달 타우 (순위 기반)


@dataclass
class CorrelationResult:
    """상관 분석 결과"""
    matrix: np.ndarray
    columns: List[str]
    method: CorrelationMethod
    p_value_matrix: Optional[np.ndarray] = None

    def get_correlation(self, col1: str, col2: str) -> float:
        """두 컬럼 간 상관계수"""
        i = self.columns.index(col1)
        j = self.columns.index(col2)
        return self.matrix[i, j]

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        """딕셔너리로 변환"""
        result = {}
        for i, col1 in enumerate(self.columns):
            result[col1] = {}
            for j, col2 in enumerate(self.columns):
                result[col1][col2] = self.matrix[i, j]
        return result


class CorrelationAnalyzer:
    """
    상관 분석기

    변수 간 상관관계를 분석합니다.
    """

    def calculate_correlation(
        self,
        data: pl.DataFrame,
        columns: List[str],
        method: CorrelationMethod = CorrelationMethod.PEARSON
    ) -> CorrelationResult:
        """
        상관 행렬 계산

        Args:
            data: 데이터프레임
            columns: 분석할 컬럼 목록
            method: 상관 계수 방법

        Returns:
            상관 분석 결과
        """
        # 데이터 추출
        logger.debug("statistics.calculate_correlation", extra={"method": method.value, "columns": columns})
        valid_columns = [c for c in columns if c in data.columns]
        subset = data.select(valid_columns).to_numpy()

        n = len(valid_columns)
        matrix = np.zeros((n, n))
        p_matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i, j] = 1.0
                    p_matrix[i, j] = np.nan
                else:
                    corr, p_value = self.pairwise_correlation(
                        subset[:, i], subset[:, j], method
                    )
                    matrix[i, j] = corr
                    p_matrix[i, j] = p_value

        return CorrelationResult(
            matrix=matrix,
            columns=valid_columns,
            method=method,
            p_value_matrix=p_matrix
        )

    def pairwise_correlation(
        self,
        x: np.ndarray,
        y: np.ndarray,
        method: CorrelationMethod = CorrelationMethod.PEARSON
    ) -> Tuple[float, float]:
        """
        두 변수 간 상관계수 계산

        Args:
            x: 첫 번째 변수
            y: 두 번째 변수
            method: 상관 계수 방법

        Returns:
            (상관계수, p-value) 튜플
        """
        # NaN 제거
        mask = ~(np.isnan(x) | np.isnan(y))
        x_clean = x[mask]
        y_clean = y[mask]

        if len(x_clean) < 3:
            return 0.0, 1.0

        if method == CorrelationMethod.PEARSON:
            corr, p_value = stats.pearsonr(x_clean, y_clean)
        elif method == CorrelationMethod.SPEARMAN:
            corr, p_value = stats.spearmanr(x_clean, y_clean)
        elif method == CorrelationMethod.KENDALL:
            corr, p_value = stats.kendalltau(x_clean, y_clean)
        else:
            corr, p_value = 0.0, 1.0

        return corr, p_value

    def get_p_value_matrix(self, result: CorrelationResult) -> np.ndarray:
        """상관 행렬의 p-value 행렬 반환"""
        return result.p_value_matrix

    def get_significant_pairs(
        self,
        result: CorrelationResult,
        alpha: float = 0.05,
        min_correlation: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        유의한 상관 쌍 찾기

        Args:
            result: 상관 분석 결과
            alpha: 유의 수준
            min_correlation: 최소 상관계수 절대값

        Returns:
            유의한 상관 쌍 목록
        """
        pairs = []
        n = len(result.columns)

        for i in range(n):
            for j in range(i + 1, n):
                corr = result.matrix[i, j]
                p_value = result.p_value_matrix[i, j]

                if p_value < alpha and abs(corr) >= min_correlation:
                    pairs.append({
                        "col1": result.columns[i],
                        "col2": result.columns[j],
                        "correlation": corr,
                        "p_value": p_value
                    })

        return sorted(pairs, key=lambda x: abs(x["correlation"]), reverse=True)


class ClusterMethod(Enum):
    """클러스터링 방법"""
    KMEANS = "kmeans"
    HIERARCHICAL = "hierarchical"
    DBSCAN = "dbscan"


@dataclass
class ClusterResult:
    """클러스터링 결과"""
    labels: np.ndarray
    n_clusters: int
    method: ClusterMethod
    centers: Optional[np.ndarray] = None
    inertia: Optional[float] = None
    silhouette: Optional[float] = None
    dendrogram_data: Optional[Dict] = None


class ClusterAnalyzer:
    """
    클러스터 분석기

    K-Means, 계층적 클러스터링, DBSCAN 등을 지원합니다.
    """

    def cluster(
        self,
        data: pl.DataFrame,
        columns: List[str],
        method: ClusterMethod = ClusterMethod.KMEANS,
        n_clusters: int = 3,
        **kwargs
    ) -> ClusterResult:
        """
        클러스터링 수행

        Args:
            data: 데이터프레임
            columns: 클러스터링에 사용할 컬럼
            method: 클러스터링 방법
            n_clusters: 클러스터 수 (K-Means, Hierarchical)
            **kwargs: 추가 파라미터

        Returns:
            클러스터링 결과
        """
        # 데이터 추출 및 정규화
        logger.debug("statistics.cluster", extra={"method": method.value, "n_clusters": n_clusters})
        valid_columns = [c for c in columns if c in data.columns]
        X = data.select(valid_columns).to_numpy()

        # NaN 처리
        X = np.nan_to_num(X, nan=0.0)

        # 정규화
        X_mean = np.mean(X, axis=0)
        X_std = np.std(X, axis=0)
        X_std[X_std == 0] = 1  # 0으로 나누기 방지
        X_normalized = (X - X_mean) / X_std

        if method == ClusterMethod.KMEANS:
            return self._kmeans_cluster(X_normalized, n_clusters)
        elif method == ClusterMethod.HIERARCHICAL:
            return self._hierarchical_cluster(X_normalized, n_clusters)
        elif method == ClusterMethod.DBSCAN:
            eps = kwargs.get("eps", 0.5)
            min_samples = kwargs.get("min_samples", 5)
            return self._dbscan_cluster(X_normalized, eps, min_samples)

        return ClusterResult(
            labels=np.zeros(len(X)),
            n_clusters=1,
            method=method
        )

    def _kmeans_cluster(
        self,
        X: np.ndarray,
        n_clusters: int,
        max_iter: int = 100
    ) -> ClusterResult:
        """K-Means 클러스터링"""
        n_samples = len(X)

        # 초기 중심 (K-Means++ 단순화 버전)
        centers = X[np.random.choice(n_samples, n_clusters, replace=False)]

        for _ in range(max_iter):
            # 각 포인트를 가장 가까운 중심에 할당
            distances = np.sqrt(((X[:, np.newaxis] - centers) ** 2).sum(axis=2))
            labels = np.argmin(distances, axis=1)

            # 중심 업데이트
            new_centers = np.array([
                X[labels == k].mean(axis=0) if np.sum(labels == k) > 0 else centers[k]
                for k in range(n_clusters)
            ])

            # 수렴 확인
            if np.allclose(centers, new_centers):
                break

            centers = new_centers

        # Inertia 계산
        inertia = sum(
            ((X[labels == k] - centers[k]) ** 2).sum()
            for k in range(n_clusters)
        )

        return ClusterResult(
            labels=labels,
            n_clusters=n_clusters,
            method=ClusterMethod.KMEANS,
            centers=centers,
            inertia=inertia
        )

    def _hierarchical_cluster(
        self,
        X: np.ndarray,
        n_clusters: int
    ) -> ClusterResult:
        """계층적 클러스터링"""
        # 연결 행렬 계산
        linkage_matrix = hierarchy.linkage(X, method='ward')

        # 클러스터 할당
        labels = hierarchy.fcluster(linkage_matrix, n_clusters, criterion='maxclust') - 1

        return ClusterResult(
            labels=labels,
            n_clusters=n_clusters,
            method=ClusterMethod.HIERARCHICAL,
            dendrogram_data={"linkage": linkage_matrix}
        )

    def _dbscan_cluster(
        self,
        X: np.ndarray,
        eps: float,
        min_samples: int
    ) -> ClusterResult:
        """DBSCAN 클러스터링"""
        n_samples = len(X)
        labels = np.full(n_samples, -1)
        cluster_id = 0

        visited = np.zeros(n_samples, dtype=bool)

        for i in range(n_samples):
            if visited[i]:
                continue

            visited[i] = True

            # 이웃 찾기
            distances = np.sqrt(((X - X[i]) ** 2).sum(axis=1))
            neighbors = np.where(distances < eps)[0]

            if len(neighbors) < min_samples:
                continue

            # 새 클러스터 시작
            labels[i] = cluster_id
            seed_set = list(neighbors)

            j = 0
            while j < len(seed_set):
                q = seed_set[j]

                if not visited[q]:
                    visited[q] = True
                    distances_q = np.sqrt(((X - X[q]) ** 2).sum(axis=1))
                    neighbors_q = np.where(distances_q < eps)[0]

                    if len(neighbors_q) >= min_samples:
                        seed_set.extend(neighbors_q)

                if labels[q] == -1:
                    labels[q] = cluster_id

                j += 1

            cluster_id += 1

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

        return ClusterResult(
            labels=labels,
            n_clusters=n_clusters,
            method=ClusterMethod.DBSCAN
        )

    def get_cluster_statistics(
        self,
        result: ClusterResult,
        data: pl.DataFrame,
        columns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        클러스터별 통계

        Returns:
            클러스터별 통계 목록
        """
        X = data.select(columns).to_numpy()
        statistics = []

        for k in range(result.n_clusters):
            mask = result.labels == k
            cluster_data = X[mask]

            stat = {
                "cluster_id": k,
                "size": int(np.sum(mask)),
                "center": cluster_data.mean(axis=0).tolist() if len(cluster_data) > 0 else [],
                "std": cluster_data.std(axis=0).tolist() if len(cluster_data) > 0 else []
            }
            statistics.append(stat)

        return statistics

    def silhouette_score(
        self,
        result: ClusterResult,
        data: pl.DataFrame,
        columns: List[str]
    ) -> float:
        """
        실루엣 점수 계산

        Returns:
            실루엣 점수 (-1 ~ 1)
        """
        X = data.select(columns).to_numpy()
        labels = result.labels

        n_samples = len(X)
        if len(set(labels)) < 2:
            return 0.0

        scores = []

        for i in range(n_samples):
            # a(i): 같은 클러스터 내 평균 거리
            same_cluster = X[labels == labels[i]]
            if len(same_cluster) > 1:
                a = np.mean(np.sqrt(((same_cluster - X[i]) ** 2).sum(axis=1)))
            else:
                a = 0

            # b(i): 다른 클러스터와의 최소 평균 거리
            b = np.inf
            for k in set(labels):
                if k == labels[i] or k == -1:
                    continue
                other_cluster = X[labels == k]
                if len(other_cluster) > 0:
                    avg_dist = np.mean(np.sqrt(((other_cluster - X[i]) ** 2).sum(axis=1)))
                    b = min(b, avg_dist)

            if b == np.inf:
                b = 0

            # 실루엣 점수
            s = (b - a) / max(a, b) if max(a, b) > 0 else 0
            scores.append(s)

        return np.mean(scores)

    def find_optimal_k(
        self,
        data: pl.DataFrame,
        columns: List[str],
        k_range: Tuple[int, int] = (2, 10)
    ) -> Tuple[List[int], List[float]]:
        """
        엘보우 방법으로 최적 k 찾기

        Returns:
            (k 값 목록, inertia 값 목록)
        """
        k_values = list(range(k_range[0], k_range[1]))
        inertias = []

        for k in k_values:
            result = self.cluster(data, columns, ClusterMethod.KMEANS, k)
            inertias.append(result.inertia)

        return k_values, inertias


class TimeSeriesAnalyzer:
    """
    시계열 분석기

    이동 평균, 분해, 자기상관 분석 등을 제공합니다.
    """

    def moving_average(
        self,
        values: np.ndarray,
        window: int = 5
    ) -> np.ndarray:
        """
        이동 평균

        Args:
            values: 시계열 값
            window: 윈도우 크기

        Returns:
            이동 평균 배열
        """
        result = np.full_like(values, np.nan, dtype=float)

        for i in range(window - 1, len(values)):
            result[i] = np.mean(values[i - window + 1:i + 1])

        return result

    def exponential_smoothing(
        self,
        values: np.ndarray,
        alpha: float = 0.3
    ) -> np.ndarray:
        """
        지수 평활

        Args:
            values: 시계열 값
            alpha: 평활 계수 (0 < alpha <= 1)

        Returns:
            평활된 배열
        """
        result = np.zeros_like(values, dtype=float)
        result[0] = values[0]

        for i in range(1, len(values)):
            result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]

        return result

    def decompose(
        self,
        values: np.ndarray,
        period: int = 12,
        model: str = "additive"
    ) -> Dict[str, np.ndarray]:
        """
        시계열 분해 (트렌드 + 계절성 + 잔차)

        Args:
            values: 시계열 값
            period: 계절성 주기
            model: 분해 모델 ("additive" 또는 "multiplicative")

        Returns:
            {"trend", "seasonal", "residual"} 딕셔너리
        """
        n = len(values)

        # 트렌드 (이동 평균)
        trend = self.moving_average(values, window=period)

        # 계절성 제거된 값
        if model == "additive":
            detrended = values - trend
        else:
            detrended = values / np.where(trend != 0, trend, 1)

        # 계절성 패턴 추출
        seasonal = np.zeros(n)
        for i in range(period):
            indices = np.arange(i, n, period)
            valid = ~np.isnan(detrended[indices])
            if np.sum(valid) > 0:
                pattern = np.nanmean(detrended[indices])
                seasonal[indices] = pattern

        # 잔차
        if model == "additive":
            residual = values - trend - seasonal
        else:
            residual = values / (trend * seasonal + 1e-10)

        return {
            "trend": trend,
            "seasonal": seasonal,
            "residual": residual
        }

    def autocorrelation(
        self,
        values: np.ndarray,
        max_lag: int = 20
    ) -> np.ndarray:
        """
        자기상관 함수 (ACF)

        Args:
            values: 시계열 값
            max_lag: 최대 시차

        Returns:
            자기상관 계수 배열
        """
        n = len(values)
        mean = np.mean(values)
        var = np.var(values)

        if var == 0:
            return np.ones(max_lag + 1)

        acf = np.zeros(max_lag + 1)

        for lag in range(max_lag + 1):
            if lag == 0:
                acf[0] = 1.0
            else:
                cov = np.sum((values[lag:] - mean) * (values[:-lag] - mean)) / n
                acf[lag] = cov / var

        return acf

    def partial_autocorrelation(
        self,
        values: np.ndarray,
        max_lag: int = 10
    ) -> np.ndarray:
        """
        편자기상관 함수 (PACF)

        Args:
            values: 시계열 값
            max_lag: 최대 시차

        Returns:
            편자기상관 계수 배열
        """
        acf = self.autocorrelation(values, max_lag)
        pacf = np.zeros(max_lag + 1)
        pacf[0] = 1.0

        if max_lag > 0:
            pacf[1] = acf[1]

        # Durbin-Levinson 알고리즘
        phi = np.zeros((max_lag + 1, max_lag + 1))
        phi[1, 1] = acf[1]

        for k in range(2, max_lag + 1):
            numerator = acf[k] - sum(phi[k-1, j] * acf[k-j] for j in range(1, k))
            denominator = 1 - sum(phi[k-1, j] * acf[j] for j in range(1, k))

            if denominator == 0:
                phi[k, k] = 0
            else:
                phi[k, k] = numerator / denominator

            for j in range(1, k):
                phi[k, j] = phi[k-1, j] - phi[k, k] * phi[k-1, k-j]

            pacf[k] = phi[k, k]

        return pacf

    def stationarity_test(
        self,
        values: np.ndarray
    ) -> Dict[str, Any]:
        """
        정상성 검정 (Augmented Dickey-Fuller Test 단순화)

        Returns:
            {"statistic", "p_value", "is_stationary"} 딕셔너리
        """
        # 단순화된 ADF 테스트 (1차 차분 사용)
        diff = np.diff(values)
        lagged = values[:-1]

        # 회귀: diff = alpha + beta * lagged + error
        X = np.column_stack([np.ones(len(lagged)), lagged])
        try:
            coeffs = np.linalg.lstsq(X, diff, rcond=None)[0]
            beta = coeffs[1]

            # 잔차
            residuals = diff - X @ coeffs
            se = np.sqrt(np.sum(residuals**2) / (len(diff) - 2))

            # t-통계량
            X_inv = np.linalg.inv(X.T @ X)
            se_beta = se * np.sqrt(X_inv[1, 1])
            t_stat = beta / se_beta if se_beta != 0 else 0

            # ADF 임계값 (근사)
            critical_values = {0.01: -3.43, 0.05: -2.86, 0.10: -2.57}

            # p-value 근사
            if t_stat < critical_values[0.01]:
                p_value = 0.01
            elif t_stat < critical_values[0.05]:
                p_value = 0.05
            elif t_stat < critical_values[0.10]:
                p_value = 0.10
            else:
                p_value = 0.5

            return {
                "statistic": t_stat,
                "p_value": p_value,
                "is_stationary": p_value < 0.05,
                "critical_values": critical_values
            }

        except Exception as e:
            logger.warning("statistics.stationarity_test.failed", extra={"error": str(e)})
            return {
                "statistic": 0,
                "p_value": 1.0,
                "is_stationary": False
            }

    def detect_seasonality(
        self,
        values: np.ndarray,
        max_period: int = 50
    ) -> Optional[int]:
        """
        계절성 주기 탐지

        Returns:
            탐지된 주기 또는 None
        """
        acf = self.autocorrelation(values, max_period)

        # 피크 찾기
        peaks, _ = find_peaks(acf[1:], height=0.1)

        if len(peaks) > 0:
            return int(peaks[0] + 1)

        return None


class HypothesisTest(Enum):
    """가설 검정 유형"""
    T_TEST_ONE_SAMPLE = "t_test_one_sample"
    T_TEST_TWO_SAMPLE = "t_test_two_sample"
    PAIRED_T_TEST = "paired_t_test"
    ANOVA_ONE_WAY = "anova_one_way"
    CHI_SQUARE = "chi_square"
    NORMALITY = "normality"
    MANN_WHITNEY_U = "mann_whitney_u"
    KRUSKAL_WALLIS = "kruskal_wallis"


@dataclass
class HypothesisTestResult:
    """가설 검정 결과"""
    test_type: HypothesisTest
    statistic: float
    p_value: float
    degrees_of_freedom: Optional[int] = None
    effect_size: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None

    @property
    def is_significant(self) -> bool:
        """유의수준 0.05에서 유의한지"""
        return self.p_value < 0.05

    def get_summary(self) -> str:
        """결과 요약"""
        return (
            f"Test: {self.test_type.value}\n"
            f"Statistic: {self.statistic:.4f}\n"
            f"p-value: {self.p_value:.4e}\n"
            f"Significant (α=0.05): {self.is_significant}"
        )


class HypothesisTester:
    """
    가설 검정기

    다양한 통계적 가설 검정을 수행합니다.
    """

    def t_test_one_sample(
        self,
        sample: np.ndarray,
        population_mean: float
    ) -> HypothesisTestResult:
        """
        단일 표본 t-검정

        H0: 표본 평균 = 모집단 평균
        """
        statistic, p_value = stats.ttest_1samp(sample, population_mean)

        return HypothesisTestResult(
            test_type=HypothesisTest.T_TEST_ONE_SAMPLE,
            statistic=statistic,
            p_value=p_value,
            degrees_of_freedom=len(sample) - 1
        )

    def t_test_two_sample(
        self,
        sample1: np.ndarray,
        sample2: np.ndarray,
        equal_var: bool = True
    ) -> HypothesisTestResult:
        """
        독립 표본 t-검정

        H0: 두 표본의 평균이 같다
        """
        statistic, p_value = stats.ttest_ind(sample1, sample2, equal_var=equal_var)

        # Cohen's d 효과 크기
        pooled_std = np.sqrt(
            ((len(sample1) - 1) * np.var(sample1) + (len(sample2) - 1) * np.var(sample2))
            / (len(sample1) + len(sample2) - 2)
        )
        effect_size = (np.mean(sample1) - np.mean(sample2)) / pooled_std if pooled_std != 0 else 0

        return HypothesisTestResult(
            test_type=HypothesisTest.T_TEST_TWO_SAMPLE,
            statistic=statistic,
            p_value=p_value,
            degrees_of_freedom=len(sample1) + len(sample2) - 2,
            effect_size=effect_size
        )

    def paired_t_test(
        self,
        before: np.ndarray,
        after: np.ndarray
    ) -> HypothesisTestResult:
        """
        대응 표본 t-검정

        H0: 처리 전후 차이가 없다
        """
        statistic, p_value = stats.ttest_rel(before, after)

        # 효과 크기 (Cohen's d for paired samples)
        diff = after - before
        effect_size = np.mean(diff) / np.std(diff) if np.std(diff) != 0 else 0

        return HypothesisTestResult(
            test_type=HypothesisTest.PAIRED_T_TEST,
            statistic=statistic,
            p_value=p_value,
            degrees_of_freedom=len(before) - 1,
            effect_size=effect_size
        )

    def anova_one_way(
        self,
        groups: List[np.ndarray]
    ) -> HypothesisTestResult:
        """
        일원 분산분석

        H0: 모든 그룹의 평균이 같다
        """
        statistic, p_value = stats.f_oneway(*groups)

        # 자유도
        k = len(groups)
        n = sum(len(g) for g in groups)
        df_between = k - 1
        n - k

        # Eta squared 효과 크기
        grand_mean = np.mean([np.mean(g) for g in groups])
        ss_between = sum(len(g) * (np.mean(g) - grand_mean)**2 for g in groups)
        ss_total = sum(np.sum((g - grand_mean)**2) for g in groups)
        eta_squared = ss_between / ss_total if ss_total != 0 else 0

        return HypothesisTestResult(
            test_type=HypothesisTest.ANOVA_ONE_WAY,
            statistic=statistic,
            p_value=p_value,
            degrees_of_freedom=df_between,
            effect_size=eta_squared
        )

    def chi_square_test(
        self,
        observed: np.ndarray
    ) -> HypothesisTestResult:
        """
        카이제곱 독립성 검정

        H0: 변수들이 독립이다
        """
        chi2, p_value, dof, expected = stats.chi2_contingency(observed)

        # Cramér's V 효과 크기
        n = np.sum(observed)
        min_dim = min(observed.shape) - 1
        cramers_v = np.sqrt(chi2 / (n * min_dim)) if n * min_dim > 0 else 0

        return HypothesisTestResult(
            test_type=HypothesisTest.CHI_SQUARE,
            statistic=chi2,
            p_value=p_value,
            degrees_of_freedom=dof,
            effect_size=cramers_v
        )

    def normality_test(
        self,
        sample: np.ndarray
    ) -> HypothesisTestResult:
        """
        정규성 검정 (Shapiro-Wilk)

        H0: 데이터가 정규분포를 따른다
        """
        # 샘플 크기 제한 (Shapiro-Wilk는 5000개까지)
        if len(sample) > 5000:
            sample = np.random.choice(sample, 5000, replace=False)

        statistic, p_value = stats.shapiro(sample)

        return HypothesisTestResult(
            test_type=HypothesisTest.NORMALITY,
            statistic=statistic,
            p_value=p_value
        )

    def mann_whitney_u(
        self,
        sample1: np.ndarray,
        sample2: np.ndarray
    ) -> HypothesisTestResult:
        """
        만-휘트니 U 검정 (비모수)

        H0: 두 그룹의 분포가 같다
        """
        statistic, p_value = stats.mannwhitneyu(sample1, sample2, alternative='two-sided')

        # 효과 크기 (rank-biserial correlation)
        n1, n2 = len(sample1), len(sample2)
        effect_size = 1 - (2 * statistic) / (n1 * n2)

        return HypothesisTestResult(
            test_type=HypothesisTest.MANN_WHITNEY_U,
            statistic=statistic,
            p_value=p_value,
            effect_size=effect_size
        )

    def kruskal_wallis(
        self,
        groups: List[np.ndarray]
    ) -> HypothesisTestResult:
        """
        크루스칼-왈리스 검정 (비모수 ANOVA)

        H0: 모든 그룹의 분포가 같다
        """
        statistic, p_value = stats.kruskal(*groups)

        return HypothesisTestResult(
            test_type=HypothesisTest.KRUSKAL_WALLIS,
            statistic=statistic,
            p_value=p_value,
            degrees_of_freedom=len(groups) - 1
        )


@dataclass
class StatisticalSummary:
    """통계 요약"""
    mean: float
    median: float
    std: float
    var: float
    min: float
    max: float
    q1: float
    q3: float
    iqr: float
    skewness: float
    kurtosis: float
    n: int


class DescriptiveStatistics:
    """
    기술 통계

    기본적인 통계량을 계산합니다.
    """

    def calculate(
        self,
        values: np.ndarray
    ) -> Dict[str, float]:
        """
        기술 통계량 계산

        Args:
            values: 데이터 배열

        Returns:
            통계량 딕셔너리
        """
        values = values[~np.isnan(values)]

        if len(values) == 0:
            logger.warning("statistics.calculate.empty_values")
            return {}

        logger.debug("statistics.calculate", extra={"n": len(values)})
        q1, median, q3 = np.percentile(values, [25, 50, 75])

        return {
            "mean": float(np.mean(values)),
            "median": float(median),
            "std": float(np.std(values)),
            "var": float(np.var(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "q1": float(q1),
            "q3": float(q3),
            "iqr": float(q3 - q1),
            "skewness": float(stats.skew(values)),
            "kurtosis": float(stats.kurtosis(values)),
            "n": len(values),
            "se": float(np.std(values) / np.sqrt(len(values)))  # 표준 오차
        }

    def confidence_interval(
        self,
        values: np.ndarray,
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """
        평균의 신뢰 구간

        Args:
            values: 데이터 배열
            confidence: 신뢰 수준

        Returns:
            (하한, 상한) 튜플
        """
        values = values[~np.isnan(values)]

        if len(values) < 2:
            mean = np.mean(values) if len(values) > 0 else 0
            return (mean, mean)

        mean = np.mean(values)
        se = stats.sem(values)
        h = se * stats.t.ppf((1 + confidence) / 2, len(values) - 1)

        return (mean - h, mean + h)

    def percentile(
        self,
        values: np.ndarray,
        percentiles: List[float]
    ) -> Dict[float, float]:
        """
        백분위수 계산

        Args:
            values: 데이터 배열
            percentiles: 백분위수 목록 (0-100)

        Returns:
            {백분위수: 값} 딕셔너리
        """
        values = values[~np.isnan(values)]

        if len(values) == 0:
            return {p: 0 for p in percentiles}

        results = np.percentile(values, percentiles)

        return {p: float(v) for p, v in zip(percentiles, results)}
