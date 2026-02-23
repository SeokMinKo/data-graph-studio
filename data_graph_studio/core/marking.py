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
        """선택이 있는지 확인"""
        return len(self.selected_indices) > 0

    @property
    def count(self) -> int:
        """선택된 인덱스 수"""
        return len(self.selected_indices)

    def select(self, indices: Set[int], mode: MarkMode = MarkMode.REPLACE) -> None:
        """
        인덱스 선택

        Args:
            indices: 선택할 인덱스 집합
            mode: 선택 모드 (REPLACE, ADD, REMOVE, TOGGLE, INTERSECT)
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
        """선택 클리어"""
        self.selected_indices.clear()
        self._table_selections.clear()

    def select_for_table(
        self,
        indices: Set[int],
        table_name: str,
        mode: MarkMode = MarkMode.REPLACE
    ) -> None:
        """
        특정 테이블에 대한 선택

        Args:
            indices: 선택할 인덱스 집합
            table_name: 테이블 이름
            mode: 선택 모드
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
        """특정 테이블의 선택된 인덱스 반환"""
        return self._table_selections.get(table_name, set())

    def clear_for_table(self, table_name: str) -> None:
        """특정 테이블의 선택 클리어"""
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
        """모든 마킹"""
        return self._markings

    @property
    def active_marking(self) -> str:
        """현재 활성 마킹 이름"""
        return self._active_marking

    def create_marking(self, name: str, color: Optional[str] = None) -> Marking:
        """
        새 마킹 생성

        Args:
            name: 마킹 이름
            color: 마킹 색상 (없으면 자동 할당)

        Returns:
            생성된 Marking 객체

        Raises:
            ValueError: 이미 존재하는 마킹 이름
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
        """
        마킹 제거

        Args:
            name: 마킹 이름

        Raises:
            ValueError: Main 마킹은 제거 불가
            KeyError: 존재하지 않는 마킹
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
        """
        활성 마킹 변경

        Args:
            name: 마킹 이름

        Raises:
            KeyError: 존재하지 않는 마킹
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
        """
        마킹에 인덱스 선택

        Args:
            marking_name: 마킹 이름
            indices: 선택할 인덱스 집합
            mode: 선택 모드
            table_name: 테이블 이름 (다중 테이블 시)

        Raises:
            KeyError: 존재하지 않는 마킹
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
        """Alias for mark(). Provided for API compatibility."""
        self.mark(marking_name, indices, mode, table_name)

    def mark_active(
        self,
        indices: Set[int],
        mode: MarkMode = MarkMode.REPLACE,
        table_name: Optional[str] = None
    ) -> None:
        """
        활성 마킹에 인덱스 선택

        Args:
            indices: 선택할 인덱스 집합
            mode: 선택 모드
            table_name: 테이블 이름
        """
        self.mark(self._active_marking, indices, mode, table_name)

    def get_marked(
        self,
        marking_name: str,
        table_name: Optional[str] = None
    ) -> Set[int]:
        """
        마킹된 인덱스 조회

        Args:
            marking_name: 마킹 이름
            table_name: 테이블 이름

        Returns:
            선택된 인덱스 집합

        Raises:
            KeyError: 존재하지 않는 마킹
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
        """
        마킹 클리어

        Args:
            marking_name: 마킹 이름
            table_name: 특정 테이블만 클리어

        Raises:
            KeyError: 존재하지 않는 마킹
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
        """모든 마킹 클리어"""
        for name, marking in self._markings.items():
            marking.clear()
            self.emit("marking_changed", name, set())

    def get_all_marked(self) -> Set[int]:
        """
        모든 마킹의 선택된 인덱스 합집합

        Returns:
            모든 마킹에서 선택된 인덱스 집합
        """
        result: Set[int] = set()
        for marking in self._markings.values():
            result.update(marking.selected_indices)
        return result

    def get_intersection(self, marking_names: List[str]) -> Set[int]:
        """
        여러 마킹의 교집합

        Args:
            marking_names: 마킹 이름 목록

        Returns:
            교집합 인덱스
        """
        if not marking_names:
            return set()

        result = set(self._markings[marking_names[0]].selected_indices)

        for name in marking_names[1:]:
            if name in self._markings:
                result.intersection_update(self._markings[name].selected_indices)

        return result

    def get_difference(self, marking_a: str, marking_b: str) -> Set[int]:
        """
        두 마킹의 차집합 (A - B)

        Args:
            marking_a: 마킹 A 이름
            marking_b: 마킹 B 이름

        Returns:
            차집합 인덱스 (A에는 있고 B에는 없는)
        """
        set_a = self._markings.get(marking_a, Marking("", "")).selected_indices
        set_b = self._markings.get(marking_b, Marking("", "")).selected_indices

        return set_a - set_b

    def is_marked(self, marking_name: str, index: int) -> bool:
        """
        특정 인덱스가 마킹되어 있는지 확인

        Args:
            marking_name: 마킹 이름
            index: 확인할 인덱스

        Returns:
            마킹 여부
        """
        if marking_name not in self._markings:
            return False
        return index in self._markings[marking_name].selected_indices

    def get_marking_names(self) -> List[str]:
        """
        모든 마킹 이름 목록

        Returns:
            마킹 이름 목록
        """
        return list(self._markings.keys())

    def get_marking(self, name: str) -> Optional[Marking]:
        """
        마킹 객체 조회

        Args:
            name: 마킹 이름

        Returns:
            Marking 객체 또는 None
        """
        return self._markings.get(name)

    def reset(self) -> None:
        """전체 초기화"""
        self._markings.clear()
        self._active_marking = "Main"
        self._color_index = 0
        self._create_default_marking()
