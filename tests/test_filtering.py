"""
Filtering System 테스트 - Spotfire 스타일 필터링 스킴
"""

import pytest
import polars as pl
from typing import List

from data_graph_studio.core.filtering import (
    FilterType,
    FilterOperator,
    Filter,
    FilteringScheme,
    FilteringManager,
)


class TestFilter:
    """Filter 클래스 테스트"""

    def test_init(self):
        """초기화 테스트"""
        f = Filter(
            column="sales",
            operator=FilterOperator.GREATER_THAN,
            value=100
        )

        assert f.column == "sales"
        assert f.operator == FilterOperator.GREATER_THAN
        assert f.value == 100
        assert f.enabled is True

    def test_filter_type_numeric(self):
        """숫자 필터 타입"""
        f = Filter(
            column="sales",
            operator=FilterOperator.GREATER_THAN,
            value=100,
            filter_type=FilterType.NUMERIC
        )

        assert f.filter_type == FilterType.NUMERIC

    def test_filter_type_text(self):
        """텍스트 필터 타입"""
        f = Filter(
            column="name",
            operator=FilterOperator.CONTAINS,
            value="apple",
            filter_type=FilterType.TEXT
        )

        assert f.filter_type == FilterType.TEXT

    def test_disable_enable(self):
        """필터 활성화/비활성화"""
        f = Filter(
            column="sales",
            operator=FilterOperator.GREATER_THAN,
            value=100
        )

        assert f.enabled is True
        f.enabled = False
        assert f.enabled is False


class TestFilteringScheme:
    """FilteringScheme 클래스 테스트"""

    def test_init(self):
        """초기화 테스트"""
        scheme = FilteringScheme(name="Main")

        assert scheme.name == "Main"
        assert len(scheme.filters) == 0

    def test_add_filter(self):
        """필터 추가"""
        scheme = FilteringScheme(name="Main")
        f = Filter(
            column="sales",
            operator=FilterOperator.GREATER_THAN,
            value=100
        )
        scheme.add_filter(f)

        assert len(scheme.filters) == 1
        assert scheme.filters[0].column == "sales"

    def test_remove_filter(self):
        """필터 제거"""
        scheme = FilteringScheme(name="Main")
        f1 = Filter(column="sales", operator=FilterOperator.GREATER_THAN, value=100)
        f2 = Filter(column="region", operator=FilterOperator.EQUALS, value="Asia")

        scheme.add_filter(f1)
        scheme.add_filter(f2)
        scheme.remove_filter(0)

        assert len(scheme.filters) == 1
        assert scheme.filters[0].column == "region"

    def test_clear_filters(self):
        """모든 필터 클리어"""
        scheme = FilteringScheme(name="Main")
        scheme.add_filter(Filter(column="a", operator=FilterOperator.EQUALS, value=1))
        scheme.add_filter(Filter(column="b", operator=FilterOperator.EQUALS, value=2))

        scheme.clear()

        assert len(scheme.filters) == 0

    def test_get_enabled_filters(self):
        """활성화된 필터만 조회"""
        scheme = FilteringScheme(name="Main")
        f1 = Filter(column="a", operator=FilterOperator.EQUALS, value=1)
        f2 = Filter(column="b", operator=FilterOperator.EQUALS, value=2, enabled=False)

        scheme.add_filter(f1)
        scheme.add_filter(f2)

        enabled = scheme.get_enabled_filters()

        assert len(enabled) == 1
        assert enabled[0].column == "a"

    def test_has_active_filters(self):
        """활성 필터 존재 여부"""
        scheme = FilteringScheme(name="Main")
        assert not scheme.has_active_filters

        scheme.add_filter(Filter(column="a", operator=FilterOperator.EQUALS, value=1))
        assert scheme.has_active_filters

        scheme.filters[0].enabled = False
        assert not scheme.has_active_filters


