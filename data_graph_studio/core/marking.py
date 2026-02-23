"""
Marking System - Spotfire 스타일 마킹 시스템

마킹(Marking)은 여러 시각화에서 동일한 데이터 선택을 공유하는 메커니즘입니다.
"""

import logging
from typing import Dict, Set, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from data_graph_studio.core.observable import Observable
from data_graph_studio.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class MarkMode(Enum):
    """마킹 모드"""
    REPLACE = "replace"      # 기존 선택 대체
    ADD = "add"              # 기존 선택에 추가
    REMOVE = "remove"        # 기존 선택에서 제거
    TOGGLE = "toggle"        # 선택 토글
    INTERSECT = "intersect"  # 교집합만 유지


@dataclass
class Marking:
    """
    단일 마킹 정의

    Spotfire의 마킹은 여러 시각화에서 공유되는 선택 상태입니다.
    """
    name: str
    color: str
    selected_indices: Set[int] = field(default_factory=set)

    # 테이블별 선택 (다중 테이블 지원)
    _table_selections: Dict[str, Set[int]] = field(default_factory=dict)

    @property
    def has_selection(self) -> bool:
        """Return True when at least one row index is selected.

        Output: bool — True when selected_indices is non-empty
        """
        return len(self.selected_indices) > 0

    @property
    def count(self) -> int:
        """Return the number of currently selected row indices.

        Output: int — len(selected_indices), >= 0
        """
        return len(self.selected_indices)

    def select(self, indices: Set[int], mode: MarkMode = MarkMode.REPLACE) -> None:
        """Update selected_indices according to the given mode.

        Input:
            indices: Set of integer row indices to apply the mode operation with.
            mode: MarkMode enum value controlling how indices are combined with the
                current selection (REPLACE, ADD, REMOVE, TOGGLE, or INTERSECT).

        Output:
            None. Side effect: self.selected_indices is updated in place.

        Raises:
            None

        Invariants:
            - REPLACE: selected_indices == set(indices) after the call.
            - ADD: selected_indices is a superset of the original.
            - REMOVE: selected_indices is a subset of the original.
            - INTERSECT: selected_indices <= original AND selected_indices <= indices.
        """
        if mode == MarkMode.REPLACE:
            self.selected_indices = set(indices)
        elif mode == MarkMode.ADD:
            self.selected_indices.update(indices)
        elif mode == MarkMode.REMOVE:
            self.selected_indices.difference_update(indices)
        elif mode == MarkMode.TOGGLE:
            # 이미 있으면 제거, 없으면 추가
            for idx in indices:
                if idx in self.selected_indices:
                    self.selected_indices.remove(idx)
                else:
                    self.selected_indices.add(idx)
        elif mode == MarkMode.INTERSECT:
            self.selected_indices.intersection_update(indices)

    def clear(self) -> None:
        """Clear all selections including per-table selections.

        Input:
            None

        Output:
            None. Side effect: selected_indices and _table_selections are emptied.

        Raises:
            None

        Invariants:
            - selected_indices == set() after the call.
            - _table_selections == {} after the call.
        """
        self.selected_indices.clear()
        self._table_selections.clear()

    def select_for_table(
        self,
        indices: Set[int],
        table_name: str,
        mode: MarkMode = MarkMode.REPLACE
    ) -> None:
        """Update the selection for a specific table.

        Input:
            indices: Set of integer row indices to apply the mode operation with.
            table_name: Non-empty string identifying the target table.
            mode: MarkMode enum value controlling the combination logic
                (REPLACE, ADD, REMOVE, TOGGLE, or INTERSECT).

        Output:
            None. Side effect: _table_selections[table_name] is updated in place.

        Raises:
            None

        Invariants:
            - table_name key always exists in _table_selections after the call.
            - global selected_indices is not affected by this method.
        """
        if table_name not in self._table_selections:
            self._table_selections[table_name] = set()

        if mode == MarkMode.REPLACE:
            self._table_selections[table_name] = set(indices)
        elif mode == MarkMode.ADD:
            self._table_selections[table_name].update(indices)
        elif mode == MarkMode.REMOVE:
            self._table_selections[table_name].difference_update(indices)
        elif mode == MarkMode.TOGGLE:
            for idx in indices:
                if idx in self._table_selections[table_name]:
                    self._table_selections[table_name].remove(idx)
                else:
                    self._table_selections[table_name].add(idx)
        elif mode == MarkMode.INTERSECT:
            self._table_selections[table_name].intersection_update(indices)

    def get_for_table(self, table_name: str) -> Set[int]:
        """Return the selected indices for a specific table.

        Input:
            table_name: Name of the table to retrieve selections for.

        Output:
            Set of selected integer row indices for the table, or an empty set if
            no selection exists for that table.

        Raises:
            None

        Invariants:
            - Returns an empty set (not None) when table_name is unknown.
            - Does not modify any state.
        """
        return self._table_selections.get(table_name, set())

    def clear_for_table(self, table_name: str) -> None:
        """Clear the selection for a specific table.

        Input:
            table_name: Name of the table whose selection to clear.

        Output:
            None. Side effect: _table_selections[table_name] is emptied if it exists.

        Raises:
            None

        Invariants:
            - No-op if table_name is not in _table_selections.
            - global selected_indices is unaffected.
        """
        if table_name in self._table_selections:
            self._table_selections[table_name].clear()


