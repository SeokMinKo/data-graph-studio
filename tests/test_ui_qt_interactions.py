"""Headless Qt interaction smoke tests.

These tests validate that common UI actions can be *triggered* without crashing.
They are intentionally light on assertions; the goal is to catch regressions like:
- signal/slot wiring errors
- missing attributes/resources
- side effects that explode only when actions are triggered

Rules:
- Never open native file dialogs
- No network access
- Keep runtime small
"""

from __future__ import annotations

import pytest


@pytest.mark.qt
def test_toggle_common_view_actions(qtbot) -> None:
    from data_graph_studio.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)

    # Prevent background update check from doing anything during tests.
    w._auto_check_updates = lambda: None  # type: ignore[attr-defined]

    # Graph element toggles (checkable actions)
    assert w._show_grid_action is not None
    assert w._show_legend_action is not None

    prev_grid = w._show_grid_action.isChecked()
    w._show_grid_action.trigger()
    assert w._show_grid_action.isChecked() != prev_grid

    prev_legend = w._show_legend_action.isChecked()
    w._show_legend_action.trigger()
    assert w._show_legend_action.isChecked() != prev_legend

    # Toggle back (idempotency / no crash)
    w._show_grid_action.trigger()
    w._show_legend_action.trigger()

    w.close()


@pytest.mark.qt
def test_toggle_dashboard_mode_action_does_not_block(qtbot, monkeypatch) -> None:
    """Dashboard mode shows QMessageBox when no data is loaded.

    In headless CI this can block the test run, so we patch QMessageBox to be non-modal.
    """

    from PySide6.QtWidgets import QMessageBox

    # Make message boxes non-blocking for tests
    monkeypatch.setattr(
        QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)

    from data_graph_studio.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)

    w._auto_check_updates = lambda: None  # type: ignore[attr-defined]

    action = w._dashboard_mode_action
    assert action is not None

    # With no data loaded, this should *return* and uncheck the action.
    action.setChecked(True)
    action.trigger()
    assert action.isChecked() is False

    w.close()


@pytest.mark.qt
def test_state_signal_path_does_not_crash(qtbot) -> None:
    """Emit a few AppState updates that UI commonly listens to.

    This catches issues where slots assume widgets are present.
    """

    from data_graph_studio.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)

    w._auto_check_updates = lambda: None  # type: ignore[attr-defined]

    # AppState update → should propagate to UI without raising
    w.state.update_chart_settings(line_width=3)
    w.state.update_chart_settings(marker_size=8)
    w.state.update_chart_settings(show_data_labels=True)

    w.close()
