"""
Data Engine - Polars 기반 빅데이터 처리 엔진

멀티 데이터셋 비교 기능 지원
"""

import gc
import os
import re
import time
import logging
import warnings
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Union, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor
import subprocess
import tempfile
from datetime import datetime
import uuid

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import numpy as np

# scipy for statistical tests
try:
    from scipy import stats as scipy_stats
    from scipy.stats import pearsonr, spearmanr, ttest_ind, mannwhitneyu, ks_2samp
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# 로깅 설정
logger = logging.getLogger(__name__)


class FileType(Enum):
    """지원 파일 형식"""
    CSV = "csv"
    EXCEL = "excel"
    PARQUET = "parquet"
    JSON = "json"
    TSV = "tsv"
    TXT = "txt"
    ETL = "etl"
    CUSTOM = "custom"


class DelimiterType(Enum):
    """구분자 타입"""
    COMMA = ","
    TAB = "\t"
    SPACE = " "
    SEMICOLON = ";"
    PIPE = "|"
    REGEX = "regex"
    AUTO = "auto"


@dataclass
class LoadingProgress:
    """로딩 진행 상태"""
    total_bytes: int = 0
    loaded_bytes: int = 0
    total_rows: int = 0
    loaded_rows: int = 0
    current_chunk: int = 0
    total_chunks: int = 0
    elapsed_seconds: float = 0.0
    status: str = "idle"  # idle, loading, indexing, complete, error
    error_message: Optional[str] = None
    
    @property
    def progress_percent(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return (self.loaded_bytes / self.total_bytes) * 100
    
    @property
    def eta_seconds(self) -> float:
        if self.loaded_bytes == 0 or self.elapsed_seconds == 0:
            return 0.0
        rate = self.loaded_bytes / self.elapsed_seconds
        remaining = self.total_bytes - self.loaded_bytes
        return remaining / rate if rate > 0 else 0.0


@dataclass
class ColumnInfo:
    """컬럼 정보"""
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
    """데이터 프로파일"""
    total_rows: int
    total_columns: int
    memory_bytes: int
    columns: List[ColumnInfo]
    load_time_seconds: float


@dataclass
class DatasetInfo:
    """
    개별 데이터셋 정보

    멀티 데이터셋 비교를 위한 데이터셋 컨테이너
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    df: Optional[pl.DataFrame] = None
    lazy_df: Optional[pl.LazyFrame] = None
    source: Optional['DataSource'] = None
    profile: Optional[DataProfile] = None
    color: str = "#1f77b4"
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def row_count(self) -> int:
        return len(self.df) if self.df is not None else 0

    @property
    def column_count(self) -> int:
        return len(self.df.columns) if self.df is not None else 0

    @property
    def columns(self) -> List[str]:
        return self.df.columns if self.df is not None else []

    @property
    def memory_bytes(self) -> int:
        return self.df.estimated_size() if self.df is not None else 0

    @property
    def is_loaded(self) -> bool:
        return self.df is not None


@dataclass
class DataSource:
    """데이터 소스 정보"""
    path: Optional[str] = None
    file_type: Optional[FileType] = None
    encoding: str = "utf-8"
    delimiter: str = ","
    delimiter_type: DelimiterType = DelimiterType.COMMA
    regex_pattern: Optional[str] = None  # regex 구분자용
    has_header: bool = True
    skip_rows: int = 0  # 상단 스킵할 행 수
    comment_char: Optional[str] = None  # 주석 문자 (예: #)
    sheet_name: Optional[str] = None  # Excel용


class PrecisionMode(Enum):
    """부동소수점 정밀도 모드"""
    AUTO = "auto"  # 자동 다운캐스팅 (기본값, Float32)
    HIGH = "high"  # 높은 정밀도 유지 (Float64)
    SCIENTIFIC = "scientific"  # 과학 데이터용 (Float64 + 특수 컬럼 감지)


class DataEngine:
    """
    빅데이터 처리 엔진

    Features:
    - 청크 기반 로딩
    - 메모리 최적화 (타입 다운캐스팅)
    - 지연 평가 (Lazy evaluation)
    - 인덱싱
    - 캐싱
    - 재시도 메커니즘
    - 멀티 데이터셋 지원 (비교 기능)
    """

    # 기본 청크 크기 (행 수)
    DEFAULT_CHUNK_SIZE = 100_000

    # 대용량 파일 임계값 (bytes)
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100MB

    # LazyFrame 사용 임계값 (1GB)
    LAZY_EVAL_THRESHOLD = 1024 * 1024 * 1024

    # 파일 접근 재시도 설정
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 0.5

    # 과학/금융 컬럼 패턴 (정밀도 유지 필요)
    PRECISION_SENSITIVE_PATTERNS = [
        r'price', r'amount', r'rate', r'ratio', r'percent',
        r'lat', r'lon', r'coord', r'precision', r'accuracy',
        r'scientific', r'decimal'
    ]

    # 멀티 데이터셋 설정
    MAX_DATASETS = 10  # 최대 동시 로드 가능 데이터셋 수
    MAX_TOTAL_MEMORY = 4 * 1024 * 1024 * 1024  # 4GB 메모리 한도

    # 기본 데이터셋 색상 팔레트
    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]

    def __init__(self, precision_mode: PrecisionMode = PrecisionMode.AUTO):
        # 기존 단일 데이터셋 (하위 호환성)
        self._df: Optional[pl.DataFrame] = None
        self._lazy_df: Optional[pl.LazyFrame] = None
        self._source: Optional[DataSource] = None
        self._profile: Optional[DataProfile] = None
        self._progress: LoadingProgress = LoadingProgress()
        self._indexes: Dict[str, Dict] = {}  # column_name -> index (deprecated)
        self._cache: Dict[str, Any] = {}
        self._loading_thread: Optional[threading.Thread] = None
        self._cancel_loading = False
        self._progress_callback: Optional[Callable[[LoadingProgress], None]] = None
        self._precision_mode: PrecisionMode = precision_mode
        self._precision_columns: Set[str] = set()  # 정밀도 유지 필요 컬럼

        # 멀티 데이터셋 지원
        self._datasets: Dict[str, DatasetInfo] = {}  # dataset_id -> DatasetInfo
        self._active_dataset_id: Optional[str] = None
        self._color_index: int = 0  # 다음 데이터셋에 할당할 색상 인덱스
    
    @property
    def df(self) -> Optional[pl.DataFrame]:
        """현재 데이터프레임"""
        return self._df
    
    @property
    def profile(self) -> Optional[DataProfile]:
        """데이터 프로파일"""
        return self._profile
    
    @property
    def progress(self) -> LoadingProgress:
        """로딩 진행 상태"""
        return self._progress
    
    @property
    def is_loaded(self) -> bool:
        """데이터 로드 여부"""
        return self._df is not None
    
    @property
    def row_count(self) -> int:
        """총 행 수"""
        return len(self._df) if self._df is not None else 0
    
    @property
    def column_count(self) -> int:
        """총 컬럼 수"""
        return len(self._df.columns) if self._df is not None else 0
    
    @property
    def columns(self) -> List[str]:
        """컬럼 이름 목록"""
        return self._df.columns if self._df is not None else []
    
    @property
    def dtypes(self) -> Dict[str, str]:
        """컬럼별 데이터 타입"""
        if self._df is None:
            return {}
        return {col: str(dtype) for col, dtype in zip(self._df.columns, self._df.dtypes)}
    
    def set_progress_callback(self, callback: Callable[[LoadingProgress], None]):
        """진행률 콜백 설정"""
        self._progress_callback = callback
    
    def _update_progress(self, **kwargs):
        """진행률 업데이트"""
        for key, value in kwargs.items():
            if hasattr(self._progress, key):
                setattr(self._progress, key, value)
        if self._progress_callback:
            self._progress_callback(self._progress)
    
    def detect_file_type(self, path: str) -> FileType:
        """파일 형식 자동 감지"""
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
        return mapping.get(ext, FileType.TXT)  # 알 수 없으면 텍스트로 시도
    
    def detect_delimiter(self, path: str, encoding: str = "utf-8", sample_lines: int = 10) -> str:
        """구분자 자동 감지"""
        delimiters = [',', '\t', ';', '|', ' ']
        delimiter_counts = {d: 0 for d in delimiters}
        
        try:
            with open(path, 'r', encoding=encoding, errors='ignore') as f:
                for i, line in enumerate(f):
                    if i >= sample_lines:
                        break
                    for d in delimiters:
                        delimiter_counts[d] += line.count(d)
            
            # 가장 많이 나온 구분자 선택 (공백은 마지막 옵션)
            best = ','
            best_count = 0
            for d, count in delimiter_counts.items():
                if d == ' ':
                    # 공백은 다른 구분자가 없을 때만
                    if best_count == 0 and count > 0:
                        best = d
                elif count > best_count:
                    best = d
                    best_count = count
            return best
        except:
            return ','
    
    def set_precision_mode(self, mode: PrecisionMode):
        """정밀도 모드 설정"""
        self._precision_mode = mode

    def add_precision_column(self, column: str):
        """정밀도 유지가 필요한 컬럼 추가"""
        self._precision_columns.add(column)

    def _retry_file_access(self, path: str) -> bool:
        """파일 접근 재시도 (네트워크 드라이브 등을 위한)"""
        for attempt in range(self.MAX_RETRIES):
            try:
                if os.path.exists(path) and os.access(path, os.R_OK):
                    return True
            except OSError as e:
                logger.warning(f"File access attempt {attempt + 1} failed: {e}")

            if attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_DELAY_SECONDS * (attempt + 1))  # 지수 백오프

        return False

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
        process_filter: Optional[List[str]] = None,  # For ETL files - filter by process names
        precision_mode: Optional[PrecisionMode] = None,  # 정밀도 모드 오버라이드
    ) -> bool:
        """
        파일 로드

        Args:
            path: 파일 경로
            file_type: 파일 형식 (자동 감지)
            encoding: 인코딩
            delimiter: 구분자 (직접 지정)
            delimiter_type: 구분자 타입 (COMMA, TAB, SPACE, SEMICOLON, PIPE, REGEX, AUTO)
            regex_pattern: regex 구분자 패턴 (delimiter_type이 REGEX일 때)
            has_header: 헤더 존재 여부
            skip_rows: 상단 스킵할 행 수
            comment_char: 주석 문자 (예: #)
            sheet_name: 시트 이름 (Excel)
            chunk_size: 청크 크기 (행 수)
            optimize_memory: 메모리 최적화 여부
            async_load: 비동기 로드 여부
            precision_mode: 정밀도 모드 (None이면 엔진 기본값 사용)
        """
        # 정밀도 모드 설정
        if precision_mode is not None:
            self._precision_mode = precision_mode

        # 파일 접근 재시도
        if not self._retry_file_access(path):
            self._update_progress(status="error", error_message=f"File not found or not accessible: {path}")
            return False
        
        # 파일 형식 감지
        if file_type is None:
            file_type = self.detect_file_type(path)
        
        # 구분자 결정
        if delimiter_type == DelimiterType.AUTO:
            delimiter = self.detect_delimiter(path, encoding)
        elif delimiter_type == DelimiterType.REGEX:
            delimiter = regex_pattern or delimiter
        elif delimiter_type != DelimiterType.REGEX:
            delimiter = delimiter_type.value
        
        # 소스 정보 저장
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
            sheet_name=sheet_name
        )

        # 파일 크기 확인
        file_size = os.path.getsize(path)
        self._update_progress(
            status="loading",
            total_bytes=file_size,
            loaded_bytes=0
        )

        # 비동기 로드
        if async_load:
            self._cancel_loading = False
            self._loading_thread = threading.Thread(
                target=self._load_file_internal,
                args=(path, file_type, encoding, delimiter, delimiter_type,
                      regex_pattern, has_header, skip_rows, comment_char,
                      sheet_name, chunk_size, optimize_memory, excluded_columns,
                      process_filter)
            )
            self._loading_thread.start()
            return True
        else:
            return self._load_file_internal(
                path, file_type, encoding, delimiter, delimiter_type,
                regex_pattern, has_header, skip_rows, comment_char,
                sheet_name, chunk_size, optimize_memory, excluded_columns,
                process_filter
            )
    
    def _load_file_internal(
        self,
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
        process_filter: Optional[List[str]] = None
    ) -> bool:
        """실제 파일 로드"""
        start_time = time.time()

        try:
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

            # Remove excluded columns
            if excluded_columns and self._df is not None:
                cols_to_drop = [c for c in excluded_columns if c in self._df.columns]
                if cols_to_drop:
                    self._df = self._df.drop(cols_to_drop)

            # Apply process filter (for ETL files converted to CSV)
            if process_filter and self._df is not None:
                self._df = self._apply_process_filter(self._df, process_filter)

            # 메모리 최적화
            if optimize_memory:
                self._update_progress(status="optimizing")
                self._df = self._optimize_memory(self._df)

            # 프로파일 생성
            self._update_progress(status="profiling")
            self._profile = self._create_profile(self._df, time.time() - start_time)

            # 완료
            self._update_progress(
                status="complete",
                loaded_bytes=self._progress.total_bytes,
                loaded_rows=len(self._df),
                total_rows=len(self._df),
                elapsed_seconds=time.time() - start_time
            )

            # 로딩 완료 후 메모리 정리
            gc.collect()
            logger.info(f"File loaded successfully: {len(self._df):,} rows, {len(self._df.columns)} columns")

            return True

        except Exception as e:
            logger.error(f"Failed to load file: {e}", exc_info=True)
            self._update_progress(status="error", error_message=str(e))
            gc.collect()  # 실패 시에도 메모리 정리
            return False
    
    def _load_csv(
        self, 
        path: str, 
        encoding: str, 
        delimiter: str, 
        has_header: bool,
        skip_rows: int = 0,
        comment_char: Optional[str] = None
    ) -> pl.DataFrame:
        """CSV 로드"""
        return pl.read_csv(
            path,
            encoding=encoding,
            separator=delimiter,
            has_header=has_header,
            skip_rows=skip_rows,
            comment_prefix=comment_char,
            infer_schema_length=10000,
            ignore_errors=True
        )
    
    def _load_text(
        self,
        path: str,
        encoding: str,
        delimiter: str,
        delimiter_type: DelimiterType,
        regex_pattern: Optional[str],
        has_header: bool,
        skip_rows: int = 0,
        comment_char: Optional[str] = None
    ) -> pl.DataFrame:
        """
        일반 텍스트 파일 로드 (TXT, LOG, DAT 등)
        다양한 구분자 지원 (쉼표, 탭, 공백, 세미콜론, 파이프, regex)
        """
        rows = []
        with open(path, 'r', encoding=encoding, errors='ignore') as f:
            lines = f.readlines()
        
        # 스킵 및 필터링
        lines = lines[skip_rows:]
        if comment_char:
            lines = [l for l in lines if not l.strip().startswith(comment_char)]
        
        # 빈 줄 제거
        lines = [l.strip() for l in lines if l.strip()]
        
        if not lines:
            return pl.DataFrame()
        
        # 구분자로 파싱
        for line in lines:
            if delimiter_type == DelimiterType.REGEX and regex_pattern:
                # regex 패턴으로 split
                fields = re.split(regex_pattern, line)
            elif delimiter_type == DelimiterType.SPACE or delimiter == ' ':
                # 공백 (연속 공백 포함)
                fields = line.split()
            else:
                # 일반 구분자
                fields = line.split(delimiter)
            
            rows.append([f.strip() for f in fields])
        
        if not rows:
            return pl.DataFrame()
        
        # 헤더 처리
        if has_header:
            headers = rows[0]
            data = rows[1:]
        else:
            max_cols = max(len(r) for r in rows)
            headers = [f"col_{i}" for i in range(max_cols)]
            data = rows
        
        # 컬럼 수 맞추기
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
        
        # DataFrame 생성
        df_dict = {headers[i]: [row[i] for row in normalized_data] for i in range(max_cols)}
        df = pl.DataFrame(df_dict)
        
        # 숫자 타입 자동 변환 시도
        for col in df.columns:
            try:
                # 정수 시도
                df = df.with_columns(pl.col(col).cast(pl.Int64).alias(col))
            except:
                try:
                    # 부동소수점 시도
                    df = df.with_columns(pl.col(col).cast(pl.Float64).alias(col))
                except:
                    pass  # 문자열 유지
        
        return df
    
    def _load_etl(
        self,
        path: str,
        encoding: str,
        delimiter: str,
        delimiter_type: DelimiterType,
        regex_pattern: Optional[str],
        has_header: bool,
        skip_rows: int = 0,
        comment_char: Optional[str] = None
    ) -> pl.DataFrame:
        """
        ETL 파일 로드

        ETL (Event Trace Log)은 Windows 바이너리 형식.
        - 텍스트로 변환된 ETL 파일은 _load_text로 처리
        - 바이너리 ETL은 tracerpt 명령으로 변환 권고
        """
        import platform

        # 바이너리 ETL인지 확인 (더 많은 바이트 검사)
        with open(path, 'rb') as f:
            header = f.read(512)

        # ETL 바이너리 체크 개선:
        # 1. null 바이트(0x00)가 있으면 바이너리 (ETL 바이너리의 특징)
        # 2. 비인쇄 문자가 많으면 바이너리
        null_count = header.count(b'\x00')
        non_printable_count = sum(1 for b in header if b < 32 and b not in (9, 10, 13))

        # null 바이트가 있거나 비인쇄 문자가 5% 이상이면 바이너리
        is_text = (null_count == 0 and
                   (non_printable_count / len(header) < 0.05 if len(header) > 0 else True))

        if not is_text:
            system = platform.system()

            if system == 'Windows':
                # Windows에서 tracerpt로 변환 시도
                try:
                    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
                        tmp_path = tmp.name

                    result = subprocess.run(
                        ['tracerpt', path, '-o', tmp_path, '-of', 'CSV', '-y'],
                        capture_output=True,
                        text=True,
                        timeout=120
                    )

                    if result.returncode == 0 and os.path.exists(tmp_path):
                        if os.path.getsize(tmp_path) > 0:
                            df = self._load_csv(tmp_path, encoding, ',', True, 0, None)
                            os.unlink(tmp_path)
                            return df
                        else:
                            os.unlink(tmp_path)
                            raise ValueError(
                                "ETL 파일 변환 결과가 비어 있습니다.\n"
                                "파일이 손상되었거나 지원되지 않는 형식일 수 있습니다."
                            )
                    else:
                        error_msg = result.stderr if result.stderr else "알 수 없는 오류"
                        raise ValueError(
                            f"ETL 파일 변환 실패: {error_msg}\n\n"
                            "수동 변환 시도:\n"
                            "  1. 관리자 권한으로 명령 프롬프트 실행\n"
                            f"  2. tracerpt \"{path}\" -o output.csv -of CSV\n"
                            "  3. 생성된 output.csv 파일을 열기"
                        )
                except subprocess.TimeoutExpired:
                    raise ValueError(
                        "ETL 변환 시간 초과 (2분).\n"
                        "파일이 너무 크거나 손상되었습니다.\n\n"
                        "대안:\n"
                        "  - Windows Performance Analyzer (WPA) 사용\n"
                        "  - xperf로 변환 후 CSV 내보내기"
                    )
                except FileNotFoundError:
                    raise ValueError(
                        "tracerpt 명령을 찾을 수 없습니다.\n\n"
                        "해결 방법:\n"
                        "  1. 관리자 권한으로 명령 프롬프트 실행\n"
                        f"  2. tracerpt \"{path}\" -o output.csv -of CSV\n"
                        "  3. 생성된 output.csv 파일을 열기"
                    )
            else:
                # Linux/Mac에서는 바이너리 ETL 지원 안 함
                filename = os.path.basename(path)
                raise ValueError(
                    f"ETL (Event Trace Log) 파일은 Windows 전용 바이너리 형식입니다.\n\n"
                    f"현재 시스템: {system}\n\n"
                    "해결 방법:\n"
                    "  1. Windows에서 CSV로 변환:\n"
                    f"     tracerpt \"{filename}\" -o output.csv -of CSV\n\n"
                    "  2. Windows Performance Analyzer (WPA) 사용:\n"
                    "     ETL 파일 열기 → File → Export → CSV\n\n"
                    "  3. 변환된 CSV 파일을 이 프로그램에서 열기\n\n"
                    "참고: 텍스트로 이미 변환된 ETL 파일은 .txt 또는 .csv로\n"
                    "확장자를 변경하면 정상적으로 열 수 있습니다."
                )
        else:
            # 텍스트 ETL (이미 변환됨)
            return self._load_text(path, encoding, delimiter, delimiter_type,
                                   regex_pattern, has_header, skip_rows, comment_char)
    
    def _load_excel(self, path: str, sheet_name: Optional[str]) -> pl.DataFrame:
        """Excel 로드"""
        return pl.read_excel(path, sheet_name=sheet_name or 0)
    
    def _load_parquet(self, path: str) -> pl.DataFrame:
        """Parquet 로드"""
        return pl.read_parquet(path)
    
    def _load_json(self, path: str) -> pl.DataFrame:
        """JSON 로드"""
        return pl.read_json(path)

    def _apply_process_filter(self, df: pl.DataFrame, process_filter: List[str]) -> pl.DataFrame:
        """
        Apply process filter to DataFrame (for ETL files converted to CSV)

        Looks for process-related columns and filters rows to only include
        rows where the process name is in the filter list.
        """
        if not process_filter or df is None:
            return df

        # Common process column names in ETL/CSV exports
        process_col_names = ['Process Name', 'ProcessName', 'Process', 'Image', 'Image Name']

        process_col = None
        for col_name in process_col_names:
            if col_name in df.columns:
                process_col = col_name
                break

        # Also check for columns containing 'process' (case-insensitive)
        if process_col is None:
            for col in df.columns:
                if 'process' in col.lower():
                    process_col = col
                    break

        if process_col is None:
            # No process column found, return original dataframe
            return df

        # Filter to only selected processes
        self._update_progress(status="filtering processes")
        filtered_df = df.filter(pl.col(process_col).is_in(process_filter))

        return filtered_df

    def _is_precision_sensitive_column(self, col_name: str) -> bool:
        """컬럼이 정밀도 유지가 필요한지 확인"""
        # 명시적으로 지정된 컬럼
        if col_name in self._precision_columns:
            return True

        # 패턴 매칭
        col_lower = col_name.lower()
        for pattern in self.PRECISION_SENSITIVE_PATTERNS:
            if re.search(pattern, col_lower):
                return True

        return False

    def _optimize_memory(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        메모리 최적화
        - 정수 다운캐스팅
        - 부동소수점 다운캐스팅 (정밀도 모드에 따라)
        - 문자열 → Categorical 변환
        """
        optimized_cols = []

        for col in df.columns:
            dtype = df[col].dtype
            series = df[col]

            if dtype in [pl.Int64, pl.Int32]:
                # 정수 다운캐스팅
                min_val = series.min()
                max_val = series.max()

                if min_val is not None and max_val is not None:
                    if min_val >= -128 and max_val <= 127:
                        series = series.cast(pl.Int8)
                    elif min_val >= -32768 and max_val <= 32767:
                        series = series.cast(pl.Int16)
                    elif min_val >= -2147483648 and max_val <= 2147483647:
                        series = series.cast(pl.Int32)

            elif dtype == pl.Float64:
                # 정밀도 모드에 따른 Float 다운캐스팅
                should_keep_precision = (
                    self._precision_mode == PrecisionMode.HIGH or
                    self._precision_mode == PrecisionMode.SCIENTIFIC or
                    self._is_precision_sensitive_column(col)
                )

                if not should_keep_precision:
                    # Float64 → Float32 (AUTO 모드이고 민감 컬럼이 아닌 경우)
                    series = series.cast(pl.Float32)
                # else: Float64 유지

            elif dtype == pl.Utf8:
                # 유니크 값이 적으면 Categorical로
                unique_ratio = series.n_unique() / len(series) if len(series) > 0 else 1
                if unique_ratio < 0.5:  # 50% 미만이면 카테고리
                    series = series.cast(pl.Categorical)

            optimized_cols.append(series)

        return pl.DataFrame(optimized_cols)
    
    def _collect_streaming(self, lazy_df: pl.LazyFrame) -> pl.DataFrame:
        """LazyFrame을 streaming 모드로 수집 (메모리 피크 완화)"""
        try:
            return lazy_df.collect(streaming=True)
        except Exception:
            # streaming 미지원 연산은 일반 collect로 폴백
            return lazy_df.collect()

    def _create_profile(self, df: pl.DataFrame, load_time: float) -> DataProfile:
        """데이터 프로파일 생성"""
        columns = []
        
        for col in df.columns:
            series = df[col]
            dtype = series.dtype
            
            col_info = ColumnInfo(
                name=col,
                dtype=str(dtype),
                null_count=series.null_count(),
                unique_count=series.n_unique(),
                is_numeric=dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, 
                                     pl.Float32, pl.Float64],
                is_temporal=dtype in [pl.Date, pl.Datetime, pl.Time],
                is_categorical=dtype == pl.Categorical or 
                              (dtype == pl.Utf8 and series.n_unique() < 100)
            )
            
            # 숫자형이면 min/max 계산
            if col_info.is_numeric:
                col_info.min_value = series.min()
                col_info.max_value = series.max()
            
            # 샘플 값
            non_null = series.drop_nulls()
            if len(non_null) > 0:
                col_info.sample_values = non_null.head(5).to_list()
            
            # 메모리 사용량 추정
            col_info.memory_bytes = series.estimated_size()
            
            columns.append(col_info)
        
        return DataProfile(
            total_rows=len(df),
            total_columns=len(df.columns),
            memory_bytes=df.estimated_size(),
            columns=columns,
            load_time_seconds=load_time
        )
    
    def cancel_loading(self):
        """로딩 취소"""
        self._cancel_loading = True
    
    def filter(
        self,
        column: str,
        operator: str,
        value: Any
    ) -> pl.DataFrame:
        """
        필터링
        
        Operators: eq, ne, gt, lt, ge, le, contains, startswith, endswith, isnull, notnull
        """
        if self._df is None:
            return None
        
        col = pl.col(column)
        
        ops = {
            'eq': col == value,
            'ne': col != value,
            'gt': col > value,
            'lt': col < value,
            'ge': col >= value,
            'le': col <= value,
            'contains': col.str.contains(str(value)),
            'startswith': col.str.starts_with(str(value)),
            'endswith': col.str.ends_with(str(value)),
            'isnull': col.is_null(),
            'notnull': col.is_not_null(),
        }
        
        if operator not in ops:
            raise ValueError(f"Unknown operator: {operator}")
        
        try:
            return self._collect_streaming(self._df.lazy().filter(ops[operator]))
        except Exception:
            return self._df.filter(ops[operator])
    
    def sort(self, columns: List[str], descending: Union[bool, List[bool]] = False) -> pl.DataFrame:
        """정렬"""
        if self._df is None:
            return None
        try:
            return self._collect_streaming(self._df.lazy().sort(columns, descending=descending))
        except Exception:
            return self._df.sort(columns, descending=descending)
    
    def group_aggregate(
        self,
        group_columns: List[str],
        value_columns: List[str],
        agg_funcs: List[str]
    ) -> pl.DataFrame:
        """
        그룹별 집계
        
        agg_funcs: sum, mean, median, min, max, count, std, var, first, last
        """
        if self._df is None:
            return None
        
        agg_map = {
            'sum': lambda c: pl.col(c).sum(),
            'mean': lambda c: pl.col(c).mean(),
            'median': lambda c: pl.col(c).median(),
            'min': lambda c: pl.col(c).min(),
            'max': lambda c: pl.col(c).max(),
            'count': lambda c: pl.col(c).count(),
            'std': lambda c: pl.col(c).std(),
            'var': lambda c: pl.col(c).var(),
            'first': lambda c: pl.col(c).first(),
            'last': lambda c: pl.col(c).last(),
        }
        
        agg_exprs = []
        for val_col, agg_func in zip(value_columns, agg_funcs):
            if agg_func in agg_map:
                expr = agg_map[agg_func](val_col).alias(f"{val_col}_{agg_func}")
                agg_exprs.append(expr)
        
        try:
            return self._collect_streaming(
                self._df.lazy().group_by(group_columns).agg(agg_exprs)
            )
        except Exception:
            return self._df.group_by(group_columns).agg(agg_exprs)
    
    def get_statistics(self, column: str) -> Dict[str, Any]:
        """컬럼 통계"""
        if self._df is None or column not in self._df.columns:
            return {}
        
        series = self._df[column]
        
        stats = {
            'count': len(series),
            'null_count': series.null_count(),
            'unique_count': series.n_unique(),
        }
        
        # 숫자형 통계
        if series.dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64]:
            stats.update({
                'sum': series.sum(),
                'mean': series.mean(),
                'median': series.median(),
                'std': series.std(),
                'min': series.min(),
                'max': series.max(),
                'q1': series.quantile(0.25),
                'q3': series.quantile(0.75),
            })
        
        return stats

    def is_column_categorical(self, column: str, max_unique_ratio: float = 0.05, max_unique_count: int = 100) -> bool:
        """
        컬럼이 categorical인지 판단

        Args:
            column: 컬럼 이름
            max_unique_ratio: 유니크 값 비율 임계값 (기본 5%)
            max_unique_count: 유니크 값 개수 임계값 (기본 100개)

        Returns:
            True if categorical, False otherwise
        """
        if self._df is None or column not in self._df.columns:
            return False

        series = self._df[column]
        dtype = series.dtype

        # 이미 Categorical 타입이면 True
        if dtype == pl.Categorical:
            return True

        # 숫자형, 날짜형은 기본적으로 False (단, 유니크 값이 매우 적으면 True)
        if dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64]:
            unique_count = series.n_unique()
            # 숫자여도 유니크 값이 매우 적으면 categorical로 취급 (예: 1, 2, 3 같은 등급)
            return unique_count <= min(20, max_unique_count) and unique_count / len(series) < max_unique_ratio

        if dtype in [pl.Date, pl.Datetime, pl.Time]:
            return False

        # 문자열 타입 (Utf8)
        if dtype == pl.Utf8:
            row_count = len(series)
            unique_count = series.n_unique()

            # 유니크 값 개수가 임계값 이하이거나, 비율이 낮으면 categorical
            return unique_count <= max_unique_count or (row_count > 0 and unique_count / row_count < max_unique_ratio)

        # Boolean은 categorical
        if dtype == pl.Boolean:
            return True

        return False

    def get_unique_values(self, column: str, limit: int = 1000) -> List[Any]:
        """
        컬럼의 유니크 값 목록 반환

        Args:
            column: 컬럼 이름
            limit: 최대 반환 개수

        Returns:
            유니크 값 리스트
        """
        if self._df is None or column not in self._df.columns:
            return []

        series = self._df[column]
        unique_values = series.unique().sort().head(limit).to_list()
        return unique_values

    def get_all_statistics(self, value_columns: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """모든 (또는 지정된) 컬럼의 통계"""
        if self._df is None:
            return {}
        
        if value_columns is None:
            # 숫자형 컬럼만
            value_columns = [
                col for col in self._df.columns
                if self._df[col].dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, 
                                           pl.Float32, pl.Float64]
            ]
        
        return {col: self.get_statistics(col) for col in value_columns}
    
    def sample(self, n: int = 10000, seed: int = 42) -> pl.DataFrame:
        """샘플링"""
        if self._df is None:
            return None
        if len(self._df) <= n:
            return self._df
        return self._df.sample(n=n, seed=seed)
    
    def get_slice(self, start: int, end: int) -> pl.DataFrame:
        """슬라이스 (가상 스크롤용)"""
        if self._df is None:
            return None
        return self._df.slice(start, end - start)
    
    def search(
        self,
        query: str,
        columns: Optional[List[str]] = None,
        case_sensitive: bool = False,
        max_columns: int = 20
    ) -> pl.DataFrame:
        """
        텍스트 검색 (최적화된 버전)

        Args:
            query: 검색어
            columns: 검색할 컬럼 목록 (None이면 문자열 컬럼만)
            case_sensitive: 대소문자 구분 여부
            max_columns: 검색할 최대 컬럼 수 (성능 보장)
        """
        if self._df is None:
            return None

        if columns is None:
            # 문자열 컬럼만 (최대 max_columns개)
            columns = [
                col for col in self._df.columns
                if self._df[col].dtype in [pl.Utf8, pl.Categorical]
            ][:max_columns]

        if not columns:
            return self._df.head(0)  # 빈 결과

        # 대소문자 구분 없이 검색 (기본)
        if not case_sensitive:
            query = f"(?i){re.escape(query)}"
            literal = False
        else:
            literal = True

        # OR 조건으로 검색 (병렬 처리 활용)
        conditions = []
        for col in columns:
            try:
                if literal:
                    cond = pl.col(col).cast(pl.Utf8).str.contains(query, literal=True)
                else:
                    cond = pl.col(col).cast(pl.Utf8).str.contains(query, literal=False)
                conditions.append(cond)
            except Exception:
                continue

        if not conditions:
            return self._df.head(0)

        # 조건 합치기
        combined = conditions[0]
        for cond in conditions[1:]:
            combined = combined | cond

        return self._df.filter(combined)
    
    def create_index(self, column: str):
        """
        인덱스 생성 (빠른 필터링용)

        [DEPRECATED] 이 메서드는 메모리 효율성 문제로 권장되지 않습니다.
        Polars의 내장 필터링을 사용하세요.
        """
        warnings.warn(
            "create_index is deprecated and will be removed in a future version. "
            "Use Polars native filtering instead.",
            DeprecationWarning,
            stacklevel=2
        )
        if self._df is None or column not in self._df.columns:
            return

        # 값 → 행 인덱스 매핑 (비효율적 - deprecated)
        logger.warning(f"Creating index for column '{column}' - this is memory intensive")
        self._indexes[column] = {}
        # 메모리 효율적인 방식으로 변경
        unique_vals = self._df[column].unique().to_list()
        for val in unique_vals:
            mask = self._df[column] == val
            indices = self._df.with_row_index().filter(mask)["index"].to_list()
            self._indexes[column][val] = indices
    
    def clear(self):
        """데이터 클리어"""
        self._df = None
        self._lazy_df = None
        self._source = None
        self._profile = None
        self._indexes.clear()
        self._cache.clear()
        self._precision_columns.clear()
        self._progress = LoadingProgress()
        # 메모리 정리
        gc.collect()
        logger.debug("Data engine cleared and memory collected")
    
    def export_csv(self, path: str, selected_rows: Optional[List[int]] = None):
        """CSV 내보내기"""
        if self._df is None:
            return
        
        df = self._df
        if selected_rows is not None:
            df = self._df[selected_rows]
        
        df.write_csv(path)
    
    def export_excel(self, path: str, selected_rows: Optional[List[int]] = None):
        """Excel 내보내기"""
        if self._df is None:
            return
        
        df = self._df
        if selected_rows is not None:
            df = self._df[selected_rows]
        
        df.write_excel(path)
    
    def export_parquet(self, path: str, selected_rows: Optional[List[int]] = None):
        """Parquet 내보내기"""
        if self._df is None:
            return

        df = self._df
        if selected_rows is not None:
            df = self._df[selected_rows]

        df.write_parquet(path)

    # ==================== LazyFrame 지원 ====================

    def load_lazy(self, path: str, **kwargs) -> bool:
        """
        LazyFrame으로 파일 로드 (대용량 파일용)

        LazyFrame은 실제 연산을 수행하기 전까지 데이터를 메모리에 로드하지 않습니다.
        대용량 파일의 필터링, 집계 등에 효율적입니다.

        Args:
            path: 파일 경로
            **kwargs: scan 함수에 전달할 추가 인자

        Returns:
            성공 여부
        """
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
                # JSON은 scan 지원 안함 - 일반 로드 후 lazy로 변환
                self._df = pl.read_json(path)
                self._lazy_df = self._df.lazy()
            else:
                # 다른 형식은 일반 로드 후 lazy로 변환
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

    def collect_lazy(
        self,
        limit: Optional[int] = None,
        optimize_memory: bool = True
    ) -> bool:
        """
        LazyFrame을 DataFrame으로 수집

        Args:
            limit: 수집할 최대 행 수 (None이면 전체)
            optimize_memory: 메모리 최적화 적용 여부

        Returns:
            성공 여부
        """
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

            # 프로파일 생성
            self._update_progress(status="profiling")
            self._profile = self._create_profile(self._df, 0)

            gc.collect()
            logger.info(f"LazyFrame collected: {len(self._df):,} rows")
            return True

        except Exception as e:
            logger.error(f"Failed to collect LazyFrame: {e}")
            return False

    def query_lazy(self, expr: pl.Expr) -> Optional[pl.LazyFrame]:
        """
        LazyFrame에 표현식 적용

        Args:
            expr: Polars 표현식

        Returns:
            필터링된 LazyFrame
        """
        if self._lazy_df is None:
            return None

        return self._lazy_df.filter(expr)

    @property
    def has_lazy(self) -> bool:
        """LazyFrame 존재 여부"""
        return self._lazy_df is not None

    # ==================== Multi-Dataset Support ====================

    @property
    def datasets(self) -> Dict[str, DatasetInfo]:
        """모든 데이터셋"""
        return self._datasets

    @property
    def dataset_count(self) -> int:
        """로드된 데이터셋 수"""
        return len(self._datasets)

    @property
    def active_dataset_id(self) -> Optional[str]:
        """현재 활성 데이터셋 ID"""
        return self._active_dataset_id

    @property
    def active_dataset(self) -> Optional[DatasetInfo]:
        """현재 활성 데이터셋"""
        if self._active_dataset_id:
            return self._datasets.get(self._active_dataset_id)
        return None

    def get_dataset(self, dataset_id: str) -> Optional[DatasetInfo]:
        """특정 데이터셋 조회"""
        return self._datasets.get(dataset_id)

    def get_dataset_df(self, dataset_id: str) -> Optional[pl.DataFrame]:
        """특정 데이터셋의 DataFrame 조회"""
        dataset = self._datasets.get(dataset_id)
        return dataset.df if dataset else None

    def list_datasets(self) -> List[DatasetInfo]:
        """
        데이터셋 목록 반환

        Returns:
            [DatasetInfo, ...]
        """
        return list(self._datasets.values())

    def get_total_memory_usage(self) -> int:
        """전체 데이터셋 메모리 사용량"""
        return sum(ds.memory_bytes for ds in self._datasets.values())

    def can_load_dataset(self, estimated_size: int) -> Tuple[bool, str]:
        """
        데이터셋 로드 가능 여부 확인

        Args:
            estimated_size: 예상 메모리 크기 (bytes)

        Returns:
            (can_load, message)
        """
        if len(self._datasets) >= self.MAX_DATASETS:
            return False, f"최대 데이터셋 수({self.MAX_DATASETS})에 도달했습니다."

        current = self.get_total_memory_usage()
        projected = current + estimated_size

        if projected > self.MAX_TOTAL_MEMORY:
            return False, (
                f"메모리 한도 초과. 현재: {current / 1e9:.1f}GB, "
                f"필요: {estimated_size / 1e9:.1f}GB, "
                f"한도: {self.MAX_TOTAL_MEMORY / 1e9:.1f}GB"
            )

        if projected > self.MAX_TOTAL_MEMORY * 0.9:
            return True, "⚠️ 메모리 사용량이 높습니다. 일부 데이터셋 제거를 권장합니다."

        return True, ""

    def load_dataset(
        self,
        path: str,
        name: str = None,
        dataset_id: str = None,
        **load_kwargs
    ) -> Optional[str]:
        """
        새 데이터셋 로드

        Args:
            path: 파일 경로
            name: 데이터셋 표시 이름 (None이면 파일명 사용)
            dataset_id: 데이터셋 ID (None이면 자동 생성)
            **load_kwargs: load_file에 전달할 추가 인자

        Returns:
            생성된 dataset_id (실패 시 None)
        """
        # ID 생성
        if dataset_id is None:
            dataset_id = str(uuid.uuid4())[:8]

        # 이름 결정
        if name is None:
            name = Path(path).name

        # 색상 할당
        color = self.DEFAULT_COLORS[self._color_index % len(self.DEFAULT_COLORS)]
        self._color_index += 1

        # DatasetInfo 생성
        dataset = DatasetInfo(
            id=dataset_id,
            name=name,
            color=color
        )

        # 파일 로드 (기존 메서드 활용)
        success = self.load_file(path, **load_kwargs)

        if not success:
            return None

        # 로드된 데이터를 DatasetInfo에 복사
        dataset.df = self._df
        dataset.lazy_df = self._lazy_df
        dataset.source = self._source
        dataset.profile = self._profile

        # 데이터셋 저장
        self._datasets[dataset_id] = dataset

        # 첫 번째 데이터셋이면 활성화
        if self._active_dataset_id is None:
            self._active_dataset_id = dataset_id

        logger.info(f"Dataset loaded: {dataset_id} ({name}), {dataset.row_count:,} rows")
        return dataset_id

    def remove_dataset(self, dataset_id: str) -> bool:
        """
        데이터셋 제거

        Args:
            dataset_id: 제거할 데이터셋 ID

        Returns:
            성공 여부
        """
        if dataset_id not in self._datasets:
            return False

        # 메모리 해제
        dataset = self._datasets[dataset_id]
        dataset.df = None
        dataset.lazy_df = None

        del self._datasets[dataset_id]

        # 활성 데이터셋이었으면 다른 것으로 전환
        if self._active_dataset_id == dataset_id:
            if self._datasets:
                self._active_dataset_id = next(iter(self._datasets.keys()))
                self._sync_active_dataset()
            else:
                self._active_dataset_id = None
                self._df = None
                self._lazy_df = None
                self._source = None
                self._profile = None

        gc.collect()
        logger.info(f"Dataset removed: {dataset_id}")
        return True

    def activate_dataset(self, dataset_id: str) -> bool:
        """
        데이터셋 활성화 (기존 단일 데이터셋 API와 동기화)

        Args:
            dataset_id: 활성화할 데이터셋 ID

        Returns:
            성공 여부
        """
        if dataset_id not in self._datasets:
            return False

        self._active_dataset_id = dataset_id
        self._sync_active_dataset()
        return True

    def _sync_active_dataset(self):
        """활성 데이터셋을 기존 단일 데이터셋 속성과 동기화"""
        dataset = self.active_dataset
        if dataset:
            self._df = dataset.df
            self._lazy_df = dataset.lazy_df
            self._source = dataset.source
            self._profile = dataset.profile

    def set_dataset_color(self, dataset_id: str, color: str):
        """데이터셋 색상 설정"""
        if dataset_id in self._datasets:
            self._datasets[dataset_id].color = color

    def rename_dataset(self, dataset_id: str, new_name: str):
        """데이터셋 이름 변경"""
        if dataset_id in self._datasets:
            self._datasets[dataset_id].name = new_name

    def clear_all_datasets(self):
        """모든 데이터셋 제거"""
        for dataset_id in list(self._datasets.keys()):
            self.remove_dataset(dataset_id)
        self._color_index = 0

    # ==================== Comparison Operations ====================

    def get_common_columns(self, dataset_ids: List[str] = None) -> List[str]:
        """
        여러 데이터셋의 공통 컬럼 반환

        Args:
            dataset_ids: 대상 데이터셋 ID 목록 (None이면 전체)

        Returns:
            공통 컬럼 이름 목록
        """
        if dataset_ids is None:
            dataset_ids = list(self._datasets.keys())

        if not dataset_ids:
            return []

        common = set(self._datasets[dataset_ids[0]].columns) if dataset_ids[0] in self._datasets else set()

        for did in dataset_ids[1:]:
            if did in self._datasets:
                common &= set(self._datasets[did].columns)

        return list(common)

    def get_numeric_columns(self, dataset_id: str) -> List[str]:
        """특정 데이터셋의 숫자형 컬럼 목록"""
        dataset = self._datasets.get(dataset_id)
        if dataset is None or dataset.df is None:
            return []

        return [
            col for col in dataset.df.columns
            if dataset.df[col].dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                                          pl.Float32, pl.Float64]
        ]

    def align_datasets(
        self,
        dataset_ids: List[str],
        key_column: str,
        fill_strategy: str = "null"
    ) -> Dict[str, pl.DataFrame]:
        """
        키 컬럼 기준으로 데이터셋 정렬

        Args:
            dataset_ids: 정렬할 데이터셋 ID 목록
            key_column: 정렬 기준 컬럼
            fill_strategy: 누락값 처리 ("null", "forward", "backward", "interpolate")

        Returns:
            {dataset_id: aligned_df} 매핑
        """
        if not dataset_ids:
            return {}

        # 모든 키 값의 합집합
        all_keys = set()
        for did in dataset_ids:
            if did in self._datasets and self._datasets[did].df is not None:
                df = self._datasets[did].df
                if key_column in df.columns:
                    all_keys.update(df[key_column].unique().to_list())

        if not all_keys:
            return {}

        # 각 데이터셋 정렬
        aligned = {}
        key_df = pl.DataFrame({key_column: sorted(list(all_keys))})

        for did in dataset_ids:
            if did not in self._datasets:
                continue

            df = self._datasets[did].df
            if df is None or key_column not in df.columns:
                continue

            # 키 DataFrame과 조인
            aligned_df = key_df.join(df, on=key_column, how="left")

            # 누락값 처리
            if fill_strategy == "forward":
                aligned_df = aligned_df.fill_null(strategy="forward")
            elif fill_strategy == "backward":
                aligned_df = aligned_df.fill_null(strategy="backward")
            elif fill_strategy == "interpolate":
                # 숫자 컬럼만 보간
                for col in aligned_df.columns:
                    if aligned_df[col].dtype in [pl.Float32, pl.Float64]:
                        aligned_df = aligned_df.with_columns(
                            pl.col(col).interpolate()
                        )

            aligned[did] = aligned_df

        return aligned

    def calculate_difference(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        value_column: str,
        key_column: str = None
    ) -> Optional[pl.DataFrame]:
        """
        두 데이터셋 간 차이 계산

        Args:
            dataset_a_id: 첫 번째 데이터셋 ID
            dataset_b_id: 두 번째 데이터셋 ID
            value_column: 비교할 값 컬럼
            key_column: 키 컬럼 (None이면 인덱스 기준)

        Returns:
            차이 데이터프레임 (key, value_a, value_b, diff, diff_pct)
        """
        ds_a = self._datasets.get(dataset_a_id)
        ds_b = self._datasets.get(dataset_b_id)

        if ds_a is None or ds_b is None or ds_a.df is None or ds_b.df is None:
            return None

        df_a = ds_a.df
        df_b = ds_b.df

        if value_column not in df_a.columns or value_column not in df_b.columns:
            return None

        if key_column:
            # 키 컬럼 기준 조인
            if key_column not in df_a.columns or key_column not in df_b.columns:
                return None

            merged = df_a.select([key_column, value_column]).join(
                df_b.select([key_column, value_column]),
                on=key_column,
                how="full",
                suffix="_b"
            )
            value_a_col = value_column
            value_b_col = f"{value_column}_b"
        else:
            # 인덱스 기준 (행 순서)
            min_len = min(len(df_a), len(df_b))
            merged = pl.DataFrame({
                "index": list(range(min_len)),
                value_column: df_a[value_column].head(min_len),
                f"{value_column}_b": df_b[value_column].head(min_len)
            })
            key_column = "index"
            value_a_col = value_column
            value_b_col = f"{value_column}_b"

        # 차이 계산
        result = merged.with_columns([
            (pl.col(value_a_col) - pl.col(value_b_col)).alias("diff"),
            (
                (pl.col(value_a_col) - pl.col(value_b_col)) /
                pl.col(value_b_col).abs() * 100
            ).alias("diff_pct")
        ]).rename({
            value_a_col: "value_a",
            value_b_col: "value_b"
        })

        return result

    def get_comparison_statistics(
        self,
        dataset_ids: List[str],
        value_column: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        여러 데이터셋의 비교 통계

        Args:
            dataset_ids: 비교할 데이터셋 ID 목록
            value_column: 통계 대상 컬럼

        Returns:
            {dataset_id: {stat_name: value, ...}, ...}
        """
        stats = {}

        for did in dataset_ids:
            if did not in self._datasets:
                continue

            ds = self._datasets[did]
            if ds.df is None or value_column not in ds.df.columns:
                continue

            series = ds.df[value_column]
            if series.dtype not in [pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                                    pl.Float32, pl.Float64]:
                continue

            stats[did] = {
                "name": ds.name,
                "color": ds.color,
                "count": len(series),
                "sum": series.sum(),
                "mean": series.mean(),
                "median": series.median(),
                "std": series.std(),
                "min": series.min(),
                "max": series.max(),
                "q1": series.quantile(0.25),
                "q3": series.quantile(0.75)
            }

        return stats

    def merge_datasets(
        self,
        dataset_ids: List[str],
        key_column: str = None,
        how: str = "outer"
    ) -> Optional[pl.DataFrame]:
        """
        여러 데이터셋 병합

        Args:
            dataset_ids: 병합할 데이터셋 ID 목록
            key_column: 조인 키 컬럼 (None이면 수직 결합)
            how: 조인 방식 ("inner", "outer", "left", "right")

        Returns:
            병합된 DataFrame
        """
        dfs = []
        for did in dataset_ids:
            if did in self._datasets and self._datasets[did].df is not None:
                df = self._datasets[did].df.with_columns(
                    pl.lit(did).alias("_dataset_id"),
                    pl.lit(self._datasets[did].name).alias("_dataset_name")
                )
                dfs.append(df)

        if not dfs:
            return None

        if key_column is None:
            # 수직 결합 (concat)
            return pl.concat(dfs, how="diagonal")
        else:
            # 수평 결합 (join)
            result = dfs[0]
            for i, df in enumerate(dfs[1:], 2):
                result = result.join(df, on=key_column, how=how, suffix=f"_{i}")
            return result

    # ==================== Statistical Testing ====================

    def perform_statistical_test(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        value_column: str,
        test_type: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        """
        두 데이터셋 간 통계 검정 수행

        Args:
            dataset_a_id: 첫 번째 데이터셋 ID
            dataset_b_id: 두 번째 데이터셋 ID
            value_column: 검정 대상 컬럼
            test_type: 검정 유형 ("auto", "ttest", "mannwhitney", "ks")
                - auto: 정규성에 따라 자동 선택
                - ttest: Independent t-test (정규분포 가정)
                - mannwhitney: Mann-Whitney U test (비모수)
                - ks: Kolmogorov-Smirnov test (분포 비교)

        Returns:
            {
                "test_name": str,
                "statistic": float,
                "p_value": float,
                "is_significant": bool,  # p < 0.05
                "effect_size": float,  # Cohen's d
                "interpretation": str,
                "error": str (optional)
            }
        """
        if not HAS_SCIPY:
            return {
                "error": "scipy is not installed. Install with: pip install scipy",
                "test_name": "none",
                "statistic": None,
                "p_value": None,
                "is_significant": None,
                "effect_size": None,
                "interpretation": "Statistical testing requires scipy"
            }

        ds_a = self._datasets.get(dataset_a_id)
        ds_b = self._datasets.get(dataset_b_id)

        if ds_a is None or ds_b is None or ds_a.df is None or ds_b.df is None:
            return {"error": "Dataset not found"}

        if value_column not in ds_a.df.columns or value_column not in ds_b.df.columns:
            return {"error": f"Column '{value_column}' not found in both datasets"}

        # 데이터 추출 (null 제거)
        data_a = ds_a.df[value_column].drop_nulls().to_numpy()
        data_b = ds_b.df[value_column].drop_nulls().to_numpy()

        if len(data_a) < 2 or len(data_b) < 2:
            return {"error": "Not enough data points for statistical testing"}

        # 검정 유형 자동 선택
        if test_type == "auto":
            test_type = self._select_test_type(data_a, data_b)

        result = {
            "test_name": test_type,
            "statistic": None,
            "p_value": None,
            "is_significant": None,
            "effect_size": None,
            "interpretation": ""
        }

        try:
            if test_type == "ttest":
                stat, p_val = ttest_ind(data_a, data_b, equal_var=False)  # Welch's t-test
                result["test_name"] = "Welch's t-test"
            elif test_type == "mannwhitney":
                stat, p_val = mannwhitneyu(data_a, data_b, alternative='two-sided')
                result["test_name"] = "Mann-Whitney U test"
            elif test_type == "ks":
                stat, p_val = ks_2samp(data_a, data_b)
                result["test_name"] = "Kolmogorov-Smirnov test"
            else:
                return {"error": f"Unknown test type: {test_type}"}

            # Effect size (Cohen's d)
            pooled_std = np.sqrt((np.var(data_a, ddof=1) + np.var(data_b, ddof=1)) / 2)
            if pooled_std > 0:
                effect_size = (np.mean(data_a) - np.mean(data_b)) / pooled_std
            else:
                effect_size = 0.0

            result["statistic"] = float(stat)
            result["p_value"] = float(p_val)
            result["is_significant"] = p_val < 0.05
            result["effect_size"] = float(effect_size)

            # 해석 생성
            result["interpretation"] = self._interpret_test_result(
                result["test_name"], p_val, effect_size, ds_a.name, ds_b.name
            )

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Statistical test failed: {e}")

        return result

    def _select_test_type(self, data_a: np.ndarray, data_b: np.ndarray) -> str:
        """정규성에 따라 적절한 검정 방법 선택"""
        if not HAS_SCIPY:
            return "ttest"

        # 샘플 크기가 충분히 크면 (중심극한정리) t-test 사용
        if len(data_a) >= 30 and len(data_b) >= 30:
            return "ttest"

        # Shapiro-Wilk 정규성 검정 (작은 샘플)
        try:
            # 최대 5000개만 검정 (계산 효율)
            sample_a = data_a[:5000] if len(data_a) > 5000 else data_a
            sample_b = data_b[:5000] if len(data_b) > 5000 else data_b

            _, p_a = scipy_stats.shapiro(sample_a) if len(sample_a) >= 3 else (0, 1)
            _, p_b = scipy_stats.shapiro(sample_b) if len(sample_b) >= 3 else (0, 1)

            # 둘 다 정규분포이면 t-test
            if p_a >= 0.05 and p_b >= 0.05:
                return "ttest"
            else:
                return "mannwhitney"
        except:
            return "ttest"

    def _interpret_test_result(
        self,
        test_name: str,
        p_value: float,
        effect_size: float,
        name_a: str,
        name_b: str
    ) -> str:
        """검정 결과 해석 생성"""
        # 유의성
        if p_value < 0.001:
            sig_text = "highly significant (p < 0.001)"
        elif p_value < 0.01:
            sig_text = "very significant (p < 0.01)"
        elif p_value < 0.05:
            sig_text = "significant (p < 0.05)"
        else:
            sig_text = "not significant (p ≥ 0.05)"

        # 효과 크기 해석 (Cohen's d)
        abs_effect = abs(effect_size)
        if abs_effect < 0.2:
            effect_text = "negligible"
        elif abs_effect < 0.5:
            effect_text = "small"
        elif abs_effect < 0.8:
            effect_text = "medium"
        else:
            effect_text = "large"

        # 방향
        if effect_size > 0:
            direction = f"{name_a} > {name_b}"
        elif effect_size < 0:
            direction = f"{name_a} < {name_b}"
        else:
            direction = f"{name_a} ≈ {name_b}"

        interpretation = (
            f"The difference between datasets is {sig_text}. "
            f"Effect size is {effect_text} (d={effect_size:.3f}). "
            f"Direction: {direction}"
        )

        return interpretation

    def calculate_correlation(
        self,
        dataset_a_id: str,
        dataset_b_id: str,
        column_a: str,
        column_b: str = None,
        method: str = "pearson"
    ) -> Optional[Dict[str, Any]]:
        """
        두 데이터셋/컬럼 간 상관관계 계산

        Args:
            dataset_a_id: 첫 번째 데이터셋 ID
            dataset_b_id: 두 번째 데이터셋 ID
            column_a: 첫 번째 컬럼
            column_b: 두 번째 컬럼 (None이면 column_a와 동일)
            method: 상관계수 유형 ("pearson", "spearman")

        Returns:
            {
                "method": str,
                "correlation": float,
                "p_value": float,
                "is_significant": bool,
                "strength": str,
                "interpretation": str
            }
        """
        if not HAS_SCIPY:
            return {
                "error": "scipy is not installed",
                "method": method,
                "correlation": None,
                "p_value": None,
                "is_significant": None,
                "strength": None,
                "interpretation": "Correlation calculation requires scipy"
            }

        if column_b is None:
            column_b = column_a

        ds_a = self._datasets.get(dataset_a_id)
        ds_b = self._datasets.get(dataset_b_id)

        if ds_a is None or ds_b is None or ds_a.df is None or ds_b.df is None:
            return {"error": "Dataset not found"}

        if column_a not in ds_a.df.columns:
            return {"error": f"Column '{column_a}' not found in dataset A"}
        if column_b not in ds_b.df.columns:
            return {"error": f"Column '{column_b}' not found in dataset B"}

        # 데이터 추출
        data_a = ds_a.df[column_a].drop_nulls().to_numpy()
        data_b = ds_b.df[column_b].drop_nulls().to_numpy()

        # 길이 맞추기 (최소 길이로)
        min_len = min(len(data_a), len(data_b))
        if min_len < 3:
            return {"error": "Not enough data points for correlation"}

        data_a = data_a[:min_len]
        data_b = data_b[:min_len]

        result = {
            "method": method,
            "correlation": None,
            "p_value": None,
            "is_significant": None,
            "strength": None,
            "interpretation": ""
        }

        try:
            if method == "pearson":
                corr, p_val = pearsonr(data_a, data_b)
                result["method"] = "Pearson"
            elif method == "spearman":
                corr, p_val = spearmanr(data_a, data_b)
                result["method"] = "Spearman"
            else:
                return {"error": f"Unknown method: {method}"}

            result["correlation"] = float(corr)
            result["p_value"] = float(p_val)
            result["is_significant"] = p_val < 0.05

            # 상관 강도
            abs_corr = abs(corr)
            if abs_corr < 0.1:
                result["strength"] = "negligible"
            elif abs_corr < 0.3:
                result["strength"] = "weak"
            elif abs_corr < 0.5:
                result["strength"] = "moderate"
            elif abs_corr < 0.7:
                result["strength"] = "strong"
            else:
                result["strength"] = "very strong"

            # 해석
            direction = "positive" if corr > 0 else "negative"
            sig_text = "significant" if result["is_significant"] else "not significant"

            result["interpretation"] = (
                f"{result['strength'].title()} {direction} correlation (r = {corr:.3f}), "
                f"{sig_text} (p = {p_val:.4f})"
            )

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Correlation calculation failed: {e}")

        return result

    def calculate_descriptive_comparison(
        self,
        dataset_ids: List[str],
        value_column: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        여러 데이터셋의 기술통계 비교 (확장)

        Args:
            dataset_ids: 비교할 데이터셋 ID 목록
            value_column: 통계 대상 컬럼

        Returns:
            {dataset_id: {stat_name: value, ...}, ...}
        """
        result = self.get_comparison_statistics(dataset_ids, value_column)

        # 추가 통계량 계산
        for did in dataset_ids:
            if did not in self._datasets:
                continue

            ds = self._datasets[did]
            if ds.df is None or value_column not in ds.df.columns:
                continue

            series = ds.df[value_column].drop_nulls()
            if len(series) == 0:
                continue

            data = series.to_numpy()

            if did not in result:
                result[did] = {}

            # 추가 통계량
            result[did]["skewness"] = float(scipy_stats.skew(data)) if HAS_SCIPY else None
            result[did]["kurtosis"] = float(scipy_stats.kurtosis(data)) if HAS_SCIPY else None
            result[did]["iqr"] = float(np.percentile(data, 75) - np.percentile(data, 25))
            result[did]["range"] = float(np.max(data) - np.min(data))
            result[did]["cv"] = float(np.std(data, ddof=1) / np.mean(data) * 100) if np.mean(data) != 0 else None  # 변동계수

        return result

    def get_normality_test(self, dataset_id: str, value_column: str) -> Optional[Dict[str, Any]]:
        """
        정규성 검정 수행

        Args:
            dataset_id: 데이터셋 ID
            value_column: 검정 대상 컬럼

        Returns:
            {
                "test_name": str,
                "statistic": float,
                "p_value": float,
                "is_normal": bool,
                "interpretation": str
            }
        """
        if not HAS_SCIPY:
            return {"error": "scipy is not installed"}

        ds = self._datasets.get(dataset_id)
        if ds is None or ds.df is None or value_column not in ds.df.columns:
            return {"error": "Dataset or column not found"}

        data = ds.df[value_column].drop_nulls().to_numpy()

        if len(data) < 3:
            return {"error": "Not enough data points"}

        try:
            # Shapiro-Wilk for small samples, D'Agostino for large
            if len(data) <= 5000:
                stat, p_val = scipy_stats.shapiro(data[:5000])
                test_name = "Shapiro-Wilk"
            else:
                stat, p_val = scipy_stats.normaltest(data)
                test_name = "D'Agostino-Pearson"

            is_normal = p_val >= 0.05

            interpretation = (
                f"Data appears to be normally distributed (p = {p_val:.4f})"
                if is_normal else
                f"Data is not normally distributed (p = {p_val:.4f})"
            )

            return {
                "test_name": test_name,
                "statistic": float(stat),
                "p_value": float(p_val),
                "is_normal": is_normal,
                "interpretation": interpretation
            }
        except Exception as e:
            return {"error": str(e)}
