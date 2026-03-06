"""
Statistical Analysis 테스트 - Spotfire 스타일 통계 분석 도구
"""

import pytest
import numpy as np
import polars as pl

from data_graph_studio.core.statistics import (
    CorrelationMethod,
    CorrelationAnalyzer,
    ClusterMethod,
    ClusterAnalyzer,
    TimeSeriesAnalyzer,
    HypothesisTest,
    HypothesisTester,
    DescriptiveStatistics,
)


class TestCorrelationAnalyzer:
    """CorrelationAnalyzer 테스트"""

    @pytest.fixture
    def analyzer(self):
        return CorrelationAnalyzer()

    @pytest.fixture
    def sample_data(self):
        np.random.seed(42)
        x = np.random.randn(100)
        y = 2 * x + np.random.randn(100) * 0.5  # 강한 양의 상관
        z = -1.5 * x + np.random.randn(100) * 0.5  # 강한 음의 상관
        w = np.random.randn(100)  # 상관 없음

        return pl.DataFrame({"x": x, "y": y, "z": z, "w": w})

    def test_pearson_correlation(self, analyzer, sample_data):
        """피어슨 상관계수"""
        result = analyzer.calculate_correlation(
            sample_data, columns=["x", "y", "z", "w"], method=CorrelationMethod.PEARSON
        )

        assert result is not None
        assert result.matrix.shape == (4, 4)

        # x와 y: 강한 양의 상관
        assert result.matrix[0, 1] > 0.9

        # x와 z: 강한 음의 상관
        assert result.matrix[0, 2] < -0.9

        # x와 w: 약한 상관
        assert abs(result.matrix[0, 3]) < 0.3

    def test_spearman_correlation(self, analyzer, sample_data):
        """스피어만 상관계수"""
        result = analyzer.calculate_correlation(
            sample_data, columns=["x", "y"], method=CorrelationMethod.SPEARMAN
        )

        assert result is not None
        assert result.method == CorrelationMethod.SPEARMAN
        # 스피어만도 강한 양의 상관 보임
        assert result.matrix[0, 1] > 0.8

    def test_kendall_correlation(self, analyzer, sample_data):
        """켄달 타우"""
        result = analyzer.calculate_correlation(
            sample_data, columns=["x", "y"], method=CorrelationMethod.KENDALL
        )

        assert result is not None
        assert result.method == CorrelationMethod.KENDALL

    def test_pairwise_correlation(self, analyzer, sample_data):
        """쌍별 상관계수"""
        corr, p_value = analyzer.pairwise_correlation(
            sample_data["x"].to_numpy(),
            sample_data["y"].to_numpy(),
            method=CorrelationMethod.PEARSON,
        )

        assert corr > 0.9
        assert p_value < 0.01  # 통계적으로 유의

    def test_correlation_significance(self, analyzer, sample_data):
        """상관 유의성 검정"""
        result = analyzer.calculate_correlation(
            sample_data, columns=["x", "y", "w"], method=CorrelationMethod.PEARSON
        )

        p_matrix = analyzer.get_p_value_matrix(result)

        # x와 y: 유의한 상관
        assert p_matrix[0, 1] < 0.05

        # 대각선: NaN 또는 0
        assert np.isnan(p_matrix[0, 0]) or p_matrix[0, 0] == 0


