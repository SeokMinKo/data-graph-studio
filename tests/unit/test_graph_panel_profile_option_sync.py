from __future__ import annotations

from data_graph_studio.core.data_engine import DataEngine
from data_graph_studio.core.state import AppState
from data_graph_studio.ui.panels.graph_panel import GraphPanel
import numpy as np


def test_apply_options_clears_title_and_subtitle_when_empty(qtbot):
    state = AppState()
    engine = DataEngine()
    panel = GraphPanel(state, engine)
    qtbot.addWidget(panel)

    panel.apply_options({"title": "Profile A", "subtitle": "Sub A"})
    assert panel.options_panel.chart_title_edit.text() == "Profile A"
    assert panel.options_panel.chart_subtitle_edit.text() == "Sub A"

    # Switch to profile without title/subtitle: fields should be cleared
    panel.apply_options({"title": "", "subtitle": ""})
    assert panel.options_panel.chart_title_edit.text() == ""
    assert panel.options_panel.chart_subtitle_edit.text() == ""


def test_main_graph_applies_title_and_subtitle_in_render(qtbot):
    state = AppState()
    engine = DataEngine()
    panel = GraphPanel(state, engine)
    qtbot.addWidget(panel)

    panel.main_graph.plot_data(
        np.array([1.0, 2.0, 3.0]),
        np.array([10.0, 20.0, 30.0]),
        options={"title": "CPU", "subtitle": "Profile A"},
    )

    html = panel.main_graph.plotItem.titleLabel.text
    assert "CPU" in html
    assert "Profile A" in html
