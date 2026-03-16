#!/usr/bin/env python3
"""Standalone: convert merged Perfetto CSV into systrace/ftrace-style text."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Sequence


def normalize_event_name(event_name: Any) -> str:
    if not isinstance(event_name, str):
        return ""
    event = event_name.strip()
    if "/" in event:
        event = event.split("/", 1)[1]
    return event


def parse_perfetto_kv_details(details: Any) -> dict[str, str]:
    if not isinstance(details, str):
        return {}
    result: dict[str, str] = {}
    for token in details.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        value = value.strip().strip(",")
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def coerce_perfetto_details(event_name: str, details: Any) -> str:
    event = normalize_event_name(event_name)
    if not isinstance(details, str):
        return ""
    if event not in {"block_rq_insert", "block_rq_issue", "block_rq_complete"}:
        return details
    kv = parse_perfetto_kv_details(details)
    dev = kv.get("dev")
    if not dev:
        major = kv.get("major")
        minor = kv.get("minor") or kv.get("first_minor")
        if major is not None and minor is not None:
            dev = f"{major},{minor}"
    rwbs = kv.get("rwbs") or kv.get("rw_bs") or "R"
    sector = kv.get("sector")
    nr_sectors = kv.get("nr_sector") or kv.get("nr_sectors")
    if not dev or sector is None or nr_sectors is None:
        return details
    if event in {"block_rq_insert", "block_rq_issue"}:
        size_bytes = kv.get("bytes") or kv.get("nr_bytes")
        if size_bytes is None:
            try:
                size_bytes = str(int(nr_sectors) * 512)
            except Exception:
                size_bytes = "0"
        return f"{dev} {rwbs} {size_bytes} () {sector} + {nr_sectors}"
    return f"{dev} {rwbs} () {sector} + {nr_sectors}"


def coerce_timestamp(value: Any) -> float:
    try:
        raw = float(value)
    except Exception:
        return 0.0
    return raw / 1e9 if raw > 1_000_000 else raw


def format_cpu_field(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    if text == "" or text.upper() == "NULL":
        return "NULL"
    try:
        return f"[{int(float(text)):03d}]"
    except Exception:
        return "NULL"


def format_systrace_line(row: dict[str, str]) -> str:
    task = str(row.get("task") or "<unknown>").strip() or "<unknown>"
    pid = row.get("pid") or "-1"
    cpu = format_cpu_field(row.get("cpu"))
    flags = str(row.get("flags") or "....").strip() or "...."
    event_raw = row.get("event") or row.get("name") or ""
    event = normalize_event_name(event_raw)
    details = coerce_perfetto_details(str(event_raw), row.get("details") or "")
    timestamp = coerce_timestamp(row.get("timestamp") or row.get("ts") or "0")
    return f"{task}-{pid} {cpu} {flags} {timestamp:.6f}: {event}: {details}".rstrip()


def systrace_header(title: str = "merged Perfetto trace") -> str:
    return "\n".join(
        [
            "# tracer: nop",
            "#",
            f"# {title}",
            "# converted from Perfetto CSV",
            "#",
            "#           TASK-PID     CPU#  ||||    TIMESTAMP  FUNCTION",
            "#              | |         |   ||||       |         |",
        ]
    )


def convert_csv_to_systrace(
    input_csv: Path,
    output_txt: Path,
    include_source_comments: bool,
    include_header: bool,
) -> int:
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    current_source = None
    with (
        input_csv.open("r", newline="", encoding="utf-8") as src,
        output_txt.open("w", encoding="utf-8") as dst,
    ):
        if include_header:
            dst.write(systrace_header(input_csv.name) + "\n")
        reader = csv.DictReader(src)
        for row in reader:
            source_trace = row.get("source_trace")
            if (
                include_source_comments
                and source_trace
                and source_trace != current_source
            ):
                if count:
                    dst.write("\n")
                dst.write(f"# source: {source_trace}\n")
                current_source = source_trace
            dst.write(format_systrace_line(row) + "\n")
            count += 1
    return count


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert merged Perfetto CSV to systrace/ftrace-style text."
    )
    parser.add_argument("input_csv", type=Path, help="Merged Perfetto CSV path.")
    parser.add_argument("--output", type=Path, required=True, help="Output txt path.")
    parser.add_argument(
        "--include-source-comments",
        action="store_true",
        help="Insert '# source: ...' lines when source_trace changes.",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Do not write systrace-style header comments.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    row_count = convert_csv_to_systrace(
        args.input_csv.expanduser(),
        args.output.expanduser(),
        args.include_source_comments,
        not args.no_header,
    )
    print(f"Wrote {row_count} systrace line(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
