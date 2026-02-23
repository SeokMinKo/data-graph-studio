"""Tests for MiniGraphWidget profile settings rendering."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

# Ensure QApplication exists
_app = QApplication.instance()
if _app is None:
    _app = QApplication([])


def _make_graph_setting(**overrides):
    """Create a minimal GraphSetting-like object."""
    from data_graph_studio.core.profile import GraphSetting

    defaults = {
        "id": "test-id",
        "name": "Test Profile",
        "dataset_id": "ds-1",
        "chart_type": "line",
        "x_column": "x",
        "value_columns": ({"name": "y1", "color": "#ff0000"},),
        "group_columns": (),
        "hover_columns": (),
    }
    defaults.update(overrides)
    return GraphSetting(**defaults)


def _make_engine_mock(df=None, numeric_cols=None):
    """Create a mock engine that returns the given df."""
    engine = MagicMock()
    ds = MagicMock()
    ds.df = df
    ds.row_count = len(df) if df is not None else 0
    engine.get_dataset.return_value = ds
    engine.get_numeric_columns.return_value = numeric_cols or []
    return engine


def _make_state_mock():
    """Create a mock AppState."""
    state = MagicMock()
    metadata = MagicMock()
    metadata.color = "#1f77b4"
    metadata.name = "Test Dataset"
    state.get_dataset_metadata.return_value = metadata
    state.x_column = None
    state.value_columns = []
    state.group_columns = []
    state.hover_columns = []
    # Prevent MagicMock auto-attribute from breaking pyqtgraph color parsing
    state._chart_settings = None
    return state


def _make_widget(graph_setting=None, qtbot=None):
    """Create a MiniGraphWidget for testing (with real QWidget)."""
    from data_graph_studio.ui.panels.side_by_side_layout import MiniGraphWidget

    engine = _make_engine_mock()
    state = _make_state_mock()
    widget = MiniGraphWidget("ds-1", engine, state, graph_setting=graph_setting)
    if qtbot:
        qtbot.addWidget(widget)
    return widget


class TestEffectiveProperties:
    """Test effective_* properties honor graph_setting."""

    def test_effective_chart_type_from_setting(self, qtbot):
        gs = _make_graph_setting(chart_type="scatter")
        widget = _make_widget(graph_setting=gs, qtbot=qtbot)
        assert widget.effective_chart_type == "scatter"

    def test_effective_chart_type_default(self, qtbot):
        gs = _make_graph_setting(chart_type="")
        widget = _make_widget(graph_setting=gs, qtbot=qtbot)
        assert widget.effective_chart_type == "line"

    def test_effective_value_columns_from_setting(self, qtbot):
        gs = _make_graph_setting(
            value_columns=({"name": "a"}, {"name": "b"}, {"name": "c"})
        )
        widget = _make_widget(graph_setting=gs, qtbot=qtbot)
        names = [vc["name"] for vc in widget.effective_value_columns]
        assert names == ["a", "b", "c"]

    def test_effective_group_columns_from_setting(self, qtbot):
        gs = _make_graph_setting(group_columns=("category",))
        widget = _make_widget(graph_setting=gs, qtbot=qtbot)
        assert widget.effective_group_columns == ["category"]

    def test_effective_hover_columns_from_setting(self, qtbot):
        gs = _make_graph_setting(hover_columns=("tooltip1", "tooltip2"))
        widget = _make_widget(graph_setting=gs, qtbot=qtbot)
        assert widget.effective_hover_columns == ["tooltip1", "tooltip2"]


class TestPlotDataRendering:
    """Test _render_series dispatches to correct pyqtgraph items."""

    def test_render_series_scatter(self, qtbot):
        """_render_series with scatter uses ScatterPlotItem."""
        import numpy as np
        widget = _make_widget(qtbot=qtbot)
        widget.plot_widget = MagicMock()

        pg = MagicMock()
        widget._render_series(
            np.array([1.0, 2.0, 3.0]),
            np.array([10.0, 20.0, 30.0]),
            "#ff0000", "scatter", pg, np, name="test",
        )
        pg.ScatterPlotItem.assert_called_once()
        widget.plot_widget.addItem.assert_called_once()

    def test_render_series_bar(self, qtbot):
        """_render_series with bar uses BarGraphItem."""
        import numpy as np
        widget = _make_widget(qtbot=qtbot)
        widget.plot_widget = MagicMock()

        pg = MagicMock()
        widget._render_series(
            np.array([1.0, 2.0, 3.0]),
            np.array([10.0, 20.0, 30.0]),
            "#00ff00", "bar", pg, np, name="test",
        )
        pg.BarGraphItem.assert_called_once()
        widget.plot_widget.addItem.assert_called_once()

    def test_render_series_line(self, qtbot):
        """_render_series with line uses plot()."""
        import numpy as np
        widget = _make_widget(qtbot=qtbot)
        widget.plot_widget = MagicMock()

        pg = MagicMock()
        widget._render_series(
            np.array([1.0, 2.0]),
            np.array([10.0, 20.0]),
            "#0000ff", "line", pg, np,
        )
        widget.plot_widget.plot.assert_called_once()

    def test_sample_downsamples(self, qtbot):
        """_sample reduces array to max_points."""
        import numpy as np

        widget = _make_widget(qtbot=qtbot)
        x = np.arange(5000)
        y = np.arange(5000)
        x_s, y_s = widget._sample(x, y, np, max_points=1000)
        assert len(x_s) <= 1000
        assert len(y_s) <= 1000

    def test_sample_no_downsample_small(self, qtbot):
        """_sample does not downsample small arrays."""
        import numpy as np

        widget = _make_widget(qtbot=qtbot)
        x = np.arange(500)
        y = np.arange(500)
        x_s, y_s = widget._sample(x, y, np, max_points=1000)
        assert len(x_s) == 500
