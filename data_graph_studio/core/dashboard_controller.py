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

from .dashboard_layout import (
    DashboardCell,
    DashboardLayout,
    LAYOUT_PRESETS,
    default_layout,
    validate_layout_json,
)
from .undo_manager import UndoActionType, UndoCommand, UndoStack

logger = logging.getLogger(__name__)


class DashboardController:
    """Business-logic controller for dashboard mode.

    Manages the DashboardLayout lifecycle: create, modify, save, load.
    All mutating operations push an undo command to the shared UndoStack.

    Input: state — AppState (or compatible mock), provides dataset_states and profile comparison flags
    Input: undo_stack — UndoStack, global undo/redo stack for recording dashboard changes
    Invariants: self._layout is None until create_layout, apply_preset, or load_layout is called
    """

    def __init__(self, state: Any, undo_stack: UndoStack) -> None:
        """Initialise the controller with application state and an undo stack.

        Input: state — Any (AppState or mock), used to query datasets and clear profile comparison
        Input: undo_stack — UndoStack, receives undo commands for all layout mutations
        """
        self._state = state
        self._undo = undo_stack
        self._layout: Optional[DashboardLayout] = None
        self._active: bool = False

    # -- properties ---------------------------------------------------------

    @property
    def current_layout(self) -> Optional[DashboardLayout]:
        """Return the currently active DashboardLayout, or None if none has been created.

        Output: DashboardLayout or None
        """
        return self._layout

    @property
    def is_active(self) -> bool:
        """Return True when dashboard mode is currently active.

        Output: bool — True after a successful activate() call, False after deactivate()
        """
        return self._active

    # -- layout lifecycle ---------------------------------------------------

    def create_layout(self, name: str, rows: int, cols: int) -> DashboardLayout:
        """Create a new empty layout and set it as the current layout.

        Input: name — str, human-readable name for the layout
        Input: rows — int, number of grid rows (>= 1)
        Input: cols — int, number of grid columns (>= 1)
        Output: DashboardLayout — the newly created empty layout
        Invariants: any previous layout is replaced; no undo entry is recorded for creation
        """
        self._layout = DashboardLayout(name=name, rows=rows, cols=cols, cells=[])
        return self._layout

    def apply_preset(self, preset_name: str) -> Optional[DashboardLayout]:
        """Apply a named layout preset, replacing the current layout (FR-1.8).

        If a layout already exists, the replacement is recorded as an undo entry.

        Input: preset_name — str, key from LAYOUT_PRESETS (e.g. "2x2", "1x3")
        Output: DashboardLayout — the new preset layout, or None if preset_name is unknown
        Invariants: LAYOUT_PRESETS maps preset names to (rows, cols) tuples
        """
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
        """Activate dashboard mode.

        ERR-1.3: blocked when no datasets are loaded.
        §8.1: mutually exclusive with profile comparison mode.
        If no layout exists, a default layout is created.

        Output: bool — True if activation succeeded, False if no datasets are available
        Invariants: profile comparison is cleared before activating; self._active is set to True on success
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
        """Deactivate dashboard mode without discarding the current layout (§10.6).

        Invariants: self._active is set to False; self._layout is preserved for reactivation
        """
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
        """Add a new cell to the current layout and record an undo entry.

        Input: row — int, zero-based row index of the cell anchor
        Input: col — int, zero-based column index of the cell anchor
        Input: row_span — int, number of rows the cell spans (>= 1)
        Input: col_span — int, number of columns the cell spans (>= 1)
        Input: profile_id — str, optional profile assigned to this cell
        Output: bool — True if the cell was added successfully, False if no layout exists or overlap detected
        Raises: nothing — returns False on failure
        """
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
        """Remove the cell anchored at (row, col) and record an undo entry.

        Input: row — int, zero-based row index of the cell to remove
        Input: col — int, zero-based column index of the cell to remove
        Output: DashboardCell that was removed, or None if no layout exists or cell not found
        """
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
        """Return the cell anchored at (row, col), or None if absent.

        Input: row — int, zero-based row index
        Input: col — int, zero-based column index
        Output: DashboardCell at the given position, or None
        """
        if self._layout is None:
            return None
        return self._layout.get_cell(row, col)

    def resize_cell(self, row: int, col: int, row_span: int, col_span: int) -> bool:
        """Change the row/column span of an existing cell (FR-1.3).

        Validates that the new span does not exceed grid bounds or overlap other cells.
        Records an undo entry on success.

        Input: row — int, zero-based row anchor of the cell to resize
        Input: col — int, zero-based column anchor of the cell to resize
        Input: row_span — int, new row span (>= 1)
        Input: col_span — int, new column span (>= 1)
        Output: bool — True if resize succeeded, False if out of bounds or overlap detected
        Invariants: on failure the cell is restored to its original span
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
        """Assign a profile to an existing cell and record an undo entry (FR-1.2).

        Input: row — int, zero-based row anchor of the target cell
        Input: col — int, zero-based column anchor of the target cell
        Input: profile_id — str, ID of the profile to assign (non-empty)
        Output: bool — True if the cell was found and updated, False otherwise
        """
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
        """Clear the profile assignment from a cell and record an undo entry.

        Input: row — int, zero-based row anchor of the target cell
        Input: col — int, zero-based column anchor of the target cell
        Output: bool — True if the cell was found and cleared, False otherwise
        Invariants: cell.profile_id is set to "" (empty string) on success
        """
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
        """Clear all cells whose profile matches the deleted profile ID (ERR-1.2).

        Input: profile_id — str, ID of the profile that was deleted
        Invariants: cells with matching profile_id are set to ""; no undo entry is recorded
        """
        if self._layout is None:
            return
        for cell in self._layout.cells:
            if cell.profile_id == profile_id:
                cell.profile_id = ""

    # -- sync ---------------------------------------------------------------

    def set_sync_x(self, enabled: bool) -> None:
        """Toggle X-axis synchronisation across dashboard cells (FR-1.5).

        Input: enabled — bool, True to enable sync, False to disable
        Invariants: no-op if no layout is set; records an undo entry when layout exists
        """
        if self._layout is None:
            return
        before = self._layout.deep_copy()
        self._layout.sync_x = enabled
        self._push_layout_undo(
            f"{'Enable' if enabled else 'Disable'} X-axis sync", before,
        )

    def set_sync_y(self, enabled: bool) -> None:
        """Toggle Y-axis synchronisation across dashboard cells (FR-1.5).

        Input: enabled — bool, True to enable sync, False to disable
        Invariants: no-op if no layout is set; records an undo entry when layout exists
        """
        if self._layout is None:
            return
        before = self._layout.deep_copy()
        self._layout.sync_y = enabled
        self._push_layout_undo(
            f"{'Enable' if enabled else 'Disable'} Y-axis sync", before,
        )

    # -- save / load --------------------------------------------------------

    def save_layout(self) -> Optional[Dict]:
        """Serialise the current layout to a plain dict (FR-1.4).

        Output: dict representation of the layout, or None if no layout is set
        """
        if self._layout is None:
            logger.warning("dashboard_controller.save_layout.no_layout")
            return None
        logger.debug("dashboard_controller.save_layout", extra={"layout_name": self._layout.name})
        return self._layout.to_dict()

    def load_layout(self, data: Dict) -> DashboardLayout:
        """Load and validate a layout from a dict, replacing the current layout (FR-1.4 / ERR-1.3).

        Input: data — Dict, serialised layout (from save_layout or file storage)
        Output: DashboardLayout — the validated and activated layout
        Raises: ValidationError — if the dict fails schema validation inside validate_layout_json
        """
        self._layout = validate_layout_json(data)
        logger.debug("dashboard_controller.load_layout", extra={"layout_name": self._layout.name})
        return self._layout

    # -- undo helpers -------------------------------------------------------

    def _push_layout_undo(self, desc: str, before: DashboardLayout) -> None:
        """Push a DASHBOARD_LAYOUT_CHANGE undo command for a generic layout mutation.

        Input: desc — str, human-readable description of the change
        Input: before — DashboardLayout, deep-copy of the layout before the change
        """
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
        """Record a do/undo command pair on the undo stack for a layout change.

        Input: action_type — UndoActionType, categorises the change for the undo stack
        Input: description — str, human-readable label shown in the undo history
        Input: before — DashboardLayout, deep-copy of the layout prior to the change
        Invariants: the current self._layout is captured as the "after" snapshot at call time
        """
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
        """Restore the layout from an undo/redo snapshot dict.

        Input: layout_dict — Dict, serialised layout produced by DashboardLayout.to_dict()
        Invariants: used exclusively by undo/redo lambdas; does not push additional undo entries
        """
        self._layout = DashboardLayout.from_dict(layout_dict)
