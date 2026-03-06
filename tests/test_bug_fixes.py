"""
Tests for bug fixes - 숨은 버그 조사 후 수정된 항목들 테스트
"""

import pytest
import numpy as np
import polars as pl


class TestExpressionEngineMissingFunctions:
    """Test for missing function implementations in ExpressionEngine"""

    def test_sin_function(self):
        """Test SIN function implementation"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"x": [0.0, np.pi / 2, np.pi]})

        result = engine.evaluate("SIN(x)", df)
        expected = np.sin([0.0, np.pi / 2, np.pi])

        np.testing.assert_array_almost_equal(result.to_numpy(), expected, decimal=5)

    def test_cos_function(self):
        """Test COS function implementation"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"x": [0.0, np.pi / 2, np.pi]})

        result = engine.evaluate("COS(x)", df)
        expected = np.cos([0.0, np.pi / 2, np.pi])

        np.testing.assert_array_almost_equal(result.to_numpy(), expected, decimal=5)

    def test_tan_function(self):
        """Test TAN function implementation"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"x": [0.0, np.pi / 4]})

        result = engine.evaluate("TAN(x)", df)
        expected = np.tan([0.0, np.pi / 4])

        np.testing.assert_array_almost_equal(result.to_numpy(), expected, decimal=5)

    def test_min_function_single_column(self):
        """Test MIN function with single column"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0]})

        result = engine.evaluate("MIN(x)", df)

        # MIN of single column returns the min value repeated
        assert all(v == 1.0 for v in result.to_list())

    def test_max_function_single_column(self):
        """Test MAX function with single column"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0]})

        result = engine.evaluate("MAX(x)", df)

        # MAX of single column returns the max value repeated
        assert all(v == 4.0 for v in result.to_list())

    def test_contains_function(self):
        """Test CONTAINS function implementation"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"text": ["hello world", "foo bar", "hello there"]})

        result = engine.evaluate("CONTAINS(text, 'hello')", df)

        assert result.to_list() == [True, False, True]

    def test_substring_function(self):
        """Test SUBSTRING function implementation"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"text": ["hello", "world"]})

        # SUBSTRING uses 1-based indexing like SQL
        result = engine.evaluate("SUBSTRING(text, 1, 3)", df)

        assert result.to_list() == ["hel", "wor"]

    def test_unknown_comparison_operator_raises_expression_error(self):
        """Unsupported comparison operators should raise a clear ExpressionError."""
        from data_graph_studio.core.expression_engine import (
            ExpressionEngine,
            ExpressionError,
        )

        engine = ExpressionEngine()
        df = pl.DataFrame({"x": [1, 2, 3]})
        ast = {
            "type": "comparison",
            "op": "===",
            "left": {"type": "number", "value": 1},
            "right": {"type": "number", "value": 1},
        }

        with pytest.raises(ExpressionError, match="Unknown comparison operator: ==="):
            engine._evaluate_ast(ast, df)

    def test_trailing_tokens_raise_expression_error(self):
        """Parser should fail fast when extra tokens remain after a valid expression."""
        from data_graph_studio.core.expression_engine import (
            ExpressionEngine,
            ExpressionError,
        )

        engine = ExpressionEngine()
        df = pl.DataFrame({"x": [1, 2, 3]})

        with pytest.raises(ExpressionError, match="Unexpected token '2' at position 2"):
            engine.evaluate("1 2", df)


class TestSamplingEdgeCases:
    """Test edge cases in sampling functions"""

    def test_lttb_empty_array(self):
        """Test LTTB with empty array"""
        from data_graph_studio.graph.sampling import DataSampler

        x = np.array([])
        y = np.array([])

        sampled_x, sampled_y = DataSampler.lttb(x, y, 10)

        assert len(sampled_x) == 0
        assert len(sampled_y) == 0

    def test_lttb_threshold_zero(self):
        """Test LTTB with threshold=0"""
        from data_graph_studio.graph.sampling import DataSampler

        x = np.array([1, 2, 3, 4, 5])
        y = np.array([1, 2, 3, 4, 5])

        sampled_x, sampled_y = DataSampler.lttb(x, y, 0)

        assert len(sampled_x) == 0
        assert len(sampled_y) == 0

    def test_min_max_empty_array(self):
        """Test min_max_per_bucket with empty array"""
        from data_graph_studio.graph.sampling import DataSampler

        x = np.array([])
        y = np.array([])

        sampled_x, sampled_y = DataSampler.min_max_per_bucket(x, y, 10)

        assert len(sampled_x) == 0
        assert len(sampled_y) == 0

    def test_min_max_n_buckets_zero(self):
        """Test min_max_per_bucket with n_buckets=0"""
        from data_graph_studio.graph.sampling import DataSampler

        x = np.array([1, 2, 3, 4, 5])
        y = np.array([1, 2, 3, 4, 5])

        sampled_x, sampled_y = DataSampler.min_max_per_bucket(x, y, 0)

        assert len(sampled_x) == 0
        assert len(sampled_y) == 0

    def test_stratified_sample_empty_array(self):
        """Test stratified_sample with empty array"""
        from data_graph_studio.graph.sampling import DataSampler

        x = np.array([])
        y = np.array([])
        groups = np.array([])

        sampled_x, sampled_y, sampled_groups = DataSampler.stratified_sample(
            x, y, groups, 10
        )

        assert len(sampled_x) == 0
        assert len(sampled_y) == 0
        assert len(sampled_groups) == 0

    def test_stratified_sample_n_samples_zero(self):
        """Test stratified_sample with n_samples=0"""
        from data_graph_studio.graph.sampling import DataSampler

        x = np.array([1, 2, 3, 4, 5])
        y = np.array([1, 2, 3, 4, 5])
        groups = np.array(["a", "a", "b", "b", "b"])

        sampled_x, sampled_y, sampled_groups = DataSampler.stratified_sample(
            x, y, groups, 0
        )

        assert len(sampled_x) == 0


class TestTrellisEdgeCases:
    """Test edge cases in trellis calculations"""

    def test_trellis_panels_per_page_zero(self):
        """Test trellis with panels_per_page=0 doesn't crash"""
        from data_graph_studio.graph.trellis import (
            TrellisCalculator,
            TrellisSettings,
            TrellisMode,
        )

        calc = TrellisCalculator()
        df = pl.DataFrame({"category": ["A", "B", "C", "D"], "value": [1, 2, 3, 4]})

        settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.PANELS,
            panel_column="category",
            panels_per_page=0,  # Edge case
        )

        # Should not crash
        layout = calc.calculate(df, settings, 100, 100, "value")

        # Should have at least 1 panel
        assert layout.panels_per_page >= 1


