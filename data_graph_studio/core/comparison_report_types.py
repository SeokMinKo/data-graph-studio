"""comparison_report_types — data structures for comparison analysis reports.

Defines immutable-style dataclasses used by the comparison engine to represent
dataset metadata, statistical summaries, hypothesis test results, and row-level
difference analyses. All types expose a to_dict() method for serialization.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime

import polars as pl

logger = logging.getLogger(__name__)

__all__ = [
    "ReportMetadata",
    "DatasetSummary",
    "StatisticalSummary",
    "ComparisonResult",
    "DifferenceAnalysis",
]


@dataclass
class ReportMetadata:
    """Authoring and display metadata attached to a comparison report.

    Input:
        title — str, primary report heading; required
        subtitle — Optional[str], secondary heading shown below the title
        author — Optional[str], display name of the report creator
        created_at — datetime, report generation time; defaults to now
        version — str, schema version string; defaults to "1.0"
        description — Optional[str], free-text report description
        tags — List[str], searchable keyword labels; defaults to []
        logo_path — Optional[str], filesystem path to a logo image
        logo_base64 — Optional[str], base64-encoded logo for self-contained HTML export
    """

    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0"
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    logo_path: Optional[str] = None
    logo_base64: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this metadata to a JSON-compatible dictionary.

        Output: Dict[str, Any] — all fields as primitives; created_at is
            ISO 8601 string; logo_base64 is excluded
        """
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
            "description": self.description,
            "tags": self.tags,
            "logo_path": self.logo_path,
        }


