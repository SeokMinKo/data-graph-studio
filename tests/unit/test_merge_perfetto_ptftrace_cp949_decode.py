from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "perfetto"
    / "merge_perfetto_ptftrace_to_csv.py"
)


def test_merge_perfetto_traces_handles_non_utf8_subprocess_output(
    tmp_path: Path,
) -> None:
    trace_a = tmp_path / "a.ptftrace"
    trace_a.write_text("trace-a", encoding="utf-8")

    fake_tp = tmp_path / "fake_trace_processor.py"
    fake_tp.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stdout.buffer.write('ts,cpu,name,task,pid,details\\n1,0,block_rq_issue,kworker,10,ok\\n'.encode('cp949'))\n"
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
    assert "block_rq_issue" in output.read_text(encoding="utf-8")
