"""
file_loader_formats — 파일 형식별 로딩 헬퍼 모음.

FileLoader 클래스에서 추출된 포맷 특화 함수들을 담는다.
각 함수는 독립 함수로 정의되며, 인스턴스 상태가 필요한 경우
첫 번째 인자로 FileLoader 인스턴스(loader)를 받는다.

포맷별 구현은 하위 모듈에 위치한다:
  - file_loader_formats_csv   : CSV / TSV / TXT / ETL
  - file_loader_formats_binary: Excel / Parquet / JSON
"""
from __future__ import annotations

import gc
import os
import time
import logging
from typing import TYPE_CHECKING, Optional, List, Dict

import polars as pl

from .types import FileType, DelimiterType, PrecisionMode, DataProfile, ColumnInfo
from .etl_helpers import HAS_ETL_PARSER
from .metrics import get_metrics
from .exceptions import DataLoadError

# Format-specific helpers (re-exported for backward compatibility)
from .file_loader_formats_csv import (
    load_csv,
    load_text,
    apply_process_filter,
    load_etl,
)
from .file_loader_formats_binary import (
    load_excel,
    load_parquet,
    load_json,
)

if TYPE_CHECKING:
    from .file_loader import FileLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ETL helpers — thin re-exports from etl_helpers
# ---------------------------------------------------------------------------

def is_binary_etl(path: str) -> bool:
    """ETL 파일이 바이너리인지 확인한다."""
    from .etl_helpers import is_binary_etl as _is_binary_etl
    return _is_binary_etl(path)


def parse_etl_binary(path: str) -> pl.DataFrame:
    """etl-parser로 바이너리 ETL 파일을 파싱한다."""
    from .etl_helpers import parse_etl_binary as _parse_etl_binary
    return _parse_etl_binary(path)


# ---------------------------------------------------------------------------
# CSV → Parquet conversion
# ---------------------------------------------------------------------------

def prepare_parquet_from_csv(
    loader: "FileLoader",
    path: str,
    encoding: str,
    delimiter: str,
    has_header: bool,
    skip_rows: int,
    comment_char: Optional[str],
) -> Optional[str]:
    """CSV를 Parquet으로 변환한다. 성공 시 parquet 경로, 실패 시 None."""
    parquet_path = f"{path}.parquet"
    try:
        if os.path.exists(parquet_path):
            csv_mtime = os.path.getmtime(path)
            pq_mtime = os.path.getmtime(parquet_path)
            if pq_mtime >= csv_mtime and os.path.getsize(parquet_path) > 0:
                return parquet_path

        loader._update_progress(status="converting_to_parquet")
        lf = pl.scan_csv(
            path, encoding=encoding, separator=delimiter,
            has_header=has_header, skip_rows=skip_rows,
            comment_prefix=comment_char, infer_schema_length=10000,
            ignore_errors=True,
        )
        lf.sink_parquet(parquet_path, compression="zstd")
        return parquet_path
    except Exception as e:
        logger.warning("file_loader.parquet_convert_failed", extra={"error": e})
        loader._warning_message = "Memory optimization unavailable. File loaded directly (higher memory usage)."
        return None


# ---------------------------------------------------------------------------
# Windowed / streaming loading
# ---------------------------------------------------------------------------

def collect_streaming(lazy_df: pl.LazyFrame) -> pl.DataFrame:
    """LazyFrame을 streaming 모드로 수집한다."""
    try:
        return lazy_df.collect(engine="streaming")
    except Exception:
        logger.debug("file_loader_formats.collect_streaming.engine_fallback", exc_info=True)
        return lazy_df.collect()


def load_window_from_lazy(
    lazy_df: pl.LazyFrame,
    window_start: int,
    window_size: int,
) -> pl.DataFrame:
    """LazyFrame에서 window 구간만 로드한다."""
    return collect_streaming(lazy_df.slice(window_start, window_size))


# ---------------------------------------------------------------------------
# Main internal load orchestration
# ---------------------------------------------------------------------------

