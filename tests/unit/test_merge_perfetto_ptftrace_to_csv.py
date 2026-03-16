from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "merge_perfetto_ptftrace_to_csv.py"


def test_merge_perfetto_traces_into_single_csv(tmp_path: Path) -> None:
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
            "    sys.stdout.write('ts,cpu,name,task,pid,details\\n1,0,block_rq_issue,kworker,10,dev=8:0\\n')\n"
            "else:\n"
            "    sys.stdout.write('ts,cpu,name,task,pid,details\\n2,1,block_rq_complete,kworker,11,dev=8:0\\n')\n"
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
    merged = output.read_text(encoding="utf-8")
    assert "source_trace,source_basename,ts,cpu,name,task,pid,details" in merged
    assert ",a.ptftrace,1,0,block_rq_issue," in merged
    assert "a.ptftrace" in merged
    assert "b.ptftrace" in merged
    assert "block_rq_issue" in merged
    assert "block_rq_complete" in merged
