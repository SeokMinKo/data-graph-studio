"""
Data Graph Studio
Big Data Visualization Tool

Usage:
    # Python API
    from data_graph_studio import DataGraphStudio, plot, load
    
    dgs = DataGraphStudio()
    dgs.load("data.csv").plot(x="Time", y=["Value"]).save("chart.png")
    
    # Quick plot
    plot("data.csv", x="Time", y="Value", output="chart.png")
    
    # CLI
    $ dgs plot data.csv -x Time -y Value -o chart.png
"""

__version__ = "0.2.0"
__author__ = "Godol"

# Python API exports
from .api import DataGraphStudio, plot, load

__all__ = [
    'DataGraphStudio',
    'plot',
    'load',
    '__version__',
]
