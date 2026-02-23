"""
Unit tests for chart_report_types.py and comparison_report_types.py.

Tests cover:
- ChartStatisticsConfig: to_dict / from_dict round-trip, field types
- ChartStatistics: get/set methods, to_dict structure
- get_default_statistics_for_chart: known types, unknown fallback
- ChartData: to_dict output, set_image base64 encoding, get_statistics_for_display
- ReportMetadata: to_dict structure, datetime serialization
- DatasetSummary: from_dataframe factory, missing values detection, date range
- StatisticalSummary: from_series numeric stats, non-numeric series, to_dict
- ComparisonResult: get_significance_symbol thresholds, to_dict
- DifferenceAnalysis: to_dict completeness
"""

import base64
import math
from datetime import datetime

import pytest
import polars as pl

from data_graph_studio.core.chart_report_types import (
    ChartStatisticsConfig,
    ChartStatistics,
    DEFAULT_CHART_STATISTICS,
    get_default_statistics_for_chart,
    ChartData,
)
from data_graph_studio.core.comparison_report_types import (
    ReportMetadata,
    DatasetSummary,
    StatisticalSummary,
    ComparisonResult,
    DifferenceAnalysis,
)
from data_graph_studio.core.report_enums import StatisticType


# ---------------------------------------------------------------------------
# ChartStatisticsConfig
# ---------------------------------------------------------------------------

class TestChartStatisticsConfig:
    def test_default_fields(self):
        cfg = ChartStatisticsConfig()
        assert cfg.enabled_statistics == []
        assert cfg.show_in_report is True
        assert cfg.decimal_places == 2

    def test_to_dict_returns_dict(self):
        cfg = ChartStatisticsConfig(
            enabled_statistics=[StatisticType.MEAN, StatisticType.MAX],
            show_in_report=False,
            decimal_places=3,
        )
        d = cfg.to_dict()
        assert isinstance(d, dict)
        assert d["show_in_report"] is False
        assert d["decimal_places"] == 3
        assert "mean" in d["enabled_statistics"]
        assert "max" in d["enabled_statistics"]

    def test_from_dict_round_trip(self):
        cfg = ChartStatisticsConfig(
            enabled_statistics=[StatisticType.COUNT, StatisticType.TOTAL],
            show_in_report=True,
            decimal_places=1,
        )
        restored = ChartStatisticsConfig.from_dict(cfg.to_dict())
        assert restored.show_in_report == cfg.show_in_report
        assert restored.decimal_places == cfg.decimal_places
        assert restored.enabled_statistics == cfg.enabled_statistics

    def test_from_dict_empty_statistics(self):
        cfg = ChartStatisticsConfig.from_dict({})
        assert cfg.enabled_statistics == []
        assert cfg.show_in_report is True
        assert cfg.decimal_places == 2

    def test_enabled_statistics_values_are_statistic_types(self):
        cfg = ChartStatisticsConfig.from_dict({"enabled_statistics": ["mean", "min"]})
        for s in cfg.enabled_statistics:
            assert isinstance(s, StatisticType)


# ---------------------------------------------------------------------------
# ChartStatistics
# ---------------------------------------------------------------------------

class TestChartStatistics:
    def test_get_missing_key_returns_default(self):
        cs = ChartStatistics(chart_type="bar")
        assert cs.get("nonexistent") is None
        assert cs.get("nonexistent", 42) == 42

    def test_set_and_get(self):
        cs = ChartStatistics(chart_type="line")
        cs.set("mean", 3.14)
        assert cs.get("mean") == pytest.approx(3.14)

    def test_to_dict_structure(self):
        cs = ChartStatistics(chart_type="scatter", statistics={"count": 100})
        d = cs.to_dict()
        assert d["chart_type"] == "scatter"
        assert d["statistics"]["count"] == 100

    def test_statistics_defaults_to_empty(self):
        cs = ChartStatistics(chart_type="pie")
        assert cs.statistics == {}


# ---------------------------------------------------------------------------
# get_default_statistics_for_chart / DEFAULT_CHART_STATISTICS
# ---------------------------------------------------------------------------

class TestDefaultChartStatistics:
    def test_known_chart_type_bar(self):
        stats = get_default_statistics_for_chart("bar")
        assert StatisticType.TOTAL in stats
        assert StatisticType.MEAN in stats

    def test_known_chart_type_scatter(self):
        stats = get_default_statistics_for_chart("scatter")
        assert StatisticType.CORRELATION in stats

    def test_unknown_chart_type_returns_fallback(self):
        stats = get_default_statistics_for_chart("totally_unknown_xyz")
        assert StatisticType.COUNT in stats
        assert StatisticType.MEAN in stats

    def test_case_insensitive(self):
        upper = get_default_statistics_for_chart("BAR")
        lower = get_default_statistics_for_chart("bar")
        assert upper == lower

    def test_all_chart_types_in_constant_have_entries(self):
        for chart_type in DEFAULT_CHART_STATISTICS:
            stats = get_default_statistics_for_chart(chart_type)
            assert len(stats) > 0, f"{chart_type} should have at least one default statistic"


