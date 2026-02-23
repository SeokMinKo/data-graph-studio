"""
Unit tests for AnalysisMixin and DatasetMixin.

Both mixins use the delegation pattern — they require a host object that
provides the collaborators they forward calls to. Tests use lightweight
fakes (not mocks) for clean, dependency-free verification.

Tests cover:
- AnalysisMixin: recommend_chart_type with time/categorical/large/small data
- AnalysisMixin: data_quality_report structure and field types
- AnalysisMixin: add_virtual_column success and error paths
- DatasetMixin: property delegation (MAX_DATASETS, datasets, dataset_count, etc.)
- DatasetMixin: load_dataset_from_dataframe calls clear_cache and syncs loader
- DatasetMixin: remove_dataset syncs loader state
- DatasetMixin: clear_all_datasets resets loader
"""

import pytest
import polars as pl

from data_graph_studio.core.data_engine_analysis_mixin import AnalysisMixin
from data_graph_studio.core.data_engine_dataset_mixin import DatasetMixin
from data_graph_studio.core.exceptions import QueryError


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------

class _FakeComparison:
    """Captures calls made by AnalysisMixin delegation methods."""
    def align_datasets(self, *a, **kw): return "aligned"
    def calculate_difference(self, *a, **kw): return "diff"
    def get_comparison_statistics(self, *a, **kw): return {}
    def merge_datasets(self, *a, **kw): return "merged"
    def perform_statistical_test(self, *a, **kw): return {"test": "t", "p_value": 0.05}
    def calculate_correlation(self, *a, **kw): return {"r": 0.9}
    def calculate_descriptive_comparison(self, *a, **kw): return {}
    def get_normality_test(self, *a, **kw): return {"is_normal": True}


class _FakeDatasetManager:
    MAX_DATASETS = 5
    MAX_TOTAL_MEMORY = 1024 * 1024 * 512
    DEFAULT_COLORS = ["#ff0000", "#00ff00", "#0000ff"]

    def __init__(self):
        self._datasets = {}
        self._active_dataset_id = None
        self._color_index = 0

    @property
    def datasets(self):
        return self._datasets

    @property
    def dataset_count(self):
        return len(self._datasets)

    @property
    def active_dataset_id(self):
        return self._active_dataset_id

    @property
    def active_dataset(self):
        return self._datasets.get(self._active_dataset_id)

    def get_dataset(self, did):
        return self._datasets.get(did)

    def get_dataset_df(self, did):
        ds = self._datasets.get(did)
        return ds.df if ds else None

    def list_datasets(self):
        return list(self._datasets.keys())

    def get_total_memory_usage(self):
        return 0

    def can_load_dataset(self, sz):
        return sz < self.MAX_TOTAL_MEMORY

    def set_dataset_color(self, did, c): pass
    def rename_dataset(self, did, n): pass
    def get_common_columns(self, ids=None): return []
    def get_numeric_columns(self, did): return []

    def load_dataset(self, path, name=None, dataset_id=None, **kw):
        return "ds_loaded"

    def load_dataset_from_dataframe(self, df, name="Untitled", dataset_id=None, source_path=None):
        did = dataset_id or "ds_fake"
        self._active_dataset_id = did
        self._datasets[did] = type("DS", (), {
            "df": df, "lazy_df": df.lazy(), "source": source_path, "profile": None
        })()
        return did

    def remove_dataset(self, dataset_id):
        if dataset_id in self._datasets:
            del self._datasets[dataset_id]
            if self._active_dataset_id == dataset_id:
                self._active_dataset_id = None
            return True
        return False

    def activate_dataset(self, dataset_id):
        if dataset_id in self._datasets:
            self._active_dataset_id = dataset_id
            return True
        return False

    def clear_all_datasets(self):
        self._datasets.clear()
        self._active_dataset_id = None


class _FakeLoader:
    def __init__(self):
        self._df = None
        self._lazy_df = None
        self._source = None
        self._profile = None


class _FakeChartType:
    """Minimal ChartType stand-in used by the AnalysisMixin recommend test."""
    pass


class _AnalysisHost(AnalysisMixin):
    """Minimal host object that satisfies AnalysisMixin's declared requirements."""

    def __init__(self, df=None):
        self._comparison = _FakeComparison()
        self.df = df
        self.dtypes = {col: str(df[col].dtype) for col in df.columns} if df is not None else {}
        self._virtual_columns = set()

    def update_dataframe(self, new_df):
        self.df = new_df

    def is_column_categorical(self, col: str) -> bool:
        if self.df is None or col not in self.df.columns:
            return False
        return self.df[col].dtype == pl.Utf8 or self.df[col].dtype == pl.Categorical


