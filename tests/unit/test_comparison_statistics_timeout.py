"""
Tests for timeout protection on ComparisonEngine and DescriptiveStatistics operations.
"""
import time
from unittest.mock import MagicMock, patch

import numpy as np
import polars as pl
import pytest

from data_graph_studio.core.exceptions import DataLoadError


# ---------------------------------------------------------------------------
# ComparisonEngine.calculate_difference timeout
# ---------------------------------------------------------------------------

class TestComparisonEngineCalculateDifferenceTimeout:
    def _make_engine(self, df_a=None, df_b=None):
        """Return a ComparisonEngine with a mocked DatasetManager."""
        from data_graph_studio.core.comparison_engine import ComparisonEngine

        datasets = MagicMock()
        engine = ComparisonEngine(datasets)

        # Patch _get_df_snapshot to return controlled DataFrames
        def snapshot(did):
            if did == "a":
                return df_a
            if did == "b":
                return df_b
            return None

        engine._get_df_snapshot = snapshot
        return engine

    def test_calculate_difference_timeout_raises_data_load_error(self):
        """calculate_difference raises DataLoadError when impl exceeds timeout."""
        from data_graph_studio.core.comparison_engine import ComparisonEngine
        from data_graph_studio.core.file_loader import _run_with_timeout

        datasets = MagicMock()
        engine = ComparisonEngine(datasets)

        # Patch _calculate_difference_impl to block
        engine._calculate_difference_impl = MagicMock(side_effect=lambda *a, **k: time.sleep(10))

        with patch(
            "data_graph_studio.core.comparison_engine._run_with_timeout",
            side_effect=lambda fn, timeout_s, operation: _run_with_timeout(fn, 0.05, operation),
        ):
            with pytest.raises(DataLoadError, match="시간 초과"):
                engine.calculate_difference("a", "b", "val")

    def test_calculate_difference_returns_result_within_timeout(self):
        """calculate_difference returns a DataFrame when it completes in time."""
        df_a = pl.DataFrame({"val": [1.0, 2.0, 3.0]})
        df_b = pl.DataFrame({"val": [0.5, 1.0, 1.5]})

        engine = self._make_engine(df_a=df_a, df_b=df_b)
        result = engine.calculate_difference("a", "b", "val")

        assert result is not None
        assert "diff" in result.columns
        assert "diff_pct" in result.columns
        assert len(result) == 3

    def test_calculate_difference_returns_none_for_missing_dataset(self):
        """calculate_difference returns None when a dataset is missing."""
        engine = self._make_engine(df_a=None, df_b=None)
        result = engine.calculate_difference("a", "b", "val")
        assert result is None


# ---------------------------------------------------------------------------
# ComparisonEngine.get_comparison_statistics timeout
# ---------------------------------------------------------------------------

class TestComparisonEngineGetComparisonStatisticsTimeout:
    def test_get_comparison_statistics_timeout_raises_data_load_error(self):
        """get_comparison_statistics raises DataLoadError when impl exceeds timeout."""
        from data_graph_studio.core.comparison_engine import ComparisonEngine
        from data_graph_studio.core.file_loader import _run_with_timeout

        datasets = MagicMock()
        engine = ComparisonEngine(datasets)

        engine._get_comparison_statistics_impl = MagicMock(
            side_effect=lambda *a, **k: time.sleep(10)
        )

        with patch(
            "data_graph_studio.core.comparison_engine._run_with_timeout",
            side_effect=lambda fn, timeout_s, operation: _run_with_timeout(fn, 0.05, operation),
        ):
            with pytest.raises(DataLoadError, match="시간 초과"):
                engine.get_comparison_statistics(["a", "b"], "val")

    def test_get_comparison_statistics_returns_dict_within_timeout(self):
        """get_comparison_statistics returns a dict with stats when it completes in time."""
        from data_graph_studio.core.comparison_engine import ComparisonEngine

        df = pl.DataFrame({"val": [1.0, 2.0, 3.0, 4.0, 5.0]})

        datasets = MagicMock()
        mock_ds = MagicMock()
        mock_ds.name = "Dataset A"
        mock_ds.color = "#ff0000"
        datasets.get_dataset.return_value = mock_ds

        engine = ComparisonEngine(datasets)
        engine._get_df_snapshot = lambda did: df

        result = engine.get_comparison_statistics(["ds_a"], "val")

        assert "ds_a" in result
        stats = result["ds_a"]
        assert stats["count"] == 5
        assert abs(stats["mean"] - 3.0) < 1e-9


# ---------------------------------------------------------------------------
# DescriptiveStatistics.calculate timeout
# ---------------------------------------------------------------------------

class TestDescriptiveStatisticsCalculateTimeout:
    def test_calculate_timeout_raises_data_load_error(self):
        """DescriptiveStatistics.calculate raises DataLoadError when impl exceeds timeout."""
        from data_graph_studio.core.statistics import DescriptiveStatistics
        from data_graph_studio.core.file_loader import _run_with_timeout

        ds = DescriptiveStatistics()
        ds._calculate_impl = MagicMock(side_effect=lambda *a, **k: time.sleep(10))

        with patch(
            "data_graph_studio.core.statistics._run_with_timeout",
            side_effect=lambda fn, timeout_s, operation: _run_with_timeout(fn, 0.05, operation),
        ):
            with pytest.raises(DataLoadError, match="시간 초과"):
                ds.calculate(np.array([1.0, 2.0, 3.0]))

    def test_calculate_returns_stats_within_timeout(self):
        """DescriptiveStatistics.calculate returns a full stats dict in normal usage."""
        from data_graph_studio.core.statistics import DescriptiveStatistics

        ds = DescriptiveStatistics()
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = ds.calculate(values)

        assert result["n"] == 5
        assert abs(result["mean"] - 3.0) < 1e-9
        assert "skewness" in result
        assert "kurtosis" in result
        assert "se" in result

    def test_calculate_returns_empty_dict_for_all_nan(self):
        """DescriptiveStatistics.calculate returns {} when all values are NaN."""
        from data_graph_studio.core.statistics import DescriptiveStatistics

        ds = DescriptiveStatistics()
        result = ds.calculate(np.array([float("nan"), float("nan")]))
        assert result == {}