class MarkingManager(Observable):
    """
    마킹 관리자

    여러 마킹을 관리하고 시각화 간 연동을 담당합니다.
    Spotfire의 Marking 시스템과 유사한 기능을 제공합니다.
    """

    # 기본 마킹 색상
    DEFAULT_COLORS = [
        "#1f77b4",  # 파란색
        "#ff7f0e",  # 주황색
        "#2ca02c",  # 초록색
        "#d62728",  # 빨간색
        "#9467bd",  # 보라색
        "#8c564b",  # 갈색
        "#e377c2",  # 분홍색
        "#7f7f7f",  # 회색
        "#bcbd22",  # 올리브색
        "#17becf",  # 청록색
    ]

    def __init__(self):
        """Initialize the MarkingManager with a default 'Main' marking.

        Output: None
        Invariants: exactly one marking ('Main') exists and is active after construction;
                    _color_index starts at 1 (first auto-color slot after 'Main')
        """
        super().__init__()

        self._markings: Dict[str, Marking] = {}
        self._active_marking: str = "Main"
        self._color_index: int = 0

        # 기본 마킹 생성
        self._create_default_marking()

    def _create_default_marking(self) -> None:
        """기본 마킹 생성"""
        self._markings["Main"] = Marking(
            name="Main",
            color=self.DEFAULT_COLORS[0]
        )
        self._color_index = 1

    @property
    def markings(self) -> Dict[str, Marking]:
        """Return the mapping of marking name to Marking instance.

        Output: Dict[str, Marking] — live reference; always contains at least 'Main'
        """
        return self._markings

    @property
    def active_marking(self) -> str:
        """Return the name of the currently active marking.

        Output: str — marking name; always a key present in self._markings
        """
        return self._active_marking

    def create_marking(self, name: str, color: Optional[str] = None) -> Marking:
        """Create and register a new Marking with a unique name.

        Input:
            name: Non-empty unique string name for the new marking; must not already exist.
            color: Optional hex color string (e.g., "#1f77b4"). If None, the next color from
                DEFAULT_COLORS is assigned automatically.

        Output:
            The newly created Marking instance.

        Raises:
            ValidationError: if a marking with the given name already exists.

        Invariants:
            - Emits "marking_created" event with name after successful creation.
            - _color_index is incremented by 1 when color is auto-assigned.
        """
        if name in self._markings:
            raise ValidationError(
                f"Marking '{name}' already exists",
                operation="create_marking",
                context={"name": name},
            )

        if color is None:
            color = self.DEFAULT_COLORS[self._color_index % len(self.DEFAULT_COLORS)]
            self._color_index += 1

        marking = Marking(name=name, color=color)
        self._markings[name] = marking

        logger.debug("marking_manager.create", extra={"marking_name": name})
        self.emit("marking_created", name)

        return marking

    def remove_marking(self, name: str) -> None:
        """Remove the named marking from the manager.

        Input:
            name: Name of the marking to remove; must not be "Main".

        Output:
            None. Side effect: marking is deleted; if it was active, active_marking
            reverts to "Main".

        Raises:
            ValidationError: if name is "Main" (the default marking is protected).
            KeyError: if name does not exist.

        Invariants:
            - Emits "marking_removed" event after successful removal.
            - active_marking is always a valid, existing marking after the call.
        """
        if name == "Main":
            raise ValidationError(
                "Cannot remove Main marking",
                operation="remove_marking",
                context={"name": name},
            )

        if name not in self._markings:
            raise KeyError(f"Marking '{name}' not found")

        del self._markings[name]

        logger.debug("marking_manager.remove", extra={"marking_name": name})

        # 활성 마킹이 제거된 경우 Main으로 변경
        if self._active_marking == name:
            self._active_marking = "Main"
            self.emit("active_marking_changed", "Main")

        self.emit("marking_removed", name)

    def set_active_marking(self, name: str) -> None:
        """Set the named marking as the currently active marking.

        Input:
            name: Name of an existing marking to activate.

        Output:
            None. Side effect: active_marking is updated and "active_marking_changed"
            event is emitted when the marking actually changes.

        Raises:
            KeyError: if name does not exist.

        Invariants:
            - active_marking == name after the call.
            - No event is emitted if name == current active_marking.
        """
        if name not in self._markings:
            raise KeyError(f"Marking '{name}' not found")

        if self._active_marking != name:
            self._active_marking = name
            self.emit("active_marking_changed", name)

    def mark(
        self,
        marking_name: str,
        indices: Set[int],
        mode: MarkMode = MarkMode.REPLACE,
        table_name: Optional[str] = None
    ) -> None:
        """Apply a selection to the named marking.

        Input:
            marking_name: Name of an existing marking to update.
            indices: Set of integer row indices to select.
            mode: MarkMode enum value controlling how indices combine with the current
                selection (default REPLACE).
            table_name: Optional table name for per-table selection; if None, the global
                selected_indices is updated.

        Output:
            None. Side effect: marking selection is updated; "marking_changed" event is
            emitted with (marking_name, updated_indices_set).

        Raises:
            KeyError: if marking_name does not exist.

        Invariants:
            - Emits "marking_changed" with the post-update selected set.
        """
        if marking_name not in self._markings:
            raise KeyError(f"Marking '{marking_name}' not found")

        marking = self._markings[marking_name]

        if table_name:
            marking.select_for_table(indices, table_name, mode)
        else:
            marking.select(indices, mode)

        # 시그널 발생
        selected = marking.get_for_table(table_name) if table_name else marking.selected_indices
        logger.debug("marking_manager.update", extra={"marking_name": marking_name, "count": len(selected)})
        self.emit("marking_changed", marking_name, set(selected))

    def update_marking(
        self,
        marking_name: str,
        indices: Set[int],
        mode: MarkMode = MarkMode.REPLACE,
        table_name: Optional[str] = None
    ) -> None:
        """Alias for mark(). Provided for API compatibility.

        Input:
            marking_name: Name of an existing marking to update.
            indices: Set of integer row indices to select.
            mode: MarkMode enum value (default REPLACE).
            table_name: Optional table name for per-table selection.

        Output:
            None. Delegates entirely to mark().

        Raises:
            KeyError: if marking_name does not exist (propagated from mark()).

        Invariants:
            - Identical behaviour to mark() in all cases.
        """
        self.mark(marking_name, indices, mode, table_name)

    def mark_active(
        self,
        indices: Set[int],
        mode: MarkMode = MarkMode.REPLACE,
        table_name: Optional[str] = None
    ) -> None:
        """Apply a selection to the currently active marking.

        Input:
            indices: Set of integer row indices to select.
            mode: MarkMode enum value controlling combination logic (default REPLACE).
            table_name: Optional table name for per-table selection.

        Output:
            None. Delegates to mark() using the current active_marking name.

        Raises:
            KeyError: if the active marking has been removed (should not happen normally).

        Invariants:
            - Equivalent to mark(self._active_marking, indices, mode, table_name).
        """
        self.mark(self._active_marking, indices, mode, table_name)

    def get_marked(
        self,
        marking_name: str,
        table_name: Optional[str] = None
    ) -> Set[int]:
        """Return the selected indices for the named marking.

        Input:
            marking_name: Name of an existing marking to query.
            table_name: Optional table name; if provided, returns the per-table selection
                instead of the global selection.

        Output:
            Set of selected integer row indices. Returns a copy of the global selection
            when table_name is None, or the table-specific selection when provided.

        Raises:
            KeyError: if marking_name does not exist.

        Invariants:
            - Does not modify marking state.
            - Returns a copy (not a reference) of global selected_indices.
        """
        if marking_name not in self._markings:
            raise KeyError(f"Marking '{marking_name}' not found")

        marking = self._markings[marking_name]

        if table_name:
            return marking.get_for_table(table_name)
        return set(marking.selected_indices)

    def clear_marking(
        self,
        marking_name: str,
        table_name: Optional[str] = None
    ) -> None:
        """Clear the selection in the named marking.

        Input:
            marking_name: Name of an existing marking to clear.
            table_name: Optional table name; if provided, only clears the per-table
                selection; if None, clears the entire marking.

        Output:
            None. Side effect: selection is cleared; "marking_changed" event emitted
            with an empty set.

        Raises:
            KeyError: if marking_name does not exist.

        Invariants:
            - selected_indices (or table selection) is empty after the call.
            - Emits "marking_changed" with an empty set.
        """
        if marking_name not in self._markings:
            raise KeyError(f"Marking '{marking_name}' not found")

        marking = self._markings[marking_name]

        if table_name:
            marking.clear_for_table(table_name)
        else:
            marking.clear()

        self.emit("marking_changed", marking_name, set())

    def clear_all_markings(self) -> None:
        """Clear the selection in every registered marking.

        Input:
            None

        Output:
            None. Side effect: all markings are cleared; "marking_changed" event is
            emitted for each marking with an empty set.

        Raises:
            None

        Invariants:
            - All markings have empty selected_indices after the call.
        """
        for name, marking in self._markings.items():
            marking.clear()
            self.emit("marking_changed", name, set())

    def get_all_marked(self) -> Set[int]:
        """Return the union of selected indices across all markings.

        Input:
            None

        Output:
            Set of integer row indices that are selected in at least one marking.
            Returns an empty set if no markings have selections.

        Raises:
            None

        Invariants:
            - Result is a superset of each individual marking's selected_indices.
            - Does not modify marking state.
        """
        result: Set[int] = set()
        for marking in self._markings.values():
            result.update(marking.selected_indices)
        return result

    def get_intersection(self, marking_names: List[str]) -> Set[int]:
        """Return the intersection of selected indices across the specified markings.

        Input:
            marking_names: List of marking name strings to intersect.
                Names that do not exist are silently skipped after the first element.

        Output:
            Set of integer row indices selected in ALL listed markings. Returns an empty
            set if marking_names is empty.

        Raises:
            KeyError: if the first marking name in the list does not exist.

        Invariants:
            - Result is a subset of each individual marking's selected_indices.
            - Does not modify marking state.
        """
        if not marking_names:
            return set()

        result = set(self._markings[marking_names[0]].selected_indices)

        for name in marking_names[1:]:
            if name in self._markings:
                result.intersection_update(self._markings[name].selected_indices)

        return result

    def get_difference(self, marking_a: str, marking_b: str) -> Set[int]:
        """Return indices in marking A that are not in marking B (set difference A - B).

        Input:
            marking_a: Name of the first marking (minuend); returns empty set if not found.
            marking_b: Name of the second marking (subtrahend); treated as empty if not found.

        Output:
            Set of integer row indices present in marking_a but absent from marking_b.

        Raises:
            None

        Invariants:
            - Result is a subset of marking_a.selected_indices.
            - Does not modify marking state.
        """
        set_a = self._markings.get(marking_a, Marking("", "")).selected_indices
        set_b = self._markings.get(marking_b, Marking("", "")).selected_indices

        return set_a - set_b

    def is_marked(self, marking_name: str, index: int) -> bool:
        """Check whether a specific row index is selected in the named marking.

        Input:
            marking_name: Name of the marking to query.
            index: Zero-based integer row index to test.

        Output:
            True if index is in the marking's selected_indices, False otherwise.
            Returns False if marking_name does not exist.

        Raises:
            None

        Invariants:
            - Does not modify marking state.
        """
        if marking_name not in self._markings:
            return False
        return index in self._markings[marking_name].selected_indices

    def get_marking_names(self) -> List[str]:
        """Return a list of all registered marking names.

        Input:
            None

        Output:
            List of marking name strings in insertion order.

        Raises:
            None

        Invariants:
            - Always contains at least "Main".
            - Does not modify manager state.
        """
        return list(self._markings.keys())

    def get_marking(self, name: str) -> Optional[Marking]:
        """Look up and return a Marking by name.

        Input:
            name: Name of the marking to retrieve.

        Output:
            Marking instance if name exists, or None.

        Raises:
            None

        Invariants:
            - Does not modify manager state.
        """
        return self._markings.get(name)

    def reset(self) -> None:
        """Reset the manager to its initial state: clear all markings and recreate the default "Main" marking.

        Input:
            None

        Output:
            None. Side effect: all markings are removed; a fresh "Main" marking is created
            and active_marking is set to "Main".

        Raises:
            None

        Invariants:
            - After the call, exactly one marking ("Main") exists and active_marking == "Main".
            - _color_index is reset to 0 before the default marking is created.
        """
        self._markings.clear()
        self._active_marking = "Main"
        self._color_index = 0
        self._create_default_marking()
