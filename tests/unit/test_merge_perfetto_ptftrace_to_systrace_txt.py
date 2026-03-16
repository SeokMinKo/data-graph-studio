from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "merge_perfetto_ptftrace_to_systrace_txt.py"
)


def test_oneshot_merge_to_systrace_pipeline(tmp_path: Path) -> None:
    trace_a = tmp_path / "a.ptftrace"
    trace_a.write_text("trace-a", encoding="utf-8")

    fake_tp = tmp_path / "fake_trace_processor.py"
    fake_tp.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "from pathlib import Path\n\n"
            "trace_path = Path(sys.argv[-1])\n"
            "if trace_path.name == 'a.ptftrace':\n"
            "    sys.stdout.write(\n"
            "        'ts,cpu,name,task,pid,details\\n'\n"
            "        '1,0,block_rq_issue,kworker,10,'\n"
            "        'dev=8:0 rwbs=R bytes=4096 sector=100 nr_sector=8\\n'\n"
            "    )\n"
            "else:\n"
            "    sys.stdout.write('ts,cpu,name,task,pid,details\\n')\n"
        ),
        encoding="utf-8",
    )
    fake_tp.chmod(0o755)

    csv_output = tmp_path / "merged.csv"
    txt_output = tmp_path / "merged.txt"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(trace_a),
            "--trace-processor",
            str(fake_tp),
            "--csv-output",
            str(csv_output),
            "--txt-output",
            str(txt_output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert csv_output.exists()
    text = txt_output.read_text(encoding="utf-8")
    assert "# tracer: nop" in text
    assert "block_rq_issue" in text