def load_file_internal(
    loader: "FileLoader",
    path: str,
    file_type: FileType,
    encoding: str,
    delimiter: str,
    delimiter_type: DelimiterType,
    regex_pattern: Optional[str],
    has_header: bool,
    skip_rows: int,
    comment_char: Optional[str],
    sheet_name: Optional[str],
    chunk_size: Optional[int],
    optimize_memory: bool,
    excluded_columns: Optional[List[str]] = None,
    process_filter: Optional[List[str]] = None,
    sample_n: Optional[int] = None,
) -> bool:
    """실제 파일 로드를 수행한다. 성공 여부를 반환한다."""
    start_time = time.time()
    loader._warning_message = None

    try:
        with get_metrics().timed_operation("file.load"):
            encoding = loader._normalize_encoding(encoding)
            file_size = os.path.getsize(path)
            loader._windowed = False
            loader._total_rows = 0
            loader._window_start = 0
            loader._lazy_df = None

            if file_type in (FileType.CSV, FileType.TSV, FileType.PARQUET) and loader._should_use_windowed_loading(file_size):
                load_windowed(loader, path, file_type, encoding, delimiter, has_header, skip_rows, comment_char, excluded_columns)
            else:
                load_eager(loader, path, file_type, encoding, delimiter, delimiter_type,
                           regex_pattern, has_header, skip_rows, comment_char, sheet_name)

            if loader._cancel_loading:
                loader._df = None
                loader._update_progress(status="cancelled")
                return False

            if loader._df is None and not loader._windowed:
                loader._update_progress(status="cancelled")
                return False

            apply_post_load_transforms(loader, excluded_columns, process_filter, sample_n, optimize_memory, start_time)

        total_rows = loader._total_rows if loader._windowed and loader._total_rows else (len(loader._df) if loader._df is not None else 0)
        loaded_rows = len(loader._df) if loader._df is not None else 0
        loader._update_progress(
            status="complete",
            loaded_bytes=loader._progress.total_bytes,
            loaded_rows=loaded_rows,
            total_rows=total_rows,
            elapsed_seconds=time.time() - start_time,
        )
        gc.collect()
        if loader._df is not None:
            logger.info("file_loader.file_loaded", extra={"row_count": loaded_rows, "column_count": len(loader._df.columns)})
        get_metrics().increment("file.loaded")
        return True
    except Exception as e:
        logger.error("file_loader.file_load_failed", extra={"error": e}, exc_info=True)
        loader._update_progress(status="error", error_message=str(e))
        gc.collect()
        return False


# ---------------------------------------------------------------------------
# Windowed setup
# ---------------------------------------------------------------------------

def load_windowed(
    loader: "FileLoader",
    path: str,
    file_type: FileType,
    encoding: str,
    delimiter: str,
    has_header: bool,
    skip_rows: int,
    comment_char: Optional[str],
    excluded_columns: Optional[List[str]],
) -> None:
    """Set up lazy scan and load first window for large CSV/TSV/Parquet files."""
    if file_type in (FileType.CSV, FileType.TSV):
        sep = delimiter if file_type == FileType.CSV else "\t"
        lazy_df = pl.scan_csv(
            path, encoding=encoding, separator=sep,
            has_header=has_header, skip_rows=skip_rows,
            comment_prefix=comment_char, infer_schema_length=10000,
            ignore_errors=True,
        )
    else:
        lazy_df = pl.scan_parquet(path)

    if excluded_columns:
        lazy_df = lazy_df.drop(excluded_columns)

    loader._lazy_df = lazy_df
    try:
        loader._total_rows = int(loader._lazy_df.select(pl.len()).collect()[0, 0])
    except Exception:
        logger.warning("file_loader_formats.load_windowed.row_count_failed", exc_info=True)
        loader._total_rows = 0

    window_size = min(loader._window_size, loader._total_rows) if loader._total_rows > 0 else loader._window_size
    loader._df = load_window_from_lazy(loader._lazy_df, loader._window_start, window_size)
    loader._windowed = loader._total_rows > window_size if loader._total_rows else True


# ---------------------------------------------------------------------------
# Eager loading dispatcher
# ---------------------------------------------------------------------------

def load_eager(
    loader: "FileLoader",
    path: str,
    file_type: FileType,
    encoding: str,
    delimiter: str,
    delimiter_type: DelimiterType,
    regex_pattern: Optional[str],
    has_header: bool,
    skip_rows: int,
    comment_char: Optional[str],
    sheet_name: Optional[str],
) -> None:
    """Load the full file eagerly using the appropriate loader."""
    if file_type == FileType.CSV:
        loader._df = load_csv(path, encoding, delimiter, has_header, skip_rows, comment_char)
    elif file_type == FileType.TSV:
        loader._df = load_csv(path, encoding, "\t", has_header, skip_rows, comment_char)
    elif file_type in (FileType.TXT, FileType.CUSTOM):
        loader._df = load_text(loader, path, encoding, delimiter, delimiter_type,
                               regex_pattern, has_header, skip_rows, comment_char)
    elif file_type == FileType.ETL:
        loader._df = load_etl(loader, path, encoding, delimiter, delimiter_type,
                              regex_pattern, has_header, skip_rows, comment_char)
    elif file_type == FileType.EXCEL:
        loader._df = load_excel(path, sheet_name)
    elif file_type == FileType.PARQUET:
        loader._df = load_parquet(path)
    elif file_type == FileType.JSON:
        loader._df = load_json(path)
    else:
        raise DataLoadError(
            f"Unsupported file type: {file_type}",
            operation="load_eager",
            context={"file_type": str(file_type)},
        )


