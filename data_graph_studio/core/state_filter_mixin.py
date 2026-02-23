"""
FilterSortMixin - Filter and sort management methods extracted from AppState.

All methods operate on shared instance state (self.*) and can call
self.emit(...) because AppState also inherits from Observable.
"""

from typing import List, Any
import copy
import time

from .state_types import (
    FilterCondition,
    SortCondition,
)
from .undo_manager import UndoCommand, UndoActionType


class FilterSortMixin:
    """Mixin providing filter and sort management capabilities to AppState.

    All mutating methods record an undo/redo command via self._push_undo
    and emit the corresponding signal via self.emit.

    Requires the host class to provide:
        self._filters — List[FilterCondition]
        self._sorts — List[SortCondition]
        self._undo_paused — int, pauses undo recording when > 0
        self._push_undo(cmd) — records an UndoCommand on the undo stack
        self.emit(signal_name) — fires an Observable signal
    """

    # ==================== Filters ====================

    @property
    def filters(self) -> List[FilterCondition]:
        """List of active filter conditions applied to the dataset.

        Output: List[FilterCondition] — may be empty; order matches insertion order
        """
        return self._filters

    def add_filter(self, column: str, operator: str, value: Any):
        """Append a new filter condition and record an undo entry.

        Input: column — str, column name to filter on
        Input: operator — str, comparison operator (e.g. "eq", "ne", "gt", "lt", "contains")
        Input: value — Any, value to compare against; type must be compatible with the column dtype
        Output: None
        Raises: nothing
        Invariants: filter is appended at the end of self._filters; filter_changed is emitted
        """
        before = copy.deepcopy(self._filters)
        self._filters.append(FilterCondition(column, operator, value))
        self.emit("filter_changed")
        after = copy.deepcopy(self._filters)

        def _apply(value_filters):
            self._undo_paused += 1
            try:
                self._filters = copy.deepcopy(value_filters)
                self.emit("filter_changed")
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.FILTER_CHANGE,
                description=f"Filter: + {column} {operator} {value}",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    def remove_filter(self, index: int):
        """Remove a filter condition by index and record an undo entry.

        Input: index — int, zero-based index of the filter to remove
        Output: None
        Raises: nothing — silently no-ops if index is out of range
        Invariants: filter_changed is emitted only when a filter is actually removed
        """
        if not (0 <= index < len(self._filters)):
            return
        before = copy.deepcopy(self._filters)
        removed = self._filters[index]
        self._filters.pop(index)
        self.emit("filter_changed")
        after = copy.deepcopy(self._filters)

        def _apply(value_filters):
            self._undo_paused += 1
            try:
                self._filters = copy.deepcopy(value_filters)
                self.emit("filter_changed")
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.FILTER_CHANGE,
                description=f"Filter: - {removed.column}",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    def clear_filters(self):
        """Remove all filter conditions and record an undo entry.

        Output: None
        Raises: nothing
        Invariants: no-op if self._filters is already empty; filter_changed is emitted on change
        """
        if not self._filters:
            return
        before = copy.deepcopy(self._filters)
        self._filters.clear()
        self.emit("filter_changed")
        after = copy.deepcopy(self._filters)

        def _apply(value_filters):
            self._undo_paused += 1
            try:
                self._filters = copy.deepcopy(value_filters)
                self.emit("filter_changed")
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.FILTER_CHANGE,
                description="Filter: Clear",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    def toggle_filter(self, index: int):
        """Toggle the enabled state of a filter condition and record an undo entry.

        Input: index — int, zero-based index of the filter to toggle
        Output: None
        Raises: nothing — silently no-ops if index is out of range
        Invariants: filter_changed is emitted only when the toggle actually occurs;
                    FilterCondition.enabled is flipped in-place before the snapshot is taken
        """
        if not (0 <= index < len(self._filters)):
            return
        before = copy.deepcopy(self._filters)
        self._filters[index].enabled = not self._filters[index].enabled
        self.emit("filter_changed")
        after = copy.deepcopy(self._filters)

        def _apply(value_filters):
            self._undo_paused += 1
            try:
                self._filters = copy.deepcopy(value_filters)
                self.emit("filter_changed")
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.FILTER_CHANGE,
                description=f"Filter: Toggle {self._filters[index].column}",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )

    # ==================== Sorts ====================

    @property
    def sorts(self) -> List[SortCondition]:
        """List of active sort conditions applied to the dataset.

        Output: List[SortCondition] — may be empty; order determines sort priority
        """
        return self._sorts

    def set_sort(self, column: str, descending: bool = False, add: bool = False):
        """Set a sort condition on a column, replacing or adding to existing sorts.

        Any existing sort on the same column is removed before the new one is added.

        Input: column — str, column name to sort by
        Input: descending — bool, True for descending order, False for ascending
        Input: add — bool, True to append to existing sorts; False to replace all
        Output: None
        Raises: nothing
        Invariants: sort_changed is emitted only when the sort list actually changes;
                    existing sort on the same column is always removed before re-adding
        """
        before = copy.deepcopy(self._sorts)

        if not add:
            self._sorts.clear()

        # Remove existing sort on the same column before re-adding
        self._sorts = [s for s in self._sorts if s.column != column]
        self._sorts.append(SortCondition(column, descending))
        self.emit("sort_changed")

        after = copy.deepcopy(self._sorts)
        if before != after:
            def _apply(value):
                self._undo_paused += 1
                try:
                    self._sorts = copy.deepcopy(value)
                    self.emit("sort_changed")
                finally:
                    self._undo_paused = max(0, self._undo_paused - 1)

            self._push_undo(
                UndoCommand(
                    action_type=UndoActionType.SORT_CHANGE,
                    description=f"Sort: {column} ({'DESC' if descending else 'ASC'})",
                    do=lambda: _apply(after),
                    undo=lambda: _apply(before),
                    timestamp=time.time(),
                )
            )

    def clear_sorts(self):
        """Remove all sort conditions and record an undo entry.

        Output: None
        Raises: nothing
        Invariants: no-op if self._sorts is already empty; sort_changed is emitted on change
        """
        before = copy.deepcopy(self._sorts)
        if not self._sorts:
            return
        self._sorts.clear()
        self.emit("sort_changed")

        after = copy.deepcopy(self._sorts)

        def _apply(value):
            self._undo_paused += 1
            try:
                self._sorts = copy.deepcopy(value)
                self.emit("sort_changed")
            finally:
                self._undo_paused = max(0, self._undo_paused - 1)

        self._push_undo(
            UndoCommand(
                action_type=UndoActionType.SORT_CHANGE,
                description="Sort: Clear",
                do=lambda: _apply(after),
                undo=lambda: _apply(before),
                timestamp=time.time(),
            )
        )
