"""
file_loader_formats_csv — CSV/TSV/TXT/ETL 포맷 로딩 함수 모음.

file_loader_formats 에서 분리된 텍스트 기반 포맷 특화 함수들.
"""
from __future__ import annotations

import os
import re
import logging
import tempfile
import subprocess
from typing import TYPE_CHECKING, Optional, List

import polars as pl

from .types import DelimiterType
from .etl_helpers import HAS_ETL_PARSER
from .exceptions import DataLoadError

if TYPE_CHECKING:
    from .file_loader import FileLoader

logger = logging.getLogger(__name__)


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
    from .file_loader_formats import is_binary_etl, parse_etl_binary

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
            raise DataLoadError(
                "ETL 파일 변환 실패",
                operation="load_etl",
                context={"path": path, "system": system},
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise DataLoadError(
                f"ETL 변환 오류: {e}",
                operation="load_etl",
                context={"path": path, "system": system},
            ) from e

    raise DataLoadError(
        f"ETL 바이너리 파일을 파싱할 수 없습니다 (시스템: {system})",
        operation="load_etl",
        context={"path": path, "system": system},
    )
