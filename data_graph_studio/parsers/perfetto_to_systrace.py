"""Perfetto trace → systrace (ftrace text) converter.

Converts one or more Perfetto binary traces (.pftrace) to a single
merged systrace file, sorted by timestamp.

Pipeline:
    1. .pftrace → CSV via trace_processor_shell (SQL query on ftrace_event)
    2. CSV → systrace text (ftrace format)
    3. Multiple traces merged & sorted by global timestamp

Usage (CLI):
    python perfetto_to_systrace.py trace1.pftrace trace2.pftrace -o merged.systrace
    python perfetto_to_systrace.py *.pftrace -o merged.systrace
    python perfetto_to_systrace.py "logs/*.pftrace" -o merged.systrace

Usage (API):
    from data_graph_studio.parsers.perfetto_to_systrace import (
        convert_perfetto_to_systrace,
    )
    convert_perfetto_to_systrace(
        ["trace1.pftrace", "trace2.pftrace"],
        output_path="merged.systrace",
    )
"""

from __future__ import annotations

import argparse
import csv
import glob
import io
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Same SQL query used by PerfettoTraceController
FTRACE_QUERY = (
    "SELECT fe.ts, c.cpu, fe.name, t.name AS task, t.tid AS pid, "
    "group_concat(a.key || '=' || a.display_value, ' ') AS details "
    "FROM ftrace_event fe "
    "LEFT JOIN cpu c ON fe.ucpu = c.id "
    "LEFT JOIN thread t ON fe.utid = t.id "
    "LEFT JOIN args a ON fe.arg_set_id = a.arg_set_id "
    "GROUP BY fe.id "
    "ORDER BY fe.ts"
)

SYSTRACE_HEADER = """\
# tracer: nop
#
# entries-in-buffer/entries-written: {entries}/{entries}   #P:{cpus}
#
#                                      _-----=> irqs-off
#                                     / _----=> need-resched
#                                    | / _---=> hardirq/softirq
#                                   || / _--=> preempt-depth
#                                  ||| /     delay
#           TASK-PID     CPU#  ||||   TIMESTAMP  FUNCTION
#              | |         |   ||||       |         |
"""


def find_trace_processor() -> str:
    """Find trace_processor_shell binary.

    Search order:
        1. Same directory as this script
        2. Bundled binaries in assets/bin/<platform>/
        3. PATH lookup
    """
    import platform as _platform
    import shutil

    _NAMES = ["trace_processor_shell", "trace_processor"]
    if sys.platform == "win32":
        _NAMES.extend(["trace_processor_shell.exe", "trace_processor.exe"])

    # 1. Same directory as this script
    script_dir = Path(__file__).resolve().parent
    for name in _NAMES:
        candidate = script_dir / name
        if candidate.exists():
            return str(candidate)

    # 2. Bundled binary (for DGS project layout)
    s = sys.platform
    m = _platform.machine().lower()
    if s == "darwin":
        plat = "darwin-arm64" if m in ("arm64", "aarch64") else "darwin-amd64"
    elif s == "linux":
        plat = "linux-arm64" if m in ("arm64", "aarch64") else "linux-amd64"
    elif s == "win32":
        plat = "win-amd64"
    else:
        plat = ""

    if plat:
        assets_dir = Path(__file__).parent.parent / "assets" / "bin" / plat
        for name in _NAMES:
            candidate = assets_dir / name
            if candidate.exists():
                return str(candidate)

    # 3. PATH lookup
    for name in _NAMES:
        found = shutil.which(name)
        if found:
            return found

    raise FileNotFoundError(
        "trace_processor_shell not found.\n"
        "Place it in the same folder as this script, or add it to PATH."
    )


