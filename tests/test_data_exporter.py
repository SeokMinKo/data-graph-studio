"""Tests for DataExporter module."""

import os
import pytest
import polars as pl

from data_graph_studio.core.data_exporter import DataExporter


@pytest.fixture
def exporter():
    return DataExporter()


class TestDataExporter:
    def test_data_exporter_csv_full(self, exporter, sample_df, tmp_path):
        path = str(tmp_path / "out.csv")
        exporter.export_csv(sample_df, path)
        assert os.path.exists(path)
        loaded = pl.read_csv(path)
        assert len(loaded) == len(sample_df)

    def test_data_exporter_csv_selected_rows(self, exporter, sample_df, tmp_path):
        path = str(tmp_path / "out.csv")
        exporter.export_csv(sample_df, path, selected_rows=[0, 1, 2])
        loaded = pl.read_csv(path)
        assert len(loaded) == 3

    def test_data_exporter_parquet(self, exporter, sample_df, tmp_path):
        path = str(tmp_path / "out.parquet")
        exporter.export_parquet(sample_df, path)
        loaded = pl.read_parquet(path)
        assert len(loaded) == len(sample_df)

    def test_data_exporter_none_df_raises(self, exporter, tmp_path):
        with pytest.raises(ValueError):
            exporter.export_csv(None, str(tmp_path / "out.csv"))
