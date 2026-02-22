"""
Statistical Analysis - Hypothesis Testing Module

가설 검정 관련 클래스를 제공합니다.
"""

import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


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
