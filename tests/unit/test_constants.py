from data_graph_studio.core import constants

def test_file_watcher_constants_exist():
    assert constants.MIN_POLL_INTERVAL_MS == 500
    assert constants.MAX_POLL_INTERVAL_MS == 60000
    assert constants.DEFAULT_POLL_INTERVAL_MS == 1000
    assert constants.DEBOUNCE_MS == 300
    assert constants.MAX_WATCHED_FILES == 10
    assert constants.LARGE_FILE_THRESHOLD == 2 * 1024 * 1024 * 1024  # 2 GB = 2,147,483,648
    assert constants.MAX_BACKOFF_MS == 30000

def test_ipc_constants_exist():
    assert constants.IPC_DEFAULT_PORT == 52849
    assert constants.IPC_MAX_PORT_ATTEMPTS == 100

def test_undo_constants_exist():
    assert constants.UNDO_MAX_DEPTH == 50

def test_annotation_constants_exist():
    assert constants.MAX_ANNOTATION_TEXT_LENGTH == 200

def test_diff_color_constants_exist():
    assert constants.DIFF_POSITIVE_COLOR == "#2ca02c"
    assert constants.DIFF_NEGATIVE_COLOR == "#d62728"
    assert constants.DIFF_NEUTRAL_COLOR == "#7f7f7f"
