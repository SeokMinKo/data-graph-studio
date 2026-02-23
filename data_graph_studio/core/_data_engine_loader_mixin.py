"""DataEngine loader mixin — FileLoader properties and delegation."""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Set

import polars as pl

from .types import DataProfile, DataSource, FileType, LoadingProgress

logger = logging.getLogger(__name__)


class _DataEngineLoaderMixin:
    """FileLoader property proxies and delegation methods for DataEngine.

    Attributes accessed from DataEngine:
        _loader: FileLoader instance.
        _datasets_mgr: DatasetManager instance.
        _transform_chain: TransformChain instance.
        _virtual_columns: Set[str] tracking virtual column names.
        _cache: OrderedDict LRU cache (via _clear_cache from _DataEngineCacheMixin).
        _exporter, _query: other sub-components (not used here directly).
    """

    # -- Properties: FileLoader -----------------------------------------------

    @property
    def df(self) -> Optional[pl.DataFrame]:
        """Active DataFrame: returns the active dataset's DataFrame, or the loader's DataFrame if no dataset is active.

        Output: Optional[pl.DataFrame] — the current working DataFrame, or None if nothing is loaded
        """
        if self._datasets_mgr.active_dataset_id:
            return self._datasets_mgr.get_dataset_df(self._datasets_mgr.active_dataset_id)
        return self._loader._df

    @property
    def _df(self) -> Optional[pl.DataFrame]:
        return self.df

    @_df.setter
    def _df(self, value: Optional[pl.DataFrame]) -> None:
        """Backward-compatible setter. Prefer update_dataframe()."""
        self._loader._df = value

    def update_dataframe(self, df: Optional[pl.DataFrame]) -> None:
        """Update the active DataFrame, sync with the active dataset, and clear the cache.

        Input:
            df: New DataFrame to set, or None to clear the loaded data.

        Output:
            None. Side effects: loader and active dataset df are updated, cache is cleared.

        Raises:
            None

        Invariants:
            - After call, self.df returns the same object passed as df.
            - Cache is always cleared regardless of df value.
        """
        self._loader._df = df
        # active dataset sync
        if self._datasets_mgr and self._datasets_mgr.active_dataset:
            self._datasets_mgr.active_dataset.df = df
        self._clear_cache()

    def drop_column(self, col_name: str) -> None:
        """Remove a column from the active DataFrame and record the step in the transform chain.

        Input:
            col_name: Non-empty string name of the column to remove; must exist in the
                active DataFrame (silently no-ops if DataFrame is None or column absent).

        Output:
            None. Side effects: active DataFrame loses the specified column, transform chain
            is updated, virtual_columns set is updated.

        Raises:
            ValidationError: if col_name is not a non-empty string.

        Invariants:
            - Column count decreases by exactly 1 when column existed.
            - All other columns are unchanged.
        """
        from .exceptions import ValidationError
        if not isinstance(col_name, str) or not col_name.strip():
            raise ValidationError(
                f"column name must be a non-empty string, got {col_name!r}",
                operation="drop_column",
                context={"col_name": col_name},
            )
        if self.df is None or col_name not in self.df.columns:
            return
        new_df = self.df.drop(col_name)
        self.update_dataframe(new_df)
        # transform chain 기록
        from .transform_chain import TransformStep
        self._transform_chain.add(TransformStep(
            name=f"Drop column '{col_name}'",
            operation='drop',
            params={'column': col_name},
            timestamp=time.time(),
        ))
        # virtual columns 추적 제거
        self._virtual_columns.discard(col_name)

    @property
    def _lazy_df(self) -> Optional[pl.LazyFrame]:
        return self._loader._lazy_df

    @_lazy_df.setter
    def _lazy_df(self, value: Optional[pl.LazyFrame]) -> None:
        self._loader._lazy_df = value

    @property
    def _source(self) -> Optional[DataSource]:
        return self._loader._source

    @_source.setter
    def _source(self, value: Optional[DataSource]) -> None:
        self._loader._source = value

    @property
    def _profile(self) -> Optional[DataProfile]:
        return self._loader._profile

    @_profile.setter
    def _profile(self, value: Optional[DataProfile]) -> None:
        self._loader._profile = value

    @property
    def _progress(self) -> LoadingProgress:
        return self._loader._progress

    @property
    def _cancel_loading(self) -> bool:
        return self._loader._cancel_loading

    @_cancel_loading.setter
    def _cancel_loading(self, value: bool) -> None:
        self._loader._cancel_loading = value

    @property
    def _precision_columns(self) -> Set[str]:
        return self._loader._precision_columns

    @property
    def profile(self) -> Optional[DataProfile]:
        """Current DataProfile for the loaded file, or None if no file is loaded.

        Output: Optional[DataProfile] — column-level statistics snapshot, or None
        """
        return self._loader.profile

    @property
    def progress(self) -> LoadingProgress:
        """Current LoadingProgress snapshot for any in-progress file load operation.

        Output: LoadingProgress — live progress state; never None
        """
        return self._loader.progress

    @property
    def is_loaded(self) -> bool:
        """True if a DataFrame is currently loaded and available.

        Output: bool — True when df is not None
        """
        return self.df is not None

    @property
    def row_count(self) -> int:
        """Total number of rows: uses the full file row count when windowed, otherwise the in-memory DataFrame length.

        Output: int — row count, never negative
        """
        if self._loader.is_windowed and self._loader._total_rows > 0:
            return self._loader._total_rows
        return len(self.df) if self.df is not None else 0

    @property
    def column_count(self) -> int:
        """Number of columns in the active DataFrame, or 0 if no data is loaded."""
        df = self.df
        return len(df.columns) if df is not None else 0

    @property
    def columns(self) -> List[str]:
        """Ordered list of column names in the active DataFrame, or an empty list if no data is loaded."""
        df = self.df
        return df.columns if df is not None else []

    @property
    def dtypes(self) -> Dict[str, str]:
        """Mapping of column name to its Polars dtype string for the active DataFrame."""
        df = self.df
        return {c: str(d) for c, d in zip(df.columns, df.dtypes)} if df is not None else {}

    @property
    def is_windowed(self) -> bool:
        """True if the loaded data is a windowed slice of a larger file rather than the full file."""
        return self._loader.is_windowed

    @property
    def total_rows(self) -> int:
        """Total row count of the source file, including rows outside the current window."""
        return self._loader.total_rows

    @property
    def window_start(self) -> int:
        """Zero-based row index of the first row in the current window."""
        return self._loader.window_start

    @property
    def window_size(self) -> int:
        """Maximum number of rows included in the current window."""
        return self._loader.window_size

    @property
    def has_lazy(self) -> bool:
        """True if a Polars LazyFrame is available for the current data source."""
        return self._loader.has_lazy

    # -- FileLoader delegation ------------------------------------------------

    @staticmethod
    def _normalize_encoding(encoding: str) -> str:
        from .file_loader import FileLoader as FL
        return FL._normalize_encoding(encoding)

    def set_progress_callback(self, cb) -> None:
        """Register a callback to receive LoadingProgress updates during file loading.

        Input:
            cb: Callable that accepts a LoadingProgress argument; called periodically
                during load operations.

        Output:
            None.

        Raises:
            None

        Invariants:
            - Only one callback is active at a time; calling again replaces the previous.
        """
        self._loader.set_progress_callback(cb)

    def detect_file_type(self, path: str) -> FileType:
        """Detect and return the FileType for the file at the given path based on its extension and content.

        Input:
            path: Non-empty filesystem path string pointing to an existing file.

        Output:
            FileType enum member representing the detected format (e.g., CSV, PARQUET, EXCEL).

        Raises:
            None

        Invariants:
            - Does not modify engine state.
            - Returns a valid FileType for any path; falls back to a default if format is unknown.
        """
        return self._loader.detect_file_type(path)

    def detect_delimiter(self, path, encoding="utf-8", sample_lines=10):
        """Detect the delimiter used in a delimited text file by sampling the first few lines.

        Input:
            path: Path to the delimited text file.
            encoding: Character encoding to use when reading the sample (default "utf-8").
            sample_lines: Number of lines to inspect for delimiter detection (default 10).

        Output:
            Single-character string representing the detected delimiter (e.g. ",", "\\t", ";").

        Raises:
            None

        Invariants:
            - Does not modify engine state.
            - sample_lines >= 1.
        """
        return self._loader.detect_delimiter(path, encoding, sample_lines)

    def set_precision_mode(self, mode) -> None:
        """Set the precision mode controlling how floating-point columns are handled during loading.

        Input:
            mode: PrecisionMode enum value (AUTO, HIGH, or STANDARD).

        Output:
            None.

        Raises:
            None

        Invariants:
            - Affects only subsequently loaded files, not the current DataFrame.
        """
        self._loader.set_precision_mode(mode)

    def add_precision_column(self, column) -> None:
        """Mark a specific column to be treated with high-precision numeric handling.

        Input:
            column: Non-empty string column name to flag for high-precision loading.

        Output:
            None.

        Raises:
            None

        Invariants:
            - Precision column set is append-only via this method.
            - Affects only subsequently loaded files.
        """
        self._loader.add_precision_column(column)

    def cancel_loading(self) -> None:
        """Signal the file loader to abort any in-progress load operation.

        Input:
            None

        Output:
            None. Side effect: sets the internal cancel flag so the loader exits early.

        Raises:
            None

        Invariants:
            - Safe to call when no load is in progress (no-op).
        """
        self._loader.cancel_loading()

    def set_window(self, start, size):
        """Configure windowed loading to read a row slice from the source file.

        Input:
            start: Zero-based index of the first row to include (>= 0).
            size: Maximum number of rows to include in the window (>= 1).

        Output:
            Return value delegated from FileLoader.set_window().

        Raises:
            None

        Invariants:
            - is_windowed becomes True after this call.
            - window_start == start, window_size == size after the call.
        """
        return self._loader.set_window(start, size)

    def load_lazy(self, path, **kw):
        """Load a file as a Polars LazyFrame without immediately collecting it into memory.

        Input:
            path: Filesystem path to the file to load.
            **kw: Additional keyword arguments forwarded to FileLoader.load_lazy().

        Output:
            True on success, False on failure (delegated from FileLoader).

        Raises:
            DataLoadError: if the file cannot be parsed or is unsupported.

        Invariants:
            - has_lazy becomes True on success.
            - df remains None until collect_lazy() is called.
        """
        return self._loader.load_lazy(path, **kw)

    def collect_lazy(self, limit=None, optimize_memory=True):
        """Collect the current LazyFrame into a DataFrame, optionally limiting rows.

        Input:
            limit: Maximum number of rows to collect, or None to collect all rows.
            optimize_memory: Whether to apply memory-optimisation passes before collecting
                (default True).

        Output:
            True if the LazyFrame was collected successfully, False if no LazyFrame is available.

        Raises:
            None

        Invariants:
            - Row count <= limit when limit is not None.
            - Operation is timed via MetricsCollector.timed_operation("engine.collect_lazy").
        """
        from .metrics import get_metrics
        with get_metrics().timed_operation("engine.collect_lazy"):
            return self._loader.collect_lazy(limit, optimize_memory)

    def query_lazy(self, expr):
        """Apply a Polars expression to the current LazyFrame and return the filtered LazyFrame.

        Input:
            expr: A Polars expression (pl.Expr) to filter or transform the LazyFrame.

        Output:
            Filtered pl.LazyFrame, or None if no LazyFrame is available.

        Raises:
            None

        Invariants:
            - Does not collect data; result is still lazy.
        """
        return self._loader.query_lazy(expr)

    def _update_progress(self, **kw): self._loader._update_progress(**kw)
    def _is_precision_sensitive_column(self, c): return self._loader._is_precision_sensitive_column(c)

    def load_file(self, path: str, **kwargs) -> bool:
        """Load a file into the engine, clearing cache first.

        Input:
            path: Non-empty filesystem path to the file to load.
            **kwargs: Additional options forwarded to FileLoader.load_file()
                (e.g., encoding, delimiter, optimize_memory).

        Output:
            True if the file was loaded successfully, False otherwise.

        Raises:
            DataLoadError: if the file format is unsupported or parsing fails.

        Invariants:
            - Cache is cleared before loading begins.
            - is_loaded becomes True on success.
            - Operation is timed via MetricsCollector.timed_operation("engine.load_file").
        """
        from .metrics import get_metrics
        with get_metrics().timed_operation("engine.load_file"):
            self._clear_cache()
            return self._loader.load_file(path, **kwargs)

    def append_rows(self, file_path: str, new_row_count: int) -> bool:
        """Incrementally append new rows from the end of a file; falls back to full reload on error.

        Input:
            file_path: Path to the CSV file containing the full updated data.
            new_row_count: Number of rows from the tail of file_path to append (>= 1).

        Output:
            True on success (either incremental append or full reload), False if full reload fails.

        Raises:
            None (exceptions trigger fallback full reload).

        Invariants:
            - If current df is None, performs a full load instead of incremental append.
            - Row count after successful append equals original row count + new_row_count.
        """
        current_df = self.df
        if current_df is None:
            return self.load_file(file_path, optimize_memory=True)

        try:
            full_df = pl.read_csv(file_path)
            new_rows = full_df.tail(new_row_count)
            merged = pl.concat([current_df, new_rows], how="vertical_relaxed")
            self.update_dataframe(merged)
            self._clear_cache()
            return True
        except (pl.exceptions.PolarsError, OSError):
            logger.warning("data_engine.append_rows.failed, falling back to full reload", extra={"path": str(file_path)}, exc_info=True)
            return self.load_file(file_path, optimize_memory=True)

    @staticmethod
    def is_binary_etl(path: str) -> bool:
        """Return True if the file is a binary ETL format requiring the ETL parser.

        Input:
            path: Filesystem path string to inspect.

        Output:
            True if the file uses the binary ETL format, False otherwise.

        Raises:
            None

        Invariants:
            - Pure inspection; does not modify any state.
        """
        from .file_loader import FileLoader as FL
        return FL.is_binary_etl(path)

    @staticmethod
    def parse_etl_binary(path: str) -> pl.DataFrame:
        """Parse a binary ETL file and return its contents as a Polars DataFrame.

        Input:
            path: Filesystem path to the binary ETL file; must exist and be a valid ETL file.

        Output:
            pl.DataFrame containing the parsed records.

        Raises:
            DataLoadError: if the file cannot be parsed as a valid ETL binary.

        Invariants:
            - Returned DataFrame schema matches the ETL file's declared schema.
        """
        from .file_loader import FileLoader as FL
        return FL.parse_etl_binary(path)
