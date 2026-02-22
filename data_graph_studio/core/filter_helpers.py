"""
filter_helpers — Filter.to_expression() 에서 사용하는 dispatch 함수 및 테이블.

filtering 모듈에서 분리된 순수 헬퍼 함수들.
"""
from __future__ import annotations

import polars as pl


# ---------------------------------------------------------------------------
# Dispatch helpers for Filter.to_expression()
# ---------------------------------------------------------------------------

def _filter_between(col, f):
    if isinstance(f.value, (list, tuple)) and len(f.value) == 2:
        return (col >= f.value[0]) & (col <= f.value[1])
    return None


def _filter_not_between(col, f):
    if isinstance(f.value, (list, tuple)) and len(f.value) == 2:
        return (col < f.value[0]) | (col > f.value[1])
    return None


def _filter_in_list(col, f):
    if isinstance(f.value, (list, tuple, set)):
        return col.is_in(list(f.value))
    return None


def _filter_not_in_list(col, f):
    if isinstance(f.value, (list, tuple, set)):
        return ~col.is_in(list(f.value))
    return None


def _filter_contains(col, f):
    if f.case_sensitive:
        return col.cast(pl.Utf8).str.contains(str(f.value))
    return col.cast(pl.Utf8).str.to_lowercase().str.contains(str(f.value).lower())


def _filter_not_contains(col, f):
    if f.case_sensitive:
        return ~col.cast(pl.Utf8).str.contains(str(f.value))
    return ~col.cast(pl.Utf8).str.to_lowercase().str.contains(str(f.value).lower())


def _filter_starts_with(col, f):
    if f.case_sensitive:
        return col.cast(pl.Utf8).str.starts_with(str(f.value))
    return col.cast(pl.Utf8).str.to_lowercase().str.starts_with(str(f.value).lower())


def _filter_ends_with(col, f):
    if f.case_sensitive:
        return col.cast(pl.Utf8).str.ends_with(str(f.value))
    return col.cast(pl.Utf8).str.to_lowercase().str.ends_with(str(f.value).lower())


FILTER_DISPATCH = {
    "eq":           lambda col, f: col == f.value,
    "ne":           lambda col, f: col != f.value,
    "gt":           lambda col, f: col > f.value,
    "ge":           lambda col, f: col >= f.value,
    "lt":           lambda col, f: col < f.value,
    "le":           lambda col, f: col <= f.value,
    "between":      _filter_between,
    "not_between":  _filter_not_between,
    "in":           _filter_in_list,
    "not_in":       _filter_not_in_list,
    "contains":     _filter_contains,
    "not_contains": _filter_not_contains,
    "starts_with":  _filter_starts_with,
    "ends_with":    _filter_ends_with,
    "regex":        lambda col, f: col.cast(pl.Utf8).str.contains(str(f.value)),
    "is_null":      lambda col, f: col.is_null(),
    "is_not_null":  lambda col, f: col.is_not_null(),
    "is_true":      lambda col, f: col.eq(True),
    "is_false":     lambda col, f: col.eq(False),
}
