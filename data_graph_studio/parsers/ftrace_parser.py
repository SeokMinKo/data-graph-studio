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
        """Return the default parsing and conversion settings for ftrace files."""
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
        "send_time": pl.Float64,
        "complete_time": pl.Float64,
        "insert_time": pl.Float64,
        "lba_mb": pl.Float64,
        "d2c_ms": pl.Float64,
        "q2d_ms": pl.Float64,
        "d2d_ms": pl.Float64,
        "c2c_ms": pl.Float64,
        "idle_time_ms": pl.Float64,
        "busy_time_ms": pl.Float64,
        "iops": pl.Float64,
        "bw_mbps": pl.Float64,
        "rw_ratio": pl.Float64,
        "seq_run_length": pl.Int32,
        "latency_tier": pl.Utf8,
        "drain_time_ms": pl.Float64,
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

        Computes d2c_ms, q2d_ms, d2d_ms, c2c_ms, queue_depth, is_sequential,
        iops, bw_mbps, rw_ratio, seq_run_length, latency_tier, drain_time_ms,
        idle_time_ms, busy_time_ms.

        Configurable thresholds via ``options["converter_options"]``:

        - ``busy_queue_depth`` (int, default 63): Queue depth threshold for busy time.
          When observed max Q < this value, max Q is used instead.
        - ``idle_queue_depth`` (int, default 1): Queue depth at/below which device
          is considered idle. Idle time = prev_complete → current dispatch gap.
        - ``window_sec`` (float, default 0.1): Rolling window size in seconds for
          IOPS, bandwidth, and R/W ratio calculations.
        - ``latency_percentiles`` (list[float], default [95, 99]): Percentile thresholds
          for latency tier classification.  First value = P95 boundary, second = P99.
        - ``drain_target_depth`` (int, default 1): Queue depth that marks the end
          of a drain event.

        Example::

            settings["converter_options"] = {
                "busy_queue_depth": 32,
                "window_sec": 0.05,
                "latency_percentiles": [90, 99],
            }
        """
        logger.info("[blocklayer-vec] converting %d raw events", len(raw_df))

        copts = options.get("converter_options", {})
        cfg_busy_qd = int(copts.get("busy_queue_depth", 63))
        cfg_idle_qd = int(copts.get("idle_queue_depth", 1))
        cfg_window_sec = float(copts.get("window_sec", 0.1))
        cfg_latency_pcts = list(copts.get("latency_percentiles", [95, 99]))
        cfg_drain_target = int(copts.get("drain_target_depth", 1))
        if len(cfg_latency_pcts) < 2:
            cfg_latency_pcts = [95, 99]

        block_events = raw_df.filter(
            pl.col("event").is_in([
                "block_rq_insert", "block_rq_issue", "block_rq_complete",
            ])
        )
        if len(block_events) == 0:
            logger.info("[blocklayer-vec] no block events found, returning empty")
            return pl.DataFrame(schema=self._RESULT_SCHEMA)

        issues = block_events.filter(pl.col("event") == "block_rq_issue")
        completes = block_events.filter(pl.col("event") == "block_rq_complete")
        inserts = block_events.filter(pl.col("event") == "block_rq_insert")

        if len(issues) == 0:
            return pl.DataFrame(schema=self._RESULT_SCHEMA)

        # Parse + match events
        issues, completes, inserts = self._blk_parse_details(issues, completes, inserts)
        result = self._blk_match_events(issues, completes, inserts)

        # Core derived columns
        result = result.with_columns([
            ((pl.col("complete_time") - pl.col("timestamp")) * 1000).alias("d2c_ms"),
            pl.when(pl.col("insert_time").is_not_null())
            .then((pl.col("timestamp") - pl.col("insert_time")) * 1000)
            .otherwise(None)
            .alias("q2d_ms"),
            (pl.col("sector").cast(pl.Float64) * 512 / (1024 * 1024)).alias("lba_mb"),
            (pl.col("size_bytes").cast(pl.Float64) / 1024).alias("size_kb"),
        ])
        result = result.sort("timestamp")
        result = result.with_columns([
            ((pl.col("timestamp") - pl.col("timestamp").shift(1)) * 1000).alias("d2d_ms"),
            ((pl.col("complete_time") - pl.col("complete_time").shift(1)) * 1000).alias("c2c_ms"),
        ])

        # Queue depth and utilization metrics
        result, queue_depths = self._blk_compute_queue_metrics(
            result, cfg_busy_qd, cfg_idle_qd
        )

        # Sequentiality
        result, seq_flags = self._blk_compute_sequentiality(result)

        # Windowed IOPS / bandwidth / rw_ratio + run length + latency tier + drain
        result = self._blk_compute_windowed_metrics(
            result, seq_flags, queue_depths, cfg_window_sec, cfg_latency_pcts, cfg_drain_target
        )

        result = result.select([
            pl.col("timestamp").alias("send_time"),
            "complete_time", "insert_time", "lba_mb",
            "d2c_ms", "q2d_ms", "d2d_ms", "c2c_ms",
            "idle_time_ms", "busy_time_ms",
            "iops", "bw_mbps", "rw_ratio",
            "seq_run_length", "latency_tier", "drain_time_ms",
            "size_kb", pl.col("rwbs").alias("cmd"),
            "queue_depth", "sector", "nr_sectors", "device", "is_sequential",
        ])
        logger.info("[blocklayer-vec] result: %d rows", len(result))
        return result

    @staticmethod
    def _blk_detail_parse_cols(is_perfetto_fmt: bool, complete: bool = False) -> list:
        """Return polars expressions to parse block event detail fields."""
        if is_perfetto_fmt:
            cols = [
                pl.col("details").str.extract(r"(?:^|\s)dev=([^\s]+)", 1).alias("device"),
                pl.col("details").str.extract(r"(?:^|\s)sector=(\d+)\b", 1).cast(pl.Int64).alias("sector"),
                pl.col("details").str.extract(r"(?:^|\s)nr_sector=(\d+)\b", 1).cast(pl.Int32).alias("nr_sectors"),
            ]
            if not complete:
                cols += [
                    pl.col("details").str.extract(r"(?:^|\s)rwbs=([^\s]+)", 1).alias("rwbs"),
                    pl.col("details").str.extract(r"(?:^|\s)bytes=(\d+)\b", 1).cast(pl.Int64).alias("size_bytes"),
                ]
        else:
            cols = [
                pl.col("details").str.extract(r"^(\S+)\s+", 1).alias("device"),
                pl.col("details").str.extract(r"\(\)\s+(\d+)", 1).cast(pl.Int64).alias("sector"),
                pl.col("details").str.extract(r"\+\s*(\d+)", 1).cast(pl.Int32).alias("nr_sectors"),
            ]
            if not complete:
                cols += [
                    pl.col("details").str.extract(r"^\S+\s+(\S+)", 1).alias("rwbs"),
                    pl.col("details").str.extract(r"^\S+\s+\S+\s+(\d+)", 1).cast(pl.Int64).alias("size_bytes"),
                ]
        return cols

    @staticmethod
    def _blk_add_key(df: pl.DataFrame) -> pl.DataFrame:
        """Add a device:sector:nr_sectors join key column."""
        return df.with_columns(
            (pl.col("device") + ":" + pl.col("sector").cast(pl.Utf8) + ":" +
             pl.col("nr_sectors").cast(pl.Utf8)).alias("key")
        )

    def _blk_parse_details(
        self,
        issues: pl.DataFrame,
        completes: pl.DataFrame,
        inserts: pl.DataFrame,
    ):
        """Parse the 'details' field for all three event types, add join keys."""
        sample_detail = issues["details"].drop_nulls().head(1).to_list()
        is_perfetto_fmt = bool(sample_detail and "dev=" in sample_detail[0])
        logger.debug("ftrace_parser.detail_format", extra={"format": "perfetto" if is_perfetto_fmt else "raw"})

        issue_cols = self._blk_detail_parse_cols(is_perfetto_fmt, complete=False)
        complete_cols = self._blk_detail_parse_cols(is_perfetto_fmt, complete=True)

        issues = self._blk_add_key(issues.with_columns(issue_cols)).with_row_index("issue_idx")
        completes = self._blk_add_key(completes.with_columns(complete_cols))
        if len(inserts) > 0:
            inserts = self._blk_add_key(inserts.with_columns(issue_cols))
        return issues, completes, inserts

    @staticmethod
    def _blk_match_events(
        issues: pl.DataFrame,
        completes: pl.DataFrame,
        inserts: pl.DataFrame,
    ) -> pl.DataFrame:
        """Join issues to their first matching complete and latest matching insert."""
        # issue → complete (first complete after issue timestamp per key)
        matched = (
            issues.select(["issue_idx", "key", "timestamp"])
            .join(
                completes.select(["key", "timestamp"]).rename({"timestamp": "complete_time"}),
                on="key", how="left",
            )
            .filter(pl.col("complete_time") > pl.col("timestamp"))
            .group_by("issue_idx")
            .agg(pl.col("complete_time").min())
        )
        result = issues.join(matched, on="issue_idx", how="inner")

        # insert → issue (latest insert before issue timestamp per key)
        if len(inserts) > 0:
            insert_matched = (
                result.select(["issue_idx", "key", "timestamp"])
                .join(
                    inserts.select(["key", "timestamp"]).rename({"timestamp": "insert_time"}),
                    on="key", how="left",
                )
                .filter(pl.col("insert_time") <= pl.col("timestamp"))
                .group_by("issue_idx")
                .agg(pl.col("insert_time").max())
            )
            result = result.join(insert_matched, on="issue_idx", how="left")
        else:
            result = result.with_columns(pl.lit(None).cast(pl.Float64).alias("insert_time"))
        return result

    @staticmethod
    def _blk_compute_queue_metrics(
        result: pl.DataFrame, cfg_busy_qd: int, cfg_idle_qd: int
    ):
        """Compute queue_depth, idle_time_ms, busy_time_ms via Python sweep."""
        n = len(result)
        issue_times = result["timestamp"].to_list()
        complete_times = result["complete_time"].to_list()

        # Queue depth sweep
        queue_depths = [0] * n
        outstanding = 0
        complete_idx = 0
        all_completes_sorted = sorted(complete_times)
        for i in range(n):
            while (complete_idx < len(all_completes_sorted)
                   and all_completes_sorted[complete_idx] <= issue_times[i]):
                outstanding -= 1
                complete_idx += 1
            outstanding += 1
            queue_depths[i] = outstanding

        result = result.with_columns(pl.Series("queue_depth", queue_depths, dtype=pl.Int32))

        # Idle / busy time
        max_q = max(queue_depths) if queue_depths else 0
        busy_threshold = min(cfg_busy_qd, max(max_q, 1))
        idle_times: list = [None] * n
        busy_times: list = [None] * n
        for i in range(1, n):
            prev_ct = complete_times[i - 1]
            if queue_depths[i] <= cfg_idle_qd and (i == 1 or queue_depths[i - 1] <= cfg_idle_qd):
                gap = (issue_times[i] - prev_ct) * 1000
                if gap >= 0:
                    idle_times[i] = gap
            if queue_depths[i] >= busy_threshold:
                gap = (complete_times[i] - prev_ct) * 1000
                if gap >= 0:
                    busy_times[i] = gap

        result = result.with_columns([
            pl.Series("idle_time_ms", idle_times, dtype=pl.Float64),
            pl.Series("busy_time_ms", busy_times, dtype=pl.Float64),
        ])
        return result, queue_depths

    @staticmethod
    def _blk_compute_sequentiality(result: pl.DataFrame):
        """Compute per-device sequentiality flag. Returns (updated_result, seq_flags)."""
        devices = result["device"].to_list()
        sectors = result["sector"].to_list()
        nr_sectors_list = result["nr_sectors"].to_list()
        prev_lba_end: Dict[str, int] = {}
        seq_flags = []
        for i in range(len(result)):
            dev = devices[i]
            sec = sectors[i]
            seq_flags.append("sequential" if (dev in prev_lba_end and sec == prev_lba_end[dev]) else "random")
            prev_lba_end[dev] = sec + nr_sectors_list[i]
        result = result.with_columns(pl.Series("is_sequential", seq_flags, dtype=pl.Utf8))
        return result, seq_flags

    @staticmethod
    def _blk_compute_windowed_metrics(
        result: pl.DataFrame,
        seq_flags: list,
        queue_depths: list,
        cfg_window_sec: float,
        cfg_latency_pcts: list,
        cfg_drain_target: int,
    ) -> pl.DataFrame:
        """Compute IOPS, bw_mbps, rw_ratio, seq_run_length, latency_tier, drain_time_ms."""
        n = len(result)
        timestamps = result["timestamp"].to_list()
        size_kb_list = result["size_kb"].to_list()
        rwbs_list = result["rwbs"].to_list()
        complete_times = result["complete_time"].to_list()

        # IOPS, bandwidth, rw_ratio (rolling window)
        iops_list = [0.0] * n
        bw_mbps_list = [0.0] * n
        rw_ratio_list: list = [None] * n
        for i in range(n):
            t_center = timestamps[i]
            t_start = t_center - cfg_window_sec / 2
            t_end = t_center + cfg_window_sec / 2
            count = 0
            total_kb = 0.0
            reads = 0
            writes = 0
            for j in range(n):
                if t_start <= timestamps[j] <= t_end:
                    count += 1
                    total_kb += size_kb_list[j] if size_kb_list[j] else 0
                    if rwbs_list[j] and 'R' in rwbs_list[j]:
                        reads += 1
                    elif rwbs_list[j] and 'W' in rwbs_list[j]:
                        writes += 1
            iops_list[i] = count / cfg_window_sec
            bw_mbps_list[i] = (total_kb / 1024) / cfg_window_sec
            total_rw = reads + writes
            if total_rw > 0:
                rw_ratio_list[i] = reads / total_rw

        result = result.with_columns([
            pl.Series("iops", iops_list, dtype=pl.Float64),
            pl.Series("bw_mbps", bw_mbps_list, dtype=pl.Float64),
            pl.Series("rw_ratio", rw_ratio_list, dtype=pl.Float64),
        ])

        # Sequential run length
        seq_run_lengths = [0] * n
        current_run = 0
        for i in range(n):
            current_run = current_run + 1 if seq_flags[i] == "sequential" else 0
            seq_run_lengths[i] = current_run
        result = result.with_columns(pl.Series("seq_run_length", seq_run_lengths, dtype=pl.Int32))

        # Latency tier
        pct_low, pct_high = float(cfg_latency_pcts[0]), float(cfg_latency_pcts[1])
        d2c_vals = result["d2c_ms"].drop_nulls().to_numpy()
        if len(d2c_vals) > 0:
            import numpy as _np
            p_high = float(_np.percentile(d2c_vals, pct_high))
            p_low = float(_np.percentile(d2c_vals, pct_low))
            result = result.with_columns(
                pl.when(pl.col("d2c_ms") >= p_high).then(pl.lit(f"P{int(pct_high)}+"))
                .when(pl.col("d2c_ms") >= p_low).then(pl.lit(f"P{int(pct_low)}-P{int(pct_high)}"))
                .otherwise(pl.lit("normal"))
                .alias("latency_tier")
            )
        else:
            result = result.with_columns(pl.lit("normal").alias("latency_tier"))

        # Queue drain time
        max_q = max(queue_depths) if queue_depths else 0
        drain_times: list = [None] * n
        if max_q > cfg_drain_target:
            in_drain = False
            drain_start_time = 0.0
            for i in range(n):
                if queue_depths[i] >= max_q and not in_drain:
                    in_drain = True
                    drain_start_time = complete_times[i]
                elif in_drain and queue_depths[i] <= cfg_drain_target:
                    drain_times[i] = (complete_times[i] - drain_start_time) * 1000
                    in_drain = False
        result = result.with_columns(pl.Series("drain_time_ms", drain_times, dtype=pl.Float64))
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
