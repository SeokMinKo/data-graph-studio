"""Unit tests for Perfetto CSV -> blocklayer converter pipeline in TraceController."""

from __future__ import annotations

import polars as pl

from data_graph_studio.parsers.ftrace_parser import FtraceParser
from data_graph_studio.parsers.graph_preset import select_preset
from data_graph_studio.ui.controllers.trace_controller import TraceController


class TestPerfettoNormalization:
    def test_normalize_perfetto_csv_for_converter_schema_and_details(self) -> None:
        perfetto_df = pl.DataFrame(
            {
                "ts": [1_000_000_000, 1_005_000_000],
                "cpu": [0, 0],
                "name": ["block/block_rq_issue", "block/block_rq_complete"],
                "task": ["kworker", "kworker"],
                "pid": [111, 111],
                "details": [
                    "dev=8,0 rwbs=R bytes=4096 sector=100 nr_sector=8",
                    "dev=8,0 rwbs=R sector=100 nr_sector=8",
                ],
            }
        )

        raw_df = TraceController._normalize_perfetto_csv_for_ftrace_converter(
            perfetto_df
        )

        assert raw_df.columns == [
            "timestamp",
            "cpu",
            "task",
            "pid",
            "flags",
            "event",
            "details",
        ]
        ts = raw_df["timestamp"].to_list()
        assert ts[0] == 1.0
        assert abs(ts[1] - 1.005) < 1e-9
        assert raw_df["event"].to_list() == ["block_rq_issue", "block_rq_complete"]
        assert raw_df["details"].to_list()[0] == "8,0 R 4096 () 100 + 8"
        assert raw_df["details"].to_list()[1] == "8,0 R () 100 + 8"


class TestPerfettoToBlocklayerPipeline:
    def test_normalized_perfetto_data_converts_and_selects_profile(self) -> None:
        perfetto_df = pl.DataFrame(
            {
                "ts": [2_000_000_000, 2_002_000_000],
                "cpu": [1, 1],
                "name": ["block_rq_issue", "block_rq_complete"],
                "task": ["kworker/1:2", "kworker/1:2"],
                "pid": [222, 222],
                "details": [
                    "dev=8,16 rwbs=W bytes=8192 sector=2048 nr_sectors=16",
                    "dev=8,16 rwbs=W sector=2048 nr_sectors=16",
                ],
            }
        )

        raw_df = TraceController._normalize_perfetto_csv_for_ftrace_converter(
            perfetto_df
        )

        parser = FtraceParser()
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"

        converted_df = parser.convert(raw_df, settings)

        assert len(converted_df) == 1
        assert {"send_time", "complete_time", "d2c_ms", "lba_mb", "cmd"}.issubset(
            set(converted_df.columns)
        )
        assert converted_df["cmd"].to_list() == ["W"]

        preset = select_preset(converted_df, converter="blocklayer")
        assert preset is not None
        assert preset.name == "LBA Map"