# ---------------------------------------------------------------------------
# Post-load transforms
# ---------------------------------------------------------------------------

def apply_post_load_transforms(
    loader: "FileLoader",
    excluded_columns: Optional[List[str]],
    process_filter: Optional[List[str]],
    sample_n: Optional[int],
    optimize_memory: bool,
    start_time: float,
) -> None:
    """Apply column exclusion, process filter, sampling, and memory optimization."""
    if excluded_columns and loader._df is not None and not loader._windowed:
        cols_to_drop = [c for c in excluded_columns if c in loader._df.columns]
        if cols_to_drop:
            loader._df = loader._df.drop(cols_to_drop)

    if process_filter and loader._df is not None:
        loader._df = apply_process_filter(loader._df, process_filter)

    if sample_n is not None and loader._df is not None and len(loader._df) > sample_n:
        loader._update_progress(status="sampling")
        original_rows = len(loader._df)
        loader._df = loader._df.sample(n=sample_n, seed=42)
        logger.info("file_loader.sampled", extra={"sample_n": sample_n, "original_rows": original_rows})

    if optimize_memory and loader._df is not None:
        loader._update_progress(status="optimizing")
        loader._df = optimize_memory_df(loader, loader._df)

    if loader._df is not None:
        loader._update_progress(status="profiling")
        loader._profile = create_profile(loader._df, time.time() - start_time)


# ---------------------------------------------------------------------------
# Data manipulation helpers
# ---------------------------------------------------------------------------

def optimize_memory_df(loader: "FileLoader", df: pl.DataFrame) -> pl.DataFrame:
    """메모리를 최적화한다 (with_columns 패턴으로 피크 메모리 절감)."""
    cast_exprs = []

    for col in df.columns:
        dtype = df[col].dtype
        series = df[col]

        if dtype in [pl.Int64, pl.Int32]:
            min_val = series.min()
            max_val = series.max()
            if min_val is not None and max_val is not None:
                if min_val >= -128 and max_val <= 127:
                    cast_exprs.append(pl.col(col).cast(pl.Int8))
                elif min_val >= -32768 and max_val <= 32767:
                    cast_exprs.append(pl.col(col).cast(pl.Int16))
                elif dtype == pl.Int64 and min_val >= -2147483648 and max_val <= 2147483647:
                    cast_exprs.append(pl.col(col).cast(pl.Int32))

        elif dtype == pl.Float64:
            should_keep = (
                loader._precision_mode == PrecisionMode.HIGH
                or loader._precision_mode == PrecisionMode.SCIENTIFIC
                or loader._is_precision_sensitive_column(col)
            )
            if not should_keep:
                cast_exprs.append(pl.col(col).cast(pl.Float32))

        elif dtype == pl.Utf8:
            unique_ratio = series.n_unique() / len(series) if len(series) > 0 else 1
            if unique_ratio < 0.5:
                cast_exprs.append(pl.col(col).cast(pl.Categorical))

    if cast_exprs:
        df = df.with_columns(cast_exprs)

    return df


def create_profile(df: pl.DataFrame, load_time: float) -> "DataProfile":
    """데이터 프로파일을 생성한다."""
    columns = []
    for col in df.columns:
        series = df[col]
        dtype = series.dtype

        col_info = ColumnInfo(
            name=col,
            dtype=str(dtype),
            null_count=series.null_count(),
            unique_count=series.n_unique(),
            is_numeric=dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64],
            is_temporal=dtype in [pl.Date, pl.Datetime, pl.Time],
            is_categorical=dtype == pl.Categorical or (dtype == pl.Utf8 and series.n_unique() < 100),
        )

        if col_info.is_numeric:
            col_info.min_value = series.min()
            col_info.max_value = series.max()

        non_null = series.drop_nulls()
        if len(non_null) > 0:
            col_info.sample_values = non_null.head(5).to_list()

        col_info.memory_bytes = series.estimated_size()
        columns.append(col_info)

    return DataProfile(
        total_rows=len(df),
        total_columns=len(df.columns),
        memory_bytes=df.estimated_size(),
        columns=columns,
        load_time_seconds=load_time,
    )
