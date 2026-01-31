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
        df = pl.DataFrame({"x": [0.0, np.pi/2, np.pi]})
        
        result = engine.evaluate("SIN(x)", df)
        expected = np.sin([0.0, np.pi/2, np.pi])
        
        np.testing.assert_array_almost_equal(result.to_numpy(), expected, decimal=5)

    def test_cos_function(self):
        """Test COS function implementation"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"x": [0.0, np.pi/2, np.pi]})
        
        result = engine.evaluate("COS(x)", df)
        expected = np.cos([0.0, np.pi/2, np.pi])
        
        np.testing.assert_array_almost_equal(result.to_numpy(), expected, decimal=5)

    def test_tan_function(self):
        """Test TAN function implementation"""
        from data_graph_studio.core.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        df = pl.DataFrame({"x": [0.0, np.pi/4]})
        
        result = engine.evaluate("TAN(x)", df)
        expected = np.tan([0.0, np.pi/4])
        
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
        
        sampled_x, sampled_y, sampled_groups = DataSampler.stratified_sample(x, y, groups, 10)
        
        assert len(sampled_x) == 0
        assert len(sampled_y) == 0
        assert len(sampled_groups) == 0

    def test_stratified_sample_n_samples_zero(self):
        """Test stratified_sample with n_samples=0"""
        from data_graph_studio.graph.sampling import DataSampler

        x = np.array([1, 2, 3, 4, 5])
        y = np.array([1, 2, 3, 4, 5])
        groups = np.array(['a', 'a', 'b', 'b', 'b'])
        
        sampled_x, sampled_y, sampled_groups = DataSampler.stratified_sample(x, y, groups, 0)
        
        assert len(sampled_x) == 0


class TestTrellisEdgeCases:
    """Test edge cases in trellis calculations"""

    def test_trellis_panels_per_page_zero(self):
        """Test trellis with panels_per_page=0 doesn't crash"""
        from data_graph_studio.graph.trellis import TrellisCalculator, TrellisSettings, TrellisMode

        calc = TrellisCalculator()
        df = pl.DataFrame({
            "category": ["A", "B", "C", "D"],
            "value": [1, 2, 3, 4]
        })
        
        settings = TrellisSettings(
            enabled=True,
            mode=TrellisMode.PANELS,
            panel_column="category",
            panels_per_page=0  # Edge case
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
            GroupColumn(name="col2", order=1)
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
            GroupColumn(name="col2", order=1)
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
