"""
Filtering System - Spotfire 스타일 필터링 스킴

필터링 스킴(Filtering Scheme)은 시각화별로 독립적인 필터를 적용할 수 있는 메커니즘입니다.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import polars as pl

logger = logging.getLogger(__name__)

from data_graph_studio.core.observable import Observable
from data_graph_studio.core.metrics import get_metrics
from data_graph_studio.core.filter_helpers import FILTER_DISPATCH as _FILTER_DISPATCH
from data_graph_studio.core.exceptions import QueryError


class IFilterApplier(ABC):
    """Abstract interface for filter application strategies."""

    @abstractmethod
    def apply_filters(self, df: pl.DataFrame, filters: List) -> pl.DataFrame:
        """Apply a list of filters to a DataFrame."""
        ...

    @abstractmethod
    def get_filter_indices(self, df: pl.DataFrame, filters: List) -> pl.Series:
        """Return boolean mask for rows matching filters."""
        ...


class FilterType(Enum):
    """필터 타입"""
    NUMERIC = "numeric"        # 숫자 필터
    TEXT = "text"              # 텍스트 필터
    DATE = "date"              # 날짜 필터
    BOOLEAN = "boolean"        # 불리언 필터
    CHECKBOX = "checkbox"      # 체크박스 (다중 선택)
    RANGE = "range"            # 범위 슬라이더
    TEXT_SEARCH = "text_search"  # 텍스트 검색


class FilterOperator(Enum):
    """필터 연산자"""
    # 비교 연산자
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUALS = "ge"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUALS = "le"

    # 범위 연산자
    BETWEEN = "between"
    NOT_BETWEEN = "not_between"

    # 리스트 연산자
    IN_LIST = "in"
    NOT_IN_LIST = "not_in"

    # 문자열 연산자
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES_REGEX = "regex"

    # NULL 연산자
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"

    # 불리언 연산자
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"


@dataclass
class Filter:
    """
    단일 필터 정의
    """
    column: str
    operator: FilterOperator
    value: Any
    enabled: bool = True
    filter_type: FilterType = FilterType.NUMERIC
    case_sensitive: bool = True  # 텍스트 검색 시 대소문자 구분

    def to_expression(self) -> Optional[pl.Expr]:
        """
        Convert this filter to a Polars boolean expression.

        Returns:
            Polars filter expression, or None when the filter is disabled
            or the operator requires a value of an unsupported type.
        """
        if not self.enabled:
            return None

        handler = _FILTER_DISPATCH.get(self.operator.value)
        if handler is None:
            return None

        return handler(pl.col(self.column), self)


@dataclass
class FilteringScheme:
    """
    필터링 스킴

    시각화별로 독립적인 필터 집합을 정의합니다.
    """
    name: str
    filters: List[Filter] = field(default_factory=list)
    inherit_from: Optional[str] = None  # 상속받을 스킴

    def add_filter(self, filter_obj: Filter) -> None:
        """필터 추가"""
        self.filters.append(filter_obj)

    def remove_filter(self, index: int) -> None:
        """필터 제거"""
        if 0 <= index < len(self.filters):
            self.filters.pop(index)

    def clear(self) -> None:
        """모든 필터 클리어"""
        self.filters.clear()

    def get_enabled_filters(self) -> List[Filter]:
        """활성화된 필터만 반환"""
        return [f for f in self.filters if f.enabled]

    @property
    def has_active_filters(self) -> bool:
        """활성 필터 존재 여부"""
        return any(f.enabled for f in self.filters)

    def get_filter_by_column(self, column: str) -> Optional[Filter]:
        """컬럼으로 필터 조회"""
        for f in self.filters:
            if f.column == column:
                return f
        return None

    def update_filter_by_column(self, column: str, **kwargs) -> bool:
        """컬럼으로 필터 업데이트"""
        for f in self.filters:
            if f.column == column:
                self._apply_kwargs_to_filter(f, kwargs)
                return True
        return False

    @staticmethod
    def _apply_kwargs_to_filter(f: "Filter", kwargs: dict) -> None:
        for key, value in kwargs.items():
            if hasattr(f, key):
                setattr(f, key, value)


class FilteringManager(Observable, IFilterApplier):
    """
    필터링 관리자

    여러 필터링 스킴을 관리하고 데이터 필터링을 담당합니다.

    Events emitted:
        filter_changed(scheme_name: str)
        scheme_created(scheme_name: str)
        scheme_removed(scheme_name: str)
    """

    def __init__(self):
        super().__init__()

        self._schemes: Dict[str, FilteringScheme] = {}
        self._active_scheme: str = "Page"

        # 기본 Page 스킴 생성
        self._create_default_scheme()

    def _create_default_scheme(self) -> None:
        """기본 필터링 스킴 생성"""
        self._schemes["Page"] = FilteringScheme(name="Page")

    @property
    def schemes(self) -> Dict[str, FilteringScheme]:
        """모든 필터링 스킴"""
        return self._schemes

    @property
    def active_scheme(self) -> str:
        """현재 활성 스킴"""
        return self._active_scheme

    def create_scheme(
        self,
        name: str,
        inherit_from: Optional[str] = None
    ) -> FilteringScheme:
        """
        새 필터링 스킴 생성

        Args:
            name: 스킴 이름
            inherit_from: 상속받을 스킴 이름

        Returns:
            생성된 FilteringScheme

        Raises:
            ValueError: 이미 존재하는 스킴 이름
        """
        if name in self._schemes:
            raise ValueError(f"Scheme '{name}' already exists")

        scheme = FilteringScheme(name=name, inherit_from=inherit_from)
        self._schemes[name] = scheme

        self.emit("scheme_created", name)

        return scheme

    def remove_scheme(self, name: str) -> None:
        """
        스킴 제거

        Args:
            name: 스킴 이름

        Raises:
            ValueError: Page 스킴은 제거 불가
        """
        if name == "Page":
            raise ValueError("Cannot remove Page scheme")

        if name in self._schemes:
            del self._schemes[name]

            if self._active_scheme == name:
                self._active_scheme = "Page"

            self.emit("scheme_removed", name)

    def set_active_scheme(self, name: str) -> None:
        """활성 스킴 변경"""
        if name in self._schemes:
            self._active_scheme = name

    def add_filter(
        self,
        scheme_name: str,
        column: str,
        operator: FilterOperator,
        value: Any,
        filter_type: FilterType = FilterType.NUMERIC,
        enabled: bool = True,
        case_sensitive: bool = True
    ) -> None:
        """
        필터 추가

        Args:
            scheme_name: 스킴 이름
            column: 컬럼 이름
            operator: 연산자
            value: 필터 값
            filter_type: 필터 타입
            enabled: 활성화 여부
            case_sensitive: 대소문자 구분 (텍스트)
        """
        if scheme_name not in self._schemes:
            raise KeyError(f"Scheme '{scheme_name}' not found")

        filter_obj = Filter(
            column=column,
            operator=operator,
            value=value,
            enabled=enabled,
            filter_type=filter_type,
            case_sensitive=case_sensitive
        )

        self._schemes[scheme_name].add_filter(filter_obj)
        self.emit("filter_changed", scheme_name)

    def remove_filter(self, scheme_name: str, index: int) -> None:
        """필터 제거"""
        if scheme_name in self._schemes:
            self._schemes[scheme_name].remove_filter(index)
            self.emit("filter_changed", scheme_name)

    def toggle_filter(self, scheme_name: str, index: int) -> None:
        """필터 토글"""
        if scheme_name in self._schemes:
            filters = self._schemes[scheme_name].filters
            if 0 <= index < len(filters):
                filters[index].enabled = not filters[index].enabled
                self.emit("filter_changed", scheme_name)

    def clear_filters(self, scheme_name: str) -> None:
        """스킴의 모든 필터 클리어"""
        if scheme_name in self._schemes:
            self._schemes[scheme_name].clear()
            self.emit("filter_changed", scheme_name)

    def add_range_filter(
        self,
        scheme_name: str,
        column: str,
        min_value: Any,
        max_value: Any
    ) -> None:
        """범위 필터 추가 (슬라이더용)"""
        self.add_filter(
            scheme_name=scheme_name,
            column=column,
            operator=FilterOperator.BETWEEN,
            value=(min_value, max_value),
            filter_type=FilterType.RANGE
        )

    def add_checkbox_filter(
        self,
        scheme_name: str,
        column: str,
        selected_values: List[Any]
    ) -> None:
        """체크박스 필터 추가"""
        self.add_filter(
            scheme_name=scheme_name,
            column=column,
            operator=FilterOperator.IN_LIST,
            value=selected_values,
            filter_type=FilterType.CHECKBOX
        )

    def update_checkbox_filter(
        self,
        scheme_name: str,
        column: str,
        selected_values: List[Any]
    ) -> None:
        """체크박스 필터 업데이트"""
        if scheme_name not in self._schemes:
            return

        scheme = self._schemes[scheme_name]

        # 기존 필터 찾아서 업데이트
        for f in scheme.filters:
            if f.column == column and f.filter_type == FilterType.CHECKBOX:
                f.value = selected_values
                self.emit("filter_changed", scheme_name)
                return

        # 없으면 새로 추가
        self.add_checkbox_filter(scheme_name, column, selected_values)

    def add_text_search_filter(
        self,
        scheme_name: str,
        column: str,
        search_text: str,
        case_sensitive: bool = True
    ) -> None:
        """텍스트 검색 필터 추가"""
        self.add_filter(
            scheme_name=scheme_name,
            column=column,
            operator=FilterOperator.CONTAINS,
            value=search_text,
            filter_type=FilterType.TEXT_SEARCH,
            case_sensitive=case_sensitive
        )

    def apply_filters(
        self,
        scheme_name: str,
        data: pl.DataFrame
    ) -> pl.DataFrame:
        """
        필터 적용

        Args:
            scheme_name: 스킴 이름
            data: 원본 데이터프레임

        Returns:
            필터링된 데이터프레임
        """
        with get_metrics().timed_operation("filter.apply"):
            if scheme_name not in self._schemes:
                return data

            scheme = self._schemes[scheme_name]

            # 상속된 스킴의 필터도 적용
            all_filters = self._get_all_filters(scheme)

            result = data
            for f in all_filters:
                if f.enabled:
                    result = self._apply_single_filter(result, f)

            get_metrics().increment("filter.applied")
            return result

    def _apply_single_filter(self, data: pl.DataFrame, f: Filter) -> pl.DataFrame:
        expr = f.to_expression()
        if expr is None:
            return data
        try:
            return data.filter(expr)
        except QueryError:
            raise
        except Exception as e:
            raise QueryError(
                "Filter execution failed",
                operation="_apply_single_filter",
                context={"column": str(f.column), "operator": str(f.operator.value), "value": str(f.value)},
            ) from e

    def _get_all_filters(self, scheme: FilteringScheme) -> List[Filter]:
        """상속 포함 모든 필터 조회"""
        filters = []

        # 상속된 스킴의 필터 먼저 추가
        if scheme.inherit_from and scheme.inherit_from in self._schemes:
            parent = self._schemes[scheme.inherit_from]
            filters.extend(self._get_all_filters(parent))

        # 현재 스킴의 필터 추가
        filters.extend(scheme.filters)

        return filters

    def get_filter_indices(
        self,
        scheme_name: str,
        data: pl.DataFrame
    ) -> Set[int]:
        """필터된 행의 인덱스 집합 반환"""
        if scheme_name not in self._schemes:
            return set(range(len(data)))

        data_with_idx = data.with_row_index("__idx__")
        filtered = self.apply_filters(scheme_name, data_with_idx)
        indices = set(filtered["__idx__"].to_list())

        return indices

    def get_scheme_names(self) -> List[str]:
        """스킴 이름 목록"""
        return list(self._schemes.keys())

    def get_scheme(self, name: str) -> Optional[FilteringScheme]:
        """스킴 조회"""
        return self._schemes.get(name)

    def reset(self) -> None:
        """전체 초기화"""
        self._schemes.clear()
        self._active_scheme = "Page"
        self._create_default_scheme()
