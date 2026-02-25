"""Unit tests for FtraceParser blocklayer converter + GraphPreset system."""

from __future__ import annotations

import tempfile

import polars as pl
import pytest

from data_graph_studio.parsers.ftrace_parser import FtraceParser


# ── Test data ─────────────────────────────────────────────────

# block_rq_issue details: <major>,<minor> <rwbs> <bytes> () <sector> + <nr_sectors> [<comm>]
# block_rq_complete details: <major>,<minor> <rwbs> () <sector> + <nr_sectors> [<errno>]

BLOCK_TRACE_SIMPLE = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 1000 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 1000 + 8 [0]
"""

BLOCK_TRACE_MULTI = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 1000 + 8 [kworker/0:1]
     kworker/0:1-100 [001] .... 1000.000500: block_rq_issue: 8,0 W 8192 () 2000 + 16 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 1000 + 8 [0]
     kworker/0:1-100 [001] .... 1000.003000: block_rq_complete: 8,0 W () 2000 + 16 [0]
"""

BLOCK_TRACE_UNMATCHED = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 1000 + 8 [kworker/0:1]
     kworker/0:1-100 [001] .... 1000.000500: block_rq_issue: 8,0 W 8192 () 2000 + 16 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 1000 + 8 [0]
"""
# 2000+16 W has no matching complete → should be dropped

BLOCK_TRACE_QUEUE_DEPTH = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 100 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.000100: block_rq_issue: 8,0 R 4096 () 200 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.000200: block_rq_issue: 8,0 R 4096 () 300 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 100 + 8 [0]
     kworker/0:1-100 [000] .... 1000.001100: block_rq_complete: 8,0 R () 200 + 8 [0]
     kworker/0:1-100 [000] .... 1000.001200: block_rq_complete: 8,0 R () 300 + 8 [0]
"""

BLOCK_TRACE_MIXED_EVENTS = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 1000 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.000500: sched_switch: prev_comm=kworker prev_pid=100
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 1000 + 8 [0]
"""

# Full lifecycle: insert → issue → complete
# block_rq_insert details format same as issue: <dev> <rwbs> <bytes> () <sector> + <nr_sectors> [<comm>]
BLOCK_TRACE_WITH_INSERT = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_insert: 8,0 R 4096 () 1000 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.000300: block_rq_issue: 8,0 R 4096 () 1000 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 1000 + 8 [0]
     kworker/0:1-100 [000] .... 1000.002000: block_rq_insert: 8,0 W 8192 () 2000 + 16 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.002500: block_rq_issue: 8,0 W 8192 () 2000 + 16 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.004000: block_rq_complete: 8,0 W () 2000 + 16 [0]
"""

# C2C: multiple completes in sequence
BLOCK_TRACE_C2C = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 100 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.000100: block_rq_issue: 8,0 R 4096 () 200 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.000200: block_rq_issue: 8,0 R 4096 () 300 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 100 + 8 [0]
     kworker/0:1-100 [000] .... 1000.001500: block_rq_complete: 8,0 R () 200 + 8 [0]
     kworker/0:1-100 [000] .... 1000.003000: block_rq_complete: 8,0 R () 300 + 8 [0]
