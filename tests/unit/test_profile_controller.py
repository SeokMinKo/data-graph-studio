import time
import uuid

from data_graph_studio.core.graph_setting_mapper import GraphSettingMapper
from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.profile_controller import ProfileController
from data_graph_studio.core.profile_store import ProfileStore
from data_graph_studio.core.state import AppState, ChartType
from data_graph_studio.core.undo_manager import UndoStack


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
    assert len(state._group_columns) == 1
    assert state._group_columns[0].name == "g1"
    assert applied == ["setting-1"]


def test_apply_profile_auto_saves_active():
    """프로파일 전환 시 기존 활성 프로파일에 변경사항이 자동 저장된다."""
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    # 프로파일 A (line) 생성 + 적용
    setting_a = make_setting(id="setting-a", name="A", chart_type="line")
    store.add(setting_a)
    controller.apply_profile("setting-a")

    # 프로파일 B (scatter) 생성 + store에 추가
    setting_b = make_setting(id="setting-b", name="B", chart_type="scatter")
    store.add(setting_b)

    # AppState에서 chart_type을 BAR로 변경 (A에 대한 수정)
    state._chart_settings.chart_type = ChartType.BAR

    # B로 전환 → A의 변경사항(BAR)이 자동 저장되어야 함
    assert controller.apply_profile("setting-b") is True

    # A를 다시 확인 → BAR로 저장되어 있어야 함
    saved_a = store.get("setting-a")
    assert saved_a.chart_type == "bar"

    # state는 B의 설정(scatter)으로 바뀌어 있어야 함
    assert state._chart_settings.chart_type == ChartType.SCATTER


def test_apply_same_profile_no_auto_save():
    """같은 프로파일을 다시 적용하면 auto-save하지 않는다."""
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    setting = make_setting(id="setting-1", name="Setting", chart_type="line")
    store.add(setting)
    controller.apply_profile("setting-1")

    # 변경 후 같은 프로파일 re-apply → auto-save 안 함 (같은 ID)
    state._chart_settings.chart_type = ChartType.BAR
    original_modified = store.get("setting-1").modified_at

    assert controller.apply_profile("setting-1") is True
    # 같은 프로파일이므로 store의 modified_at이 변하지 않아야 함
    assert store.get("setting-1").modified_at == original_modified


def test_rename_profile_and_undo():
    store = ProfileStore()
    state = make_state()
    undo_stack = UndoStack()
    controller = ProfileController(store, state, undo_stack=undo_stack)

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
    undo_stack = UndoStack()
    controller = ProfileController(store, state, undo_stack=undo_stack)

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
