"""
Comparison-related Report Types
비교 분석 관련 레포트 타입 정의
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime

import polars as pl

__all__ = [
    "ReportMetadata",
    "DatasetSummary",
    "StatisticalSummary",
    "ComparisonResult",
    "DifferenceAnalysis",
]


@dataclass
class ReportMetadata:
    """레포트 메타데이터"""
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
        """딕셔너리로 변환"""
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
    """데이터셋 요약 정보"""
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
        """딕셔너리로 변환"""
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
        """Polars DataFrame에서 생성"""
        columns = df.columns
        column_types = {col: str(df[col].dtype) for col in columns}

        # 결측값 계산
        missing_values = {}
        for col in columns:
            null_count = df[col].null_count()
            if null_count > 0:
                missing_values[col] = null_count

        # 날짜 범위 계산 (날짜 컬럼이 있는 경우)
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
                    pass

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
    """통계 요약"""
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
        """딕셔너리로 변환"""
        return asdict(self)

    @classmethod
    def from_series(
        cls,
        series: pl.Series,
        column: str,
        dataset_id: str = "",
        dataset_name: str = ""
    ) -> "StatisticalSummary":
        """Polars Series에서 생성"""
        stats = StatisticalSummary(
            column=column,
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            count=len(series),
            null_count=series.null_count()
        )

        # 수치형 컬럼인 경우 통계 계산
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
                    pass

            except Exception:
                pass

        return stats


@dataclass
class ComparisonResult:
    """비교 분석 결과"""
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
        """딕셔너리로 변환"""
        result = asdict(self)
        if self.confidence_interval:
            result["confidence_interval"] = list(self.confidence_interval)
        return result

    def get_significance_symbol(self) -> str:
        """유의수준 기호 반환"""
        if self.p_value < 0.001:
            return "***"
        elif self.p_value < 0.01:
            return "**"
        elif self.p_value < 0.05:
            return "*"
        return ""


@dataclass
class DifferenceAnalysis:
    """차이 분석 결과"""
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
        """딕셔너리로 변환"""
        return asdict(self)
