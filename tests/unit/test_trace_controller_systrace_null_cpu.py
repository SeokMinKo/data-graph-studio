from __future__ import annotations

from data_graph_studio.ui.controllers.trace_controller import TraceController


def test_trace_controller_systrace_line_handles_null_cpu() -> None:
    line = TraceController._format_systrace_line_from_csv_row(
        {
            "ts": "1000000000",
            "cpu": "NULL",
            "name": "block/block_rq_issue",
            "task": "kworker",
            "pid": "77",
            "details": "dev=8:0 rwbs=R bytes=4096 sector=123 nr_sector=8",
        }
    )
    assert line == "kworker-77 [000] .... 1.000000: block_rq_issue: 8:0 R 4096 () 123 + 8"
