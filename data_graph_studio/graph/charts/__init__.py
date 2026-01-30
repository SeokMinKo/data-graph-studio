"""
Advanced Charts Module
"""

from .box_plot import BoxPlotChart
from .violin_plot import ViolinPlotChart
from .heatmap import HeatmapChart
from .candlestick import CandlestickChart
from .waterfall import WaterfallChart


_CHART_REGISTRY = {
    'box': BoxPlotChart,
    'violin': ViolinPlotChart,
    'heatmap': HeatmapChart,
    'candlestick': CandlestickChart,
    'waterfall': WaterfallChart,
}


def get_chart(chart_type: str):
    """차트 인스턴스 반환"""
    chart_class = _CHART_REGISTRY.get(chart_type.lower())
    if chart_class:
        return chart_class()
    return None


__all__ = [
    'BoxPlotChart',
    'ViolinPlotChart', 
    'HeatmapChart',
    'CandlestickChart',
    'WaterfallChart',
    'get_chart',
]
