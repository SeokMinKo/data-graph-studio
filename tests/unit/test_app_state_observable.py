from data_graph_studio.core.state import AppState

def test_app_state_not_qobject():
    try:
        from PySide6.QtCore import QObject
        state = AppState()
        assert not isinstance(state, QObject)
    except ImportError:
        pass

def test_data_loaded_event():
    received = []
    state = AppState()
    state.subscribe("data_loaded", lambda: received.append(True))
    state.emit("data_loaded")
    assert len(received) == 1

def test_summary_updated_event():
    received = []
    state = AppState()
    state.subscribe("summary_updated", lambda d: received.append(d))
    state.emit("summary_updated", {"rows": 100})
    assert received == [{"rows": 100}]

def test_dataset_added_event():
    received = []
    state = AppState()
    state.subscribe("dataset_added", lambda id_: received.append(id_))
    state.emit("dataset_added", "ds_001")
    assert received == ["ds_001"]