@dataclass
class DatasetSummary:
    """Shape, type, and quality snapshot for one dataset in a comparison.

    Input:
        id — str, unique identifier matching the dataset registry key
        name — str, human-readable display name
        file_path — Optional[str], source file path if loaded from disk
        row_count — int, number of rows; >= 0
        column_count — int, number of columns; >= 0
        columns — List[str], ordered column names
        column_types — Dict[str, str], column name → Polars dtype string
        date_range — Optional[Dict[str, str]], first temporal column's min/max dates
        memory_bytes — int, estimated in-memory size in bytes
        color — str, hex color used in charts; defaults to "#1f77b4"
        missing_values — Dict[str, int], column name → null count for non-zero counts
    """

    id: str
    name: str
    file_path: Optional[str] = None
    row_count: int = 0
    column_count: int = 0
    columns: List[str] = field(default_factory=list)
    column_types: Dict[str, str] = field(default_factory=dict)
    date_range: Optional[Dict[str, str]] = None
    memory_bytes: int = 0
    color: str = "#1f77b4"
    missing_values: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this summary to a JSON-compatible dictionary via dataclasses.asdict.

        Output: Dict[str, Any] — all fields recursively converted to primitives
        """
        return asdict(self)

    @classmethod
    def from_dataframe(
        cls,
        df: pl.DataFrame,
        id: str,
        name: str,
        file_path: Optional[str] = None,
        color: str = "#1f77b4"
    ) -> "DatasetSummary":
        """Construct a DatasetSummary by inspecting a Polars DataFrame.

        Computes column types, non-zero null counts, and the date range of the
        first temporal column found. Date range failures are logged and suppressed.

        Input:
            df — pl.DataFrame, the dataset to summarize
            id — str, identifier for the dataset in the registry
            name — str, display name
            file_path — Optional[str], original file path for provenance
            color — str, hex chart color; defaults to "#1f77b4"
        Output: DatasetSummary — fully populated summary reflecting df at call time
        Invariants: row_count == len(df); column_count == len(df.columns)
        """
        columns = df.columns
        column_types = {col: str(df[col].dtype) for col in columns}

        # Missing value counts (only non-zero entries stored)
        missing_values = {}
        for col in columns:
            null_count = df[col].null_count()
            if null_count > 0:
                missing_values[col] = null_count

        # Date range from the first temporal column
        date_range = None
        for col in columns:
            if df[col].dtype in [pl.Date, pl.Datetime]:
                try:
                    min_date = df[col].min()
                    max_date = df[col].max()
                    if min_date and max_date:
                        date_range = {
                            "column": col,
                            "min": str(min_date),
                            "max": str(max_date)
                        }
                        break
                except Exception:
                    logger.debug("comparison_report_types.date_range.failed", extra={"col": col}, exc_info=True)

        return cls(
            id=id,
            name=name,
            file_path=file_path,
            row_count=len(df),
            column_count=len(columns),
            columns=columns,
            column_types=column_types,
            date_range=date_range,
            memory_bytes=df.estimated_size(),
            color=color,
            missing_values=missing_values
        )


@dataclass
class StatisticalSummary:
    """Descriptive statistics for one column of one dataset.

    Numeric columns carry the full set of statistics; non-numeric columns
    carry only count and null_count. All optional fields default to None
    when not applicable or when computation fails.

    Input:
        column — str, column name
        dataset_id — str, owning dataset identifier; defaults to ""
        dataset_name — str, owning dataset display name; defaults to ""
        count — int, total row count including nulls
        null_count — int, number of null values
        sum, mean, median, std, variance, min, max — Optional[float], basic stats
        q1, q3, iqr — Optional[float], quartile and interquartile range
        skewness, kurtosis — Optional[float], shape statistics
    """

    column: str
    dataset_id: str = ""
    dataset_name: str = ""
    count: int = 0
    null_count: int = 0
    sum: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    variance: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    q1: Optional[float] = None
    q3: Optional[float] = None
    iqr: Optional[float] = None
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this summary to a JSON-compatible dictionary via dataclasses.asdict.

        Output: Dict[str, Any] — all fields recursively converted to primitives;
            None values are preserved
        """
        return asdict(self)

    @classmethod
    def from_series(
        cls,
        series: pl.Series,
        column: str,
        dataset_id: str = "",
        dataset_name: str = ""
    ) -> "StatisticalSummary":
        """Compute a StatisticalSummary from a Polars Series.

        Numeric series get full descriptive stats including quartiles, skewness,
        and kurtosis. Non-numeric series get only count and null_count. Failures
        in individual stat computations are caught and logged at DEBUG level.

        Input:
            series — pl.Series, the column data to summarize
            column — str, column name for labeling
            dataset_id — str, owning dataset identifier; defaults to ""
            dataset_name — str, owning dataset display name; defaults to ""
        Output: StatisticalSummary — populated with all computable statistics
        Invariants: count == len(series); null_count == series.null_count()
        """
        stats = StatisticalSummary(
            column=column,
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            count=len(series),
            null_count=series.null_count()
        )

        # Full stats for numeric columns only
        if series.dtype.is_numeric():
            try:
                stats.sum = float(series.sum()) if series.sum() is not None else None
                stats.mean = float(series.mean()) if series.mean() is not None else None
                stats.median = float(series.median()) if series.median() is not None else None
                stats.std = float(series.std()) if series.std() is not None else None
                stats.variance = float(series.var()) if series.var() is not None else None
                stats.min = float(series.min()) if series.min() is not None else None
                stats.max = float(series.max()) if series.max() is not None else None

                # Quantiles
                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                stats.q1 = float(q1) if q1 is not None else None
                stats.q3 = float(q3) if q3 is not None else None
                if stats.q1 is not None and stats.q3 is not None:
                    stats.iqr = stats.q3 - stats.q1

                # Skewness & Kurtosis
                try:
                    stats.skewness = float(series.skew()) if hasattr(series, 'skew') else None
                    stats.kurtosis = float(series.kurtosis()) if hasattr(series, 'kurtosis') else None
                except Exception:
                    logger.debug("comparison_report_types.skewness_kurtosis.failed", exc_info=True)

            except Exception:
                logger.debug("comparison_report_types.numeric_stats.failed", extra={"col": column}, exc_info=True)

        return stats


