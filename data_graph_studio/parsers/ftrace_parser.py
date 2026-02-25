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
    r"\s+(?P<flags>\S{3,6})"
    r"\s+(?P<timestamp>\d+(?:\.\d+)?):"
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

    # Converter option definitions: converter name → list of option defs
    _converter_option_defs: Dict[str, list] = {
        "blocklayer": [
            {"key": "busy_queue_depth", "type": "int", "default": 32,
             "label": "Busy Queue Depth",
             "description": "Queue depth threshold to classify I/O as 'busy'"},
            {"key": "idle_queue_depth", "type": "int", "default": 4,
             "label": "Idle Queue Depth",
             "description": "Queue depth threshold to classify I/O as 'idle'"},
            {"key": "window_sec", "type": "float", "default": 1.0,
             "label": "Window (sec)",
             "description": "Sliding window size in seconds for time-based aggregation"},
            {"key": "latency_percentiles", "type": "str", "default": "50,90,99",
             "label": "Latency Percentiles",
             "description": "Comma-separated percentile values to compute (e.g. 50,90,99)"},
            {"key": "drain_target_depth", "type": "int", "default": 0,
             "label": "Drain Target Depth",
             "description": "Target queue depth for drain analysis (0 = fully drained)"},
        ],
        "sched": [],
    }

    @classmethod
    def get_option_defs(cls, converter: str) -> list:
        """Return option definitions for a converter."""
        return cls._converter_option_defs.get(converter, [])

    @classmethod
    def get_default_options(cls, converter: str) -> Dict[str, Any]:
        """Return default converter_options dict for a converter."""
        return {d["key"]: d["default"] for d in cls.get_option_defs(converter)}

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
            # ftrace events from UI may include category prefix (e.g. "block/block_rq_issue")
            normalized_evt_filter = [
                e.split("/", 1)[-1] if "/" in e else e
                for e in evt_filter
            ]
            df = df.filter(pl.col("event").is_in(normalized_evt_filter))
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
        "send_time": pl.Float64,
        "complete_time": pl.Float64,
        "insert_time": pl.Float64,
        "lba_mb": pl.Float64,
        "d2c_ms": pl.Float64,
        "q2d_ms": pl.Float64,
        "d2d_ms": pl.Float64,
        "c2c_ms": pl.Float64,
        "size_kb": pl.Float64,
        "cmd": pl.Utf8,
        "queue_depth": pl.Int32,
        "sector": pl.Int64,
        "nr_sectors": pl.Int32,
        "device": pl.Utf8,
        "is_sequential": pl.Utf8,
    }

    def _convert_blocklayer(
        self, raw_df: pl.DataFrame, options: Dict[str, Any]
    ) -> pl.DataFrame:
        """Block layer converter — vectorized version with legacy fallback.

        Tries the fast vectorized path first; falls back to the legacy
        Python-loop implementation on error.
        """
        try:
            return self._convert_blocklayer_vectorized(raw_df, options)
        except Exception:
            logger.warning("[blocklayer] vectorized path failed, falling back to legacy",
                           exc_info=True)
            return self._convert_blocklayer_legacy(raw_df, options)

    def _convert_blocklayer_vectorized(
        self, raw_df: pl.DataFrame, options: Dict[str, Any]
    ) -> pl.DataFrame:
        """Block layer converter — polars vectorized implementation.

        Tracks the full block I/O lifecycle::

            block_rq_insert (Q) → block_rq_issue (D) → block_rq_complete (C)

        Computes d2c_ms, q2d_ms, d2d_ms, c2c_ms, queue_depth, is_sequential.
        """
        logger.info("[blocklayer-vec] converting %d raw events", len(raw_df))

        block_events = raw_df.filter(
            pl.col("event").is_in([
                "block_rq_insert", "block_rq_issue", "block_rq_complete",
            ])
        )
        if len(block_events) == 0:
            logger.info("[blocklayer-vec] no block events found, returning empty")
            return pl.DataFrame(schema=self._RESULT_SCHEMA)

        # ── 1. Split by event type ──
        issues = block_events.filter(pl.col("event") == "block_rq_issue")
        completes = block_events.filter(pl.col("event") == "block_rq_complete")
        inserts = block_events.filter(pl.col("event") == "block_rq_insert")

        if len(issues) == 0:
            return pl.DataFrame(schema=self._RESULT_SCHEMA)

        # ── 2. Parse details (vectorized regex) ──
        # issue/insert format: <dev> <rwbs> <bytes> () <sector> + <nr_sectors> [<comm>]
        issue_parse_cols = [
            pl.col("details").str.extract(r"^(\S+)\s+", 1).alias("device"),
            pl.col("details").str.extract(r"^\S+\s+(\S+)", 1).alias("rwbs"),
            pl.col("details").str.extract(r"^\S+\s+\S+\s+(\d+)", 1).cast(pl.Int64).alias("size_bytes"),
            pl.col("details").str.extract(r"\(\)\s+(\d+)", 1).cast(pl.Int64).alias("sector"),
            pl.col("details").str.extract(r"\+\s*(\d+)", 1).cast(pl.Int32).alias("nr_sectors"),
        ]
        issues = issues.with_columns(issue_parse_cols)
        issues = issues.with_columns(
            (pl.col("device") + ":" + pl.col("sector").cast(pl.Utf8) + ":" +
             pl.col("nr_sectors").cast(pl.Utf8)).alias("key")
        ).with_row_index("issue_idx")

        # complete format: <dev> <rwbs> () <sector> + <nr_sectors> [<errno>]
        completes = completes.with_columns([
            pl.col("details").str.extract(r"^(\S+)\s+", 1).alias("device"),
            pl.col("details").str.extract(r"\(\)\s+(\d+)", 1).cast(pl.Int64).alias("sector"),
            pl.col("details").str.extract(r"\+\s*(\d+)", 1).cast(pl.Int32).alias("nr_sectors"),
        ]).with_columns(
            (pl.col("device") + ":" + pl.col("sector").cast(pl.Utf8) + ":" +
             pl.col("nr_sectors").cast(pl.Utf8)).alias("key")
        )

        # ── 3. Match issue→complete (first complete after issue timestamp per key) ──
        matched = (
            issues.select(["issue_idx", "key", "timestamp"])
            .join(
                completes.select(["key", "timestamp"]).rename({"timestamp": "complete_time"}),
                on="key",
                how="left",
            )
            .filter(pl.col("complete_time") > pl.col("timestamp"))
            .group_by("issue_idx")
            .agg(pl.col("complete_time").min())
        )

        result = issues.join(matched, on="issue_idx", how="inner")

        # ── 4. Match insert→issue (Q2D) ──
        if len(inserts) > 0:
            inserts = inserts.with_columns(issue_parse_cols).with_columns(
                (pl.col("device") + ":" + pl.col("sector").cast(pl.Utf8) + ":" +
                 pl.col("nr_sectors").cast(pl.Utf8)).alias("key")
            )
            # For each issue, find the latest insert before it with the same key
            insert_matched = (
                result.select(["issue_idx", "key", "timestamp"])
                .join(
                    inserts.select(["key", "timestamp"]).rename({"timestamp": "insert_time"}),
                    on="key",
                    how="left",
                )
                .filter(pl.col("insert_time") <= pl.col("timestamp"))
                .group_by("issue_idx")
                .agg(pl.col("insert_time").max())  # latest insert before issue
            )
            result = result.join(insert_matched, on="issue_idx", how="left")
        else:
            result = result.with_columns(pl.lit(None).cast(pl.Float64).alias("insert_time"))

        # ── 5. Compute metrics ──
        result = result.with_columns([
            ((pl.col("complete_time") - pl.col("timestamp")) * 1000).alias("d2c_ms"),
            pl.when(pl.col("insert_time").is_not_null())
            .then((pl.col("timestamp") - pl.col("insert_time")) * 1000)
            .otherwise(None)
            .alias("q2d_ms"),
            (pl.col("sector").cast(pl.Float64) * 512 / (1024 * 1024)).alias("lba_mb"),
            (pl.col("size_bytes").cast(pl.Float64) / 1024).alias("size_kb"),
        ])

        # Sort by issue timestamp for D2D/C2C/queue_depth/sequentiality
        result = result.sort("timestamp")

        # D2D, C2C via shift
        result = result.with_columns([
            ((pl.col("timestamp") - pl.col("timestamp").shift(1)) * 1000).alias("d2d_ms"),
            ((pl.col("complete_time") - pl.col("complete_time").shift(1)) * 1000).alias("c2c_ms"),
        ])

        # Queue depth: cumulative issues up to this point minus cumulative completes
        # We compute it by counting how many issues occurred before each issue
        # that haven't completed yet (complete_time > current issue timestamp).
        # For efficiency, use the same approach as legacy: sequential counter.
        # This requires a Python loop but only over the result (matched pairs), not raw events.
        n = len(result)
        queue_depths = [0] * n
        issue_times = result["timestamp"].to_list()
        complete_times = result["complete_time"].to_list()
        outstanding = 0
        complete_idx = 0
        # Sort complete times for sweep
        all_completes_sorted = sorted(complete_times)

        # Simple approach: at each issue, outstanding = issues_so_far - completes_before_issue
        for i in range(n):
            while complete_idx < len(all_completes_sorted) and all_completes_sorted[complete_idx] <= issue_times[i]:
                outstanding -= 1
                complete_idx += 1
            outstanding += 1
            queue_depths[i] = outstanding

        result = result.with_columns(pl.Series("queue_depth", queue_depths, dtype=pl.Int32))

        # Is_sequential: per-device, sector == prev_sector + prev_nr_sectors
        devices = result["device"].to_list()
        sectors = result["sector"].to_list()
        nr_sectors_list = result["nr_sectors"].to_list()
        prev_lba_end: Dict[str, int] = {}
        seq_flags = []
        for i in range(n):
            dev = devices[i]
            sec = sectors[i]
            if dev in prev_lba_end and sec == prev_lba_end[dev]:
                seq_flags.append("sequential")
            else:
                seq_flags.append("random")
            prev_lba_end[dev] = sec + nr_sectors_list[i]

        result = result.with_columns(pl.Series("is_sequential", seq_flags, dtype=pl.Utf8))

        # ── 6. Select final columns ──
        result = result.select([
            pl.col("timestamp").alias("send_time"),
            "complete_time",
            "insert_time",
            "lba_mb",
            "d2c_ms",
            "q2d_ms",
            "d2d_ms",
            "c2c_ms",
            "size_kb",
            pl.col("rwbs").alias("cmd"),
            "queue_depth",
            "sector",
            "nr_sectors",
            "device",
            "is_sequential",
        ])

        logger.info("[blocklayer-vec] result: %d rows", len(result))
        return result

    def _convert_blocklayer_legacy(
        self, raw_df: pl.DataFrame, options: Dict[str, Any]
    ) -> pl.DataFrame:
        """Block layer converter — legacy Python-loop implementation.

        Kept as fallback for the vectorized version.
        """
        logger.info("[blocklayer-legacy] converting %d raw events", len(raw_df))

        block_events = raw_df.filter(
            pl.col("event").is_in([
                "block_rq_insert", "block_rq_issue", "block_rq_complete",
            ])
        )

        if len(block_events) == 0:
            return pl.DataFrame(schema=self._RESULT_SCHEMA)

        issues: Dict[str, Dict[str, Any]] = {}
        inserts: Dict[str, float] = {}  # key → insert timestamp
        issue_order: List[Dict[str, Any]] = []
        outstanding = 0

        for row in block_events.iter_rows(named=True):
            event = row["event"]
            details = row["details"]
            ts = row["timestamp"]

            if event == "block_rq_insert":
                m = self._ISSUE_RE.match(details)
                if not m:
                    continue
                key = f"{m.group('dev')}:{m.group('sector')}:{m.group('nr_sectors')}"
                inserts[key] = ts

            elif event == "block_rq_issue":
                m = self._ISSUE_RE.match(details)
                if not m:
                    continue
                dev = m.group("dev")
                sector = int(m.group("sector"))
                nr_sectors = int(m.group("nr_sectors"))
                key = f"{dev}:{sector}:{nr_sectors}"

                outstanding += 1
                entry: Dict[str, Any] = {
                    "issue_ts": ts,
                    "sector": sector,
                    "nr_sectors": nr_sectors,
                    "rwbs": m.group("rwbs"),
                    "size_bytes": int(m.group("bytes")),
                    "device": dev,
                    "queue_depth": outstanding,
                    "key": key,
                }
                if key in inserts:
                    entry["insert_ts"] = inserts.pop(key)
                issues[key] = entry
                issue_order.append(entry)

            elif event == "block_rq_complete":
                m = self._COMPLETE_RE.match(details)
                if not m:
                    continue
                key = f"{m.group('dev')}:{m.group('sector')}:{m.group('nr_sectors')}"
                if key in issues:
                    issues[key]["complete_ts"] = ts
                    outstanding = max(0, outstanding - 1)

        result_rows: List[Dict[str, Any]] = []
        prev_complete_ts: Optional[float] = None
        prev_issue_ts: Optional[float] = None
        prev_lba_end: Dict[str, int] = {}

        for entry in issue_order:
            if "complete_ts" not in entry:
                continue

            issue_ts = entry["issue_ts"]
            complete_ts = entry["complete_ts"]

            d2d_ms: Optional[float] = None
            if prev_issue_ts is not None:
                d2d_ms = (issue_ts - prev_issue_ts) * 1000.0
            prev_issue_ts = issue_ts

            c2c_ms: Optional[float] = None
            if prev_complete_ts is not None:
                c2c_ms = (complete_ts - prev_complete_ts) * 1000.0
            prev_complete_ts = complete_ts

            sector = entry["sector"]
            nr_sects = entry["nr_sectors"]
            dev = entry["device"]

            if dev in prev_lba_end and sector == prev_lba_end[dev]:
                is_seq = "sequential"
            else:
                is_seq = "random"
            prev_lba_end[dev] = sector + nr_sects

            insert_ts = entry.get("insert_ts")
            q2d_ms: Optional[float] = None
            if insert_ts is not None:
                q2d_ms = (issue_ts - insert_ts) * 1000.0

            result_rows.append({
                "send_time": issue_ts,
                "complete_time": complete_ts,
                "insert_time": insert_ts,
                "lba_mb": sector * 512.0 / (1024.0 * 1024.0),
                "d2c_ms": (complete_ts - issue_ts) * 1000.0,
                "q2d_ms": q2d_ms,
                "d2d_ms": d2d_ms,
                "c2c_ms": c2c_ms,
                "size_kb": entry["size_bytes"] / 1024.0,
                "cmd": entry["rwbs"],
                "queue_depth": entry["queue_depth"],
                "sector": sector,
                "nr_sectors": nr_sects,
                "device": dev,
                "is_sequential": is_seq,
            })

        if not result_rows:
            return pl.DataFrame(schema=self._RESULT_SCHEMA)

        return pl.DataFrame(result_rows).sort("send_time")

    # ------------------------------------------------------------------
    # Sched converter
    # ------------------------------------------------------------------

    _SCHED_SCHEMA = {
        "timestamp": pl.Float64,
        "cpu": pl.Int32,
        "event_type": pl.Utf8,
        "prev_comm": pl.Utf8,
        "prev_pid": pl.Int32,
        "prev_state": pl.Utf8,
        "next_comm": pl.Utf8,
        "next_pid": pl.Int32,
        "runtime_ms": pl.Float64,
        "wait_time_ms": pl.Float64,
    }

    _SWITCH_RE = r"prev_comm=(.+?)\s+prev_pid=(\d+)\s+prev_prio=\d+\s+prev_state=(\S+)\s+==>\s+next_comm=(.+?)\s+next_pid=(\d+)"
    _WAKEUP_RE = r"comm=(.+?)\s+pid=(\d+)"

    def _convert_sched(
        self, raw_df: pl.DataFrame, options: Dict[str, Any]
    ) -> pl.DataFrame:
        """Scheduler converter — parses sched_switch/wakeup/waking events.

        Computes:
        - **runtime_ms**: per-CPU time between consecutive context switches
        - **wait_time_ms**: wakeup-to-switch latency (TODO: complex matching)

        Args:
            raw_df: Raw event DataFrame from parse_raw().
            options: Converter-specific options (currently unused).

        Returns:
            Analysis-ready DataFrame sorted by timestamp.
        """
        logger.info("[sched] converting %d raw events", len(raw_df))

        sched_events = raw_df.filter(
            pl.col("event").is_in(["sched_switch", "sched_wakeup", "sched_waking"])
        )
        logger.debug("[sched] sched events: %d", len(sched_events))

        if len(sched_events) == 0:
            logger.info("[sched] no sched events found, returning empty")
            return pl.DataFrame(schema=self._SCHED_SCHEMA)

        # --- sched_switch parsing ---
        switches = sched_events.filter(pl.col("event") == "sched_switch")

        if len(switches) == 0:
            logger.info("[sched] no sched_switch events, returning empty")
            return pl.DataFrame(schema=self._SCHED_SCHEMA)

        switches = switches.with_columns([
            pl.lit("switch").alias("event_type"),
            pl.col("details").str.extract(self._SWITCH_RE, 1).alias("prev_comm"),
            pl.col("details").str.extract(self._SWITCH_RE, 2).cast(pl.Int32).alias("prev_pid"),
            pl.col("details").str.extract(self._SWITCH_RE, 3).alias("prev_state"),
            pl.col("details").str.extract(self._SWITCH_RE, 4).alias("next_comm"),
            pl.col("details").str.extract(self._SWITCH_RE, 5).cast(pl.Int32).alias("next_pid"),
        ])

        # runtime: per-CPU consecutive switch time delta
        switches = switches.sort(["cpu", "timestamp"])
        switches = switches.with_columns([
            (
                (pl.col("timestamp") - pl.col("timestamp").shift(1).over("cpu")) * 1000.0
            ).alias("runtime_ms"),
        ])

        # TODO: wait_time_ms — wakeup→switch matching (complex pid-based join)
        switches = switches.with_columns([
            pl.lit(None, dtype=pl.Float64).alias("wait_time_ms"),
        ])

        result = switches.select([
            "timestamp", "cpu", "event_type",
            "prev_comm", "prev_pid", "prev_state",
            "next_comm", "next_pid",
            "runtime_ms", "wait_time_ms",
        ])

        matched = len(result)
        logger.info("[sched] produced %d switch records", matched)
        return result.sort("timestamp")

    # Map converter name → method
    _converters: Dict[str, Any] = {
        "blocklayer": _convert_blocklayer,
        "sched": _convert_sched,
    }
