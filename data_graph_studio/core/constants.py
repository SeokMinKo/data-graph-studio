"""
Central constants for Data Graph Studio.
All magic numbers and configurable defaults live here.
Import from this module — do not define constants elsewhere in core/.
"""

# --- File Watcher ---
MIN_POLL_INTERVAL_MS: int = 500       # 0.5 seconds
MAX_POLL_INTERVAL_MS: int = 60_000    # 60 seconds
DEFAULT_POLL_INTERVAL_MS: int = 1_000 # 1 second
DEBOUNCE_MS: int = 300                # 300ms debounce
MAX_WATCHED_FILES: int = 10           # Section 10.2
LARGE_FILE_THRESHOLD: int = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_BACKOFF_MS: int = 30_000          # 30 seconds max backoff

# --- IPC Server ---
IPC_DEFAULT_PORT: int = 52_849
IPC_MAX_PORT_ATTEMPTS: int = 100

# IPC Protocol message keys
IPC_KEY_COMMAND: str = "command"
IPC_KEY_ARGS: str = "args"
IPC_KEY_STATUS: str = "status"
IPC_KEY_MESSAGE: str = "message"
IPC_STATUS_OK: str = "ok"
IPC_STATUS_ERROR: str = "error"

# IPC server config
IPC_PORT_DIR: str = ".dgs"
IPC_PORT_FILE_NAME: str = "ipc_port"
IPC_SERVER_HOST: str = "127.0.0.1"
IPC_THREAD_NAME: str = "ipc-server"

# --- Undo / History ---
UNDO_MAX_DEPTH: int = 50

# --- Annotations ---
MAX_ANNOTATION_TEXT_LENGTH: int = 200

# --- Diff Colors ---
DIFF_POSITIVE_COLOR: str = "#2ca02c"  # green (increase)
DIFF_NEGATIVE_COLOR: str = "#d62728"  # red (decrease)
DIFF_NEUTRAL_COLOR: str = "#7f7f7f"   # grey (no change)

# --- Cache ---
LRU_CACHE_MAXSIZE: int = 128          # LRU cache capacity for DataEngine query results

# --- Dataset IDs ---
DATASET_ID_LENGTH: int = 8            # UUID prefix length used as short dataset ID

# --- Memory ---
MEMORY_WARNING_THRESHOLD: float = 0.9  # Warn when projected usage exceeds this fraction of the limit

# --- File I/O timeouts (seconds) ---
FILE_ENCODING_DETECT_TIMEOUT: int = 10   # encoding/delimiter sniff
FILE_LOAD_TIMEOUT: int = 120             # full file load

# --- Operation timeouts (seconds) ---
COMPARISON_TIMEOUT: int = 60     # comparison_engine heavy operations
STATISTICS_TIMEOUT: int = 30     # statistics calculations

# --- IPC ---
IPC_HANDLER_TIMEOUT: int = 30  # max seconds per IPC command handler call

# --- Filter Schemes ---
DEFAULT_SCHEME_NAME: str = "Page"  # Name of the built-in, protected filtering scheme

# --- File Loading ---
DEFAULT_DELIMITER: str = ','
DEFAULT_ENCODING: str = 'utf-8'
DELIMITER_SAMPLE_LINES: int = 10
ENCODING_SAMPLE_SIZE: int = 65536          # 64 KB sample — enough for encoding detection
PARQUET_CONVERT_THRESHOLD: int = 500 * 1024 * 1024   # 500 MB — convert CSV → Parquet above this
WINDOWED_LOAD_THRESHOLD: int = 300 * 1024 * 1024     # 300 MB — use windowed loading above this
DEFAULT_WINDOW_SIZE: int = 200_000         # rows per window in windowed-load mode
FILE_LOADER_CHUNK_SIZE: int = 100_000      # rows per chunk in streaming/chunked reads
FILE_LOADER_LARGE_FILE_THRESHOLD: int = 100 * 1024 * 1024  # 100 MB — file-loader heuristic
LAZY_EVAL_THRESHOLD: int = 1024 * 1024 * 1024  # 1 GB — use LazyFrame above this
FILE_LOADER_MAX_RETRIES: int = 3           # retries for transient file-access failures
FILE_LOADER_RETRY_DELAY_SECONDS: float = 0.5  # base delay (multiplied by attempt index)

# --- Reports ---
DEFAULT_CHART_DPI: int = 150               # raster DPI for chart exports in reports

# --- DataQuery defaults ---
DEFAULT_UNIQUE_VALUES_LIMIT: int = 1000   # max unique values returned by get_unique_values
DEFAULT_SAMPLE_SIZE: int = 10_000         # max rows returned by sample()
CATEGORICAL_MAX_NUMERIC_UNIQUE: int = 20  # numeric columns with <= this many unique values may be categorical

# --- Statistical Analysis ---
SHAPIRO_WILK_MAX_SAMPLE: int = 5000       # max sample size for Shapiro-Wilk vs D'Agostino
NORMALITY_SIGNIFICANCE_LEVEL: float = 0.05  # p-value threshold for normality tests
STATISTICAL_SAMPLE_THRESHOLD: int = 30    # min sample size for parametric tests

# --- IPC ---
IPC_SOCKET_BUFFER_SIZE: int = 4096        # bytes read per IPC socket chunk
IPC_MAX_MESSAGE_SIZE: int = 65536         # max IPC message size in bytes (64 KB)

# --- Data Processing ---
INFER_SCHEMA_LENGTH: int = 10000          # rows sampled for schema inference
