"""Headless end-to-end-ish UI cycle smoke test.

Covers a common lifecycle without native dialogs:
1) load a real sample CSV via DataEngine
2) notify AppState (data_loaded) → MainWindow updates panels
3) exercise a few UI operations (refresh/autofit/tab switching)

Goal: catch regressions that require *both* data + widget wiring.
"""

from __future__ import annotations

import pytest


@pytest.mark.qt
def test_headless_load_refresh_tab_cycle(qtbot, monkeypatch, sample_csv_path) -> None:
    from PySide6.QtWidgets import QMessageBox

    # Avoid modal dialogs blocking CI.
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "about", lambda *a, **k: QMessageBox.Ok)

    from data_graph_studio.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)

    # Disable update checks during tests.
    w._auto_check_updates = lambda: None  # type: ignore[attr-defined]

    # Load data without using file dialogs/controllers.
    ok = w.engine.load_file(sample_csv_path)
    assert ok is True
    assert w.engine.df is not None

    # Trigger the normal UI update path.
    w.state.set_data_loaded(True, total_rows=len(w.engine.df))

    # Sanity: panels should have been updated.
    assert w.state.is_data_loaded is True

    # DataTab should know the columns.
    data_tab = w.graph_panel.options_panel.data_tab
    assert len(getattr(data_tab, "_all_columns", [])) > 0

    # Exercise a few common operations.
    w.graph_panel.refresh()
    w.graph_panel.autofit()
    w.summary_panel.refresh()

    # Tab switching smoke: options panel uses QTabWidget.
    tabs = getattr(w.graph_panel.options_panel, "tabs", None) or getattr(
        w.graph_panel.options_panel, "tab_widget", None
    )
    if tabs is not None and hasattr(tabs, "count") and tabs.count() > 1:
        tabs.setCurrentIndex(1)
        tabs.setCurrentIndex(0)

    # Clear data cycle should also not crash.
    w.state.set_data_loaded(False)

    w.close()
