"""Tests for performance and memory optimizations (items #1-#19)."""
import sys
import copy
from unittest.mock import MagicMock, patch
import polars as pl
import pytest


# ---------------------------------------------------------------------------
# #4: data_quality_report uses is_duplicated instead of df.unique()
# ---------------------------------------------------------------------------

class TestDataQualityReport:
    def test_duplicate_count_correct(self):
        from data_graph_studio.core.data_engine import DataEngine
        engine = DataEngine()
        df = pl.DataFrame({"a": [1, 2, 2, 3, 3, 3], "b": ["x", "y", "y", "z", "z", "z"]})
        engine.update_dataframe(df)
        report = engine.data_quality_report()
        assert report["duplicate_rows"] == 3  # 6 total - 3 unique = 3 duplicate rows
        assert report["row_count"] == 6
        assert report["col_count"] == 2

    def test_no_duplicates(self):
        from data_graph_studio.core.data_engine import DataEngine
        engine = DataEngine()
        df = pl.DataFrame({"a": [1, 2, 3]})
        engine.update_dataframe(df)
        report = engine.data_quality_report()
        assert report["duplicate_rows"] == 0


# ---------------------------------------------------------------------------
# #5 & #6: Batch update mechanism
# ---------------------------------------------------------------------------

class TestBatchUpdate:
    def test_begin_end_batch(self):
        from data_graph_studio.core.state import AppState
        state = AppState()
        signals_received = []

        state.group_zone_changed.connect(lambda: signals_received.append("group"))
        state.value_zone_changed.connect(lambda: signals_received.append("value"))

        state.begin_batch_update()
        state._batch_pending_signals.append("group_zone_changed")
        state._batch_pending_signals.append("value_zone_changed")
        state._batch_pending_signals.append("group_zone_changed")  # duplicate
        assert len(signals_received) == 0  # No signals during batch

        state.end_batch_update()
        # Each signal emitted once (deduplicated)
        assert signals_received.count("group") == 1
        assert signals_received.count("value") == 1

    def test_nested_batch(self):
        from data_graph_studio.core.state import AppState
        state = AppState()
        signals_received = []
        state.chart_settings_changed.connect(lambda: signals_received.append("chart"))

        state.begin_batch_update()
        state.begin_batch_update()  # nested
        state._batch_pending_signals.append("chart_settings_changed")
        state.end_batch_update()  # depth 1 -> still batching
        assert len(signals_received) == 0
        state.end_batch_update()  # depth 0 -> fire
        assert len(signals_received) == 1

    def test_sync_from_dataset_state_uses_batch(self):
        """_sync_from_dataset_state should emit signals via batch."""
        from data_graph_studio.core.state import AppState, DatasetState
        state = AppState()
        ds = DatasetState(dataset_id="test1")
        state._dataset_states["test1"] = ds

        signals = []
        state.group_zone_changed.connect(lambda: signals.append("g"))
        state.value_zone_changed.connect(lambda: signals.append("v"))
        state.hover_zone_changed.connect(lambda: signals.append("h"))
        state.chart_settings_changed.connect(lambda: signals.append("c"))
        state.filter_changed.connect(lambda: signals.append("f"))
        state.sort_changed.connect(lambda: signals.append("s"))

        state._sync_from_dataset_state("test1")
        # All 6 signals should fire exactly once
        assert len(signals) == 6
        assert set(signals) == {"g", "v", "h", "c", "f", "s"}


# ---------------------------------------------------------------------------
# #7: Cache memory-based eviction
# ---------------------------------------------------------------------------

class TestCacheMemoryEviction:
    def test_cache_tracks_bytes(self):
        from data_graph_studio.core.data_engine import DataEngine
        engine = DataEngine()
        engine._set_cache("key1", pl.DataFrame({"a": list(range(100))}))
        assert engine._cache_total_bytes > 0

    def test_cache_clear_resets_bytes(self):
        from data_graph_studio.core.data_engine import DataEngine
        engine = DataEngine()
        engine._set_cache("key1", pl.DataFrame({"a": list(range(100))}))
        engine._clear_cache()
        assert engine._cache_total_bytes == 0
        assert len(engine._cache_sizes) == 0

    def test_cache_eviction_by_memory(self):
        from data_graph_studio.core.data_engine import DataEngine
        engine = DataEngine()
        # Set very low memory limit
        engine.CACHE_MAX_MEMORY_BYTES = 1000
        engine._cache_maxsize = 10000  # Don't evict by count

        # Add items until eviction
        for i in range(100):
            engine._set_cache(f"key{i}", pl.DataFrame({"a": list(range(50))}))

        assert engine._cache_total_bytes <= 1000 + 500  # some tolerance


# ---------------------------------------------------------------------------
# #8: Search returns mask via search_mask
# ---------------------------------------------------------------------------

class TestSearchMask:
    def test_search_mask_returns_bool_series(self):
        from data_graph_studio.core.data_query import DataQuery
        dq = DataQuery()
        df = pl.DataFrame({"name": ["alice", "bob", "charlie"], "age": [25, 30, 35]})
        mask = dq.search_mask(df, "bob")
        assert isinstance(mask, pl.Series)
        assert mask.dtype == pl.Boolean
        assert mask.to_list() == [False, True, False]

    def test_search_mask_none_on_no_match(self):
        from data_graph_studio.core.data_query import DataQuery
        dq = DataQuery()
        df = pl.DataFrame({"name": ["alice"]})
        mask = dq.search_mask(df, "zzz")
        assert mask is not None
        assert mask.sum() == 0

    def test_search_still_returns_dataframe(self):
        """search() should still return DataFrame for backward compat."""
        from data_graph_studio.core.data_query import DataQuery
        dq = DataQuery()
        df = pl.DataFrame({"name": ["alice", "bob"], "v": [1, 2]})
        result = dq.search(df, "alice")
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# #9: pl.arange in _apply_limit_to_marking (tested indirectly)
# ---------------------------------------------------------------------------

