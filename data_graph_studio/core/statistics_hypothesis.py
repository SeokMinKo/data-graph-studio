"""
Statistical Analysis - Hypothesis Testing Module

Provides hypothesis test types, result dataclass, and tester class.
"""

import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


class HypothesisTest(Enum):
    """Enumeration of supported statistical hypothesis test types."""
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
    """Immutable result container for a single hypothesis test.

    Fields:
        test_type — HypothesisTest, the test that produced this result
        statistic — float, the test statistic value (t, F, chi2, U, H, or W)
        p_value — float, two-tailed p-value in [0, 1]
        degrees_of_freedom — int or None, degrees of freedom where applicable
        effect_size — float or None, standardised effect size (Cohen's d, eta², Cramér's V, r)
        confidence_interval — (float, float) or None, 95% CI where computed
    """
    test_type: HypothesisTest
    statistic: float
    p_value: float
    degrees_of_freedom: Optional[int] = None
    effect_size: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None

    @property
    def is_significant(self) -> bool:
        """Return True when p_value < 0.05 (alpha = 0.05 significance level).

        Output: bool — True if the result is statistically significant at alpha=0.05
        """
        return self.p_value < 0.05

    def get_summary(self) -> str:
        """Return a human-readable multi-line summary of the test result.

        Output: str — formatted lines showing test type, statistic, p-value, and significance
        """
        return (
            f"Test: {self.test_type.value}\n"
            f"Statistic: {self.statistic:.4f}\n"
            f"p-value: {self.p_value:.4e}\n"
            f"Significant (α=0.05): {self.is_significant}"
        )


class HypothesisTester:
    """Runs statistical hypothesis tests and returns structured results.

    All methods are stateless — each call is independent.
    Effect sizes are computed alongside the test statistic where standard.
    """

    def t_test_one_sample(
        self,
        sample: np.ndarray,
        population_mean: float
    ) -> HypothesisTestResult:
        """Run a one-sample t-test against a known population mean.

        H0: sample mean equals population_mean.

        Input: sample — np.ndarray, 1-D array of observations (n >= 2)
        Input: population_mean — float, the hypothesised population mean
        Output: HypothesisTestResult with test_type=T_TEST_ONE_SAMPLE, df=n-1
        Raises: ValueError — if sample has fewer than 2 observations (scipy raises)
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
        """Run an independent two-sample t-test with optional Welch correction.

        H0: mean of sample1 equals mean of sample2.
        Effect size is Cohen's d using pooled standard deviation.

        Input: sample1 — np.ndarray, first group observations
        Input: sample2 — np.ndarray, second group observations
        Input: equal_var — bool, True for Student's t-test, False for Welch's t-test
        Output: HypothesisTestResult with test_type=T_TEST_TWO_SAMPLE, df=n1+n2-2, effect_size=Cohen's d
        Raises: ValueError — if either sample is empty (scipy raises)
        """
        statistic, p_value = stats.ttest_ind(sample1, sample2, equal_var=equal_var)

        # Cohen's d effect size
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
        """Run a paired-sample t-test for matched before/after observations.

        H0: mean difference between after and before is zero.
        Effect size is Cohen's d for paired samples (mean diff / std diff).

        Input: before — np.ndarray, pre-treatment observations
        Input: after — np.ndarray, post-treatment observations (same length as before)
        Output: HypothesisTestResult with test_type=PAIRED_T_TEST, df=n-1, effect_size=Cohen's d
        Raises: ValueError — if arrays have different lengths or fewer than 2 pairs
        """
        statistic, p_value = stats.ttest_rel(before, after)

        # Effect size (Cohen's d for paired samples)
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
        """Run a one-way ANOVA across two or more independent groups.

        H0: all group means are equal.
        Effect size is eta-squared (proportion of variance explained by group membership).

        Input: groups — List[np.ndarray], each array contains observations for one group (>= 2 groups)
        Output: HypothesisTestResult with test_type=ANOVA_ONE_WAY, df=k-1, effect_size=eta²
        Raises: ValueError — if fewer than 2 groups are provided
        """
        statistic, p_value = stats.f_oneway(*groups)

        # Degrees of freedom (between-groups)
        k = len(groups)
        n = sum(len(g) for g in groups)
        df_between = k - 1
        n - k

        # Eta squared effect size
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
        """Run a chi-square test of independence on a contingency table.

        H0: the variables forming the rows and columns are independent.
        Effect size is Cramér's V.

        Input: observed — np.ndarray shape (r, c), observed frequency contingency table
        Output: HypothesisTestResult with test_type=CHI_SQUARE, df=dof from scipy, effect_size=Cramér's V
        Raises: ValueError — if any expected cell frequency is zero
        """
        chi2, p_value, dof, expected = stats.chi2_contingency(observed)

        # Cramér's V effect size
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
        """Run a Shapiro-Wilk normality test.

        H0: the data are drawn from a normal distribution.
        Samples larger than 5000 are randomly subsampled to 5000.

        Input: sample — np.ndarray, 1-D array of observations (n >= 3)
        Output: HypothesisTestResult with test_type=NORMALITY, no effect_size
        Raises: ValueError — if sample has fewer than 3 observations (scipy raises)
        Invariants: input sample is not mutated; subsampling uses random.choice without replacement
        """
        # Sample size limit (Shapiro-Wilk supports up to 5000)
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
        """Run a Mann-Whitney U non-parametric two-sample test.

        H0: the two groups have the same distribution.
        Effect size is rank-biserial correlation r = 1 - 2U/(n1*n2).

        Input: sample1 — np.ndarray, first group observations
        Input: sample2 — np.ndarray, second group observations
        Output: HypothesisTestResult with test_type=MANN_WHITNEY_U, effect_size=rank-biserial r
        Raises: ValueError — if either sample is empty
        """
        statistic, p_value = stats.mannwhitneyu(sample1, sample2, alternative='two-sided')

        # Effect size (rank-biserial correlation)
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
        """Run a Kruskal-Wallis non-parametric one-way ANOVA.

        H0: all groups have the same distribution.
        Non-parametric alternative to one-way ANOVA; does not assume normality.

        Input: groups — List[np.ndarray], each array contains observations for one group (>= 2 groups)
        Output: HypothesisTestResult with test_type=KRUSKAL_WALLIS, df=k-1, no effect_size
        Raises: ValueError — if fewer than 2 groups are provided
        """
        statistic, p_value = stats.kruskal(*groups)

        return HypothesisTestResult(
            test_type=HypothesisTest.KRUSKAL_WALLIS,
            statistic=statistic,
            p_value=p_value,
            degrees_of_freedom=len(groups) - 1
        )
