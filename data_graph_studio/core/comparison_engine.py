"""
ComparisonEngine — 데이터셋 비교 분석 모듈

DatasetManager를 참조하여 멀티 데이터셋 간 비교, 통계 검정,
상관 분석, 기술통계 비교, 정규성 검정을 수행한다.
비교 연산 시 datasets snapshot을 사용하여 원본 변경에 안전하다.
"""

import logging
from typing import Optional, List, Dict, Any

import polars as pl
import numpy as np

try:
    from scipy import stats as scipy_stats
    from scipy.stats import pearsonr, spearmanr, ttest_ind, mannwhitneyu, ks_2samp

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from .dataset_manager import DatasetManager

logger = logging.getLogger(__name__)


class ComparisonEngine:
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
        """키 컬럼 기준으로 데이터셋을 정렬한다.

        Args:
            dataset_ids: 정렬할 데이터셋 ID 목록.
            key_column: 정렬 기준 컬럼.
            fill_strategy: 누락값 처리 ('null', 'forward', 'backward', 'interpolate').

        Returns:
            {dataset_id: aligned_df} 매핑.
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
        """두 데이터셋 간 차이를 계산한다.

        Args:
            dataset_a_id: 첫 번째 데이터셋 ID.
            dataset_b_id: 두 번째 데이터셋 ID.
            value_column: 비교할 값 컬럼.
            key_column: 키 컬럼 (None이면 인덱스 기준).

        Returns:
            차이 DataFrame (key, value_a, value_b, diff, diff_pct) 또는 None.
        """
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
                on=key_column,
                how="full",
                suffix="_b",
            )
            value_a_col = value_column
            value_b_col = f"{value_column}_b"
        else:
            min_len = min(len(df_a), len(df_b))
            merged = pl.DataFrame(
                {
                    "index": list(range(min_len)),
                    value_column: df_a[value_column].head(min_len),
                    f"{value_column}_b": df_b[value_column].head(min_len),
                }
            )
            key_column = "index"
            value_a_col = value_column
            value_b_col = f"{value_column}_b"

        result = merged.with_columns(
            [
                (pl.col(value_a_col) - pl.col(value_b_col)).alias("diff"),
                (
                    (pl.col(value_a_col) - pl.col(value_b_col))
                    / pl.col(value_b_col).abs()
                    * 100
                ).alias("diff_pct"),
            ]
        ).rename({value_a_col: "value_a", value_b_col: "value_b"})

        return result

    def get_comparison_statistics(
        self,
        dataset_ids: List[str],
        value_column: str,
    ) -> Dict[str, Dict[str, Any]]:
        """여러 데이터셋의 비교 통계를 반환한다.

        Args:
            dataset_ids: 비교할 데이터셋 ID 목록.
            value_column: 통계 대상 컬럼.

        Returns:
            {dataset_id: {stat_name: value}} 매핑.
        """
        stats: Dict[str, Dict[str, Any]] = {}

        for did in dataset_ids:
            ds = self._datasets.get_dataset(did)
            df = self._get_df_snapshot(did)
            if ds is None or df is None or value_column not in df.columns:
                continue

            series = df[value_column]
            if series.dtype not in [
                pl.Int8,
                pl.Int16,
                pl.Int32,
                pl.Int64,
                pl.Float32,
                pl.Float64,
            ]:
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
        """여러 데이터셋을 병합한다.

        Args:
            dataset_ids: 병합할 데이터셋 ID 목록.
            key_column: 조인 키 컬럼 (None이면 수직 결합).
            how: 조인 방식 ('inner', 'outer', 'left', 'right').

        Returns:
            병합된 DataFrame 또는 None.
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

    # ------------------------------------------------------------------
    # Statistical Testing
    # ------------------------------------------------------------------

    def perform_statistical_test(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        value_column: str,
        test_type: str = "auto",
    ) -> Optional[Dict[str, Any]]:
        """두 데이터셋 간 통계 검정을 수행한다.

        Args:
            dataset_a_id: 첫 번째 데이터셋 ID.
            dataset_b_id: 두 번째 데이터셋 ID.
            value_column: 검정 대상 컬럼.
            test_type: 검정 유형 ('auto', 'ttest', 'mannwhitney', 'ks').

        Returns:
            검정 결과 딕셔너리 또는 에러 딕셔너리.
        """
        if not HAS_SCIPY:
            return {
                "error": "scipy is not installed",
                "test_name": "none",
                "statistic": None,
                "p_value": None,
                "is_significant": None,
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
            test_type = self._select_test_type(data_a, data_b)

        result: Dict[str, Any] = {
            "test_name": test_type,
            "statistic": None,
            "p_value": None,
            "is_significant": None,
            "effect_size": None,
            "interpretation": "",
        }

        try:
            if test_type == "ttest":
                stat, p_val = ttest_ind(data_a, data_b, equal_var=False)
                result["test_name"] = "Welch's t-test"
            elif test_type == "mannwhitney":
                stat, p_val = mannwhitneyu(data_a, data_b, alternative="two-sided")
                result["test_name"] = "Mann-Whitney U test"
            elif test_type == "ks":
                stat, p_val = ks_2samp(data_a, data_b)
                result["test_name"] = "Kolmogorov-Smirnov test"
            else:
                return {"error": f"Unknown test type: {test_type}"}

            pooled_std = np.sqrt((np.var(data_a, ddof=1) + np.var(data_b, ddof=1)) / 2)
            effect_size = (
                (np.mean(data_a) - np.mean(data_b)) / pooled_std
                if pooled_std > 0
                else 0.0
            )

            result["statistic"] = float(stat)
            result["p_value"] = float(p_val)
            result["is_significant"] = p_val < 0.05
            result["effect_size"] = float(effect_size)
            result["interpretation"] = self._interpret_test_result(
                result["test_name"],
                p_val,
                effect_size,
                ds_a.name,
                ds_b.name,
            )

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Statistical test failed: {e}")

        return result

    def _select_test_type(self, data_a: np.ndarray, data_b: np.ndarray) -> str:
        """정규성에 따라 적절한 검정 방법을 선택한다.

        Args:
            data_a: 첫 번째 데이터.
            data_b: 두 번째 데이터.

        Returns:
            검정 유형 문자열.
        """
        if not HAS_SCIPY:
            return "ttest"

        if len(data_a) >= 30 and len(data_b) >= 30:
            return "ttest"

        try:
            sample_a = data_a[:5000] if len(data_a) > 5000 else data_a
            sample_b = data_b[:5000] if len(data_b) > 5000 else data_b
            _, p_a = scipy_stats.shapiro(sample_a) if len(sample_a) >= 3 else (0, 1)
            _, p_b = scipy_stats.shapiro(sample_b) if len(sample_b) >= 3 else (0, 1)
            return "ttest" if p_a >= 0.05 and p_b >= 0.05 else "mannwhitney"
        except Exception:
            return "ttest"

    def _interpret_test_result(
        self,
        test_name: str,
        p_value: float,
        effect_size: float,
        name_a: str,
        name_b: str,
    ) -> str:
        """검정 결과를 해석한다.

        Args:
            test_name: 검정 이름.
            p_value: p-value.
            effect_size: 효과 크기 (Cohen's d).
            name_a: 데이터셋 A 이름.
            name_b: 데이터셋 B 이름.

        Returns:
            해석 문자열.
        """
        if p_value < 0.001:
            sig_text = "highly significant (p < 0.001)"
        elif p_value < 0.01:
            sig_text = "very significant (p < 0.01)"
        elif p_value < 0.05:
            sig_text = "significant (p < 0.05)"
        else:
            sig_text = "not significant (p ≥ 0.05)"

        abs_effect = abs(effect_size)
        if abs_effect < 0.2:
            effect_text = "negligible"
        elif abs_effect < 0.5:
            effect_text = "small"
        elif abs_effect < 0.8:
            effect_text = "medium"
        else:
            effect_text = "large"

        direction = (
            f"{name_a} > {name_b}"
            if effect_size > 0
            else (f"{name_a} < {name_b}" if effect_size < 0 else f"{name_a} ≈ {name_b}")
        )

        return (
            f"The difference between datasets is {sig_text}. "
            f"Effect size is {effect_text} (d={effect_size:.3f}). "
            f"Direction: {direction}"
        )

    def calculate_correlation(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        column_a: str,
        column_b: Optional[str] = None,
        method: str = "pearson",
    ) -> Optional[Dict[str, Any]]:
        """두 데이터셋/컬럼 간 상관관계를 계산한다.

        Args:
            dataset_a_id: 첫 번째 데이터셋 ID.
            dataset_b_id: 두 번째 데이터셋 ID.
            column_a: 첫 번째 컬럼.
            column_b: 두 번째 컬럼 (None이면 column_a와 동일).
            method: 상관계수 유형 ('pearson', 'spearman').

        Returns:
            상관 결과 딕셔너리.
        """
        if not HAS_SCIPY:
            return {
                "error": "scipy is not installed",
                "method": method,
                "correlation": None,
                "p_value": None,
                "is_significant": None,
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
            "method": method,
            "correlation": None,
            "p_value": None,
            "is_significant": None,
            "strength": None,
            "interpretation": "",
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

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Correlation calculation failed: {e}")

        return result

    def calculate_descriptive_comparison(
        self,
        dataset_ids: List[str],
        value_column: str,
    ) -> Dict[str, Dict[str, Any]]:
        """여러 데이터셋의 기술통계 비교를 수행한다.

        Args:
            dataset_ids: 비교할 데이터셋 ID 목록.
            value_column: 통계 대상 컬럼.

        Returns:
            {dataset_id: {stat_name: value}} 매핑 (확장 통계 포함).
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

            result[did]["skewness"] = (
                float(scipy_stats.skew(data)) if HAS_SCIPY else None
            )
            result[did]["kurtosis"] = (
                float(scipy_stats.kurtosis(data)) if HAS_SCIPY else None
            )
            result[did]["iqr"] = float(
                np.percentile(data, 75) - np.percentile(data, 25)
            )
            result[did]["range"] = float(np.max(data) - np.min(data))
            result[did]["cv"] = (
                float(np.std(data, ddof=1) / np.mean(data) * 100)
                if np.mean(data) != 0
                else None
            )

        return result

    def get_normality_test(
        self,
        dataset_id: str,
        value_column: str,
    ) -> Optional[Dict[str, Any]]:
        """정규성 검정을 수행한다.

        Args:
            dataset_id: 데이터셋 ID.
            value_column: 검정 대상 컬럼.

        Returns:
            검정 결과 딕셔너리.
        """
        if not HAS_SCIPY:
            return {"error": "scipy is not installed"}

        df = self._get_df_snapshot(dataset_id)
        if df is None or value_column not in df.columns:
            return {"error": "Dataset or column not found"}

        data = df[value_column].drop_nulls().to_numpy()
        if len(data) < 3:
            return {"error": "Not enough data points"}

        try:
            if len(data) <= 5000:
                stat, p_val = scipy_stats.shapiro(data[:5000])
                test_name = "Shapiro-Wilk"
            else:
                stat, p_val = scipy_stats.normaltest(data)
                test_name = "D'Agostino-Pearson"

            is_normal = p_val >= 0.05
            interpretation = (
                f"Data appears to be normally distributed (p = {p_val:.4f})"
                if is_normal
                else f"Data is not normally distributed (p = {p_val:.4f})"
            )

            return {
                "test_name": test_name,
                "statistic": float(stat),
                "p_value": float(p_val),
                "is_normal": is_normal,
                "interpretation": interpretation,
            }
        except Exception as e:
            return {"error": str(e)}
