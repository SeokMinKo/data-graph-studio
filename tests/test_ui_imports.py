"""UI import smoke tests.

Goal: catch import-time errors in UI modules (e.g., NameError from type annotations)
without requiring a GUI display.

We intentionally keep this lightweight: import-only, no QApplication creation.
"""

import importlib


def _import(module: str) -> None:
    importlib.import_module(module)


def test_import_graph_options_panel() -> None:
    _import("data_graph_studio.ui.panels.graph_options_panel")


def test_import_data_tab() -> None:
    _import("data_graph_studio.ui.panels.data_tab")


def test_import_main_window() -> None:
    # This should be import-safe (no QApplication side effects).
    _import("data_graph_studio.ui.main_window")
