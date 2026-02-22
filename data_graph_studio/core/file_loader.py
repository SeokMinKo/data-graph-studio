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
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Set

import polars as pl

from .types import (
    FileType, DelimiterType, LoadingProgress, DataProfile,
    DataSource, PrecisionMode,
)

from .file_loader_formats import (
    is_binary_etl as _is_binary_etl,
    parse_etl_binary as _parse_etl_binary,
    prepare_parquet_from_csv,
    load_window_from_lazy,
    collect_streaming,
    load_file_internal,
    optimize_memory_df,
    create_profile,
)

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
        self._warning_message: Optional[str] = None

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

    @property
    def warning_message(self) -> Optional[str]:
        """마지막 로딩 중 발생한 사용자 표시 경고 메시지."""
        return self._warning_message

    def set_progress_callback(self, callback: Callable[[LoadingProgress], None]) -> None:
        """진행률 콜백을 설정한다."""
        self._progress_callback = callback

    def set_precision_mode(self, mode: PrecisionMode) -> None:
        """정밀도 모드를 설정한다."""
        self._precision_mode = mode

    def add_precision_column(self, column: str) -> None:
        """정밀도 유지가 필요한 컬럼을 추가한다."""
        if not isinstance(column, str) or not column.strip():
            raise ValueError(f"column must be a non-empty string, got {column!r}")
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
                logger.info("file_loader.encoding_detected", extra={"encoding": detected})
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

            logger.info("file_loader.lazy_frame_created", extra={"path": path})
            return True
        except Exception as e:
            logger.error("file_loader.lazy_frame_create_failed", extra={"error": e})
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
            logger.info("file_loader.lazy_frame_collected", extra={"row_count": len(self._df)})
            return True
        except Exception as e:
            logger.error("file_loader.lazy_frame_collect_failed", extra={"error": e})
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
        return _is_binary_etl(path)

    @staticmethod
    def parse_etl_binary(path: str) -> pl.DataFrame:
        """etl-parser로 바이너리 ETL 파일을 파싱한다."""
        return _parse_etl_binary(path)
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
        return prepare_parquet_from_csv(
            self, path, encoding=encoding, delimiter=delimiter,
            has_header=has_header, skip_rows=skip_rows, comment_char=comment_char,
        )

    def _load_window_from_lazy(
        self, lazy_df: pl.LazyFrame, window_start: int, window_size: int,
    ) -> pl.DataFrame:
        """LazyFrame에서 window 구간만 로드한다."""
        return load_window_from_lazy(lazy_df, window_start, window_size)

    def _collect_streaming(self, lazy_df: pl.LazyFrame) -> pl.DataFrame:
        """LazyFrame을 streaming 모드로 수집한다."""
        return collect_streaming(lazy_df)

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
        return load_file_internal(
            self, path, file_type, encoding, delimiter, delimiter_type,
            regex_pattern, has_header, skip_rows, comment_char, sheet_name,
            chunk_size, optimize_memory, excluded_columns, process_filter, sample_n,
        )

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
        return optimize_memory_df(self, df)

    def _create_profile(self, df: pl.DataFrame, load_time: float) -> DataProfile:
        """데이터 프로파일을 생성한다.
            df: 프로파일 대상 DataFrame."""
        return create_profile(df, load_time)
