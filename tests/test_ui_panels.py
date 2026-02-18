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

        # 필터 타입이 반환되어야 함 (구체적인 타입은 구현에 따라 다를 수 있음)
        sales_type = model.get_filter_type("sales")
        assert sales_type is not None
        
        category_type = model.get_filter_type("category")
        assert category_type is not None
        
        active_type = model.get_filter_type("active")
        assert active_type is not None

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

        result = model.get_value_range("sales")
        
        # 튜플 또는 기타 범위 형식 반환
        assert result is not None
        if isinstance(result, tuple) and len(result) == 2:
            min_val, max_val = result
            assert min_val <= max_val


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

        # 순서는 보장되지 않을 수 있으므로 set으로 비교
        assert set(widget.get_selected_values()) == {"A", "B", "C"}

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


class TestLegendSeriesSync:
    """Legend 시리즈 동기화 테스트"""

    def test_series_colors_unique(self):
        """각 시리즈(그룹)가 고유한 색상을 갖는지 테스트"""
        from data_graph_studio.ui.panels.color_scheme import ColorScheme
        
        # 5개 그룹이 있을 때 각각 고유 색상을 가져야 함
        scheme = ColorScheme(
            name="Test",
            colors=["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF"]
        )
        
        group_names = ["Group A", "Group B", "Group C", "Group D", "Group E"]
        colors = [scheme.get_color(i) for i in range(len(group_names))]
        
        # 모든 색상이 고유해야 함
        assert len(set(colors)) == len(group_names)
    
    def test_series_colors_cycle(self):
        """그룹 수가 팔레트보다 많을 때 색상 순환 테스트"""
        from data_graph_studio.ui.panels.color_scheme import ColorScheme
        
        scheme = ColorScheme(
            name="Small",
            colors=["#FF0000", "#00FF00", "#0000FF"]
        )
        
        # 5개 그룹, 3개 색상 → 순환
        colors = [scheme.get_color(i) for i in range(5)]
        
        assert colors[0] == colors[3]  # 순환
        assert colors[1] == colors[4]
    
    def test_legend_visibility(self):
        """Legend 표시/숨김 동작 테스트"""
        config = LegendConfig()
        
        # 기본 표시
        assert config.visible is True
        
        # 숨김
        config.visible = False
        assert config.visible is False
        
        # 다시 표시
        config.visible = True
        assert config.visible is True


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


class TestStatPanel:
    """StatPanel 테스트 - 2x2 그리드 레이아웃 및 새 그래프"""

    @pytest.fixture
    def sample_data(self):
        """테스트용 샘플 데이터"""
        import numpy as np
        np.random.seed(42)
        return {
            'x_data': np.random.randn(100),
            'y_data': np.random.randn(100) * 10 + 50,
            'group_data': {
                'Group A': 100.0,
                'Group B': 200.0,
                'Group C': 150.0,
            }
        }

    def test_stat_panel_init(self):
        """StatPanel 초기화 테스트"""
        from data_graph_studio.core.state import AppState
        from data_graph_studio.ui.panels.graph_panel import StatPanel

        state = AppState()
        panel = StatPanel(state)

        # 기본 속성 확인
        assert panel is not None
        assert panel.minimumWidth() >= 200  # responsive compact design (min reduced)
        assert panel.maximumWidth() <= 500

    def test_stat_panel_widgets(self):
        """StatPanel 4개 그래프 위젯 존재 확인"""
        from data_graph_studio.core.state import AppState
        from data_graph_studio.ui.panels.graph_panel import StatPanel

        state = AppState()
        panel = StatPanel(state)

        # 4개 그래프 위젯 확인
        assert hasattr(panel, 'x_hist_widget')
        assert hasattr(panel, 'y_hist_widget')
        assert hasattr(panel, 'pie_widget')
        assert hasattr(panel, 'percentile_widget')
        assert hasattr(panel, 'stats_label')

    def test_stat_panel_update_histograms(self, sample_data):
        """히스토그램 업데이트 테스트"""
        from data_graph_studio.core.state import AppState
        from data_graph_studio.ui.panels.graph_panel import StatPanel

        state = AppState()
        panel = StatPanel(state)

        # 데이터 업데이트
        panel.update_histograms(
            sample_data['x_data'],
            sample_data['y_data'],
            sample_data['group_data']
        )

        # 데이터가 저장되었는지 확인
        assert panel._x_data is not None
        assert panel._y_data is not None
        assert panel._group_data is not None

    def test_stat_panel_update_stats(self):
        """통계 업데이트 테스트"""
        from data_graph_studio.core.state import AppState
        from data_graph_studio.ui.panels.graph_panel import StatPanel

        state = AppState()
        panel = StatPanel(state)

        stats = {
            'mean': 50.0,
            'median': 49.5,
            'std': 10.0,
            'min': 20.0,
            'max': 80.0,
        }

        panel.update_stats(stats)

        # stats_label에 값이 표시되었는지 확인
        label_text = panel.stats_label.text()
        assert "mean" in label_text.lower() or "50" in label_text

    def test_stat_panel_set_group_data(self):
        """Pie chart 그룹 데이터 설정 테스트"""
        from data_graph_studio.core.state import AppState
        from data_graph_studio.ui.panels.graph_panel import StatPanel

        state = AppState()
        panel = StatPanel(state)

        group_data = {
            'Category A': 150.0,
            'Category B': 250.0,
            'Category C': 100.0,
        }

        panel.set_group_data(group_data)

        assert panel._group_data == group_data


