"""
Data Graph Studio - Setup
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="data-graph-studio",
    version="0.1.0",
    author="Godol",
    author_email="",
    description="Big Data Visualization Tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Visualization",
    ],
    python_requires=">=3.9",
    install_requires=[
        "PySide6>=6.6.0",
        "polars>=0.20.0",
        "duckdb>=0.9.0",
        "pyarrow>=14.0.0",
        "pyqtgraph>=0.13.0",
        "plotly>=5.18.0",
        "numpy>=1.24.0",
        "openpyxl>=3.1.0",
        "psutil>=5.9.0",
        "click>=8.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-qt>=4.2.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
        ],
        "graph": [
            "matplotlib>=3.7.0",  # For headless graph generation
        ],
    },
    entry_points={
        "console_scripts": [
            "dgs=src.cli:main",
            "data-graph-studio=main:main",
        ],
        "gui_scripts": [
            "dgs-gui=main:main",
        ],
    },
)
