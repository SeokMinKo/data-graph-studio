#!/usr/bin/env python3
"""Standalone one-shot pipeline: multiple Perfetto traces -> merged CSV
-> systrace txt.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge multiple Perfetto traces into CSV, then convert to systrace txt."
        )
    )
    parser.add_argument("inputs", nargs="*", help="Trace files or glob patterns.")
    parser.add_argument(
        "--input-dir",
        action="append",
        default=[],
        help="Directory to scan for trace files.",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Additional glob patterns for --input-dir.",
    )
    parser.add_argument(
        "--csv-output", type=Path, required=True, help="Merged CSV path."
    )
    parser.add_argument(
        "--txt-output", type=Path, required=True, help="Systrace txt path."
    )
    parser.add_argument(
        "--trace-processor",
        default=None,
        help="Path to trace_processor_shell (or trace_processor).",
    )
    parser.add_argument("--query-file", type=Path, help="Optional SQL file.")
    parser.add_argument(
        "--strict", action="store_true", help="Stop on first failed trace."
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Do not write systrace header comments.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    script_dir = Path(__file__).resolve().parent
    merge_script = script_dir / "merge_perfetto_ptftrace_to_csv.py"
    convert_script = script_dir / "convert_merged_perfetto_csv_to_systrace_txt.py"
    merge_cmd = [
        sys.executable,
        str(merge_script),
        *args.inputs,
        "--output",
        str(args.csv_output),
    ]
    for input_dir in args.input_dir:
        merge_cmd.extend(["--input-dir", input_dir])
    for pattern in args.pattern:
        merge_cmd.extend(["--pattern", pattern])
    if args.trace_processor:
        merge_cmd.extend(["--trace-processor", args.trace_processor])
    if args.query_file:
        merge_cmd.extend(["--query-file", str(args.query_file)])
    if args.strict:
        merge_cmd.append("--strict")
    rc = subprocess.run(merge_cmd, check=False).returncode
    if rc != 0:
        return rc
    convert_cmd = [
        sys.executable,
        str(convert_script),
        str(args.csv_output),
        "--output",
        str(args.txt_output),
        "--include-source-comments",
    ]
    if args.no_header:
        convert_cmd.append("--no-header")
    return subprocess.run(convert_cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
