"""Tests for DatasetManager module."""

import pytest
import polars as pl

from data_graph_studio.core.file_loader import FileLoader
from data_graph_studio.core.dataset_manager import DatasetManager


@pytest.fixture
def manager(sample_csv_path):
    loader = FileLoader()
    mgr = DatasetManager(loader)
    return mgr


class TestDatasetManagerCRUD:
    def test_dataset_manager_load_success(self, manager, sample_csv_path):
        did = manager.load_dataset(sample_csv_path, name="test")
        assert did is not None
        assert manager.dataset_count == 1
        assert manager.get_dataset(did).name == "test"

    def test_dataset_manager_load_auto_name(self, manager, sample_csv_path):
        did = manager.load_dataset(sample_csv_path)
        assert manager.get_dataset(did).name == "sample.csv"

    def test_dataset_manager_load_activates_first(self, manager, sample_csv_path):
        did = manager.load_dataset(sample_csv_path)
        assert manager.active_dataset_id == did

    def test_dataset_manager_remove(self, manager, sample_csv_path):
        did = manager.load_dataset(sample_csv_path)
        assert manager.remove_dataset(did) is True
        assert manager.dataset_count == 0
        assert manager.active_dataset_id is None

    def test_dataset_manager_remove_nonexistent(self, manager):
        assert manager.remove_dataset("xxx") is False

    def test_dataset_manager_activate(self, manager, sample_csv_path):
        d1 = manager.load_dataset(sample_csv_path, name="a")
        d2 = manager.load_dataset(sample_csv_path, name="b")
        assert manager.activate_dataset(d2) is True
        assert manager.active_dataset_id == d2

    def test_dataset_manager_list(self, manager, sample_csv_path):
        manager.load_dataset(sample_csv_path, name="a")
        manager.load_dataset(sample_csv_path, name="b")
        assert len(manager.list_datasets()) == 2

    def test_dataset_manager_get_df(self, manager, sample_csv_path):
        did = manager.load_dataset(sample_csv_path)
        df = manager.get_dataset_df(did)
        assert df is not None
        assert len(df) == 10

    def test_dataset_manager_load_failure_returns_none(self, manager):
        assert manager.load_dataset("/nonexistent.csv") is None
        assert manager.dataset_count == 0


class TestDatasetManagerCallback:
    def test_dataset_manager_removing_callback(self, manager, sample_csv_path):
        removed_ids = []
        manager.set_on_dataset_removing(lambda did: removed_ids.append(did))
        did = manager.load_dataset(sample_csv_path)
        manager.remove_dataset(did)
        assert did in removed_ids


class TestDatasetManagerMemory:
    def test_dataset_manager_memory_usage(self, manager, sample_csv_path):
        manager.load_dataset(sample_csv_path)
        assert manager.get_total_memory_usage() > 0

    def test_dataset_manager_can_load(self, manager):
        ok, msg = manager.can_load_dataset(1024)
        assert ok is True


class TestDatasetManagerMeta:
    def test_dataset_manager_rename(self, manager, sample_csv_path):
        did = manager.load_dataset(sample_csv_path, name="old")
        manager.rename_dataset(did, "new")
        assert manager.get_dataset(did).name == "new"

    def test_dataset_manager_set_color(self, manager, sample_csv_path):
        did = manager.load_dataset(sample_csv_path)
        manager.set_dataset_color(did, "#ff0000")
        assert manager.get_dataset(did).color == "#ff0000"

    def test_dataset_manager_clear_all(self, manager, sample_csv_path):
        manager.load_dataset(sample_csv_path)
        manager.load_dataset(sample_csv_path)
        manager.clear_all_datasets()
        assert manager.dataset_count == 0


class TestDatasetManagerColumns:
    def test_dataset_manager_common_columns(self, manager, sample_csv_path):
        d1 = manager.load_dataset(sample_csv_path, name="a")
        d2 = manager.load_dataset(sample_csv_path, name="b")
        common = manager.get_common_columns([d1, d2])
        assert "name" in common

    def test_dataset_manager_numeric_columns(self, manager, sample_csv_path):
        did = manager.load_dataset(sample_csv_path)
        nums = manager.get_numeric_columns(did)
        assert "age" in nums or "score" in nums
