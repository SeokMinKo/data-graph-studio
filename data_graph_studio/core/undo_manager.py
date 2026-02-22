"""data_graph_studio.core.undo_manager

Session-only undo/redo for DGS.

Design goals:
- Undo/redo actually *applies* state changes (previous implementation only popped).
- History-friendly (single linear timeline with a cursor).
- Session-only (no persistence across save/load).
- Safe for UI integration (signals + pause during replay).

This is intentionally lightweight (not Qt's QUndoStack) to keep core independent.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

from data_graph_studio.core.constants import UNDO_MAX_DEPTH


class UndoActionType(Enum):
    """Categorization for history UI / analytics (not required for execution)."""

    # Dataset / comparison
    DATASET_ADD = "dataset_add"
    DATASET_REMOVE = "dataset_remove"
    DATASET_ACTIVATE = "dataset_activate"
    COMPARISON_SETTINGS = "comparison_settings"

    # Query / view
    FILTER_CHANGE = "filter_change"
    SORT_CHANGE = "sort_change"
    CHART_SETTINGS = "chart_settings"
    THEME_CHANGE = "theme_change"

    # Existing
    ANNOTATION_ADD = "annotation_add"
    ANNOTATION_DELETE = "annotation_delete"
    ANNOTATION_EDIT = "annotation_edit"
    COLUMN_ADD = "column_add"
    COLUMN_DELETE = "column_delete"
    COLUMN_EDIT = "column_edit"
    DASHBOARD_LAYOUT_CHANGE = "dashboard_layout_change"
    DASHBOARD_CELL_ASSIGN = "dashboard_cell_assign"
    DASHBOARD_CELL_REMOVE = "dashboard_cell_remove"


@dataclass
class UndoCommand:
    """Executable command for undo/redo."""

    action_type: UndoActionType
    description: str
    do: Callable[[], None]
    undo: Callable[[], None]
    timestamp: float = time.time()


class UndoStack:
    """Linear undo timeline with a cursor.

    commands: [0..n)
    index: points to next command to redo (i.e. commands[:index] are applied).

    - push(cmd): executes cmd.do() and records it.
    - record(cmd): records a command already applied.
    - undo()/redo(): replays do/undo and returns the command.

    pause() is used to prevent recursion when replaying commands.
    """

    def __init__(self, max_depth: int = UNDO_MAX_DEPTH, on_changed: Optional[Callable[[], None]] = None):
        self.max_depth = max_depth
        self._commands: List[UndoCommand] = []
        self._index: int = 0
        self._paused: int = 0
        self._on_changed = on_changed

        # Compound support (for compatibility)
        self._compound_active: bool = False
        self._compound_description: str = ""
        self._compound_buffer: List[UndoCommand] = []

    # ── Introspection ─────────────────────────────────────────

    @property
    def index(self) -> int:
        return self._index

    @property
    def commands(self) -> List[UndoCommand]:
        return list(self._commands)

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._commands)

    # ── Mutation ──────────────────────────────────────────────

    def clear(self) -> None:
        self._commands.clear()
        self._index = 0
        self._emit_changed()

    @contextmanager
    def pause(self):
        self._paused += 1
        try:
            yield
        finally:
            self._paused = max(0, self._paused - 1)

    def push(self, cmd: UndoCommand) -> None:
        """Execute cmd.do() and record it in the timeline."""
        if self._compound_active:
            # Execute now, buffer for compound
            if self._paused:
                cmd.do()
            else:
                with self.pause():
                    cmd.do()
            self._compound_buffer.append(cmd)
            return

        if self._paused:
            cmd.do()
            return

        if self._index < len(self._commands):
            self._commands = self._commands[: self._index]

        with self.pause():
            cmd.do()

        self._record(cmd)

    def record(self, cmd: UndoCommand) -> None:
        """Record a command that has already been applied (do NOT execute)."""
        if self._paused:
            return

        if self._compound_active:
            self._compound_buffer.append(cmd)
            return

        if self._index < len(self._commands):
            self._commands = self._commands[: self._index]
        self._record(cmd)

    def _record(self, cmd: UndoCommand) -> None:
        self._commands.append(cmd)
        self._index += 1
        self._enforce_max_depth()
        self._emit_changed()

    def undo(self) -> Optional[UndoCommand]:
        if not self.can_undo():
            return None
        self._index -= 1
        cmd = self._commands[self._index]
        with self.pause():
            cmd.undo()
        self._emit_changed()
        return cmd

    def redo(self) -> Optional[UndoCommand]:
        if not self.can_redo():
            return None
        cmd = self._commands[self._index]
        with self.pause():
            cmd.do()
        self._index += 1
        self._emit_changed()
        return cmd

    # ── Internal ──────────────────────────────────────────────

    def begin_compound(self, description: str) -> None:
        if self._compound_active:
            return
        self._compound_active = True
        self._compound_description = description
        self._compound_buffer.clear()

    def end_compound(self) -> None:
        if not self._compound_active:
            return
        self._compound_active = False

        items = list(self._compound_buffer)
        self._compound_buffer.clear()

        if not items:
            return

        desc = self._compound_description or "Compound"
        self._compound_description = ""

        # Combine into a single command
        def _do_all():
            for c in items:
                c.do()

        def _undo_all():
            for c in reversed(items):
                c.undo()

        compound = UndoCommand(
            action_type=items[0].action_type,
            description=desc,
            do=_do_all,
            undo=_undo_all,
            timestamp=time.time(),
        )

        # Backward-compat for tests: expose snapshot lists when present.
        setattr(compound, "before_state", [getattr(c, "before_state", None) for c in items])
        setattr(compound, "after_state", [getattr(c, "after_state", None) for c in items])

        # Compound items already executed when they were pushed (if they were commands).
        # So we only record the compound now.
        self.record(compound)

    def _emit_changed(self) -> None:
        if self._on_changed:
            try:
                self._on_changed()
            except Exception:
                pass

# (removed UndoAction compatibility layer)
    def _enforce_max_depth(self) -> None:
        while len(self._commands) > self.max_depth:
            self._commands.pop(0)
            self._index = max(0, self._index - 1)
