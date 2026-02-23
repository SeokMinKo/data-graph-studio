"""
Tests for comparison_report.py.

ComparisonReport depends on DataEngine and AppState. We mock both so the tests
are pure unit tests with no Qt, no disk I/O (except export tests that use tmp_path),
and no real data engine logic.

Covers:
- generate_report_data: no datasets (error path), minimal two-dataset case
- _generate_html_report: structure sanity (title, datasets section present)
- _render_html_* helpers: individual section rendering
- export_json: normal success, raises ExportError on write failure, no-datasets error
- export_csv: normal success, no-datasets error
- export_html: normal success, raises ExportError on write failure, no-datasets error
"""

import json
from enum import Enum
from typing import Any, Dict, List
from unittest.mock import MagicMock

import polars as pl
import pytest

from data_graph_studio.core.comparison_report import ComparisonReport
from data_graph_studio.core.exceptions import ExportError


# ---------------------------------------------------------------------------
# Minimal stand-in for ComparisonMode enum
# ---------------------------------------------------------------------------

class _FakeComparisonMode(Enum):
    OVERLAY = "overlay"
    SIDE_BY_SIDE = "side_by_side"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_report(
    dataset_ids: List[str] = None,
    common_cols: List[str] = None,
    stats: Dict[str, Any] = None,
) -> ComparisonReport:
    """Build a ComparisonReport with mocked engine and state."""
    engine = MagicMock()
    state = MagicMock()

    dataset_ids = dataset_ids or []
    common_cols = common_cols or []

    state.comparison_dataset_ids = dataset_ids
    state.comparison_mode = _FakeComparisonMode.OVERLAY

    def fake_get_metadata(did):
        m = MagicMock()
        m.name = f"Dataset_{did}"
        m.file_path = f"/tmp/{did}.csv"
        m.row_count = 100
        m.column_count = 5
        m.color = "#1f77b4"
        return m

    state.get_dataset_metadata.side_effect = fake_get_metadata

    def fake_get_dataset(did):
        ds = MagicMock()
        ds.name = f"Dataset_{did}"
        ds.row_count = 100
        ds.column_count = 5
        ds.color = "#1f77b4"
        # Give it a real df so numeric column detection works
        ds.df = pl.DataFrame({"val": [1.0, 2.0, 3.0]})
        return ds

    engine.get_dataset.side_effect = fake_get_dataset
    engine.get_common_columns.return_value = common_cols
    engine.calculate_descriptive_comparison.return_value = stats or {}
    engine.perform_statistical_test.return_value = {"error": "no test"}
    engine.calculate_correlation.return_value = {"error": "no corr"}

    return ComparisonReport(engine, state)


# ---------------------------------------------------------------------------
# generate_report_data
# ---------------------------------------------------------------------------

class TestGenerateReportData:
    def test_no_datasets_returns_error_key(self):
        report = _make_report(dataset_ids=[])
        result = report.generate_report_data([])
        assert "error" in result

    def test_no_datasets_via_state_returns_error(self):
        report = _make_report(dataset_ids=[])
        result = report.generate_report_data()
        assert "error" in result

    def test_single_dataset_returns_report_dict(self):
        report = _make_report(dataset_ids=["ds1"])
        result = report.generate_report_data(["ds1"])
        assert "error" not in result
        assert result["title"] == "Data Comparison Report"
        assert len(result["datasets"]) == 1

    def test_two_datasets_structure(self):
        report = _make_report(dataset_ids=["ds1", "ds2"], common_cols=["val"])
        result = report.generate_report_data(["ds1", "ds2"])
        assert "error" not in result
        assert len(result["datasets"]) == 2
        assert result["common_columns"] == ["val"]
        assert "generated_at" in result
        assert "comparison_mode" in result
        assert "statistics" in result
        assert "statistical_tests" in result
        assert "correlations" in result

    def test_comparison_mode_in_result(self):
        report = _make_report(dataset_ids=["ds1"])
        result = report.generate_report_data(["ds1"])
        assert result["comparison_mode"] == "overlay"

    def test_dataset_metadata_used_when_available(self):
        report = _make_report(dataset_ids=["abc"])
        result = report.generate_report_data(["abc"])
        ds_info = result["datasets"][0]
        assert ds_info["name"] == "Dataset_abc"
        assert ds_info["row_count"] == 100


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------

