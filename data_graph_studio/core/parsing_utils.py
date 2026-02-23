"""parsing_utils — encoding detection and delimited-text parsing for preview and full load.

Provides ParsingEngine, a collection of static methods that read files described
by a ParsingSettings instance and return pandas DataFrames. Used by the preview
panel and the initial file-load pipeline before data is handed to Polars.
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
    """Static utility engine for file encoding detection and tabular parsing.

    All methods are @staticmethod. No instance state is required or maintained.
    The primary public entry points are detect_encoding, parse_preview, and
    parse_full. Internal helpers (_parse_file, _parse_delimited, etc.) are
    called transitively.
    """

    @staticmethod
    def detect_encoding(file_path: str) -> str:
        """Detect the character encoding of a file and return a normalized encoding string.

        Reads up to 32 KB from the file and tries charset_normalizer first,
        then chardet as a fallback. Falls back to "utf-8" when both libraries
        fail or return no result. ASCII/US-ASCII is remapped to "utf-8" because
        ASCII is a strict subset and this avoids inconsistency for files that
        happen to contain only ASCII characters.

        Input: file_path — str, path to the file to inspect; must be readable
        Output: str — lowercase, dash-normalized encoding name (e.g. "utf-8",
            "cp949", "latin-1")
        Invariants: never returns None; always returns a non-empty string
        """
        with open(file_path, "rb") as f:
            raw = f.read(32768)

        encoding = None
        try:
            from charset_normalizer import from_bytes

            result = from_bytes(raw).best()
            if result is not None:
                encoding = result.encoding
        except (ImportError, ValueError, SyntaxError, TypeError):
            logger.debug("parsing_utils.detect_encoding.charset_normalizer_failed", exc_info=True)
            encoding = None

        if not encoding:
            try:
                import chardet  # type: ignore

                result = chardet.detect(raw)
                encoding = result.get("encoding")
            except (ImportError, ValueError, SyntaxError, TypeError):
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
        """Parse up to max_rows rows from the file described by settings.

        Input:
            settings — ParsingSettings, fully configured parse parameters
            max_rows — int, upper bound on data rows returned (header excluded);
                defaults to 100; must be > 0
        Output: pd.DataFrame — at most max_rows data rows with columns from
            the header or auto-generated names
        """
        return ParsingEngine._parse_file(settings, max_rows=max_rows)

    @staticmethod
    def parse_full(settings: ParsingSettings) -> pd.DataFrame:
        """Parse the entire file described by settings and return a DataFrame.

        Input: settings — ParsingSettings, fully configured parse parameters
        Output: pd.DataFrame — all data rows in the file
        """
        return ParsingEngine._parse_file(settings, max_rows=None)

    @staticmethod
    def _parse_file(settings: ParsingSettings, max_rows: Optional[int]) -> pd.DataFrame:
        """Dispatch to the appropriate format-specific reader and post-process.

        Input:
            settings — ParsingSettings, parse configuration
            max_rows — Optional[int], row limit; None means read all rows
        Output: pd.DataFrame — parsed and post-processed result
        """
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
        """Apply column exclusion and ETL process filtering to a parsed DataFrame.

        Input:
            df — pd.DataFrame, the raw parsed result
            settings — ParsingSettings, provides excluded_columns and
                etl_selected_processes
        Output: pd.DataFrame — df with excluded columns dropped and, for ETL
            files, rows filtered to the selected process names
        Invariants: columns not present in df are silently ignored during exclusion
        """
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
        """Parse a delimited text file (CSV/TSV/TXT/ETL) row-by-row into a DataFrame.

        Resolves the delimiter (including AUTO detection), reads rows via
        _read_rows, assigns header or generates column names, and normalizes row
        widths by padding short rows and truncating long ones.

        Input:
            settings — ParsingSettings, parse configuration
            max_rows — Optional[int], data row limit; None means read all
        Output: pd.DataFrame — normalized tabular result; empty DataFrame when
            the file has no content after skipping and filtering
        """
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
        """Determine the effective delimiter and DelimiterType from settings.

        When delimiter_type is AUTO, samples up to 10 lines and runs frequency
        heuristics to pick the most common standard delimiter. Falls back to
        space when none of the candidates appear.

        Input: settings — ParsingSettings, provides delimiter, delimiter_type,
            and file parameters used for sampling
        Output: Tuple[str, DelimiterType] — resolved (delimiter_char, type) pair
        """
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
        """Read up to max_lines non-comment, non-empty lines after skipping leading rows.

        Input:
            settings — ParsingSettings, provides file_path, encoding, skip_rows,
                and comment_char
            max_lines — int, maximum number of lines to return; defaults to 10
        Output: List[str] — stripped lines suitable for delimiter detection;
            at most max_lines entries
        """
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
        """Choose the most frequent standard delimiter character from sample lines.

        Counts occurrences of comma, tab, semicolon, and pipe across up to 10
        lines. Returns space when none of the candidates appear.

        Input: lines — Iterable[str], sample lines from the file (no newlines)
        Output: str — the winning delimiter character; one of ",", "\\t", ";",
            "|", or " "
        Invariants: always returns a non-empty single-character string
        """
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
        """Read and split file lines into a list of field lists.

        Respects skip_rows, comment_char, and blank-line filtering. Counts
        the header row against target_rows when has_header is True. Fields are
        stripped of leading/trailing whitespace.

        Input:
            settings — ParsingSettings, provides file_path, encoding, skip_rows,
                comment_char, has_header, and regex_pattern
            delimiter — str, resolved delimiter character
            delimiter_type — DelimiterType, resolved interpretation mode
            max_rows — Optional[int], maximum number of data rows (not counting
                the header); None means read all
        Output: List[List[str]] — list of rows; first entry is the header row
            when has_header is True
        """
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
        """Split a single line into fields using the configured delimiter strategy.

        REGEX mode uses re.split with regex_pattern; an re.error returns the
        whole line as a single field. SPACE mode or a space delimiter uses
        str.split() (splits on any whitespace and collapses runs). All other
        modes call str.split(delimiter).

        Input:
            line — str, a single line of text with newlines already stripped
            delimiter — str, the resolved delimiter character
            delimiter_type — DelimiterType, the resolved interpretation mode
            regex_pattern — str, compiled regex pattern used when delimiter_type
                is REGEX; may be empty or None for other modes
        Output: List[str] — ordered field strings; not yet stripped of whitespace
        """
        if delimiter_type == DelimiterType.REGEX and regex_pattern:
            try:
                return re.split(regex_pattern, line)
            except re.error:
                return [line]
        if delimiter_type == DelimiterType.SPACE or delimiter == " ":
            return line.split()
        return line.split(delimiter)
