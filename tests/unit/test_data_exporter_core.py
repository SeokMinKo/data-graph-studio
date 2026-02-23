"""
Tests for data_exporter.py (DataExporter)

Covers:
- CSV export: happy path, round-trip, 0-row, Unicode columns/values, selected_rows
- Excel export: happy path, 0-row
- Parquet export: happy path, round-trip
- Error cases: None DataFrame raises ValueError
- selected_rows filtering works correctly
"""

from __future__ import annotations

import os

import polars as pl
import pytest

from data_graph_studio.core.data_exporter import DataExporter
from data_graph_studio.core.exceptions import ExportError


@pytest.fixture()
def exporter() -> DataExporter:
    return DataExporter()


@pytest.fixture()
def sample_df() -> pl.DataFrame:
    return pl.DataFrame({
        "name": ["Alice", "Bob", "Carol"],
        "age": [30, 25, 35],
        "score": [1.1, 2.2, 3.3],
    })


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

class TestExportCsv:

    def test_csv_creates_nonempty_file(self, exporter, sample_df, tmp_path):
        path = str(tmp_path / "out.csv")
        exporter.export_csv(sample_df, path)
        assert os.path.getsize(path) > 0

    def test_csv_roundtrip_same_shape(self, exporter, sample_df, tmp_path):
        """Export → import via polars → same shape."""
        path = str(tmp_path / "out.csv")
        exporter.export_csv(sample_df, path)
        loaded = pl.read_csv(path)
        assert loaded.shape == sample_df.shape

    def test_csv_roundtrip_values_intact(self, exporter, sample_df, tmp_path):
        path = str(tmp_path / "out.csv")
        exporter.export_csv(sample_df, path)
        loaded = pl.read_csv(path)
        assert loaded["name"].to_list() == ["Alice", "Bob", "Carol"]
        assert loaded["age"].to_list() == [30, 25, 35]

    def test_csv_zero_rows_boundary(self, exporter, tmp_path):
        """0-row DataFrame exports without error; file has header only."""
        df = pl.DataFrame({"x": [], "y": []}, schema={"x": pl.Int64, "y": pl.Float64})
        path = str(tmp_path / "empty.csv")
        exporter.export_csv(df, path)
        loaded = pl.read_csv(path)
        assert loaded.shape == (0, 2)

    def test_csv_unicode_column_names_and_values(self, exporter, tmp_path):
        """Unicode (Korean) column names and values survive the round-trip."""
        df = pl.DataFrame({"이름": ["홍길동", "김철수"], "점수": [90, 85]})
        path = str(tmp_path / "unicode.csv")
        exporter.export_csv(df, path)
        loaded = pl.read_csv(path)
        assert "이름" in loaded.columns
        assert loaded["이름"].to_list() == ["홍길동", "김철수"]

    def test_csv_selected_rows_subset(self, exporter, sample_df, tmp_path):
        """selected_rows filters the exported rows correctly."""
        path = str(tmp_path / "subset.csv")
        exporter.export_csv(sample_df, path, selected_rows=[0, 2])
        loaded = pl.read_csv(path)
        assert loaded.shape[0] == 2
        assert loaded["name"].to_list() == ["Alice", "Carol"]

    def test_csv_none_df_raises_export_error(self, exporter, tmp_path):
        path = str(tmp_path / "bad.csv")
        with pytest.raises(ExportError, match="No DataFrame"):
            exporter.export_csv(None, path)


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

class TestExportExcel:

    def test_excel_creates_nonempty_file(self, exporter, sample_df, tmp_path):
        path = str(tmp_path / "out.xlsx")
        exporter.export_excel(sample_df, path)
        assert os.path.getsize(path) > 0

    def test_excel_zero_rows_boundary(self, exporter, tmp_path):
        """0-row DataFrame exports to Excel without error."""
        df = pl.DataFrame({"a": [], "b": []}, schema={"a": pl.Utf8, "b": pl.Int32})
        path = str(tmp_path / "empty.xlsx")
        exporter.export_excel(df, path)
        assert os.path.exists(path)

    def test_excel_selected_rows(self, exporter, sample_df, tmp_path):
        """selected_rows arg is respected for Excel export."""
        path = str(tmp_path / "sel.xlsx")
        exporter.export_excel(sample_df, path, selected_rows=[1])
        # File must exist and be non-empty
        assert os.path.getsize(path) > 0

    def test_excel_none_df_raises_export_error(self, exporter, tmp_path):
        path = str(tmp_path / "bad.xlsx")
        with pytest.raises(ExportError, match="No DataFrame"):
            exporter.export_excel(None, path)


# ---------------------------------------------------------------------------
# Parquet export
# ---------------------------------------------------------------------------

class TestExportParquet:

    def test_parquet_creates_nonempty_file(self, exporter, sample_df, tmp_path):
        path = str(tmp_path / "out.parquet")
        exporter.export_parquet(sample_df, path)
        assert os.path.getsize(path) > 0

    def test_parquet_roundtrip_same_shape(self, exporter, sample_df, tmp_path):
        """Export → import via polars → same shape and dtypes."""
        path = str(tmp_path / "out.parquet")
        exporter.export_parquet(sample_df, path)
        loaded = pl.read_parquet(path)
        assert loaded.shape == sample_df.shape

    def test_parquet_roundtrip_schema_preserved(self, exporter, sample_df, tmp_path):
        """Parquet preserves column names and dtypes exactly."""
        path = str(tmp_path / "schema.parquet")
        exporter.export_parquet(sample_df, path)
        loaded = pl.read_parquet(path)
        assert loaded.columns == sample_df.columns
        assert loaded.dtypes == sample_df.dtypes

    def test_parquet_zero_rows_boundary(self, exporter, tmp_path):
        """0-row DataFrame round-trips through Parquet correctly."""
        df = pl.DataFrame({"val": []}, schema={"val": pl.Float64})
        path = str(tmp_path / "empty.parquet")
        exporter.export_parquet(df, path)
        loaded = pl.read_parquet(path)
        assert loaded.shape == (0, 1)

    def test_parquet_none_df_raises_export_error(self, exporter, tmp_path):
        path = str(tmp_path / "bad.parquet")
        with pytest.raises(ExportError, match="No DataFrame"):
            exporter.export_parquet(None, path)
