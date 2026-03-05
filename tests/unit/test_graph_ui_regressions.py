from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from PySide6.QtCore import Qt

from data_graph_studio.core.data_engine import DataEngine
from data_graph_studio.core.graph_setting_mapper import GraphSettingMapper
from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.state import AppState, AggregationType, ChartType
from data_graph_studio.ui.panels.graph_options_panel import GraphOptionsPanel
from data_graph_studio.ui.panels.graph_panel import GraphPanel
from data_graph_studio.ui.panels.main_graph import MainGraph


class _DummyWheelEvent:
    def __init__(self) -> None:
        self.ignored = False

    def ignore(self) -> None:
        self.ignored = True


@pytest.mark.qt
def test_chart_options_combo_ignores_accidental_wheel_when_popup_closed(qtbot) -> None:
    state = AppState()
    panel = GraphOptionsPanel(state)
    qtbot.addWidget(panel)

    combo = panel.chart_type_combo
    initial_index = combo.currentIndex()

    event = _DummyWheelEvent()
    combo.wheelEvent(event)

    assert event.ignored is True
    assert combo.currentIndex() == initial_index


@pytest.mark.qt
def test_group_masks_order_is_stable_for_color_mapping(qtbot) -> None:
    state = AppState()
    engine = DataEngine()

    df = pl.DataFrame(
        {
            "x": np.arange(12, dtype=np.float64),
            "y": np.arange(12, dtype=np.float64),
            "grp": ["B", "C", "A", "B", "C", "A", "B", "C", "A", "B", "C", "A"],
        }
    )
    engine.update_dataframe(df)

    state.set_x_column("x")
    state.add_value_column("y", aggregation=AggregationType.MEAN)
    state.add_group_column("grp")

    panel = GraphPanel(state, engine)
    qtbot.addWidget(panel)

    keys_runs = []
    for _ in range(5):
        groups = panel._build_group_masks(df)
        keys_runs.append(tuple(groups.keys()))

    # Deterministic order is required so palette assignment does not flicker.
    assert len(set(keys_runs)) == 1
    assert keys_runs[0] == ("A", "B", "C")


@pytest.mark.qt
def test_graph_selection_maps_sampled_indices_back_to_original_rows(qtbot) -> None:
    state = AppState()
    engine = DataEngine()

    df = pl.DataFrame(
        {
            "x": np.arange(10, dtype=np.float64),
            "y": np.arange(10, dtype=np.float64),
        }
    )
    engine.update_dataframe(df)

    state.set_x_column("x")
    state.add_value_column("y", aggregation=AggregationType.MEAN)

    panel = GraphPanel(state, engine)
    qtbot.addWidget(panel)

    # Simulate sampling: rendered indices [0,1,2] correspond to original rows [2,5,9]
    panel._sampled_original_indices = np.array([2, 5, 9], dtype=np.int64)

    panel._on_graph_points_selected([1, 2])

    selected = sorted(list(state.selection.selected_rows))
    assert selected == [5, 9]

    # Visual feedback should be immediate in graph rendered index space.
    panel.main_graph._data_x = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    panel.main_graph._data_y = np.array([10.0, 20.0, 30.0], dtype=np.float64)
    panel.main_graph.highlight_selection([1])
    assert panel.main_graph._selection_scatter is not None


@pytest.mark.qt
def test_graph_panel_refresh_handles_empty_dataframe_without_error(qtbot) -> None:
    state = AppState()
    engine = DataEngine()

    # Empty frame that still has typical blocklayer columns.
    engine.update_dataframe(
        pl.DataFrame(
            {
                "send_time": [],
                "d2c_ms": [],
                "cmd": [],
                "size_kb": [],
            },
            schema={
                "send_time": pl.Float64,
                "d2c_ms": pl.Float64,
                "cmd": pl.Utf8,
                "size_kb": pl.Float64,
            },
        )
    )

    # Simulate chart settings that could previously hit division-by-zero paths.
    state.set_chart_type(ChartType.BAR)

    panel = GraphPanel(state, engine)
    qtbot.addWidget(panel)

    # Must not raise.
    panel.refresh()