class _DatasetHost(DatasetMixin):
    """Minimal host that satisfies DatasetMixin's declared requirements."""

    def __init__(self):
        self._datasets_mgr = _FakeDatasetManager()
        self._loader = _FakeLoader()
        self._cache_cleared = 0

    def _clear_cache(self):
        self._cache_cleared += 1

    def _sync_active_dataset(self):
        ds = self._datasets_mgr.active_dataset
        if ds:
            self._loader._df = ds.df
            self._loader._lazy_df = ds.lazy_df
            self._loader._source = ds.source
            self._loader._profile = ds.profile


# ---------------------------------------------------------------------------
# AnalysisMixin: data_quality_report
# ---------------------------------------------------------------------------

class TestDataQualityReport:
    def test_returns_empty_dict_when_no_df(self):
        host = _AnalysisHost(df=None)
        assert host.data_quality_report() == {}

    def test_returns_dict_with_expected_keys(self):
        df = pl.DataFrame({"x": [1, 2, 3], "y": [None, 2.0, 3.0]})
        host = _AnalysisHost(df=df)
        report = host.data_quality_report()
        assert "row_count" in report
        assert "col_count" in report
        assert "null_counts" in report
        assert "null_pct" in report
        assert "duplicate_rows" in report
        assert "dtypes" in report

    def test_row_count_is_correct(self):
        df = pl.DataFrame({"a": [10, 20, 30]})
        host = _AnalysisHost(df=df)
        assert host.data_quality_report()["row_count"] == 3

    def test_col_count_is_correct(self):
        df = pl.DataFrame({"a": [1], "b": [2], "c": [3]})
        host = _AnalysisHost(df=df)
        assert host.data_quality_report()["col_count"] == 3

    def test_null_counts_detects_nulls(self):
        df = pl.DataFrame({"x": [None, None, 1]})
        host = _AnalysisHost(df=df)
        report = host.data_quality_report()
        assert report["null_counts"]["x"] == 2

    def test_no_duplicates_single_row(self):
        df = pl.DataFrame({"a": [1]})
        host = _AnalysisHost(df=df)
        assert host.data_quality_report()["duplicate_rows"] == 0


# ---------------------------------------------------------------------------
# AnalysisMixin: recommend_chart_type
# ---------------------------------------------------------------------------

class TestRecommendChartType:
    def test_returns_empty_list_when_no_df(self):
        host = _AnalysisHost(df=None)
        result = host.recommend_chart_type("x", ["y"])
        assert result == []

    def test_returns_list_of_tuples(self):
        df = pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        host = _AnalysisHost(df=df)
        result = host.recommend_chart_type("x", ["y"])
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_at_most_three_recommendations(self):
        df = pl.DataFrame({"x": list(range(2000)), "y": list(range(2000)), "z": list(range(2000))})
        host = _AnalysisHost(df=df)
        result = host.recommend_chart_type("x", ["y", "z"])
        assert len(result) <= 3

    def test_time_column_name_triggers_line(self):
        df = pl.DataFrame({"timestamp": [1, 2, 3], "value": [10, 20, 30]})
        host = _AnalysisHost(df=df)
        host.dtypes = {"timestamp": "Int64", "value": "Int64"}
        result = host.recommend_chart_type("timestamp", ["value"])
        chart_names = [str(ct) for ct, _ in result]
        # LINE should be in recommendations for time-named column
        assert any("LINE" in name or "line" in name.lower() for name in chart_names)

    def test_fallback_single_y_gives_at_least_one(self):
        df = pl.DataFrame({"x": [1.0, 2.0], "y": [3.0, 4.0]})
        host = _AnalysisHost(df=df)
        result = host.recommend_chart_type("x", ["y"])
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# AnalysisMixin: add_virtual_column
# ---------------------------------------------------------------------------

