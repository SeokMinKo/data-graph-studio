"""
file_loader_formats — 파일 형식별 로딩 헬퍼 모음.

FileLoader 클래스에서 추출된 포맷 특화 함수들을 담는다.
각 함수는 독립 함수로 정의되며, 인스턴스 상태가 필요한 경우
첫 번째 인자로 FileLoader 인스턴스(loader)를 받는다.
"""
from __future__ import annotations

import gc
import os
import re
import time
import logging
import tempfile
import subprocess
from typing import TYPE_CHECKING, Optional, List, Dict

import polars as pl

from .types import FileType, DelimiterType, PrecisionMode, DataProfile, ColumnInfo
from .etl_helpers import HAS_ETL_PARSER
from .metrics import get_metrics

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
    """CSV를 Parquet으로 변환한다.

    Args:
        loader: FileLoader 인스턴스 (진행률 업데이트 및 경고 메시지용).
        path: 원본 CSV 파일 경로.
        encoding: 파일 인코딩.
        delimiter: 구분자.
        has_header: 헤더 존재 여부.
        skip_rows: 건너뛸 행 수.
        comment_char: 주석 문자.

    Returns:
        변환된 Parquet 파일 경로. 변환 실패 시 None.
    """
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
        return lazy_df.collect()


def load_window_from_lazy(
    lazy_df: pl.LazyFrame,
    window_start: int,
    window_size: int,
) -> pl.DataFrame:
    """LazyFrame에서 window 구간만 로드한다.

    Args:
        lazy_df: 원본 LazyFrame.
        window_start: 윈도우 시작 행.
        window_size: 윈도우 크기.

    Returns:
        슬라이스된 DataFrame.
    """
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
    """실제 파일 로드를 수행한다.

    Args:
        loader: FileLoader 인스턴스.
        path: 파일 경로.
        file_type: 파일 형식.
        encoding: 파일 인코딩.
        delimiter: 구분자.
        delimiter_type: 구분자 유형.
        regex_pattern: 정규식 패턴 (REGEX 구분자 유형에서 사용).
        has_header: 헤더 존재 여부.
        skip_rows: 건너뛸 행 수.
        comment_char: 주석 문자.
        sheet_name: 엑셀 시트 이름.
        chunk_size: 청크 크기 (미사용, 하위 호환성용).
        optimize_memory: 메모리 최적화 여부.
        excluded_columns: 제외할 컬럼 목록.
        process_filter: 프로세스 필터.
        sample_n: 샘플링 행 수.

    Returns:
        로딩 성공 여부.
    """
    start_time = time.time()
    loader._warning_message = None

    try:
        with get_metrics().timer("file.load_duration"):
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
        raise ValueError(f"Unsupported file type: {file_type}")


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
# Format-specific loaders (pure or near-pure functions)
# ---------------------------------------------------------------------------

def load_csv(
    path: str,
    encoding: str,
    delimiter: str,
    has_header: bool,
    skip_rows: int = 0,
    comment_char: Optional[str] = None,
) -> pl.DataFrame:
    """CSV를 로드한다."""
    return pl.read_csv(
        path, encoding=encoding, separator=delimiter,
        has_header=has_header, skip_rows=skip_rows,
        comment_prefix=comment_char, infer_schema_length=10000,
        ignore_errors=True,
    )


