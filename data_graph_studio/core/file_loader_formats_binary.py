"""
file_loader_formats_binary — Excel/Parquet/JSON 포맷 로딩 함수 모음.

file_loader_formats 에서 분리된 바이너리 포맷 특화 함수들.
"""
from __future__ import annotations

from typing import Optional

import polars as pl


def load_excel(path: str, sheet_name: Optional[str]) -> pl.DataFrame:
    """Excel을 로드한다."""
    return pl.read_excel(path, sheet_name=sheet_name or 0)


def load_parquet(path: str) -> pl.DataFrame:
    """Parquet을 로드한다."""
    return pl.read_parquet(path)


def load_json(path: str) -> pl.DataFrame:
    """JSON을 로드한다."""
    return pl.read_json(path)
