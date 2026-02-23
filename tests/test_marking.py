"""
Marking System 테스트 - Spotfire 스타일 마킹 시스템
"""

import pytest

from data_graph_studio.core.marking import (
    Marking,
    MarkMode,
    MarkingManager,
)


class TestMarking:
    """Marking 클래스 테스트"""

    def test_init(self):
        """초기화 테스트"""
        marking = Marking(name="Main", color="#ff0000")

        assert marking.name == "Main"
        assert marking.color == "#ff0000"
        assert len(marking.selected_indices) == 0

    def test_init_with_indices(self):
        """인덱스와 함께 초기화"""
        marking = Marking(
            name="Test",
            color="#00ff00",
            selected_indices={1, 2, 3}
        )

        assert len(marking.selected_indices) == 3
        assert 1 in marking.selected_indices

    def test_select(self):
        """선택 테스트"""
        marking = Marking(name="Main", color="#ff0000")
        marking.select({1, 2, 3})

        assert len(marking.selected_indices) == 3
        assert marking.has_selection

    def test_select_replace(self):
        """선택 대체 테스트"""
        marking = Marking(name="Main", color="#ff0000")
        marking.select({1, 2, 3})
        marking.select({4, 5}, mode=MarkMode.REPLACE)

        assert len(marking.selected_indices) == 2
        assert 1 not in marking.selected_indices
        assert 4 in marking.selected_indices

    def test_select_add(self):
        """선택 추가 테스트"""
        marking = Marking(name="Main", color="#ff0000")
        marking.select({1, 2, 3})
        marking.select({4, 5}, mode=MarkMode.ADD)

        assert len(marking.selected_indices) == 5

    def test_select_remove(self):
        """선택 제거 테스트"""
        marking = Marking(name="Main", color="#ff0000")
        marking.select({1, 2, 3, 4, 5})
        marking.select({2, 4}, mode=MarkMode.REMOVE)

        assert len(marking.selected_indices) == 3
        assert 2 not in marking.selected_indices
        assert 4 not in marking.selected_indices

    def test_select_toggle(self):
        """선택 토글 테스트"""
        marking = Marking(name="Main", color="#ff0000")
        marking.select({1, 2, 3})
        marking.select({2, 4}, mode=MarkMode.TOGGLE)

        assert len(marking.selected_indices) == 3
        assert 2 not in marking.selected_indices  # 토글로 제거
        assert 4 in marking.selected_indices      # 토글로 추가

    def test_select_intersect(self):
        """선택 교집합 테스트"""
        marking = Marking(name="Main", color="#ff0000")
        marking.select({1, 2, 3, 4, 5})
        marking.select({2, 3, 6}, mode=MarkMode.INTERSECT)

        assert len(marking.selected_indices) == 2
        assert 2 in marking.selected_indices
        assert 3 in marking.selected_indices
        assert 1 not in marking.selected_indices

    def test_clear(self):
        """클리어 테스트"""
        marking = Marking(name="Main", color="#ff0000")
        marking.select({1, 2, 3})
        marking.clear()

        assert len(marking.selected_indices) == 0
        assert not marking.has_selection

    def test_has_selection(self):
        """선택 여부 테스트"""
        marking = Marking(name="Main", color="#ff0000")
        assert not marking.has_selection

        marking.select({1})
        assert marking.has_selection

    def test_count(self):
        """선택 개수 테스트"""
        marking = Marking(name="Main", color="#ff0000")
        assert marking.count == 0

        marking.select({1, 2, 3})
        assert marking.count == 3


