"""
Data Engine - Polars 기반 빅데이터 처리 엔진
"""

import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor

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
    has_header: bool = True
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
            '.xlsx': FileType.EXCEL,
            '.xls': FileType.EXCEL,
            '.parquet': FileType.PARQUET,
            '.pq': FileType.PARQUET,
            '.json': FileType.JSON,
        }
        return mapping.get(ext, FileType.CSV)
    
    def load_file(
        self,
        path: str,
        file_type: Optional[FileType] = None,
        encoding: str = "utf-8",
        delimiter: str = ",",
        has_header: bool = True,
        sheet_name: Optional[str] = None,
        chunk_size: Optional[int] = None,
        optimize_memory: bool = True,
        async_load: bool = False
    ) -> bool:
        """
        파일 로드
        
        Args:
            path: 파일 경로
            file_type: 파일 형식 (자동 감지)
            encoding: 인코딩
            delimiter: 구분자 (CSV)
            has_header: 헤더 존재 여부
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
        
        # 소스 정보 저장
        self._source = DataSource(
            path=path,
            file_type=file_type,
            encoding=encoding,
            delimiter=delimiter,
            has_header=has_header,
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
                args=(path, file_type, encoding, delimiter, has_header, 
                      sheet_name, chunk_size, optimize_memory)
            )
            self._loading_thread.start()
            return True
        else:
            return self._load_file_internal(
                path, file_type, encoding, delimiter, has_header,
                sheet_name, chunk_size, optimize_memory
            )
    
    def _load_file_internal(
        self,
        path: str,
        file_type: FileType,
        encoding: str,
        delimiter: str,
        has_header: bool,
        sheet_name: Optional[str],
        chunk_size: Optional[int],
        optimize_memory: bool
    ) -> bool:
        """실제 파일 로드"""
        start_time = time.time()
        
        try:
            if file_type == FileType.CSV:
                self._df = self._load_csv(path, encoding, delimiter, has_header)
            elif file_type == FileType.TSV:
                self._df = self._load_csv(path, encoding, "\t", has_header)
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
        has_header: bool
    ) -> pl.DataFrame:
        """CSV 로드"""
        return pl.read_csv(
            path,
            encoding=encoding,
            separator=delimiter,
            has_header=has_header,
            infer_schema_length=10000,
            ignore_errors=True
        )
    
    def _load_excel(self, path: str, sheet_name: Optional[str]) -> pl.DataFrame:
        """Excel 로드"""
        return pl.read_excel(path, sheet_name=sheet_name or 0)
    
    def _load_parquet(self, path: str) -> pl.DataFrame:
        """Parquet 로드"""
        return pl.read_parquet(path)
    
    def _load_json(self, path: str) -> pl.DataFrame:
        """JSON 로드"""
        return pl.read_json(path)
    
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
