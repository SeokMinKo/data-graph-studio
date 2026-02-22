"""
graph_panel package — backward-compatible re-export of GraphPanel.

The original ``ui/panels/graph_panel.py`` module has been refactored into:
  graph_panel/
    __init__.py              ← this file (re-exports GraphPanel)
    graph_panel.py           ← coordinator (~550 lines)
    drawing_tools.py         ← DrawingToolsMixin
    renderers/
      __init__.py
      combo_renderer.py      ← ComboChartMixin
      statistical_renderer.py ← StatisticalChartMixin
      grid_renderer.py       ← GridChartMixin

All existing ``from .panels.graph_panel import GraphPanel`` imports continue
to work unchanged because this ``__init__.py`` re-exports the class.
"""

from .graph_panel import GraphPanel  # noqa: F401

# Re-export symbols that the original graph_panel.py module exposed at the
# top level (via imports from sibling modules).  External code that does
# ``from data_graph_studio.ui.panels.graph_panel import MainGraph`` (or any
# of the other names below) continues to work after the module-to-package
# rename.
from ..main_graph import MainGraph  # noqa: F401
from ..graph_widgets import (  # noqa: F401
    ColorButton,
    ExpandedChartDialog,
    ClickablePlotWidget,
    FormattedAxisItem,
)
from ..graph_options_panel import GraphOptionsPanel  # noqa: F401
from ..stat_panel import StatPanel  # noqa: F401

__all__ = [
    "GraphPanel",
    "MainGraph",
    "ColorButton",
    "ExpandedChartDialog",
    "ClickablePlotWidget",
    "FormattedAxisItem",
    "GraphOptionsPanel",
    "StatPanel",
]