class TestMarkingManager:
    """MarkingManager 클래스 테스트"""

    @pytest.fixture
    def manager(self, qtbot):
        """MarkingManager 인스턴스"""
        return MarkingManager()

    def test_init(self, manager):
        """초기화 테스트 - 기본 마킹 존재"""
        assert "Main" in manager.markings
        assert manager.active_marking == "Main"

    def test_create_marking(self, manager):
        """마킹 생성 테스트"""
        manager.create_marking("Comparison", "#00ff00")

        assert "Comparison" in manager.markings
        assert manager.markings["Comparison"].color == "#00ff00"

    def test_create_marking_duplicate(self, manager):
        """중복 마킹 생성 방지 테스트"""
        with pytest.raises(ValueError):
            manager.create_marking("Main", "#00ff00")  # 이미 존재

    def test_remove_marking(self, manager):
        """마킹 제거 테스트"""
        manager.create_marking("Temp", "#0000ff")
        manager.remove_marking("Temp")

        assert "Temp" not in manager.markings

    def test_remove_main_marking_error(self, manager):
        """Main 마킹 제거 불가 테스트"""
        with pytest.raises(ValueError):
            manager.remove_marking("Main")

    def test_set_active_marking(self, manager):
        """활성 마킹 변경 테스트"""
        manager.create_marking("Secondary", "#00ff00")
        manager.set_active_marking("Secondary")

        assert manager.active_marking == "Secondary"

    def test_set_active_marking_invalid(self, manager):
        """존재하지 않는 마킹 활성화 오류"""
        with pytest.raises(KeyError):
            manager.set_active_marking("NotExists")

    def test_mark(self, manager):
        """마킹 테스트"""
        manager.mark("Main", {1, 2, 3})

        assert manager.get_marked("Main") == {1, 2, 3}

    def test_mark_add(self, manager):
        """마킹 추가 테스트"""
        manager.mark("Main", {1, 2, 3})
        manager.mark("Main", {4, 5}, mode=MarkMode.ADD)

        assert manager.get_marked("Main") == {1, 2, 3, 4, 5}

    def test_mark_active(self, manager):
        """활성 마킹에 마킹 테스트"""
        manager.mark_active({1, 2, 3})

        assert manager.get_marked("Main") == {1, 2, 3}

    def test_clear_marking(self, manager):
        """마킹 클리어 테스트"""
        manager.mark("Main", {1, 2, 3})
        manager.clear_marking("Main")

        assert manager.get_marked("Main") == set()

    def test_clear_all_markings(self, manager, qtbot):
        """모든 마킹 클리어 테스트"""
        manager.create_marking("Secondary", "#00ff00")
        manager.mark("Main", {1, 2, 3})
        manager.mark("Secondary", {4, 5, 6})

        manager.clear_all_markings()

        assert manager.get_marked("Main") == set()
        assert manager.get_marked("Secondary") == set()

    def test_get_marked_invalid(self, manager):
        """존재하지 않는 마킹 조회 오류"""
        with pytest.raises(KeyError):
            manager.get_marked("NotExists")

    def test_get_all_marked(self, manager):
        """모든 마킹된 인덱스 조회"""
        manager.create_marking("Secondary", "#00ff00")
        manager.mark("Main", {1, 2, 3})
        manager.mark("Secondary", {3, 4, 5})

        all_marked = manager.get_all_marked()

        assert all_marked == {1, 2, 3, 4, 5}

    def test_get_intersection(self, manager):
        """마킹 교집합 테스트"""
        manager.create_marking("Secondary", "#00ff00")
        manager.mark("Main", {1, 2, 3, 4})
        manager.mark("Secondary", {3, 4, 5, 6})

        intersection = manager.get_intersection(["Main", "Secondary"])

        assert intersection == {3, 4}

    def test_get_difference(self, manager):
        """마킹 차집합 테스트"""
        manager.create_marking("Secondary", "#00ff00")
        manager.mark("Main", {1, 2, 3, 4})
        manager.mark("Secondary", {3, 4, 5, 6})

        difference = manager.get_difference("Main", "Secondary")

        assert difference == {1, 2}

    def test_is_marked(self, manager):
        """특정 인덱스 마킹 여부 테스트"""
        manager.mark("Main", {1, 2, 3})

        assert manager.is_marked("Main", 1)
        assert manager.is_marked("Main", 2)
        assert not manager.is_marked("Main", 5)

    def test_get_marking_names(self, manager):
        """마킹 이름 목록 테스트"""
        manager.create_marking("A", "#ff0000")
        manager.create_marking("B", "#00ff00")

        names = manager.get_marking_names()

        assert "Main" in names
        assert "A" in names
        assert "B" in names

    def test_signal_emit_with_marking_name(self, manager):
        """이벤트 발생 시 마킹 이름 전달"""
        received = []

        def on_marking_changed(name, indices):
            received.append((name, indices))

        manager.subscribe("marking_changed", on_marking_changed)
        manager.mark("Main", {1, 2, 3})

        assert len(received) == 1
        assert received[0][0] == "Main"
        assert received[0][1] == {1, 2, 3}


class TestMarkingManagerMultiTable:
    """다중 테이블 마킹 테스트"""

    @pytest.fixture
    def manager(self, qtbot):
        """MarkingManager 인스턴스"""
        return MarkingManager()

    def test_mark_with_table(self, manager):
        """테이블별 마킹 테스트"""
        manager.mark("Main", {1, 2, 3}, table_name="orders")
        manager.mark("Main", {4, 5, 6}, table_name="customers")

        assert manager.get_marked("Main", table_name="orders") == {1, 2, 3}
        assert manager.get_marked("Main", table_name="customers") == {4, 5, 6}

    def test_clear_marking_by_table(self, manager):
        """테이블별 마킹 클리어"""
        manager.mark("Main", {1, 2, 3}, table_name="orders")
        manager.mark("Main", {4, 5, 6}, table_name="customers")

        manager.clear_marking("Main", table_name="orders")

        assert manager.get_marked("Main", table_name="orders") == set()
        assert manager.get_marked("Main", table_name="customers") == {4, 5, 6}
