"""file_loader_formats — format-specific loading helpers extracted from FileLoader.

Each function is a standalone helper. When instance state is needed, the first
argument is the FileLoader instance (``loader``).

Format implementations live in sub-modules:
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
from .constants import INFER_SCHEMA_LENGTH

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
    """Return True if the ETL file at path is binary rather than plain text.

    Input: path — str, absolute or relative filesystem path to the ETL file
    Output: bool — True when the file starts with a binary magic signature
    """
    from .etl_helpers import is_binary_etl as _is_binary_etl
    return _is_binary_etl(path)


def parse_etl_binary(path: str) -> pl.DataFrame:
    """Parse a binary ETL file using the etl-parser library and return a DataFrame.

    Input: path — str, path to a binary ETL file
    Output: pl.DataFrame — parsed tabular data from the ETL binary format
    Raises: DataLoadError — when etl-parser is unavailable or the file is malformed
    """
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
    """Convert a CSV file to a Parquet cache file and return the cache path.

    Skips conversion when a fresh cache already exists (parquet mtime >= csv mtime
    and file size > 0). On any I/O or memory failure the warning is stored on
    loader._warning_message and None is returned so the caller can fall back to
    direct CSV loading.

    Input:
        loader — FileLoader, provides _update_progress and _warning_message
        path — str, absolute path to the source CSV file
        encoding — str, character encoding of the CSV (e.g. "utf-8")
        delimiter — str, field separator character
        has_header — bool, whether the first non-skipped row is a header
        skip_rows — int, number of rows to skip before reading
        comment_char — Optional[str], line prefix that marks comment rows
    Output: Optional[str] — parquet cache path on success, None on failure
    Invariants: the returned path, when not None, is a readable Parquet file
        whose content matches the CSV at path
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
            comment_prefix=comment_char, infer_schema_length=INFER_SCHEMA_LENGTH,
            ignore_errors=True,
        )
        lf.sink_parquet(parquet_path, compression="zstd")
        return parquet_path
    except (OSError, PermissionError, MemoryError, pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError) as e:
        logger.warning("file_loader.parquet_convert_failed", extra={"reason": type(e).__name__, "path": str(path)})
        loader._warning_message = "Memory optimization unavailable. File loaded directly (higher memory usage)."
        return None


# ---------------------------------------------------------------------------
# Windowed / streaming loading
# ---------------------------------------------------------------------------

def collect_streaming(lazy_df: pl.LazyFrame) -> pl.DataFrame:
    """Collect a LazyFrame using the streaming engine, falling back to default on error.

    Input: lazy_df — pl.LazyFrame, the lazy query to materialize
    Output: pl.DataFrame — the collected result
    Invariants: always returns a DataFrame; never raises on streaming failure
    """
    try:
        return lazy_df.collect(engine="streaming")
    except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, MemoryError, OSError) as e:
        logger.debug("file_loader_formats.collect_streaming.engine_fallback",
                     extra={"reason": type(e).__name__})
        return lazy_df.collect()