class TestFilteringManager:
    """FilteringManager 클래스 테스트"""

    @pytest.fixture
    def manager(self):
        """FilteringManager 인스턴스"""
        return FilteringManager()

    @pytest.fixture
    def sample_data(self):
        """샘플 데이터"""
        return pl.DataFrame({
            "id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "name": ["Apple", "Banana", "Cherry", "Date", "Elderberry",
                     "Fig", "Grape", "Honeydew", "Apple", "Banana"],
            "sales": [100, 200, 150, 300, 50, 400, 250, 180, 90, 220],
            "region": ["Asia", "Europe", "Asia", "America", "Europe",
                       "Asia", "America", "Europe", "Asia", "America"],
            "active": [True, True, False, True, False, True, True, False, True, True]
        })

    def test_init(self, manager):
        """초기화 테스트 - 기본 필터링 스킴 존재"""
        assert "Page" in manager.schemes
        assert manager.active_scheme == "Page"

    def test_create_scheme(self, manager):
        """필터링 스킴 생성"""
        manager.create_scheme("Custom")

        assert "Custom" in manager.schemes

    def test_create_scheme_duplicate(self, manager):
        """중복 스킴 생성 방지"""
        with pytest.raises(ValueError):
            manager.create_scheme("Page")

    def test_remove_scheme(self, manager):
        """스킴 제거"""
        manager.create_scheme("Temp")
        manager.remove_scheme("Temp")

        assert "Temp" not in manager.schemes

    def test_remove_page_scheme_error(self, manager):
        """Page 스킴 제거 불가"""
        with pytest.raises(ValueError):
            manager.remove_scheme("Page")

    def test_add_filter(self, manager):
        """필터 추가"""
        received = []
        manager.subscribe("filter_changed", lambda s: received.append(s))
        manager.add_filter(
            scheme_name="Page",
            column="sales",
            operator=FilterOperator.GREATER_THAN,
            value=100
        )
        assert len(manager.schemes["Page"].filters) == 1
        assert received == ["Page"]

    def test_remove_filter(self, manager):
        """필터 제거"""
        manager.add_filter("Page", "sales", FilterOperator.GREATER_THAN, 100)
        manager.add_filter("Page", "region", FilterOperator.EQUALS, "Asia")

        received = []
        manager.subscribe("filter_changed", lambda s: received.append(s))
        manager.remove_filter("Page", 0)

        assert len(manager.schemes["Page"].filters) == 1
        assert manager.schemes["Page"].filters[0].column == "region"
        assert received == ["Page"]

    def test_toggle_filter(self, manager):
        """필터 토글"""
        manager.add_filter("Page", "sales", FilterOperator.GREATER_THAN, 100)

        received = []
        manager.subscribe("filter_changed", lambda s: received.append(s))
        manager.toggle_filter("Page", 0)

        assert manager.schemes["Page"].filters[0].enabled is False
        assert received == ["Page"]

    def test_clear_filters(self, manager):
        """필터 클리어"""
        manager.add_filter("Page", "a", FilterOperator.EQUALS, 1)
        manager.add_filter("Page", "b", FilterOperator.EQUALS, 2)

        received = []
        manager.subscribe("filter_changed", lambda s: received.append(s))
        manager.clear_filters("Page")

        assert len(manager.schemes["Page"].filters) == 0
        assert received == ["Page"]

    def test_apply_filters_greater_than(self, manager, sample_data):
        """필터 적용 - GREATER_THAN"""
        manager.add_filter("Page", "sales", FilterOperator.GREATER_THAN, 200)

        result = manager.apply_filters("Page", sample_data)

        # 모든 결과가 sales > 200이어야 함
        assert len(result) > 0
        assert all(result["sales"].to_list()[i] > 200 for i in range(len(result)))

    def test_apply_filters_less_than(self, manager, sample_data):
        """필터 적용 - LESS_THAN"""
        manager.add_filter("Page", "sales", FilterOperator.LESS_THAN, 150)

        result = manager.apply_filters("Page", sample_data)

        assert all(v < 150 for v in result["sales"].to_list())

    def test_apply_filters_equals(self, manager, sample_data):
        """필터 적용 - EQUALS"""
        manager.add_filter("Page", "region", FilterOperator.EQUALS, "Asia")

        result = manager.apply_filters("Page", sample_data)

        assert all(v == "Asia" for v in result["region"].to_list())

    def test_apply_filters_not_equals(self, manager, sample_data):
        """필터 적용 - NOT_EQUALS"""
        manager.add_filter("Page", "region", FilterOperator.NOT_EQUALS, "Asia")

        result = manager.apply_filters("Page", sample_data)

        assert all(v != "Asia" for v in result["region"].to_list())

    def test_apply_filters_contains(self, manager, sample_data):
        """필터 적용 - CONTAINS"""
        manager.add_filter("Page", "name", FilterOperator.CONTAINS, "an")

        result = manager.apply_filters("Page", sample_data)

        assert all("an" in v.lower() for v in result["name"].to_list())

    def test_apply_filters_starts_with(self, manager, sample_data):
        """필터 적용 - STARTS_WITH"""
        manager.add_filter("Page", "name", FilterOperator.STARTS_WITH, "A")

        result = manager.apply_filters("Page", sample_data)

        assert all(v.startswith("A") for v in result["name"].to_list())

    def test_apply_filters_ends_with(self, manager, sample_data):
        """필터 적용 - ENDS_WITH"""
        manager.add_filter("Page", "name", FilterOperator.ENDS_WITH, "e")

        result = manager.apply_filters("Page", sample_data)

        assert all(v.endswith("e") for v in result["name"].to_list())

    def test_apply_filters_in_list(self, manager, sample_data):
        """필터 적용 - IN_LIST"""
        manager.add_filter("Page", "region", FilterOperator.IN_LIST, ["Asia", "Europe"])

        result = manager.apply_filters("Page", sample_data)

        assert all(v in ["Asia", "Europe"] for v in result["region"].to_list())

    def test_apply_filters_between(self, manager, sample_data):
        """필터 적용 - BETWEEN"""
        manager.add_filter("Page", "sales", FilterOperator.BETWEEN, (100, 200))

        result = manager.apply_filters("Page", sample_data)

        assert all(100 <= v <= 200 for v in result["sales"].to_list())

    def test_apply_filters_is_null(self, manager):
        """필터 적용 - IS_NULL"""
        data = pl.DataFrame({
            "a": [1, None, 3, None, 5],
            "b": ["x", "y", None, "w", None]
        })

        manager.add_filter("Page", "a", FilterOperator.IS_NULL, None)
        result = manager.apply_filters("Page", data)

        assert len(result) == 2

    def test_apply_filters_is_not_null(self, manager):
        """필터 적용 - IS_NOT_NULL"""
        data = pl.DataFrame({
            "a": [1, None, 3, None, 5],
        })

        manager.add_filter("Page", "a", FilterOperator.IS_NOT_NULL, None)
        result = manager.apply_filters("Page", data)

        assert len(result) == 3

    def test_apply_multiple_filters(self, manager, sample_data):
        """다중 필터 적용"""
        manager.add_filter("Page", "sales", FilterOperator.GREATER_THAN, 100)
        manager.add_filter("Page", "region", FilterOperator.EQUALS, "Asia")

        result = manager.apply_filters("Page", sample_data)

        assert all(v > 100 for v in result["sales"].to_list())
        assert all(v == "Asia" for v in result["region"].to_list())

    def test_apply_disabled_filter_ignored(self, manager, sample_data):
        """비활성화된 필터는 무시"""
        manager.add_filter("Page", "sales", FilterOperator.GREATER_THAN, 9999)
        manager.toggle_filter("Page", 0)  # 비활성화

        result = manager.apply_filters("Page", sample_data)

        assert len(result) == 10  # 필터 무시됨

    def test_get_filter_indices(self, manager, sample_data):
        """필터된 인덱스 조회"""
        manager.add_filter("Page", "region", FilterOperator.EQUALS, "Asia")

        indices = manager.get_filter_indices("Page", sample_data)

        # Asia 지역: 인덱스 0, 2, 5, 8
        assert indices == {0, 2, 5, 8}

    def test_scheme_inheritance(self, manager, sample_data):
        """스킴 상속"""
        # Page 스킴에 필터 추가
        manager.add_filter("Page", "sales", FilterOperator.GREATER_THAN, 100)

        # Custom 스킴 생성 (Page 상속)
        manager.create_scheme("Custom", inherit_from="Page")

        # Custom에 추가 필터
        manager.add_filter("Custom", "region", FilterOperator.EQUALS, "Asia")

        result = manager.apply_filters("Custom", sample_data)

        # Page 필터 + Custom 필터 모두 적용
        assert all(v > 100 for v in result["sales"].to_list())
        assert all(v == "Asia" for v in result["region"].to_list())

    def test_get_scheme_names(self, manager):
        """스킴 이름 목록"""
        manager.create_scheme("A")
        manager.create_scheme("B")

        names = manager.get_scheme_names()

        assert "Page" in names
        assert "A" in names
        assert "B" in names


