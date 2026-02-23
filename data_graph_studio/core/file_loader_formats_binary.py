"""
file_loader_formats_binary — Excel/Parquet/JSON 포맷 로딩 함수 모음.

file_loader_formats 에서 분리된 바이너리 포맷 특화 함수들.
"""
from __future__ import annotations

from typing import Optional

import polars as pl


def load_excel(path: str, sheet_name: Optional[str]) -> pl.DataFrame:
    """Load an Excel file and return its contents as a Polars DataFrame.

    Input: path — str, absolute path to the .xlsx or .xls file
           sheet_name — str | None, sheet to load; uses the first sheet (index 0) when None
    Output: pl.DataFrame — parsed table data from the specified sheet
    Raises: Exception — propagated from polars.read_excel on file/format errors
    """
    return pl.read_excel(path, sheet_name=sheet_name or 0)


def load_parquet(path: str) -> pl.DataFrame:
    """Load a Parquet file and return its contents as a Polars DataFrame.

    Input: path — str, absolute path to the .parquet file
    Output: pl.DataFrame — decoded columnar data from the Parquet file
    Raises: Exception — propagated from polars.read_parquet on file/format errors
    """
    return pl.read_parquet(path)


def load_json(path: str) -> pl.DataFrame:
    """Load a JSON file and return its contents as a Polars DataFrame.

    Input: path — str, absolute path to the .json file (array-of-objects or columnar format)
    Output: pl.DataFrame — parsed data from the JSON file
    Raises: Exception — propagated from polars.read_json on file/format errors
    """
    return pl.read_json(path)
