from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from data_graph_studio.core.data_engine import DataEngine
from data_graph_studio.core.state import AppState, AggregationType
from data_graph_studio.ui.panels.graph_panel import GraphPanel
from data_graph_studio.ui.panels.minimap_widget import MinimapWidget


@pytest.mark.qt
def test_minimap_downsamples_to_50k_max(qtbot) -> None:
    w = MinimapWidget()
    qtbot.addWidget(w)

    x = np.arange(120_000, dtype=np.float64)
    y = np.sin(x / 1000.0)
    w.set_data(x, y)

    assert w._data_item is not None
    x_plot, y_plot = w._data_item.getData()
    assert len(x_plot) <= 50_000
    assert len(y_plot) <= 50_000


@pytest.mark.qt
def test_minimap_region_emits_xy_ranges_on_drag(qtbot) -> None:
    w = MinimapWidget()
    qtbot.addWidget(w)

    x = np.linspace(0.0, 100.0, 2000)
    y = np.linspace(-20.0, 20.0, 2000)
    w.set_data(x, y)
    w.set_region(10.0, 30.0, -5.0, 5.0)

    events: list[tuple[float, float, float, float]] = []
    w.region_changed.connect(lambda x1, x2, y1, y2: events.append((x1, x2, y1, y2)))

    # Simulate rectangle drag by moving ROI and invoking change callback.
    w._viewport_roi.setPos((20.0, -3.0), finish=False)
    w._on_viewport_changed()

    assert events, "region_changed was not emitted"
    x1, x2, y1, y2 = events[-1]
    assert pytest.approx(x2 - x1, rel=1e-6) == 20.0
    assert pytest.approx(y2 - y1, rel=1e-6) == 10.0


@pytest.mark.qt
def test_graph_panel_minimap_overlay_fit_and_region_sync(qtbot) -> None:
    state = AppState()
    engine = DataEngine()

    df = pl.DataFrame(
        {
            "x": np.linspace(0.0, 1000.0, 2000),
            "y": np.sin(np.linspace(0.0, 40.0, 2000)) * 100.0,
        }
    )
    engine.update_dataframe(df)

    state.set_x_column("x")
    state.add_value_column("y", aggregation=AggregationType.MEAN)

    panel = GraphPanel(state, engine)
    qtbot.addWidget(panel)
    panel.resize(1000, 700)
    panel.show()

    panel.toggle_minimap(True)
    panel.refresh()

    assert panel._minimap_overlay.isVisible()
    assert panel.minimap.get_data_bounds() is not None

    # Narrow current range, then Fit should expand the visible window.
    panel.main_graph.setXRange(100.0, 200.0, padding=0)
    panel.main_graph.setYRange(-10.0, 10.0, padding=0)
    before = panel.main_graph.viewRange()

    panel._on_minimap_fit_clicked()
    after_fit = panel.main_graph.viewRange()
    assert (after_fit[0][1] - after_fit[0][0]) > (before[0][1] - before[0][0])

    # Dragging minimap viewport should move main graph range as well.
    panel._on_minimap_region_changed(300.0, 450.0, -30.0, 30.0)
    moved = panel.main_graph.viewRange()
    assert pytest.approx(moved[0][0], rel=1e-3) == 300.0
    assert pytest.approx(moved[0][1], rel=1e-3) == 450.0
    assert pytest.approx(moved[1][0], rel=1e-3) == -30.0
    assert pytest.approx(moved[1][1], rel=1e-3) == 30.0
