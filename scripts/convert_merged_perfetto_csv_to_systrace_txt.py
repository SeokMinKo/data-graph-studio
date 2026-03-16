#!/usr/bin/env python3
"""Convert merged Perfetto CSV back into systrace/ftrace-style text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_graph_studio.ui.controllers.trace_controller import TraceController


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert merged Perfetto CSV to systrace/ftrace-style text."
    )
    parser.add_argument("input_csv", type=Path, help="Merged Perfetto CSV path.")
    parser.add_argument("--output", type=Path, required=True, help="Output txt path.")
    parser.add_argument(
        "--include-source-comments",
        action="store_true",
        help="Insert '# source: ...' comment lines when source_trace changes.",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Do not write the systrace-style header comments.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    row_count = TraceController.convert_perfetto_csv_to_systrace_txt(
        args.input_csv.expanduser(),
        args.output.expanduser(),
        include_source_comments=args.include_source_comments,
        include_header=not args.no_header,
    )
    print(f"Wrote {row_count} systrace line(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
