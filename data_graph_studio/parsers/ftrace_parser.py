"""Ftrace log parser — 2-step pipeline.

Step 1 (parse_raw): raw ftrace text → structured event DataFrame
Step 2 (convert):   event DataFrame → analysis-ready DataFrame
                    (e.g. block layer: send/complete → latency, queue depth)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import polars as pl

from .base import BaseParser

logger = logging.getLogger(__name__)

# Ftrace line format reference: https://docs.kernel.org/trace/ftrace.html
# Standard:  <task>-<pid>   [<cpu>] <flags> <timestamp>: <event>: <details>
# With tgid: <task>-<pid>  (<tgid>) [<cpu>] <flags> <timestamp>: <event>: <details>
# Example:   kworker/0:1-12345 [000] .... 12345.678901: block_rq_issue: 8,0 R 4096
FTRACE_LINE_RE = re.compile(
    r"^\s*(?P<task>.+?)-(?P<pid>\d+)"
    r"\s+(?:\([\s\d-]+\)\s+)?"
    r"\[(?P<cpu>\d+)\]"
    r"\s+(?P<flags>\S{4,5})"
    r"\s+(?P<timestamp>\d+\.\d+):"
    r"\s+(?P<event>[\w:]+):"
    r"\s+(?P<details>.*?)$",
    re.MULTILINE,
)

# Schema for the raw event DataFrame.
_RAW_SCHEMA = {
    "timestamp": pl.Float64,
    "cpu": pl.Int32,
    "task": pl.Utf8,
    "pid": pl.Int32,
    "flags": pl.Utf8,
    "event": pl.Utf8,
    "details": pl.Utf8,
}


class FtraceParser(BaseParser):
    """Linux ftrace log parser (2-step: parse → convert)."""

    name = "Ftrace Parser"
    key = "ftrace"
    file_filter = "Ftrace Files (*.txt *.dat *.log);;All Files (*)"

    def default_settings(self) -> Dict[str, Any]:
        return {
            # --- Step 1: parsing ---
            "skip_comments": True,       # skip lines starting with #
            "events": [],                # filter specific events (empty = all)
            "cpus": [],                  # filter specific CPUs (empty = all)
            # --- Step 2: conversion ---
            "converter": "",             # converter name (e.g. "blocklayer")
            "converter_options": {},     # converter-specific options
        }

    def parse(self, file_path: str, settings: Optional[Dict[str, Any]] = None) -> pl.DataFrame:
        """Full pipeline: parse_raw → convert."""
        settings = settings or self.default_settings()

        raw_df = self.parse_raw(file_path, settings)
        result_df = self.convert(raw_df, settings)
        return result_df

    # ==================================================================
    # Step 1: Raw Parsing
    # ==================================================================

    def parse_raw(self, file_path: str, settings: Dict[str, Any]) -> pl.DataFrame:
        """Parse raw ftrace text into a structured event DataFrame.

        Reads the file, extracts ftrace events via regex, and returns a
        polars DataFrame with columns: timestamp, cpu, task, pid, flags,
        event, details.  Non-matching lines (comments, headers, garbage)
        are silently skipped.

        Args:
            file_path: Path to ftrace log file.
            settings: Parser settings dict (expects ``events`` and ``cpus``).

        Returns:
            Raw event DataFrame filtered by requested events/cpus.

        Raises:
            FileNotFoundError: If *file_path* does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        df = self._extract_events(text)
        return self._apply_filters(df, settings)

    # -- private helpers --------------------------------------------------

    @staticmethod
    def _extract_events(text: str) -> pl.DataFrame:
        """Extract ftrace events from *text* via regex.

        Args:
            text: Raw ftrace file content.

        Returns:
            Unfiltered DataFrame of all matched events.
        """
        timestamps: List[float] = []
        cpus: List[int] = []
        tasks: List[str] = []
        pids: List[int] = []
        flags: List[str] = []
        events: List[str] = []
        details: List[str] = []

        for m in FTRACE_LINE_RE.finditer(text):
            timestamps.append(float(m["timestamp"]))
            cpus.append(int(m["cpu"]))
            tasks.append(m["task"].strip())
            pids.append(int(m["pid"]))
            flags.append(m["flags"])
            events.append(m["event"])
            details.append(m["details"].strip())

        if not timestamps:
            return pl.DataFrame(schema=_RAW_SCHEMA)

        return pl.DataFrame(
            {
                "timestamp": timestamps,
                "cpu": cpus,
                "task": tasks,
                "pid": pids,
                "flags": flags,
                "event": events,
                "details": details,
            },
            schema=_RAW_SCHEMA,
        )

    @staticmethod
    def _apply_filters(df: pl.DataFrame, settings: Dict[str, Any]) -> pl.DataFrame:
        """Apply event and CPU filters using polars vector operations.

        Args:
            df: Unfiltered event DataFrame.
            settings: Must contain ``events`` and ``cpus`` lists.

        Returns:
            Filtered DataFrame.
        """
        evt_filter: List[str] = settings.get("events", [])
        cpu_filter: List[int] = settings.get("cpus", [])

        if evt_filter:
            df = df.filter(pl.col("event").is_in(evt_filter))
        if cpu_filter:
            df = df.filter(pl.col("cpu").is_in(cpu_filter))

        return df

    # ==================================================================
    # Step 2: Conversion
    # ==================================================================

    def convert(self, raw_df: pl.DataFrame, settings: Dict[str, Any]) -> pl.DataFrame:
        """Convert raw events into analysis-ready DataFrame.

        Dispatches to specific converter based on settings["converter"].
        e.g. "blocklayer" → send/complete pair matching → latency, queue depth

        TODO: 고돌 구현 예정

        Args:
            raw_df: Output from parse_raw().
            settings: Parser settings dict.

        Returns:
            Analysis-ready DataFrame.
        """
        converter = settings.get("converter", "")

        if not converter:
            # No conversion — return raw events as-is
            return raw_df

        convert_fn = self._converters.get(converter)
        if convert_fn is None:
            raise ValueError(f"Unknown converter: '{converter}'")

        return convert_fn(self, raw_df, settings.get("converter_options", {}))

    # ------------------------------------------------------------------
    # Converter registry — add new converters here
    # ------------------------------------------------------------------

    # block_rq_issue/insert details: <dev> <rwbs> <bytes> () <sector> + <nr_sectors> [<comm>]
    # block_rq_complete details:     <dev> <rwbs> () <sector> + <nr_sectors> [<errno>]
    _ISSUE_RE = re.compile(
        r"^(?P<dev>\S+)\s+(?P<rwbs>\S+)\s+(?P<bytes>\d+)\s+\(\)\s+"
        r"(?P<sector>\d+)\s*\+\s*(?P<nr_sectors>\d+)"
    )
    _COMPLETE_RE = re.compile(
        r"^(?P<dev>\S+)\s+(?P<rwbs>\S+)\s+\(\)\s+"
        r"(?P<sector>\d+)\s*\+\s*(?P<nr_sectors>\d+)"
    )

    _RESULT_SCHEMA = {
        "timestamp": pl.Float64,
        "latency_ms": pl.Float64,
        "d2c_ms": pl.Float64,
        "q2c_ms": pl.Float64,
        "c2c_ms": pl.Float64,
        "issue_time": pl.Float64,
        "complete_time": pl.Float64,
        "sector": pl.Int64,
        "nr_sectors": pl.Int32,
        "rwbs": pl.Utf8,
        "size_bytes": pl.Int64,
        "device": pl.Utf8,
        "queue_depth": pl.Int32,
    }

    def _convert_blocklayer(
        self, raw_df: pl.DataFrame, options: Dict[str, Any]
    ) -> pl.DataFrame:
        """Block layer converter — matches insert/issue/complete events.

        Tracks the full block I/O lifecycle::

            block_rq_insert (Q) → block_rq_issue (D) → block_rq_complete (C)

        Computes:
        - **d2c_ms** (D2C): dispatch-to-complete latency
        - **q2c_ms** (Q2C): queue-to-complete latency (falls back to D2C if no insert)
        - **c2c_ms** (C2C): inter-completion time (time between consecutive completes)
        - **latency_ms**: alias for d2c_ms (backward compat)
        - **issue_time**: absolute timestamp of dispatch (issue)
        - **complete_time**: absolute timestamp of completion
        - **queue_depth**: outstanding I/Os at dispatch time

        Unmatched issues (no corresponding complete) are dropped.

        Args:
            raw_df: Raw event DataFrame from parse_raw().
            options: Converter-specific options (currently unused).

        Returns:
            Analysis-ready DataFrame sorted by issue timestamp.
        """
        logger.info("[blocklayer] converting %d raw events", len(raw_df))

        # Filter to block events only
        block_events = raw_df.filter(
            pl.col("event").is_in([
                "block_rq_insert", "block_rq_issue", "block_rq_complete",
            ])
        )
        logger.debug("[blocklayer] block events: %d (insert+issue+complete)", len(block_events))

        if len(block_events) == 0:
            logger.info("[blocklayer] no block events found, returning empty")
            return pl.DataFrame(schema=self._RESULT_SCHEMA)

        # Track per-request state: key=(dev:sector:nr_sectors)
        inserts: Dict[str, float] = {}      # key → insert timestamp
        issues: Dict[str, Dict[str, Any]] = {}  # key → issue info
        issue_order: List[Dict[str, Any]] = []
        outstanding = 0

        for row in block_events.iter_rows(named=True):
            event = row["event"]
            details = row["details"]
            ts = row["timestamp"]

            if event == "block_rq_insert":
                m = self._ISSUE_RE.match(details)
                if not m:
                    logger.debug("[blocklayer] insert parse fail: %s", details[:100])
                    continue
                key = f"{m.group('dev')}:{m.group('sector')}:{m.group('nr_sectors')}"
                inserts[key] = ts
                logger.debug("[blocklayer] insert: %s @ %.6f", key, ts)

            elif event == "block_rq_issue":
                m = self._ISSUE_RE.match(details)
                if not m:
                    logger.debug("[blocklayer] issue parse fail: %s", details[:100])
                    continue
                dev = m.group("dev")
                sector = int(m.group("sector"))
                nr_sectors = int(m.group("nr_sectors"))
                key = f"{dev}:{sector}:{nr_sectors}"

                outstanding += 1
                entry = {
                    "insert_ts": inserts.pop(key, None),  # may be None
                    "issue_ts": ts,
                    "sector": sector,
                    "nr_sectors": nr_sectors,
                    "rwbs": m.group("rwbs"),
                    "size_bytes": int(m.group("bytes")),
                    "device": dev,
                    "queue_depth": outstanding,
                    "key": key,
                }
                issues[key] = entry
                issue_order.append(entry)

            elif event == "block_rq_complete":
                m = self._COMPLETE_RE.match(details)
                if not m:
                    logger.debug("[blocklayer] complete parse fail: %s", details[:100])
                    continue
                key = f"{m.group('dev')}:{m.group('sector')}:{m.group('nr_sectors')}"

                if key in issues:
                    issues[key]["complete_ts"] = ts
                    outstanding = max(0, outstanding - 1)
                else:
                    logger.debug("[blocklayer] orphan complete: %s", key)

        # Build result from matched pairs, computing all latencies
        result_rows: List[Dict[str, Any]] = []
        prev_complete_ts: Optional[float] = None

        for entry in issue_order:
            if "complete_ts" not in entry:
                logger.debug("[blocklayer] unmatched issue: %s", entry["key"])
                continue

            issue_ts = entry["issue_ts"]
            complete_ts = entry["complete_ts"]
            insert_ts = entry.get("insert_ts")

            d2c_s = complete_ts - issue_ts
            q2c_s = (complete_ts - insert_ts) if insert_ts is not None else d2c_s

            # C2C: time since previous complete (sorted by complete_ts later)
            c2c_ms: Optional[float] = None
            if prev_complete_ts is not None:
                c2c_ms = (complete_ts - prev_complete_ts) * 1000.0
            prev_complete_ts = complete_ts

            result_rows.append({
                "timestamp": issue_ts,
                "latency_ms": d2c_s * 1000.0,  # backward compat
                "d2c_ms": d2c_s * 1000.0,
                "q2c_ms": q2c_s * 1000.0,
                "c2c_ms": c2c_ms,
                "issue_time": issue_ts,
                "complete_time": complete_ts,
                "sector": entry["sector"],
                "nr_sectors": entry["nr_sectors"],
                "rwbs": entry["rwbs"],
                "size_bytes": entry["size_bytes"],
                "device": entry["device"],
                "queue_depth": entry["queue_depth"],
            })

        matched = len(result_rows)
        total_issues = len(issue_order)
        logger.info("[blocklayer] matched %d/%d issues (%.0f%%), inserts=%d",
                    matched, total_issues,
                    (matched / total_issues * 100) if total_issues else 0,
                    sum(1 for e in issue_order if e.get("insert_ts") is not None))

        if not result_rows:
            return pl.DataFrame(schema=self._RESULT_SCHEMA)

        return pl.DataFrame(result_rows).sort("timestamp")

    # Map converter name → method
    _converters: Dict[str, Any] = {
        "blocklayer": _convert_blocklayer,
    }
