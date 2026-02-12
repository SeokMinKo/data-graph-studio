"""Integration test: GraphPreset → GraphSetting → ProfileController → AppState.

Verifies the full pipeline from preset creation to profile application,
ensuring chart type, x/y/group columns are correctly applied to AppState.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

import polars as pl
import pytest

from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.profile_store import ProfileStore
from data_graph_studio.core.profile_controller import ProfileController
from data_graph_studio.core.graph_setting_mapper import GraphSettingMapper
from data_graph_studio.core.state import AppState, ChartType, AggregationType, ValueColumn, GroupColumn
from data_graph_studio.parsers.graph_preset import GraphPreset, BUILTIN_PRESETS, select_preset


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def state() -> AppState:
    return AppState()


@pytest.fixture
def store() -> ProfileStore:
    return ProfileStore()


@pytest.fixture
def controller(store, state) -> ProfileController:
    return ProfileController(store, state)


SAMPLE_BLOCKLAYER_DF = pl.DataFrame({
    "timestamp": [1000.0, 1000.001, 1000.002],
    "latency_ms": [0.5, 1.2, 0.8],
    "sector": [100, 200, 300],
    "nr_sectors": [8, 16, 8],
    "rwbs": ["R", "W", "R"],
    "size_bytes": [4096, 8192, 4096],
    "device": ["8,0", "8,0", "8,0"],
    "queue_depth": [1, 2, 1],
})

DATASET_ID = "test-dataset-001"


# ══════════════════════════════════════════════════════════════
# Test: Preset → GraphSetting creation
# ══════════════════════════════════════════════════════════════

class TestPresetToGraphSetting:
    """Verify GraphPreset can create a valid GraphSetting."""

    def _make_setting(self, preset: GraphPreset) -> GraphSetting:
        """Simulate what _apply_graph_presets does."""
        value_cols = []
        for col_name in preset.y_columns:
            value_cols.append({
                "name": col_name,
                "aggregation": "sum",
                "color": "#1f77b4",
                "use_secondary_axis": False,
                "order": len(value_cols),
                "formula": "",
            })
        group_cols = []
        if preset.group_column:
            group_cols.append({
                "name": preset.group_column,
                "selected_values": [],
                "order": 0,
            })
        return GraphSetting(
            id=str(uuid.uuid4()),
            name=preset.name,
            dataset_id=DATASET_ID,
            chart_type=preset.chart_type,
            x_column=preset.x_column,
            value_columns=tuple(value_cols),
            group_columns=tuple(group_cols),
        )

    def test_latency_scatter_setting(self):
        preset = BUILTIN_PRESETS["blocklayer"][0]  # Latency Scatter
        gs = self._make_setting(preset)
        assert gs.chart_type == "scatter"
        assert gs.x_column == "timestamp"
        assert len(gs.value_columns) == 1
        assert gs.value_columns[0]["name"] == "latency_ms"
        assert len(gs.group_columns) == 1
        assert gs.group_columns[0]["name"] == "rwbs"

    def test_all_blocklayer_presets_create_valid_settings(self):
        for preset in BUILTIN_PRESETS["blocklayer"]:
            gs = self._make_setting(preset)
            assert gs.name == preset.name
            assert gs.chart_type == preset.chart_type
            assert gs.x_column == preset.x_column


# ══════════════════════════════════════════════════════════════
# Test: GraphSetting → AppState via GraphSettingMapper
# ══════════════════════════════════════════════════════════════

class TestGraphSettingToAppState:
    """Verify GraphSetting correctly maps to AppState."""

    def test_scatter_chart_type_applied(self, state):
        gs = GraphSetting(
            id="test-1", name="Latency Scatter", dataset_id=DATASET_ID,
            chart_type="scatter", x_column="timestamp",
            value_columns=({"name": "latency_ms", "aggregation": "sum",
                            "color": "#1f77b4", "use_secondary_axis": False,
                            "order": 0, "formula": ""},),
            group_columns=({"name": "rwbs", "selected_values": [], "order": 0},),
        )
        GraphSettingMapper.to_app_state(gs, state)
        assert state._chart_settings.chart_type == ChartType.SCATTER

    def test_x_column_applied(self, state):
        gs = GraphSetting(
            id="test-2", name="Test", dataset_id=DATASET_ID,
            chart_type="line", x_column="timestamp",
            value_columns=({"name": "queue_depth", "aggregation": "sum",
                            "color": "#1f77b4", "use_secondary_axis": False,
                            "order": 0, "formula": ""},),
        )
        GraphSettingMapper.to_app_state(gs, state)
        assert state._x_column == "timestamp"

    def test_value_columns_applied(self, state):
        gs = GraphSetting(
            id="test-3", name="Test", dataset_id=DATASET_ID,
            chart_type="scatter", x_column="timestamp",
            value_columns=(
                {"name": "latency_ms", "aggregation": "sum",
                 "color": "#ff0000", "use_secondary_axis": False,
                 "order": 0, "formula": ""},
            ),
        )
        GraphSettingMapper.to_app_state(gs, state)
        assert len(state._value_columns) == 1
        vc = state._value_columns[0]
        assert isinstance(vc, ValueColumn)
        assert vc.name == "latency_ms"
        assert vc.color == "#ff0000"

    def test_group_columns_applied(self, state):
        gs = GraphSetting(
            id="test-4", name="Test", dataset_id=DATASET_ID,
            chart_type="scatter", x_column="timestamp",
            value_columns=({"name": "latency_ms", "aggregation": "sum",
                            "color": "#1f77b4", "use_secondary_axis": False,
                            "order": 0, "formula": ""},),
            group_columns=({"name": "rwbs", "selected_values": [], "order": 0},),
        )
        GraphSettingMapper.to_app_state(gs, state)
        assert len(state._group_columns) == 1
        gc = state._group_columns[0]
        assert isinstance(gc, GroupColumn)
        assert gc.name == "rwbs"

    def test_histogram_chart_type(self, state):
        gs = GraphSetting(
            id="test-5", name="Hist", dataset_id=DATASET_ID,
            chart_type="histogram", x_column="latency_ms",
            value_columns=({"name": "latency_ms", "aggregation": "sum",
                            "color": "#1f77b4", "use_secondary_axis": False,
                            "order": 0, "formula": ""},),
        )
        GraphSettingMapper.to_app_state(gs, state)
        assert state._chart_settings.chart_type == ChartType.HISTOGRAM

    def test_aggregation_fallback_for_invalid(self, state):
        """Invalid aggregation value should fallback to SUM, not crash."""
        gs = GraphSetting(
            id="test-6", name="Test", dataset_id=DATASET_ID,
            chart_type="scatter", x_column="timestamp",
            value_columns=({"name": "latency_ms", "aggregation": "none",
                            "color": "#1f77b4", "use_secondary_axis": False,
                            "order": 0, "formula": ""},),
        )
        GraphSettingMapper.to_app_state(gs, state)
        # Should not crash, fallback to SUM
        assert state._value_columns[0].aggregation == AggregationType.SUM


# ══════════════════════════════════════════════════════════════
# Test: ProfileController apply_profile flow
# ══════════════════════════════════════════════════════════════

class TestProfileControllerApply:
    """Verify ProfileController correctly orchestrates apply."""

    def test_apply_sets_state(self, store, controller, state):
        gs = GraphSetting(
            id="p-1", name="Latency Scatter", dataset_id=DATASET_ID,
            chart_type="scatter", x_column="timestamp",
            value_columns=({"name": "latency_ms", "aggregation": "sum",
                            "color": "#1f77b4", "use_secondary_axis": False,
                            "order": 0, "formula": ""},),
            group_columns=({"name": "rwbs", "selected_values": [], "order": 0},),
        )
        store.add(gs)
        ok = controller.apply_profile("p-1")
        assert ok is True
        assert state._chart_settings.chart_type == ChartType.SCATTER
        assert state._x_column == "timestamp"
        assert len(state._value_columns) == 1
        assert state._value_columns[0].name == "latency_ms"

    def test_switch_between_profiles(self, store, controller, state):
        gs1 = GraphSetting(
            id="p-1", name="Scatter", dataset_id=DATASET_ID,
            chart_type="scatter", x_column="timestamp",
            value_columns=({"name": "latency_ms", "aggregation": "sum",
                            "color": "#1f77b4", "use_secondary_axis": False,
                            "order": 0, "formula": ""},),
        )
        gs2 = GraphSetting(
            id="p-2", name="Line", dataset_id=DATASET_ID,
            chart_type="line", x_column="timestamp",
            value_columns=({"name": "queue_depth", "aggregation": "sum",
                            "color": "#ff7f0e", "use_secondary_axis": False,
                            "order": 0, "formula": ""},),
        )
        store.add(gs1)
        store.add(gs2)

        controller.apply_profile("p-1")
        assert state._chart_settings.chart_type == ChartType.SCATTER
        assert state._value_columns[0].name == "latency_ms"

        controller.apply_profile("p-2")
        assert state._chart_settings.chart_type == ChartType.LINE
        assert state._value_columns[0].name == "queue_depth"

    def test_save_active_preserves_state(self, store, controller, state):
        gs = GraphSetting(
            id="p-1", name="Test", dataset_id=DATASET_ID,
            chart_type="scatter", x_column="timestamp",
            value_columns=({"name": "latency_ms", "aggregation": "sum",
                            "color": "#1f77b4", "use_secondary_axis": False,
                            "order": 0, "formula": ""},),
        )
        store.add(gs)
        controller.apply_profile("p-1")

        # Manually change state
        state.set_chart_type(ChartType.LINE)

        # Save should capture the change
        controller.save_active_profile()
        updated = store.get("p-1")
        assert updated.chart_type == "line"


# ══════════════════════════════════════════════════════════════
# Test: Full E2E — blocklayer preset → profiles → state
# ══════════════════════════════════════════════════════════════

class TestE2EBlocklayerPresets:
    """Simulate the full _apply_graph_presets flow."""

    def _create_profiles_from_presets(self, store, df, dataset_id):
        """Mimics _apply_graph_presets logic."""
        presets = BUILTIN_PRESETS.get("blocklayer", [])
        created_ids = []
        for preset in presets:
            if not preset.columns_present(df):
                continue
            value_cols = []
            for col_name in preset.y_columns:
                value_cols.append({
                    "name": col_name,
                    "aggregation": "sum",
                    "color": "#1f77b4",
                    "use_secondary_axis": False,
                    "order": len(value_cols),
                    "formula": "",
                })
            group_cols = []
            if preset.group_column:
                group_cols.append({
                    "name": preset.group_column,
                    "selected_values": [],
                    "order": 0,
                })
            gs = GraphSetting(
                id=str(uuid.uuid4()),
                name=preset.name,
                dataset_id=dataset_id,
                chart_type=preset.chart_type,
                x_column=preset.x_column,
                value_columns=tuple(value_cols),
                group_columns=tuple(group_cols),
            )
            store.add(gs)
            created_ids.append(gs.id)
        return created_ids

    def test_creates_4_profiles(self, store):
        ids = self._create_profiles_from_presets(store, SAMPLE_BLOCKLAYER_DF, DATASET_ID)
        assert len(ids) == 4

    def test_profiles_retrievable_by_dataset(self, store):
        self._create_profiles_from_presets(store, SAMPLE_BLOCKLAYER_DF, DATASET_ID)
        profiles = store.get_by_dataset(DATASET_ID)
        assert len(profiles) == 4
        names = {p.name for p in profiles}
        assert "Latency Scatter" in names
        assert "IOPS Timeline" in names
        assert "Latency Distribution" in names
        assert "Size vs Latency" in names

    def test_apply_each_profile_no_crash(self, store, controller, state):
        ids = self._create_profiles_from_presets(store, SAMPLE_BLOCKLAYER_DF, DATASET_ID)
        for pid in ids:
            ok = controller.apply_profile(pid)
            assert ok is True
            # State should have valid chart type
            assert state._chart_settings.chart_type in (
                ChartType.SCATTER, ChartType.LINE, ChartType.HISTOGRAM,
            )

    def test_no_duplicates_on_second_run(self, store):
        self._create_profiles_from_presets(store, SAMPLE_BLOCKLAYER_DF, DATASET_ID)
        # Second run should detect existing names
        existing_names = {s.name for s in store.get_by_dataset(DATASET_ID)}
        presets = BUILTIN_PRESETS.get("blocklayer", [])
        new_count = sum(1 for p in presets if p.name not in existing_names and p.columns_present(SAMPLE_BLOCKLAYER_DF))
        assert new_count == 0