@dataclass
class ComparisonResult:
    """Outcome of a statistical hypothesis test comparing two datasets on one column.

    Input:
        dataset_a_id — str, identifier of the first dataset
        dataset_a_name — str, display name of the first dataset
        dataset_b_id — str, identifier of the second dataset
        dataset_b_name — str, display name of the second dataset
        column — str, column on which the test was run
        test_type — str, name of the statistical test (e.g. "t-test", "Mann-Whitney U")
        test_statistic — float, computed test statistic value
        p_value — float, probability of the observed result under the null hypothesis
        effect_size — Optional[float], magnitude of difference (e.g. Cohen's d)
        effect_size_interpretation — str, human label for effect_size ("small", "large", …)
        significant — bool, True when p_value is below the chosen alpha
        significance_level — str, APA star notation: "", "*", "**", or "***"
        interpretation — str, plain-English conclusion for the report
        confidence_interval — Optional[tuple], (lower, upper) bounds of the CI
    """

    dataset_a_id: str
    dataset_a_name: str
    dataset_b_id: str
    dataset_b_name: str
    column: str
    test_type: str
    test_statistic: float
    p_value: float
    effect_size: Optional[float] = None
    effect_size_interpretation: str = ""
    significant: bool = False
    significance_level: str = ""  # "", "*", "**", "***"
    interpretation: str = ""
    confidence_interval: Optional[tuple] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this result to a JSON-compatible dictionary.

        confidence_interval is converted from tuple to list for JSON safety.

        Output: Dict[str, Any] — all fields as primitives; confidence_interval
            is a list or absent when None
        """
        result = asdict(self)
        if self.confidence_interval:
            result["confidence_interval"] = list(self.confidence_interval)
        return result

    def get_significance_symbol(self) -> str:
        """Return the APA significance star notation for the stored p_value.

        Output: str — "***" for p < 0.001, "**" for p < 0.01,
            "*" for p < 0.05, "" otherwise
        """
        if self.p_value < 0.001:
            return "***"
        elif self.p_value < 0.01:
            return "**"
        elif self.p_value < 0.05:
            return "*"
        return ""


@dataclass
class DifferenceAnalysis:
    """Row-level difference breakdown between two datasets joined on a key column.

    Counts how many matched rows have a positive (A > B), negative (A < B), or
    neutral (A == B) value difference, and surfaces the top diverging records.

    Input:
        dataset_a_id — str, identifier of the first dataset
        dataset_a_name — str, display name of the first dataset
        dataset_b_id — str, identifier of the second dataset
        dataset_b_name — str, display name of the second dataset
        key_column — str, join key used to match rows across datasets
        value_column — str, numeric column whose values are compared
        total_records — int, total rows in the join result
        matched_records — int, rows where both datasets have a value
        positive_count — int, matched rows where A > B
        negative_count — int, matched rows where A < B
        neutral_count — int, matched rows where A == B
        positive_percentage — float, positive_count / matched_records * 100
        negative_percentage — float, negative_count / matched_records * 100
        neutral_percentage — float, neutral_count / matched_records * 100
        total_difference — float, sum of (A - B) across all matched rows
        mean_difference — float, average (A - B) across matched rows
        top_differences — List[Dict[str, Any]], records with the largest absolute differences
    """

    dataset_a_id: str
    dataset_a_name: str
    dataset_b_id: str
    dataset_b_name: str
    key_column: str
    value_column: str
    total_records: int = 0
    matched_records: int = 0
    positive_count: int = 0  # A > B
    negative_count: int = 0  # A < B
    neutral_count: int = 0   # A == B
    positive_percentage: float = 0.0
    negative_percentage: float = 0.0
    neutral_percentage: float = 0.0
    total_difference: float = 0.0
    mean_difference: float = 0.0
    top_differences: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this analysis to a JSON-compatible dictionary via dataclasses.asdict.

        Output: Dict[str, Any] — all fields recursively converted to primitives
        """
        return asdict(self)
