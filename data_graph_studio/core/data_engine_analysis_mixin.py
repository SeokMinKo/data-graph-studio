"""
AnalysisMixin — statistical analysis and comparison delegation methods.

Extracted from DataEngine to reduce god-object complexity.
All methods delegate to self._comparison and self._query / self.df,
which are initialised by DataEngine.__init__.
"""

import logging
from typing import Optional, List, Dict, Any

import polars as pl

logger = logging.getLogger(__name__)


class AnalysisMixin(object):
    """Mixin for statistical analysis and comparison methods.

    Requires the host class to provide:
        self._comparison        — ComparisonEngine instance
        self.df                 — active Polars DataFrame (or None)
        self.dtypes             — dict mapping column name to dtype string
        self.update_dataframe() — DataFrame updater with cache-clear
        self._virtual_columns  — set of virtual column names
        self.is_column_categorical() — cardinality helper
    """

    # -- ComparisonEngine delegation ------------------------------------------

    def align_datasets(self, dataset_ids, key_column, fill_strategy="null"):
        """Align multiple datasets on a shared key column, filling missing values according to the strategy.

        Args:
            dataset_ids: List of dataset ID strings to align.
            key_column: Column name used as the join key across all datasets.
            fill_strategy: How to fill missing values after alignment; "null" leaves them as null.

        Returns:
            A Polars DataFrame with all datasets merged and aligned on the key column.
        """
        return self._comparison.align_datasets(dataset_ids, key_column, fill_strategy)

    def calculate_difference(self, dataset_a_id, dataset_b_id, value_column, key_column=None):
        """Compute the row-wise difference between a value column in two datasets.

        Args:
            dataset_a_id: ID string of the first (base) dataset.
            dataset_b_id: ID string of the second (comparison) dataset.
            value_column: Name of the numeric column to subtract.
            key_column: Optional column to align rows before differencing; uses positional alignment if None.

        Returns:
            A Polars DataFrame with the original values and their computed differences.
        """
        return self._comparison.calculate_difference(dataset_a_id, dataset_b_id, value_column, key_column)

    def get_comparison_statistics(self, dataset_ids, value_column):
        """Gather descriptive statistics for a value column across multiple datasets for side-by-side comparison.

        Args:
            dataset_ids: List of dataset ID strings to include.
            value_column: Name of the column to summarise in each dataset.

        Returns:
            A dict mapping dataset ID to its statistics dict for the given column.
        """
        return self._comparison.get_comparison_statistics(dataset_ids, value_column)

    def merge_datasets(self, dataset_ids, key_column=None, how="full"):
        """Merge multiple datasets into a single DataFrame using the specified join strategy.

        Args:
            dataset_ids: List of dataset ID strings to merge.
            key_column: Column name to join on; if None, datasets are concatenated vertically.
            how: Join type string (e.g., "full", "inner", "left").

        Returns:
            A merged Polars DataFrame.
        """
        return self._comparison.merge_datasets(dataset_ids, key_column, how)

    def perform_statistical_test(self, dataset_a_id, dataset_b_id, value_column, test_type="auto"):
        """Run a statistical significance test comparing a numeric column between two datasets.

        Args:
            dataset_a_id: ID string of the first dataset.
            dataset_b_id: ID string of the second dataset.
            value_column: Name of the numeric column to test.
            test_type: Test to run ("auto", "ttest", "mannwhitney", or "ks"); "auto" selects based on normality.

        Returns:
            A dict with the test name, statistic, p-value, and a human-readable interpretation.

        Raises:
            ImportError: If scipy is not installed.
        """
        return self._comparison.perform_statistical_test(dataset_a_id, dataset_b_id, value_column, test_type)

    def calculate_correlation(self, dataset_a_id, dataset_b_id, column_a, column_b=None, method="pearson"):
        """Calculate the correlation coefficient between columns in two datasets.

        Args:
            dataset_a_id: ID string of the first dataset.
            dataset_b_id: ID string of the second dataset.
            column_a: Column name from the first dataset (and from the second if column_b is None).
            column_b: Column name from the second dataset; defaults to column_a if not provided.
            method: Correlation method to use ("pearson" or "spearman").

        Returns:
            A dict containing the correlation coefficient and p-value.

        Raises:
            ImportError: If scipy is not installed.
        """
        return self._comparison.calculate_correlation(dataset_a_id, dataset_b_id, column_a, column_b, method)

    def calculate_descriptive_comparison(self, dataset_ids, value_column):
        """Produce a structured descriptive comparison of a value column across multiple datasets.

        Args:
            dataset_ids: List of dataset ID strings to compare.
            value_column: Name of the column to describe in each dataset.

        Returns:
            A dict mapping dataset ID to a descriptive statistics summary dict.
        """
        return self._comparison.calculate_descriptive_comparison(dataset_ids, value_column)

    def get_normality_test(self, dataset_id, value_column):
        """Test whether a column's distribution is approximately normal.

        Uses Shapiro-Wilk for n <= 5000, D'Agostino-Pearson for larger datasets.

        Args:
            dataset_id: ID of the dataset to test.
            value_column: Column name to test for normality.

        Returns:
            Dict with 'test', 'statistic', 'p_value', and 'is_normal' keys,
            or {'error': reason} if scipy is not installed or column is non-numeric.
        """
        return self._comparison.get_normality_test(dataset_id, value_column)

    # -- Chart recommendation -------------------------------------------------

    def recommend_chart_type(
        self,
        x_col: Optional[str],
        y_cols: List[str],
        group_cols: Optional[List[str]] = None,
    ) -> List[tuple]:
        """데이터 특성 분석 후 추천 차트 타입 반환 (최대 3개, 이유 포함).

        Returns list of (ChartType, reason_str) tuples.
        """
        if self.df is None:
            return []

        from .state import ChartType

        recommendations: list = []
        group_cols = group_cols or []

        x_is_cat = self.is_column_categorical(x_col) if x_col else False
        x_is_time = False
        if x_col:
            col_lower = x_col.lower()
            if "time" in col_lower or "date" in col_lower:
                x_is_time = True
            else:
                dt = self.dtypes.get(x_col, "")
                if isinstance(dt, str) and dt.startswith("datetime"):
                    x_is_time = True
                elif hasattr(dt, "__str__") and "datetime" in str(dt).lower():
                    x_is_time = True

        n_rows = len(self.df) if self.df is not None else 0
        n_y = len(y_cols)
        has_groups = bool(group_cols)

        if x_is_time:
            recommendations.append((ChartType.LINE, "시계열 데이터 → 라인 차트"))
            if n_y >= 2:
                recommendations.append((ChartType.AREA, "다중 시계열 → 영역 차트"))
        elif x_is_cat:
            recommendations.append((ChartType.BAR, "카테고리 데이터 → 바 차트"))
            if has_groups:
                recommendations.append((ChartType.STACKED_BAR, "그룹 카테고리 → 누적 바"))
        elif n_rows > 1000:
            recommendations.append((ChartType.SCATTER, "대량 데이터 → 산점도"))

        # 분포 분석
        if n_y == 1 and not x_is_time:
            recommendations.append((ChartType.HISTOGRAM, "단일 변수 분포 → 히스토그램"))
        if x_is_cat and n_y == 1:
            recommendations.append((ChartType.BOX, "카테고리별 분포 → 박스플롯"))

        # Fallback: at least one recommendation
        if not recommendations:
            if n_y >= 2:
                recommendations.append((ChartType.LINE, "다중 Y 컬럼 → 라인 차트"))
            elif n_y == 1:
                recommendations.append((ChartType.BAR, "단일 Y 컬럼 → 바 차트"))

        return recommendations[:3]

    # -- Data quality report (F4) ---------------------------------------------

    def data_quality_report(self) -> Dict[str, Any]:
        """null 비율, 중복 행, 타입별 통계."""
        if self.df is None:
            return {}
        df = self.df
        row_count = len(df)
        return {
            'row_count': row_count,
            'col_count': len(df.columns),
            'null_counts': {col: df[col].null_count() for col in df.columns},
            'null_pct': {col: df[col].null_count() / max(row_count, 1) * 100 for col in df.columns},
            'duplicate_rows': row_count - len(df.unique()),
            'dtypes': dict(zip(df.columns, [str(d) for d in df.dtypes])),
        }

    # -- Virtual columns (F6) -------------------------------------------------

    def add_virtual_column(self, name: str, expr: pl.Expr) -> bool:
        """가상 컬럼 추가."""
        if self.df is None:
            return False
        try:
            new_df = self.df.with_columns(expr.alias(name))
            self.update_dataframe(new_df)
            self._virtual_columns.add(name)
            return True
        except Exception:
            logger.warning("analysis_mixin.add_virtual_column.failed", extra={"name": name}, exc_info=True)
            return False
