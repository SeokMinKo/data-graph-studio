"""Unit tests for perfetto-style block detail parsing in FtraceParser."""

from __future__ import annotations

import tempfile

import pytest

from data_graph_studio.parsers.ftrace_parser import FtraceParser


@pytest.fixture
def parser() -> FtraceParser:
    return FtraceParser()


def _write_trace(issue_detail: str, complete_detail: str, *, issue_ts: float = 1000.000000, complete_ts: float = 1000.001000) -> str:
    trace = f"""\
     perfetto-100 [000] .... {issue_ts:.6f}: block_rq_issue: {issue_detail}
     perfetto-100 [000] .... {complete_ts:.6f}: block_rq_complete: {complete_detail}
"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    f.write(trace)
    f.close()
    return f.name


def _parse_blocklayer(parser: FtraceParser, path: str):
    settings = parser.default_settings()
    settings["converter"] = "blocklayer"
    return parser.parse(path, settings)


@pytest.mark.parametrize(
    "issue_detail,complete_detail,expected",
    [
        (
            "dev=8,0 rwbs=R bytes=4096 sector=1000 nr_sector=8 comm=io_worker",
            "dev=8,0 rwbs=R sector=1000 nr_sector=8 error=0",
            {"device": "8,0", "sector": 1000, "nr_sectors": 8, "cmd": "R", "size_kb": 4.0},
        ),
        (
            "bytes=8192 comm=kworker/u16:3 dev=8,16 sector=2000 rwbs=W nr_sector=16",
            "error=0 nr_sector=16 dev=8,16 sector=2000 rwbs=W",
            {"device": "8,16", "sector": 2000, "nr_sectors": 16, "cmd": "W", "size_kb": 8.0},
        ),
        (
            "comm=mmcqd/0 nr_sector=4 rwbs=WS bytes=2048 sector=3000 dev=179,0",
            "rwbs=WS sector=3000 dev=179,0 error=0 nr_sector=4",
            {"device": "179,0", "sector": 3000, "nr_sectors": 4, "cmd": "WS", "size_kb": 2.0},
        ),
    ],
)
def test_perfetto_detail_pattern_1_2_3_parse_and_match(parser: FtraceParser, issue_detail: str, complete_detail: str, expected: dict) -> None:
    path = _write_trace(issue_detail, complete_detail)

    df = _parse_blocklayer(parser, path)

    assert len(df) > 0
    assert df["device"][0] == expected["device"]
    assert df["sector"][0] == expected["sector"]
    assert df["nr_sectors"][0] == expected["nr_sectors"]
    assert df["cmd"][0] == expected["cmd"]
    assert df["size_kb"][0] == expected["size_kb"]
    assert df["d2c_ms"][0] is not None
    assert abs(df["d2c_ms"][0] - 1.0) < 0.01


def test_perfetto_detail_parses_with_key_order_shuffled(parser: FtraceParser) -> None:
    issue_detail = "error=0 comm=kjournald2 bytes=16384 nr_sector=32 sector=4096 rwbs=W dev=259,2"
    complete_detail = "nr_sector=32 error=0 dev=259,2 rwbs=W sector=4096"
    path = _write_trace(issue_detail, complete_detail, issue_ts=2000.000000, complete_ts=2000.003000)

    df = _parse_blocklayer(parser, path)

    assert len(df) == 1
    assert df["device"][0] == "259,2"
    assert df["sector"][0] == 4096
    assert df["nr_sectors"][0] == 32
    assert df["cmd"][0] == "W"
    assert df["size_kb"][0] == 16.0
    assert abs(df["d2c_ms"][0] - 3.0) < 0.01


def test_perfetto_detail_missing_bytes_keeps_row_with_null_size(parser: FtraceParser) -> None:
    issue_detail = "dev=8,0 rwbs=R sector=7000 nr_sector=8 comm=kworker/0:1"
    complete_detail = "dev=8,0 rwbs=R sector=7000 nr_sector=8 error=0"
    path = _write_trace(issue_detail, complete_detail)

    df = _parse_blocklayer(parser, path)

    assert len(df) == 1
    assert df["device"][0] == "8,0"
    assert df["size_kb"][0] is None
    assert abs(df["d2c_ms"][0] - 1.0) < 0.01


def test_perfetto_detail_missing_comm_still_parses(parser: FtraceParser) -> None:
    issue_detail = "dev=8,1 rwbs=R bytes=1024 sector=8000 nr_sector=2"
    complete_detail = "dev=8,1 rwbs=R sector=8000 nr_sector=2 error=0"
    path = _write_trace(issue_detail, complete_detail)

    df = _parse_blocklayer(parser, path)

    assert len(df) == 1
    assert df["device"][0] == "8,1"
    assert df["cmd"][0] == "R"
    assert df["size_kb"][0] == 1.0
    assert abs(df["d2c_ms"][0] - 1.0) < 0.01


def test_perfetto_detail_empty_cmd_keeps_row_with_null_cmd(parser: FtraceParser) -> None:
    issue_detail = "dev=8,2 rwbs= bytes=4096 sector=9000 nr_sector=8 comm=worker"
    complete_detail = "dev=8,2 rwbs= sector=9000 nr_sector=8 error=0"
    path = _write_trace(issue_detail, complete_detail)

    df = _parse_blocklayer(parser, path)

    assert len(df) == 1
    assert df["device"][0] == "8,2"
    assert df["cmd"][0] is None
    assert df["size_kb"][0] == 4.0
    assert abs(df["d2c_ms"][0] - 1.0) < 0.01