class TestClusterAnalyzer:
    """ClusterAnalyzer 테스트"""

    @pytest.fixture
    def analyzer(self):
        return ClusterAnalyzer()

    @pytest.fixture
    def cluster_data(self):
        """클러스터 테스트 데이터 (3개 클러스터)"""
        np.random.seed(42)
        # 클러스터 1: 중심 (0, 0)
        c1 = np.random.randn(30, 2) + [0, 0]
        # 클러스터 2: 중심 (5, 5)
        c2 = np.random.randn(30, 2) + [5, 5]
        # 클러스터 3: 중심 (-5, 5)
        c3 = np.random.randn(30, 2) + [-5, 5]

        data = np.vstack([c1, c2, c3])
        return pl.DataFrame({"x": data[:, 0], "y": data[:, 1]})

    def test_kmeans_clustering(self, analyzer, cluster_data):
        """K-Means 클러스터링"""
        result = analyzer.cluster(
            cluster_data, columns=["x", "y"], method=ClusterMethod.KMEANS, n_clusters=3
        )

        assert result is not None
        assert len(result.labels) == 90
        assert result.n_clusters == 3
        assert len(set(result.labels)) == 3

    def test_hierarchical_clustering(self, analyzer, cluster_data):
        """계층적 클러스터링"""
        result = analyzer.cluster(
            cluster_data,
            columns=["x", "y"],
            method=ClusterMethod.HIERARCHICAL,
            n_clusters=3,
        )

        assert result is not None
        assert len(result.labels) == 90
        assert result.n_clusters == 3

    def test_dbscan_clustering(self, analyzer, cluster_data):
        """DBSCAN 클러스터링"""
        result = analyzer.cluster(
            cluster_data,
            columns=["x", "y"],
            method=ClusterMethod.DBSCAN,
            eps=1.0,
            min_samples=5,
        )

        assert result is not None
        assert len(result.labels) == 90
        # DBSCAN은 클러스터 수가 자동 결정됨 (노이즈 포인트는 -1)

    def test_cluster_statistics(self, analyzer, cluster_data):
        """클러스터 통계"""
        result = analyzer.cluster(
            cluster_data, columns=["x", "y"], method=ClusterMethod.KMEANS, n_clusters=3
        )

        stats = analyzer.get_cluster_statistics(result, cluster_data, ["x", "y"])

        assert len(stats) == 3
        for cluster_stat in stats:
            assert "center" in cluster_stat
            assert "size" in cluster_stat

    def test_silhouette_score(self, analyzer, cluster_data):
        """실루엣 스코어"""
        result = analyzer.cluster(
            cluster_data, columns=["x", "y"], method=ClusterMethod.KMEANS, n_clusters=3
        )

        score = analyzer.silhouette_score(result, cluster_data, ["x", "y"])

        assert score is not None
        assert -1 <= score <= 1
        # 잘 분리된 클러스터이므로 높은 점수
        assert score > 0.5

    def test_find_optimal_k(self, analyzer, cluster_data):
        """최적 클러스터 수 찾기 (엘보우 방법)"""
        k_values, scores = analyzer.find_optimal_k(
            cluster_data, columns=["x", "y"], k_range=(2, 6)
        )

        assert len(k_values) == 4
        assert len(scores) == 4


class TestTimeSeriesAnalyzer:
    """TimeSeriesAnalyzer 테스트"""

    @pytest.fixture
    def analyzer(self):
        return TimeSeriesAnalyzer()

    @pytest.fixture
    def time_series_data(self):
        """시계열 테스트 데이터"""
        np.random.seed(42)
        n = 100
        # 트렌드 + 계절성 + 노이즈
        trend = np.linspace(0, 10, n)
        seasonal = 3 * np.sin(np.linspace(0, 8 * np.pi, n))
        noise = np.random.randn(n) * 0.5

        values = trend + seasonal + noise

        return pl.DataFrame(
            {
                "date": pl.date_range(
                    pl.date(2020, 1, 1), pl.date(2020, 4, 9), eager=True
                ),
                "value": values,
            }
        )

    def test_moving_average(self, analyzer, time_series_data):
        """이동 평균"""
        values = time_series_data["value"].to_numpy()

        ma = analyzer.moving_average(values, window=5)

        assert len(ma) == len(values)
        # 처음 몇 개 값은 NaN
        assert np.isnan(ma[0])
        assert not np.isnan(ma[5])

    def test_exponential_smoothing(self, analyzer, time_series_data):
        """지수 평활"""
        values = time_series_data["value"].to_numpy()

        smoothed = analyzer.exponential_smoothing(values, alpha=0.3)

        assert len(smoothed) == len(values)
        # 첫 값은 원본과 동일
        assert smoothed[0] == values[0]

    def test_decompose(self, analyzer, time_series_data):
        """시계열 분해"""
        values = time_series_data["value"].to_numpy()

        result = analyzer.decompose(values, period=12)

        assert result is not None
        assert "trend" in result
        assert "seasonal" in result
        assert "residual" in result
        assert len(result["trend"]) == len(values)

    def test_autocorrelation(self, analyzer, time_series_data):
        """자기상관"""
        values = time_series_data["value"].to_numpy()

        acf = analyzer.autocorrelation(values, max_lag=20)

        assert len(acf) == 21  # lag 0 ~ 20
        assert acf[0] == 1.0  # lag 0은 항상 1

    def test_partial_autocorrelation(self, analyzer, time_series_data):
        """편자기상관"""
        values = time_series_data["value"].to_numpy()

        pacf = analyzer.partial_autocorrelation(values, max_lag=10)

        assert len(pacf) == 11

    def test_stationarity_test(self, analyzer, time_series_data):
        """정상성 검정 (ADF 테스트)"""
        values = time_series_data["value"].to_numpy()

        result = analyzer.stationarity_test(values)

        assert "statistic" in result
        assert "p_value" in result
        assert "is_stationary" in result

    def test_seasonality_detection(self, analyzer, time_series_data):
        """계절성 탐지"""
        values = time_series_data["value"].to_numpy()

        period = analyzer.detect_seasonality(values)

        # 주기가 감지되어야 함
        assert period is not None or period == 0  # 데이터에 따라 다름