def _expand_paths(patterns: List[str]) -> List[str]:
    """Expand glob patterns and return sorted unique file paths.

    Supports:
        - Direct file paths: trace1.pftrace
        - Shell glob patterns: *.pftrace, logs/*.pftrace
    """
    result = []
    seen = set()
    for pattern in patterns:
        # Try glob expansion first
        matched = sorted(glob.glob(pattern))
        if matched:
            for p in matched:
                rp = str(Path(p).resolve())
                if rp not in seen:
                    seen.add(rp)
                    result.append(p)
        else:
            # No glob match — treat as literal path (will error later if missing)
            rp = str(Path(pattern).resolve())
            if rp not in seen:
                seen.add(rp)
                result.append(pattern)
    return result


def _perfetto_to_csv_text(pftrace_path: str, tp_shell: str) -> str:
    """Run trace_processor_shell and return raw CSV text."""
    result = subprocess.run(
        [tp_shell, "-Q", FTRACE_QUERY, pftrace_path],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"trace_processor_shell failed for {pftrace_path}: "
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _normalize_event_name(name: str) -> str:
    """'block/block_rq_issue' → 'block_rq_issue'."""
    if "/" in name:
        return name.split("/", 1)[1]
    return name


def _parse_perfetto_kv(details: str) -> dict:
    """Parse 'key=value key2=value2' into dict."""
    result = {}
    for token in details.split():
        if "=" not in token:
            continue
        k, v = token.split("=", 1)
        result[k.strip()] = v.strip().strip(",").strip('"')
    return result


def _coerce_details_to_ftrace(event: str, details: str) -> str:
    """Convert Perfetto key=value details to legacy ftrace format.

    For block layer events, produces:
        issue/insert: <dev> <rwbs> <bytes> () <sector> + <nr_sectors>
        complete:     <dev> <rwbs> () <sector> + <nr_sectors>

    For non-block events, returns the original key=value string reformatted
    as ftrace-compatible details.
    """
    event = _normalize_event_name(event)

    if event not in {"block_rq_insert", "block_rq_issue", "block_rq_complete"}:
        # Non-block events: convert key=value pairs to ftrace-like format
        return details

    kv = _parse_perfetto_kv(details)

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


def _csv_to_events(csv_text: str) -> List[dict]:
    """Parse CSV text into list of event dicts with normalized fields.

    Returns list of dicts with keys:
        ts_ns (int), ts_sec (float), cpu (int), task (str),
        pid (int), event (str), details (str)
    """
    events = []
    reader = csv.DictReader(io.StringIO(csv_text))

    # Detect column name variants
    for row in reader:
        # Timestamp in nanoseconds
        ts_ns = int(row.get("ts") or row.get("timestamp") or 0)

        cpu = int(row.get("cpu") or 0)
        task = (row.get("task") or row.get("name_1") or "").strip() or "<...>"
        pid = int(row.get("pid") or row.get("tid") or 0)
        raw_event = (row.get("name") or row.get("event") or "").strip()
        details = (row.get("details") or "").strip()

        event = _normalize_event_name(raw_event)
        details = _coerce_details_to_ftrace(raw_event, details)

        events.append(
            {
                "ts_ns": ts_ns,
                "ts_sec": ts_ns / 1e9,
                "cpu": cpu,
                "task": task,
                "pid": pid,
                "event": event,
                "details": details,
            }
        )

    return events


def _format_systrace_line(ev: dict) -> str:
    """Format a single event dict as an ftrace text line.

    Format:
        <task>-<pid>   [<cpu>] ....  <timestamp>: <event>: <details>
    """
    task = ev["task"] or "<...>"
    pid = ev["pid"]
    cpu = ev["cpu"]
    ts = ev["ts_sec"]
    event = ev["event"]
    details = ev["details"]

    # Pad task-pid to align with standard ftrace output
    task_pid = f"{task}-{pid}"
    return f"  {task_pid:>20s} [{cpu:03d}] .... {ts:15.6f}: {event}: {details}"


def convert_perfetto_to_systrace(
    pftrace_paths: List[str],
    output_path: str,
    tp_shell: Optional[str] = None,
    save_intermediate_csv: bool = False,
) -> str:
    """Convert one or more Perfetto traces to a single merged systrace file.

    Args:
        pftrace_paths: List of .pftrace file paths.
        output_path: Output systrace file path.
        tp_shell: Path to trace_processor_shell (auto-detected if None).
        save_intermediate_csv: If True, save per-trace CSV files alongside output.

    Returns:
        Path to the output systrace file.
    """
    if tp_shell is None:
        tp_shell = find_trace_processor()
    logger.info("Using trace_processor_shell: %s", tp_shell)
    print(f"Using: {tp_shell}")

    # Expand glob patterns (e.g. *.pftrace)
    resolved_paths = _expand_paths(pftrace_paths)
    if not resolved_paths:
        raise FileNotFoundError(
            f"No files matched: {pftrace_paths}"
        )
    print(f"Found {len(resolved_paths)} trace file(s)")

    all_events: List[dict] = []

    for i, pf_path in enumerate(resolved_paths):
        pf_path = str(Path(pf_path).resolve())
        if not Path(pf_path).exists():
            raise FileNotFoundError(f"Trace file not found: {pf_path}")

        logger.info("[%d/%d] Converting: %s", i + 1, len(resolved_paths), pf_path)
        print(f"[{i + 1}/{len(resolved_paths)}] Converting: {Path(pf_path).name}")

        csv_text = _perfetto_to_csv_text(pf_path, tp_shell)

        if save_intermediate_csv:
            csv_path = str(Path(pf_path).with_suffix(".csv"))
            Path(csv_path).write_text(csv_text, encoding="utf-8")
            logger.info("  Saved CSV: %s", csv_path)
            print(f"  Saved CSV: {csv_path}")

        events = _csv_to_events(csv_text)
        logger.info("  Parsed %d events from %s", len(events), Path(pf_path).name)
        print(f"  Parsed {len(events)} events")
        all_events.extend(events)

    # Sort all events by timestamp
    all_events.sort(key=lambda e: e["ts_ns"])
    logger.info("Total events after merge: %d", len(all_events))
    print(f"Total events after merge & sort: {len(all_events)}")

    # Determine max CPU count for header
    max_cpu = max((e["cpu"] for e in all_events), default=0) + 1

    # Write systrace output
    out = Path(output_path)
    with out.open("w", encoding="utf-8") as f:
        f.write(SYSTRACE_HEADER.format(entries=len(all_events), cpus=max_cpu))
        for ev in all_events:
            f.write(_format_systrace_line(ev))
            f.write("\n")

    logger.info("Systrace written: %s (%d events)", output_path, len(all_events))
    print(f"Output: {output_path} ({len(all_events)} events)")
    return str(out)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert Perfetto traces (.pftrace) to systrace format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Single trace
  %(prog)s trace.pftrace -o trace.systrace

  # Multiple traces merged by time
  %(prog)s trace1.pftrace trace2.pftrace trace3.pftrace -o merged.systrace

  # Glob pattern (all .pftrace in current dir)
  %(prog)s *.pftrace -o merged.systrace
  %(prog)s "logs/*.pftrace" -o merged.systrace

  # Also save intermediate CSVs
  %(prog)s *.pftrace -o merged.systrace --save-csv

Note: trace_processor_shell is auto-detected in this order:
  1. Same folder as this script
  2. Bundled in assets/bin/<platform>/
  3. PATH
""",
    )
    parser.add_argument(
        "traces",
        nargs="+",
        help="Perfetto trace files (.pftrace) or glob patterns (e.g. *.pftrace)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output systrace file path",
    )
    parser.add_argument(
        "--tp-shell",
        default=None,
        help="Path to trace_processor_shell (auto-detected if omitted)",
    )
    parser.add_argument(
        "--save-csv",
        action="store_true",
        help="Save intermediate CSV files alongside output",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        convert_perfetto_to_systrace(
            pftrace_paths=args.traces,
            output_path=args.output,
            tp_shell=args.tp_shell,
            save_intermediate_csv=args.save_csv,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
