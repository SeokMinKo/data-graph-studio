from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "convert_merged_perfetto_csv_to_systrace_txt.py"
)


def test_convert_merged_perfetto_csv_to_systrace_txt(tmp_path: Path) -> None:
    merged_csv = tmp_path / "merged.csv"
    merged_csv.write_text(
        "source_trace,source_basename,ts,cpu,name,task,pid,details\n"
        "/tmp/a.ptftrace,a.ptftrace,1000000000,0,block/block_rq_issue,kworker,10,dev=8:0 rwbs=W bytes=4096 sector=100 nr_sector=8\n"
        "/tmp/a.ptftrace,a.ptftrace,1000200000,0,block/block_rq_complete,kworker,10,dev=8:0 rwbs=W sector=100 nr_sector=8\n",
        encoding="utf-8",
    )

    output_txt = tmp_path / "merged_systrace.txt"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(merged_csv),
            "--output",
            str(output_txt),
            "--include-source-comments",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    text = output_txt.read_text(encoding="utf-8")
    assert "# tracer: nop" in text
    assert "# converted from Perfetto CSV by Data Graph Studio" in text
    assert "#           TASK-PID     CPU#  ||||    TIMESTAMP  FUNCTION" in text
    assert "# source: /tmp/a.ptftrace" in text
    assert "kworker-10 [000] .... 1.000000: block_rq_issue: 8:0 W 4096 () 100 + 8" in text
    assert "kworker-10 [000] .... 1.000200: block_rq_complete: 8:0 W () 100 + 8" in text
