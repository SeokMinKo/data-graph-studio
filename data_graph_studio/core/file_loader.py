"""
FileLoader — 파일 I/O 및 로딩 담당 모듈

DataEngine에서 추출된 파일 로딩 관련 로직을 담당한다.
CSV, TSV, TXT, Excel, Parquet, JSON, ETL 형식을 지원하며,
대용량 파일을 위한 windowed/lazy 로딩, 인코딩 정규화,
메모리 최적화, 정밀도 모드를 제공한다.

상태 소유:
    _df, _lazy_df, _progress, _cancel_loading
"""
import gc
import os
import re
import time
import logging
import tempfile
import subprocess
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Set

import polars as pl

from .types import (
    FileType, DelimiterType, LoadingProgress, DataProfile, ColumnInfo,
    DataSource, PrecisionMode,
)

from .etl_helpers import HAS_ETL_PARSER

logger = logging.getLogger(__name__)

def detect_encoding(path: str, sample_size: int = 10000) -> str:
    """파일 인코딩을 자동 감지한다."""
    try:
        from charset_normalizer import from_path
        result = from_path(path)
        best = result.best()
        return best.encoding if best else 'utf-8'
    except ImportError:
        # Fallback: try utf-8, then latin-1
        try:
            with open(path, 'r', encoding='utf-8') as f:
                f.read(sample_size)
            return 'utf-8'
        except UnicodeDecodeError:
            return 'latin-1'
    except Exception:
        return 'utf-8'


