"""
Data Engine - Polars 기반 빅데이터 처리 엔진
"""

import os
import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor
import subprocess
import tempfile

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq


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


class DataEngine:
    """
    빅데이터 처리 엔진
    
    Features:
    - 청크 기반 로딩
    - 메모리 최적화 (타입 다운캐스팅)
    - 지연 평가 (Lazy evaluation)
    - 인덱싱
    - 캐싱
    """
    
    # 기본 청크 크기 (행 수)
    DEFAULT_CHUNK_SIZE = 100_000
    
    # 대용량 파일 임계값 (bytes)
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100MB
    
    def __init__(self):
        self._df: Optional[pl.DataFrame] = None
        self._lazy_df: Optional[pl.LazyFrame] = None
        self._source: Optional[DataSource] = None
        self._profile: Optional[DataProfile] = None
        self._progress: LoadingProgress = LoadingProgress()
        self._indexes: Dict[str, Dict] = {}  # column_name -> index
        self._cache: Dict[str, Any] = {}
        self._loading_thread: Optional[threading.Thread] = None
        self._cancel_loading = False
        self._progress_callback: Optional[Callable[[LoadingProgress], None]] = None
    
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
        """
        if not os.path.exists(path):
            self._update_progress(status="error", error_message=f"File not found: {path}")
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

            return True

        except Exception as e:
            self._update_progress(status="error", error_message=str(e))
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

    def _optimize_memory(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        메모리 최적화
        - 정수 다운캐스팅
        - 부동소수점 다운캐스팅
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
                # Float64 → Float32
                series = series.cast(pl.Float32)
                
            elif dtype == pl.Utf8:
                # 유니크 값이 적으면 Categorical로
                unique_ratio = series.n_unique() / len(series) if len(series) > 0 else 1
                if unique_ratio < 0.5:  # 50% 미만이면 카테고리
                    series = series.cast(pl.Categorical)
            
            optimized_cols.append(series)
        
        return pl.DataFrame(optimized_cols)
    
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
        
        return self._df.filter(ops[operator])
    
    def sort(self, columns: List[str], descending: Union[bool, List[bool]] = False) -> pl.DataFrame:
        """정렬"""
        if self._df is None:
            return None
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
    
    def search(self, query: str, columns: Optional[List[str]] = None) -> pl.DataFrame:
        """텍스트 검색"""
        if self._df is None:
            return None
        
        if columns is None:
            # 문자열 컬럼만
            columns = [
                col for col in self._df.columns
                if self._df[col].dtype in [pl.Utf8, pl.Categorical]
            ]
        
        if not columns:
            return self._df.head(0)  # 빈 결과
        
        # OR 조건으로 검색
        condition = pl.lit(False)
        for col in columns:
            condition = condition | pl.col(col).cast(pl.Utf8).str.contains(query, literal=True)
        
        return self._df.filter(condition)
    
    def create_index(self, column: str):
        """인덱스 생성 (빠른 필터링용)"""
        if self._df is None or column not in self._df.columns:
            return
        
        # 값 → 행 인덱스 매핑
        self._indexes[column] = {}
        for idx, val in enumerate(self._df[column].to_list()):
            if val not in self._indexes[column]:
                self._indexes[column][val] = []
            self._indexes[column][val].append(idx)
    
    def clear(self):
        """데이터 클리어"""
        self._df = None
        self._lazy_df = None
        self._source = None
        self._profile = None
        self._indexes.clear()
        self._cache.clear()
        self._progress = LoadingProgress()
    
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
