"""
Tests for Task 4.2: ValueError/RuntimeError → typed exception conversions.

Covers:
- dataset_manager._load_single: RuntimeError → DatasetError
- data_query.filter: ValueError (unknown operator) → QueryError
- export_workers.ExportWorker.run: ValueError (unknown task) → ExportError
- data_exporter.DataExporter.export_csv/excel/parquet: ValueError (None df) → ExportError
- report.ReportManager.generate_report: ValueError (unsupported format) → ExportError
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import polars as pl
import pytest

from data_graph_studio.core.exceptions import (
    DatasetError,
    QueryError,
    ExportError,
)


# ---------------------------------------------------------------------------
# dataset_manager: _load_single RuntimeError → DatasetError
# ---------------------------------------------------------------------------

class TestDatasetManagerTypedExceptions:

    def test_parallel_load_failure_produces_dataset_error(self, tmp_path):
        """When a file fails to load in load_datasets_parallel, result contains DatasetError."""
        from data_graph_studio.core.dataset_manager import DatasetManager
        from unittest.mock import MagicMock

        loader = MagicMock()
        loader._precision_mode = None
        manager = DatasetManager(loader)

        nonexistent = str(tmp_path / "ghost.csv")

        # load_datasets_parallel captures exceptions in results dict
        results = manager.load_datasets_parallel([nonexistent], max_workers=1)
        exc = results.get(nonexistent)
        # Should be a DatasetError (or subclass), not a raw RuntimeError
        assert exc is not None
        assert isinstance(exc, DatasetError), (
            f"Expected DatasetError, got {type(exc).__name__}: {exc}"
        )

    def test_load_single_raises_dataset_error_not_runtime_error(self, tmp_path):
        """_load_single must raise DatasetError (not RuntimeError) when load fails."""
        from data_graph_studio.core.dataset_manager import DatasetManager

        loader = MagicMock()
        loader._precision_mode = None
        manager = DatasetManager(loader)

        # Patch FileLoader so load_file returns False (simulated failure)
        with patch("data_graph_studio.core.dataset_manager.FileLoader") as MockLoader:
            instance = MockLoader.return_value
            instance.load_file.return_value = False
            instance._df = None

            results = manager.load_datasets_parallel(["/fake/path.csv"], max_workers=1)
            exc = results.get("/fake/path.csv")
            assert isinstance(exc, DatasetError), (
                f"Expected DatasetError, got {type(exc).__name__}: {exc}"
            )
            assert not isinstance(exc, RuntimeError)


# ---------------------------------------------------------------------------
# data_query: filter unknown operator → QueryError
# ---------------------------------------------------------------------------

class TestDataQueryTypedExceptions:

    def test_filter_unknown_operator_raises_query_error(self):
        """filter() with an unrecognised operator must raise QueryError, not ValueError."""
        from data_graph_studio.core.data_query import DataQuery

        dq = DataQuery()
        df = pl.DataFrame({"x": [1, 2, 3]})

        with pytest.raises(QueryError):
            dq.filter(df, "x", "totally_unknown_op", "val")

    def test_filter_unknown_operator_not_value_error(self):
        """Specifically: should NOT raise a bare ValueError any more."""
        from data_graph_studio.core.data_query import DataQuery

        dq = DataQuery()
        df = pl.DataFrame({"x": [1, 2, 3]})

        with pytest.raises(QueryError):
            dq.filter(df, "x", "bad_op", "val")

    def test_filter_unknown_operator_message_preserved(self):
        """Error message must mention the bad operator."""
        from data_graph_studio.core.data_query import DataQuery

        dq = DataQuery()
        df = pl.DataFrame({"x": [1, 2, 3]})

        with pytest.raises(QueryError, match="bad_operator"):
            dq.filter(df, "x", "bad_operator", "val")


# ---------------------------------------------------------------------------
# export_workers: unknown task → ExportError
# ---------------------------------------------------------------------------

class TestExportWorkerTypedExceptions:

    def test_unknown_task_raises_export_error(self):
        """ExportWorker.run() with unknown task should call on_failed (ExportError caught)."""
        from data_graph_studio.core.export_workers import ExportWorker, ExportFormat

        failed_messages = []
        worker = ExportWorker(
            task="totally_unknown_task",
            fmt=ExportFormat.PNG,
            on_failed=lambda msg: failed_messages.append(msg),
        )
        worker.run()
        # on_failed should have been called (the ExportError is caught in run() itself)
        assert len(failed_messages) == 1

    def test_unknown_task_does_not_propagate_value_error(self):
        """The ValueError for unknown task must be converted before propagating."""
        from data_graph_studio.core.export_workers import ExportWorker, ExportFormat

        raised = []
        worker = ExportWorker(
            task="unknown_xyz",
            fmt=ExportFormat.PNG,
            on_failed=lambda msg: None,
        )
        # run() must not raise anything to the caller
        try:
            worker.run()
        except Exception as e:
            raised.append(e)
        assert raised == [], f"run() raised unexpectedly: {raised}"


# ---------------------------------------------------------------------------
# data_exporter: None df → ExportError
# ---------------------------------------------------------------------------

class TestDataExporterTypedExceptions:

    def test_export_csv_none_df_raises_export_error(self, tmp_path):
        """export_csv with None df must raise ExportError, not ValueError."""
        from data_graph_studio.core.data_exporter import DataExporter

        exporter = DataExporter()
        with pytest.raises(ExportError):
            exporter.export_csv(None, str(tmp_path / "out.csv"))

    def test_export_excel_none_df_raises_export_error(self, tmp_path):
        """export_excel with None df must raise ExportError, not ValueError."""
        from data_graph_studio.core.data_exporter import DataExporter

        exporter = DataExporter()
        with pytest.raises(ExportError):
            exporter.export_excel(None, str(tmp_path / "out.xlsx"))

    def test_export_parquet_none_df_raises_export_error(self, tmp_path):
        """export_parquet with None df must raise ExportError, not ValueError."""
        from data_graph_studio.core.data_exporter import DataExporter

        exporter = DataExporter()
        with pytest.raises(ExportError):
            exporter.export_parquet(None, str(tmp_path / "out.parquet"))

    def test_export_csv_error_message_preserved(self, tmp_path):
        """ExportError message still says 'No DataFrame to export'."""
        from data_graph_studio.core.data_exporter import DataExporter

        exporter = DataExporter()
        with pytest.raises(ExportError, match="No DataFrame"):
            exporter.export_csv(None, str(tmp_path / "out.csv"))


# ---------------------------------------------------------------------------
# report: unsupported format → ExportError
# ---------------------------------------------------------------------------

class TestReportManagerTypedExceptions:

    def _make_report_data(self):
        """Build a minimal valid ReportData for testing."""
        from data_graph_studio.core.report_types import ReportData
        from data_graph_studio.core.comparison_report_types import ReportMetadata
        meta = ReportMetadata(title="Test Report")
        return ReportData(metadata=meta)

    def test_generate_report_unsupported_format_raises_export_error(self):
        """generate_report() with no registered generator must raise ExportError."""
        from data_graph_studio.core.report import ReportManager
        from data_graph_studio.core.report_types import ReportOptions, ReportFormat

        manager = ReportManager()
        # Remove all registered generators to force the "unsupported format" path
        manager.generators.clear()

        options = ReportOptions(format=ReportFormat.HTML)
        data = self._make_report_data()

        with pytest.raises(ExportError):
            manager.generate_report(data, options)

    def test_generate_report_not_value_error(self):
        """Specifically: should NOT raise a bare ValueError any more."""
        from data_graph_studio.core.report import ReportManager
        from data_graph_studio.core.report_types import ReportOptions, ReportFormat

        manager = ReportManager()
        manager.generators.clear()

        options = ReportOptions(format=ReportFormat.PDF)
        data = self._make_report_data()

        with pytest.raises(ExportError):
            manager.generate_report(data, options)

    def test_generate_report_error_message_contains_format(self):
        """ExportError message mentions the bad format."""
        from data_graph_studio.core.report import ReportManager
        from data_graph_studio.core.report_types import ReportOptions, ReportFormat

        manager = ReportManager()
        manager.generators.clear()

        options = ReportOptions(format=ReportFormat.HTML)
        data = self._make_report_data()

        with pytest.raises(ExportError, match="HTML"):
            manager.generate_report(data, options)