def load_window_from_lazy(
    lazy_df: pl.LazyFrame,
    window_start: int,
    window_size: int,
) -> pl.DataFrame:
    """Collect a row-range slice from a LazyFrame.

    Input:
        lazy_df — pl.LazyFrame, source query
        window_start — int, zero-based index of the first row to include; >= 0
        window_size — int, maximum number of rows to return; > 0
    Output: pl.DataFrame — rows [window_start, window_start + window_size)
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
    """Orchestrate the full file-load pipeline and return True on success.

    Chooses windowed or eager loading based on file size, then applies
    post-load transforms (column exclusion, process filter, sampling, memory
    optimization, profiling). Progress events are emitted to loader throughout.
    Exceptions are caught internally; the caller receives a bool result.

    Input:
        loader — FileLoader, owns state (_df, _lazy_df, _windowed, etc.)
        path — str, absolute path to the file to load
        file_type — FileType, the format enum value
        encoding — str, character encoding
        delimiter — str, field separator (CSV/TXT/ETL)
        delimiter_type — DelimiterType, how the delimiter is interpreted
        regex_pattern — Optional[str], regex used when delimiter_type is REGEX
        has_header — bool, whether the first data row is a header
        skip_rows — int, rows to skip before reading; >= 0
        comment_char — Optional[str], single-character comment prefix
        sheet_name — Optional[str], Excel sheet name or index
        chunk_size — Optional[int], reserved for future chunked loading
        optimize_memory — bool, whether to downcast column dtypes after load
        excluded_columns — Optional[List[str]], column names to drop
        process_filter — Optional[List[str]], ETL process names to keep
        sample_n — Optional[int], cap the loaded rows to this count via random sample
    Output: bool — True when data was loaded into loader._df; False on
        cancellation, missing data, or exception
    Invariants: loader._df is None when False is returned
    """
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
    except (ValueError, OSError, UnicodeDecodeError, pl.exceptions.InvalidOperationError) as e:
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
    """Set up lazy scan and load first window for large CSV/TSV/Parquet files.

    Stores the LazyFrame in loader._lazy_df, counts total rows, loads the first
    window into loader._df, and sets loader._windowed = True when the file
    exceeds one window. Row count failures are logged and suppressed.

    Input:
        loader — FileLoader, receives _lazy_df, _total_rows, _df, _windowed
        path — str, absolute path to the file
        file_type — FileType, one of CSV, TSV, or PARQUET
        encoding — str, character encoding for text formats
        delimiter — str, field separator (CSV only)
        has_header — bool, whether the first row is a header
        skip_rows — int, rows to skip before data; >= 0
        comment_char — Optional[str], single-character comment line prefix
        excluded_columns — Optional[List[str]], columns to drop from the lazy scan
    Invariants: loader._df contains the first window after this call returns
    """
    if file_type in (FileType.CSV, FileType.TSV):
        sep = delimiter if file_type == FileType.CSV else "\t"
        lazy_df = pl.scan_csv(
            path, encoding=encoding, separator=sep,
            has_header=has_header, skip_rows=skip_rows,
            comment_prefix=comment_char, infer_schema_length=INFER_SCHEMA_LENGTH,
            ignore_errors=True,
        )
    else:
        lazy_df = pl.scan_parquet(path)

    if excluded_columns:
        lazy_df = lazy_df.drop(excluded_columns)

    loader._lazy_df = lazy_df
    try:
        loader._total_rows = int(loader._lazy_df.select(pl.len()).collect()[0, 0])
    except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError, MemoryError, OSError) as e:
        logger.warning("file_loader_formats.load_windowed.row_count_failed",
                       extra={"reason": type(e).__name__, "path": path})
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
    """Load the full file eagerly using the appropriate format-specific loader.

    Dispatches to load_csv, load_text, load_etl, load_excel, load_parquet, or
    load_json based on file_type and stores the result in loader._df.

    Input:
        loader — FileLoader, receives _df after loading
        path — str, absolute path to the file
        file_type — FileType, determines which loader is called
        encoding — str, character encoding for text-based formats
        delimiter — str, field separator character
        delimiter_type — DelimiterType, interpretation mode for the delimiter
        regex_pattern — Optional[str], regex split pattern when delimiter_type is REGEX
        has_header — bool, whether the first row is a column header
        skip_rows — int, rows to skip at the start of the file; >= 0
        comment_char — Optional[str], single-character prefix for comment lines
        sheet_name — Optional[str], Excel sheet name; None selects the first sheet
    Raises: DataLoadError — when file_type is not recognized
    Invariants: loader._df is set to a non-None DataFrame on success
    """
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
    """Apply column exclusion, process filtering, sampling, memory optimization, and profiling.

    Mutates loader._df in place through a sequence of optional transforms.
    Each step is skipped when its controlling argument is None/False or when
    loader._df is None. Progress events are emitted for optimizing and profiling.

    Input:
        loader — FileLoader, owns _df and provides _update_progress
        excluded_columns — Optional[List[str]], columns to drop (skipped in windowed mode)
        process_filter — Optional[List[str]], ETL process names to keep
        sample_n — Optional[int], max rows after random sampling with seed=42
        optimize_memory — bool, whether to downcast dtypes via optimize_memory_df
        start_time — float, epoch time when loading began (used to compute load_time)
    Invariants: loader._profile is set when loader._df is not None after transforms
    """
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
    """Downcast column dtypes to minimize memory usage and return the optimized DataFrame.

    Integer columns are narrowed to the smallest signed type that fits their
    value range (Int8 → Int16 → Int32). Float64 columns are cast to Float32
    unless precision mode is HIGH or SCIENTIFIC, or the column is flagged as
    precision-sensitive. String columns with < 50% unique values are converted
    to Categorical. All casts are applied in a single with_columns call to
    minimize peak memory during transformation.

    Input:
        loader — FileLoader, consulted for _precision_mode and
            _is_precision_sensitive_column
        df — pl.DataFrame, the frame to optimize; not mutated in-place
    Output: pl.DataFrame — new frame with downcasted column types
    Invariants: column names and row count are unchanged; values are preserved
        within the target type range
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
    """Build a DataProfile describing the structure and statistics of a DataFrame.

    Iterates over all columns to collect dtype, null count, unique count,
    numeric/temporal/categorical flags, min/max for numeric columns, and up to
    five sample values. Estimated memory size is recorded per column and for
    the whole frame.

    Input:
        df — pl.DataFrame, the loaded data to profile
        load_time — float, elapsed seconds from load start to now
    Output: DataProfile — immutable snapshot of df's shape, column metadata,
        and load timing
    Invariants: returned profile reflects the state of df at call time;
        len(profile.columns) == len(df.columns)
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
