"""Integration tests: core pipeline from file load to filtered output.

Tests the complete data path across two or more core layers:
    DataEngine.load_file → engine.df → FilteringManager.apply_filters

No UI, no Qt — pure core layer integration. This is the cross-layer
integration coverage flagged as missing in the GOAT audit.
"""
from pathlib import Path

import polars as pl
import pytest

from data_graph_studio.core.data_engine import DataEngine
from data_graph_studio.core.exceptions import DataLoadError
from data_graph_studio.core.filtering import FilterOperator, FilterType, FilteringManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """CSV with numeric and string columns (no NaN)."""
    p = tmp_path / "sample.csv"
    p.write_text(
        "name,score,active\n"
        "alice,80,true\n"
        "bob,45,false\n"
        "carol,90,true\n"
    )
    return p


@pytest.fixture
def nan_csv(tmp_path: Path) -> Path:
    """CSV where one score row is missing (becomes NaN when read as float)."""
    p = tmp_path / "nan_sample.csv"
    p.write_text(
        "name,score\n"
        "alice,80.0\n"
        "bob,\n"
        "carol,90.0\n"
        "dave,45.0\n"
    )
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCoreLoadFilter:
    """End-to-end tests: DataEngine.load_file → FilteringManager.apply_filters."""

    def test_load_then_filter_returns_correct_rows(self, sample_csv: Path) -> None:
        """Full pipeline: load CSV → filter by score > 50 → only alice and carol."""
        engine = DataEngine()
        loaded = engine.load_file(str(sample_csv))
        assert loaded is True

        df = engine.df
        assert df is not None
        assert df.shape == (3, 3)

        # Layer 2: filtering
        mgr = FilteringManager()
        mgr.create_scheme("main")
        mgr.add_filter(
            "main",
            "score",
            FilterOperator.GREATER_THAN,
            50,
            filter_type=FilterType.NUMERIC,
        )
        result = mgr.apply_filters("main", df)

        assert len(result) == 2
        names = set(result["name"].to_list())
        assert names == {"alice", "carol"}
        assert "bob" not in names

    def test_load_nonexistent_raises_data_load_error(self, tmp_path: Path) -> None:
        """DataLoadError is raised when the file does not exist."""
        engine = DataEngine()
        missing = str(tmp_path / "ghost.csv")

        with pytest.raises(DataLoadError):
            engine.load_file(missing)

    def test_filter_nan_excluded_from_range(self, tmp_path: Path) -> None:
        """NaN values are excluded from numeric range filter results.

        Polars treats NaN as greater than all finite values under IEEE 754
        total ordering, so a naive gt/ge filter silently passes NaN rows.
        The NaN fix in FilteringManager._apply_single_filter must strip them.
        This test verifies the fix is active end-to-end: from a DataFrame
        containing NaN through FilteringManager.apply_filters.
        """
        # Build the DataFrame directly so we can inject a true float NaN
        # (CSV nulls become Polars null, not NaN; we want NaN specifically).
        df = pl.DataFrame({
            "name": ["alice", "bob_nan", "carol", "dave"],
            "score": [80.0, float("nan"), 90.0, 45.0],
        })

        mgr = FilteringManager()
        mgr.create_scheme("range_test")
        mgr.add_filter(
            "range_test",
            "score",
            FilterOperator.GREATER_THAN,
            50.0,
            filter_type=FilterType.NUMERIC,
        )
        result = mgr.apply_filters("range_test", df)

        # bob_nan has NaN score — must not appear in results
        assert "bob_nan" not in result["name"].to_list()

        # alice and carol should be present (both > 50)
        names = set(result["name"].to_list())
        assert names == {"alice", "carol"}

        # No NaN values should survive the filter
        nan_count = result["score"].is_nan().sum()
        assert nan_count == 0, f"Expected 0 NaN rows, got {nan_count}"

    def test_load_csv_then_multi_filter(self, sample_csv: Path) -> None:
        """Load CSV → apply two chained filters → single matching row.

        Verifies that multiple filters in one scheme compose correctly
        across the DataEngine → FilteringManager boundary.
        """
        engine = DataEngine()
        engine.load_file(str(sample_csv))
        df = engine.df

        mgr = FilteringManager()
        mgr.create_scheme("combo")
        # score > 50
        mgr.add_filter(
            "combo",
            "score",
            FilterOperator.GREATER_THAN,
            50,
            filter_type=FilterType.NUMERIC,
        )
        # score < 85  → only alice (80) survives; carol (90) is excluded
        mgr.add_filter(
            "combo",
            "score",
            FilterOperator.LESS_THAN,
            85,
            filter_type=FilterType.NUMERIC,
        )
        result = mgr.apply_filters("combo", df)

        assert len(result) == 1
        assert result["name"][0] == "alice"
