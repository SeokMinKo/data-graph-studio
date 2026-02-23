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