def load_text(
    loader: "FileLoader",
    path: str,
    encoding: str,
    delimiter: str,
    delimiter_type: DelimiterType,
    regex_pattern: Optional[str],
    has_header: bool,
    skip_rows: int = 0,
    comment_char: Optional[str] = None,
) -> Optional[pl.DataFrame]:
    """텍스트 파일을 로드한다."""
    MAX_TEXT_LINES = 1_000_000
    lines = []
    with open(path, 'r', encoding=encoding, errors='replace') as f:
        for i, line in enumerate(f):
            if loader._cancel_loading:
                return None
            if i >= MAX_TEXT_LINES:
                logger.warning("file_loader.text_file_truncated", extra={"max_lines": MAX_TEXT_LINES})
                break
            lines.append(line)

    lines = lines[skip_rows:]
    if comment_char:
        lines = [line for line in lines if not line.strip().startswith(comment_char)]
    lines = [line.strip() for line in lines if line.strip()]

    if not lines:
        return pl.DataFrame()

    rows = []
    for line in lines:
        if delimiter_type == DelimiterType.REGEX and regex_pattern:
            fields = re.split(regex_pattern, line)
        elif delimiter_type == DelimiterType.SPACE or delimiter == ' ':
            fields = line.split()
        else:
            fields = line.split(delimiter)
        rows.append([f.strip() for f in fields])

    if not rows:
        return pl.DataFrame()

    if has_header:
        headers = rows[0]
        data = rows[1:]
    else:
        max_cols = max(len(r) for r in rows)
        headers = [f"col_{i}" for i in range(max_cols)]
        data = rows

    max_cols = len(headers)
    normalized_data = []
    for row in data:
        if len(row) < max_cols:
            row = row + [''] * (max_cols - len(row))
        elif len(row) > max_cols:
            row = row[:max_cols]
        normalized_data.append(row)

    if not normalized_data:
        return pl.DataFrame({h: [] for h in headers})

    df_dict = {headers[i]: [row[i] for row in normalized_data] for i in range(max_cols)}
    df = pl.DataFrame(df_dict)

    # Type inference via sampling instead of exception-based casting
    int_pattern = re.compile(r'^-?\d+$')
    float_pattern = re.compile(r'^-?\d+\.?\d*(?:[eE][+-]?\d+)?$')

    cast_exprs = []
    for col in df.columns:
        sample = df[col].drop_nulls().head(100).to_list()
        sample = [s for s in sample if s.strip()] if sample else []
        if not sample:
            continue
        if all(int_pattern.match(s) for s in sample):
            cast_exprs.append(pl.col(col).cast(pl.Int64, strict=False))
        elif all(float_pattern.match(s) for s in sample):
            cast_exprs.append(pl.col(col).cast(pl.Float64, strict=False))

    if cast_exprs:
        df = df.with_columns(cast_exprs)
    return df


def load_etl(
    loader: "FileLoader",
    path: str,
    encoding: str,
    delimiter: str,
    delimiter_type: DelimiterType,
    regex_pattern: Optional[str],
    has_header: bool,
    skip_rows: int = 0,
    comment_char: Optional[str] = None,
) -> pl.DataFrame:
    """ETL 파일을 로드한다."""
    import platform

    _is_binary = is_binary_etl(path)

    if not _is_binary:
        return load_text(loader, path, encoding, delimiter, delimiter_type,
                         regex_pattern, has_header, skip_rows, comment_char)

    if HAS_ETL_PARSER:
        try:
            return parse_etl_binary(path)
        except (ImportError, ValueError, Exception) as e:
            logger.warning("file_loader.etl_parser_failed", extra={"error": e})
            loader._warning_message = "ETL file parsing failed, loaded as plain text. Data may be incomplete."

    system = platform.system()
    if system == 'Windows':
        try:
            with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
                tmp_path = tmp.name
            result = subprocess.run(
                ['tracerpt', path, '-o', tmp_path, '-of', 'CSV', '-y'],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                df = load_csv(tmp_path, encoding, ',', True, 0, None)
                os.unlink(tmp_path)
                return df
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise ValueError("ETL 파일 변환 실패")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise ValueError(f"ETL 변환 오류: {e}")

    raise ValueError(f"ETL 바이너리 파일을 파싱할 수 없습니다 (시스템: {system})")


def load_excel(path: str, sheet_name: Optional[str]) -> pl.DataFrame:
    """Excel을 로드한다."""
    return pl.read_excel(path, sheet_name=sheet_name or 0)


def load_parquet(path: str) -> pl.DataFrame:
    """Parquet을 로드한다."""
    return pl.read_parquet(path)


def load_json(path: str) -> pl.DataFrame:
    """JSON을 로드한다."""
    return pl.read_json(path)


# ---------------------------------------------------------------------------
# Data manipulation helpers
# ---------------------------------------------------------------------------

def apply_process_filter(df: pl.DataFrame, process_filter: List[str]) -> pl.DataFrame:
    """프로세스 필터를 적용한다."""
    if not process_filter or df is None:
        return df

    process_col_names = ['Process Name', 'ProcessName', 'Process', 'Image', 'Image Name']
    process_col = None
    for col_name in process_col_names:
        if col_name in df.columns:
            process_col = col_name
            break
    if process_col is None:
        for col in df.columns:
            if 'process' in col.lower():
                process_col = col
                break
    if process_col is None:
        return df

    return df.filter(pl.col(process_col).is_in(process_filter))


def optimize_memory_df(loader: "FileLoader", df: pl.DataFrame) -> pl.DataFrame:
    """메모리를 최적화한다 (with_columns 패턴으로 피크 메모리 절감).

    Args:
        loader: FileLoader 인스턴스 (정밀도 모드 및 정밀도 컬럼 목록용).
        df: 최적화할 DataFrame.
    """
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
    """데이터 프로파일을 생성한다.

    Args:
        df: 프로파일 대상 DataFrame.
        load_time: 로딩 소요 시간 (초).
    """
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
