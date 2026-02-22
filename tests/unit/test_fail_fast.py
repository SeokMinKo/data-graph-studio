"""Fail Fast: core API must reject invalid input at the boundary."""
import pytest


# ── DataEngine.drop_column ─────────────────────────────────────────────────

def test_drop_column_rejects_empty_string():
    """drop_column() must raise ValueError for empty column name."""
    from data_graph_studio.core.data_engine import DataEngine
    import polars as pl
    engine = DataEngine()
    engine.update_dataframe(pl.DataFrame({"a": [1, 2, 3]}))
    with pytest.raises(ValueError, match="column name"):
        engine.drop_column("")


def test_drop_column_rejects_whitespace_only():
    """drop_column() must raise ValueError for whitespace-only column name."""
    from data_graph_studio.core.data_engine import DataEngine
    import polars as pl
    engine = DataEngine()
    engine.update_dataframe(pl.DataFrame({"a": [1]}))
    with pytest.raises(ValueError, match="column name"):
        engine.drop_column("   ")


def test_drop_column_rejects_none():
    """drop_column() must raise TypeError or ValueError for None."""
    from data_graph_studio.core.data_engine import DataEngine
    import polars as pl
    engine = DataEngine()
    engine.update_dataframe(pl.DataFrame({"a": [1]}))
    with pytest.raises((ValueError, TypeError)):
        engine.drop_column(None)


def test_drop_column_accepts_valid_name():
    """drop_column() must not raise for a valid, existing column name."""
    from data_graph_studio.core.data_engine import DataEngine
    import polars as pl
    engine = DataEngine()
    engine.update_dataframe(pl.DataFrame({"a": [1, 2], "b": [3, 4]}))
    engine.drop_column("a")  # should not raise
    assert engine.df.columns == ["b"]


# ── FileLoader.add_precision_column ────────────────────────────────────────

def test_add_precision_column_rejects_empty_string():
    """add_precision_column() must raise ValueError for empty string."""
    from data_graph_studio.core.file_loader import FileLoader
    loader = FileLoader()
    with pytest.raises(ValueError, match="column"):
        loader.add_precision_column("")


def test_add_precision_column_rejects_whitespace_only():
    """add_precision_column() must raise ValueError for whitespace-only string."""
    from data_graph_studio.core.file_loader import FileLoader
    loader = FileLoader()
    with pytest.raises(ValueError, match="column"):
        loader.add_precision_column("   ")


def test_add_precision_column_rejects_none():
    """add_precision_column() must raise TypeError or ValueError for None."""
    from data_graph_studio.core.file_loader import FileLoader
    loader = FileLoader()
    with pytest.raises((ValueError, TypeError)):
        loader.add_precision_column(None)


def test_add_precision_column_accepts_valid_name():
    """add_precision_column() must not raise for a valid column name string."""
    from data_graph_studio.core.file_loader import FileLoader
    loader = FileLoader()
    loader.add_precision_column("price")  # should not raise
    assert "price" in loader._precision_columns


# ── SelectionState.select / deselect ──────────────────────────────────────

def test_select_rejects_negative_index():
    """SelectionState.select() must raise ValueError for a negative row index."""
    from data_graph_studio.core.state import SelectionState
    sel = SelectionState()
    with pytest.raises(ValueError, match="non-negative"):
        sel.select([-1])


def test_select_rejects_mixed_valid_and_negative():
    """SelectionState.select() must raise ValueError when any index is negative."""
    from data_graph_studio.core.state import SelectionState
    sel = SelectionState()
    with pytest.raises(ValueError, match="non-negative"):
        sel.select([0, 1, -5])


def test_select_rejects_non_integer():
    """SelectionState.select() must raise ValueError for non-integer row index."""
    from data_graph_studio.core.state import SelectionState
    sel = SelectionState()
    with pytest.raises((ValueError, TypeError)):
        sel.select(["row_0"])


def test_select_accepts_valid_indices():
    """SelectionState.select() must not raise for non-negative integer indices."""
    from data_graph_studio.core.state import SelectionState
    sel = SelectionState()
    sel.select([0, 1, 5])  # should not raise
    assert sel.selected_rows == {0, 1, 5}


def test_deselect_rejects_negative_index():
    """SelectionState.deselect() must raise ValueError for a negative row index."""
    from data_graph_studio.core.state import SelectionState
    sel = SelectionState()
    sel.select([0, 1, 2])
    with pytest.raises(ValueError, match="non-negative"):
        sel.deselect([-1])


def test_deselect_accepts_valid_indices():
    """SelectionState.deselect() must not raise for non-negative integer indices."""
    from data_graph_studio.core.state import SelectionState
    sel = SelectionState()
    sel.select([0, 1, 2])
    sel.deselect([1])  # should not raise
    assert sel.selected_rows == {0, 2}
