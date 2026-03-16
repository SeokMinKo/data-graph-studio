from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "perfetto" / "merge_perfetto_ptftrace_to_csv.py"


def test_merge_perfetto_traces_sorts_by_ts_and_absorbs_extra_csv_fields(tmp_path: Path) -> None:
    trace_a = tmp_path / "a.ptftrace"
    trace_b = tmp_path / "b.ptftrace"
    trace_a.write_text("trace-a", encoding="utf-8")
    trace_b.write_text("trace-b", encoding="utf-8")

    fake_tp = tmp_path / "fake_trace_processor.py"
    fake_tp.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "from pathlib import Path\n\n"
            "trace_path = Path(sys.argv[-1])\n"
            "if trace_path.name == 'a.ptftrace':\n"
            "    sys.stdout.buffer.write(b'ts,cpu,name,task,pid,details\\n200,0,block_rq_issue,kworker,10,dev=8,0 rwbs=R bytes=4096 sector=200 nr_sector=8\\n')\n"
            "else:\n"
            "    sys.stdout.buffer.write('ts,cpu,name,task,pid,details\\n100,0,block_rq_issue,kworker,11,dev=8:0 rwbs=W bytes=4096 sector=100 nr_sector=8\\n'.encode('utf-8'))\n"
        ),
        encoding="utf-8",
    )
    fake_tp.chmod(0o755)

    output = tmp_path / "merged.csv"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(trace_a),
            str(trace_b),
            "--trace-processor",
            str(fake_tp),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = output.read_text(encoding="utf-8").strip().splitlines()
    assert lines[1].split(",", 3)[2] == "100"
    assert "dev=8,0 rwbs=R bytes=4096 sector=200 nr_sector=8" in lines[2]
