"""
DataQuery — 데이터 조회/변환/통계 모듈 (stateless)

모든 메서드는 pl.DataFrame을 첫 번째 인자로 받아 동작한다.
내부 상태를 갖지 않으며, optional cache 파라미터로 결과를 캐싱할 수 있다.
"""

import re
import warnings
import logging
from typing import Optional, List, Dict, Any, Union

import polars as pl

logger = logging.getLogger(__name__)


class DataQuery:
    """Stateless 데이터 조회/변환/통계 클래스.

    모든 메서드는 순수 함수에 가깝게 설계되어 있으며,
    DataFrame을 인자로 받아 결과를 반환한다.
    """

    def filter(
        self,
        df: pl.DataFrame,
        column: str,
        operator: str,
        value: Any,
    ) -> Optional[pl.DataFrame]:
        """조건에 맞는 행을 필터링한다.

        Args:
            df: 대상 DataFrame.
            column: 필터 컬럼 이름.
            operator: 연산자 ('eq', 'ne', 'gt', 'lt', 'ge', 'le',
                      'contains', 'startswith', 'endswith', 'isnull', 'notnull').
            value: 비교 값.

        Returns:
            필터링된 새 DataFrame. df가 None이면 None.

        Raises:
            ValueError: 알 수 없는 연산자.
        """
        if df is None:
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
            return self._collect_streaming(df.lazy().filter(ops[operator]))
        except Exception as e:
            logger.debug("Streaming filter failed, falling back to eager: %s", e)
            return df.filter(ops[operator])

    def sort(
        self,
        df: pl.DataFrame,
        columns: List[str],
        descending: Union[bool, List[bool]] = False,
    ) -> Optional[pl.DataFrame]:
        """DataFrame을 정렬한다.

        Args:
            df: 대상 DataFrame.
            columns: 정렬 컬럼 목록.
            descending: 내림차순 여부 (단일 값 또는 컬럼별 리스트).

        Returns:
            정렬된 새 DataFrame.
        """
        if df is None:
            return None
        try:
            return self._collect_streaming(df.lazy().sort(columns, descending=descending))
        except Exception as e:
            logger.debug("Streaming sort failed, falling back to eager: %s", e)
            return df.sort(columns, descending=descending)

    def group_aggregate(
        self,
        df: pl.DataFrame,
        group_columns: List[str],
        value_columns: List[str],
        agg_funcs: List[str],
    ) -> Optional[pl.DataFrame]:
        """그룹별 집계를 수행한다.

        Args:
            df: 대상 DataFrame.
            group_columns: 그룹 컬럼 목록.
            value_columns: 집계 대상 값 컬럼 목록.
            agg_funcs: 집계 함수 목록
                ('sum', 'mean', 'median', 'min', 'max', 'count', 'std', 'var', 'first', 'last').

        Returns:
            집계 결과 DataFrame.
        """
        if df is None:
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
                agg_exprs.append(agg_map[agg_func](val_col).alias(f"{val_col}_{agg_func}"))

        try:
            return self._collect_streaming(df.lazy().group_by(group_columns).agg(agg_exprs))
        except Exception as e:
            logger.debug("Streaming group_by failed, falling back to eager: %s", e)
            return df.group_by(group_columns).agg(agg_exprs)

    def get_statistics(
        self,
        df: pl.DataFrame,
        column: str,
        lazy_df: Optional[pl.LazyFrame] = None,
        windowed: bool = False,
        cache: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """컬럼 통계를 계산한다.

        Args:
            df: 대상 DataFrame.
            column: 통계 대상 컬럼.
            lazy_df: windowed 모드에서 전체 통계용 LazyFrame.
            windowed: windowed 모드 여부.
            cache: 결과 캐시 딕셔너리 (있으면 캐시에서 조회/저장).

        Returns:
            통계 딕셔너리.
        """
        cache_key = f"stats_{column}"
        if cache is not None and cache_key in cache:
            return cache[cache_key]

        result = self._compute_statistics(df, column, lazy_df, windowed)

        if cache is not None:
            cache[cache_key] = result

        return result

    def get_all_statistics(
        self,
        df: pl.DataFrame,
        value_columns: Optional[List[str]] = None,
        lazy_df: Optional[pl.LazyFrame] = None,
        windowed: bool = False,
        cache: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """모든 (또는 지정된) 컬럼의 통계를 반환한다.

        Args:
            df: 대상 DataFrame.
            value_columns: 대상 컬럼 목록 (None이면 숫자형 컬럼만).
            lazy_df: windowed 모드용 LazyFrame.
            windowed: windowed 모드 여부.
            cache: 결과 캐시 딕셔너리.

        Returns:
            {컬럼명: 통계 딕셔너리} 매핑.
        """
        if df is None:
            return {}

        if value_columns is None:
            value_columns = [
                col for col in df.columns
                if df[col].dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                                     pl.Float32, pl.Float64]
            ]

        return {
            col: self.get_statistics(df, col, lazy_df, windowed, cache)
            for col in value_columns
        }

    def get_full_profile_summary(
        self,
        df: pl.DataFrame,
        profile: Any = None,
        lazy_df: Optional[pl.LazyFrame] = None,
        windowed: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """전체 데이터 기준 요약 통계를 반환한다.

        Args:
            df: 대상 DataFrame.
            profile: DataProfile 인스턴스 (windowed가 아닐 때 사용).
            lazy_df: windowed 모드용 LazyFrame.
            windowed: windowed 모드 여부.

        Returns:
            요약 통계 딕셔너리 또는 None.
        """
        if not windowed or lazy_df is None:
            if profile is None:
                return None
            return {
                'total_rows': profile.total_rows,
                'total_columns': profile.total_columns,
                'columns': profile.columns,
                'memory_bytes': profile.memory_bytes,
                'load_time_seconds': profile.load_time_seconds,
            }

        try:
            schema = lazy_df.schema
            total_columns = len(schema)
            numeric_cols = sum(1 for dtype in schema.values()
                               if dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                                            pl.Float32, pl.Float64])
            temporal_cols = sum(1 for dtype in schema.values()
                                if dtype in [pl.Date, pl.Datetime, pl.Time])

            null_exprs = [pl.col(c).null_count().alias(c) for c in schema.keys()]
            stats_df = self._collect_streaming(
                lazy_df.select([pl.len().alias('total_rows')] + null_exprs)
            )
            if stats_df is None or stats_df.height == 0:
                return None

            total_rows = int(stats_df[0, 'total_rows'])
            total_nulls = sum(
                int(stats_df[0, c]) for c in schema.keys()
                if c in stats_df.columns
            )
            total_cells = total_rows * total_columns if total_rows > 0 else 0
            missing_percent = (total_nulls / total_cells * 100) if total_cells > 0 else 0.0

            return {
                'total_rows': total_rows,
                'total_columns': total_columns,
                'numeric_columns': numeric_cols,
                'text_columns': total_columns - numeric_cols,
                'missing_percent': missing_percent,
                'memory_bytes': 0,
                'load_time_seconds': 0,
            }
        except Exception:
            return None

    def is_column_categorical(
        self,
        df: pl.DataFrame,
        column: str,
        max_unique_ratio: float = 0.05,
        max_unique_count: int = 100,
    ) -> bool:
        """컬럼이 categorical인지 판단한다.

        Args:
            df: 대상 DataFrame.
            column: 컬럼 이름.
            max_unique_ratio: 유니크 값 비율 임계값.
            max_unique_count: 유니크 값 개수 임계값.

        Returns:
            categorical이면 True.
        """
        if df is None or column not in df.columns:
            return False

        series = df[column]
        dtype = series.dtype

        if dtype == pl.Categorical:
            return True

        if dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64]:
            unique_count = series.n_unique()
            return unique_count <= min(20, max_unique_count) and unique_count / len(series) < max_unique_ratio

        if dtype in [pl.Date, pl.Datetime, pl.Time]:
            return False

        if dtype == pl.Utf8:
            row_count = len(series)
            unique_count = series.n_unique()
            return unique_count <= max_unique_count or (row_count > 0 and unique_count / row_count < max_unique_ratio)

        if dtype == pl.Boolean:
            return True

        return False

    def get_unique_values(
        self,
        df: pl.DataFrame,
        column: str,
        limit: int = 1000,
    ) -> List[Any]:
        """컬럼의 유니크 값 목록을 반환한다.

        Args:
            df: 대상 DataFrame.
            column: 컬럼 이름.
            limit: 최대 반환 개수.

        Returns:
            유니크 값 리스트.
        """
        if df is None or column not in df.columns:
            return []
        return df[column].unique().sort().head(limit).to_list()

    def sample(
        self,
        df: pl.DataFrame,
        n: int = 10000,
        seed: int = 42,
    ) -> Optional[pl.DataFrame]:
        """DataFrame에서 샘플링한다.

        Args:
            df: 대상 DataFrame.
            n: 샘플 수.
            seed: 랜덤 시드.

        Returns:
            샘플링된 DataFrame.
        """
        if df is None:
            return None
        if len(df) <= n:
            return df
        return df.sample(n=n, seed=seed)

    def get_slice(
        self,
        df: pl.DataFrame,
        start: int,
        end: int,
    ) -> Optional[pl.DataFrame]:
        """DataFrame 슬라이스를 반환한다.

        Args:
            df: 대상 DataFrame.
            start: 시작 인덱스.
            end: 끝 인덱스 (exclusive).

        Returns:
            슬라이스된 DataFrame.
        """
        if df is None:
            return None
        return df.slice(start, end - start)

    def search(
        self,
        df: pl.DataFrame,
        query: str,
        columns: Optional[List[str]] = None,
        case_sensitive: bool = False,
        max_columns: int = 20,
    ) -> Optional[pl.DataFrame]:
        """텍스트 검색을 수행한다.

        Args:
            df: 대상 DataFrame.
            query: 검색어.
            columns: 검색할 컬럼 목록 (None이면 전체).
            case_sensitive: 대소문자 구분 여부.
            max_columns: 검색할 최대 컬럼 수.

        Returns:
            매칭된 행의 DataFrame.
        """
        if df is None:
            return None

        mask = self.search_mask(df, query, columns, case_sensitive, max_columns)
        if mask is None:
            return df.head(0)

        return df.filter(mask)

    def search_mask(
        self,
        df: pl.DataFrame,
        query: str,
        columns: Optional[List[str]] = None,
        case_sensitive: bool = False,
        max_columns: int = 20,
    ) -> Optional[pl.Series]:
        """텍스트 검색의 boolean mask를 반환한다.

        Args:
            df: 대상 DataFrame.
            query: 검색어.
            columns: 검색할 컬럼 목록 (None이면 전체).
            case_sensitive: 대소문자 구분 여부.
            max_columns: 검색할 최대 컬럼 수.

        Returns:
            boolean mask (pl.Series of bool) 또는 None.
        """
        if df is None:
            return None

        if columns is None:
            columns = df.columns[:max_columns]

        if not columns:
            return None

        if not case_sensitive:
            query_pattern = f"(?i){re.escape(query)}"
            literal = False
        else:
            query_pattern = query
            literal = True

        conditions = []
        for col in columns:
            try:
                cond = pl.col(col).cast(pl.Utf8).str.contains(query_pattern, literal=literal)
                conditions.append(cond)
            except Exception:
                continue

        if not conditions:
            return None

        combined = conditions[0]
        for cond in conditions[1:]:
            combined = combined | cond

        return df.select(combined.alias("__mask__")).to_series()

    def create_index(self, df: pl.DataFrame, column: str) -> Dict[Any, List[int]]:
        """인덱스를 생성한다 (deprecated).

        Args:
            df: 대상 DataFrame.
            column: 인덱스 컬럼.

        Returns:
            값 → 행 인덱스 매핑.
        """
        warnings.warn(
            "create_index is deprecated. Use Polars native filtering instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        if df is None or column not in df.columns:
            return {}

        index: Dict[Any, List[int]] = {}
        unique_vals = df[column].unique().to_list()
        for val in unique_vals:
            mask = df[column] == val
            indices = df.with_row_index().filter(mask)["index"].to_list()
            index[val] = indices
        return index

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_statistics(
        self,
        df: pl.DataFrame,
        column: str,
        lazy_df: Optional[pl.LazyFrame],
        windowed: bool,
    ) -> Dict[str, Any]:
        """통계를 실제로 계산한다."""
        if windowed and lazy_df is not None:
            try:
                if column not in lazy_df.columns:
                    return {}
                dtype = lazy_df.schema.get(column)
                exprs = [
                    pl.len().alias('count'),
                    pl.col(column).null_count().alias('null_count'),
                    pl.col(column).n_unique().alias('unique_count'),
                ]
                if dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64]:
                    exprs.extend([
                        pl.col(column).sum().alias('sum'),
                        pl.col(column).mean().alias('mean'),
                        pl.col(column).median().alias('median'),
                        pl.col(column).std().alias('std'),
                        pl.col(column).min().alias('min'),
                        pl.col(column).max().alias('max'),
                        pl.col(column).quantile(0.25).alias('q1'),
                        pl.col(column).quantile(0.75).alias('q3'),
                    ])
                stats_df = self._collect_streaming(lazy_df.select(exprs))
                if stats_df is not None and stats_df.height > 0:
                    return stats_df.to_dicts()[0]
            except Exception as e:
                logger.debug("Windowed statistics failed for column '%s': %s", column, e)

        if df is None or column not in df.columns:
            return {}

        series = df[column]
        stats: Dict[str, Any] = {
            'count': len(series),
            'null_count': series.null_count(),
            'unique_count': series.n_unique(),
        }

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

    @staticmethod
    def _collect_streaming(lazy_df: pl.LazyFrame) -> pl.DataFrame:
        """LazyFrame을 streaming 모드로 수집한다."""
        try:
            return lazy_df.collect(engine="streaming")
        except Exception as e:
            logger.debug("Streaming collect failed, using default engine: %s", e)
            return lazy_df.collect()
