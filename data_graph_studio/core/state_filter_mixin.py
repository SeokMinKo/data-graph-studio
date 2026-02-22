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
    """Mixin providing filter and sort management capabilities to AppState."""

    # ==================== Filters ====================

    @property
    def filters(self) -> List[FilterCondition]:
        """List of active filter conditions applied to the dataset."""
        return self._filters

    def add_filter(self, column: str, operator: str, value: Any):
        """
        Append a new filter condition and record an undo entry.

        Args:
            column: Column name to filter on.
            operator: Comparison operator (e.g. "eq", "ne", "gt", "lt", "contains").
            value: Value to compare against.

        Emits:
            filter_changed signal.
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
        """
        Remove a filter condition by index and record an undo entry.

        Args:
            index: Zero-based index of the filter to remove. No-op if out of range.

        Emits:
            filter_changed signal.
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
        """
        Remove all filter conditions and record an undo entry.

        No-op if there are no active filters.

        Emits:
            filter_changed signal.
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
        """
        Toggle the enabled state of a filter condition and record an undo entry.

        Args:
            index: Zero-based index of the filter to toggle. No-op if out of range.

        Emits:
            filter_changed signal.
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
        """List of active sort conditions applied to the dataset."""
        return self._sorts

    def set_sort(self, column: str, descending: bool = False, add: bool = False):
        """
        Set a sort condition on a column and record an undo entry.

        Any existing sort on the same column is removed before adding the new one.

        Args:
            column: Column name to sort by.
            descending: Sort in descending order if True, ascending if False.
            add: If True, add to existing sorts. If False, replace all sorts.

        Emits:
            sort_changed signal.
        """
        before = copy.deepcopy(self._sorts)

        if not add:
            self._sorts.clear()

        # 기존 정렬 제거
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
        """
        Remove all sort conditions and record an undo entry.

        No-op if there are no active sorts.

        Emits:
            sort_changed signal.
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
