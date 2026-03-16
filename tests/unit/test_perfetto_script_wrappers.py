from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_perfetto_script_wrapper_help() -> None:
    wrapper = (
        REPO_ROOT
        / "scripts"
        / "perfetto"
        / "merge_perfetto_ptftrace_to_systrace_txt.py"
    )
    result = subprocess.run(
        [sys.executable, str(wrapper), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--csv-output" in result.stdout
    assert "--txt-output" in result.stdout