class TestHypothesisTester:
    """HypothesisTester 테스트"""

    @pytest.fixture
    def tester(self):
        return HypothesisTester()

    def test_t_test_one_sample(self, tester):
        """단일 표본 t-검정"""
        np.random.seed(42)
        sample = np.random.randn(100) + 5  # 평균 약 5

        result = tester.t_test_one_sample(sample, population_mean=5)

        assert result is not None
        assert result.test_type == HypothesisTest.T_TEST_ONE_SAMPLE
        # 귀무가설 기각 안됨 (실제 평균이 5에 가까움)
        assert result.p_value > 0.05

    def test_t_test_two_sample(self, tester):
        """독립 표본 t-검정"""
        np.random.seed(42)
        group1 = np.random.randn(50)
        group2 = np.random.randn(50) + 2  # 다른 평균

        result = tester.t_test_two_sample(group1, group2)

        assert result is not None
        assert result.test_type == HypothesisTest.T_TEST_TWO_SAMPLE
        # 귀무가설 기각 (두 그룹의 평균이 다름)
        assert result.p_value < 0.05

    def test_paired_t_test(self, tester):
        """대응 표본 t-검정"""
        np.random.seed(42)
        before = np.random.randn(30)
        after = before + 0.5 + np.random.randn(30) * 0.2  # 처리 효과 있음

        result = tester.paired_t_test(before, after)

        assert result is not None
        assert result.test_type == HypothesisTest.PAIRED_T_TEST
        # 처리 효과가 유의함
        assert result.p_value < 0.05

    def test_anova_one_way(self, tester):
        """일원 분산분석"""
        np.random.seed(42)
        group1 = np.random.randn(30)
        group2 = np.random.randn(30) + 1
        group3 = np.random.randn(30) + 2

        result = tester.anova_one_way([group1, group2, group3])

        assert result is not None
        assert result.test_type == HypothesisTest.ANOVA_ONE_WAY
        # 그룹 간 차이가 유의함
        assert result.p_value < 0.05

    def test_chi_square_test(self, tester):
        """카이제곱 검정"""
        observed = np.array([[10, 20, 30], [15, 25, 35]])

        result = tester.chi_square_test(observed)

        assert result is not None
        assert result.test_type == HypothesisTest.CHI_SQUARE
        assert result.degrees_of_freedom is not None

    def test_normality_test(self, tester):
        """정규성 검정 (샤피로-윌크)"""
        np.random.seed(42)
        normal_data = np.random.randn(50)
        non_normal_data = np.random.exponential(1, 50)

        result_normal = tester.normality_test(normal_data)
        result_non_normal = tester.normality_test(non_normal_data)

        assert result_normal.p_value > 0.05  # 정규분포
        assert result_non_normal.p_value < 0.05  # 비정규분포

    def test_mann_whitney_u(self, tester):
        """만-휘트니 U 검정 (비모수)"""
        np.random.seed(42)
        group1 = np.random.randn(30)
        group2 = np.random.randn(30) + 2

        result = tester.mann_whitney_u(group1, group2)

        assert result is not None
        assert result.test_type == HypothesisTest.MANN_WHITNEY_U
        assert result.p_value < 0.05


class TestDescriptiveStatistics:
    """DescriptiveStatistics 테스트"""

    @pytest.fixture
    def stats(self):
        return DescriptiveStatistics()

    @pytest.fixture
    def sample_data(self):
        np.random.seed(42)
        return np.random.randn(100) * 10 + 50  # 평균 50, 표준편차 10

    def test_basic_statistics(self, stats, sample_data):
        """기본 통계량"""
        result = stats.calculate(sample_data)

        assert result is not None
        assert "mean" in result
        assert "median" in result
        assert "std" in result
        assert "var" in result
        assert "min" in result
        assert "max" in result

        # 평균은 50 근처
        assert 45 < result["mean"] < 55

    def test_percentiles(self, stats, sample_data):
        """백분위수"""
        result = stats.calculate(sample_data)

        assert "q1" in result
        assert "q3" in result
        assert "iqr" in result

        assert result["q1"] < result["median"] < result["q3"]

    def test_skewness_kurtosis(self, stats, sample_data):
        """왜도와 첨도"""
        result = stats.calculate(sample_data)

        assert "skewness" in result
        assert "kurtosis" in result

        # 정규분포에 가까우므로
        assert abs(result["skewness"]) < 1
        assert abs(result["kurtosis"]) < 2

    def test_confidence_interval(self, stats, sample_data):
        """신뢰 구간"""
        ci = stats.confidence_interval(sample_data, confidence=0.95)

        assert ci is not None
        assert len(ci) == 2
        assert ci[0] < ci[1]

        # 평균이 신뢰 구간 내에 있음
        mean = np.mean(sample_data)
        assert ci[0] < mean < ci[1]
