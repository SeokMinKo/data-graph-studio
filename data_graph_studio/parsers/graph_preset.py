"""Graph Preset system — predefined graph configurations for parsed data.

Each parser converter can define builtin presets that auto-configure
the graph when data is loaded. This removes the need for users to
manually set X/Y/chart type after parsing.

Usage:
    from data_graph_studio.parsers.graph_preset import select_preset

    preset = select_preset(df, converter="blocklayer")
    if preset:
        state.set_chart_type(ChartType(preset.chart_type))
        state.set_x_column(preset.x_column)
        for col in preset.y_columns:
            state.add_value_column(col)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import polars as pl

logger = logging.getLogger(__name__)


@dataclass
class GraphPreset:
    """A predefined graph configuration.

    Attributes:
        name: Human-readable preset name.
        chart_type: Chart type string (must match ChartType enum values).
        x_column: Column name for X axis.
        y_columns: Column name(s) for Y axis / value zone.
        group_column: Optional column for grouping/coloring.
        description: Optional description shown in UI.
    """

    name: str
    chart_type: str
    x_column: str
    y_columns: List[str]
    group_column: Optional[str] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "chart_type": self.chart_type,
            "x_column": self.x_column,
            "y_columns": list(self.y_columns),
            "group_column": self.group_column,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> GraphPreset:
        return cls(
            name=d["name"],
            chart_type=d["chart_type"],
            x_column=d["x_column"],
            y_columns=list(d["y_columns"]),
            group_column=d.get("group_column"),
            description=d.get("description", ""),
        )

    def columns_present(self, df: pl.DataFrame) -> bool:
        """Check if all required columns exist in the DataFrame."""
        available = set(df.columns)
        required = {self.x_column} | set(self.y_columns)
        if self.group_column:
            required.add(self.group_column)
        return required.issubset(available)


# ── Builtin presets ───────────────────────────────────────────

BUILTIN_PRESETS: Dict[str, List[GraphPreset]] = {
    "blocklayer": [
        GraphPreset(
            name="D2C Latency",
            chart_type="scatter",
            x_column="timestamp",
            y_columns=["d2c_ms"],
            group_column="rwbs",
            description="Dispatch-to-Complete latency over time (R/W colored)",
        ),
        GraphPreset(
            name="Q2C Latency",
            chart_type="scatter",
            x_column="timestamp",
            y_columns=["q2c_ms"],
            group_column="rwbs",
            description="Queue-to-Complete latency (full I/O time incl. queue wait)",
        ),
        GraphPreset(
            name="C2C Interval",
            chart_type="scatter",
            x_column="timestamp",
            y_columns=["c2c_ms"],
            description="Inter-completion time (time between consecutive completes)",
        ),
        GraphPreset(
            name="IOPS Timeline",
            chart_type="line",
            x_column="timestamp",
            y_columns=["queue_depth"],
            description="Queue depth over time (proxy for IOPS)",
        ),
        GraphPreset(
            name="Latency Distribution",
            chart_type="histogram",
            x_column="d2c_ms",
            y_columns=["d2c_ms"],
            description="D2C latency distribution histogram",
        ),
        GraphPreset(
            name="Size vs Latency",
            chart_type="scatter",
            x_column="size_bytes",
            y_columns=["d2c_ms"],
            group_column="rwbs",
            description="I/O size vs D2C latency correlation",
        ),
    ],
}


def select_preset(
    df: pl.DataFrame,
    converter: str = "",
    preset_name: Optional[str] = None,
) -> Optional[GraphPreset]:
    """Select the best preset for a DataFrame.

    Args:
        df: The loaded DataFrame.
        converter: Converter name (e.g. "blocklayer").
        preset_name: Specific preset name to select. If None, picks the first
                     matching preset.

    Returns:
        A GraphPreset if found and columns match, else None.
    """
    if not converter:
        logger.debug("[GraphPreset] no converter specified, skipping")
        return None

    presets = BUILTIN_PRESETS.get(converter)
    if not presets:
        logger.debug("[GraphPreset] no presets for converter=%s", converter)
        return None

    if preset_name:
        for p in presets:
            if p.name == preset_name and p.columns_present(df):
                logger.info("[GraphPreset] selected preset: %s (explicit)", p.name)
                return p
        logger.warning("[GraphPreset] preset '%s' not found or columns missing", preset_name)
        return None

    # Auto-select: first preset whose columns are present
    for p in presets:
        if p.columns_present(df):
            logger.info("[GraphPreset] auto-selected preset: %s for converter=%s", p.name, converter)
            return p

    logger.warning("[GraphPreset] no preset matched columns=%s for converter=%s",
                   df.columns, converter)
    return None
