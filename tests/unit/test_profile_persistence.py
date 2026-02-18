"""Tests for ProfileStore JSON persistence (save_to_disk / load_from_disk)."""

import json
import time
import uuid

from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.profile_store import ProfileStore


def make_setting(**kw) -> GraphSetting:
    return GraphSetting(
        id=kw.get("id", str(uuid.uuid4())),
        name=kw.get("name", "Test"),
        dataset_id=kw.get("dataset_id", "ds-1"),
        chart_type=kw.get("chart_type", "line"),
    )


def test_save_and_load_roundtrip(tmp_path):
    store = ProfileStore()
    store.set_persist_dir(tmp_path / "profiles")

    s1 = make_setting(name="Alpha")
    s2 = make_setting(name="Beta")
    store.add(s1)
    store.add(s2)
    store.save_to_disk()

    # Verify files exist
    files = list((tmp_path / "profiles").glob("*.json"))
    assert len(files) == 2

    # Load into fresh store
    store2 = ProfileStore()
    store2.set_persist_dir(tmp_path / "profiles")
    count = store2.load_from_disk()
    assert count == 2
    assert store2.get(s1.id).name == "Alpha"
    assert store2.get(s2.id).name == "Beta"


def test_save_removes_stale_files(tmp_path):
    store = ProfileStore()
    store.set_persist_dir(tmp_path / "profiles")

    s1 = make_setting(name="Keep")
    s2 = make_setting(name="Remove")
    store.add(s1)
    store.add(s2)
    store.save_to_disk()

    # Remove s2 from store, save again
    store.remove(s2.id)
    store.save_to_disk()

    files = list((tmp_path / "profiles").glob("*.json"))
    assert len(files) == 1
    assert files[0].stem == s1.id


def test_load_from_empty_dir(tmp_path):
    store = ProfileStore()
    d = tmp_path / "empty"
    d.mkdir()
    store.set_persist_dir(d)
    assert store.load_from_disk() == 0


def test_load_without_persist_dir():
    store = ProfileStore()
    assert store.load_from_disk() == 0


def test_delete_file(tmp_path):
    store = ProfileStore()
    store.set_persist_dir(tmp_path / "profiles")

    s = make_setting(name="ToDelete")
    store.add(s)
    store.save_to_disk()

    store.delete_file(s.id)
    assert not (tmp_path / "profiles" / f"{s.id}.json").exists()


def test_save_preserves_all_fields(tmp_path):
    store = ProfileStore()
    store.set_persist_dir(tmp_path / "profiles")

    s = GraphSetting(
        id="test-id",
        name="Full",
        dataset_id="ds-1",
        version=1,
        chart_type="scatter",
        x_column="date",
        group_columns=({"name": "cat"},),
        value_columns=({"name": "val", "aggregation": "sum"},),
        hover_columns=("info",),
        chart_settings={"show_legend": False, "opacity": 0.5},
        is_favorite=True,
        description="A test profile",
    )
    store.add(s)
    store.save_to_disk()

    store2 = ProfileStore()
    store2.set_persist_dir(tmp_path / "profiles")
    store2.load_from_disk()
    loaded = store2.get("test-id")

    assert loaded.name == "Full"
    assert loaded.chart_type == "scatter"
    assert loaded.x_column == "date"
    assert loaded.is_favorite is True
    assert dict(loaded.chart_settings)["opacity"] == 0.5