class TestAddVirtualColumn:
    def test_add_virtual_column_success(self):
        df = pl.DataFrame({"a": [1, 2, 3]})
        host = _AnalysisHost(df=df)
        ok = host.add_virtual_column("a_doubled", pl.col("a") * 2)
        assert ok is True
        assert "a_doubled" in host.df.columns
        assert "a_doubled" in host._virtual_columns

    def test_add_virtual_column_no_df_returns_false(self):
        host = _AnalysisHost(df=None)
        ok = host.add_virtual_column("x", pl.lit(1))
        assert ok is False

    def test_add_virtual_column_bad_expr_raises_query_error(self):
        df = pl.DataFrame({"a": [1, 2]})
        host = _AnalysisHost(df=df)
        with pytest.raises(QueryError):
            host.add_virtual_column("bad", pl.col("nonexistent_column_xyz"))


# ---------------------------------------------------------------------------
# AnalysisMixin: comparison delegation smoke tests
# ---------------------------------------------------------------------------

class TestAnalysisDelegation:
    def test_align_datasets_delegates(self):
        host = _AnalysisHost(df=pl.DataFrame({"x": [1]}))
        assert host.align_datasets(["a", "b"], "key") == "aligned"

    def test_merge_datasets_delegates(self):
        host = _AnalysisHost(df=pl.DataFrame({"x": [1]}))
        assert host.merge_datasets(["a", "b"]) == "merged"

    def test_perform_statistical_test_delegates(self):
        host = _AnalysisHost(df=pl.DataFrame({"x": [1]}))
        result = host.perform_statistical_test("a", "b", "col")
        assert "p_value" in result


# ---------------------------------------------------------------------------
# DatasetMixin: property delegation
# ---------------------------------------------------------------------------

class TestDatasetMixinProperties:
    def test_max_datasets_property(self):
        host = _DatasetHost()
        assert host.MAX_DATASETS == 5

    def test_max_total_memory_property(self):
        host = _DatasetHost()
        assert host.MAX_TOTAL_MEMORY == 1024 * 1024 * 512

    def test_default_colors_property(self):
        host = _DatasetHost()
        assert isinstance(host.DEFAULT_COLORS, list)
        assert len(host.DEFAULT_COLORS) > 0

    def test_datasets_returns_dict(self):
        host = _DatasetHost()
        assert isinstance(host.datasets, dict)

    def test_dataset_count_empty(self):
        host = _DatasetHost()
        assert host.dataset_count == 0

    def test_active_dataset_id_initially_none(self):
        host = _DatasetHost()
        assert host.active_dataset_id is None


# ---------------------------------------------------------------------------
# DatasetMixin: load/remove/activate
# ---------------------------------------------------------------------------

class TestDatasetMixinMutations:
    def _load_df(self, host):
        df = pl.DataFrame({"val": [1, 2, 3]})
        did = host.load_dataset_from_dataframe(df, name="test", dataset_id="ds1")
        return did, df

    def test_load_from_dataframe_returns_id(self):
        host = _DatasetHost()
        did, _ = self._load_df(host)
        assert did == "ds1"

    def test_load_from_dataframe_clears_cache(self):
        host = _DatasetHost()
        self._load_df(host)
        assert host._cache_cleared >= 1

    def test_load_from_dataframe_syncs_loader(self):
        host = _DatasetHost()
        self._load_df(host)
        assert host._loader._df is not None

    def test_remove_dataset_returns_true_when_exists(self):
        host = _DatasetHost()
        self._load_df(host)
        result = host.remove_dataset("ds1")
        assert result is True

    def test_remove_dataset_resets_loader_when_no_datasets(self):
        host = _DatasetHost()
        self._load_df(host)
        host.remove_dataset("ds1")
        assert host._loader._df is None

    def test_remove_nonexistent_dataset_returns_false(self):
        host = _DatasetHost()
        result = host.remove_dataset("does_not_exist")
        assert result is False

    def test_clear_all_datasets_resets_state(self):
        host = _DatasetHost()
        self._load_df(host)
        host.clear_all_datasets()
        assert host.dataset_count == 0
        assert host._loader._df is None

    def test_can_load_dataset_small_size(self):
        host = _DatasetHost()
        assert host.can_load_dataset(100) is True

    def test_can_load_dataset_exceeding_limit(self):
        host = _DatasetHost()
        assert host.can_load_dataset(10 ** 12) is False

    def test_get_dataset_returns_none_for_unknown(self):
        host = _DatasetHost()
        assert host.get_dataset("unknown") is None

    def test_list_datasets_empty_initially(self):
        host = _DatasetHost()
        assert host.list_datasets() == []