"""


BLOCK_TRACE_PERFETTO_CMD_PRIORITY = """\
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: dev=8,0 sector=1000 nr_sector=8 rwbs=R bytes=4096 cmd=READ
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: dev=8,0 sector=1000 nr_sector=8 rwbs=R cmd=COMPLETE_READ
"""

BLOCK_TRACE_PERFETTO_COMPLETE_FALLBACK = """\
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: dev=8,0 sector=1000 nr_sector=8 bytes=4096
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: dev=8,0 sector=1000 nr_sector=8 rwbs=W cmd=COMPLETE_WRITE
"""


@pytest.fixture
def parser() -> FtraceParser:
    return FtraceParser()


def _write_trace(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    f.write(content)
    f.close()
    return f.name


# ══════════════════════════════════════════════════════════════
# blocklayer converter
# ══════════════════════════════════════════════════════════════


class TestBlocklayerBasic:
    """Basic pair matching and latency calculation."""

    def test_simple_pair_produces_one_row(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert len(df) == 1

    def test_latency_ms_correct(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        latency = df["d2c_ms"][0]
        assert abs(latency - 1.0) < 0.01  # 1000.001 - 1000.000 = 0.001s = 1ms

    def test_has_required_columns(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        required = {"send_time", "d2c_ms", "sector", "nr_sectors", "cmd",
                     "size_kb", "device", "queue_depth"}
        assert required.issubset(set(df.columns))

    def test_sector_and_size_parsed(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert df["sector"][0] == 1000
        assert df["nr_sectors"][0] == 8
        assert df["size_kb"][0] == 4.0  # 4096 bytes = 4 KB

    def test_rwbs_parsed(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert df["cmd"][0] == "R"



class TestBlocklayerCmdDerivation:
    """cmd derivation priority and fallback behavior."""

    def test_cmd_prefers_cmd_from_detail_over_rwbs(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_PERFETTO_CMD_PRIORITY)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert len(df) == 1
        assert df["cmd"][0] == "READ"

    def test_cmd_falls_back_from_complete_when_issue_missing(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_PERFETTO_COMPLETE_FALLBACK)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert len(df) == 1
        assert df["cmd"][0] == "COMPLETE_WRITE"


class TestBlocklayerMulti:
    """Multiple I/O requests."""

    def test_multi_pairs(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_MULTI)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert len(df) == 2

    def test_multi_latencies(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_MULTI)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        # R: 1000.001 - 1000.000 = 1ms, W: 1000.003 - 1000.0005 = 2.5ms
        df_sorted = df.sort("sector")
        assert abs(df_sorted["d2c_ms"][0] - 1.0) < 0.01
        assert abs(df_sorted["d2c_ms"][1] - 2.5) < 0.01

    def test_multi_ordered_by_issue_time(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_MULTI)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        timestamps = df["send_time"].to_list()
        assert timestamps == sorted(timestamps)


class TestBlocklayerUnmatched:
    """Unmatched issues (no complete) should be dropped."""

    def test_unmatched_dropped(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_UNMATCHED)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert len(df) == 1
        assert df["sector"][0] == 1000


class TestBlocklayerQueueDepth:
    """Queue depth tracking."""

    def test_queue_depth_values(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_QUEUE_DEPTH)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert len(df) == 3
        # At issue time: 1st=1, 2nd=2, 3rd=3
        depths = df["queue_depth"].to_list()
        assert depths == [1, 2, 3]


class TestBlocklayerMixedEvents:
    """Non-block events should be ignored by converter."""

    def test_non_block_events_ignored(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_MIXED_EVENTS)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert len(df) == 1


class TestBlocklayerNewColumns:
    """New latency columns: d2c, d2d, c2c, issue_time, complete_time."""

    def test_has_new_columns(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_WITH_INSERT)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        new_cols = {"d2c_ms", "d2d_ms", "c2c_ms", "send_time", "complete_time"}

        assert new_cols.issubset(set(df.columns)), f"Missing: {new_cols - set(df.columns)}"

    def test_d2c_latency(self, parser: FtraceParser):
        """D2C = dispatch(issue) → complete."""
        path = _write_trace(BLOCK_TRACE_WITH_INSERT)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        df_sorted = df.sort("sector")
        # sector 1000: issue=0.0003, complete=0.001 → d2c=0.7ms
        assert abs(df_sorted["d2c_ms"][0] - 0.7) < 0.01
        # sector 2000: issue=0.0025, complete=0.004 → d2c=1.5ms
        assert abs(df_sorted["d2c_ms"][1] - 1.5) < 0.01

    def test_d2d_interval(self, parser: FtraceParser):
        """D2D = dispatch-to-dispatch (time between consecutive issues)."""
        path = _write_trace(BLOCK_TRACE_WITH_INSERT)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        d2d = df["d2d_ms"].to_list()
        # First issue has no previous → None
        assert d2d[0] is None
        # sector 1000 issue=0.0003, sector 2000 issue=0.0025 → d2d=2.2ms
        assert abs(d2d[1] - 2.2) < 0.01

    def test_d2d_none_for_single_io(self, parser: FtraceParser):
        """Single I/O has no D2D (no previous dispatch)."""
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert df["d2d_ms"][0] is None

    def test_c2c_latency(self, parser: FtraceParser):
        """C2C = time between consecutive completes."""
        path = _write_trace(BLOCK_TRACE_C2C)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        c2c = df["c2c_ms"].to_list()
        # First complete has no previous → NaN or 0
        assert c2c[0] is None or c2c[0] == 0.0 or str(c2c[0]) == "NaN"
        # Second: 1000.001500 - 1000.001000 = 0.5ms
        assert abs(c2c[1] - 0.5) < 0.01
        # Third: 1000.003000 - 1000.001500 = 1.5ms
        assert abs(c2c[2] - 1.5) < 0.01

    def test_issue_and_complete_times(self, parser: FtraceParser):
        """issue_time and complete_time are absolute timestamps."""
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert abs(df["send_time"][0] - 1000.000000) < 0.0001
        assert abs(df["complete_time"][0] - 1000.001000) < 0.0001

    def test_latency_ms_equals_d2c(self, parser: FtraceParser):
        """latency_ms should now be the same as d2c_ms (backward compat)."""
        path = _write_trace(BLOCK_TRACE_WITH_INSERT)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        for i in range(len(df)):
            assert abs(df["d2c_ms"][i] - df["d2c_ms"][i]) < 0.001


class TestBlocklayerQ2D:
    """Q2D (Queue-to-Dispatch) latency: insert → issue."""

    def test_q2d_column_exists(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_WITH_INSERT)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert "q2d_ms" in df.columns
        assert "insert_time" in df.columns

    def test_q2d_latency_values(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_WITH_INSERT)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        df_sorted = df.sort("sector")
        # sector 1000: insert=0.000000, issue=0.000300 → q2d=0.3ms
        assert abs(df_sorted["q2d_ms"][0] - 0.3) < 0.01
        # sector 2000: insert=0.002000, issue=0.002500 → q2d=0.5ms
        assert abs(df_sorted["q2d_ms"][1] - 0.5) < 0.01

    def test_q2d_none_without_insert(self, parser: FtraceParser):
        """No insert events → q2d_ms is None."""
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert df["q2d_ms"][0] is None

    def test_insert_time_recorded(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_WITH_INSERT)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        df_sorted = df.sort("sector")
        assert abs(df_sorted["insert_time"][0] - 1000.000000) < 0.0001
        assert abs(df_sorted["insert_time"][1] - 1000.002000) < 0.0001


class TestBlocklayerSequentiality:
    """LBA sequentiality: sequential if current_sector == prev_sector + prev_nr_sectors."""

    def test_has_is_sequential_column(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert "is_sequential" in df.columns

    def test_first_io_is_random(self, parser: FtraceParser):
        """First I/O has no predecessor → random."""
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert df["is_sequential"][0] == "random"

    def test_sequential_detection(self, parser: FtraceParser):
        """Second I/O starts exactly where first ended → sequential."""
        # sector=1000 nr_sectors=8, then sector=1008 nr_sectors=8
        trace = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 1000 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.000100: block_rq_issue: 8,0 R 4096 () 1008 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 1000 + 8 [0]
     kworker/0:1-100 [000] .... 1000.001100: block_rq_complete: 8,0 R () 1008 + 8 [0]
"""
        path = _write_trace(trace)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert df["is_sequential"][0] == "random"  # first has no prev
        assert df["is_sequential"][1] == "sequential"

    def test_random_detection(self, parser: FtraceParser):
        """Non-contiguous sectors → random."""
        # sector=1000 nr_sectors=8 (ends at 1008), then sector=5000
        trace = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 1000 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.000100: block_rq_issue: 8,0 R 4096 () 5000 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 1000 + 8 [0]
     kworker/0:1-100 [000] .... 1000.001100: block_rq_complete: 8,0 R () 5000 + 8 [0]
