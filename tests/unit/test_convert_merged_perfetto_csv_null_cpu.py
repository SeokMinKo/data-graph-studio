from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "perfetto"
    / "convert_merged_perfetto_csv_to_systrace_txt.py"
)


def test_convert_merged_perfetto_csv_handles_null_cpu(tmp_path: Path) -> None:
    merged_csv = tmp_path / "merged.csv"
    merged_csv.write_text(
        "\n".join(
            [
                "source_trace,source_basename,ts,cpu,name,task,pid,details",
                "/tmp/a.ptftrace,a.ptftrace,1000000000,NULL,"
                "block/block_rq_issue,kworker,10,"
                "dev=8:0 rwbs=W bytes=4096 sector=100 nr_sector=8",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_txt = tmp_path / "merged_systrace.txt"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(merged_csv), "--output", str(output_txt)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    text = output_txt.read_text(encoding="utf-8")
    assert "kworker-10 NULL .... 1.000000: block_rq_issue:" in text
    assert "block_rq_issue" in text