class TestStateDeepCopy:
    """Test that state synchronization uses deep copy"""

    def test_sync_from_dataset_state_deep_copy(self):
        """Test that _sync_from_dataset_state uses deep copy"""
        from data_graph_studio.core.state import AppState, DatasetState, GroupColumn

        state = AppState()

        # Create a dataset with some group columns
        dataset_state = DatasetState(dataset_id="test")
        dataset_state.group_columns = [
            GroupColumn(name="col1", order=0),
            GroupColumn(name="col2", order=1),
        ]

        state._dataset_states["test"] = dataset_state

        # Sync from dataset state
        state._sync_from_dataset_state("test")

        # Modify the original dataset state
        dataset_state.group_columns[0].name = "modified"

        # App state's group columns should NOT be affected (deep copy)
        assert state._group_columns[0].name == "col1"

    def test_sync_to_dataset_state_deep_copy(self):
        """Test that _sync_to_dataset_state uses deep copy"""
        from data_graph_studio.core.state import AppState, DatasetState, GroupColumn

        state = AppState()
        state._active_dataset_id = "test"
        state._dataset_states["test"] = DatasetState(dataset_id="test")

        # Set some group columns on app state
        state._group_columns = [
            GroupColumn(name="col1", order=0),
            GroupColumn(name="col2", order=1),
        ]

        # Sync to dataset state
        state._sync_to_dataset_state("test")

        # Modify the app state's group columns
        state._group_columns[0].name = "modified"

        # Dataset state's group columns should NOT be affected (deep copy)
        assert state._dataset_states["test"].group_columns[0].name == "col1"


class TestGraphPanelDataHandling:
    """Test graph panel data handling edge cases"""

    def test_plot_data_with_none(self):
        """Test plot_data handles None data gracefully"""
        # This is more of an integration test - just verify the logic
        # would be tested with actual UI components in integration tests
        pass

    def test_plot_data_with_empty_arrays(self):
        """Test plot_data handles empty arrays gracefully"""
        # This is more of an integration test
        pass


class TestExpressionEngineRegressionEdges:
    """Additional regression tests for known fragile expression cases."""

    def test_contains_handles_none_values_without_crash(self):
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"text": ["hello", None, "world"]})

        result = engine.evaluate("CONTAINS(text, 'o')", df)

        assert result.to_list() == [True, None, True]

    def test_substring_overflow_length_is_safe(self):
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"text": ["abc", "x"]})

        result = engine.evaluate("SUBSTRING(text, 2, 99)", df)

        assert result.to_list() == ["bc", ""]


