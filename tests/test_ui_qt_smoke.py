"""Headless Qt smoke tests.

These tests go one step beyond import-smoke:
- Ensure we can *instantiate* key Qt widgets in an offscreen environment.
- Catch errors that only appear when Qt objects are constructed (signals, layouts,
  missing resources, circular imports triggered by runtime paths, etc.).

We keep this lightweight:
- No file dialogs
- No rendering assertions
- No network / external resources

If this ever becomes flaky on CI, split into smaller tests and/or skip known
problematic widgets.
"""

from __future__ import annotations

import pytest


@pytest.mark.qt
def test_qt_can_create_main_window(qtbot) -> None:
    from data_graph_studio.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)

    # Basic sanity: window title should exist after initialization
    assert w.windowTitle() is not None

    w.close()


@pytest.mark.qt
def test_qt_can_construct_core_panels(qtbot) -> None:
    from data_graph_studio.core.state import AppState
    from data_graph_studio.ui.panels.graph_options_panel import GraphOptionsPanel
    from data_graph_studio.ui.panels.summary_panel import SummaryPanel

    state = AppState()

    graph_opts = GraphOptionsPanel(state)
    qtbot.addWidget(graph_opts)

    summary = SummaryPanel(state)
    qtbot.addWidget(summary)

    graph_opts.close()
    summary.close()


@pytest.mark.qt
def test_qt_can_open_basic_dialogs(qtbot) -> None:
    # Dialog constructors sometimes touch shortcuts/theme resources.
    from data_graph_studio.ui.main_window import MainWindow
    from data_graph_studio.core.shortcut_controller import ShortcutController
    from data_graph_studio.ui.dialogs.shortcut_help_dialog import ShortcutHelpDialog
    from data_graph_studio.ui.dialogs.command_palette_dialog import CommandPaletteDialog

    w = MainWindow()
    qtbot.addWidget(w)

    sc = ShortcutController()
    sc.register_defaults()

    dlg1 = ShortcutHelpDialog(sc, parent=w)
    qtbot.addWidget(dlg1)
    dlg1.close()

    dlg2 = CommandPaletteDialog(parent=w)
    qtbot.addWidget(dlg2)
    dlg2.close()

    w.close()
