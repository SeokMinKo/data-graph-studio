import time
import uuid

from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.profile_store import ProfileStore


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


def test_add_and_get():
    store = ProfileStore()
    setting = make_setting(name="Revenue")

    store.add(setting)

    assert store.get(setting.id) == setting


def test_get_by_dataset():
    store = ProfileStore()
    setting1 = make_setting(dataset_id="dataset-a", name="A")
    setting2 = make_setting(dataset_id="dataset-a", name="B")
    setting3 = make_setting(dataset_id="dataset-b", name="C")

    store.add(setting1)
    store.add(setting2)
    store.add(setting3)

    result = store.get_by_dataset("dataset-a")

    assert len(result) == 2
    assert {s.id for s in result} == {setting1.id, setting2.id}


def test_update():
    store = ProfileStore()
    setting = make_setting(name="Original")
    store.add(setting)

    updated = setting.with_name("Updated")
    store.update(updated)

    assert store.get(setting.id).name == "Updated"


def test_remove():
    store = ProfileStore()
    setting = make_setting(name="To Remove")
    store.add(setting)

    assert store.remove(setting.id) is True
    assert store.get(setting.id) is None
    assert store.remove(setting.id) is False


def test_duplicate_generates_new_id():
    store = ProfileStore()
    setting = make_setting(name="Base")
    store.add(setting)

    duplicated = store.duplicate(setting.id)

    assert duplicated is not None
    assert duplicated.id != setting.id
    assert store.get(duplicated.id) == duplicated


def test_name_conflict_suffix():
    store = ProfileStore()
    setting = make_setting(name="Report", dataset_id="dataset-1")
    existing = make_setting(name="Report (1)", dataset_id="dataset-1")

    store.add(setting)
    store.add(existing)

    duplicated = store.duplicate(setting.id)

    assert duplicated.name == "Report (2)"
