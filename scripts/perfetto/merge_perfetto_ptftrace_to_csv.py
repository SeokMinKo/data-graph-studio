#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

TARGET = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "perfetto"
    / "merge_perfetto_ptftrace_to_csv.py"
)

runpy.run_path(str(TARGET), run_name="__main__")
