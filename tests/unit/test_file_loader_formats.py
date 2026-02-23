"""
Tests for file_loader_formats.py and file_loader_formats_csv.py.

Covers:
- load_eager: unsupported file type raises DataLoadError
- load_etl (via file_loader_formats_csv): non-Windows binary ETL raises DataLoadError
"""

import platform

import pytest


# ---------------------------------------------------------------------------
# load_eager — unsupported file type
# ---------------------------------------------------------------------------

class TestLoadEager:
    def test_unsupported_file_type_raises_data_load_error(self, tmp_path):
        """load_eager raises DataLoadError (not ValueError) for unknown FileType."""
        from unittest.mock import MagicMock
        from data_graph_studio.core.exceptions import DataLoadError
        from data_graph_studio.core.file_loader_formats import load_eager
        from data_graph_studio.core.types import DelimiterType

        # Create a fake file type value not in the FileType enum
        fake_type = MagicMock()
        fake_type.__eq__ = lambda self, other: False
        fake_type.__str__ = lambda self: "FAKE_TYPE"

        loader = MagicMock()
        loader._windowed = False

        with pytest.raises(DataLoadError):
            load_eager(
                loader=loader,
                path=str(tmp_path / "dummy.xyz"),
                file_type=fake_type,
                encoding="utf-8",
                delimiter=",",
                delimiter_type=DelimiterType.COMMA,
                regex_pattern=None,
                has_header=True,
                skip_rows=0,
                comment_char=None,
                sheet_name=None,
            )


# ---------------------------------------------------------------------------
# load_etl — non-Windows binary ETL without etl-parser raises DataLoadError
# ---------------------------------------------------------------------------

class TestLoadEtlNonWindows:
    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Non-Windows path only",
    )
    def test_binary_etl_no_parser_raises_data_load_error(self, tmp_path, monkeypatch):
        """On non-Windows without etl-parser, load_etl raises DataLoadError for binary ETL."""
        from unittest.mock import MagicMock
        from data_graph_studio.core.exceptions import DataLoadError
        import data_graph_studio.core.file_loader_formats_csv as csv_mod

        # Force HAS_ETL_PARSER to False so parse_etl_binary path is skipped
        monkeypatch.setattr(csv_mod, "HAS_ETL_PARSER", False)

        # Create a fake binary file (lots of null bytes → is_binary_etl returns True)
        binary_etl = tmp_path / "test.etl"
        binary_etl.write_bytes(bytes(range(256)) * 4)

        loader = MagicMock()
        loader._warning_message = ""

        from data_graph_studio.core.types import DelimiterType
        from data_graph_studio.core.file_loader_formats_csv import load_etl

        with pytest.raises(DataLoadError):
            load_etl(
                loader=loader,
                path=str(binary_etl),
                encoding="utf-8",
                delimiter=",",
                delimiter_type=DelimiterType.COMMA,
                regex_pattern=None,
                has_header=True,
            )


# ---------------------------------------------------------------------------
# _run_with_timeout — raises DataLoadError on timeout
# ---------------------------------------------------------------------------

class TestRunWithTimeout:
    def test_raises_data_load_error_on_timeout(self):
        """_run_with_timeout raises DataLoadError when operation exceeds timeout."""
        import time
        from data_graph_studio.core.file_loader import _run_with_timeout
        from data_graph_studio.core.exceptions import DataLoadError

        with pytest.raises(DataLoadError, match="시간 초과"):
            _run_with_timeout(lambda: time.sleep(10), timeout_s=0.05, operation="test_op")

    def test_returns_result_on_success(self):
        """_run_with_timeout returns the function's return value when it completes in time."""
        from data_graph_studio.core.file_loader import _run_with_timeout

        result = _run_with_timeout(lambda: 42, timeout_s=5.0, operation="test_return")
        assert result == 42

    def test_propagates_exception_from_fn(self):
        """_run_with_timeout re-raises exceptions from fn (not wrapped in DataLoadError)."""
        from data_graph_studio.core.file_loader import _run_with_timeout

        with pytest.raises(ValueError, match="boom"):
            _run_with_timeout(lambda: (_ for _ in ()).throw(ValueError("boom")), timeout_s=5.0, operation="test_exc")
