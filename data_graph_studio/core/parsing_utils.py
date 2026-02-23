"""
Parsing utilities for preview/full loading.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

from .data_engine import FileType, DelimiterType
from .parsing import ParsingSettings


class ParsingEngine:
    """Parsing utility engine."""

    @staticmethod
    def detect_encoding(file_path: str) -> str:
        """Detect file encoding (best-effort)."""
        with open(file_path, "rb") as f:
            raw = f.read(32768)

        encoding = None
        try:
            from charset_normalizer import from_bytes

            result = from_bytes(raw).best()
            if result is not None:
                encoding = result.encoding
        except Exception:
            logger.debug("parsing_utils.detect_encoding.charset_normalizer_failed", exc_info=True)
            encoding = None

        if not encoding:
            try:
                import chardet  # type: ignore

                result = chardet.detect(raw)
                encoding = result.get("encoding")
            except Exception:
                logger.debug("parsing_utils.detect_encoding.chardet_failed", exc_info=True)
                encoding = None

        if not encoding:
            encoding = "utf-8"

        normalized = encoding.lower().replace("_", "-")
        # ASCII is a strict subset of UTF-8; for our purposes treat it as UTF-8
        # so that UTF-8 files containing only ASCII characters are handled consistently.
        if normalized in ("ascii", "us-ascii"):
            normalized = "utf-8"

        return normalized

    @staticmethod
    def parse_preview(settings: ParsingSettings, max_rows: int = 100) -> pd.DataFrame:
        """Parse up to max_rows rows from the file described by settings."""
        return ParsingEngine._parse_file(settings, max_rows=max_rows)

    @staticmethod
    def parse_full(settings: ParsingSettings) -> pd.DataFrame:
        """Parse the entire file described by settings and return a DataFrame."""
        return ParsingEngine._parse_file(settings, max_rows=None)

    @staticmethod
    def _parse_file(settings: ParsingSettings, max_rows: Optional[int]) -> pd.DataFrame:
        if settings.file_type == FileType.EXCEL:
            df = pd.read_excel(
                settings.file_path,
                sheet_name=settings.sheet_name,
                nrows=max_rows,
            )
            return ParsingEngine._post_process(df, settings)

        if settings.file_type == FileType.PARQUET:
            df = pd.read_parquet(settings.file_path)
            if max_rows is not None:
                df = df.head(max_rows)
            return ParsingEngine._post_process(df, settings)

        if settings.file_type == FileType.JSON:
            df = pd.read_json(settings.file_path)
            if max_rows is not None:
                df = df.head(max_rows)
            return ParsingEngine._post_process(df, settings)

        # Default: delimited text (CSV/TSV/TXT/ETL)
        df = ParsingEngine._parse_delimited(settings, max_rows=max_rows)
        return ParsingEngine._post_process(df, settings)

    @staticmethod
    def _post_process(df: pd.DataFrame, settings: ParsingSettings) -> pd.DataFrame:
        if settings.excluded_columns:
            drop_cols = [c for c in settings.excluded_columns if c in df.columns]
            if drop_cols:
                df = df.drop(columns=drop_cols)

        if settings.etl_selected_processes:
            process_cols = [c for c in df.columns if "process" in str(c).lower()]
            if process_cols:
                df = df[df[process_cols[0]].isin(settings.etl_selected_processes)]

        return df

    @staticmethod
    def _parse_delimited(settings: ParsingSettings, max_rows: Optional[int]) -> pd.DataFrame:
        delimiter, delimiter_type = ParsingEngine._resolve_delimiter(settings)
        rows = ParsingEngine._read_rows(
            settings,
            delimiter=delimiter,
            delimiter_type=delimiter_type,
            max_rows=max_rows,
        )

        if not rows:
            return pd.DataFrame()

        if settings.has_header:
            headers = rows[0]
            data = rows[1:]
        else:
            max_cols = max(len(r) for r in rows)
            headers = [f"Column {i + 1}" for i in range(max_cols)]
            data = rows

        max_cols = len(headers)
        normalized = []
        for row in data:
            if len(row) < max_cols:
                row = row + [""] * (max_cols - len(row))
            elif len(row) > max_cols:
                row = row[:max_cols]
            normalized.append(row)

        return pd.DataFrame(normalized, columns=headers)

    @staticmethod
    def _resolve_delimiter(settings: ParsingSettings) -> Tuple[str, DelimiterType]:
        delimiter = settings.delimiter
        delimiter_type = settings.delimiter_type

        if delimiter_type == DelimiterType.AUTO:
            sample_lines = ParsingEngine._sample_lines(settings, max_lines=10)
            delimiter = ParsingEngine._detect_delimiter_auto(sample_lines)
            type_map = {
                ",": DelimiterType.COMMA,
                "\t": DelimiterType.TAB,
                ";": DelimiterType.SEMICOLON,
                "|": DelimiterType.PIPE,
                " ": DelimiterType.SPACE,
            }
            delimiter_type = type_map.get(delimiter, DelimiterType.COMMA)

        return delimiter, delimiter_type

    @staticmethod
    def _sample_lines(settings: ParsingSettings, max_lines: int = 10) -> List[str]:
        lines: List[str] = []
        skip_rows = settings.skip_rows
        comment_char = settings.comment_char

        with open(settings.file_path, "r", encoding=settings.encoding, errors="replace") as f:
            for line in f:
                if skip_rows > 0:
                    skip_rows -= 1
                    continue
                line = line.rstrip("\n\r")
                if comment_char and line.strip().startswith(comment_char):
                    continue
                if not line.strip():
                    continue
                lines.append(line)
                if len(lines) >= max_lines:
                    break

        return lines

    @staticmethod
    def _detect_delimiter_auto(lines: Iterable[str]) -> str:
        if not lines:
            return ","

        delimiters = [",", "\t", ";", "|"]
        counts = {d: 0 for d in delimiters}
        for line in list(lines)[:10]:
            for d in delimiters:
                counts[d] += line.count(d)

        best = max(counts, key=counts.get)
        if counts[best] == 0:
            return " "
        return best

    @staticmethod
    def _read_rows(
        settings: ParsingSettings,
        delimiter: str,
        delimiter_type: DelimiterType,
        max_rows: Optional[int],
    ) -> List[List[str]]:
        rows: List[List[str]] = []
        skip_rows = settings.skip_rows
        comment_char = settings.comment_char

        if max_rows is not None:
            target_rows = max_rows + (1 if settings.has_header else 0)
        else:
            target_rows = None

        with open(settings.file_path, "r", encoding=settings.encoding, errors="replace") as f:
            for line in f:
                if skip_rows > 0:
                    skip_rows -= 1
                    continue
                line = line.rstrip("\n\r")
                if comment_char and line.strip().startswith(comment_char):
                    continue
                if not line.strip():
                    continue

                fields = ParsingEngine._split_line(
                    line=line,
                    delimiter=delimiter,
                    delimiter_type=delimiter_type,
                    regex_pattern=settings.regex_pattern,
                )
                rows.append([field.strip() for field in fields])

                if target_rows is not None and len(rows) >= target_rows:
                    break

        return rows

    @staticmethod
    def _split_line(
        line: str,
        delimiter: str,
        delimiter_type: DelimiterType,
        regex_pattern: str,
    ) -> List[str]:
        if delimiter_type == DelimiterType.REGEX and regex_pattern:
            try:
                return re.split(regex_pattern, line)
            except re.error:
                return [line]
        if delimiter_type == DelimiterType.SPACE or delimiter == " ":
            return line.split()
        return line.split(delimiter)
