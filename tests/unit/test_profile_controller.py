import time
import uuid

from data_graph_studio.core.graph_setting_mapper import GraphSettingMapper
from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.profile_controller import ProfileController
from data_graph_studio.core.profile_store import ProfileStore
from data_graph_studio.core.state import AppState, ChartType


def make_setting(**overrides) -> GraphSetting:
    return GraphSetting(
        id=overrides.get("id", str(uuid.uuid4())),
        name=overrides.get("name", "Setting"),
        dataset_id=overrides.get("dataset_id", "dataset-1"),
        schema_version=overrides.get("schema_version", 1),
        chart_type=overrides.get("chart_type", "line"),
        x_column=overrides.get("x_column"),
        group_columns=overrides.get("group_columns", ()),
        value_columns=overrides.get("value_columns", ()),
        hover_columns=overrides.get("hover_columns", ()),
        filters=overrides.get("filters", ()),
        sorts=overrides.get("sorts", ()),
        chart_settings=overrides.get("chart_settings", {}),
        created_at=overrides.get("created_at", time.time()),
        modified_at=overrides.get("modified_at", time.time()),
    )


def make_state() -> AppState:
    state = AppState()
    state.begin_batch_update = lambda: None
    state.end_batch_update = lambda: None
    return state


def test_create_profile_adds_and_emits():
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)
    created = []

    controller.profile_created.connect(lambda pid: created.append(pid))

    state._chart_settings.chart_type = ChartType.BAR
    state._x_column = "x"

    profile_id = controller.create_profile("dataset-1", "My Profile")

    assert profile_id is not None
    assert store.get(profile_id) is not None
    assert created == [profile_id]


def test_apply_profile_updates_state():
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    setting = make_setting(
        id="setting-1",
        name="Setting",
        chart_type="scatter",
        x_column="x",
        group_columns=({"name": "g1"},),
    )
    store.add(setting)

    applied = []
    controller.profile_applied.connect(lambda pid: applied.append(pid))

    assert controller.apply_profile("setting-1") is True
    assert state._chart_settings.chart_type == ChartType.SCATTER
    assert state._x_column == "x"
    assert state._group_columns == [{"name": "g1"}]
    assert applied == ["setting-1"]


def test_apply_profile_blocks_on_unsaved_changes():
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    setting = make_setting(id="setting-1", name="Setting", chart_type="line")
    store.add(setting)
    controller._active_profile_id = "setting-1"

    state._chart_settings.chart_type = ChartType.BAR

    errors = []
    controller.error_occurred.connect(lambda msg: errors.append(msg))

    assert controller.apply_profile("setting-1") is False
    assert errors


def test_rename_profile_and_undo():
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    setting = make_setting(id="setting-1", name="Original")
    store.add(setting)

    renamed = []
    controller.profile_renamed.connect(lambda pid, name: renamed.append((pid, name)))

    assert controller.rename_profile("setting-1", "Updated") is True
    assert store.get("setting-1").name == "Updated"
    assert renamed[-1] == ("setting-1", "Updated")

    assert controller.undo() is True
    assert store.get("setting-1").name == "Original"


def test_delete_profile_and_undo():
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    setting = make_setting(id="setting-1", name="To Remove")
    store.add(setting)

    deleted = []
    controller.profile_deleted.connect(lambda pid: deleted.append(pid))

    assert controller.delete_profile("setting-1") is True
    assert store.get("setting-1") is None
    assert deleted == ["setting-1"]

    assert controller.undo() is True
    assert store.get("setting-1") is not None


def test_has_unsaved_changes():
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    setting = make_setting(id="setting-1", name="Setting", chart_type="line")
    store.add(setting)

    controller.apply_profile("setting-1")
    assert controller.has_unsaved_changes() is False

    state._chart_settings.chart_type = ChartType.BAR
    assert controller.has_unsaved_changes() is True


def test_import_profile_overrides_dataset_id():
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    imported_setting = make_setting(id="setting-1", dataset_id="old")

    store.import_async = lambda path: imported_setting

    profile_id = controller.import_profile("new", "fake-path")

    assert profile_id == "setting-1"
    assert store.get("setting-1").dataset_id == "new"
