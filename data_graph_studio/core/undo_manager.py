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

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

from data_graph_studio.core.constants import UNDO_MAX_DEPTH

logger = logging.getLogger(__name__)


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
    """Executable command for undo/redo.

    Holds a paired do/undo callable along with metadata used for logging and
    history display. Instances are created by callers and passed to UndoStack.push
    or UndoStack.record.

    Input:
        action_type — UndoActionType, category used in history UI
        description — str, human-readable summary of the operation
        do — Callable[[], None], applies the state change
        undo — Callable[[], None], reverses the state change
        timestamp — float, epoch time of creation; defaults to time.time()
    """

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
        """Initialize an empty undo stack.

        Input:
            max_depth — int, maximum number of commands retained; oldest entries
                are evicted when exceeded; defaults to UNDO_MAX_DEPTH
            on_changed — Optional[Callable[[], None]], called after every
                structural change to the stack (push, record, undo, redo, clear)
        Invariants: _index == 0 and _commands is empty after construction
        """
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
        """Return the current position in the undo stack.

        Output: int — number of applied commands; equals len(commands) when
            nothing has been undone
        """
        return self._index

    @property
    def commands(self) -> List[UndoCommand]:
        """Return a copy of the recorded command list.

        Output: List[UndoCommand] — snapshot of all recorded commands in
            chronological order; safe to iterate without affecting the stack
        """
        return list(self._commands)

    def can_undo(self) -> bool:
        """Return True if there is a command available to undo.

        Output: bool — True when _index > 0
        """
        return self._index > 0

    def can_redo(self) -> bool:
        """Return True if there is a command available to redo.

        Output: bool — True when _index < len(_commands)
        """
        return self._index < len(self._commands)

    # ── Mutation ──────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all recorded commands and reset the index to zero.

        Triggers the on_changed callback. Compound state is not affected.
        Invariants: can_undo() == False and can_redo() == False after this call
        """
        self._commands.clear()
        self._index = 0
        self._emit_changed()

    @contextmanager
    def pause(self):
        """Context manager that temporarily suspends recording new commands.

        Re-entrant: multiple nested pause() calls are reference-counted.
        Commands pushed or recorded while paused are executed but not stored.
        Invariants: _paused returns to its prior value when the block exits,
            even on exception
        """
        self._paused += 1
        try:
            yield
        finally:
            self._paused = max(0, self._paused - 1)

    def push(self, cmd: UndoCommand) -> None:
        """Execute cmd.do() and record it in the timeline.

        If a compound group is active, the command is executed immediately and
        buffered for the compound entry. If the stack is paused, the command
        executes but is not recorded. Otherwise, any commands ahead of the
        current index are discarded before recording the new command.

        Input: cmd — UndoCommand, the command to execute and record
        Invariants: cmd.do() is always called exactly once; on_changed fires
            after a successful record
        """
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

        logger.debug("undo_manager.push", extra={"action_type": cmd.action_type.value, "description": cmd.description})
        self._record(cmd)

    def record(self, cmd: UndoCommand) -> None:
        """Record a command that has already been applied (do NOT execute).

        Use this when the state change was applied outside the undo system and
        only the undo callback needs to be registered. Ignored when paused.
        Buffered when a compound group is active.

        Input: cmd — UndoCommand, a command whose do() has already been called
        Invariants: cmd.do() is never called by this method
        """
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
        """Undo the most recent command and return it, or None if nothing to undo.

        Decrements the index, calls cmd.undo() inside a pause block to prevent
        re-recording, then fires on_changed.

        Output: Optional[UndoCommand] — the command that was undone, or None
        Invariants: _index decrements by 1 on success; state is reversed by cmd.undo()
        """
        if not self.can_undo():
            logger.debug("undo_manager.undo.nothing_to_undo")
            return None
        self._index -= 1
        cmd = self._commands[self._index]
        logger.debug("undo_manager.undo", extra={"action_type": cmd.action_type.value, "description": cmd.description})
        with self.pause():
            cmd.undo()
        self._emit_changed()
        return cmd

    def redo(self) -> Optional[UndoCommand]:
        """Re-apply the next command in the timeline and return it, or None if nothing to redo.

        Calls cmd.do() inside a pause block to prevent re-recording, then
        increments the index and fires on_changed.

        Output: Optional[UndoCommand] — the command that was re-applied, or None
        Invariants: _index increments by 1 on success; state is re-applied by cmd.do()
        """
        if not self.can_redo():
            logger.debug("undo_manager.redo.nothing_to_redo")
            return None
        cmd = self._commands[self._index]
        logger.debug("undo_manager.redo", extra={"action_type": cmd.action_type.value, "description": cmd.description})
        with self.pause():
            cmd.do()
        self._index += 1
        self._emit_changed()
        return cmd

    # ── Internal ──────────────────────────────────────────────

    def begin_compound(self, description: str) -> None:
        """Start accumulating multiple commands into a single compound undo entry.

        Subsequent push() and record() calls are buffered until end_compound()
        is called. Re-entrant calls are ignored (first caller owns the group).

        Input: description — str, label for the combined command shown in history UI
        Invariants: _compound_active is True after this call unless it was
            already True
        """
        if self._compound_active:
            return
        self._compound_active = True
        self._compound_description = description
        self._compound_buffer.clear()

    def end_compound(self) -> None:
        """Finish the compound group and record it as one undoable command.

        Combines all buffered commands into a single UndoCommand whose do()
        replays them in order and whose undo() reverses them. The compound
        is recorded via record() (not push()) since constituent commands were
        already executed during buffering. No-ops when the buffer is empty.

        Invariants: _compound_active is False after this call; all buffered
            commands are cleared regardless of buffer size
        """
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
                logger.error("undo_manager.apply.failed", extra={"op": "on_changed_callback"}, exc_info=True)

# (removed UndoAction compatibility layer)
    def _enforce_max_depth(self) -> None:
        while len(self._commands) > self.max_depth:
            logger.warning("undo_manager.max_depth_exceeded", extra={"max_depth": self.max_depth})
            self._commands.pop(0)
            self._index = max(0, self._index - 1)
