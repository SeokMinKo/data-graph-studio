"""Tests for GraphSetting version migration."""

from data_graph_studio.core.profile import GraphSetting


def test_from_dict_without_version_gets_v1():
    """Legacy dicts without 'version' field should be migrated to v1."""
    data = {
        "id": "abc",
        "name": "Legacy",
        "dataset_id": "ds-1",
        "chart_type": "line",
    }
    gs = GraphSetting.from_dict(data)
    assert gs.version == 1


def test_from_dict_with_version_preserves():
    data = {
        "id": "abc",
        "name": "Versioned",
        "dataset_id": "ds-1",
        "version": 1,
    }
    gs = GraphSetting.from_dict(data)
    assert gs.version == 1


def test_to_dict_includes_version():
    gs = GraphSetting(id="x", name="Y", dataset_id="ds")
    d = gs.to_dict()
    assert "version" in d
    assert d["version"] == 1


def test_roundtrip_preserves_version():
    gs = GraphSetting(id="x", name="Y", dataset_id="ds", version=1)
    d = gs.to_dict()
    gs2 = GraphSetting.from_dict(d)
    assert gs2.version == gs.version


def test_normalized_chart_settings_defaults():
    gs = GraphSetting(id="x", name="Y", dataset_id="ds")
    norm = gs.normalized_chart_settings()
    assert norm["show_legend"] is True
    assert norm["opacity"] == 1.0


def test_normalized_chart_settings_overrides():
    gs = GraphSetting(
        id="x",
        name="Y",
        dataset_id="ds",
        chart_settings={"show_legend": False, "custom_key": 42},
    )
    norm = gs.normalized_chart_settings()
    assert norm["show_legend"] is False
    assert norm["custom_key"] == 42
    # Defaults still present
    assert "show_grid" in norm


def test_migrate_v0_to_v1():
    """_migrate should upgrade version 0 → 1."""
    data = {"id": "a", "name": "b", "dataset_id": "c"}
    migrated = GraphSetting._migrate(data)
    assert migrated["version"] == 1


def test_frozen_chart_settings_is_mapping_proxy():
    """Issue #10 — chart_settings is now a plain dict (MappingProxyType removed)."""
    gs = GraphSetting(id="x", name="Y", dataset_id="ds", chart_settings={"a": 1})
    assert isinstance(gs.chart_settings, dict)
    assert gs.chart_settings == {"a": 1}


def test_frozen_tuples():
    gs = GraphSetting(
        id="x",
        name="Y",
        dataset_id="ds",
        group_columns=[1, 2],
        value_columns=[3],
        filters=[4],
        sorts=[5],
    )
    assert isinstance(gs.group_columns, tuple)
    assert isinstance(gs.value_columns, tuple)
    assert isinstance(gs.filters, tuple)
    assert isinstance(gs.sorts, tuple)