# ---------------------------------------------------------------------------
# ChartData
# ---------------------------------------------------------------------------

class TestChartData:
    def _make(self, **kw):
        defaults = dict(id="c1", chart_type="bar", title="Test Chart")
        defaults.update(kw)
        return ChartData(**defaults)

    def test_to_dict_contains_required_keys(self):
        cd = self._make()
        d = cd.to_dict()
        for key in ("id", "chart_type", "title", "image_format", "width", "height"):
            assert key in d

    def test_set_image_stores_bytes_and_base64(self):
        cd = self._make()
        raw = b"fake_image_data"
        cd.set_image(raw, format="png")
        assert cd.image_bytes == raw
        assert cd.image_format == "png"
        assert cd.image_base64 == base64.b64encode(raw).decode("utf-8")

    def test_set_image_base64_roundtrips(self):
        cd = self._make()
        raw = b"\x89PNG\r\n\x1a\n" + bytes(range(100))
        cd.set_image(raw)
        decoded = base64.b64decode(cd.image_base64)
        assert decoded == raw

    def test_get_statistics_for_display_empty_when_no_stats(self):
        cd = self._make()
        assert cd.get_statistics_for_display() == {}

    def test_get_statistics_for_display_uses_default_chart_stats(self):
        cd = self._make(chart_type="bar")
        cs = ChartStatistics(chart_type="bar", statistics={"total": 999, "mean": 5.0})
        cd.set_statistics(cs)
        result = cd.get_statistics_for_display()
        # bar chart defaults include TOTAL and MEAN
        assert "total" in result or "mean" in result

    def test_get_statistics_for_display_respects_config_filter(self):
        cd = self._make(chart_type="bar")
        cs = ChartStatistics(chart_type="bar", statistics={"total": 100, "mean": 10.0, "count": 5})
        cfg = ChartStatisticsConfig(enabled_statistics=[StatisticType.COUNT])
        cd.set_statistics(cs)
        cd.statistics_config = cfg
        result = cd.get_statistics_for_display()
        assert "count" in result
        assert "total" not in result

    def test_to_dict_statistics_none_when_not_set(self):
        cd = self._make()
        d = cd.to_dict()
        assert d["statistics"] is None

    def test_default_dimensions(self):
        cd = self._make()
        assert cd.width == 800
        assert cd.height == 600


# ---------------------------------------------------------------------------
# ReportMetadata
# ---------------------------------------------------------------------------

class TestReportMetadata:
    def test_to_dict_has_title(self):
        rm = ReportMetadata(title="My Report")
        d = rm.to_dict()
        assert d["title"] == "My Report"

    def test_created_at_is_iso_string_in_dict(self):
        rm = ReportMetadata(title="T")
        d = rm.to_dict()
        # Should parse back without error
        dt = datetime.fromisoformat(d["created_at"])
        assert isinstance(dt, datetime)

    def test_optional_fields_default_to_none(self):
        rm = ReportMetadata(title="T")
        assert rm.subtitle is None
        assert rm.author is None
        assert rm.logo_path is None

    def test_tags_defaults_to_empty_list(self):
        rm = ReportMetadata(title="T")
        assert rm.tags == []

    def test_version_default(self):
        rm = ReportMetadata(title="T")
        assert rm.version == "1.0"


# ---------------------------------------------------------------------------
# DatasetSummary
# ---------------------------------------------------------------------------

class TestDatasetSummary:
    def _df(self):
        return pl.DataFrame({
            "a": [1, 2, None],
            "b": ["x", "y", "z"],
        })

    def test_from_dataframe_row_and_col_count(self):
        df = self._df()
        ds = DatasetSummary.from_dataframe(df, id="ds1", name="test")
        assert ds.row_count == 3
        assert ds.column_count == 2

    def test_from_dataframe_detects_null(self):
        df = self._df()
        ds = DatasetSummary.from_dataframe(df, id="ds1", name="test")
        assert "a" in ds.missing_values
        assert ds.missing_values["a"] == 1

    def test_from_dataframe_no_nulls_missing_values_empty(self):
        df = pl.DataFrame({"x": [1, 2, 3]})
        ds = DatasetSummary.from_dataframe(df, id="ds1", name="test")
        assert ds.missing_values == {}

    def test_from_dataframe_column_types_are_strings(self):
        df = self._df()
        ds = DatasetSummary.from_dataframe(df, id="ds1", name="test")
        for v in ds.column_types.values():
            assert isinstance(v, str)

    def test_from_dataframe_memory_bytes_positive(self):
        df = pl.DataFrame({"a": list(range(1000))})
        ds = DatasetSummary.from_dataframe(df, id="ds1", name="test")
        assert ds.memory_bytes > 0

    def test_to_dict_is_serializable(self):
        df = self._df()
        ds = DatasetSummary.from_dataframe(df, id="ds1", name="test")
        d = ds.to_dict()
        assert isinstance(d, dict)
        assert d["id"] == "ds1"

    def test_from_dataframe_with_date_column_sets_date_range(self):
        import datetime as dt
        df = pl.DataFrame({
            "ts": [dt.date(2023, 1, 1), dt.date(2023, 6, 15), dt.date(2023, 12, 31)],
            "v": [1, 2, 3],
        })
        ds = DatasetSummary.from_dataframe(df, id="d1", name="dated")
        assert ds.date_range is not None
        assert "min" in ds.date_range
        assert "max" in ds.date_range