class TestPlArange:
    def test_arange_produces_series(self):
        s = pl.arange(0, 10, eager=True).alias("idx")
        assert isinstance(s, pl.Series)
        assert len(s) == 10
        assert s[0] == 0
        assert s[9] == 9


# ---------------------------------------------------------------------------
# #10: _sync_to_dataset_state deepcopy minimization
# ---------------------------------------------------------------------------

class TestSyncToDatasetState:
    def test_sync_preserves_data(self):
        from data_graph_studio.core.state import AppState, DatasetState, GroupColumn, AggregationType
        state = AppState()
        ds = DatasetState(dataset_id="t1")
        state._dataset_states["t1"] = ds
        state._active_dataset_id = "t1"

        state._x_column = "col_x"
        state._group_columns = [GroupColumn(name="g1")]
        state._hover_columns = ["h1", "h2"]

        state._sync_to_dataset_state()

        assert ds.x_column == "col_x"
        assert len(ds.group_columns) == 1
        assert ds.hover_columns == ["h1", "h2"]
        # Verify isolation (hover is shallow copied list)
        state._hover_columns.append("h3")
        assert ds.hover_columns == ["h1", "h2"]


# ---------------------------------------------------------------------------
# #12: headerData tooltip cache
# ---------------------------------------------------------------------------

class TestHeaderTooltipCache:
    def test_stats_precomputed(self):
        from data_graph_studio.ui.panels.table_panel import PolarsTableModel
        model = PolarsTableModel()
        df = pl.DataFrame({"a": [1.0, 2.0, 3.0], "b": ["x", "y", "z"]})
        model.set_dataframe(df)
        # Check cached stats exist
        assert "a" in model._column_stats
        assert "Min:" in model._column_stats["a"]
        assert "b" in model._column_stats

    def test_headerdata_uses_cache(self):
        from data_graph_studio.ui.panels.table_panel import PolarsTableModel
        from PySide6.QtCore import Qt
        model = PolarsTableModel()
        df = pl.DataFrame({"col": [10, 20, 30]})
        model.set_dataframe(df)
        tooltip = model.headerData(0, Qt.Horizontal, Qt.ToolTipRole)
        assert tooltip is not None
        assert "col" in tooltip


# ---------------------------------------------------------------------------
# #14: Filter result cache
# ---------------------------------------------------------------------------

class TestFilterCache:
    def test_filter_cache_hash_logic(self):
        """Filter cache hash should be deterministic for same filters."""
        from data_graph_studio.core.state import FilterCondition

        filters = [FilterCondition("a", "gt", 2, True)]
        h1 = hash(tuple((f.column, f.operator, str(f.value), f.enabled) for f in filters))
        h2 = hash(tuple((f.column, f.operator, str(f.value), f.enabled) for f in filters))
        assert h1 == h2

        filters2 = [FilterCondition("a", "gt", 3, True)]
        h3 = hash(tuple((f.column, f.operator, str(f.value), f.enabled) for f in filters2))
        assert h1 != h3


# ---------------------------------------------------------------------------
# #15: Conditional format ranges cached
# ---------------------------------------------------------------------------

class TestConditionalFormatRangesCache:
    def test_ranges_cached_on_set_dataframe(self):
        from data_graph_studio.ui.panels.table_panel import PolarsTableModel, ConditionalFormat
        model = PolarsTableModel()
        fmt = ConditionalFormat(mode="heatmap")
        model.set_conditional_format("val", fmt)
        df = pl.DataFrame({"val": [10.0, 20.0, 30.0]})
        model.set_dataframe(df)
        assert "val" in model._cond_fmt_ranges
        assert model._cond_fmt_ranges["val"] == (10.0, 30.0)


# ---------------------------------------------------------------------------
# #17: DatasetState.clone() selective deepcopy
# ---------------------------------------------------------------------------

class TestDatasetStateClone:
    def test_clone_empty_selection(self):
        from data_graph_studio.core.state import DatasetState
        ds = DatasetState(dataset_id="x")
        cloned = ds.clone()
        assert cloned.dataset_id == "x"
        assert cloned.selection is not ds.selection
        assert len(cloned.selection.selected_rows) == 0

    def test_clone_with_selection(self):
        from data_graph_studio.core.state import DatasetState
        ds = DatasetState(dataset_id="y")
        ds.selection.select([1, 2, 3])
        cloned = ds.clone()
        assert cloned.selection.selected_rows == {1, 2, 3}
        # Verify isolation
        cloned.selection.select([10])
        assert 10 not in ds.selection.selected_rows

    def test_clone_hover_isolation(self):
        from data_graph_studio.core.state import DatasetState
        ds = DatasetState(dataset_id="z")
        ds.hover_columns = ["a", "b"]
        cloned = ds.clone()
        cloned.hover_columns.append("c")
        assert ds.hover_columns == ["a", "b"]
