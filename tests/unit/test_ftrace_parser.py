"""Unit tests for FtraceParser.parse_raw()."""

from __future__ import annotations

import os
import tempfile
from typing import Dict, Any

import polars as pl
import pytest

from data_graph_studio.parsers.ftrace_parser import FtraceParser

SAMPLE_FTRACE = """\
# tracer: nop
#
# entries-in-buffer/entries-written: 1234/1234   #P:8
#
#                                _-----=> irqs-off
#                               / _----=> need-resched
#                              | / _---=> hardirq/softirq
#                              || / _--=> preempt-depth
#                              ||| /     delay
#           TASK-PID     CPU#  ||||   TIMESTAMP  FUNCTION
#              | |         |   ||||      |         |
     kworker/0:1-12345 [000] .... 12345.678901: block_rq_issue: 8,0 R 4096 () 1234 + 8 [kworker/0:1]
          <idle>-0     [001] d..1 12345.679000: block_rq_complete: 8,0 R () 1234 + 8 [0]
    systemd-journald-456   [003] .... 12345.680000: sched_switch: prev_comm=systemd prev_pid=1 prev_prio=120
"""

SAMPLE_TGID = """\
     kworker/0:1-12345 (  123) [000] .... 12345.678901: block_rq_issue: 8,0 R 4096
          <idle>-0     (-----) [001] d..1 12345.679000: block_rq_complete: 8,0 R ()
"""

SCHEMA = {
    "timestamp": pl.Float64,
    "cpu": pl.Int32,
    "task": pl.Utf8,
    "pid": pl.Int32,
    "flags": pl.Utf8,
    "event": pl.Utf8,
    "details": pl.Utf8,
}


@pytest.fixture
def parser() -> FtraceParser:
    return FtraceParser()


@pytest.fixture
def settings(parser: FtraceParser) -> Dict[str, Any]:
    return parser.default_settings()


def _write_tmp(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.write(fd, content.encode())
    os.close(fd)
    return path


class TestParseRawBasic:
    """UT-1: Normal ftrace text → correct DataFrame."""

    def test_columns_and_types(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        path = _write_tmp(SAMPLE_FTRACE)
        try:
            df = parser.parse_raw(path, settings)
            assert set(df.columns) == set(SCHEMA.keys())
            for col, dtype in SCHEMA.items():
                assert df[col].dtype == dtype, f"{col}: {df[col].dtype} != {dtype}"
        finally:
            os.unlink(path)

    def test_values(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        path = _write_tmp(SAMPLE_FTRACE)
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 3
            row0 = df.row(0, named=True)
            assert row0["task"] == "kworker/0:1"
            assert row0["pid"] == 12345
            assert row0["cpu"] == 0
            assert row0["timestamp"] == pytest.approx(12345.678901)
            assert row0["event"] == "block_rq_issue"
            assert row0["flags"] == "...."
        finally:
            os.unlink(path)


class TestCommentSkip:
    """UT-2: Comment lines are skipped."""

    def test_comments_skipped(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        path = _write_tmp(SAMPLE_FTRACE)
        try:
            df = parser.parse_raw(path, settings)
            # No row should have '#' as task or contain comment data
            assert len(df) == 3
        finally:
            os.unlink(path)


class TestEventsFilter:
    """UT-3: Events filter."""

    def test_filter_single_event(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        settings["events"] = ["block_rq_issue"]
        path = _write_tmp(SAMPLE_FTRACE)
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 1
            assert df["event"][0] == "block_rq_issue"
        finally:
            os.unlink(path)


class TestCpusFilter:
    """UT-4: CPUs filter."""

    def test_filter_single_cpu(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        settings["cpus"] = [1]
        path = _write_tmp(SAMPLE_FTRACE)
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 1
            assert df["cpu"][0] == 1
        finally:
            os.unlink(path)


class TestIntegerTimestamp:
    """UT-5+: integer timestamp formats."""

    def test_integer_timestamp(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        text = """     kworker/0:1-12345 [000] .... 12345: block_rq_issue: 8,0 R 4096 () 1234 + 8 [kworker/0:1]\n"""
        path = _write_tmp(text)
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 1
            assert df["timestamp"][0] == pytest.approx(12345.0)
            assert df["event"][0] == "block_rq_issue"
        finally:
            os.unlink(path)


class TestEventFilterCategoryPrefix:
    """UT-5+: event filter category prefix compatibility."""

    def test_filter_with_prefix(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        settings["events"] = ["block/block_rq_issue", "block/block_rq_complete"]
        path = _write_tmp(SAMPLE_FTRACE)
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 2
            assert set(df["event"].to_list()) == {"block_rq_issue", "block_rq_complete"}
        finally:
            os.unlink(path)


class TestCombinedFilter:
    """UT-5: Events + CPUs combined filter."""

    def test_combined(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        settings["events"] = ["block_rq_issue", "block_rq_complete"]
        settings["cpus"] = [0]
        path = _write_tmp(SAMPLE_FTRACE)
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 1
            assert df["event"][0] == "block_rq_issue"
            assert df["cpu"][0] == 0
        finally:
            os.unlink(path)


class TestEmptyFile:
    """UT-6: Empty file → empty DataFrame."""

    def test_empty(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        path = _write_tmp("")
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 0
            assert set(df.columns) == set(SCHEMA.keys())
        finally:
            os.unlink(path)


class TestHeaderOnly:
    """UT-7: Header-only file."""

    def test_header_only(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        header = "# tracer: nop\n# entries-in-buffer: 0\n"
        path = _write_tmp(header)
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 0
        finally:
            os.unlink(path)


class TestNonStandardLines:
    """UT-8: Non-standard lines are skipped."""

    def test_garbage_lines(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        text = "garbage line\nrandom stuff\n" + SAMPLE_FTRACE
        path = _write_tmp(text)
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 3
        finally:
            os.unlink(path)


class TestTgidFormat:
    """UT-9: tgid format support."""

    def test_tgid(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        path = _write_tmp(SAMPLE_TGID)
        try:
            df = parser.parse_raw(path, settings)
            assert len(df) == 2
            assert df["pid"][0] == 12345
            assert df["task"][0] == "kworker/0:1"
        finally:
            os.unlink(path)


class TestFileNotFound:
    """UT-10: FileNotFoundError."""

    def test_missing_file(self, parser: FtraceParser, settings: Dict[str, Any]) -> None:
        with pytest.raises(FileNotFoundError):
            parser.parse_raw("/nonexistent/path/ftrace.txt", settings)
