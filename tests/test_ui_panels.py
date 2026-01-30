"""
UI/UX Panels 테스트 - Spotfire 스타일 UI 컴포넌트
"""

import pytest
import polars as pl
from unittest.mock import MagicMock, patch
import sys

# Qt imports
from PySide6.QtWidgets import QApplication

# Ensure QApplication exists
app = QApplication.instance()
if not app:
    app = QApplication([])

from data_graph_studio.ui.panels.filter_panel import (
    FilterWidget,
    FilterPanelModel,
    FilterType as UIFilterType,
    RangeSliderWidget,
    CheckboxListWidget,
    TextSearchWidget,
)

from data_graph_studio.ui.panels.property_panel import (
    PropertyPanel,
    PropertyItem,
    PropertyGroup,
    PropertyType,
    ColorPickerWidget,
    FontPickerWidget,
)

from data_graph_studio.ui.panels.tooltip_config import (
    TooltipConfig,
    TooltipItem,
    TooltipFormatter,
)

from data_graph_studio.ui.panels.legend_panel import (
    LegendConfig,
    LegendPosition,
    LegendStyle,
)

from data_graph_studio.ui.panels.color_scheme import (
    ColorScheme,
    ColorPalette,
    ColorScale,
    ColorSchemeManager,
)


class TestFilterPanelModel:
    """FilterPanelModel 테스트"""

    @pytest.fixture
    def sample_data(self):
        return pl.DataFrame({
            "id": [1, 2, 3, 4, 5],
            "category": ["A", "A", "B", "B", "C"],
            "sales": [100, 200, 150, 250, 80],
            "active": [True, False, True, False, True],
            "date": pl.date_range(pl.date(2024, 1, 1), pl.date(2024, 1, 5), eager=True)
        })

    def test_init(self, sample_data):
        """초기화"""
        model = FilterPanelModel()
        model.set_data(sample_data)

        assert model.column_count() == 5

    def test_detect_filter_type(self, sample_data):
        """필터 타입 자동 감지"""
        model = FilterPanelModel()
        model.set_data(sample_data)

        assert model.get_filter_type("sales") == UIFilterType.RANGE
        assert model.get_filter_type("category") == UIFilterType.CHECKBOX
        assert model.get_filter_type("active") == UIFilterType.BOOLEAN

    def test_get_unique_values(self, sample_data):
        """고유값 조회"""
        model = FilterPanelModel()
        model.set_data(sample_data)

        unique = model.get_unique_values("category")

        assert "A" in unique
        assert "B" in unique
        assert "C" in unique

    def test_get_value_range(self, sample_data):
        """값 범위 조회"""
        model = FilterPanelModel()
        model.set_data(sample_data)

        min_val, max_val = model.get_value_range("sales")

        assert min_val == 80
        assert max_val == 250


class TestRangeSliderWidget:
    """RangeSliderWidget 테스트"""

    def test_init(self):
        """초기화"""
        widget = RangeSliderWidget(min_val=0, max_val=100)

        assert widget.min_value == 0
        assert widget.max_value == 100

    def test_set_range(self):
        """범위 설정"""
        widget = RangeSliderWidget(min_val=0, max_val=100)
        widget.set_range(20, 80)

        assert widget.current_min == 20
        assert widget.current_max == 80

    def test_get_filter_value(self):
        """필터 값 조회"""
        widget = RangeSliderWidget(min_val=0, max_val=100)
        widget.set_range(25, 75)

        filter_val = widget.get_filter_value()

        assert filter_val == (25, 75)


class TestCheckboxListWidget:
    """CheckboxListWidget 테스트"""

    def test_init(self):
        """초기화"""
        values = ["A", "B", "C", "D"]
        widget = CheckboxListWidget(values)

        assert widget.item_count() == 4

    def test_select_all(self):
        """전체 선택"""
        widget = CheckboxListWidget(["A", "B", "C"])
        widget.select_all()

        assert widget.get_selected_values() == ["A", "B", "C"]

    def test_deselect_all(self):
        """전체 해제"""
        widget = CheckboxListWidget(["A", "B", "C"])
        widget.select_all()
        widget.deselect_all()

        assert widget.get_selected_values() == []

    def test_toggle_item(self):
        """항목 토글"""
        widget = CheckboxListWidget(["A", "B", "C"])
        widget.toggle_item("B")

        assert "B" in widget.get_selected_values()

    def test_search_filter(self):
        """검색 필터"""
        widget = CheckboxListWidget(["Apple", "Banana", "Cherry", "Date"])
        widget.set_search_filter("an")

        visible = widget.get_visible_items()

        assert "Banana" in visible
        assert "Apple" not in visible


