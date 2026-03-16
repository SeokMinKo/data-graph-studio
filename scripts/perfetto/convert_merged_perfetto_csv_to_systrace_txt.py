#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

TARGET = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "perfetto"
    / "convert_merged_perfetto_csv_to_systrace_txt.py"
)

runpy.run_path(str(TARGET), run_name="__main__")