class TestRangeFilter:
    """범위 필터 테스트 (슬라이더 등)"""

    @pytest.fixture
    def manager(self):
        return FilteringManager()

    def test_range_filter(self, manager):
        """범위 필터"""
        manager.add_range_filter("Page", "date", "2024-01-01", "2024-12-31")

        filters = manager.schemes["Page"].filters
        assert len(filters) == 1
        assert filters[0].operator == FilterOperator.BETWEEN


class TestCheckboxFilter:
    """체크박스 필터 테스트"""

    @pytest.fixture
    def manager(self):
        return FilteringManager()

    def test_checkbox_filter(self, manager):
        """체크박스 필터 (선택된 값들만)"""
        manager.add_checkbox_filter("Page", "region", ["Asia", "Europe"])

        filters = manager.schemes["Page"].filters
        assert len(filters) == 1
        assert filters[0].operator == FilterOperator.IN_LIST
        assert filters[0].value == ["Asia", "Europe"]

    def test_update_checkbox_filter(self, manager):
        """체크박스 필터 업데이트"""
        manager.add_checkbox_filter("Page", "region", ["Asia"])

        received = []
        manager.subscribe("filter_changed", lambda s: received.append(s))
        manager.update_checkbox_filter("Page", "region", ["Asia", "Europe", "America"])

        filters = [f for f in manager.schemes["Page"].filters if f.column == "region"]
        assert len(filters) == 1
        assert filters[0].value == ["Asia", "Europe", "America"]
        assert received == ["Page"]


class TestTextSearchFilter:
    """텍스트 검색 필터 테스트"""

    @pytest.fixture
    def manager(self):
        return FilteringManager()

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame({
            "name": ["Apple", "Banana", "Cherry", "Date", "Elderberry"]
        })

    def test_text_search_filter(self, manager, sample_data):
        """텍스트 검색 필터"""
        manager.add_text_search_filter("Page", "name", "an")

        result = manager.apply_filters("Page", sample_data)

        assert len(result) == 1
        assert result["name"][0] == "Banana"

    def test_text_search_case_insensitive(self, manager, sample_data):
        """대소문자 구분 없는 검색"""
        manager.add_text_search_filter("Page", "name", "APPLE", case_sensitive=False)

        result = manager.apply_filters("Page", sample_data)

        assert len(result) == 1
        assert result["name"][0] == "Apple"
