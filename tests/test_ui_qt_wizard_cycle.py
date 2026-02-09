"""Headless New Project Wizard result application smoke test.

Simulates the post-wizard path without opening native dialogs:
- Load a dataset (so active_dataset_id exists)
- Emulate wizard result payload (graph_setting + project_name)
- Call MainWindow._apply_pending_wizard_result()

Also exercises:
- profile_controller.apply_profile()
- auto-fit scheduling
- debounced autosave scheduling (patched to avoid filesystem writes)

Goal: catch wiring/typing errors that only appear in the wizard→profile flow.
"""

from __future__ import annotations

import pytest


@pytest.mark.qt
def test_apply_pending_wizard_result_profile_cycle(qtbot, monkeypatch, sample_csv_path) -> None:
    from PySide6.QtWidgets import QMessageBox

    # Avoid modal dialogs blocking CI.
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "about", lambda *a, **k: QMessageBox.Ok)

    from data_graph_studio.core.profile import GraphSetting
    from data_graph_studio.ui.main_window import MainWindow

    w = MainWindow()
    qtbot.addWidget(w)

    # Disable update checks + autosave writing.
    w._auto_check_updates = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setattr(w._profile_ui_controller, "_autosave_active_profile", lambda: None)

    # Load dataset (ensures active_dataset_id exists)
    dataset_id = w.engine.load_dataset(sample_csv_path, name="sample")
    assert dataset_id is not None
    assert w.engine.active_dataset_id == dataset_id

    # Trigger normal UI update path
    assert w.engine.df is not None
    w.state.set_data_loaded(True, total_rows=len(w.engine.df))

    # Create a minimal graph setting as if produced by the wizard.
    # (dataset_id will be overridden to active_id inside _apply_pending_wizard_result)
    gs = GraphSetting.create_new(name="Wizard Setting", dataset_id="")

    # Emulate wizard result payload
    w._pending_wizard_result = {
        "project_name": "Wizard Project",
        "graph_setting": gs,
    }

    # Apply
    w._apply_pending_wizard_result()

    # Expect the setting is now registered
    stored = w.profile_store.get(gs.id)
    assert stored is not None
    assert stored.dataset_id == dataset_id

    # Autofit is scheduled via QTimer.singleShot(50)
    qtbot.wait(120)

    # Trigger autosave schedule path (debounced), but autosave itself is patched.
    w.state.update_chart_settings(line_width=2)
    qtbot.wait(600)

    w.close()