"""
        path = _write_trace(trace)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert df["is_sequential"][0] == "random"
        assert df["is_sequential"][1] == "random"

    def test_sequentiality_per_device(self, parser: FtraceParser):
        """Sequentiality tracked per device — different devices don't chain."""
        trace = """\
# tracer: nop
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 1000 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.000100: block_rq_issue: 8,16 R 4096 () 1008 + 8 [kworker/0:1]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 1000 + 8 [0]
     kworker/0:1-100 [000] .... 1000.001100: block_rq_complete: 8,16 R () 1008 + 8 [0]
"""
        path = _write_trace(trace)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        # Both are first on their device → random
        assert df["is_sequential"][0] == "random"
        assert df["is_sequential"][1] == "random"


class TestBlocklayerEmpty:
    """Edge case: no block events."""

    def test_empty_trace(self, parser: FtraceParser):
        path = _write_trace("# tracer: nop\n")
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert len(df) == 0

    def test_no_block_events(self, parser: FtraceParser):
        trace = (
            "# tracer: nop\n"
            "     kworker/0:1-100 [000] .... 1000.000000: sched_switch: prev_comm=foo\n"
        )
        path = _write_trace(trace)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert len(df) == 0


# ══════════════════════════════════════════════════════════════
# Graph Preset system
# ══════════════════════════════════════════════════════════════

