"""Targeted tests for narrowed exception paths from Rounds 12-13.

Covers:
- comparison_algorithms.select_test_type with bad input → falls back to "ttest"
- expression_engine.evaluate with invalid expressions → raises ExpressionError
- expression_engine.validate with invalid expressions → returns (False, msg) gracefully
- export_workers ExportWorker cancelled before run → skips on_completed
- data_query.filter with unknown operator → raises QueryError
- data_query.sort on non-existent column → raises (Polars error)

All tests are Qt-free — no QApplication required.
"""
import numpy as np
import polars as pl
import pytest

from data_graph_studio.core.comparison_algorithms import select_test_type
from data_graph_studio.core.data_query import DataQuery
from data_graph_studio.core.exceptions import QueryError
from data_graph_studio.core.expression_engine import ExpressionEngine, ExpressionError
from data_graph_studio.core.export_workers import ExportWorker, ExportFormat


# ---------------------------------------------------------------------------
# comparison_algorithms.select_test_type — fallback paths
# ---------------------------------------------------------------------------


class TestSelectTestTypeFallbacks:
    def test_empty_arrays_fallback_to_ttest(self):
        """Empty arrays cannot run normality test; result must be 'ttest'."""
        result = select_test_type(np.array([]), np.array([]))
        assert result == "ttest"

    def test_single_element_arrays_fallback_to_ttest(self):
        """Arrays of length 1 cannot be tested for normality; must return 'ttest'."""
        result = select_test_type(np.array([42.0]), np.array([7.0]))
        assert result == "ttest"

    def test_two_element_arrays_fallback_to_ttest(self):
        """Arrays of length 2 cannot use Shapiro-Wilk (needs >= 3); must return 'ttest'."""
        result = select_test_type(np.array([1.0, 2.0]), np.array([3.0, 4.0]))
        assert result == "ttest"

    def test_large_arrays_always_use_ttest(self):
        """Arrays of length >= 30 always return 'ttest' (CLT shortcut, no normality test)."""
        a = np.random.default_rng(0).normal(0, 1, 50)
        b = np.random.default_rng(1).normal(0, 1, 50)
        result = select_test_type(a, b)
        assert result == "ttest"

    def test_return_is_valid_test_type(self):
        """select_test_type always returns a known string, never None or unexpected value."""
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([4.0, 5.0, 6.0])
        result = select_test_type(a, b)
        assert result in {"ttest", "mannwhitney"}


# ---------------------------------------------------------------------------
# expression_engine.evaluate — invalid expression → ExpressionError
# ---------------------------------------------------------------------------


class TestExpressionEngineErrorPaths:
    def setup_method(self):
        self.engine = ExpressionEngine()
        self.df = pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})

    def test_unknown_column_raises_expression_error(self):
        """Referencing a column that doesn't exist raises ExpressionError."""
        with pytest.raises(ExpressionError, match="not found"):
            self.engine.evaluate("nonexistent_col + 1", self.df)

    def test_unknown_function_raises_expression_error(self):
        """Calling a function that isn't registered raises ExpressionError."""
        with pytest.raises(ExpressionError, match="Unknown function"):
            self.engine.evaluate("NOTAFUNCTION(x)", self.df)

    def test_malformed_expression_raises_expression_error(self):
        """A syntactically malformed expression raises ExpressionError."""
        with pytest.raises(ExpressionError):
            self.engine.evaluate("(((x", self.df)

    def test_unterminated_string_raises_expression_error(self):
        """An unterminated string literal raises ExpressionError."""
        with pytest.raises(ExpressionError):
            self.engine.evaluate('"unclosed string', self.df)


# ---------------------------------------------------------------------------
# expression_engine.validate — graceful (False, msg) not exceptions
# ---------------------------------------------------------------------------