class TestFtraceConverterRegressionEdges:
    """Regression tests for converter dispatch and sched conversion behavior."""

    def test_unknown_converter_raises_clear_error(self):
        from data_graph_studio.parsers.ftrace_parser import FtraceParser

        parser = FtraceParser()
        raw_df = pl.DataFrame(
            {
                "timestamp": [1.0],
                "cpu": [0],
                "task": ["kworker"],
                "pid": [1],
                "flags": ["...."],
                "event": ["block_rq_issue"],
                "details": ["8,0 R 4096 () 100 + 8 [kworker]"],
            }
        )

        with pytest.raises(ValueError, match="Unknown converter: 'unknown_converter'"):
            parser.convert(raw_df, {"converter": "unknown_converter"})

    def test_sched_converter_runtime_is_per_cpu(self):
        from data_graph_studio.parsers.ftrace_parser import FtraceParser

        parser = FtraceParser()
        raw_df = pl.DataFrame(
            {
                "timestamp": [1.0, 1.5, 2.0],
                "cpu": [0, 0, 1],
                "task": ["a", "b", "c"],
                "pid": [1, 2, 3],
                "flags": ["....", "....", "...."],
                "event": ["sched_switch", "sched_switch", "sched_switch"],
                "details": [
                    "prev_comm=foo prev_pid=10 prev_prio=120 prev_state=S ==> next_comm=bar next_pid=20",
                    "prev_comm=bar prev_pid=20 prev_prio=120 prev_state=R ==> next_comm=baz next_pid=30",
                    "prev_comm=q prev_pid=11 prev_prio=120 prev_state=S ==> next_comm=w next_pid=22",
                ],
            }
        )

        result = parser.convert(raw_df, {"converter": "sched"}).sort(
            ["cpu", "timestamp"]
        )

        # CPU0 second switch: 0.5s => 500ms runtime
        cpu0 = result.filter(pl.col("cpu") == 0)
        assert cpu0["runtime_ms"][0] is None
        assert cpu0["runtime_ms"][1] == pytest.approx(500.0)

        # CPU1 first switch should not inherit CPU0 runtime
        cpu1 = result.filter(pl.col("cpu") == 1)
        assert cpu1["runtime_ms"][0] is None


class TestFileLoadingControllerRegression:
    """Regression tests for multi-file load flow."""

    def test_open_multiple_files_with_paths_enables_overlay_compare(self):
        from unittest.mock import MagicMock, patch

        from data_graph_studio.ui.controllers.file_loading_controller import (
            FileLoadingController,
        )
        from data_graph_studio.core.state import ComparisonMode

        class _Dataset:
            row_count = 10
            column_count = 2
            memory_bytes = 128

        class _Engine:
            def __init__(self):
                self._datasets = {}

            def load_dataset(self, file_path, name=None):
                dataset_id = f"ds-{len(self._datasets) + 1}"
                self._datasets[dataset_id] = _Dataset()
                return dataset_id

            def get_dataset(self, dataset_id):
                return self._datasets.get(dataset_id)

            def activate_dataset(self, dataset_id):
                self.active = dataset_id

        class _State:
            def __init__(self):
                self.added = []
                self.comparison_dataset_ids = None
                self.mode = None

            def add_dataset(self, **kwargs):
                self.added.append(kwargs)

            def set_comparison_datasets(self, ids):
                self.comparison_dataset_ids = ids

            def set_comparison_mode(self, mode):
                self.mode = mode

        class _Window:
            def __init__(self):
                self.engine = _Engine()
                self.state = _State()
                self.statusbar = MagicMock()
                self._loaded = False
                self._comp_started = None

            def _on_data_loaded(self):
                self._loaded = True

            def _on_comparison_started(self, ids):
                self._comp_started = ids

        w = _Window()
        ctrl = FileLoadingController(w)

        progress = MagicMock()
        progress.wasCanceled.return_value = False

        with (
            patch(
                "data_graph_studio.ui.controllers.file_loading_controller.QProgressDialog",
                return_value=progress,
            ),
            patch(
                "data_graph_studio.ui.controllers.file_loading_controller.QApplication.processEvents",
                return_value=None,
            ),
        ):
            ctrl._on_open_multiple_files_with_paths(["a.csv", "b.csv"])

        assert len(w.state.added) == 2
        assert w._loaded is True
        assert w.state.comparison_dataset_ids == ["ds-1", "ds-2"]
        assert w.state.mode == ComparisonMode.OVERLAY
        assert w._comp_started == ["ds-1", "ds-2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
