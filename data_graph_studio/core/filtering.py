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

from data_graph_studio.core.observable import Observable
from data_graph_studio.core.metrics import get_metrics
from data_graph_studio.core.filter_helpers import FILTER_DISPATCH as _FILTER_DISPATCH
from data_graph_studio.core.exceptions import QueryError, ValidationError
from data_graph_studio.core.constants import DEFAULT_SCHEME_NAME
from data_graph_studio.core.types import ColumnName

logger = logging.getLogger(__name__)


class IFilterApplier(ABC):
    """Abstract interface for filter application strategies."""

    @abstractmethod
    def apply_filters(self, df: pl.DataFrame, filters: List) -> pl.DataFrame:
        """Apply a list of filters to a DataFrame.

        Input: df — pl.DataFrame to filter; filters — List of filter objects
        Output: pl.DataFrame — filtered result with the same columns
        """
        ...

    @abstractmethod
    def get_filter_indices(self, df: pl.DataFrame, filters: List) -> pl.Series:
        """Return boolean mask for rows matching filters.

        Input: df — pl.DataFrame to evaluate; filters — List of filter objects
        Output: pl.Series[bool] — True for rows that pass all filters
        """
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
        """Convert this filter to a Polars boolean expression.

        Input:
            None (uses self.column, self.operator, self.value, self.enabled,
            self.case_sensitive).

        Output:
            Polars filter expression (pl.Expr) that evaluates to a boolean Series,
            or None when the filter is disabled or the operator is not registered in
            the filter dispatch table.

        Raises:
            None

        Invariants:
            - Returns None (not an error) when enabled is False.
            - Expression references self.column by name; applying it to a DataFrame
              that lacks the column will raise an error at eval time.
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
        """Append a Filter to this scheme's filter list.

        Input:
            filter_obj: A fully constructed Filter instance to add.

        Output:
            None. Side effect: filter_obj is appended to self.filters.

        Raises:
            None

        Invariants:
            - len(self.filters) increases by exactly 1.
        """
        self.filters.append(filter_obj)

    def remove_filter(self, index: int) -> None:
        """Remove the filter at the given index from this scheme.

        Input:
            index: Zero-based integer index of the filter to remove (0 <= index < len(filters)).

        Output:
            None. Side effect: filter at index is removed from self.filters.

        Raises:
            None

        Invariants:
            - No-op if index is out of bounds.
            - len(self.filters) decreases by at most 1.
        """
        if 0 <= index < len(self.filters):
            self.filters.pop(index)

    def clear(self) -> None:
        """Remove all filters from this scheme.

        Input:
            None

        Output:
            None. Side effect: self.filters is emptied.

        Raises:
            None

        Invariants:
            - len(self.filters) == 0 after the call.
        """
        self.filters.clear()

    def get_enabled_filters(self) -> List[Filter]:
        """Return only the filters that are currently enabled.

        Input:
            None

        Output:
            List of Filter objects where enabled is True. May be empty.

        Raises:
            None

        Invariants:
            - Result is a subset of self.filters.
            - Does not modify self.filters.
        """
        return [f for f in self.filters if f.enabled]

    @property
    def has_active_filters(self) -> bool:
        """Return whether any enabled filter exists on this scheme.

        Input:
            self: FilteringScheme instance.

        Output:
            True if any enabled filter exists, False otherwise.

        Raises:
            None

        Invariants:
            - Result is True iff len(get_enabled_filters()) > 0.
        """
        return any(f.enabled for f in self.filters)

    def get_filter_by_column(self, column: str) -> Optional[Filter]:
        """Return the first filter targeting the given column, or None if not found.

        Input:
            column: Column name string to look up; exact match required.

        Output:
            First matching Filter object, or None.

        Raises:
            None

        Invariants:
            - Does not modify self.filters.
        """
        for f in self.filters:
            if f.column == column:
                return f
        return None

    def update_filter_by_column(self, column: str, **kwargs) -> bool:
        """Update attributes on the first filter that targets the given column.

        Input:
            column: Column name string to identify the filter to update.
            **kwargs: Attribute name/value pairs to set on the matching Filter
                (e.g., value=10, enabled=False). Only existing Filter attributes
                are updated; unknown keys are silently ignored.

        Output:
            True if a matching filter was found and updated, False otherwise.

        Raises:
            None

        Invariants:
            - At most one filter is updated (the first match).
            - No filters are added or removed.
        """
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
        """Initialize the FilteringManager with a default 'Page' scheme.

        Output: None
        Invariants: exactly one scheme ('Page') exists and is active after construction
        """
        super().__init__()

        self._schemes: Dict[str, FilteringScheme] = {}
        self._active_scheme: str = DEFAULT_SCHEME_NAME

        # 기본 Page 스킴 생성
        self._create_default_scheme()

    def _create_default_scheme(self) -> None:
        """기본 필터링 스킴 생성"""
        self._schemes[DEFAULT_SCHEME_NAME] = FilteringScheme(name=DEFAULT_SCHEME_NAME)

    @property
    def schemes(self) -> Dict[str, FilteringScheme]:
        """Return all registered filtering schemes.

        Output: Dict[str, FilteringScheme] — live reference keyed by scheme name
        """
        return self._schemes

    @property
    def active_scheme(self) -> str:
        """Return the name of the currently active filtering scheme.

        Output: str — scheme name; always a key present in self._schemes
        """
        return self._active_scheme

    def create_scheme(
        self,
        name: str,
        inherit_from: Optional[str] = None
    ) -> FilteringScheme:
        """Create and register a new filtering scheme.

        Input:
            name: Non-empty unique name for the new scheme; must not already exist.
            inherit_from: Optional name of an existing scheme whose filters this scheme
                inherits at apply time (default None — no inheritance).

        Output:
            The newly created FilteringScheme instance.

        Raises:
            ValidationError: if a scheme with the given name already exists.

        Invariants:
            - Emits "scheme_created" event with name after successful creation.
            - Scheme is immediately accessible via self._schemes[name].
        """
        if name in self._schemes:
            raise ValidationError(
                f"Scheme '{name}' already exists",
                operation="create_scheme",
                context={"name": name},
            )

        scheme = FilteringScheme(name=name, inherit_from=inherit_from)
        self._schemes[name] = scheme

        self.emit("scheme_created", name)

        return scheme

    def remove_scheme(self, name: str) -> None:
        """Remove the named scheme from the manager.

        Input:
            name: Name of the scheme to remove; must not be "Page".

        Output:
            None. Side effect: scheme is deleted; if it was the active scheme,
            the active scheme reverts to "Page".

        Raises:
            ValidationError: if name is "Page" (the default scheme is protected).

        Invariants:
            - Emits "scheme_removed" event after successful removal.
            - No-op (no error) if name does not exist (other than "Page").
            - active_scheme is always a valid, existing scheme after the call.
        """
        if name == DEFAULT_SCHEME_NAME:
            raise ValidationError(
                "Cannot remove Page scheme",
                operation="remove_scheme",
                context={"name": name},
            )

        if name in self._schemes:
            del self._schemes[name]

            if self._active_scheme == name:
                self._active_scheme = DEFAULT_SCHEME_NAME

            self.emit("scheme_removed", name)

    def set_active_scheme(self, name: str) -> None:
        """Set the named scheme as the currently active scheme.

        Input:
            name: Name of an existing scheme to activate.

        Output:
            None.

        Raises:
            None

        Invariants:
            - No-op if name does not exist in _schemes.
            - active_scheme == name after the call when name exists.
        """
        if name in self._schemes:
            self._active_scheme = name

    def add_filter(
        self,
        scheme_name: str,
        column: ColumnName,
        operator: FilterOperator,
        value: Any,
        filter_type: FilterType = FilterType.NUMERIC,
        enabled: bool = True,
        case_sensitive: bool = True
    ) -> None:
        """Add a new filter to the named scheme.

        Input:
            scheme_name: Name of an existing scheme to add the filter to.
            column: DataFrame column name the filter targets.
            operator: FilterOperator enum value specifying the comparison operation.
            value: Filter value; type must be compatible with the column dtype and operator.
            filter_type: FilterType classification for UI purposes (default NUMERIC).
            enabled: Whether the filter is active immediately (default True).
            case_sensitive: Case sensitivity for text operators (default True).

        Output:
            None. Side effect: new Filter is appended to the scheme; "filter_changed"
            event is emitted.

        Raises:
            KeyError: if scheme_name does not exist.

        Invariants:
            - Emits "filter_changed" event with scheme_name after successful addition.
        """
        if scheme_name not in self._schemes:
            raise QueryError(f"Scheme not found: {scheme_name}", operation="get_scheme", context={"scheme_name": scheme_name})

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
        """Remove the filter at the given index from the named scheme.

        Input:
            scheme_name: Name of an existing scheme.
            index: Zero-based index of the filter to remove.

        Output:
            None. Side effect: filter removed; "filter_changed" event emitted.

        Raises:
            None

        Invariants:
            - No-op if scheme_name does not exist.
            - No-op if index is out of bounds (delegated to FilteringScheme.remove_filter).
        """
        if scheme_name in self._schemes:
            self._schemes[scheme_name].remove_filter(index)
            self.emit("filter_changed", scheme_name)

    def toggle_filter(self, scheme_name: str, index: int) -> None:
        """Toggle the enabled state of the filter at the given index in the named scheme.

        Input:
            scheme_name: Name of an existing scheme.
            index: Zero-based index of the filter to toggle (0 <= index < len(filters)).

        Output:
            None. Side effect: filter.enabled is flipped; "filter_changed" event emitted.

        Raises:
            None

        Invariants:
            - No-op if scheme_name does not exist or index is out of bounds.
        """
        if scheme_name in self._schemes:
            filters = self._schemes[scheme_name].filters
            if 0 <= index < len(filters):
                filters[index].enabled = not filters[index].enabled
                self.emit("filter_changed", scheme_name)

    def clear_filters(self, scheme_name: str) -> None:
        """Remove all filters from the named scheme.

        Input:
            scheme_name: Name of an existing scheme.

        Output:
            None. Side effect: all filters removed; "filter_changed" event emitted.

        Raises:
            None

        Invariants:
            - No-op if scheme_name does not exist.
            - len(scheme.filters) == 0 after the call when scheme exists.
        """
        if scheme_name in self._schemes:
            self._schemes[scheme_name].clear()
            self.emit("filter_changed", scheme_name)

    def add_range_filter(
        self,
        scheme_name: str,
        column: ColumnName,
        min_value: Any,
        max_value: Any
    ) -> None:
        """Add a BETWEEN range filter to the named scheme (convenience wrapper for add_filter).

        Input:
            scheme_name: Name of an existing scheme.
            column: DataFrame column name to filter on.
            min_value: Inclusive lower bound of the range.
            max_value: Inclusive upper bound of the range.

        Output:
            None. Side effect: BETWEEN filter appended; "filter_changed" event emitted.

        Raises:
            KeyError: if scheme_name does not exist.

        Invariants:
            - Equivalent to calling add_filter with operator=BETWEEN, value=(min_value, max_value).
        """
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
        column: ColumnName,
        selected_values: List[Any]
    ) -> None:
        """Add an IN_LIST filter for checkbox-style multi-value selection.

        Input:
            scheme_name: Name of an existing scheme.
            column: DataFrame column name to filter on.
            selected_values: Non-empty list of allowed values; rows matching any value pass.

        Output:
            None. Side effect: IN_LIST filter appended; "filter_changed" event emitted.

        Raises:
            KeyError: if scheme_name does not exist.

        Invariants:
            - Equivalent to calling add_filter with operator=IN_LIST, filter_type=CHECKBOX.
        """
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
        column: ColumnName,
        selected_values: List[Any]
    ) -> None:
        """Update the value of an existing checkbox (IN_LIST) filter, or add a new one if absent.

        Input:
            scheme_name: Name of an existing scheme.
            column: DataFrame column name of the checkbox filter to update.
            selected_values: New list of allowed values to set on the filter.

        Output:
            None. Side effect: matching filter's value is updated and "filter_changed" event
            emitted, or a new checkbox filter is added if none exists.

        Raises:
            None

        Invariants:
            - No-op if scheme_name does not exist.
            - At most one filter is updated (the first CHECKBOX filter matching column).
        """
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
        column: ColumnName,
        search_text: str,
        case_sensitive: bool = True
    ) -> None:
        """Add a CONTAINS text-search filter to the named scheme.

        Input:
            scheme_name: Name of an existing scheme.
            column: DataFrame column name (string dtype) to search in.
            search_text: Substring to search for; empty string matches all rows.
            case_sensitive: Whether the search is case-sensitive (default True).

        Output:
            None. Side effect: CONTAINS filter appended; "filter_changed" event emitted.

        Raises:
            KeyError: if scheme_name does not exist.

        Invariants:
            - Equivalent to calling add_filter with operator=CONTAINS, filter_type=TEXT_SEARCH.
        """
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
        """Apply all enabled filters from the named scheme (including inherited schemes) to a DataFrame.

        Input:
            scheme_name: Name of an existing scheme whose filters to apply.
            data: pl.DataFrame to filter; must not be None.

        Output:
            Filtered pl.DataFrame with the same columns. Returns data unchanged if
            scheme_name does not exist or the scheme has no enabled filters.

        Raises:
            QueryError: if any single filter fails to evaluate (e.g., type mismatch).

        Invariants:
            - Result row count <= input row count.
            - Column set is unchanged.
            - Operation is timed via MetricsCollector.timed_operation("filter.apply").
            - "filter.applied" counter is incremented after successful application.
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

    _RANGE_OPERATORS = frozenset({
        FilterOperator.GREATER_THAN,
        FilterOperator.GREATER_THAN_OR_EQUALS,
        FilterOperator.LESS_THAN,
        FilterOperator.LESS_THAN_OR_EQUALS,
    })

    def _apply_single_filter(self, data: pl.DataFrame, f: Filter) -> pl.DataFrame:
        expr = f.to_expression()
        if expr is None:
            return data
        try:
            result = data.filter(expr)
            # Exclude NaN rows for float columns with range operators.
            # Polars treats NaN as greater than all finite values (IEEE 754
            # total ordering), so NaN rows silently pass gt/ge filters.
            # We explicitly remove them for consistent SQL-like semantics.
            if (
                f.operator in self._RANGE_OPERATORS
                and f.column in result.columns
                and result[f.column].dtype.is_float()
            ):
                result = result.filter(~pl.col(f.column).is_nan())
            return result
        except QueryError:
            raise
        except (
            pl.exceptions.InvalidOperationError,
            pl.exceptions.ComputeError,
            pl.exceptions.ColumnNotFoundError,
            TypeError,
            ValueError,
        ) as e:
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
        """Return the set of row indices that pass all filters in the named scheme.

        Input:
            scheme_name: Name of an existing scheme to evaluate.
            data: pl.DataFrame to filter; must not be None.

        Output:
            Set of zero-based integer row indices for rows that pass all enabled filters.
            If scheme_name does not exist, returns the full set of indices (no filtering).

        Raises:
            QueryError: if any filter fails to evaluate.

        Invariants:
            - Result is a subset of {0, 1, ..., len(data) - 1}.
            - Equivalent to {i for i, row in enumerate(data) if all filters pass}.
        """
        if scheme_name not in self._schemes:
            return set(range(len(data)))

        data_with_idx = data.with_row_index("__idx__")
        filtered = self.apply_filters(scheme_name, data_with_idx)
        indices = set(filtered["__idx__"].to_list())

        return indices

    def get_scheme_names(self) -> List[str]:
        """Return the list of all registered scheme names.

        Input:
            None

        Output:
            List of scheme name strings in insertion order.

        Raises:
            None

        Invariants:
            - Always contains at least "Page".
            - Does not modify manager state.
        """
        return list(self._schemes.keys())

    def get_scheme(self, name: str) -> Optional[FilteringScheme]:
        """Look up and return a scheme by name.

        Input:
            name: Name of the scheme to retrieve.

        Output:
            FilteringScheme instance if name exists, or None.

        Raises:
            None

        Invariants:
            - Does not modify manager state.
        """
        return self._schemes.get(name)

    def reset(self) -> None:
        """Reset the manager to its initial state: clear all schemes and recreate the default "Page" scheme.

        Input:
            None

        Output:
            None. Side effect: all schemes and filters are removed; a fresh "Page" scheme is created.

        Raises:
            None

        Invariants:
            - After the call, exactly one scheme ("Page") exists and active_scheme == "Page".
        """
        self._schemes.clear()
        self._active_scheme = DEFAULT_SCHEME_NAME
        self._create_default_scheme()
