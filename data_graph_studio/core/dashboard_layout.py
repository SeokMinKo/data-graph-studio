"""
Dashboard Layout — PRD v2 Feature 1 (§6.1)

Data structures for DashboardCell and DashboardLayout with
serialization, validation, and preset management.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

# Minimum cell dimensions in pixels (FR-1.9)
MIN_CELL_WIDTH: int = 240
MIN_CELL_HEIGHT: int = 180


# ---------------------------------------------------------------------------
# DashboardCell
# ---------------------------------------------------------------------------

@dataclass
class DashboardCell:
    """Single cell in a dashboard grid."""
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    profile_id: str = ""

    # -- serialization --

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this cell to a compact JSON-compatible dictionary."""
        d: Dict[str, Any] = {
            "row": self.row,
            "col": self.col,
        }
        if self.row_span != 1:
            d["row_span"] = self.row_span
        if self.col_span != 1:
            d["col_span"] = self.col_span
        if self.profile_id:
            d["profile_id"] = self.profile_id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DashboardCell:
        """Deserialize a DashboardCell from a dictionary produced by to_dict."""
        return cls(
            row=int(data["row"]),
            col=int(data["col"]),
            row_span=int(data.get("row_span", 1)),
            col_span=int(data.get("col_span", 1)),
            profile_id=str(data.get("profile_id", "")),
        )

    # -- helpers --

    def occupies(self, r: int, c: int) -> bool:
        """Return True if this cell covers grid position (r, c)."""
        return (
            self.row <= r < self.row + self.row_span
            and self.col <= c < self.col + self.col_span
        )

    def overlaps(self, other: DashboardCell) -> bool:
        """Return True if two cells overlap."""
        r_overlap = self.row < other.row + other.row_span and other.row < self.row + self.row_span
        c_overlap = self.col < other.col + other.col_span and other.col < self.col + self.col_span
        return r_overlap and c_overlap


# ---------------------------------------------------------------------------
# DashboardLayout
# ---------------------------------------------------------------------------

@dataclass
class DashboardLayout:
    """Grid layout definition for dashboard mode (§6.1)."""
    name: str
    rows: int
    cols: int
    cells: List[DashboardCell] = field(default_factory=list)
    sync_x: bool = False
    sync_y: bool = False

    # -- serialization --

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this layout to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "rows": self.rows,
            "cols": self.cols,
            "cells": [c.to_dict() for c in self.cells],
            "sync_x": self.sync_x,
            "sync_y": self.sync_y,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DashboardLayout:
        """Deserialize a DashboardLayout from a dictionary produced by to_dict."""
        cells = [DashboardCell.from_dict(cd) for cd in data.get("cells", [])]
        return cls(
            name=data.get("name", "Untitled"),
            rows=int(data.get("rows", 2)),
            cols=int(data.get("cols", 2)),
            cells=cells,
            sync_x=bool(data.get("sync_x", False)),
            sync_y=bool(data.get("sync_y", False)),
        )

    # -- validation --

    def validate(self) -> bool:
        """
        Validate layout: no overlaps, no out-of-bounds spans.

        Returns True if valid.
        """
        for cell in self.cells:
            # out-of-bounds check
            if cell.row + cell.row_span > self.rows:
                return False
            if cell.col + cell.col_span > self.cols:
                return False
            if cell.row < 0 or cell.col < 0:
                return False
            if cell.row_span < 1 or cell.col_span < 1:
                return False

        # overlap check (pairwise)
        for i, a in enumerate(self.cells):
            for b in self.cells[i + 1:]:
                if a.overlaps(b):
                    return False
        return True

    # -- helpers --

    def get_cell(self, row: int, col: int) -> Optional[DashboardCell]:
        """Get the cell at given grid position (exact match on row/col)."""
        for cell in self.cells:
            if cell.row == row and cell.col == col:
                return cell
        return None

    def cell_at(self, row: int, col: int) -> Optional[DashboardCell]:
        """Get any cell that occupies position (row, col)."""
        for cell in self.cells:
            if cell.occupies(row, col):
                return cell
        return None

    def add_cell(self, cell: DashboardCell) -> bool:
        """Add cell if it does not overlap existing cells and is in bounds."""
        # bounds check
        if cell.row + cell.row_span > self.rows:
            return False
        if cell.col + cell.col_span > self.cols:
            return False
        # overlap check
        for existing in self.cells:
            if existing.overlaps(cell):
                return False
        self.cells.append(cell)
        return True

    def remove_cell(self, row: int, col: int) -> Optional[DashboardCell]:
        """Remove the cell at (row, col). Returns removed cell or None."""
        for i, cell in enumerate(self.cells):
            if cell.row == row and cell.col == col:
                return self.cells.pop(i)
        return None

    def minimum_window_size(self) -> Tuple[int, int]:
        """
        Minimum window dimensions to display all cells at MIN_CELL size.

        FR-1.9 / NFR-1.5.
        """
        return (self.cols * MIN_CELL_WIDTH, self.rows * MIN_CELL_HEIGHT)

    def deep_copy(self) -> DashboardLayout:
        """Return an independent deep copy."""
        return copy.deepcopy(self)


# ---------------------------------------------------------------------------
# Layout Presets (FR-1.8)
# ---------------------------------------------------------------------------

LAYOUT_PRESETS: Dict[str, Tuple[int, int]] = {
    "1×1": (1, 1),
    "1×2": (1, 2),
    "2×1": (2, 1),
    "2×2": (2, 2),
    "1×3": (1, 3),
    "3×1": (3, 1),
    "2×3": (2, 3),
}


def default_layout() -> DashboardLayout:
    """ERR-1.3 fallback: default 2×2 layout."""
    return DashboardLayout(name="Default", rows=2, cols=2, cells=[])


# ---------------------------------------------------------------------------
# JSON schema validation (ERR-1.3)
# ---------------------------------------------------------------------------

def validate_layout_json(data: Any) -> DashboardLayout:
    """
    Validate a dict as a DashboardLayout.

    On any error or overlap, returns ``default_layout()`` (ERR-1.3 fallback).
    """
    try:
        if not isinstance(data, dict):
            return default_layout()
        if "rows" not in data or "cols" not in data:
            return default_layout()
        layout = DashboardLayout.from_dict(data)
        if not layout.validate():
            return default_layout()
        return layout
    except Exception:
        return default_layout()
