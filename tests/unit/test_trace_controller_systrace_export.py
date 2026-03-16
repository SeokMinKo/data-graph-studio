from __future__ import annotations

from pathlib import Path

from data_graph_studio.ui.controllers.trace_controller import TraceController


def test_trace_controller_formats_systrace_line() -> None:
    line = TraceController._format_systrace_line_from_csv_row(
        {
            "ts": "1000000000",
            "cpu": "2",
            "name": "block/block_rq_issue",
            "task": "kworker",
            "pid": "77",
            "details": "dev=8:0 rwbs=R bytes=4096 sector=123 nr_sector=8",
        }
    )
    assert line == "kworker-77 [002] .... 1.000000: block_rq_issue: 8:0 R 4096 () 123 + 8"


def test_trace_controller_converts_csv_to_systrace_txt(tmp_path: Path) -> None:
    input_csv = tmp_path / "merged.csv"
    input_csv.write_text(
        "source_trace,source_basename,ts,cpu,name,task,pid,details\n"
        "/tmp/a.ptftrace,a.ptftrace,1000000000,0,block/block_rq_issue,kworker,10,dev=8:0 rwbs=W bytes=4096 sector=100 nr_sector=8\n",
        encoding="utf-8",
    )
    output_txt = tmp_path / "merged.txt"

    count = TraceController.convert_perfetto_csv_to_systrace_txt(
        input_csv,
        output_txt,
        include_source_comments=True,
        include_header=True,
    )

    text = output_txt.read_text(encoding="utf-8")
    assert count == 1
    assert "# tracer: nop" in text
    assert "#           TASK-PID     CPU#  ||||    TIMESTAMP  FUNCTION" in text
    assert "# source: /tmp/a.ptftrace" in text
    assert "kworker-10 [000] .... 1.000000: block_rq_issue: 8:0 W 4096 () 100 + 8" in text