def test_profile_title_subtitle_do_not_leak_between_profiles() -> None:
    state = AppState()

    setting_a = GraphSetting(
        id="a",
        name="A",
        dataset_id="ds",
        chart_type="line",
        chart_settings={"title": "Profile A", "subtitle": "Sub A"},
    )
    setting_b = GraphSetting(
        id="b",
        name="B",
        dataset_id="ds",
        chart_type="line",
        chart_settings={},
    )

    GraphSettingMapper.to_app_state(setting_a, state)
    assert state.chart_settings.title == "Profile A"
    assert state.chart_settings.subtitle == "Sub A"

    # Applying profile B with no title/subtitle must clear prior values.
    GraphSettingMapper.to_app_state(setting_b, state)
    assert state.chart_settings.title is None
    assert state.chart_settings.subtitle is None


@pytest.mark.qt
def test_set_columns_populates_color_and_marker_by_combos(qtbot) -> None:
    state = AppState()
    engine = DataEngine()
    engine.update_dataframe(pl.DataFrame({"x": [1, 2], "kind": ["A", "B"]}))

    panel = GraphPanel(state, engine)
    qtbot.addWidget(panel)
    panel.set_columns(engine.columns)

    color_items = [panel.options_panel.color_by_combo.itemText(i) for i in range(panel.options_panel.color_by_combo.count())]
    mark_items = [panel.options_panel.mark_by_combo.itemText(i) for i in range(panel.options_panel.mark_by_combo.count())]

    assert "x" in color_items and "kind" in color_items
    assert "x" in mark_items and "kind" in mark_items


@pytest.mark.qt
def test_graph_panel_set_grid_visible_updates_both_axes(qtbot) -> None:
    state = AppState()
    engine = DataEngine()
    engine.update_dataframe(pl.DataFrame({"x": [1, 2], "y": [3, 4]}))

    panel = GraphPanel(state, engine)
    qtbot.addWidget(panel)

    panel.set_grid_visible(False)
    assert panel.options_panel.grid_x_check.isChecked() is False
    assert panel.options_panel.grid_y_check.isChecked() is False

    panel.set_grid_visible(True)
    assert panel.options_panel.grid_x_check.isChecked() is True
    assert panel.options_panel.grid_y_check.isChecked() is True


@pytest.mark.qt
def test_legend_settings_include_marker_symbol() -> None:
    state = AppState()
    panel = GraphOptionsPanel(state)
    panel.set_series(["Series A"])

    marker_combo = panel._series_items[0]["marker_combo"]
    marker_combo.setCurrentIndex(marker_combo.findData("d"))

    legend = panel.get_legend_settings()
    assert legend["series"][0]["marker_symbol"] == "d"


@pytest.mark.qt
def test_graph_panel_applies_legend_marker_symbol(qtbot) -> None:
    state = AppState()
    engine = DataEngine()
    engine.update_dataframe(pl.DataFrame({"x": [0, 1, 2], "y": [1, 2, 3]}))

    state.set_x_column("x")
    state.add_value_column("y", aggregation=AggregationType.MEAN)
    state.set_chart_type(ChartType.SCATTER)

    panel = GraphPanel(state, engine)
    qtbot.addWidget(panel)
    panel.set_columns(engine.columns)

    marker_combo = panel.options_panel._series_items[0]["marker_combo"]
    marker_combo.setCurrentIndex(marker_combo.findData("d"))

    panel.refresh()

    assert len(panel.main_graph._scatter_items) >= 1
    assert panel.main_graph._scatter_items[0].opts.get("symbol") == "d"


@pytest.mark.qt
def test_main_graph_applies_legend_marker_symbol(qtbot) -> None:
    graph = MainGraph(AppState())
    qtbot.addWidget(graph)

    x = np.array([0.0, 1.0, 2.0], dtype=np.float64)
    y = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    legend_settings = {
        "show": True,
        "position": (1, 1),
        "series": [{"name": "Series A", "visible": True, "color": "#1f77b4", "marker_symbol": "d"}],
    }
    graph.plot_data(x, y, groups=None, chart_type=ChartType.SCATTER, options={"show_points": True}, legend_settings=legend_settings)

    assert len(graph._scatter_items) == 1
    assert graph._scatter_items[0].opts.get("symbol") == "d"


@pytest.mark.qt
def test_graph_options_tabs_are_readable_not_elided() -> None:
    panel = GraphOptionsPanel(AppState())
    bar = panel.tabs.tabBar()

    assert bar.elideMode() == Qt.ElideNone
    assert panel.tabs.tabText(0) == "Data"
    assert panel.tabs.tabText(1) == "Chart"
    assert panel.tabs.tabText(2) == "Legend"
    assert panel.tabs.tabText(3) == "Axes"
    assert panel.tabs.tabText(4) == "Style"
