"""
공유 데이터 타입 — Enum, dataclass 정의

data_engine.py, file_loader.py, dataset_manager.py 등에서 공통 사용.
기존 호환: ``from data_graph_studio.core.data_engine import FileType`` 동작 유지
(data_engine.py가 이 모듈을 re-export).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
import uuid

import polars as pl


class FileType(Enum):
    """지원 파일 형식."""

    CSV = "csv"
    EXCEL = "excel"
    PARQUET = "parquet"
    JSON = "json"
    TSV = "tsv"
    TXT = "txt"
    ETL = "etl"
    CUSTOM = "custom"


class DelimiterType(Enum):
    """구분자 타입."""

    COMMA = ","
    TAB = "\t"
    SPACE = " "
    SEMICOLON = ";"
    PIPE = "|"
    REGEX = "regex"
    AUTO = "auto"


class PrecisionMode(Enum):
    """부동소수점 정밀도 모드."""

    AUTO = "auto"
    HIGH = "high"
    SCIENTIFIC = "scientific"


@dataclass
class LoadingProgress:
    """로딩 진행 상태."""

    total_bytes: int = 0
    loaded_bytes: int = 0
    total_rows: int = 0
    loaded_rows: int = 0
    current_chunk: int = 0
    total_chunks: int = 0
    elapsed_seconds: float = 0.0
    status: str = "idle"
    error_message: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        """진행률(%)."""
        if self.total_bytes == 0:
            return 0.0
        return (self.loaded_bytes / self.total_bytes) * 100

    @property
    def eta_seconds(self) -> float:
        """남은 예상 시간(초)."""
        if self.loaded_bytes == 0 or self.elapsed_seconds == 0:
            return 0.0
        rate = self.loaded_bytes / self.elapsed_seconds
        remaining = self.total_bytes - self.loaded_bytes
        return remaining / rate if rate > 0 else 0.0


@dataclass
class ColumnInfo:
    """컬럼 정보."""

    name: str
    dtype: str
    null_count: int = 0
    unique_count: int = 0
    min_value: Any = None
    max_value: Any = None
    sample_values: List[Any] = field(default_factory=list)
    is_numeric: bool = False
    is_temporal: bool = False
    is_categorical: bool = False
    memory_bytes: int = 0


@dataclass
class DataProfile:
    """데이터 프로파일."""

    total_rows: int
    total_columns: int
    memory_bytes: int
    columns: List[ColumnInfo]
    load_time_seconds: float


@dataclass
class DatasetInfo:
    """개별 데이터셋 정보."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    df: Optional[pl.DataFrame] = None
    lazy_df: Optional[pl.LazyFrame] = None
    source: Optional[DataSource] = None
    profile: Optional[DataProfile] = None
    color: str = "#1f77b4"
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def row_count(self) -> int:
        """로드된 행 수."""
        return len(self.df) if self.df is not None else 0

    @property
    def column_count(self) -> int:
        """컬럼 수."""
        return len(self.df.columns) if self.df is not None else 0

    @property
    def columns(self) -> List[str]:
        """컬럼명 목록."""
        return self.df.columns if self.df is not None else []

    @property
    def memory_bytes(self) -> int:
        """메모리 사용량(bytes)."""
        return self.df.estimated_size() if self.df is not None else 0

    @property
    def is_loaded(self) -> bool:
        """데이터 로드 여부."""
        return self.df is not None


@dataclass
class DataSource:
    """데이터 소스 정보."""

    path: Optional[str] = None
    file_type: Optional[FileType] = None
    encoding: str = "utf-8"
    delimiter: str = ","
    delimiter_type: DelimiterType = DelimiterType.COMMA
    regex_pattern: Optional[str] = None
    has_header: bool = True
    skip_rows: int = 0
    comment_char: Optional[str] = None
    sheet_name: Optional[str] = None
