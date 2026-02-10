"""Ftrace log parser — 2-step pipeline.

Step 1 (parse_raw): raw ftrace text → structured event DataFrame
Step 2 (convert):   event DataFrame → analysis-ready DataFrame
                    (e.g. block layer: send/complete → latency, queue depth)

고돌이 기존 코드를 여기에 넣을 예정.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import polars as pl

from .base import BaseParser

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

    def _convert_blocklayer(
        self, raw_df: pl.DataFrame, options: Dict[str, Any]
    ) -> pl.DataFrame:
        """Block layer converter.

        Matches send/complete pairs → computes latency, queue depth, etc.

        TODO: 고돌 기존 코드 여기에

        Args:
            raw_df: Raw event DataFrame.
            options: Converter-specific options.

        Returns:
            DataFrame with latency, queue depth columns.
        """
        raise NotImplementedError(
            "blocklayer converter not yet implemented."
        )

    # Map converter name → method
    _converters: Dict[str, Any] = {
        "blocklayer": _convert_blocklayer,
    }
