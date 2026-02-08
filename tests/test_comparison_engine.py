"""Tests for ComparisonEngine module."""

import pytest
import polars as pl

from data_graph_studio.core.file_loader import FileLoader
from data_graph_studio.core.dataset_manager import DatasetManager
from data_graph_studio.core.comparison_engine import ComparisonEngine


@pytest.fixture
def setup(sample_csv_path):
    loader = FileLoader()
    mgr = DatasetManager(loader)
    engine = ComparisonEngine(mgr)
    d1 = mgr.load_dataset(sample_csv_path, name="ds1")
    d2 = mgr.load_dataset(sample_csv_path, name="ds2")
    return engine, mgr, d1, d2


class TestComparisonEngineBasic:
    def test_comparison_engine_statistics(self, setup):
        engine, mgr, d1, d2 = setup
        stats = engine.get_comparison_statistics([d1, d2], "age")
        assert d1 in stats
        assert "mean" in stats[d1]

    def test_comparison_engine_difference(self, setup):
        engine, mgr, d1, d2 = setup
        diff = engine.calculate_difference(d1, d2, "age")
        assert diff is not None
        assert "diff" in diff.columns

    def test_comparison_engine_difference_with_key(self, setup):
        engine, mgr, d1, d2 = setup
        diff = engine.calculate_difference(d1, d2, "age", key_column="name")
        assert diff is not None

    def test_comparison_engine_merge_vertical(self, setup):
        engine, mgr, d1, d2 = setup
        merged = engine.merge_datasets([d1, d2])
        assert merged is not None
        assert len(merged) == 20  # 10 + 10

    def test_comparison_engine_merge_with_key(self, setup):
        engine, mgr, d1, d2 = setup
        merged = engine.merge_datasets([d1, d2], key_column="name")
        assert merged is not None

    def test_comparison_engine_align(self, setup):
        engine, mgr, d1, d2 = setup
        aligned = engine.align_datasets([d1, d2], "name")
        assert d1 in aligned
        assert d2 in aligned


class TestComparisonEngineStatistical:
    def test_comparison_engine_statistical_test(self, setup):
        engine, mgr, d1, d2 = setup
        result = engine.perform_statistical_test(d1, d2, "age")
        assert result is not None
        assert "p_value" in result or "error" in result

    def test_comparison_engine_correlation(self, setup):
        engine, mgr, d1, d2 = setup
        result = engine.calculate_correlation(d1, d2, "age")
        assert result is not None
        assert "correlation" in result or "error" in result

    def test_comparison_engine_normality(self, setup):
        engine, mgr, d1, d2 = setup
        result = engine.get_normality_test(d1, "age")
        assert result is not None

    def test_comparison_engine_descriptive(self, setup):
        engine, mgr, d1, d2 = setup
        result = engine.calculate_descriptive_comparison([d1, d2], "age")
        assert d1 in result


class TestComparisonEngineEdgeCases:
    def test_comparison_engine_missing_dataset(self, setup):
        engine, _, _, _ = setup
        result = engine.calculate_difference("xxx", "yyy", "age")
        assert result is None

    def test_comparison_engine_missing_column(self, setup):
        engine, _, d1, d2 = setup
        result = engine.calculate_difference(d1, d2, "nonexistent")
        assert result is None
