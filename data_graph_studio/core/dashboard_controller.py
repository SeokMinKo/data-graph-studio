"""
Dashboard Controller — PRD v2 Feature 1 (§9.2)

Manages DashboardLayout lifecycle: create, modify, save, load.
Integrates with UndoManager and ensures mutual exclusion with
profile comparison mode (§8.1).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from .dashboard_layout import (
    DashboardCell,
    DashboardLayout,
    LAYOUT_PRESETS,
    default_layout,
    validate_layout_json,
)
from .undo_manager import UndoActionType, UndoCommand, UndoStack


class DashboardController:
    """
    Business-logic controller for dashboard mode.

    Parameters
    ----------
    state : AppState (or mock)
        Application state — used to query dataset availability and
        clear profile comparison.
    undo_stack : UndoStack
        Global undo/redo stack for recording dashboard changes.
    """

    def __init__(self, state: Any, undo_stack: UndoStack) -> None:
        self._state = state
        self._undo = undo_stack
        self._layout: Optional[DashboardLayout] = None
        self._active: bool = False

    # -- properties ---------------------------------------------------------

    @property
    def current_layout(self) -> Optional[DashboardLayout]:
        """Return the currently active DashboardLayout, or None."""
        return self._layout

    @property
    def is_active(self) -> bool:
        """Return True when dashboard mode is active."""
        return self._active

    # -- layout lifecycle ---------------------------------------------------

    def create_layout(self, name: str, rows: int, cols: int) -> DashboardLayout:
        """Create a new empty layout and set it as current."""
        self._layout = DashboardLayout(name=name, rows=rows, cols=cols, cells=[])
        return self._layout

    def apply_preset(self, preset_name: str) -> Optional[DashboardLayout]:
        """Apply a named layout preset (FR-1.8)."""
        if preset_name not in LAYOUT_PRESETS:
            return None
        rows, cols = LAYOUT_PRESETS[preset_name]
        before = self._layout.deep_copy() if self._layout else None
        self._layout = DashboardLayout(name=preset_name, rows=rows, cols=cols, cells=[])
        if before is not None:
            self._push_layout_undo("Apply preset " + preset_name, before)
        return self._layout

    # -- activation / deactivation ------------------------------------------

    def activate(self) -> bool:
        """
        Activate dashboard mode.

        ERR-1.3: blocked when no datasets are loaded.
        §8.1: mutually exclusive with profile comparison.
        """
        if not self._state.dataset_states:
            logger.warning("dashboard_controller.activate.no_datasets")
            return False
        if self._layout is None:
            self._layout = default_layout()
        # Mutual exclusion with profile comparison (§8.1)
        if self._state.is_profile_comparison_active:
            self._state.clear_profile_comparison()
        logger.debug("dashboard_controller.activate")
        self._active = True
        return True

    def deactivate(self) -> None:
        """Deactivate dashboard mode (§10.6)."""
        self._active = False

    # -- cell management ----------------------------------------------------

    def add_cell(
        self,
        row: int,
        col: int,
        row_span: int = 1,
        col_span: int = 1,
        profile_id: str = "",
    ) -> bool:
        """Add a cell to the current layout."""
        if self._layout is None:
            return False
        before = self._layout.deep_copy()
        cell = DashboardCell(
            row=row, col=col, row_span=row_span, col_span=col_span,
            profile_id=profile_id,
        )
        ok = self._layout.add_cell(cell)
        if ok:
            self._push_undo(
                UndoActionType.DASHBOARD_CELL_ASSIGN,
                f"Add cell ({row},{col})",
                before,
            )
        return ok

    def remove_cell(self, row: int, col: int) -> Optional[DashboardCell]:
        """Remove a cell from the current layout."""
        if self._layout is None:
            return None
        before = self._layout.deep_copy()
        removed = self._layout.remove_cell(row, col)
        if removed is not None:
            self._push_undo(
                UndoActionType.DASHBOARD_CELL_REMOVE,
                f"Remove cell ({row},{col})",
                before,
            )
        return removed

    def get_cell(self, row: int, col: int) -> Optional[DashboardCell]:
        """Return the cell at (row, col) in the current layout, or None."""
        if self._layout is None:
            return None
        return self._layout.get_cell(row, col)

    def resize_cell(self, row: int, col: int, row_span: int, col_span: int) -> bool:
        """
        Change the span of an existing cell (FR-1.3).

        Returns False if the new span would cause overlap or go out of bounds.
        """
        if self._layout is None:
            return False
        cell = self._layout.get_cell(row, col)
        if cell is None:
            return False

        before = self._layout.deep_copy()

        # Temporarily remove to check new span
        _old_rs, _old_cs = cell.row_span, cell.col_span
        self._layout.cells.remove(cell)
        new_cell = DashboardCell(
            row=row, col=col, row_span=row_span, col_span=col_span,
            profile_id=cell.profile_id,
        )
        # Bounds check
        if new_cell.row + new_cell.row_span > self._layout.rows:
            self._layout.cells.append(cell)
            return False
        if new_cell.col + new_cell.col_span > self._layout.cols:
            self._layout.cells.append(cell)
            return False
        # Overlap check
        for existing in self._layout.cells:
            if existing.overlaps(new_cell):
                self._layout.cells.append(cell)
                return False

        self._layout.cells.append(new_cell)
        self._push_layout_undo(f"Resize cell ({row},{col})", before)
        return True

    # -- profile assignment -------------------------------------------------

    def assign_profile(self, row: int, col: int, profile_id: str) -> bool:
        """Assign a profile to an existing cell (FR-1.2)."""
        if self._layout is None:
            return False
        cell = self._layout.get_cell(row, col)
        if cell is None:
            return False
        before = self._layout.deep_copy()
        cell.profile_id = profile_id
        self._push_undo(
            UndoActionType.DASHBOARD_CELL_ASSIGN,
            f"Assign profile to ({row},{col})",
            before,
        )
        return True

    def unassign_profile(self, row: int, col: int) -> bool:
        """Clear profile from a cell (with undo support)."""
        if self._layout is None:
            return False
        cell = self._layout.get_cell(row, col)
        if cell is None:
            return False
        before = self._layout.deep_copy()
        cell.profile_id = ""
        self._push_undo(
            UndoActionType.DASHBOARD_CELL_ASSIGN,
            f"Unassign profile from ({row},{col})",
            before,
        )
        return True

    def on_profile_deleted(self, profile_id: str) -> None:
        """ERR-1.2: when a profile is deleted, clear matching cells."""
        if self._layout is None:
            return
        for cell in self._layout.cells:
            if cell.profile_id == profile_id:
                cell.profile_id = ""

    # -- sync ---------------------------------------------------------------

    def set_sync_x(self, enabled: bool) -> None:
        """FR-1.5: toggle X-axis synchronisation."""
        if self._layout is None:
            return
        before = self._layout.deep_copy()
        self._layout.sync_x = enabled
        self._push_layout_undo(
            f"{'Enable' if enabled else 'Disable'} X-axis sync", before,
        )

    def set_sync_y(self, enabled: bool) -> None:
        """FR-1.5: toggle Y-axis synchronisation."""
        if self._layout is None:
            return
        before = self._layout.deep_copy()
        self._layout.sync_y = enabled
        self._push_layout_undo(
            f"{'Enable' if enabled else 'Disable'} Y-axis sync", before,
        )

    # -- save / load --------------------------------------------------------

    def save_layout(self) -> Optional[Dict]:
        """FR-1.4: serialise current layout to a dict."""
        if self._layout is None:
            logger.warning("dashboard_controller.save_layout.no_layout")
            return None
        logger.debug("dashboard_controller.save_layout", extra={"name": self._layout.name})
        return self._layout.to_dict()

    def load_layout(self, data: Dict) -> DashboardLayout:
        """FR-1.4 / ERR-1.3: load layout from dict with validation fallback."""
        self._layout = validate_layout_json(data)
        logger.debug("dashboard_controller.load_layout", extra={"name": self._layout.name})
        return self._layout

    # -- undo helpers -------------------------------------------------------

    def _push_layout_undo(self, desc: str, before: DashboardLayout) -> None:
        self._push_undo(
            UndoActionType.DASHBOARD_LAYOUT_CHANGE,
            desc,
            before,
        )

    def _push_undo(
        self,
        action_type: UndoActionType,
        description: str,
        before: DashboardLayout,
    ) -> None:
        after = self._layout.deep_copy() if self._layout else None
        before_dict = before.to_dict() if before else None
        after_dict = after.to_dict() if after else None

        def _apply(layout_dict: Dict):
            if layout_dict is None:
                return
            self.restore_layout(layout_dict)

        # Layout change already happened before this call, so record.
        self._undo.record(
            UndoCommand(
                action_type=action_type,
                description=description,
                do=lambda: _apply(after_dict),
                undo=lambda: _apply(before_dict),
                timestamp=time.time(),
            )
        )

    def restore_layout(self, layout_dict: Dict) -> None:
        """Restore layout from undo/redo snapshot."""
        self._layout = DashboardLayout.from_dict(layout_dict)
