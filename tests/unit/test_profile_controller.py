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


# ==================== Chart Options Per-Profile Tests ====================


def test_chart_options_saved_per_profile():
    """title/subtitle이 프로파일별로 독립적으로 저장/복원되어야 한다."""
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    # Profile A 생성 및 적용
    pid_a = controller.create_profile("ds-1", "Profile A")
    assert pid_a is not None
    # Simulate UI setting title/subtitle into the options cache
    state._chart_options_cache = {'title': 'Title A', 'subtitle': 'Sub A', 'x_title': 'X-A'}
    controller.save_active_profile()

    # Profile B 생성 및 적용
    pid_b = controller.create_profile("ds-1", "Profile B")
    assert pid_b is not None
    state._chart_options_cache = {'title': 'Title B', 'subtitle': 'Sub B', 'x_title': 'X-B'}
    controller.save_active_profile()

    # A로 전환 → title이 A로 복원되어야 함
    controller.apply_profile(pid_a)
    assert state._chart_options_cache.get('title') == 'Title A'
    assert state._chart_options_cache.get('subtitle') == 'Sub A'
    assert state._chart_options_cache.get('x_title') == 'X-A'

    # B로 전환 → title이 B로 복원되어야 함
    controller.apply_profile(pid_b)
    assert state._chart_options_cache.get('title') == 'Title B'
    assert state._chart_options_cache.get('subtitle') == 'Sub B'
    assert state._chart_options_cache.get('x_title') == 'X-B'


def test_chart_options_cleared_for_empty_profile():
    """빈 프로파일로 전환 시 chart_options_cache가 빈 dict로 초기화되어야 한다."""
    store = ProfileStore()
    state = make_state()
    controller = ProfileController(store, state)

    # Profile with title
    pid_with_title = controller.create_profile("ds-1", "With Title")
    state._chart_options_cache = {'title': 'My Title', 'subtitle': 'My Sub'}
    controller.save_active_profile()

    # Profile without title (empty chart_settings)
    pid_empty = controller.create_profile("ds-1", "Empty")
    state._chart_options_cache = {}
    controller.save_active_profile()

    # Apply profile with title → verify title present
    controller.apply_profile(pid_with_title)
    assert state._chart_options_cache.get('title') == 'My Title'

    # Apply empty profile → title should be cleared
    controller.apply_profile(pid_empty)
    assert state._chart_options_cache.get('title') is None or state._chart_options_cache.get('title') == ''


def test_from_app_state_includes_chart_options_cache():
    """from_app_state()가 _chart_options_cache의 내용을 chart_settings에 포함해야 한다."""
    state = make_state()
    state._chart_settings.chart_type = ChartType.LINE
    state._x_column = "x_col"
    state._chart_options_cache = {
        'title': 'Test Title',
        'subtitle': 'Test Subtitle',
        'x_title': 'X Axis',
        'y_title': 'Y Axis',
        'grid_x': True,
        'grid_y': False,
        'bg_color': '#ffffff',
    }

    gs = GraphSettingMapper.from_app_state(state, "test", "ds-1")

    assert gs.chart_settings.get('title') == 'Test Title'
    assert gs.chart_settings.get('subtitle') == 'Test Subtitle'
    assert gs.chart_settings.get('x_title') == 'X Axis'
    assert gs.chart_settings.get('y_title') == 'Y Axis'
    assert gs.chart_settings.get('grid_x') is True
    assert gs.chart_settings.get('grid_y') is False
    assert gs.chart_settings.get('bg_color') == '#ffffff'


def test_to_app_state_restores_chart_options_cache():
    """to_app_state()가 chart_settings를 _chart_options_cache에 복원해야 한다."""
    state = make_state()
    setting = make_setting(
        chart_type="line",
        chart_settings={
            'title': 'Restored Title',
            'subtitle': 'Restored Sub',
            'x_title': 'Restored X',
            'line_width': 3,
        },
    )

    GraphSettingMapper.to_app_state(setting, state)

    assert state._chart_options_cache.get('title') == 'Restored Title'
    assert state._chart_options_cache.get('subtitle') == 'Restored Sub'
    assert state._chart_options_cache.get('x_title') == 'Restored X'
    assert state._chart_options_cache.get('line_width') == 3


def test_chart_options_round_trip():
    """from_app_state → to_app_state 왕복 시 chart options이 보존되어야 한다."""
    state = make_state()
    state._chart_settings.chart_type = ChartType.SCATTER
    state._x_column = "time"
    state._chart_options_cache = {
        'title': 'Round Trip Test',
        'subtitle': 'Subtitle',
        'x_title': 'Time (s)',
        'y_title': 'Value',
        'grid_x': True,
        'grid_y': True,
        'grid_opacity': 0.5,
        'show_labels': False,
        'show_points': True,
        'line_width': 3,
        'marker_size': 8,
        'fill_opacity': 0.7,
        'bg_color': '#1e1e2e',
    }

    # Save: AppState → GraphSetting
    gs = GraphSettingMapper.from_app_state(state, "test", "ds-1")

    # Restore: GraphSetting → fresh AppState
    state2 = make_state()
    GraphSettingMapper.to_app_state(gs, state2)

    # Verify all options survived the round trip
    assert state2._chart_options_cache.get('title') == 'Round Trip Test'
    assert state2._chart_options_cache.get('subtitle') == 'Subtitle'
    assert state2._chart_options_cache.get('x_title') == 'Time (s)'
    assert state2._chart_options_cache.get('y_title') == 'Value'
    assert state2._chart_options_cache.get('grid_x') is True
    assert state2._chart_options_cache.get('grid_opacity') == 0.5
    assert state2._chart_options_cache.get('show_points') is True
    assert state2._chart_options_cache.get('line_width') == 3
    assert state2._chart_options_cache.get('bg_color') == '#1e1e2e'


def test_chart_type_excluded_from_cache_in_chart_settings():
    """chart_type은 GraphSetting의 top-level 필드이므로 chart_settings에 중복 저장되지 않아야 한다."""
    state = make_state()
    state._chart_settings.chart_type = ChartType.BAR
    state._chart_options_cache = {
        'chart_type': 'bar',  # This should be excluded
        'title': 'Test',
    }

    gs = GraphSettingMapper.from_app_state(state, "test", "ds-1")

    # chart_type should be at top level, not in chart_settings
    assert gs.chart_type == 'bar'
    assert 'chart_type' not in gs.chart_settings