# ---------------------------------------------------------------------------
# StatisticalSummary
# ---------------------------------------------------------------------------

class TestStatisticalSummary:
    def test_from_series_numeric_populates_stats(self):
        s = pl.Series("v", [1.0, 2.0, 3.0, 4.0, 5.0])
        ss = StatisticalSummary.from_series(s, column="v")
        assert ss.count == 5
        assert ss.mean == pytest.approx(3.0)
        assert ss.min == pytest.approx(1.0)
        assert ss.max == pytest.approx(5.0)

    def test_from_series_string_leaves_numeric_stats_none(self):
        s = pl.Series("name", ["alice", "bob", "carol"])
        ss = StatisticalSummary.from_series(s, column="name")
        assert ss.mean is None
        assert ss.std is None

    def test_from_series_count_is_correct(self):
        s = pl.Series("x", [10, 20, 30])
        ss = StatisticalSummary.from_series(s, column="x")
        assert ss.count == 3

    def test_from_series_null_count(self):
        s = pl.Series("x", [1, None, 3])
        ss = StatisticalSummary.from_series(s, column="x")
        assert ss.null_count == 1

    def test_from_series_iqr_computed(self):
        s = pl.Series("x", [1.0, 2.0, 3.0, 4.0, 5.0])
        ss = StatisticalSummary.from_series(s, column="x")
        if ss.q1 is not None and ss.q3 is not None:
            assert ss.iqr == pytest.approx(ss.q3 - ss.q1)

    def test_to_dict_returns_dict_with_column_key(self):
        s = pl.Series("x", [1, 2, 3])
        ss = StatisticalSummary.from_series(s, column="x", dataset_id="d1")
        d = ss.to_dict()
        assert d["column"] == "x"
        assert d["dataset_id"] == "d1"

    def test_from_series_empty_series(self):
        s = pl.Series("x", [], dtype=pl.Float64)
        ss = StatisticalSummary.from_series(s, column="x")
        assert ss.count == 0


# ---------------------------------------------------------------------------
# ComparisonResult
# ---------------------------------------------------------------------------

class TestComparisonResult:
    def _make(self, p_value=0.03):
        return ComparisonResult(
            dataset_a_id="a",
            dataset_a_name="A",
            dataset_b_id="b",
            dataset_b_name="B",
            column="score",
            test_type="ttest",
            test_statistic=2.1,
            p_value=p_value,
        )

    def test_significance_one_star(self):
        cr = self._make(p_value=0.03)
        assert cr.get_significance_symbol() == "*"

    def test_significance_two_stars(self):
        cr = self._make(p_value=0.005)
        assert cr.get_significance_symbol() == "**"

    def test_significance_three_stars(self):
        cr = self._make(p_value=0.0005)
        assert cr.get_significance_symbol() == "***"

    def test_not_significant(self):
        cr = self._make(p_value=0.1)
        assert cr.get_significance_symbol() == ""

    def test_to_dict_has_all_required_keys(self):
        cr = self._make()
        d = cr.to_dict()
        for k in ("dataset_a_id", "dataset_b_id", "column", "test_type", "p_value", "test_statistic"):
            assert k in d

    def test_to_dict_confidence_interval_as_list(self):
        cr = self._make()
        cr.confidence_interval = (0.1, 0.9)
        d = cr.to_dict()
        assert d["confidence_interval"] == [0.1, 0.9]


# ---------------------------------------------------------------------------
# DifferenceAnalysis
# ---------------------------------------------------------------------------

class TestDifferenceAnalysis:
    def _make(self):
        return DifferenceAnalysis(
            dataset_a_id="a",
            dataset_a_name="A",
            dataset_b_id="b",
            dataset_b_name="B",
            key_column="id",
            value_column="revenue",
            total_records=100,
            matched_records=95,
            positive_count=60,
            negative_count=30,
            neutral_count=5,
        )

    def test_to_dict_returns_dict(self):
        da = self._make()
        d = da.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_dataset_ids(self):
        da = self._make()
        d = da.to_dict()
        assert d["dataset_a_id"] == "a"
        assert d["dataset_b_id"] == "b"

    def test_to_dict_has_counts(self):
        da = self._make()
        d = da.to_dict()
        assert d["total_records"] == 100
        assert d["matched_records"] == 95
        assert d["positive_count"] == 60

    def test_default_top_differences_empty(self):
        da = self._make()
        assert da.top_differences == []

    def test_percentages_default_to_zero(self):
        da = self._make()
        assert da.positive_percentage == 0.0
        assert da.negative_percentage == 0.0
        assert da.neutral_percentage == 0.0
