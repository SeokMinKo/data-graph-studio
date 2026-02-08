"""Tests for FileLoader module."""

import os
import pytest
import polars as pl

from data_graph_studio.core.file_loader import FileLoader
from data_graph_studio.core.data_engine import FileType, PrecisionMode


class TestFileLoaderDetection:
    def test_file_loader_detect_csv(self):
        assert FileLoader.detect_file_type("data.csv") == FileType.CSV

    def test_file_loader_detect_parquet(self):
        assert FileLoader.detect_file_type("data.parquet") == FileType.PARQUET

    def test_file_loader_detect_unknown_defaults_txt(self):
        assert FileLoader.detect_file_type("data.xyz") == FileType.TXT

    def test_file_loader_detect_delimiter_csv(self, sample_csv_path):
        assert FileLoader.detect_delimiter(sample_csv_path) == ","


class TestFileLoaderLoad:
    def test_file_loader_csv_load_success(self, sample_csv_path):
        loader = FileLoader()
        assert loader.load_file(sample_csv_path) is True
        assert loader.df is not None
        assert loader.row_count == 10
        assert "name" in loader.columns

    def test_file_loader_parquet_load_success(self, sample_parquet_path):
        loader = FileLoader()
        assert loader.load_file(sample_parquet_path) is True
        assert loader.row_count == 10

    def test_file_loader_json_load_success(self, sample_json_path):
        loader = FileLoader()
        assert loader.load_file(sample_json_path) is True
        assert loader.row_count == 2

    def test_file_loader_tsv_load_success(self, sample_tsv_path):
        loader = FileLoader()
        assert loader.load_file(sample_tsv_path) is True
        assert loader.row_count == 10

    def test_file_loader_nonexistent_file_returns_false(self):
        loader = FileLoader()
        assert loader.load_file("/nonexistent/path.csv") is False
        assert loader.df is None

    def test_file_loader_cancel_loading(self, sample_csv_path):
        loader = FileLoader()
        loader._cancel_loading = True
        # async_load=False but cancel is already set
        result = loader.load_file(sample_csv_path)
        # Cancel is checked after loading, so df should be None
        assert loader.df is None

    def test_file_loader_clear(self, sample_csv_path):
        loader = FileLoader()
        loader.load_file(sample_csv_path)
        assert loader.df is not None
        loader.clear()
        assert loader.df is None
        assert loader.is_loaded is False


class TestFileLoaderPrecision:
    def test_file_loader_precision_mode_high(self, sample_csv_path):
        loader = FileLoader(precision_mode=PrecisionMode.HIGH)
        loader.load_file(sample_csv_path)
        # Float64 should be preserved in HIGH mode
        assert loader.df is not None

    def test_file_loader_add_precision_column(self):
        loader = FileLoader()
        loader.add_precision_column("price")
        assert loader._is_precision_sensitive_column("price")
        assert loader._is_precision_sensitive_column("total_amount")  # pattern match
        assert not loader._is_precision_sensitive_column("name")


class TestFileLoaderEncoding:
    def test_normalize_encoding_utf8(self):
        assert FileLoader._normalize_encoding("utf-8") == "utf8"
        assert FileLoader._normalize_encoding("UTF-8") == "utf8"
        assert FileLoader._normalize_encoding("") == "utf8"
        assert FileLoader._normalize_encoding("latin-1") == "iso-8859-1"


class TestFileLoaderLazy:
    def test_file_loader_load_lazy_csv(self, sample_csv_path):
        loader = FileLoader()
        assert loader.load_lazy(sample_csv_path) is True
        assert loader.has_lazy is True

    def test_file_loader_collect_lazy(self, sample_csv_path):
        loader = FileLoader()
        loader.load_lazy(sample_csv_path)
        assert loader.collect_lazy() is True
        assert loader.df is not None
        assert loader.row_count == 10

    def test_file_loader_query_lazy(self, sample_csv_path):
        loader = FileLoader()
        loader.load_lazy(sample_csv_path)
        result = loader.query_lazy(pl.col("age") > 28)
        assert result is not None

    def test_file_loader_no_lazy_returns_none(self):
        loader = FileLoader()
        assert loader.query_lazy(pl.col("x") > 1) is None
        assert loader.collect_lazy() is False