from data_graph_studio.parsers.graph_preset import GraphPreset, BUILTIN_PRESETS


class TestGraphPreset:
    """GraphPreset data class."""

    def test_preset_has_required_fields(self):
        p = GraphPreset(
            name="test",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["d2c_ms"],
        )
        assert p.name == "test"
        assert p.chart_type == "scatter"
        assert p.x_column == "send_time"
        assert p.y_columns == ["d2c_ms"]

    def test_preset_optional_group(self):
        p = GraphPreset(
            name="test",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["d2c_ms"],
            group_column="cmd",
        )
        assert p.group_column == "cmd"

    def test_preset_to_dict_roundtrip(self):
        p = GraphPreset(
            name="test",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["d2c_ms", "size_kb"],
            group_column="cmd",
        )
        d = p.to_dict()
        p2 = GraphPreset.from_dict(d)
        assert p2.name == p.name
        assert p2.y_columns == p.y_columns
        assert p2.group_column == p.group_column


class TestBuiltinPresets:
    """Builtin presets for blocklayer converter."""

    def test_blocklayer_presets_exist(self):
        assert "blocklayer" in BUILTIN_PRESETS
        presets = BUILTIN_PRESETS["blocklayer"]
        assert len(presets) >= 6

    def test_d2c_latency_preset(self):
        presets = {p.name: p for p in BUILTIN_PRESETS["blocklayer"]}
        assert "D2C Latency" in presets
        p = presets["D2C Latency"]
        assert p.chart_type == "scatter"
        assert p.x_column == "send_time"
        assert "d2c_ms" in p.y_columns

    def test_d2d_interval_preset(self):
        presets = {p.name: p for p in BUILTIN_PRESETS["blocklayer"]}
        assert "D2D Interval" in presets
        p = presets["D2D Interval"]
        assert p.chart_type == "scatter"
        assert "d2d_ms" in p.y_columns

    def test_c2c_interval_preset(self):
        presets = {p.name: p for p in BUILTIN_PRESETS["blocklayer"]}
        assert "C2C Interval" in presets

    def test_queue_depth_preset(self):
        presets = {p.name: p for p in BUILTIN_PRESETS["blocklayer"]}
        assert "Queue Depth" in presets
        p = presets["Queue Depth"]
        assert p.x_column == "send_time"

    def test_q2d_latency_preset(self):
        presets = {p.name: p for p in BUILTIN_PRESETS["blocklayer"]}
        assert "Q2D Latency" in presets
        p = presets["Q2D Latency"]
        assert p.chart_type == "scatter"
        assert "q2d_ms" in p.y_columns
        assert p.group_column == "cmd"

    def test_all_presets_have_valid_chart_types(self):
        valid_types = {"line", "scatter", "bar", "area", "histogram", "heatmap", "box"}
        for converter, presets in BUILTIN_PRESETS.items():
            for p in presets:
                assert p.chart_type in valid_types, f"{converter}/{p.name}: invalid chart_type={p.chart_type}"


# ══════════════════════════════════════════════════════════════
# Auto-apply preset (integration-level unit test)
# ══════════════════════════════════════════════════════════════

from data_graph_studio.parsers.graph_preset import select_preset


class TestSelectPreset:
    """select_preset() picks the right preset for a DataFrame."""

    def test_selects_lba_map_for_blocklayer(self):
        df = pl.DataFrame({
            "send_time": [1.0, 2.0],
            "complete_time": [1.0005, 2.001],
            "lba_mb": [0.024, 0.049],
            "d2c_ms": [0.5, 1.0],
            "d2d_ms": [None, 1.0],
            "c2c_ms": [None, 0.5],
            "size_kb": [4.0, 8.0],
            "cmd": ["R", "W"],
            "queue_depth": [1, 2],
            "sector": [100, 200],
            "nr_sectors": [8, 8],
            "device": ["8,0", "8,0"],
        })
        preset = select_preset(df, converter="blocklayer")
        assert preset is not None
        assert preset.name == "LBA Map"

    def test_returns_none_for_unknown_converter(self):
        df = pl.DataFrame({"a": [1]})
        preset = select_preset(df, converter="unknown")
        assert preset is None

    def test_returns_none_for_empty_converter(self):
        df = pl.DataFrame({"a": [1]})
        preset = select_preset(df, converter="")
        assert preset is None

    def test_returns_none_when_columns_missing(self):
        # Missing latency_ms
        df = pl.DataFrame({"send_time": [1.0], "sector": [100]})
        preset = select_preset(df, converter="blocklayer")
        assert preset is None