class TestPropertyPanel:
    """PropertyPanel 테스트"""

    def test_init(self):
        """초기화"""
        panel = PropertyPanel()

        assert panel is not None

    def test_add_property_group(self):
        """속성 그룹 추가"""
        panel = PropertyPanel()

        group = PropertyGroup(name="General", expanded=True)
        panel.add_group(group)

        assert "General" in panel.get_group_names()

    def test_add_property_item(self):
        """속성 항목 추가"""
        panel = PropertyPanel()
        group = PropertyGroup(name="Appearance")
        panel.add_group(group)

        item = PropertyItem(
            name="color",
            display_name="Color",
            property_type=PropertyType.COLOR,
            value="#FF0000"
        )
        panel.add_item("Appearance", item)

        assert panel.get_value("Appearance", "color") == "#FF0000"

    def test_set_value(self):
        """값 설정"""
        panel = PropertyPanel()
        group = PropertyGroup(name="Size")
        panel.add_group(group)

        item = PropertyItem(
            name="width",
            display_name="Width",
            property_type=PropertyType.NUMBER,
            value=100
        )
        panel.add_item("Size", item)

        panel.set_value("Size", "width", 200)

        assert panel.get_value("Size", "width") == 200


class TestTooltipConfig:
    """TooltipConfig 테스트"""

    def test_init(self):
        """초기화"""
        config = TooltipConfig()

        assert config.enabled is True

    def test_add_item(self):
        """항목 추가"""
        config = TooltipConfig()

        item = TooltipItem(
            column="sales",
            display_name="Sales",
            format_string="${value:,.0f}"
        )
        config.add_item(item)

        assert len(config.items) == 1

    def test_format_tooltip(self):
        """툴팁 포맷팅"""
        config = TooltipConfig()
        config.add_item(TooltipItem(
            column="name",
            display_name="Name"
        ))
        config.add_item(TooltipItem(
            column="value",
            display_name="Value",
            format_string="{value:.2f}"
        ))

        data = {"name": "Test", "value": 123.456}
        formatter = TooltipFormatter(config)
        text = formatter.format(data)

        assert "Name" in text
        assert "Test" in text
        assert "123.46" in text

    def test_custom_template(self):
        """커스텀 템플릿"""
        config = TooltipConfig()
        config.template = "<b>{name}</b>: {value}"

        formatter = TooltipFormatter(config)
        text = formatter.format({"name": "Sales", "value": 100})

        assert "<b>Sales</b>" in text


class TestLegendConfig:
    """LegendConfig 테스트"""

    def test_init(self):
        """초기화"""
        config = LegendConfig()

        assert config.visible is True
        assert config.position == LegendPosition.RIGHT

    def test_set_position(self):
        """위치 설정"""
        config = LegendConfig()
        config.position = LegendPosition.BOTTOM

        assert config.position == LegendPosition.BOTTOM

    def test_set_style(self):
        """스타일 설정"""
        config = LegendConfig()
        config.style = LegendStyle.HORIZONTAL

        assert config.style == LegendStyle.HORIZONTAL


class TestColorScheme:
    """ColorScheme 테스트"""

    def test_init(self):
        """초기화"""
        scheme = ColorScheme(
            name="Custom",
            colors=["#FF0000", "#00FF00", "#0000FF"]
        )

        assert scheme.name == "Custom"
        assert len(scheme.colors) == 3

    def test_get_color(self):
        """색상 조회"""
        scheme = ColorScheme(
            name="Test",
            colors=["#FF0000", "#00FF00", "#0000FF"]
        )

        assert scheme.get_color(0) == "#FF0000"
        assert scheme.get_color(1) == "#00FF00"
        assert scheme.get_color(3) == "#FF0000"  # 순환

    def test_interpolate(self):
        """색상 보간"""
        scale = ColorScale(
            colors=["#000000", "#FFFFFF"],
            positions=[0.0, 1.0]
        )

        color = scale.interpolate(0.5)

        # 중간 회색
        assert color is not None


class TestColorSchemeManager:
    """ColorSchemeManager 테스트"""

    @pytest.fixture
    def manager(self):
        return ColorSchemeManager()

    def test_builtin_schemes(self, manager):
        """내장 스킴 확인"""
        schemes = manager.list_schemes()

        assert "Categorical" in schemes or len(schemes) > 0

    def test_add_scheme(self, manager):
        """스킴 추가"""
        scheme = ColorScheme(
            name="MyColors",
            colors=["#111111", "#222222"]
        )
        manager.add_scheme(scheme)

        assert "MyColors" in manager.list_schemes()

    def test_get_scheme(self, manager):
        """스킴 조회"""
        scheme = ColorScheme(
            name="TestScheme",
            colors=["#AAAAAA"]
        )
        manager.add_scheme(scheme)

        retrieved = manager.get_scheme("TestScheme")

        assert retrieved is not None
        assert retrieved.name == "TestScheme"

    def test_remove_scheme(self, manager):
        """스킴 제거"""
        scheme = ColorScheme(name="ToRemove", colors=["#000000"])
        manager.add_scheme(scheme)
        manager.remove_scheme("ToRemove")

        assert "ToRemove" not in manager.list_schemes()
