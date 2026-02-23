"""
TransformChain — 선언적 변환 파이프라인 (undo 지원, 직렬화 가능)
"""

import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

import polars as pl

import logging

logger = logging.getLogger(__name__)


@dataclass
class TransformStep:
    """단일 변환 단계."""
    name: str
    operation: str  # 'filter', 'sort', 'cast', 'compute', 'drop', 'sample'
    params: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class TransformChain:
    """변환 체인: 순서 기록, undo, 직렬화, lineage 제공."""

    def __init__(self):
        self._steps: List[TransformStep] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, step: TransformStep) -> None:
        """변환 단계를 추가한다."""
        self._steps.append(step)

    def undo_last(self) -> Optional[TransformStep]:
        """마지막 변환을 제거하고 반환한다."""
        if self._steps:
            return self._steps.pop()
        return None

    def clear(self) -> None:
        """모든 단계를 제거한다."""
        self._steps.clear()

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(self, df: pl.DataFrame) -> pl.DataFrame:
        """모든 단계를 순서대로 적용한다."""
        for step in self._steps:
            df = self._apply_step(df, step)
        return df

    @staticmethod
    def _apply_step(df: pl.DataFrame, step: TransformStep) -> pl.DataFrame:
        """단일 단계를 적용한다."""
        op = step.operation
        params = step.params

        if op == 'filter':
            col = params.get('column')
            operator = params.get('operator', '==')
            value = params.get('value')
            if col and col in df.columns:
                if operator == '==':
                    df = df.filter(pl.col(col) == value)
                elif operator == '!=':
                    df = df.filter(pl.col(col) != value)
                elif operator == '>':
                    df = df.filter(pl.col(col) > value)
                elif operator == '<':
                    df = df.filter(pl.col(col) < value)
                elif operator == '>=':
                    df = df.filter(pl.col(col) >= value)
                elif operator == '<=':
                    df = df.filter(pl.col(col) <= value)

        elif op == 'sort':
            col = params.get('column')
            descending = params.get('descending', False)
            if col and col in df.columns:
                df = df.sort(col, descending=descending)

        elif op == 'cast':
            col = params.get('column')
            dtype_str = params.get('dtype')
            if col and col in df.columns and dtype_str:
                dtype_map = {
                    'Int8': pl.Int8, 'Int16': pl.Int16, 'Int32': pl.Int32, 'Int64': pl.Int64,
                    'Float32': pl.Float32, 'Float64': pl.Float64,
                    'Utf8': pl.Utf8, 'Boolean': pl.Boolean,
                    'Date': pl.Date, 'Datetime': pl.Datetime,
                }
                target = dtype_map.get(dtype_str)
                if target:
                    try:
                        df = df.with_columns(pl.col(col).cast(target, strict=False))
                    except (ValueError, TypeError, AttributeError):
                        logger.debug("transform_chain.apply_step.cast_failed", extra={"col": col, "dtype": dtype_str}, exc_info=True)

        elif op == 'drop':
            col = params.get('column')
            if col and col in df.columns:
                df = df.drop(col)

        elif op == 'sample':
            n = params.get('n')
            seed = params.get('seed', 42)
            if n and len(df) > n:
                df = df.sample(n=n, seed=seed)

        return df

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> List[Dict[str, Any]]:
        """직렬화."""
        return [asdict(s) for s in self._steps]

    @classmethod
    def from_dict(cls, data: List[Dict[str, Any]]) -> 'TransformChain':
        """역직렬화."""
        chain = cls()
        for d in data:
            chain.add(TransformStep(**d))
        return chain

    # ------------------------------------------------------------------
    # Lineage (F8)
    # ------------------------------------------------------------------

    def get_lineage(self) -> List[Dict[str, Any]]:
        """전체 변환 이력 반환."""
        return [
            {
                'step': i,
                'name': s.name,
                'op': s.operation,
                'params': s.params,
                'time': s.timestamp,
            }
            for i, s in enumerate(self._steps)
        ]

    @property
    def steps(self) -> List[TransformStep]:
        """Return a copy of the ordered list of transform steps."""
        return list(self._steps)

    def __len__(self) -> int:
        return len(self._steps)
