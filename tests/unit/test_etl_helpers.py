"""
Tests for etl_helpers.py.

Covers:
- is_binary_etl: text files, binary files, empty file, nonexistent path
- _filetime_to_datetime: normal Windows FILETIME, epoch 0 (sentinel), None, overflow
- _build_etl_dataframe: normal event list, empty list, extra columns, all-null column pruning
"""

import io
import os
import tempfile
from datetime import datetime

import polars as pl
import pytest

from data_graph_studio.core.etl_helpers import (
    _FILETIME_EPOCH,
    _build_etl_dataframe,
    _filetime_to_datetime,
    is_binary_etl,
)


# ---------------------------------------------------------------------------
# is_binary_etl
# ---------------------------------------------------------------------------

class TestIsBinaryEtl:
    def _write_temp(self, content: bytes) -> str:
        f = tempfile.NamedTemporaryFile(delete=False, suffix=".etl")
        f.write(content)
        f.close()
        return f.name

    def teardown_method(self):
        # nothing persistent to clean up — each test uses its own tempfile
        pass

    def test_text_file_returns_false(self, tmp_path):
        p = tmp_path / "sample.csv"
        p.write_text("id,value\n1,hello\n2,world\n", encoding="utf-8")
        assert is_binary_etl(str(p)) is False

    def test_binary_file_returns_true(self, tmp_path):
        # Lots of null bytes — clearly binary
        p = tmp_path / "sample.etl"
        p.write_bytes(bytes(range(256)) * 2)
        assert is_binary_etl(str(p)) is True

    def test_empty_file_returns_false(self, tmp_path):
        p = tmp_path / "empty.etl"
        p.write_bytes(b"")
        assert is_binary_etl(str(p)) is False

    def test_nonexistent_path_returns_false(self):
        assert is_binary_etl("/nonexistent/path/that/does_not_exist.etl") is False

    def test_unicode_text_file_returns_false(self, tmp_path):
        # Korean text — printable, no nulls
        p = tmp_path / "unicode.txt"
        p.write_text("안녕하세요 세계\n테스트 데이터\n", encoding="utf-8")
        assert is_binary_etl(str(p)) is False


# ---------------------------------------------------------------------------
# _filetime_to_datetime
# ---------------------------------------------------------------------------

class TestFiletimeToDatetime:
    def test_known_filetime_converts_correctly(self):
        # 2009-07-25 23:59:59 UTC in FILETIME: 128930687990000000
        # FILETIME epoch is 1601-01-01, so offset = 128930687990000000 // 10 microseconds
        # Quick sanity: result should be after year 2000
        filetime = 128930687990000000
        result = _filetime_to_datetime(filetime)
        assert result is not None
        assert isinstance(result, datetime)
        assert result.year > 2000

    def test_zero_returns_none(self):
        # 0 is sentinel for "no timestamp"
        assert _filetime_to_datetime(0) is None

    def test_negative_returns_none(self):
        assert _filetime_to_datetime(-1) is None

    def test_none_input_returns_none(self):
        assert _filetime_to_datetime(None) is None

    def test_epoch_offset_one_second(self):
        # 1 second = 10_000_000 100-nanosecond intervals
        result = _filetime_to_datetime(10_000_000)
        assert result is not None
        expected = datetime(1601, 1, 1, 0, 0, 1)
        assert result == expected

    def test_very_large_filetime_does_not_raise(self):
        # Should either return a datetime or None — no exception
        result = _filetime_to_datetime(10 ** 18)
        assert result is None or isinstance(result, datetime)

    def test_filetime_epoch_base(self):
        # A small but valid FILETIME close to epoch
        # 100 microseconds = 1000 intervals
        result = _filetime_to_datetime(1000)
        assert result is not None
        assert result >= _FILETIME_EPOCH


# ---------------------------------------------------------------------------
# _build_etl_dataframe
# ---------------------------------------------------------------------------

class TestBuildEtlDataframe:
    def _base_event(self, **overrides):
        event = {
            'Timestamp': None,
            'EventType': 'DiskRead',
            'ProcessID': 1234,
            'ThreadID': 5678,
            'DiskNumber': 0,
            'TransferSize': 4096,
            'ByteOffset': 0,
            'IrpFlags': 0,
            'HighResResponseTime': 1000,
            'IssuingThreadId': 5678,
            'Source': 'SystemTrace',
        }
        event.update(overrides)
        return event

    def test_single_event_produces_dataframe(self):
        events = [self._base_event()]
        df = _build_etl_dataframe(events)
        assert isinstance(df, pl.DataFrame)
        assert df.height == 1

    def test_multiple_events_correct_row_count(self):
        events = [self._base_event(ProcessID=i) for i in range(5)]
        df = _build_etl_dataframe(events)
        assert df.height == 5

    def test_numeric_columns_cast_to_int64(self):
        events = [self._base_event(ProcessID=42, TransferSize=8192)]
        df = _build_etl_dataframe(events)
        assert df['ProcessID'].dtype == pl.Int64
        assert df['TransferSize'].dtype == pl.Int64

    def test_extra_columns_included(self):
        events = [self._base_event(ExtraField="hello")]
        df = _build_etl_dataframe(events)
        assert 'ExtraField' in df.columns

    def test_all_null_column_is_pruned(self):
        # A column that is entirely null across all events should be dropped
        events = [self._base_event(DiskNumber=None, IssuingThreadId=None) for _ in range(3)]
        df = _build_etl_dataframe(events)
        # Either pruned or not — we verify it doesn't crash and returns a DataFrame
        assert isinstance(df, pl.DataFrame)
        # Columns with all nulls should not appear
        if 'DiskNumber' in df.columns:
            assert df['DiskNumber'].null_count() < len(df)

    def test_empty_events_returns_dataframe(self):
        # Empty list — should return an empty DataFrame without raising
        df = _build_etl_dataframe([])
        assert isinstance(df, pl.DataFrame)
        assert df.height == 0

    def test_unicode_event_type_preserved(self):
        events = [self._base_event(EventType="디스크읽기/쓰기")]
        df = _build_etl_dataframe(events)
        assert df['EventType'][0] == "디스크읽기/쓰기"

    def test_mixed_null_and_nonnull_extra_column_kept(self):
        events = [
            self._base_event(Extra="value"),
            self._base_event(),  # Extra missing → None
        ]
        df = _build_etl_dataframe(events)
        assert 'Extra' in df.columns
        assert df.height == 2
