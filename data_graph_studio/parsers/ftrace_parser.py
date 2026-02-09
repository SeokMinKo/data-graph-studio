"""Ftrace log parser — 2-step pipeline.

Step 1 (parse_raw): raw ftrace text → structured event DataFrame
Step 2 (convert):   event DataFrame → analysis-ready DataFrame
                    (e.g. block layer: send/complete → latency, queue depth)

고돌이 기존 코드를 여기에 넣을 예정.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import polars as pl

from .base import BaseParser


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
        """Parse raw ftrace text into structured event DataFrame.

        TODO: 고돌 구현 예정

        Expected output columns:
          - timestamp (f64): seconds
          - cpu (i32): CPU number
          - task (str): task/process name
          - pid (i32): process ID
          - event (str): event name (e.g. "block_rq_issue", "block_rq_complete")
          - details (str): raw event arguments

        Args:
            file_path: Path to ftrace log file.
            settings: Parser settings dict.

        Returns:
            Raw event DataFrame.
        """
        raise NotImplementedError(
            "parse_raw() not yet implemented. "
            "Add ftrace text parsing logic here."
        )

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