class TestExpressionEngineValidateGraceful:
    def setup_method(self):
        self.engine = ExpressionEngine()
        self.df = pl.DataFrame({"a": [1.0, 2.0, 3.0]})

    def test_valid_expression_returns_true_none(self):
        """validate returns (True, None) for a well-formed expression."""
        ok, msg = self.engine.validate("a + 1", self.df)
        assert ok is True
        assert msg is None

    def test_unknown_column_returns_false_with_message(self):
        """validate never raises; returns (False, str) for unknown column."""
        ok, msg = self.engine.validate("missing_col * 2", self.df)
        assert ok is False
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_bad_function_returns_false_with_message(self):
        """validate returns (False, str) for an unknown function name."""
        ok, msg = self.engine.validate("BOGUS(a)", self.df)
        assert ok is False
        assert isinstance(msg, str)

    def test_malformed_expression_returns_false_with_message(self):
        """validate returns (False, str) instead of raising on parse error."""
        ok, msg = self.engine.validate("(((a", self.df)
        assert ok is False
        assert isinstance(msg, str)


# ---------------------------------------------------------------------------
# export_workers ExportWorker — cancelled state handling
# ---------------------------------------------------------------------------


class TestExportWorkerCancelledState:
    def test_cancel_sets_is_cancelled_true(self):
        """Calling cancel() flips is_cancelled() to True."""
        worker = ExportWorker(task="data", df=None, path="/tmp/test.csv",
                              fmt=ExportFormat.CSV)
        assert worker.is_cancelled() is False
        worker.cancel()
        assert worker.is_cancelled() is True

    def test_cancelled_before_run_does_not_call_on_completed(self):
        """A worker cancelled before run() never fires on_completed."""
        completed = []
        failed = []
        worker = ExportWorker(
            task="data",
            df=pl.DataFrame({"x": [1, 2, 3]}),
            path="/tmp/nonexistent_path/out.csv",
            fmt=ExportFormat.CSV,
            on_completed=lambda p: completed.append(p),
            on_failed=lambda e: failed.append(e),
        )
        worker.cancel()
        worker.run()

        assert len(completed) == 0, "on_completed should not fire after cancel"

    def test_unknown_task_calls_on_failed(self):
        """An unrecognised task string triggers on_failed, not an unhandled exception."""
        failed = []
        completed = []
        worker = ExportWorker(
            task="nonexistent_task_type",
            path="/tmp/out.csv",
            fmt=ExportFormat.CSV,
            on_failed=lambda e: failed.append(e),
            on_completed=lambda p: completed.append(p),
        )
        # Must not raise
        worker.run()
        assert len(failed) == 1
        assert len(completed) == 0

    def test_data_export_with_none_df_calls_on_failed(self):
        """Exporting data without a DataFrame calls on_failed gracefully."""
        failed = []
        worker = ExportWorker(
            task="data",
            df=None,
            path="/tmp/out.csv",
            fmt=ExportFormat.CSV,
            on_failed=lambda e: failed.append(e),
        )
        worker.run()
        assert len(failed) == 1
        assert "DataFrame" in failed[0] or failed[0]  # any non-empty error message


# ---------------------------------------------------------------------------
# data_query narrowed exceptions
# ---------------------------------------------------------------------------


class TestDataQueryNarrowedExceptions:
    def setup_method(self):
        self.dq = DataQuery()
        self.df = pl.DataFrame({"val": [1, 2, 3, 4, 5]})

    def test_filter_unknown_operator_raises_query_error(self):
        """An unrecognised operator string raises the narrowed QueryError."""
        with pytest.raises(QueryError):
            self.dq.filter(self.df, "val", "UNKNOWN_OP", 3)

    def test_filter_none_df_returns_none(self):
        """filter(None, ...) returns None — contract for null DataFrames."""
        result = self.dq.filter(None, "val", "gt", 0)
        assert result is None

    def test_sort_none_df_returns_none(self):
        """sort(None, ...) returns None — contract for null DataFrames."""
        result = self.dq.sort(None, ["val"])
        assert result is None

    def test_sample_none_df_returns_none(self):
        """sample(None, ...) returns None — contract for null DataFrames."""
        result = self.dq.sample(None, n=5)
        assert result is None

    def test_get_slice_none_df_returns_none(self):
        """get_slice(None, ...) returns None — contract for null DataFrames."""
        result = self.dq.get_slice(None, 0, 5)
        assert result is None

    def test_sort_nonexistent_column_raises(self):
        """sort on a column name that doesn't exist propagates an exception."""
        with pytest.raises(Exception):
            self.dq.sort(self.df, ["zzz_nonexistent"])
