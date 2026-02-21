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
from dataclasses import dataclass
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
            name="LBA Map",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["lba_mb"],
            group_column="cmd",
            description="Logical Block Address over time (R/W colored)",
        ),
        GraphPreset(
            name="D2C Latency",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["d2c_ms"],
            group_column="cmd",
            description="Dispatch-to-Complete latency over time",
        ),
        GraphPreset(
            name="C2C Interval",
            chart_type="scatter",
            x_column="complete_time",
            y_columns=["c2c_ms"],
            description="Complete-to-Complete interval",
        ),
        GraphPreset(
            name="D2D Interval",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["d2d_ms"],
            group_column="cmd",
            description="Dispatch-to-Dispatch interval",
        ),
        GraphPreset(
            name="I/O Size",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["size_kb"],
            group_column="cmd",
            description="I/O size (KB) over time",
        ),
        GraphPreset(
            name="Command",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["cmd"],
            description="I/O command (R/W/D/F) over time",
        ),
        GraphPreset(
            name="Q2D Latency",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["q2d_ms"],
            group_column="cmd",
            description="Queue-to-Dispatch latency (insert→issue)",
        ),
        GraphPreset(
            name="Queue Depth",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["queue_depth"],
            description="Queue depth over time (send + complete timeline)",
        ),
        # ── Correlation & Locality presets ──
        GraphPreset(
            name="Latency vs Size",
            chart_type="scatter",
            x_column="size_kb",
            y_columns=["d2c_ms"],
            group_column="cmd",
            description="D2C latency vs I/O size — does latency scale with size?",
        ),
        GraphPreset(
            name="Latency vs Queue Depth",
            chart_type="scatter",
            x_column="queue_depth",
            y_columns=["d2c_ms"],
            group_column="cmd",
            description="D2C latency vs queue depth — load impact on latency",
        ),
        GraphPreset(
            name="Latency vs LBA",
            chart_type="scatter",
            x_column="lba_mb",
            y_columns=["d2c_ms"],
            group_column="cmd",
            description="D2C latency by LBA position — identify hot/cold zones",
        ),
        GraphPreset(
            name="Latency by Pattern",
            chart_type="box",
            x_column="is_sequential",
            y_columns=["d2c_ms"],
            description="Sequential vs Random latency distribution (box plot)",
        ),
        GraphPreset(
            name="Size Distribution",
            chart_type="box",
            x_column="cmd",
            y_columns=["size_kb"],
            description="I/O size distribution by command type",
        ),
        GraphPreset(
            name="LBA Heatmap",
            chart_type="heatmap",
            x_column="send_time",
            y_columns=["lba_mb"],
            description="LBA access density over time — spatial locality heatmap",
        ),
        GraphPreset(
            name="Idle Time",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["idle_time_ms"],
            description="Device idle time (Q=0: prev_complete → dispatch gap)",
        ),
        GraphPreset(
            name="Busy Time",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["busy_time_ms"],
            description="Device busy time (Q≥63: complete → complete interval)",
        ),
        # ── Histogram presets ──
        GraphPreset(
            name="D2C Histogram",
            chart_type="histogram",
            x_column="d2c_ms",
            y_columns=["d2c_ms"],
            group_column="cmd",
            description="Latency distribution (R/W split)",
        ),
        GraphPreset(
            name="I/O Size Histogram",
            chart_type="histogram",
            x_column="size_kb",
            y_columns=["size_kb"],
            group_column="cmd",
            description="I/O size distribution by command",
        ),
        GraphPreset(
            name="Idle Time Histogram",
            chart_type="histogram",
            x_column="idle_time_ms",
            y_columns=["idle_time_ms"],
            description="Device idle time distribution — temporal locality",
        ),
        GraphPreset(
            name="Busy Time Histogram",
            chart_type="histogram",
            x_column="busy_time_ms",
            y_columns=["busy_time_ms"],
            description="Device busy time distribution — saturation behavior",
        ),
        GraphPreset(
            name="Queue Depth Histogram",
            chart_type="histogram",
            x_column="queue_depth",
            y_columns=["queue_depth"],
            description="Queue depth distribution — device load profile",
        ),
        # ── Throughput presets ──
        GraphPreset(
            name="IOPS Timeline",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["iops"],
            description="I/O operations per second (100ms window) over time",
        ),
        GraphPreset(
            name="Bandwidth Timeline",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["bw_mbps"],
            group_column="cmd",
            description="Throughput in MB/s (100ms window) over time",
        ),
        # ── Access pattern presets ──
        GraphPreset(
            name="R/W Ratio Timeline",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["rw_ratio"],
            description="Read/Write ratio over time (1.0=all read, 0.0=all write)",
        ),
        GraphPreset(
            name="Sequential Run Length",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["seq_run_length"],
            description="Consecutive sequential I/O count — prefetch effectiveness",
        ),
        GraphPreset(
            name="Seq Run Histogram",
            chart_type="histogram",
            x_column="seq_run_length",
            y_columns=["seq_run_length"],
            description="Sequential run length distribution",
        ),
        # ── Tail latency presets ──
        GraphPreset(
            name="Latency Outlier Map",
            chart_type="scatter",
            x_column="lba_mb",
            y_columns=["d2c_ms"],
            group_column="latency_tier",
            description="Latency by LBA colored by P95/P99 tier — find problem areas",
        ),
        GraphPreset(
            name="Latency Tier Timeline",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["d2c_ms"],
            group_column="latency_tier",
            description="D2C latency colored by percentile tier over time",
        ),
        # ── Queue behavior presets ──
        GraphPreset(
            name="QD vs IOPS",
            chart_type="scatter",
            x_column="queue_depth",
            y_columns=["iops"],
            description="Queue depth vs IOPS — find saturation point",
        ),
        GraphPreset(
            name="Queue Drain Time",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["drain_time_ms"],
            description="Time for queue to drain from max to empty (ms)",
        ),
        # ── Multi-device preset ──
        GraphPreset(
            name="Device Latency Compare",
            chart_type="scatter",
            x_column="send_time",
            y_columns=["d2c_ms"],
            group_column="device",
            description="D2C latency by device — multi-device comparison",
        ),
    ],
    "sched": [
        GraphPreset(
            name="Task Runtime",
            chart_type="scatter",
            x_column="timestamp",
            y_columns=["runtime_ms"],
            group_column="next_comm",
            description="Per-task runtime duration",
        ),
        GraphPreset(
            name="CPU Activity",
            chart_type="scatter",
            x_column="timestamp",
            y_columns=["cpu"],
            group_column="next_comm",
            description="Task scheduling across CPUs",
        ),
        GraphPreset(
            name="Context Switches",
            chart_type="scatter",
            x_column="timestamp",
            y_columns=["next_pid"],
            group_column="cpu",
            description="Context switch timeline by CPU",
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
