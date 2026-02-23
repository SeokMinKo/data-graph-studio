"""
ComparisonEngine — 데이터셋 비교 분석 모듈

DatasetManager를 참조하여 멀티 데이터셋 간 비교, 통계 검정,
상관 분석, 기술통계 비교, 정규성 검정을 수행한다.
비교 연산 시 datasets snapshot을 사용하여 원본 변경에 안전하다.

Pure statistical helpers live in comparison_algorithms.py.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

import polars as pl
import numpy as np

try:
    from scipy.stats import pearsonr, spearmanr, ttest_ind, mannwhitneyu, ks_2samp
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from .dataset_manager import DatasetManager
from .comparison_algorithms import select_test_type, interpret_test_result, run_normality_test
from .file_loader import _run_with_timeout
from .constants import COMPARISON_TIMEOUT
from data_graph_studio.core.metrics import get_metrics

logger = logging.getLogger(__name__)


class IComparisonEngine(ABC):
    """Abstract interface for dataset comparison."""

    @abstractmethod
    def calculate_difference(self, dataset_a_id: str, dataset_b_id: str, value_column: str, key_column=None):
        """Calculate difference between two datasets."""
        ...

    @abstractmethod
    def get_comparison_statistics(self, dataset_ids: list, value_column: str) -> dict:
        """Calculate comparison statistics for multiple datasets."""
        ...


class ComparisonEngine(IComparisonEngine):
    """데이터셋 비교 분석 클래스.

    DatasetManager를 참조하여 데이터셋에 접근하고,
    비교 연산 시 DataFrame의 snapshot을 사용한다.

    Attributes:
        _datasets: DatasetManager 참조.
    """

    def __init__(self, datasets: DatasetManager):
        """ComparisonEngine을 초기화한다.

        Args:
            datasets: 데이터셋 접근에 사용할 DatasetManager 참조.
        """
        self._datasets = datasets

    def _get_df_snapshot(self, dataset_id: str) -> Optional[pl.DataFrame]:
        """데이터셋의 DataFrame snapshot을 가져온다.

        연산 중 원본 변경에 안전하도록 참조를 고정한다.
        Polars DataFrame은 immutable이므로 참조 고정만으로 충분하다.

        Args:
            dataset_id: 데이터셋 ID.

        Returns:
            DataFrame 또는 None.
        """
        return self._datasets.get_dataset_df(dataset_id)

    def align_datasets(
        self,
        dataset_ids: List[str],
        key_column: str,
        fill_strategy: str = "null",
    ) -> Dict[str, pl.DataFrame]:
        """Align multiple datasets on a shared key column, filling gaps according to a fill strategy.

        Input:
            dataset_ids: Non-empty list of dataset ID strings to align; datasets that do not
                contain key_column are silently skipped.
            key_column: Column name used as the alignment key; must exist in at least one
                referenced dataset.
            fill_strategy: How to fill missing values after the join. One of "null" (keep
                nulls), "forward", "backward", or "interpolate" (float columns only).
                Default "null".

        Output:
            Dict mapping dataset_id to the aligned pl.DataFrame. Keys include only datasets
            that contained key_column. Returns an empty dict if dataset_ids is empty or no
            dataset contains key_column.

        Raises:
            None

        Invariants:
            - All returned DataFrames share the same key_column value set (union of all keys).
            - Row count per aligned DataFrame == number of unique key values across all datasets.
            - Column sets per dataset are unchanged beyond added fill values.
        """
        if not dataset_ids:
            return {}
        # Snapshot 확보
        snapshots: Dict[str, pl.DataFrame] = {}
        all_keys: set = set()
        for did in dataset_ids:
            df = self._get_df_snapshot(did)
            if df is not None and key_column in df.columns:
                snapshots[did] = df
                all_keys.update(df[key_column].unique().to_list())

        if not all_keys:
            return {}

        key_df = pl.DataFrame({key_column: sorted(list(all_keys))})
        aligned: Dict[str, pl.DataFrame] = {}

        for did, df in snapshots.items():
            aligned_df = key_df.join(df, on=key_column, how="left")

            if fill_strategy == "forward":
                aligned_df = aligned_df.fill_null(strategy="forward")
            elif fill_strategy == "backward":
                aligned_df = aligned_df.fill_null(strategy="backward")
            elif fill_strategy == "interpolate":
                for col in aligned_df.columns:
                    if aligned_df[col].dtype in [pl.Float32, pl.Float64]:
                        aligned_df = aligned_df.with_columns(pl.col(col).interpolate())

            aligned[did] = aligned_df

        return aligned

    def calculate_difference(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        value_column: str,
        key_column: Optional[str] = None,
    ) -> Optional[pl.DataFrame]:
        """Calculate row-wise difference between two datasets for a given value column.

        Input:
            dataset_a_id: ID of the first (base) dataset; must be registered in DatasetManager.
            dataset_b_id: ID of the second (comparison) dataset; must be registered in DatasetManager.
            value_column: Name of the numeric column to compare; must exist in both datasets.
            key_column: Optional column name for key-based joining. If None, comparison is done
                by positional index, truncating to the shorter dataset length.

        Output:
            pl.DataFrame with columns [key_column|"index", "value_a", "value_b", "diff",
            "diff_pct"], or None if either dataset is missing or value_column is absent.

        Raises:
            DataLoadError: If the operation exceeds COMPARISON_TIMEOUT seconds.

        Invariants:
            - "diff" == value_a - value_b for each row.
            - "diff_pct" == (value_a - value_b) / abs(value_b) * 100.
            - Operation is timed via MetricsCollector.timed_operation("comparison.calculate_difference").
            - metrics "comparison.calculated" counter is incremented on success.
        """
        return _run_with_timeout(
            lambda: self._calculate_difference_impl(
                dataset_a_id, dataset_b_id, value_column, key_column
            ),
            timeout_s=COMPARISON_TIMEOUT,
            operation="comparison.calculate_difference",
        )

    def _calculate_difference_impl(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        value_column: str,
        key_column: Optional[str],
    ) -> Optional[pl.DataFrame]:
        """Internal implementation for calculate_difference; runs under timeout."""
        with get_metrics().timed_operation("comparison.calculate_difference"):
            df_a = self._get_df_snapshot(dataset_a_id)
            df_b = self._get_df_snapshot(dataset_b_id)

            if df_a is None or df_b is None:
                return None
            if value_column not in df_a.columns or value_column not in df_b.columns:
                return None

            if key_column:
                if key_column not in df_a.columns or key_column not in df_b.columns:
                    return None
                merged = df_a.select([key_column, value_column]).join(
                    df_b.select([key_column, value_column]),
                    on=key_column, how="full", suffix="_b",
                )
                value_a_col = value_column
                value_b_col = f"{value_column}_b"
            else:
                min_len = min(len(df_a), len(df_b))
                merged = pl.DataFrame({
                    "index": list(range(min_len)),
                    value_column: df_a[value_column].head(min_len),
                    f"{value_column}_b": df_b[value_column].head(min_len),
                })
                key_column = "index"
                value_a_col = value_column
                value_b_col = f"{value_column}_b"

            result = merged.with_columns([
                (pl.col(value_a_col) - pl.col(value_b_col)).alias("diff"),
                ((pl.col(value_a_col) - pl.col(value_b_col)) /
                 pl.col(value_b_col).abs() * 100).alias("diff_pct"),
            ]).rename({value_a_col: "value_a", value_b_col: "value_b"})

            get_metrics().increment("comparison.calculated")
            return result

    def get_comparison_statistics(
        self,
        dataset_ids: List[str],
        value_column: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Compute summary statistics for a value column across multiple datasets.

        Input:
            dataset_ids: List of dataset ID strings to include; datasets that do not exist
                or do not contain value_column are silently skipped.
            value_column: Name of the numeric column to summarise; must have a numeric dtype
                (Int8–Int64, Float32, Float64) to be included.

        Output:
            Dict mapping dataset_id to a stats dict with keys: name, color, count, sum, mean,
            median, std, min, max, q1, q3. Datasets that are skipped are absent from the dict.

        Raises:
            DataLoadError: If the operation exceeds COMPARISON_TIMEOUT seconds.

        Invariants:
            - Only numeric columns produce entries; non-numeric datasets are skipped silently.
            - Does not modify any dataset state.
        """
        return _run_with_timeout(
            lambda: self._get_comparison_statistics_impl(dataset_ids, value_column),
            timeout_s=COMPARISON_TIMEOUT,
            operation="comparison.get_comparison_statistics",
        )

    def _get_comparison_statistics_impl(
        self,
        dataset_ids: List[str],
        value_column: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Internal implementation for get_comparison_statistics; runs under timeout."""
        stats: Dict[str, Dict[str, Any]] = {}

        for did in dataset_ids:
            ds = self._datasets.get_dataset(did)
            df = self._get_df_snapshot(did)
            if ds is None or df is None or value_column not in df.columns:
                continue

            series = df[value_column]
            if series.dtype not in [pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                                    pl.Float32, pl.Float64]:
                continue

            stats[did] = {
                "name": ds.name,
                "color": ds.color,
                "count": len(series),
                "sum": series.sum(),
                "mean": series.mean(),
                "median": series.median(),
                "std": series.std(),
                "min": series.min(),
                "max": series.max(),
                "q1": series.quantile(0.25),
                "q3": series.quantile(0.75),
            }

        return stats

    def merge_datasets(
        self,
        dataset_ids: List[str],
        key_column: Optional[str] = None,
        how: str = "full",
    ) -> Optional[pl.DataFrame]:
        """Merge multiple datasets into a single DataFrame.

        Input:
            dataset_ids: List of dataset ID strings to merge; datasets that do not exist
                or have no DataFrame are silently skipped.
            key_column: Optional join key column name. If None, datasets are vertically
                concatenated (diagonal concat to handle schema differences).
            how: Join strategy when key_column is provided: "inner", "outer", "left", or
                "right" (default "full").

        Output:
            Merged pl.DataFrame, or None if no valid datasets were found.

        Raises:
            None

        Invariants:
            - Each source dataset is tagged with "_dataset_id" and "_dataset_name" columns.
            - When key_column is None, result schema is the union of all dataset schemas.
            - When key_column is provided, columns from dataset N are suffixed with "_N".
        """
        dfs = []
        for did in dataset_ids:
            ds = self._datasets.get_dataset(did)
            df = self._get_df_snapshot(did)
            if ds is not None and df is not None:
                df = df.with_columns(
                    pl.lit(did).alias("_dataset_id"),
                    pl.lit(ds.name).alias("_dataset_name"),
                )
                dfs.append(df)

        if not dfs:
            return None

        if key_column is None:
            return pl.concat(dfs, how="diagonal")

        result = dfs[0]
        for i, df in enumerate(dfs[1:], 2):
            result = result.join(df, on=key_column, how=how, suffix=f"_{i}")
        return result

    def perform_statistical_test(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        value_column: str,
        test_type: str = "auto",
    ) -> Optional[Dict[str, Any]]:
        """Perform a two-sample statistical test between datasets for a given column.

        Input:
            dataset_a_id: ID of the first dataset; must be registered in DatasetManager.
            dataset_b_id: ID of the second dataset; must be registered in DatasetManager.
            value_column: Name of the numeric column to test; must exist in both datasets.
            test_type: One of "auto" (select automatically), "ttest" (Welch's t-test),
                "mannwhitney" (Mann-Whitney U), or "ks" (Kolmogorov-Smirnov).
                Default "auto".

        Output:
            Dict with keys: test_name, statistic, p_value, is_significant, effect_size,
            interpretation. On error, dict contains "error" key with a description and
            remaining keys set to None.

        Raises:
            None (errors are captured in the returned dict).

        Invariants:
            - Returns an error dict (not None) when scipy is unavailable.
            - is_significant == (p_value < 0.05) when a test succeeds.
            - effect_size is Cohen's d calculated using pooled variance.
        """
        if not HAS_SCIPY:
            return {
                "error": "scipy is not installed",
                "test_name": "none", "statistic": None,
                "p_value": None, "is_significant": None,
                "effect_size": None,
                "interpretation": "Statistical testing requires scipy",
            }

        ds_a = self._datasets.get_dataset(dataset_a_id)
        ds_b = self._datasets.get_dataset(dataset_b_id)
        df_a = self._get_df_snapshot(dataset_a_id)
        df_b = self._get_df_snapshot(dataset_b_id)

        if ds_a is None or ds_b is None or df_a is None or df_b is None:
            return {"error": "Dataset not found"}

        if value_column not in df_a.columns or value_column not in df_b.columns:
            return {"error": f"Column '{value_column}' not found in both datasets"}

        data_a = df_a[value_column].drop_nulls().to_numpy()
        data_b = df_b[value_column].drop_nulls().to_numpy()

        if len(data_a) < 2 or len(data_b) < 2:
            return {"error": "Not enough data points for statistical testing"}

        if test_type == "auto":
            test_type = select_test_type(data_a, data_b)

        result: Dict[str, Any] = {
            "test_name": test_type, "statistic": None,
            "p_value": None, "is_significant": None,
            "effect_size": None, "interpretation": "",
        }

        try:
            if test_type == "ttest":
                stat, p_val = ttest_ind(data_a, data_b, equal_var=False)
                result["test_name"] = "Welch's t-test"
            elif test_type == "mannwhitney":
                stat, p_val = mannwhitneyu(data_a, data_b, alternative='two-sided')
                result["test_name"] = "Mann-Whitney U test"
            elif test_type == "ks":
                stat, p_val = ks_2samp(data_a, data_b)
                result["test_name"] = "Kolmogorov-Smirnov test"
            else:
                return {"error": f"Unknown test type: {test_type}"}

            pooled_std = np.sqrt((np.var(data_a, ddof=1) + np.var(data_b, ddof=1)) / 2)
            effect_size = (np.mean(data_a) - np.mean(data_b)) / pooled_std if pooled_std > 0 else 0.0

            result["statistic"] = float(stat)
            result["p_value"] = float(p_val)
            result["is_significant"] = p_val < 0.05
            result["effect_size"] = float(effect_size)
            result["interpretation"] = interpret_test_result(
                result["test_name"], p_val, effect_size, ds_a.name, ds_b.name,
            )

        except (ValueError, TypeError, ArithmeticError) as e:
            result["error"] = str(e)
            logger.error("comparison_engine.statistical_test_failed", extra={"error": e})

        return result

    def calculate_correlation(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        column_a: str,
        column_b: Optional[str] = None,
        method: str = "pearson",
    ) -> Optional[Dict[str, Any]]:
        """Compute the correlation coefficient between two columns across two datasets.

        Input:
            dataset_a_id: ID of the first dataset; must be registered in DatasetManager.
            dataset_b_id: ID of the second dataset; must be registered in DatasetManager.
            column_a: Column name from dataset A to correlate; must be numeric.
            column_b: Column name from dataset B to correlate; defaults to column_a if None.
            method: Correlation method: "pearson" or "spearman" (default "pearson").

        Output:
            Dict with keys: method, correlation, p_value, is_significant, strength,
            interpretation. On error, dict contains "error" key. Returns an error dict
            (not None) when scipy is unavailable.

        Raises:
            None (errors are captured in the returned dict).

        Invariants:
            - Comparison uses min(len(data_a), len(data_b)) aligned data points.
            - Returns an error dict when fewer than 3 aligned data points are available.
            - is_significant == (p_value < 0.05) on success.
            - strength is one of: "negligible", "weak", "moderate", "strong", "very strong".
        """
        if not HAS_SCIPY:
            return {
                "error": "scipy is not installed",
                "method": method, "correlation": None,
                "p_value": None, "is_significant": None,
                "strength": None,
                "interpretation": "Correlation calculation requires scipy",
            }

        if column_b is None:
            column_b = column_a

        df_a = self._get_df_snapshot(dataset_a_id)
        df_b = self._get_df_snapshot(dataset_b_id)

        if df_a is None or df_b is None:
            return {"error": "Dataset not found"}
        if column_a not in df_a.columns:
            return {"error": f"Column '{column_a}' not found in dataset A"}
        if column_b not in df_b.columns:
            return {"error": f"Column '{column_b}' not found in dataset B"}

        data_a = df_a[column_a].drop_nulls().to_numpy()
        data_b = df_b[column_b].drop_nulls().to_numpy()

        min_len = min(len(data_a), len(data_b))
        if min_len < 3:
            return {"error": "Not enough data points for correlation"}

        data_a = data_a[:min_len]
        data_b = data_b[:min_len]

        result: Dict[str, Any] = {
            "method": method, "correlation": None,
            "p_value": None, "is_significant": None,
            "strength": None, "interpretation": "",
        }

        try:
            if method == "pearson":
                corr, p_val = pearsonr(data_a, data_b)
                result["method"] = "Pearson"
            elif method == "spearman":
                corr, p_val = spearmanr(data_a, data_b)
                result["method"] = "Spearman"
            else:
                return {"error": f"Unknown method: {method}"}

            result["correlation"] = float(corr)
            result["p_value"] = float(p_val)
            result["is_significant"] = p_val < 0.05

            abs_corr = abs(corr)
            if abs_corr < 0.1:
                result["strength"] = "negligible"
            elif abs_corr < 0.3:
                result["strength"] = "weak"
            elif abs_corr < 0.5:
                result["strength"] = "moderate"
            elif abs_corr < 0.7:
                result["strength"] = "strong"
            else:
                result["strength"] = "very strong"

            direction = "positive" if corr > 0 else "negative"
            sig_text = "significant" if result["is_significant"] else "not significant"
            result["interpretation"] = (
                f"{result['strength'].title()} {direction} correlation (r = {corr:.3f}), "
                f"{sig_text} (p = {p_val:.4f})"
            )

        except (ValueError, TypeError, ArithmeticError) as e:
            result["error"] = str(e)
            logger.error("comparison_engine.correlation_failed", extra={"error": e})

        return result

    def calculate_descriptive_comparison(
        self,
        dataset_ids: List[str],
        value_column: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Compute extended descriptive statistics for a column across multiple datasets.

        Input:
            dataset_ids: List of dataset ID strings to include; datasets that do not exist
                or do not contain value_column are silently skipped.
            value_column: Name of the numeric column to summarise.

        Output:
            Dict mapping dataset_id to an extended stats dict that includes all keys from
            get_comparison_statistics() plus: skewness, kurtosis, iqr, range, cv (coefficient
            of variation). skewness/kurtosis are None when scipy is unavailable.

        Raises:
            None

        Invariants:
            - cv is None when the column mean is zero (avoids division by zero).
            - Extends (does not replace) the base stats from get_comparison_statistics().
        """
        result = self.get_comparison_statistics(dataset_ids, value_column)

        for did in dataset_ids:
            df = self._get_df_snapshot(did)
            if df is None or value_column not in df.columns:
                continue

            series = df[value_column].drop_nulls()
            if len(series) == 0:
                continue

            data = series.to_numpy()

            if did not in result:
                result[did] = {}

            result[did]["skewness"] = float(scipy_stats.skew(data)) if HAS_SCIPY else None
            result[did]["kurtosis"] = float(scipy_stats.kurtosis(data)) if HAS_SCIPY else None
            result[did]["iqr"] = float(np.percentile(data, 75) - np.percentile(data, 25))
            result[did]["range"] = float(np.max(data) - np.min(data))
            result[did]["cv"] = float(np.std(data, ddof=1) / np.mean(data) * 100) if np.mean(data) != 0 else None

        return result

    def get_normality_test(
        self,
        dataset_id: str,
        value_column: str,
    ) -> Optional[Dict[str, Any]]:
        """Run a normality test on a column from the specified dataset.

        Input:
            dataset_id: ID of the dataset to test; must be registered in DatasetManager.
            value_column: Name of the numeric column to test; must exist in the dataset.

        Output:
            Dict with normality test results (delegated from run_normality_test), or
            {"error": "Dataset or column not found"} if the dataset or column is absent.

        Raises:
            None

        Invariants:
            - Null values are dropped before the test is run.
            - Does not modify any dataset state.
        """
        df = self._get_df_snapshot(dataset_id)
        if df is None or value_column not in df.columns:
            return {"error": "Dataset or column not found"}
        data = df[value_column].drop_nulls().to_numpy()
        return run_normality_test(data)