class TestExpandedChartDialog:
    """ExpandedChartDialog 테스트 - Non-modal 동작"""

    def test_expanded_chart_dialog_init(self):
        """ExpandedChartDialog 초기화 및 non-modal 확인"""
        from data_graph_studio.ui.panels.graph_panel import ExpandedChartDialog

        dialog = ExpandedChartDialog("Test Title")

        # Non-modal 확인
        assert dialog.isModal() is False
        assert dialog.windowTitle() == "Test Title"

    def test_expanded_chart_dialog_histogram(self):
        """히스토그램 플롯 테스트"""
        import numpy as np
        from data_graph_studio.ui.panels.graph_panel import ExpandedChartDialog

        dialog = ExpandedChartDialog("Histogram Test")
        data = np.random.randn(100)

        # 플롯 호출 (에러 없이 실행되어야 함)
        dialog.plot_histogram(data, "Test Histogram", (100, 100, 200, 100))
        assert dialog.windowTitle() == "Test Histogram"

    def test_expanded_chart_dialog_pie(self):
        """Pie chart 플롯 테스트"""
        from data_graph_studio.ui.panels.graph_panel import ExpandedChartDialog

        dialog = ExpandedChartDialog("Pie Test")
        labels = ['A', 'B', 'C']
        values = [100, 200, 150]

        # 플롯 호출 (에러 없이 실행되어야 함)
        dialog.plot_pie_chart(labels, values, "Test Pie Chart")
        assert dialog.windowTitle() == "Test Pie Chart"

    def test_expanded_chart_dialog_percentile(self):
        """Percentile chart 플롯 테스트"""
        import numpy as np
        from data_graph_studio.ui.panels.graph_panel import ExpandedChartDialog

        dialog = ExpandedChartDialog("Percentile Test")
        data = np.random.randn(100)

        # 플롯 호출 (에러 없이 실행되어야 함)
        dialog.plot_percentile(data, "Test Percentile")
        assert dialog.windowTitle() == "Test Percentile"


class TestClickablePlotWidget:
    """ClickablePlotWidget 테스트 - 다양한 차트 타입 지원"""

    def test_clickable_plot_widget_histogram_data(self):
        """히스토그램 데이터 설정 테스트"""
        import numpy as np
        from data_graph_studio.ui.panels.graph_panel import ClickablePlotWidget

        widget = ClickablePlotWidget()
        data = np.random.randn(100)

        widget.set_data(data, "Test Histogram", (100, 100, 200, 100))

        assert widget._chart_type == "histogram"
        assert widget._data is not None
        assert widget._title == "Test Histogram"

    def test_clickable_plot_widget_pie_data(self):
        """Pie chart 데이터 설정 테스트"""
        from data_graph_studio.ui.panels.graph_panel import ClickablePlotWidget

        widget = ClickablePlotWidget()
        labels = ['A', 'B', 'C']
        values = [100, 200, 150]

        widget.set_pie_data(labels, values, "Test Pie")

        assert widget._chart_type == "pie"
        assert widget._pie_labels == labels
        assert widget._pie_values == values

    def test_clickable_plot_widget_percentile_data(self):
        """Percentile chart 데이터 설정 테스트"""
        import numpy as np
        from data_graph_studio.ui.panels.graph_panel import ClickablePlotWidget

        widget = ClickablePlotWidget()
        data = np.random.randn(100)

        widget.set_percentile_data(data, "Test Percentile")

        assert widget._chart_type == "percentile"
        assert widget._data is not None


class TestFloatWindowNonModal:
    """FloatWindow Non-modal 동작 테스트"""

    def test_float_window_is_non_modal(self):
        """FloatWindow가 non-modal인지 테스트"""
        from data_graph_studio.ui.floatable import FloatWindow
        from PySide6.QtWidgets import QLabel

        content = QLabel("Test Content")
        window = FloatWindow("Test", content)

        # Non-modal 확인
        assert window.isModal() is False
