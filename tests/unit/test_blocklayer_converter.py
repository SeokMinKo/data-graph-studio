"""Unit tests for FtraceParser blocklayer converter + GraphPreset system."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict

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
        latency = df["latency_ms"][0]
        assert abs(latency - 1.0) < 0.01  # 1000.001 - 1000.000 = 0.001s = 1ms

    def test_has_required_columns(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        required = {"timestamp", "latency_ms", "sector", "nr_sectors", "rwbs",
                     "size_bytes", "device", "queue_depth"}
        assert required.issubset(set(df.columns))

    def test_sector_and_size_parsed(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert df["sector"][0] == 1000
        assert df["nr_sectors"][0] == 8
        assert df["size_bytes"][0] == 4096

    def test_rwbs_parsed(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_SIMPLE)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        assert df["rwbs"][0] == "R"


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
        assert abs(df_sorted["latency_ms"][0] - 1.0) < 0.01
        assert abs(df_sorted["latency_ms"][1] - 2.5) < 0.01

    def test_multi_ordered_by_issue_time(self, parser: FtraceParser):
        path = _write_trace(BLOCK_TRACE_MULTI)
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(path, settings)
        timestamps = df["timestamp"].to_list()
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
            x_column="timestamp",
            y_columns=["latency_ms"],
        )
        assert p.name == "test"
        assert p.chart_type == "scatter"
        assert p.x_column == "timestamp"
        assert p.y_columns == ["latency_ms"]

    def test_preset_optional_group(self):
        p = GraphPreset(
            name="test",
            chart_type="scatter",
            x_column="timestamp",
            y_columns=["latency_ms"],
            group_column="rwbs",
        )
        assert p.group_column == "rwbs"

    def test_preset_to_dict_roundtrip(self):
        p = GraphPreset(
            name="test",
            chart_type="scatter",
            x_column="timestamp",
            y_columns=["latency_ms", "size_bytes"],
            group_column="rwbs",
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
        assert len(presets) >= 2

    def test_latency_scatter_preset(self):
        presets = {p.name: p for p in BUILTIN_PRESETS["blocklayer"]}
        assert "Latency Scatter" in presets
        p = presets["Latency Scatter"]
        assert p.chart_type == "scatter"
        assert p.x_column == "timestamp"
        assert "latency_ms" in p.y_columns

    def test_iops_timeline_preset(self):
        presets = {p.name: p for p in BUILTIN_PRESETS["blocklayer"]}
        assert "IOPS Timeline" in presets
        p = presets["IOPS Timeline"]
        assert p.x_column == "timestamp"

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

    def test_selects_latency_scatter_for_blocklayer(self):
        df = pl.DataFrame({
            "timestamp": [1.0, 2.0],
            "latency_ms": [0.5, 1.0],
            "sector": [100, 200],
            "nr_sectors": [8, 8],
            "rwbs": ["R", "W"],
            "size_bytes": [4096, 4096],
            "device": ["8,0", "8,0"],
            "queue_depth": [1, 2],
        })
        preset = select_preset(df, converter="blocklayer")
        assert preset is not None
        assert preset.name == "Latency Scatter"

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
        df = pl.DataFrame({"timestamp": [1.0], "sector": [100]})
        preset = select_preset(df, converter="blocklayer")
        assert preset is None
