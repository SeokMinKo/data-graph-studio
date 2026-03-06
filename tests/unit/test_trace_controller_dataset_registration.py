from __future__ import annotations

import pytest
import polars as pl


@pytest.mark.qt
def test_trace_dataset_registration_binds_profiles_to_project_node(
    qtbot, monkeypatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    from data_graph_studio.ui.main_window import MainWindow

    # Avoid modal dialogs blocking CI.
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "about", lambda *a, **k: QMessageBox.Ok)

    w = MainWindow()
    qtbot.addWidget(w)

    # Minimal blocklayer-converted-like dataframe that satisfies preset columns.
    df = pl.DataFrame(
        {
            "send_time": [1.0, 2.0],
            "complete_time": [1.1, 2.2],
            "lba_mb": [0.1, 0.2],
            "d2c_ms": [0.1, 0.2],
            "c2c_ms": [0.0, 1.1],
            "d2d_ms": [0.0, 1.0],
            "size_kb": [4.0, 8.0],
            "cmd": ["R", "W"],
            "q2d_ms": [0.05, 0.06],
            "queue_depth": [1, 2],
        }
    )

    dataset_id = w.engine.load_dataset_from_dataframe(
        df, name="raw-trace", source_path="/tmp/raw-trace.csv"
    )
    assert dataset_id is not None

    # Before registration, state has no metadata for this dataset id.
    assert w.state.get_dataset_metadata(dataset_id) is None

    w._trace_ctrl._register_loaded_dataset(
        dataset_id,
        name="Trace Project",
        source_path="/tmp/raw-trace.csv",
        df=df,
    )

    metadata = w.state.get_dataset_metadata(dataset_id)
    assert metadata is not None
    assert metadata.name == "Trace Project"
    assert w.state.active_dataset_id == dataset_id

    # Profiles from presets should be created under the same dataset(project) id.
    w._trace_ctrl._apply_graph_presets(df, converter="blocklayer")
    profiles = list(w.profile_store.get_by_dataset(dataset_id))
    assert len(profiles) > 0
    assert all(p.dataset_id == dataset_id for p in profiles)

    w.close()