class TestHtmlGeneration:
    def test_generate_html_contains_title(self):
        report = _make_report(dataset_ids=["ds1"])
        data = report.generate_report_data(["ds1"])
        html = report._generate_html_report(data)
        assert "Data Comparison Report" in html

    def test_generate_html_contains_doctype(self):
        report = _make_report(dataset_ids=["ds1"])
        data = report.generate_report_data(["ds1"])
        html = report._generate_html_report(data)
        assert "<!DOCTYPE html>" in html

    def test_generate_html_has_dataset_section(self):
        report = _make_report(dataset_ids=["ds1", "ds2"])
        data = report.generate_report_data(["ds1", "ds2"])
        html = report._generate_html_report(data)
        assert "Datasets" in html

    def test_render_html_footer_closes_tags(self):
        footer = ComparisonReport._render_html_footer()
        assert "</html>" in footer
        assert "</body>" in footer

    def test_render_html_tests_section_empty_when_no_tests(self):
        report = _make_report(dataset_ids=["ds1"])
        data = report.generate_report_data(["ds1"])
        data["statistical_tests"] = []
        section = report._render_html_tests_section(data)
        assert section == ""

    def test_render_html_correlations_section_empty_when_no_correlations(self):
        report = _make_report(dataset_ids=["ds1"])
        data = report.generate_report_data(["ds1"])
        data["correlations"] = []
        section = report._render_html_correlations_section(data)
        assert section == ""

    def test_render_html_stats_section_empty_when_no_stats(self):
        report = _make_report(dataset_ids=["ds1"])
        data = report.generate_report_data(["ds1"])
        data["statistics"] = {}
        section = report._render_html_stats_section(data)
        assert section == ""


# ---------------------------------------------------------------------------
# export_json
# ---------------------------------------------------------------------------

class TestExportJson:
    def test_exports_valid_json_file(self, tmp_path):
        report = _make_report(dataset_ids=["ds1"])
        out = str(tmp_path / "report.json")
        result = report.export_json(out, ["ds1"])
        assert result is True
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        assert data["title"] == "Data Comparison Report"

    def test_export_json_returns_false_when_no_datasets(self, tmp_path):
        report = _make_report(dataset_ids=[])
        out = str(tmp_path / "report.json")
        result = report.export_json(out, [])
        assert result is False

    def test_export_json_raises_export_error_on_write_error(self, tmp_path):
        report = _make_report(dataset_ids=["ds1"])
        # Write to a non-existent directory
        out = str(tmp_path / "no_such_dir" / "report.json")
        with pytest.raises(ExportError) as exc_info:
            report.export_json(out, ["ds1"])
        err = exc_info.value
        assert err.operation == "export_json"
        assert "path" in err.context


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------

class TestExportCsv:
    def test_exports_csv_file(self, tmp_path):
        report = _make_report(dataset_ids=["ds1"])
        out = str(tmp_path / "report.csv")
        result = report.export_csv(out, ["ds1"])
        assert result is True
        with open(out, encoding="utf-8") as f:
            content = f.read()
        assert "Data Comparison Report" in content

    def test_export_csv_returns_false_when_no_datasets(self, tmp_path):
        report = _make_report(dataset_ids=[])
        out = str(tmp_path / "report.csv")
        result = report.export_csv(out, [])
        assert result is False

    def test_csv_contains_dataset_names(self, tmp_path):
        report = _make_report(dataset_ids=["ds1", "ds2"])
        out = str(tmp_path / "report.csv")
        report.export_csv(out, ["ds1", "ds2"])
        with open(out, encoding="utf-8") as f:
            content = f.read()
        assert "Dataset_ds1" in content
        assert "Dataset_ds2" in content

    def test_export_csv_raises_export_error_on_write_error(self, tmp_path):
        report = _make_report(dataset_ids=["ds1"])
        out = str(tmp_path / "no_such_dir" / "report.csv")
        with pytest.raises(ExportError) as exc_info:
            report.export_csv(out, ["ds1"])
        err = exc_info.value
        assert err.operation == "export_csv"
        assert "path" in err.context


# ---------------------------------------------------------------------------
# export_html
# ---------------------------------------------------------------------------

class TestExportHtml:
    def test_exports_html_file(self, tmp_path):
        report = _make_report(dataset_ids=["ds1"])
        out = str(tmp_path / "report.html")
        result = report.export_html(out, ["ds1"])
        assert result is True
        with open(out, encoding="utf-8") as f:
            content = f.read()
        assert "<!DOCTYPE html>" in content

    def test_export_html_returns_false_when_no_datasets(self, tmp_path):
        report = _make_report(dataset_ids=[])
        out = str(tmp_path / "report.html")
        result = report.export_html(out, [])
        assert result is False

    def test_export_html_raises_export_error_on_write_error(self, tmp_path):
        report = _make_report(dataset_ids=["ds1"])
        out = str(tmp_path / "no_dir" / "report.html")
        with pytest.raises(ExportError) as exc_info:
            report.export_html(out, ["ds1"])
        err = exc_info.value
        assert err.operation == "export_html"
        assert "path" in err.context
