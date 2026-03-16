#!/usr/bin/env python3
"""Standalone: merge multiple Perfetto trace files into one CSV."""

from __future__ import annotations

import argparse
import csv
import glob
import locale
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_QUERY = (
    "SELECT fe.ts, c.cpu, fe.name, t.name AS task, t.tid AS pid, "
    "group_concat(a.key || '=' || a.display_value, ' ') AS details "
    "FROM ftrace_event fe "
    "LEFT JOIN cpu c ON fe.ucpu = c.id "
    "LEFT JOIN thread t ON fe.utid = t.id "
    "LEFT JOIN args a ON fe.arg_set_id = a.arg_set_id "
    "GROUP BY fe.id "
    "ORDER BY fe.ts"
)
DEFAULT_PATTERNS = ("*.ptftrace", "*.pftrace", "*.perfetto-trace")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert multiple Perfetto trace files and merge them into one CSV."
    )
    parser.add_argument("inputs", nargs="*", help="Trace files or glob patterns.")
    parser.add_argument(
        "--input-dir", type=Path, action="append", default=[], help="Directory to scan."
    )
    parser.add_argument(
        "--pattern", action="append", default=[], help="Additional glob pattern(s)."
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Merged CSV output path."
    )
    parser.add_argument(
        "--trace-processor",
        default=None,
        help="Path to trace_processor_shell (or trace_processor).",
    )
    parser.add_argument("--query-file", type=Path, help="Optional SQL file.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Stop immediately if any trace conversion fails.",
    )
    return parser.parse_args(argv)


def resolve_trace_processor(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"trace processor not found: {path}")
        return str(path)

    local_dir = Path(__file__).resolve().parent
    local_candidates = [
        local_dir / "trace_processor_shell.exe",
        local_dir / "trace_processor_shell",
        local_dir / "trace_processor.exe",
        local_dir / "trace_processor",
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)

    for name in (
        "trace_processor_shell.exe",
        "trace_processor_shell",
        "trace_processor.exe",
        "trace_processor",
    ):
        found = shutil.which(name)
        if found:
            return found
    raise FileNotFoundError(
        "trace_processor_shell not found. Put trace_processor_shell.exe next "
        "to this script or pass --trace-processor explicitly."
    )


def expand_inputs(
    raw_inputs: Sequence[str], input_dirs: Sequence[Path], extra_patterns: Sequence[str]
) -> list[Path]:
    resolved: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        rp = path.expanduser().resolve()
        if rp.is_file() and rp not in seen:
            resolved.append(rp)
            seen.add(rp)

    for raw in raw_inputs:
        has_glob = any(ch in raw for ch in "*?[]")
        matches = [Path(match) for match in glob.glob(raw)] if has_glob else []
        if matches:
            for match in matches:
                add(match)
            continue
        add(Path(raw))

    patterns = list(DEFAULT_PATTERNS) + list(extra_patterns)
    for base_dir in input_dirs:
        base = base_dir.expanduser().resolve()
        if not base.is_dir():
            continue
        for pattern in patterns:
            for match in sorted(base.glob(pattern)):
                add(match)
    return resolved


def load_query(query_file: Path | None) -> str:
    return (
        DEFAULT_QUERY
        if query_file is None
        else query_file.expanduser().read_text(encoding="utf-8").strip()
    )


def _decode_output(raw: bytes) -> str:
    for encoding in ("utf-8", locale.getpreferredencoding(False), "cp949"):
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def convert_trace(trace_processor: str, query: str, trace_path: Path) -> str:
    proc = subprocess.run(
        [trace_processor, "-Q", query, str(trace_path)],
        capture_output=True,
        timeout=300,
    )
    stdout = _decode_output(proc.stdout)
    stderr = _decode_output(proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(
            "trace_processor failed for "
            f"{trace_path.name}: {stderr.strip() or stdout.strip()}"
        )
    return stdout


def _parse_ts_sort_value(value: str | None) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _normalize_row(
    fieldnames: list[str], row: dict[str, str | list[str] | None]
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for field in fieldnames:
        value = row.get(field, "")
        normalized[field] = "" if value is None else str(value)

    extras = row.get(None)
    if extras:
        extra_text = ",".join(str(part) for part in extras if part is not None)
        if extra_text:
            details = normalized.get("details", "")
            normalized["details"] = f"{details},{extra_text}" if details else extra_text
    return normalized


def merge_csv_rows(
    csv_texts: Iterable[tuple[Path, str]], output_path: Path
) -> tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header: list[str] | None = None
    row_count = 0
    trace_count = 0
    merged_rows: list[dict[str, str]] = []

    for trace_path, csv_text in csv_texts:
        reader = csv.DictReader(csv_text.splitlines())
        if reader.fieldnames is None:
            continue

        base_fields = list(reader.fieldnames)
        fieldnames = ["source_trace", "source_basename", *base_fields]
        if header is None:
            header = fieldnames
        elif fieldnames != header:
            raise ValueError(
                "CSV schema mismatch for "
                f"{trace_path.name}: expected {header[2:]}, got {reader.fieldnames}"
            )

        wrote_any = False
        for row in reader:
            clean_row = _normalize_row(base_fields, row)
            merged_rows.append(
                {
                    "source_trace": str(trace_path),
                    "source_basename": trace_path.name,
                    **clean_row,
                }
            )
            row_count += 1
            wrote_any = True
        if wrote_any:
            trace_count += 1

    if header is None:
        return 0, 0

    sort_key = (
        "ts" if "ts" in header else ("timestamp" if "timestamp" in header else None)
    )
    if sort_key is not None:
        merged_rows.sort(key=lambda row: _parse_ts_sort_value(row.get(sort_key)))

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in merged_rows:
            writer.writerow(row)
    return trace_count, row_count


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    trace_processor = resolve_trace_processor(args.trace_processor)
    query = load_query(args.query_file)
    trace_paths = expand_inputs(args.inputs, args.input_dir, args.pattern)
    if not trace_paths:
        print("No trace files found.", file=sys.stderr)
        return 2
    converted: list[tuple[Path, str]] = []
    failures: list[str] = []
    for trace_path in trace_paths:
        try:
            csv_text = convert_trace(trace_processor, query, trace_path)
            converted.append((trace_path, csv_text))
            print(f"[ok] {trace_path}", file=sys.stderr)
        except Exception as exc:
            msg = f"[fail] {trace_path}: {exc}"
            failures.append(msg)
            print(msg, file=sys.stderr)
            if args.strict:
                return 1
    if not converted:
        print("No traces were converted successfully.", file=sys.stderr)
        return 1
    trace_count, row_count = merge_csv_rows(converted, args.output)
    print(
        f"Merged {trace_count} trace(s) into {args.output} ({row_count} row(s)).",
        file=sys.stderr,
    )
    if failures:
        print(f"Completed with {len(failures)} failure(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