class FileLoader:
    """파일 로딩 전담 클래스.
    DataEngine의 파일 I/O 관련 상태와 메서드를 모두 소유한다.
    외부에서는 이 클래스를 직접 사용하지 않고 DataEngine Facade를 통해 접근한다.
    Attributes:
        _df: 현재 로딩된 DataFrame (단일 파일 / windowed 결과).
        _lazy_df: 대용량 파일의 LazyFrame.
        _progress: 로딩 진행 상태.
        _cancel_loading: 로딩 취소 플래그."""

    # 클래스 상수 — DataEngine에서 이관
    DEFAULT_CHUNK_SIZE = 100_000
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024
    LAZY_EVAL_THRESHOLD = 1024 * 1024 * 1024
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 0.5

    PRECISION_SENSITIVE_PATTERNS = [
        r'price', r'amount', r'rate', r'ratio', r'percent',
        r'lat', r'lon', r'coord', r'precision', r'accuracy',
        r'scientific', r'decimal',
    ]

    def __init__(self, precision_mode: PrecisionMode = PrecisionMode.AUTO):
        """FileLoader를 초기화한다.
            precision_mode: 부동소수점 정밀도 모드."""
        self._df: Optional[pl.DataFrame] = None
        self._lazy_df: Optional[pl.LazyFrame] = None
        self._source: Optional[DataSource] = None
        self._profile: Optional[DataProfile] = None
        self._progress: LoadingProgress = LoadingProgress()
        self._loading_thread: Optional[threading.Thread] = None
        self._cancel_loading: bool = False
        self._progress_callback: Optional[Callable[[LoadingProgress], None]] = None
        self._precision_mode: PrecisionMode = precision_mode
        self._precision_columns: Set[str] = set()

        # windowed loading
        self._total_rows: int = 0
        self._window_start: int = 0
        self._window_size: int = 200_000
        self._windowed: bool = False
    @property
    def df(self) -> Optional[pl.DataFrame]:
        """현재 로딩된 DataFrame."""
        return self._df
    @property
    def profile(self) -> Optional[DataProfile]:
        """데이터 프로파일."""
        return self._profile
    @property
    def progress(self) -> LoadingProgress:
        """로딩 진행 상태."""
        return self._progress
    @property
    def source(self) -> Optional[DataSource]:
        """데이터 소스 정보."""
        return self._source
    @property
    def is_loaded(self) -> bool:
        """데이터 로드 여부."""
        return self._df is not None
    @property
    def row_count(self) -> int:
        """총 행 수 (windowed인 경우 전체 행 수)."""
        if self._windowed and self._total_rows > 0:
            return self._total_rows
        return len(self._df) if self._df is not None else 0
    @property
    def column_count(self) -> int:
        """총 컬럼 수."""
        return len(self._df.columns) if self._df is not None else 0
    @property
    def columns(self) -> List[str]:
        """컬럼 이름 목록."""
        return self._df.columns if self._df is not None else []
    @property
    def dtypes(self) -> Dict[str, str]:
        """컬럼별 데이터 타입."""
        if self._df is None:
            return {}
        return {col: str(dtype) for col, dtype in zip(self._df.columns, self._df.dtypes)}
    @property
    def is_windowed(self) -> bool:
        """windowed 모드 여부."""
        return self._windowed
    @property
    def total_rows(self) -> int:
        """전체 행 수."""
        return self._total_rows if self._total_rows else self.row_count
    @property
    def window_start(self) -> int:
        """현재 윈도우 시작 행."""
        return self._window_start
    @property
    def window_size(self) -> int:
        """현재 윈도우 크기."""
        return self._window_size
    @property
    def has_lazy(self) -> bool:
        """LazyFrame 존재 여부."""
        return self._lazy_df is not None

    def set_progress_callback(self, callback: Callable[[LoadingProgress], None]) -> None:
        """진행률 콜백을 설정한다."""
        self._progress_callback = callback

    def set_precision_mode(self, mode: PrecisionMode) -> None:
        """정밀도 모드를 설정한다."""
        self._precision_mode = mode

    def add_precision_column(self, column: str) -> None:
        """정밀도 유지가 필요한 컬럼을 추가한다."""
        self._precision_columns.add(column)

    def cancel_loading(self) -> None:
        """진행 중인 로딩을 취소한다."""
        self._cancel_loading = True
    @staticmethod
    def detect_file_type(path: str) -> FileType:
        """파일 형식을 확장자로 감지한다."""
        ext = Path(path).suffix.lower()
        mapping = {
            '.csv': FileType.CSV,
            '.tsv': FileType.TSV,
            '.txt': FileType.TXT,
            '.log': FileType.TXT,
            '.dat': FileType.TXT,
            '.etl': FileType.ETL,
            '.xlsx': FileType.EXCEL,
            '.xls': FileType.EXCEL,
            '.parquet': FileType.PARQUET,
            '.pq': FileType.PARQUET,
            '.json': FileType.JSON,
        }
        return mapping.get(ext, FileType.TXT)
    @staticmethod
    def detect_delimiter(path: str, encoding: str = "utf-8", sample_lines: int = 10) -> str:
        """구분자를 자동 감지한다."""
        delimiters = [',', '\t', ';', '|', ' ']
        delimiter_counts: Dict[str, int] = {d: 0 for d in delimiters}

        try:
            with open(path, 'r', encoding=encoding, errors='ignore') as f:
                for i, line in enumerate(f):
                    if i >= sample_lines:
                        break
                    for d in delimiters:
                        delimiter_counts[d] += line.count(d)

            best = ','
            best_count = 0
            for d, count in delimiter_counts.items():
                if d == ' ':
                    if best_count == 0 and count > 0:
                        best = d
                elif count > best_count:
                    best = d
                    best_count = count
            return best
        except Exception:
            return ','

    def load_file(
        self,
        path: str,
        file_type: Optional[FileType] = None,
        encoding: str = "utf-8",
        delimiter: str = ",",
        delimiter_type: DelimiterType = DelimiterType.AUTO,
        regex_pattern: Optional[str] = None,
        has_header: bool = True,
        skip_rows: int = 0,
        comment_char: Optional[str] = None,
        sheet_name: Optional[str] = None,
        chunk_size: Optional[int] = None,
        optimize_memory: bool = True,
        async_load: bool = False,
        excluded_columns: Optional[List[str]] = None,
        process_filter: Optional[List[str]] = None,
        precision_mode: Optional[PrecisionMode] = None,
        sample_n: Optional[int] = None,
    ) -> bool:
        """파일을 로드한다.

        Args:
            sample_n: 로드 후 N개 행만 샘플링 (None이면 전체 로드).
        """
        if precision_mode is not None:
            self._precision_mode = precision_mode

        if not self._retry_file_access(path):
            self._update_progress(status="error", error_message=f"File not found or not accessible: {path}")
            return False

        if file_type is None:
            file_type = self.detect_file_type(path)

        # Auto-detect encoding for text-based formats
        if encoding == "utf-8" and file_type in (FileType.CSV, FileType.TSV, FileType.TXT, FileType.CUSTOM):
            detected = detect_encoding(path)
            if detected and detected != 'utf-8':
                logger.info(f"Auto-detected encoding: {detected}")
                encoding = detected

        if delimiter_type == DelimiterType.AUTO:
            delimiter = self.detect_delimiter(path, encoding)
        elif delimiter_type == DelimiterType.REGEX:
            delimiter = regex_pattern or delimiter
        elif delimiter_type != DelimiterType.REGEX:
            delimiter = delimiter_type.value

        self._source = DataSource(
            path=path,
            file_type=file_type,
            encoding=encoding,
            delimiter=delimiter,
            delimiter_type=delimiter_type,
            regex_pattern=regex_pattern,
            has_header=has_header,
            skip_rows=skip_rows,
            comment_char=comment_char,
            sheet_name=sheet_name,
        )

        file_size = os.path.getsize(path)
        self._update_progress(status="loading", total_bytes=file_size, loaded_bytes=0)

        if self._should_convert_to_parquet(file_type, file_size):
            parquet_path = self._prepare_parquet_from_csv(
                path, encoding=encoding, delimiter=delimiter,
                has_header=has_header, skip_rows=skip_rows, comment_char=comment_char,
            )
            if parquet_path:
                path = parquet_path
                file_type = FileType.PARQUET

        if async_load:
            self._cancel_loading = False
            self._loading_thread = threading.Thread(
                target=self._load_file_internal,
                args=(path, file_type, encoding, delimiter, delimiter_type,
                      regex_pattern, has_header, skip_rows, comment_char,
                      sheet_name, chunk_size, optimize_memory, excluded_columns,
                      process_filter, sample_n),
            )
            self._loading_thread.start()
            return True

        return self._load_file_internal(
            path, file_type, encoding, delimiter, delimiter_type,
            regex_pattern, has_header, skip_rows, comment_char,
            sheet_name, chunk_size, optimize_memory, excluded_columns,
            process_filter, sample_n,
        )

    def set_window(self, start: int, size: int) -> bool:
        """현재 window 구간을 변경한다."""
        if self._lazy_df is None:
            return False

        start = max(0, int(start))
        size = max(1, int(size))

        self._window_start = start
        self._window_size = size
        self._df = self._load_window_from_lazy(self._lazy_df, start, size)
        self._windowed = True
        return True

    def load_lazy(self, path: str, **kwargs: Any) -> bool:
        """LazyFrame으로 파일을 로드한다."""
        if not self._retry_file_access(path):
            self._update_progress(status="error", error_message=f"File not found: {path}")
            return False

        file_type = self.detect_file_type(path)

        try:
            if file_type == FileType.CSV:
                self._lazy_df = pl.scan_csv(path, **kwargs)
            elif file_type == FileType.PARQUET:
                self._lazy_df = pl.scan_parquet(path, **kwargs)
            elif file_type == FileType.JSON:
                self._df = pl.read_json(path)
                self._lazy_df = self._df.lazy()
            else:
                success = self.load_file(path, file_type=file_type, **kwargs)
                if success and self._df is not None:
                    self._lazy_df = self._df.lazy()
                return success

            logger.info(f"LazyFrame created for: {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create LazyFrame: {e}")
            self._update_progress(status="error", error_message=str(e))
            return False

    def collect_lazy(self, limit: Optional[int] = None, optimize_memory: bool = True) -> bool:
        """LazyFrame을 DataFrame으로 수집한다."""
        if self._lazy_df is None:
            logger.warning("No LazyFrame to collect")
            return False

        try:
            self._update_progress(status="collecting")

            if limit is not None:
                self._df = self._lazy_df.head(limit).collect()
            else:
                self._df = self._lazy_df.collect()

            if optimize_memory:
                self._update_progress(status="optimizing")
                self._df = self._optimize_memory(self._df)

            self._update_progress(status="profiling")
            self._profile = self._create_profile(self._df, 0)

            gc.collect()
            logger.info(f"LazyFrame collected: {len(self._df):,} rows")
            return True
        except Exception as e:
            logger.error(f"Failed to collect LazyFrame: {e}")
            return False

    def query_lazy(self, expr: pl.Expr) -> Optional[pl.LazyFrame]:
        """LazyFrame에 표현식을 적용한다."""
        if self._lazy_df is None:
            return None
        return self._lazy_df.filter(expr)

    def clear(self) -> None:
        """모든 로딩 상태를 초기화한다."""
        self._df = None
        self._lazy_df = None
        self._source = None
        self._profile = None
        self._precision_columns.clear()
        self._progress = LoadingProgress()
        self._total_rows = 0
        self._window_start = 0
        self._windowed = False
        gc.collect()
    @staticmethod
    def is_binary_etl(path: str) -> bool:
        """ETL 파일이 바이너리인지 확인한다."""
        from .etl_helpers import is_binary_etl
        return is_binary_etl(path)
    @staticmethod
    def parse_etl_binary(path: str) -> pl.DataFrame:
        """etl-parser로 바이너리 ETL 파일을 파싱한다."""
        from .etl_helpers import parse_etl_binary
        return parse_etl_binary(path)
    @staticmethod
    def _normalize_encoding(encoding: str) -> str:
        """인코딩 이름을 Polars 호환 형식으로 정규화한다.
            encoding: 원본 인코딩 이름."""
        if not encoding:
            return "utf8"
        enc = encoding.strip().lower().replace("_", "-")
        mapping = {
            "utf-8": "utf8", "utf8": "utf8", "utf-8-sig": "utf8",
            "utf-16": "utf16", "utf16": "utf16",
            "latin-1": "iso-8859-1", "latin1": "iso-8859-1",
            "ascii": "utf8",
        }
        return mapping.get(enc, encoding)

    def _update_progress(self, **kwargs: Any) -> None:
        """진행률을 업데이트한다."""
        for key, value in kwargs.items():
            if hasattr(self._progress, key):
                setattr(self._progress, key, value)
        if self._progress_callback:
            self._progress_callback(self._progress)

    def _retry_file_access(self, path: str) -> bool:
        """파일 접근을 재시도한다."""
        for attempt in range(self.MAX_RETRIES):
            try:
                if os.path.exists(path) and os.access(path, os.R_OK):
                    return True
            except OSError:
                pass
            if attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_DELAY_SECONDS * (attempt + 1))
        return False

    def _should_convert_to_parquet(self, file_type: FileType, file_size: int) -> bool:
        """대용량 CSV를 Parquet으로 전환할지 결정한다."""
        if file_type not in (FileType.CSV, FileType.TSV):
            return False
        return file_size >= 500 * 1024 * 1024

    def _should_use_windowed_loading(self, file_size: int) -> bool:
        """windowed loading 적용 여부를 결정한다."""
        return file_size >= 300 * 1024 * 1024

    def _prepare_parquet_from_csv(
        self, path: str, encoding: str, delimiter: str,
        has_header: bool, skip_rows: int, comment_char: Optional[str],
    ) -> Optional[str]:
        """CSV를 Parquet으로 변환한다."""
        parquet_path = f"{path}.parquet"
        try:
            if os.path.exists(parquet_path):
                csv_mtime = os.path.getmtime(path)
                pq_mtime = os.path.getmtime(parquet_path)
                if pq_mtime >= csv_mtime and os.path.getsize(parquet_path) > 0:
                    return parquet_path

            self._update_progress(status="converting_to_parquet")
            lf = pl.scan_csv(
                path, encoding=encoding, separator=delimiter,
                has_header=has_header, skip_rows=skip_rows,
                comment_prefix=comment_char, infer_schema_length=10000,
                ignore_errors=True,
            )
            lf.sink_parquet(parquet_path, compression="zstd")
            return parquet_path
        except Exception as e:
            logger.warning(f"Failed to convert to parquet: {e}")
            return None

    def _load_window_from_lazy(
        self, lazy_df: pl.LazyFrame, window_start: int, window_size: int,
    ) -> pl.DataFrame:
        """LazyFrame에서 window 구간만 로드한다."""
        return self._collect_streaming(lazy_df.slice(window_start, window_size))

    def _collect_streaming(self, lazy_df: pl.LazyFrame) -> pl.DataFrame:
        """LazyFrame을 streaming 모드로 수집한다."""
        try:
            return lazy_df.collect(engine="streaming")
        except Exception:
            return lazy_df.collect()

    def _load_file_internal(
        self, path: str, file_type: FileType, encoding: str,
        delimiter: str, delimiter_type: DelimiterType,
        regex_pattern: Optional[str], has_header: bool, skip_rows: int,
        comment_char: Optional[str], sheet_name: Optional[str],
        chunk_size: Optional[int], optimize_memory: bool,
        excluded_columns: Optional[List[str]] = None,
        process_filter: Optional[List[str]] = None,
        sample_n: Optional[int] = None,
    ) -> bool:
        """실제 파일 로드를 수행한다."""
        start_time = time.time()

        try:
            encoding = self._normalize_encoding(encoding)
            file_size = os.path.getsize(path)
            self._windowed = False
            self._total_rows = 0
            self._window_start = 0
            self._lazy_df = None

            if file_type in (FileType.CSV, FileType.TSV, FileType.PARQUET) and self._should_use_windowed_loading(file_size):
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

                self._lazy_df = lazy_df
                try:
                    self._total_rows = int(self._lazy_df.select(pl.len()).collect()[0, 0])
                except Exception:
                    self._total_rows = 0

                window_size = min(self._window_size, self._total_rows) if self._total_rows > 0 else self._window_size
                self._df = self._load_window_from_lazy(self._lazy_df, self._window_start, window_size)
                self._windowed = self._total_rows > window_size if self._total_rows else True
            else:
                if file_type == FileType.CSV:
                    self._df = self._load_csv(path, encoding, delimiter, has_header, skip_rows, comment_char)
                elif file_type == FileType.TSV:
                    self._df = self._load_csv(path, encoding, "\t", has_header, skip_rows, comment_char)
                elif file_type in [FileType.TXT, FileType.CUSTOM]:
                    self._df = self._load_text(path, encoding, delimiter, delimiter_type,
                                               regex_pattern, has_header, skip_rows, comment_char)
                elif file_type == FileType.ETL:
                    self._df = self._load_etl(path, encoding, delimiter, delimiter_type,
                                              regex_pattern, has_header, skip_rows, comment_char)
                elif file_type == FileType.EXCEL:
                    self._df = self._load_excel(path, sheet_name)
                elif file_type == FileType.PARQUET:
                    self._df = self._load_parquet(path)
                elif file_type == FileType.JSON:
                    self._df = self._load_json(path)
                else:
                    raise ValueError(f"Unsupported file type: {file_type}")

            if self._cancel_loading:
                self._df = None
                self._update_progress(status="cancelled")
                return False

            # loader returned None (e.g. cancel during _load_text)
            if self._df is None and not self._windowed:
                self._update_progress(status="cancelled")
                return False

            if excluded_columns and self._df is not None and not self._windowed:
                cols_to_drop = [c for c in excluded_columns if c in self._df.columns]
                if cols_to_drop:
                    self._df = self._df.drop(cols_to_drop)

            if process_filter and self._df is not None:
                self._df = self._apply_process_filter(self._df, process_filter)

            if sample_n is not None and self._df is not None and len(self._df) > sample_n:
                self._update_progress(status="sampling")
                original_rows = len(self._df)
                self._df = self._df.sample(n=sample_n, seed=42)
                logger.info(f"Sampled {sample_n:,} rows from {original_rows:,}")

            if optimize_memory and self._df is not None:
                self._update_progress(status="optimizing")
                self._df = self._optimize_memory(self._df)

            if self._df is not None:
                self._update_progress(status="profiling")
                self._profile = self._create_profile(self._df, time.time() - start_time)

            total_rows = self._total_rows if self._windowed and self._total_rows else (len(self._df) if self._df is not None else 0)
            loaded_rows = len(self._df) if self._df is not None else 0

            self._update_progress(
                status="complete",
                loaded_bytes=self._progress.total_bytes,
                loaded_rows=loaded_rows,
                total_rows=total_rows,
                elapsed_seconds=time.time() - start_time,
            )

            gc.collect()
            if self._df is not None:
                logger.info(f"File loaded successfully: {loaded_rows:,} rows, {len(self._df.columns)} columns")
            return True
        except Exception as e:
            logger.error(f"Failed to load file: {e}", exc_info=True)
            self._update_progress(status="error", error_message=str(e))
            gc.collect()
            return False

    def _load_csv(self, path: str, encoding: str, delimiter: str,
                  has_header: bool, skip_rows: int = 0,
                  comment_char: Optional[str] = None) -> pl.DataFrame:
        """CSV를 로드한다."""
        return pl.read_csv(
            path, encoding=encoding, separator=delimiter,
            has_header=has_header, skip_rows=skip_rows,
            comment_prefix=comment_char, infer_schema_length=10000,
            ignore_errors=True,
        )

    def _load_text(self, path: str, encoding: str, delimiter: str,
                   delimiter_type: DelimiterType, regex_pattern: Optional[str],
                   has_header: bool, skip_rows: int = 0,
                   comment_char: Optional[str] = None) -> pl.DataFrame:
        """텍스트 파일을 로드한다."""
        MAX_TEXT_LINES = 1_000_000
        lines = []
        with open(path, 'r', encoding=encoding, errors='replace') as f:
            for i, line in enumerate(f):
                if self._cancel_loading:
                    return None
                if i >= MAX_TEXT_LINES:
                    logger.warning(f"Text file truncated at {MAX_TEXT_LINES:,} lines")
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

    def _load_etl(self, path: str, encoding: str, delimiter: str,
                  delimiter_type: DelimiterType, regex_pattern: Optional[str],
                  has_header: bool, skip_rows: int = 0,
                  comment_char: Optional[str] = None) -> pl.DataFrame:
        """ETL 파일을 로드한다."""
        import platform

        is_binary = self.is_binary_etl(path)

        if not is_binary:
            return self._load_text(path, encoding, delimiter, delimiter_type,
                                   regex_pattern, has_header, skip_rows, comment_char)

        if HAS_ETL_PARSER:
            try:
                return self.parse_etl_binary(path)
            except (ImportError, ValueError, Exception) as e:
                logger.warning(f"etl-parser failed: {e}")

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
                    df = self._load_csv(tmp_path, encoding, ',', True, 0, None)
                    os.unlink(tmp_path)
                    return df
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise ValueError("ETL 파일 변환 실패")
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                raise ValueError(f"ETL 변환 오류: {e}")

        raise ValueError(f"ETL 바이너리 파일을 파싱할 수 없습니다 (시스템: {system})")

    def _load_excel(self, path: str, sheet_name: Optional[str]) -> pl.DataFrame:
        """Excel을 로드한다."""
        return pl.read_excel(path, sheet_name=sheet_name or 0)

    def _load_parquet(self, path: str) -> pl.DataFrame:
        """Parquet을 로드한다."""
        return pl.read_parquet(path)

    def _load_json(self, path: str) -> pl.DataFrame:
        """JSON을 로드한다."""
        return pl.read_json(path)

    def _apply_process_filter(self, df: pl.DataFrame, process_filter: List[str]) -> pl.DataFrame:
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

    def _is_precision_sensitive_column(self, col_name: str) -> bool:
        """컬럼이 정밀도 유지가 필요한지 확인한다."""
        if col_name in self._precision_columns:
            return True
        col_lower = col_name.lower()
        for pattern in self.PRECISION_SENSITIVE_PATTERNS:
            if re.search(pattern, col_lower):
                return True
        return False

    def _optimize_memory(self, df: pl.DataFrame) -> pl.DataFrame:
        """메모리를 최적화한다 (with_columns 패턴으로 피크 메모리 절감).
            df: 최적화할 DataFrame."""
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
                    self._precision_mode == PrecisionMode.HIGH
                    or self._precision_mode == PrecisionMode.SCIENTIFIC
                    or self._is_precision_sensitive_column(col)
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

    def _create_profile(self, df: pl.DataFrame, load_time: float) -> DataProfile:
        """데이터 프로파일을 생성한다.
            df: 프로파일 대상 DataFrame."""
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
